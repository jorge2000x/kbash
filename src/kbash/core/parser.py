"""Parser estático de scripts anotados (SPEC.md §4).

Regra inviolável (§4.1): o parser **nunca executa** nada do script — apenas
tokeniza linhas ``#@`` com regras de shell (``shlex``) e valida o resultado (§4.6).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .contratos import ensure
from .errors import Diagnostics, ParseError, ValidationError
from .model import (
    RUNTIME_VERSION_SUPPORTED,
    Script,
    is_valid_id,
    slugify,
)

from .parser_opcoes import _OpcoesMixin
from .parser_passos import _PassosMixin
from .parser_base import (
    ACTION_ATTRS,
    ANNOTATION,
    ASSIGNMENT_RE,
    BLOCK_START,
    FALSY,
    FUNCTION_KINDS,
    KNOWN_DIRECTIVES,
    OPTION_ATTRS,
    ParseResult,
    STEP_ATTRS,
    TOP_LEVEL_OK,
    TRUTHY,
    _Block,
    _bool,
    _brace_delta,
    _match_function,
    _strip_comment,
    _tokenize,
    _unquote,
    sha256_of,
)

__all__ = ["ParseResult", "check_script", "parse_script", "parse_text", "sha256_of"]


class _Parser(_OpcoesMixin, _PassosMixin):
    def __init__(self, text: str, path: Path | None) -> None:
        self.text = text
        self.path = path
        self.diag = Diagnostics(path)
        self.header: dict[str, str] = {}
        self.header_lines: dict[str, int] = {}
        self.header_desc: list[str] = []
        self.blocks: list[_Block] = []
        self.functions: set[str] = set()
        self.resolved_functions: set[str] = set()
        self._loose: list[tuple[int, str]] = []
        self._pending: _Block | None = None
        self._seen_ids: dict[str, str] = {}
        self._depth = 0
        self._runtime_version = 0
        self._name = ""
        self._id = ""
        self._requires: tuple[str, ...] = ()
        self._strict = True

    # -- linha a linha ----------------------------------------------------
    def parse(self) -> None:
        first_code_line: int | None = None
        for number, raw in enumerate(self.text.splitlines(), start=1):
            code = _strip_comment(raw)
            annotation = raw.lstrip().startswith(ANNOTATION)
            if not annotation:
                if code.strip():
                    first_code_line = first_code_line or number
                self._handle_code(code, number)
            else:
                self._handle_annotation(raw, number)
        if self._pending is not None and self._pending.kind in FUNCTION_KINDS:
            raise ParseError(
                f"bloco #@{self._pending.kind} {self._pending.id!r} sem definição de função",
                self.path,
                self._pending.line,
            )
        self._close_pending()
        self._check_loose_top_level(first_code_line)

    def _close_pending(self) -> None:
        """Fecha o bloco de option aberto; steps precisam da definição (§4.1)."""
        if self._pending is not None and self._pending.kind == "option":
            self.blocks.append(self._pending)
            self._pending = None

    def _handle_annotation(self, raw: str, number: int) -> None:
        body = raw.lstrip()[len(ANNOTATION):]
        # corpo só com espaço (inclusive \xa0) também é vazio: split() daria lista vazia
        if not body.strip():
            self.diag.warning("anotação vazia", number)
            return
        parts = body.split(None, 1)
        key = parts[0]
        rest = parts[1].strip() if len(parts) > 1 else ""
        if key not in KNOWN_DIRECTIVES:
            self.diag.warning(f"diretiva desconhecida {ANNOTATION}{key}", number)
            return
        if key in BLOCK_START:
            self._start_block(key, rest, number)
            return
        if key in ("desc", "description"):
            text = " ".join(_tokenize(rest, number, self.path)) if rest else ""
            if self._pending is not None:
                self._pending.descs.append(text)
                self._pending.desc_lines.append(number)
            else:
                self.header_desc.append(text)
            return
        if self._pending is not None and key in (STEP_ATTRS | ACTION_ATTRS | OPTION_ATTRS):
            if key in self._pending.attrs:
                self.diag.warning(f"{ANNOTATION}{key} repetido no bloco {self._pending.id!r}", number)
            self._pending.attrs[key] = rest
            self._pending.attr_lines[key] = number
            return
        if self._pending is not None:
            self.diag.warning(
                f"{ANNOTATION}{key} não é válido em #@{self._pending.kind}", number
            )
            return
        if key in self.header and key != "description":
            self.diag.warning(f"{ANNOTATION}{key} repetido no cabeçalho", number)
        self.header[key] = rest
        self.header_lines[key] = number

    def _start_block(self, kind: str, rest: str, number: int) -> None:
        tokens = _tokenize(rest, number, self.path)
        if not tokens:
            raise ParseError(f"{ANNOTATION}{kind} sem id", self.path, number)
        identifier = tokens[0]
        if not is_valid_id(identifier):
            raise ParseError(
                f"id inválido {identifier!r} (esperado [a-z][a-z0-9_]*)", self.path, number
            )
        # §4.6 — id duplicado entre steps ou entre opções é erro.
        if identifier in self._seen_ids:
            first = self._seen_ids[identifier]
            raise ValidationError(
                f"id duplicado {identifier!r} (já declarado em {ANNOTATION}{first})",
                self.path,
                number,
            )
        if self._pending is not None:
            if self._pending.kind in FUNCTION_KINDS:
                raise ParseError(
                    f"bloco #@{self._pending.kind} {self._pending.id!r} sem definição de função"
                    f" (apareceu {ANNOTATION}{kind} antes)",
                    self.path,
                    self._pending.line,
                )
            if self._pending.id == identifier:
                raise ValidationError(
                    f"id duplicado {identifier!r} (bloco #@option ainda aberto)", self.path, number
                )
            self._close_pending()  # options consecutivas
        self._seen_ids[identifier] = kind
        self._pending = _Block(kind=kind, id=identifier, line=number)
        # §4.1/§4.3 — atributos na própria linha: type=choice label="Editor" …
        for extra in tokens[1:]:
            key, separator, value = extra.partition("=")
            if not separator:
                self.diag.warning(
                    f"argumento extra {extra!r} ignorado em {ANNOTATION}{kind}", number
                )
                continue
            self._pending.attrs[key] = value
            self._pending.attr_lines[key] = number

    def _handle_code(self, code: str, number: int) -> None:
        stripped = code.strip()
        if not stripped:
            return
        if self._pending is not None and self._pending.kind == "option":
            self._close_pending()  # a linha de código encerra o bloco de option
        function = _match_function(code)
        if function is not None:
            self._on_function(function[0], code)
            return
        if self._pending is not None:
            raise ParseError(
                f"#@{self._pending.kind} {self._pending.id!r} deve ser seguido"
                f" da definição da função (encontrado: {stripped[:40]!r})",
                self.path,
                self._pending.line,
            )
        if stripped in ("{", "}"):
            self._depth += 1 if stripped == "{" else -1
            return
        if self._depth <= 0:
            self._loose.append((number, stripped))

    def _on_function(self, name: str, code: str) -> None:
        self._depth += _brace_delta(code)
        self.functions.add(name)
        block = self._pending
        if block is not None and block.kind in FUNCTION_KINDS:
            block.attrs["__defined__"] = name
            self.resolved_functions.add(name)
            self.blocks.append(block)
            self._pending = None

    def _check_loose_top_level(self, first_code_line: int | None) -> None:
        """§4.5 — warning heurístico para comandos soltos fora de funções."""
        if first_code_line is None:
            return
        for number, statement in self._loose:
            head = statement.split()[0]
            if head in TOP_LEVEL_OK or ASSIGNMENT_RE.match(statement):
                continue
            self.diag.warning(
                f"comando de nível superior {head!r} roda a cada step"
                " (mova-o para dentro de uma função)",
                number,
            )

    # -- validação e construção -----------------------------------------
    def build(self, path: Path, sha256: str) -> Script:
        self._parse_header()
        options = self._build_options()
        steps = self._build_steps()
        actions = self._build_actions()
        self._check_cycles(steps)
        self._check_show_if(options)
        self._check_needs_step(options, steps)
        script = Script(
            path=path,
            sha256=sha256,
            runtime_version=self._runtime_version,
            name=self._name,
            id=self._id,
            description=" ".join(self.header_desc),
            version=self.header.get("version", "").strip(),
            author=self.header.get("author", "").strip(),
            icon=_unquote(self.header.get("icon", "").strip()) or None,
            requires=self._requires,
            strict=self._strict,
            options=tuple(options),
            steps=tuple(steps),
            actions=tuple(actions),
        )
        return script

    def _parse_header(self) -> None:
        path = self.path
        if "runtime" not in self.header:
            raise ParseError("diretiva obrigatória ausente: #@runtime", path, None)
        raw_runtime = self.header["runtime"].strip()
        try:
            self._runtime_version = int(raw_runtime)
        except ValueError:
            line = self.header_lines["runtime"]
            raise ParseError(f"#@runtime inválido: {raw_runtime!r}", path, line) from None
        if self._runtime_version < 1:
            raise ValidationError(
                f"#@runtime deve ser >= 1 (recebido {self._runtime_version})",
                path,
                self.header_lines["runtime"],
            )
        if self._runtime_version > RUNTIME_VERSION_SUPPORTED:
            raise ValidationError(
                f"#@runtime {self._runtime_version} é mais novo que a versão suportada"
                f" ({RUNTIME_VERSION_SUPPORTED})",
                path,
                self.header_lines["runtime"],
            )
        if "name" not in self.header or not self.header["name"].strip():
            raise ParseError("diretiva obrigatória ausente: #@name", path, None)
        self._name = " ".join(_tokenize(self.header["name"], self.header_lines["name"], path))
        raw_id = _unquote(self.header.get("id", "").strip())
        if raw_id and not is_valid_id(raw_id.replace(".", "_")) and "." not in raw_id:
            self.diag.warning(f"#@id {raw_id!r} fora do padrão esperado", self.header_lines["id"])
        self._id = raw_id or slugify(self._name)
        requires_raw = self.header.get("requires", "")
        self._requires = tuple(
            item for item in (part.strip() for part in requires_raw.split(",")) if item
        )
        self._strict = _bool(self.header.get("strict"), True)
        if "strict" in self.header:
            text = self.header["strict"].strip().lower()
            if text not in TRUTHY | FALSY:
                self.diag.warning(
                    f"#@strict {self.header['strict']!r} não é booleano (usando padrão true)",
                    self.header_lines["strict"],
                )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


@ensure(
    lambda result: len({o.id for o in result.script.options} | {s.id for s in result.script.steps}
                       | {a.id for a in result.script.actions})
    == len(result.script.options) + len(result.script.steps) + len(result.script.actions),
    "ids de opções, steps e ações são únicos entre si (§4.6)",
)
@ensure(
    lambda result: all(s.timeout is None or s.timeout > 0 for s in result.script.steps)
    and all(a.timeout > 0 for a in result.script.actions),
    "timeout é nulo ou positivo",
)
def parse_text(text: str, path: Path | None = None) -> ParseResult:
    """Parseia o conteúdo de um script (sem tocar no disco além do nome).

    :raises ParseError: sintaxe ou diretiva inválida, com linha (§4.6).
    :raises ValidationError: referência inexistente, id duplicado, ciclo etc. (§4.6).
    """
    if text.startswith("#!"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    parser = _Parser(text, path)
    parser.parse()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    script = parser.build(path or Path("<script>"), digest)
    return ParseResult(script=script, warnings=tuple(parser.diag.warnings), source=text)


def parse_script(path: Path) -> Script:
    """Lê e valida ``path``; levanta :class:`ParseError`/:class:`ValidationError` (§4.6).

    O caminho é normalizado para absoluto: o executor roda cada step com
    ``cwd=$HOME`` (§7.1), então um caminho relativo quebraria o ``source``.
    """
    path = Path(path).expanduser().resolve()
    return parse_text(_read_text(path), path).script


def check_script(path: Path) -> tuple[Script | None, Diagnostics]:
    """§12 ``check``: devolve o script (se válido) e **todos** os diagnósticos."""
    path = Path(path)
    diag = Diagnostics(path)
    try:
        result = parse_text(_read_text(path), path)
    except (ParseError, ValidationError) as exc:
        diag.items.append(exc.diagnostic)
        return None, diag
    diag.items.extend(result.warnings)
    return result.script, diag

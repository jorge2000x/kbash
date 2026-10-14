"""Parser estático de scripts anotados (SPEC.md §4).

Regra inviolável (§4.1): o parser **nunca executa** nada do script — apenas
tokeniza linhas ``#@`` com regras de shell (``shlex``) e valida o resultado (§4.6).
"""

from __future__ import annotations

import hashlib
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from .errors import Diagnostics, ParseError, ValidationError
from .model import (
    ON_ERROR_VALUES,
    NON_VALUE_TYPES,
    OPTION_TYPES,
    is_allowed_link,
    RUNTIME_VERSION_SUPPORTED,
    Option,
    Script,
    Step,
    is_valid_date,
    is_valid_id,
    is_valid_number,
    is_valid_time,
    slugify,
)

__all__ = ["ParseResult", "parse_text", "parse_script", "check_script", "sha256_of"]

ANNOTATION = "#@"
BLOCK_START = ("step", "option")

#: §4.1 — ``nome() {``, ``function nome {``, ``function nome() {}`` e variantes
#: de uma linha (``nome() { cmd; }``). Aregex é de *prefixo*; refinamos abaixo
#: para não confundir com atribuição de array (``files=(a b)``).
FUNCTION_HEAD_RE = re.compile(r"^\s*(?:(function)\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*(.*)$")
#: Linha só de atribuição (``PATH=/x``, ``LC_ALL=C``) — definição, não comando.
ASSIGNMENT_RE = re.compile(r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*\+?=\S*(\s.*)?|declare\s|local\s|export\s+\w+=)")

#: Top-level tolerado pelo heurístico do §4.5 (definições e ajustes de shell).
TOP_LEVEL_OK = frozenset(
    {
        ":", ".", "set", "shopt", "export", "readonly", "declare", "typeset", "local",
        "unset", "alias", "unalias", "trap", "return", "exit", "true", "false", "eval",
        "umask", "ulimit", "source", "wait", "read",
    }
)

TRUTHY = frozenset({"1", "true", "on", "yes", "sim", "y"})
FALSY = frozenset({"0", "false", "off", "no", "nao", "não", "n"})

STEP_ATTRS = frozenset(
    {"title", "desc", "group", "default", "required", "depends", "root", "timeout", "on_error", "function"}
)
OPTION_ATTRS = frozenset(
    {"type", "label", "default", "choices", "required", "help",
     "min", "max", "step", "filters", "pattern", "minlen", "maxlen", "multiple",
     "show_if", "url", "needs_step"}
)
HEADER_ATTRS = frozenset(
    {"runtime", "name", "id", "description", "version", "author", "icon", "requires", "strict"}
)
KNOWN_DIRECTIVES = HEADER_ATTRS | {"step", "option"} | STEP_ATTRS | OPTION_ATTRS


def sha256_of(path: Path) -> str:
    """§5/§9.1 — hash do arquivo do script."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class _Block:
    kind: str  # "step" | "option"
    id: str
    line: int
    attrs: dict[str, str] = field(default_factory=dict)
    attr_lines: dict[str, int] = field(default_factory=dict)
    descs: list[str] = field(default_factory=list)
    desc_lines: list[int] = field(default_factory=list)

    def attr_line(self, key: str) -> int:
        return self.attr_lines.get(key, self.line)

    def get(self, key: str, fallback: str | None = None) -> str | None:
        return self.attrs.get(key, fallback)


@dataclass
class ParseResult:
    """Resultado do parse: script + diagnósticos de warning (§4.6/§4.5)."""

    script: Script
    warnings: tuple = ()
    source: str = ""

    @property
    def path(self) -> Path:
        return self.script.path


def _strip_comment(line: str) -> str:
    """Remove o comentário respeitando aspas simples e duplas."""
    quote: str | None = None
    for index, char in enumerate(line):
        if quote:
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == "#":
            return line[:index]
    return line


def _match_function(code: str) -> tuple[str, bool] | None:
    """§4.1 — devolve ``(nome, abriu_chave)`` se a linha define uma função."""
    match = FUNCTION_HEAD_RE.match(code)
    if match is None:
        return None
    keyword, name, rest = bool(match.group(1)), match.group(2), match.group(3)
    if rest.startswith("()"):
        rest = rest[2:]
    elif rest.startswith("("):
        return None  # files=(a b) — atribuição de array, não definição
    elif not keyword:
        return None  # "comando argumentos" (echo, apt-get, ...)
    tail = rest.lstrip()
    if tail.startswith("{"):
        return name, True
    if tail and not tail.startswith(";"):
        return None
    return name, False


def _brace_delta(code: str) -> int:
    """Saldo de ``{``/``}`` na linha, ignorando o que está entre aspas."""
    delta = 0
    quote: str | None = None
    for char in code:
        if quote:
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == "{":
            delta += 1
        elif char == "}":
            delta -= 1
    return delta


def _tokenize(value: str, line: int, path: Path | None) -> list[str]:
    """Tokeniza com regras de shell (§4.1)."""
    lexer = shlex.shlex(value, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError as exc:  # aspas desbalanceadas etc.
        raise ParseError(f"não foi possível tokenizar a anotação: {exc}", path, line) from exc


def _unquote(value: str) -> str:
    return value[1:-1] if len(value) >= 2 and value[0] == value[-1] == '"' else value


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    text = value.strip().lower()
    if text in TRUTHY:
        return True
    if text in FALSY:
        return False
    return default


def _flag(value: str | None, default: bool = True) -> bool:
    """§4.4 — flag: ausente usa ``default``; forma nua (``#@root``) liga."""
    if value is None:
        return default
    if not value.strip():
        return True
    return _bool(value, default)


class _Parser:
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

    # -- utilidades -------------------------------------------------------
    def _error(self, message: str, line: int | None) -> None:
        raise ValidationError(message, self.path, line)

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
        if self._pending is not None and self._pending.kind == "step":
            raise ParseError(
                f"bloco #@step {self._pending.id!r} sem definição de função",
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
        if not body:
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
        if self._pending is not None and key in (STEP_ATTRS | OPTION_ATTRS):
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
            if self._pending.kind == "step":
                raise ParseError(
                    f"bloco #@step {self._pending.id!r} sem definição de função"
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
        if block is not None and block.kind == "step":
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
                " (mov[a]-o para dentro de uma função)",
                number,
            )

    # -- validação e construção -----------------------------------------
    def build(self, path: Path, sha256: str) -> Script:
        self._parse_header()
        options = self._build_options()
        steps = self._build_steps()
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
            raise ParseError(f"#@runtime inválido: {raw_runtime!r}", path, self.header_lines["runtime"]) from None
        if self._runtime_version < 1:
            raise ValidationError(
                f"#@runtime deve ser >= 1 (recebido {self._runtime_version})", path, self.header_lines["runtime"]
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

    def _build_options(self) -> list[Option]:
        options: list[Option] = []
        for block in self.blocks:
            if block.kind != "option":
                continue
            option = self._build_option(block)
            options.append(option)
        return options

    def _build_option(self, block: _Block) -> Option:
        path = self.path
        kind = (block.get("type") or "string").strip() or "string"
        if kind not in OPTION_TYPES:
            self.diag.warning(
                f"type={kind!r} desconhecido em #@option {block.id!r}; usando 'string'",
                block.attr_line("type"),
            )
            kind = "string"
        label = _unquote((block.get("label") or block.id).strip())
        default_raw = block.get("default")
        default = _unquote(default_raw.strip()) if default_raw is not None else None
        choices_raw = block.get("choices")
        choices = tuple(
            part.strip()
            for part in _unquote((choices_raw or "").strip()).split(",")
            if part.strip()
        )
        required = _flag(block.get("required"), False)
        help_text = " ".join(_tokenize(block.get("help") or "", block.line, path))
        if kind in NON_VALUE_TYPES:
            # §4.3: só exibem texto/link; não têm valor, então saem antes das
            # checagens de valor (default, faixa, pattern…)
            url = self._check_display_option(block, kind)
            if kind == "link":
                label = _unquote((block.get("label") or url).strip())
            return Option(
                id=block.id,
                type=kind,
                label=label,
                help=help_text,
                url=url,
                show_if=self._parse_show_if(block),
                needs_step=self._parse_needs_step(block),
                line=block.line,
            )
        if kind in ("choice", "multi"):
            if not choices:
                self._error(
                    f"#@option {block.id!r} type={kind} exige choices", block.line
                )
            if default and default not in choices:
                self._error(
                    f"default={default!r} de #@option {block.id!r} não está em choices"
                    f" ({', '.join(choices)})",
                    block.attr_line("default"),
                )
        if kind == "bool" and default is not None:
            if default.strip().lower() not in TRUTHY | FALSY:
                self.diag.warning(
                    f"default={default!r} de #@option {block.id!r} (bool) não é booleano",
                    block.attr_line("default"),
                )
        if required and kind == "bool":
            self.diag.warning(
                f"#@option {block.id!r} é required mas do tipo bool", block.attr_line("required")
            )
        minimum, maximum, step = self._parse_range(block, kind)
        filters = tuple(
            part.strip()
            for part in _unquote((block.get("filters") or "").strip()).split(",")
            if part.strip()
        )
        if filters and kind != "file":
            self.diag.warning(
                f"filters de #@option {block.id!r} só vale para type=file",
                block.attr_line("filters"),
            )
        if kind in ("number", "slider"):
            self._check_numeric_default(block, default, minimum, maximum)
        if kind == "date" and default:
            if not is_valid_date(default):
                self._error(
                    f"default={default!r} de #@option {block.id!r} não é data ISO (AAAA-MM-DD)",
                    block.attr_line("default"),
                )
        if kind == "time" and default:
            if not is_valid_time(default):
                self._error(
                    f"default={default!r} de #@option {block.id!r} não é hora (HH:MM)",
                    block.attr_line("default"),
                )
        pattern, minlen, maxlen, multiple = self._parse_text_checks(block, kind, default)
        show_if = self._parse_show_if(block)
        return Option(
            id=block.id,
            type=kind,
            label=label,
            default=default,
            choices=choices,
            required=required,
            help=help_text,
            minimum=minimum,
            maximum=maximum,
            step=step,
            filters=filters,
            pattern=pattern,
            minlen=minlen,
            maxlen=maxlen,
            multiple=multiple,
            show_if=show_if,
            needs_step=self._parse_needs_step(block),
            line=block.line,
        )

    def _parse_needs_step(self, block: _Block) -> str | None:
        """``needs_step=<id>``: id do step a que a opção pertence (ou ``None``)."""
        raw = block.get("needs_step")
        if raw is None or not raw.strip():
            return None
        return raw.strip()

    def _check_needs_step(self, options: list[Option], steps: list[Step]) -> None:
        """Ligação opção → step: o step precisa existir."""
        step_ids = {step.id for step in steps}
        lines = {
            block.id: block.attr_line("needs_step")
            for block in self.blocks
            if block.kind == "option" and block.get("needs_step")
        }
        for option in options:
            if option.needs_step is not None and option.needs_step not in step_ids:
                self._error(
                    f"needs_step de #@option {option.id!r} aponta para step inexistente "
                    f"{option.needs_step!r}",
                    lines.get(option.id, option.line),
                )

    def _check_display_option(self, block: _Block, kind: str) -> str:
        """§4.3: valida ``paragraph`` (precisa de ``label``) e ``link`` (precisa de
        ``url`` http/https). Devolve a ``url`` ("" para ``paragraph``)."""
        url = _unquote((block.get("url") or "").strip())
        if kind == "paragraph" and not (block.get("label") or "").strip():
            self._error(
                f"#@option {block.id!r} type=paragraph exige label (o texto mostrado)",
                block.line,
            )
        if kind == "link":
            if not url:
                self._error(f"#@option {block.id!r} type=link exige url", block.line)
            elif not is_allowed_link(url):
                self._error(
                    f"url={url!r} de #@option {block.id!r} precisa começar com http:// ou https://",
                    block.attr_line("url"),
                )
        elif block.get("url") is not None:
            self.diag.warning(
                f"url de #@option {block.id!r} só vale para type=link",
                block.attr_line("url"),
            )
        for attr in ("default", "required", "choices", "filters", "multiple", "pattern",
                     "minlen", "maxlen", "min", "max", "step"):
            if block.get(attr) is not None:
                self.diag.warning(
                    f"{attr}= de #@option {block.id!r} não se aplica a type={kind} (ignorado)",
                    block.attr_line(attr),
                )
        return url

    def _parse_show_if(self, block: _Block) -> tuple[tuple[str, str], ...]:
        """§4.3: `show_if="outra=valor,outra2=valor2"` → pares `(id, valor)`."""
        raw = block.get("show_if")
        if raw is None:
            return ()
        pairs: list[tuple[str, str]] = []
        for part in _unquote(raw.strip()).split(","):
            item = part.strip()
            if not item:
                continue
            if "=" not in item:
                self._error(
                    f"show_if={item!r} de #@option {block.id!r} precisa ser id=valor",
                    block.attr_line("show_if"),
                )
                continue
            ref_id, _, expected = item.partition("=")
            ref_id, expected = ref_id.strip(), expected.strip()
            if not ref_id or not is_valid_id(ref_id):
                self._error(
                    f"show_if referencia id inválido {ref_id!r} em #@option {block.id!r}",
                    block.attr_line("show_if"),
                )
                continue
            pairs.append((ref_id, expected))
        return tuple(pairs)

    def _parse_range(self, block: _Block, kind: str) -> tuple[str | None, str | None, str | None]:
        """§4.3: `min`/`max`/`step` de `number`/`slider` (strings numéricas ou `None`).

        O `slider` sem faixa usa `0`/`100`/`1` (SPEC.md §4.3).
        """
        raw_min = block.get("min")
        raw_max = block.get("max")
        raw_step = block.get("step")
        minimum = _unquote(raw_min.strip()) if raw_min is not None else None
        maximum = _unquote(raw_max.strip()) if raw_max is not None else None
        step = _unquote(raw_step.strip()) if raw_step is not None else None
        if kind == "slider":
            minimum = minimum if minimum not in (None, "") else "0"
            maximum = maximum if maximum not in (None, "") else "100"
            step = step if step not in (None, "") else "1"
        if kind not in ("number", "slider"):
            if raw_min is not None or raw_max is not None or raw_step is not None:
                self.diag.warning(
                    f"min/max/step de #@option {block.id!r} só vale para type=number/slider",
                    block.line,
                )
            return None, None, None
        for name, bound in (("min", minimum), ("max", maximum), ("step", step)):
            if bound not in (None, "") and not is_valid_number(bound):
                self._error(
                    f"{name}={bound!r} de #@option {block.id!r} não é número",
                    block.attr_line(name),
                )
        if step not in (None, "") and float(step) <= 0:
            self._error(
                f"step={step!r} de #@option {block.id!r} precisa ser > 0",
                block.attr_line("step"),
            )
        numbers = [float(bound) for bound in (minimum, maximum) if bound not in (None, "")]
        if len(numbers) == 2 and numbers[0] > numbers[1]:
            self._error(
                f"min={minimum!r} maior que max={maximum!r} em #@option {block.id!r}",
                block.attr_line("min"),
            )
        return minimum or None, maximum or None, step or None

    def _check_numeric_default(
        self,
        block: _Block,
        default: str | None,
        minimum: str | None,
        maximum: str | None,
    ) -> None:
        """§4.3: `default` de `number`/`slider` precisa ser numérico e caber na faixa."""
        if not default:
            return
        if not is_valid_number(default):
            self._error(
                f"default={default!r} de #@option {block.id!r} não é número",
                block.attr_line("default"),
            )
            return
        value = float(default)
        if minimum not in (None, "") and value < float(minimum):
            self._error(
                f"default={default!r} de #@option {block.id!r} abaixo de min={minimum!r}",
                block.attr_line("default"),
            )
        if maximum not in (None, "") and value > float(maximum):
            self._error(
                f"default={default!r} de #@option {block.id!r} acima de max={maximum!r}",
                block.attr_line("default"),
            )

    def _parse_text_checks(
        self, block: _Block, kind: str, default: str | None
    ) -> tuple[str, str | None, str | None, bool]:
        """§4.3: `pattern`/`minlen`/`maxlen` (`string`/`password`/`text`) e
        `multiple` (`file`). Devolve `(pattern, minlen, maxlen, multiple)`."""
        raw_pattern = block.get("pattern")
        pattern = _unquote(raw_pattern.strip()) if raw_pattern is not None else ""
        raw_minlen = block.get("minlen")
        raw_maxlen = block.get("maxlen")
        minlen = _unquote(raw_minlen.strip()) if raw_minlen is not None else None
        maxlen = _unquote(raw_maxlen.strip()) if raw_maxlen is not None else None
        multiple = _flag(block.get("multiple"), False)
        if kind in ("string", "password", "text"):
            if pattern:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    self._error(
                        f"pattern={pattern!r} de #@option {block.id!r} é regex inválida: {exc}",
                        block.attr_line("pattern"),
                    )
                else:
                    if default and not re.fullmatch(pattern, default):
                        self._error(
                            f"default={default!r} de #@option {block.id!r} não casa com pattern",
                            block.attr_line("default"),
                        )
            for name, bound in (("minlen", minlen), ("maxlen", maxlen)):
                if bound is not None and (not bound.isdigit() or int(bound) < 0):
                    self._error(
                        f"{name}={bound!r} de #@option {block.id!r} precisa ser inteiro >= 0",
                        block.attr_line(name),
                    )
            if (minlen is not None and maxlen is not None
                    and minlen.isdigit() and maxlen.isdigit()
                    and int(minlen) > int(maxlen)):
                self._error(
                    f"minlen={minlen!r} maior que maxlen={maxlen!r} em #@option {block.id!r}",
                    block.attr_line("minlen"),
                )
            if default:
                if minlen is not None and minlen.isdigit() and len(default) < int(minlen):
                    self._error(
                        f"default de #@option {block.id!r} menor que minlen={minlen!r}",
                        block.attr_line("default"),
                    )
                if maxlen is not None and maxlen.isdigit() and len(default) > int(maxlen):
                    self._error(
                        f"default de #@option {block.id!r} maior que maxlen={maxlen!r}",
                        block.attr_line("default"),
                    )
        else:
            if raw_pattern is not None or raw_minlen is not None or raw_maxlen is not None:
                self.diag.warning(
                    f"pattern/minlen/maxlen de #@option {block.id!r} só vale para string/password/text",
                    block.line,
                )
            pattern, minlen, maxlen = "", None, None
        if multiple and kind != "file":
            self.diag.warning(
                f"multiple de #@option {block.id!r} só vale para type=file",
                block.attr_line("multiple"),
            )
            multiple = False
        return pattern, minlen, maxlen, multiple

    def _build_steps(self) -> list[Step]:
        steps: list[Step] = []
        for block in self.blocks:
            if block.kind != "step":
                continue
            steps.append(self._build_step(block))
        return steps

    def _build_step(self, block: _Block) -> Step:
        function = (block.get("function") or block.id).strip()
        defined = block.attrs.get("__defined__")
        if function == block.id and defined is not None and defined != block.id:
            # §4.4 — o id deve ser igual ao nome da função (ou use function=)
            self._error(
                f"step {block.id!r}: a função definida é {defined!r},"
                " o id deve ser igual ao nome da função (ou use #@function)",
                block.line,
            )
        if function not in self.functions:
            self._error(
                f"função {function!r} do step {block.id!r} não encontrada no script", block.line
            )
        title = _unquote((block.get("title") or block.id).strip())
        group = block.get("group")
        group = _unquote(group.strip()) if group else None
        depends_raw = block.get("depends") or ""
        depends = tuple(
            item for item in (part.strip() for part in depends_raw.split(",")) if item
        )
        for dependency in depends:
            if not is_valid_id(dependency):
                self.diag.warning(
                    f"dependência {dependency!r} de {block.id!r} não segue [a-z][a-z0-9_]*",
                    block.attr_line("depends"),
                )
        timeout_raw = block.get("timeout")
        timeout: int | None = None
        if timeout_raw is not None:
            try:
                timeout = int(timeout_raw.strip())
            except ValueError:
                self.diag.warning(
                    f"#@timeout {timeout_raw!r} inválido; step sem timeout",
                    block.attr_line("timeout"),
                )
            else:
                if timeout <= 0:
                    self.diag.warning(
                        f"#@timeout {timeout} precisa ser > 0; step sem timeout",
                        block.attr_line("timeout"),
                    )
                    timeout = None
        on_error = (block.get("on_error") or "stop").strip() or "stop"
        if on_error not in ON_ERROR_VALUES:
            self.diag.warning(
                f"#@on_error {on_error!r} inválido (use stop|continue); usando 'stop'",
                block.attr_line("on_error"),
            )
            on_error = "stop"
        default_raw = block.get("default")
        if default_raw is not None and default_raw.strip().lower() not in TRUTHY | FALSY:
            self.diag.warning(
                f"#@default {default_raw!r} inválido (use on|off)", block.attr_line("default")
            )
        return Step(
            id=block.id,
            function=function,
            title=title,
            description="\n".join(part for part in block.descs if part),
            group=group,
            default=_flag(default_raw),
            required=_flag(block.get("required"), False),
            depends=depends,
            root=_flag(block.get("root"), False),
            timeout=timeout,
            on_error=on_error,
            line=block.line,
        )

    def _check_show_if(self, options: list[Option]) -> None:
        """§4.3/§4.6: `show_if` só referencia opção existente, sem ciclo."""
        by_id = {option.id: option for option in options}
        lines = {
            block.id: block.attr_line("show_if")
            for block in self.blocks
            if block.kind == "option" and block.get("show_if")
        }
        for option in options:
            for ref_id, _expected in option.show_if:
                if ref_id == option.id:
                    self._error(
                        f"show_if de #@option {option.id!r} referencia a si mesma",
                        lines.get(option.id, option.line),
                    )
                elif ref_id not in by_id:
                    self._error(
                        f"show_if de #@option {option.id!r} aponta para opção inexistente {ref_id!r}",
                        lines.get(option.id, option.line),
                    )
        graph = {option.id: [ref for ref, _ in option.show_if] for option in options}
        state: dict[str, int] = {}

        def visit(node: str, stack: list[str]) -> None:
            if state.get(node) == 2:
                return
            if state.get(node) == 1:
                cycle = stack[stack.index(node):] + [node]
                self._error(
                    "ciclo em show_if: " + " -> ".join(cycle),
                    lines.get(stack[-1], by_id[node].line),
                )
                return
            state[node] = 1
            for dependency in graph.get(node, ()):
                if dependency in graph:
                    visit(dependency, stack + [node])
            state[node] = 2

        for option in options:
            visit(option.id, [])

    def _check_cycles(self, steps: list[Step]) -> None:
        graph = {step.id: [d for d in step.depends] for step in steps}
        by_id = {step.id: step for step in steps}
        # aponta a diretiva #@depends, não o início do bloco (§4.6)
        lines = {
            block.id: block.attr_line("depends")
            for block in self.blocks
            if block.kind == "step" and block.get("depends")
        }
        for step in steps:
            for dependency in step.depends:
                if dependency not in by_id:
                    self._error(
                        f"#@depends {dependency!r} do step {step.id!r} aponta para"
                        " um step inexistente",
                        lines.get(step.id, step.line),
                    )
        state: dict[str, int] = {}

        def visit(node: str, stack: list[str]) -> None:
            if state.get(node) == 2:
                return
            if state.get(node) == 1:
                cycle = stack[stack.index(node):] + [node]
                self._error(
                    "ciclo nas dependências: " + " -> ".join(cycle), by_id[node].line
                )
            state[node] = 1
            for dependency in graph.get(node, ()):
                visit(dependency, stack + [node])
            state[node] = 2

        for step in steps:
            visit(step.id, [])


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_text(text: str, path: Path | None = None) -> ParseResult:
    """Parseia o conteúdo de um script (sem tocar no disco além do nome)."""
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

"""Constantes, helpers de linha e o contrato comum dos mixins do parser (SPEC.md §4)."""

from __future__ import annotations

import hashlib
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from .errors import Diagnostics, ParseError, ValidationError
from .model import (
    Script,
)


ANNOTATION = "#@"
BLOCK_START = ("step", "action", "option")
#: §4.4/§4.8 — blocos que precisam de definição de função logo abaixo.
FUNCTION_KINDS = frozenset({"step", "action"})

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
#: §4.8 — ação: mesmas diretivas de step que fazem sentido, mais `button`.
ACTION_ATTRS = frozenset(
    {"title", "desc", "group", "root", "timeout", "function", "button",
     "default", "required", "depends", "on_error"}  # os quatro últimos: aviso e ignorados
)
#: §4.8 — diretivas de ação que não valem (viram aviso).
ACTION_IGNORED = ("default", "required", "depends", "on_error")
OPTION_ATTRS = frozenset(
    {"type", "label", "default", "choices", "required", "help",
     "min", "max", "step", "filters", "pattern", "minlen", "maxlen", "multiple",
     "show_if", "url", "needs_step", "group"}
)
HEADER_ATTRS = frozenset(
    {"runtime", "name", "id", "description", "version", "author", "icon", "requires", "strict"}
)
KNOWN_DIRECTIVES = HEADER_ATTRS | {"step", "action", "option"} | STEP_ATTRS | ACTION_ATTRS | OPTION_ATTRS


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


def _sem_aspas(raw: str | None) -> str | None:
    """Valor de atributo sem espaços e aspas (ou ``None`` se o atributo não existe)."""
    return _unquote(raw.strip()) if raw is not None else None


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


def _lista_separada_por_virgula(raw: str | None) -> tuple[str, ...]:
    """``choices=`` e ``filters=``: itens separados por vírgula, sem vazios nem espaços."""
    return tuple(
        part.strip()
        for part in _unquote((raw or "").strip()).split(",")
        if part.strip()
    )

class _ParserBase:
    """Atributos e `_error` que os mixins de opções e passos compartilham com `_Parser`."""

    path: Path | None
    diag: Diagnostics
    blocks: list[_Block]
    functions: set[str]

    def _error(self, message: str, line: int | None) -> None:
        raise ValidationError(message, self.path, line)

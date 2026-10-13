"""Modelo de dados do kbash (SPEC.md §5)."""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

__all__ = [
    "Option",
    "Step",
    "Script",
    "RunPlan",
    "StepState",
    "RunState",
    "OPTION_TYPES",
    "NON_VALUE_TYPES",
    "LINK_SCHEMES",
    "ON_ERROR_VALUES",
    "RUNTIME_VERSION_SUPPORTED",
    "ID_RE",
    "DATE_RE",
    "TIME_RE",
    "slugify",
    "is_valid_id",
    "is_valid_number",
    "is_valid_date",
    "is_valid_time",
    "is_allowed_link",
    "placeholder_script",
]

#: Versão de ``#@runtime`` suportada por este runtime (SPEC.md §4.2/§4.6).
RUNTIME_VERSION_SUPPORTED = 1

OPTION_TYPES = (
    "bool", "string", "password", "choice", "multi", "path",
    "number", "slider", "file", "text", "date", "time",
    "paragraph", "link",
)
#: §4.3: tipos que só mostram algo na tela. Não têm valor: não viram
#: ``OPT_*``, não entram em ``--opt``, não são obrigatórios e somem do plano.
NON_VALUE_TYPES = ("paragraph", "link")
#: §4.3: esquemas aceitos em ``url=`` do tipo ``link``.
LINK_SCHEMES = ("http", "https")
ON_ERROR_VALUES = ("stop", "continue")
ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
#: §4.3: `date` vai em ISO (`AAAA-MM-DD`); `fromisoformat` sozinho
#: aceita também o básico sem traço (`AAAAMMDD`), então o formato
#: com traço é exigido antes.
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: §4.3: `time` vai em `HH:MM` (24h).
TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def is_valid_id(value: str) -> bool:
    """§4.3/§4.4: ``[a-z][a-z0-9_]*``."""
    return bool(ID_RE.match(value))


def slugify(name: str) -> str:
    """§4.2: ID padrão = slug do nome (usado quando ``#@id`` falta)."""
    ascii_only = name.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "script"


def is_valid_number(value: str) -> bool:
    """§4.3: `number`/`slider` aceitam inteiro ou decimal."""
    try:
        float(value.strip())
    except (TypeError, ValueError):
        return False
    return True


def is_valid_date(value: str) -> bool:
    """§4.3: `date` exige ISO válido (`AAAA-MM-DD`, com mês/dia reais)."""
    text = value.strip()
    if not DATE_RE.match(text):
        return False
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def is_valid_time(value: str) -> bool:
    """§4.3: `time` exige `HH:MM` válido (00-23:00-59)."""
    text = value.strip()
    if not TIME_RE.match(text):
        return False
    try:
        datetime.time.fromisoformat(text)
    except ValueError:
        return False
    return True


def is_allowed_link(url: str) -> bool:
    """§4.3: ``link`` só abre ``http://`` ou ``https://`` com host e sem espaços/controles."""
    text = url.strip()
    if not text or any(ch.isspace() or ord(ch) < 32 for ch in text):
        return False
    scheme, sep, rest = text.partition("://")
    return bool(sep) and scheme.lower() in LINK_SCHEMES and bool(rest.split("/", 1)[0])


def placeholder_script() -> "Script":
    """Script vazio da tela inicial (home): sem etapas nem opções, até o usuário
    escolher um arquivo. Não é executável; a GUI não oferece execução com ele."""
    return Script(
        path=Path(""), sha256="", runtime_version=RUNTIME_VERSION_SUPPORTED,
        name="kbash", id="kbash", description="Abra um script para começar.",
    )


class StepState(str, Enum):
    """§5: pending → running → success | failed | cancelled | skipped."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class RunState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Option:
    """§4.3. ``id`` é o primeiro argumento posicional de ``#@option``."""

    id: str
    type: str
    label: str
    default: str | None = None
    choices: tuple[str, ...] = ()
    required: bool = False
    help: str = ""
    #: §4.3: faixa e passo (`number`/`slider`); `filters` são globs
    #: de `file` (`"*.png,*.jpg"`). `None` = sem limite.
    minimum: str | None = None
    maximum: str | None = None
    step: str | None = None
    filters: tuple[str, ...] = ()
    #: §4.3: validação de texto (`string`/`password`/`text`) e `file`
    #: múltiplo. `minlen`/`maxlen` são inteiros em texto (`None` = sem limite).
    pattern: str = ""
    minlen: str | None = None
    maxlen: str | None = None
    multiple: bool = False
    #: §4.3: ``link`` — endereço que o botão abre (``http``/``https``).
    url: str = ""
    #: §4.3: visibilidade condicional (`show_if="outra=valor,..."`;
    #: AND entre pares). Tuplas `(option_id, valor)` já fatiadas.
    show_if: tuple[tuple[str, str], ...] = ()
    line: int = 0

    @property
    def carries_value(self) -> bool:
        """§4.3: ``False`` para ``paragraph``/``link`` (só exibem; não têm ``OPT_*``)."""
        return self.type not in NON_VALUE_TYPES

    def env_value(self, raw: str | bool | None = None) -> str:
        """Valor pronto para ``OPT_<ID>`` (bool → ``1``/``0``; multi → vírgulas)."""
        value = self.default if raw is None else raw
        if self.type == "bool":
            if isinstance(value, bool):
                return "1" if value else "0"
            return "1" if str(value).strip().lower() in ("1", "true", "on", "yes", "sim") else "0"
        if value is None:
            return ""
        return str(value)


@dataclass(frozen=True)
class Step:
    """§4.4. ``function`` é o nome da função bash chamada pelo executor."""

    id: str
    function: str
    title: str
    description: str = ""
    group: str | None = None
    default: bool = True
    required: bool = False
    depends: tuple[str, ...] = ()
    root: bool = False
    timeout: int | None = None
    on_error: str = "stop"
    line: int = 0


@dataclass(frozen=True)
class Script:
    """§5."""

    path: Path
    sha256: str
    runtime_version: int
    name: str
    id: str
    description: str = ""
    version: str = ""
    author: str = ""
    icon: str | None = None
    requires: tuple[str, ...] = ()
    strict: bool = True
    options: tuple[Option, ...] = ()
    steps: tuple[Step, ...] = ()

    def step(self, step_id: str) -> Step | None:
        for candidate in self.steps:
            if candidate.id == step_id:
                return candidate
        return None

    def option(self, option_id: str) -> Option | None:
        for candidate in self.options:
            if candidate.id == option_id:
                return candidate
        return None

    @property
    def groups(self) -> tuple[str, ...]:
        """Ordem dos grupos na declaração, sem duplicatas e sem ``None``."""
        seen: list[str] = []
        for step in self.steps:
            if step.group and step.group not in seen:
                seen.append(step.group)
        return tuple(seen)


@dataclass
class RunPlan:
    """§5/§6: o que será executado, já resolvido e ordenado."""

    script: Script
    selected: list[str] = field(default_factory=list)
    options: dict[str, str] = field(default_factory=dict)
    auto_added: set[str] = field(default_factory=set)

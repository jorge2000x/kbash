"""Modelo de dados do kbash (SPEC.md §5)."""

from __future__ import annotations

import datetime
import math
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

__all__ = [
    "DATE_RE",
    "ID_RE",
    "LINK_SCHEMES",
    "NON_VALUE_TYPES",
    "ON_ERROR_VALUES",
    "OPTION_TYPES",
    "RUNTIME_VERSION_SUPPORTED",
    "TIME_RE",
    "Action",
    "Option",
    "RunPlan",
    "RunState",
    "Script",
    "Step",
    "StepState",
    "is_allowed_link",
    "is_valid_date",
    "is_valid_id",
    "is_valid_number",
    "is_valid_time",
    "placeholder_script",
    "slugify",
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


#: §4.2: id do script — letras, dígitos e ``._-``, começa com letra ou dígito,
#: até 64 caracteres. Aceita id reverso (``com.exemplo.app``); recusa ``/``, espaço e ``..``.
SCRIPT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def is_safe_script_id(value: str) -> bool:
    return bool(SCRIPT_ID_RE.match(value)) and ".." not in value


def slugify(name: str) -> str:
    """§4.2: ID padrão = slug do nome (usado quando ``#@id`` falta)."""
    ascii_only = name.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "script"


#: §4.3: inteiro ou decimal com sinal e expoente opcionais, só dígitos ASCII.
_NUMERO_RE = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


def is_valid_number(value: str) -> bool:
    """§4.3: `number`/`slider` aceitam inteiro ou decimal finito (sem ``nan``, ``inf`` nem ``_``)."""
    texto = value.strip()
    if _NUMERO_RE.fullmatch(texto) is None:
        return False
    return math.isfinite(float(texto))


def is_ascii_digits(value: str) -> bool:
    """Só dígitos ``0``-``9``. ``str.isdigit()`` também aceita ``²`` e ``٣``, que ``int()``
    não converte da mesma forma (``²`` levanta ``ValueError``)."""
    return re.fullmatch(r"[0-9]+", value) is not None


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


def erro_de_entrada(kind: str, value: str, minimum: str = "", maximum: str = "") -> str:
    """Mensagem de erro para a resposta de um prompt ``number``/``date``/``time``; ``""`` se válida.

    Fonte única para o terminal (``core/ui.py``) e o QML (via ``bridge.validateAnswer``).
    Vazio é válido: significa "usar o padrão". Limite não numérico é ignorado.
    """
    texto = value.strip()
    if kind == "number":
        if texto == "":
            return ""
        if not is_valid_number(texto):
            return "digite um número"
        numero = float(texto)
        if minimum != "" and is_valid_number(minimum) and numero < float(minimum):
            return f"mínimo: {minimum}"
        if maximum != "" and is_valid_number(maximum) and numero > float(maximum):
            return f"máximo: {maximum}"
        return ""
    if kind == "date":
        if texto == "" or is_valid_date(texto):
            return ""
        return "formato inválido (use AAAA-MM-DD)"
    if kind == "time":
        if texto == "" or is_valid_time(texto):
            return ""
        return "formato inválido (use HH:MM)"
    raise ValueError(f"tipo de prompt sem validação: {kind!r}")


def is_allowed_link(url: str) -> bool:
    """§4.3: ``link`` só abre ``http://`` ou ``https://`` com host e sem espaços/controles."""
    text = url.strip()
    if not text or any(ch.isspace() or ord(ch) < 32 for ch in text):
        return False
    scheme, sep, rest = text.partition("://")
    return bool(sep) and scheme.lower() in LINK_SCHEMES and bool(rest.split("/", 1)[0])


def placeholder_script() -> Script:
    """Script vazio da tela inicial (home): sem etapas nem opções, até o usuário
    escolher um arquivo. Não é executável; a GUI não oferece execução com ele."""
    return Script(
        path=Path(""), sha256="", runtime_version=RUNTIME_VERSION_SUPPORTED,
        name="kbash", id="kbash", description="Abra um script para começar.",
    )


class StepState(str, Enum):  # noqa: UP042 — StrEnum mudaria str() dos membros
    """§5: pending → running → success | failed | cancelled | skipped."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class RunState(str, Enum):  # noqa: UP042 — StrEnum mudaria str() dos membros
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
    #: Opção ligada a um step (``needs_step=<id>``): só aparece e vale quando o
    #: step está selecionado (efetivamente, depois das dependências).
    needs_step: str | None = None
    #: §4.8.1: grupo de exibição da opção geral (`group=`). `None` = bloco sem título.
    group: str | None = None
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
class Action:
    """§4.8. Mini-script rodado sob demanda pela tela de Seleção, fora do plano."""

    id: str
    function: str
    title: str
    description: str = ""
    button: str = "Rodar"
    group: str | None = None
    root: bool = False
    timeout: int = 60
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
    actions: tuple[Action, ...] = ()

    def action(self, action_id: str) -> Action | None:
        for candidate in self.actions:
            if candidate.id == action_id:
                return candidate
        return None

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
        """§4.8.1 — grupos na ordem da primeira declaração (linha) entre opções
        gerais, steps e ações. ``""`` é o bloco sem título. Opção com
        ``needs_step`` não entra: aparece dentro da linha do seu step."""
        items: list[tuple[int, str]] = [
            (option.line, option.group or "")
            for option in self.options
            if option.needs_step is None
        ]
        items += [(step.line, step.group or "") for step in self.steps]
        items += [(action.line, action.group or "") for action in self.actions]
        seen: list[str] = []
        for _, name in sorted(items):
            if name not in seen:
                seen.append(name)
        return tuple(seen)


@dataclass
class RunPlan:
    """§5/§6: o que será executado, já resolvido e ordenado."""

    script: Script
    selected: list[str] = field(default_factory=list)
    options: dict[str, str] = field(default_factory=dict)
    auto_added: set[str] = field(default_factory=set)

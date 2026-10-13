"""Provedores de UI para a interação com o usuário (SPEC.md §8.5).

O core não desenha interfaces: entrega um :class:`Prompt` a um *provedor* e
recebe um :class:`Answer`. É a mesma ideia do ``kdialog`` — trocar a interface
não muda o core nem o script. Python puro: ``core/`` nunca importa Qt (§3).

Implementações nesta v1:

* :class:`TerminalUi` — perguntas no terminal (``--headless`` com TTY);
* :class:`YesUi`      — assume o padrão, sem perguntar (CI, ``--yes``);
* :class:`NoneUi`     — cancela tudo (§7.4);
* ``gui/ui_qt.py``    — diálogos QML da GUI.

A sintaxe vista pelo autor do script é a do ``kdialog``
(``rt_confirm``/``rt_input``/``rt_choice``), mas **o diálogo é do próprio
runtime**: nenhum programa externo é executado para obter a resposta (§8.1).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

__all__ = [
    "Prompt",
    "Answer",
    "Ui",
    "TerminalUi",
    "YesUi",
    "NoneUi",
    "OkUi",
    "register",
    "available",
    "create",
    "select_name",
    "default_answer",
    "CANCEL_SENTINEL",
    "OK_SENTINEL",
    "DEFAULT_UI",
    "AUTO",
]

AUTO = "auto"
DEFAULT_UI = AUTO
KIND_CONFIRM = "confirm"
KIND_INPUT = "input"
KIND_CHOICE = "choice"
KIND_NUMBER = "number"
KIND_DATE = "date"
KIND_TIME = "time"
KIND_FILE = "file"
KIND_TEXT = "text"
KIND_TEXTBOX = "textbox"

#: Sentinelas para o QML responder "cancelado" sem ambiguidade com texto.
CANCEL_SENTINEL = object()
OK_SENTINEL = object()

Status = Literal["ok", "cancel"]


@dataclass(frozen=True)
class Prompt:
    """Uma pergunta para o usuário (espelha ``PromptRequest`` do §7.3)."""

    id: str
    kind: Literal["confirm", "input", "choice", "number", "date", "time", "file", "text", "textbox"]
    text: str = ""
    label: str = ""
    secret: bool = False
    default: Any = None
    choices: tuple[str, ...] = ()
    multi: bool = False
    step_id: str | None = None
    #: §8.4: faixa de `number` (`""` = sem limite).
    minimum: str = ""
    maximum: str = ""

    @property
    def title(self) -> str:
        return self.text or self.label

    @classmethod
    def from_request(cls, event: Any) -> "Prompt":
        """Constrói a partir de um :class:`~kbash.core.events.PromptRequest`."""
        default = event.default
        if isinstance(default, (list, tuple)):
            default = tuple(str(item) for item in default)
        return cls(
            id=event.request_id,
            kind=event.kind,
            text=event.text,
            label=event.label,
            secret=event.secret,
            default=default,
            choices=tuple(event.choices),
            multi=event.multi,
            step_id=event.step_id,
            minimum=getattr(event, "minimum", "") or "",
            maximum=getattr(event, "maximum", "") or "",
        )


@dataclass(frozen=True)
class Answer:
    """Resposta do usuário, no formato esperado pelo transporte (§8.3)."""

    status: Status = "ok"
    value: Any = ""
    cancelled: bool = field(default=False, compare=False)

    @classmethod
    def ok(cls, value: Any) -> "Answer":
        return cls(status="ok", value=value)

    @classmethod
    def cancel(cls) -> "Answer":
        return cls(status="cancel", value="", cancelled=True)

    @property
    def accepted(self) -> bool:
        return self.status == "ok"


@runtime_checkable
class Ui(Protocol):
    """Contrato mínimo de um provedor de interação (§8.5)."""

    name: str

    def ask(self, prompt: Prompt) -> Answer: ...

    def notify(self, text: str, level: str = "info") -> None: ...

    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# Implementações puras
# ---------------------------------------------------------------------------
class YesUi:
    """Assume o padrão do prompt — para ``--yes`` e CI (§8.5)."""

    name = "yes"

    def ask(self, prompt: Prompt) -> Answer:
        return default_answer(prompt)

    def notify(self, text: str, level: str = "info") -> None:
        print(f"• {text}", file=sys.stderr if level in ("warn", "error") else sys.stdout)

    def close(self) -> None:
        return None


class OkUi(YesUi):
    """Atalho para ``--yes`` (mesmo comportamento, nome explícito)."""

    name = "ok"


class NoneUi:
    """Sem interface: cancela os prompts pendentes (§7.4)."""

    name = "none"

    def ask(self, prompt: Prompt) -> Answer:
        return Answer.cancel()

    def notify(self, text: str, level: str = "info") -> None:
        print(f"• {text}", file=sys.stderr if level in ("warn", "error") else sys.stdout)

    def close(self) -> None:
        return None


class TerminalUi:
    """Perguntas no terminal, no formato do ``kdialog`` (§8.5).

    Só aparece no ``--headless``; na GUI quem pergunta é :class:`QtUi`.
    """

    name = "terminal"

    def __init__(self, input_fn: Callable[[str], str] | None = None,
                 out: Any = None, err: Any = None) -> None:
        self._read = input_fn or input
        self._out = out or sys.stdout
        self._err = err or sys.stderr

    def ask(self, prompt: Prompt) -> Answer:
        try:
            if prompt.kind == KIND_CONFIRM:
                return Answer.ok(self._confirm(prompt))
            if prompt.kind == KIND_CHOICE:
                return Answer.ok(self._choice(prompt))
            if prompt.kind == KIND_NUMBER:
                return Answer.ok(self._number(prompt))
            if prompt.kind == KIND_DATE:
                return Answer.ok(self._dated(prompt, "date"))
            if prompt.kind == KIND_TIME:
                return Answer.ok(self._dated(prompt, "time"))
            if prompt.kind == KIND_FILE:
                return Answer.ok(self._file(prompt))
            if prompt.kind == KIND_TEXT:
                return Answer.ok(self._text(prompt))
            if prompt.kind == KIND_TEXTBOX:
                return Answer.ok(self._textbox(prompt))
            return Answer.ok(self._input(prompt))
        except (EOFError, KeyboardInterrupt):
            print(file=self._err)
            return Answer.cancel()

    # -- confirm -------------------------------------------------------
    def _confirm(self, prompt: Prompt) -> bool:
        hint = "[S/n]" if prompt.default else "[s/N]"
        while True:
            raw = self._read(f"{prompt.title} {hint} ").strip().lower()
            if not raw:
                return bool(prompt.default)
            if raw in ("s", "y", "sim", "yes", "1", "true"):
                return True
            if raw in ("n", "nao", "não", "no", "0", "false"):
                return False
            print("responda s ou n", file=self._err)

    # -- input / secret ------------------------------------------------
    def _input(self, prompt: Prompt) -> str:
        hint = f" [{prompt.default}]" if prompt.default else ""
        raw = self._read(f"{prompt.label}{hint}: ")
        if prompt.secret and raw:  # §9.1 — não ecoa o valor
            print(file=self._err)
        return raw or ("" if prompt.default is None else str(prompt.default))

    # -- choice / multi -------------------------------------------------
    def _choice(self, prompt: Prompt) -> Any:
        choices = list(prompt.choices)
        for number, choice in enumerate(choices, start=1):
            print(f"   {number}) {choice}", file=self._err)
        if prompt.multi:
            raw = self._read(f"{prompt.label} (números separados por vírgula): ").strip()
            if not raw:
                return tuple(prompt.default or choices)
            picked: list[str] = []
            for token in raw.replace(",", " ").split():
                index = int(token) - 1 if token.isdigit() else -1
                if 0 <= index < len(choices) and choices[index] not in picked:
                    picked.append(choices[index])
            return tuple(picked)
        raw = self._read(f"{prompt.label} [1]: ").strip()
        if not raw:
            return prompt.default or (choices[0] if choices else "")
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1]
        return raw

    # -- number / date / time / file / text / textbox ---------------------
    def _number(self, prompt: Prompt) -> str:
        from .model import is_valid_number

        hint = f" [{prompt.default}]" if prompt.default not in (None, "") else ""
        bounds = ""
        if prompt.minimum != "" or prompt.maximum != "":
            bounds = f" ({prompt.minimum or '…'}–{prompt.maximum or '…'})"
        while True:
            raw = self._read(f"{prompt.label}{hint}{bounds}: ").strip()
            if not raw:
                return "" if prompt.default in (None, "") else str(prompt.default)
            if not is_valid_number(raw):
                print("digite um número", file=self._err)
                continue
            number = float(raw)
            if prompt.minimum != "" and number < float(prompt.minimum):
                print(f"mínimo: {prompt.minimum}", file=self._err)
                continue
            if prompt.maximum != "" and number > float(prompt.maximum):
                print(f"máximo: {prompt.maximum}", file=self._err)
                continue
            return raw

    def _dated(self, prompt: Prompt, which: str) -> str:
        from .model import is_valid_date, is_valid_time

        valid = is_valid_date if which == "date" else is_valid_time
        expected = "AAAA-MM-DD" if which == "date" else "HH:MM"
        hint = f" [{prompt.default}]" if prompt.default not in (None, "") else ""
        while True:
            raw = self._read(f"{prompt.label}{hint} ({expected}): ").strip()
            if not raw:
                return "" if prompt.default in (None, "") else str(prompt.default)
            if not valid(raw):
                print(f"formato inválido (use {expected})", file=self._err)
                continue
            return raw

    def _file(self, prompt: Prompt) -> str:
        hint = f" [{prompt.default}]" if prompt.default not in (None, "") else ""
        raw = self._read(f"{prompt.label}{hint}: ").strip()
        return raw or ("" if prompt.default in (None, "") else str(prompt.default))

    def _text(self, prompt: Prompt) -> str:
        print(f"{prompt.label} (termine com uma linha só com ponto):", file=self._err)
        lines: list[str] = []
        while True:
            raw = self._read("")
            if raw.strip() == ".":
                break
            lines.append(raw)
        if not lines:
            return "" if prompt.default in (None, "") else str(prompt.default)
        return "\n".join(lines)

    def _textbox(self, prompt: Prompt) -> str:
        print(prompt.text or prompt.label, file=self._out)
        self._read("(Enter para continuar) ")
        return ""

    def notify(self, text: str, level: str = "info") -> None:
        print(f"• {text}", file=self._err if level in ("warn", "error") else self._out)

    def close(self) -> None:
        return None


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------
_FACTORIES: dict[str, Callable[..., Ui]] = {
    "yes": YesUi,
    "ok": OkUi,
    "none": NoneUi,
    "terminal": TerminalUi,
}


def register(name: str, factory: Callable[..., Ui], *, force: bool = False) -> None:
    """Registra um provedor (§8.5). Torna possível escrever o seu."""
    if not force and name in _FACTORIES and _FACTORIES[name] is not factory:
        raise ValueError(f"provedor de UI {name!r} já registrado")
    _FACTORIES[name] = factory


def available() -> tuple[str, ...]:
    """Nomes disponíveis, incluindo os registrados por plugins."""
    return tuple(sorted(_FACTORIES))


def select_name(
    explicit: str | None = None,
    *,
    has_gui: bool = False,
    stdin: Any = None,
    environ: dict[str, str] | None = None,
    kdialog: str | None = None,
) -> str:
    """Resolve o provedor (§8.5): ``--ui`` > ``$KBASH_UI`` > ``auto``."""
    env = os.environ if environ is None else environ
    for candidate in (explicit, env.get("KBASH_UI"), AUTO):
        if not candidate:
            continue
        if candidate == AUTO:
            continue
        if candidate not in _FACTORIES:
            raise ValueError(
                f"provedor de UI desconhecido: {candidate!r} (disponíveis: {', '.join(available())})"
            )
        return candidate
    if has_gui:
        return "qt"
    stream = sys.stdin if stdin is None else stdin
    try:
        interactive = bool(stream.isatty())
    except (AttributeError, ValueError):
        interactive = False
    return "terminal" if interactive else "yes"


def create(name: str | None = None, **kwargs: Any) -> Ui:
    """Cria o provedor pedido (ou resolve ``auto``)."""
    return _FACTORIES[select_name(name, **kwargs)]()


def default_answer(prompt: Prompt) -> Answer:
    """Resposta padrão do prompt — usada por ``YesUi`` e como fallback."""
    if prompt.kind == KIND_CONFIRM:
        return Answer.ok(bool(prompt.default))
    if prompt.kind == KIND_CHOICE:
        if prompt.multi:
            return Answer.ok(tuple(prompt.default or prompt.choices))
        chosen = prompt.default or (prompt.choices[0] if prompt.choices else "")
        return Answer.ok(str(chosen))
    if prompt.kind == KIND_TEXTBOX:
        return Answer.ok("")
    return Answer.ok("" if prompt.default is None else str(prompt.default))

"""Eventos emitidos pelo core (SPEC.md §7.3).

Dataclasses puras — quem converte em sinais Qt é ``gui/bridge.py`` (§3 regra 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, TypeAlias

from .model import RunState, StepState

__all__ = [
    "Event",
    "RunStarted",
    "StepStarted",
    "StepFinished",
    "LogLine",
    "Progress",
    "PromptRequest",
    "Notify",
    "RunFinished",
    "RequestEvent",
    "RespondFn",
    "EventSink",
    "PROMPT_KINDS",
]

PROMPT_KINDS = ("confirm", "input", "choice")


@dataclass(frozen=True)
class Event:
    """Base de todos os eventos."""


@dataclass(frozen=True)
class RunStarted(Event):
    script_id: str
    script_name: str
    total_steps: int
    workdir: str
    prechecks: tuple[str, ...] = ()


@dataclass(frozen=True)
class StepStarted(Event):
    step_id: str
    index: int
    total: int


@dataclass(frozen=True)
class StepFinished(Event):
    step_id: str
    status: StepState
    exit_code: int | None
    duration: float
    reason: str = ""


@dataclass(frozen=True)
class LogLine(Event):
    step_id: str | None
    stream: Literal["stdout", "stderr", "kbash"]
    text: str
    level: str = "info"


@dataclass(frozen=True)
class Progress(Event):
    step_id: str | None
    value: float | None  # 0.0–1.0; None = indeterminado
    text: str = ""

    @property
    def overall(self) -> float | None:
        """0.0–1.0 do step, ou ``None`` se indeterminado."""
        return None if self.value is None else max(0.0, min(1.0, self.value))


@dataclass(frozen=True)
class PromptRequest(Event):
    """§8.2: pedido de interação que precisa de resposta do usuário."""

    request_id: str
    kind: Literal["confirm", "input", "choice", "number", "date", "time", "file", "text", "textbox"]
    text: str = ""
    default: Any = None
    choices: tuple[str, ...] = ()
    multi: bool = False
    secret: bool = False
    label: str = ""
    #: §8.4: faixa de `number` (`rt_number "rótulo" [padrão] [min] [max]`).
    minimum: str = ""
    maximum: str = ""
    step_id: str | None = None
    timeout: float | None = None


@dataclass(frozen=True)
class Notify(Event):
    text: str
    level: str = "info"


@dataclass(frozen=True)
class ProgressWin(Event):
    """§8.2/§8.4 — progresso dirigido pelo script (``rt_progresswin_*``).

    Fire-and-forget como :class:`Notify`: não cria pendência nem
    espera resposta. ``op`` é ``start`` | ``update`` | ``done``.
    """

    op: str
    value: float = 0.0
    #: `None` no `update` = mantém o máximo do `start`.
    maximum: float | None = 100.0
    text: str = ""
    step_id: str | None = None


@dataclass(frozen=True)
class RunFinished(Event):
    status: RunState
    duration: float = 0.0


#: Eventos que exigem resposta do chamador (headless/terminal ou GUI).
RequestEvent: TypeAlias = PromptRequest

#: Callback para responder um :class:`PromptRequest`: ``(request_id, value)``.
RespondFn: TypeAlias = Callable[[str, Any], None]

#: Callable genérico de emissão de eventos.
EventSink: TypeAlias = Callable[[Event], None]

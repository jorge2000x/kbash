"""Provedor de UI da GUI: os diálogos QML (SPEC.md §8.5, §10.2).

``ask()`` é chamado pela thread do IPC e **bloqueia lá**, nunca na thread da GUI
(§10.4): o pedido é entregue como sinal Qt, o QML mostra o diálogo e chama
:meth:`QtUi.resolve` quando o usuário responde.
"""

from __future__ import annotations

import threading
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from ..core.ui import Answer, Prompt

__all__ = ["QtUi"]

#: Tempo máximo que um prompt espera resposta antes de virar ``cancel``.
DEFAULT_TIMEOUT = 3600.0


class QtUi(QObject):
    """Implementa :class:`~rt.core.ui.Ui` sobre o QML (§8.5)."""

    promptRequested = Signal(str, str, str, str, "QVariant", "QStringList", bool, bool, str, str)
    notifyRaised = Signal(str, str)

    def __init__(self, parent: QObject | None = None, timeout: float = DEFAULT_TIMEOUT) -> None:
        super().__init__(parent)
        self.name = "qt"
        self._timeout = timeout
        self._pending: dict[str, tuple[threading.Event, list[Answer]]] = {}
        self._lock = threading.RLock()

    # -- Ui ------------------------------------------------------------
    def ask(self, prompt: Prompt) -> Answer:
        done = threading.Event()
        slot: list[Answer] = []
        with self._lock:
            self._pending[prompt.id] = (done, slot)
        try:
            self.promptRequested.emit(
                prompt.id,
                prompt.kind,
                prompt.text,
                prompt.label,
                prompt.default if prompt.default is not None else "",
                list(prompt.choices),
                bool(prompt.multi),
                bool(prompt.secret),
                prompt.minimum,
                prompt.maximum,
            )
        except RuntimeError:  # objeto já destruído
            self._forget(prompt.id)
            return Answer.cancel()
        if not done.wait(self._timeout):
            self._forget(prompt.id)
            return Answer.cancel()
        with self._lock:
            self._pending.pop(prompt.id, None)
        return slot[0] if slot else Answer.cancel()

    def notify(self, text: str, level: str = "info") -> None:
        self.notifyRaised.emit(text, level)

    def close(self) -> None:
        """§7.4 — cancela tudo que estiver esperando resposta."""
        with self._lock:
            pending = list(self._pending.items())
            self._pending.clear()
        for _request_id, (done, slot) in pending:
            slot.append(Answer.cancel())
            done.set()

    # -- resposta do QML -----------------------------------------------
    @Slot(str, "QVariant")
    def resolve(self, request_id: str, value: Any) -> None:
        with self._lock:
            entry = self._pending.pop(request_id, None)
        if entry is None:
            return
        done, slot = entry
        slot.append(_to_answer(value))
        done.set()

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def _forget(self, request_id: str) -> None:
        with self._lock:
            self._pending.pop(request_id, None)


def _from_qml(value: Any) -> Any:
    """QML entrega arrays JS como QJSValue: converte para tipos Python."""
    to_variant = getattr(value, "toVariant", None)
    if callable(to_variant):
        try:
            return to_variant()
        except (RuntimeError, ValueError):
            return value
    return value


def _to_answer(value: Any) -> Answer:
    from ..core.ui import CANCEL_SENTINEL, OK_SENTINEL

    value = _from_qml(value)
    if value is CANCEL_SENTINEL or value == CANCEL_SENTINEL:
        return Answer.cancel()
    if value is OK_SENTINEL or value == OK_SENTINEL:
        return Answer.ok(True)
    if isinstance(value, bool):
        return Answer.ok(value)
    if isinstance(value, (list, tuple)):
        return Answer.ok(tuple(str(item) for item in value))
    return Answer.ok("" if value is None else str(value))

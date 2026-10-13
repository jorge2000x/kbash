"""Modelos QML do runtime (SPEC.md §10.3).

Cada modelo é um ``QAbstractListModel`` que traduz o dataclass do core
(SPEC.md §5) em roles para o QML. Nenhuma lógica de execução mora aqui.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any

from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
)

from ..core.model import Script, Step, StepState
from ..core.planner import option_visible

__all__ = ["StepListModel", "OptionModel", "LogModel", "SelectedStepsProxy", "LOG_BUFFER"]

#: §10.3 — buffer circular do log.
LOG_BUFFER = 20_000

_STATUS_LABELS = {
    StepState.PENDING.value: "",
    StepState.RUNNING.value: "Em execução",
    StepState.SUCCESS.value: "Concluído",
    StepState.FAILED.value: "Falhou",
    StepState.CANCELLED.value: "Cancelado",
    StepState.SKIPPED.value: "Ignorado",
}


def _role(name: str, start: int) -> int:
    return int(Qt.ItemDataRole.UserRole) + start


class StepListModel(QAbstractListModel):
    """§10.3 — roles: stepId, title, description, group, checked, locked, status, root, duration."""

    StepId = _role("stepId", 1)
    Title = _role("title", 2)
    Description = _role("description", 3)
    Group = _role("group", 4)
    Checked = _role("checked", 5)
    Locked = _role("locked", 6)
    Status = _role("status", 7)
    Root = _role("root", 8)
    Duration = _role("duration", 9)
    Required = _role("required", 10)
    AutoAdded = _role("autoAdded", 11)
    Reason = _role("reason", 12)
    StatusLabel = _role("statusLabel", 13)

    _NAMES = {
        StepId: b"stepId",
        Title: b"title",
        Description: b"description",
        Group: b"group",
        Checked: b"checked",
        Locked: b"locked",
        Status: b"status",
        Root: b"root",
        Duration: b"duration",
        Required: b"required",
        AutoAdded: b"autoAdded",
        Reason: b"reason",
        StatusLabel: b"statusLabel",
    }

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._steps: list[Step] = []
        self._checked: dict[str, bool] = {}
        self._locked: dict[str, bool] = {}
        self._auto: dict[str, bool] = {}
        self._status: dict[str, tuple[str, float, str]] = {}

    # -- API Qt ----------------------------------------------------------
    def roleNames(self) -> dict[int, QByteArray]:  # noqa: N802 (nome Qt)
        return {role: QByteArray(name) for role, name in self._NAMES.items()}

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._steps)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._steps):
            return None
        step = self._steps[index.row()]
        status, duration, reason = self._status.get(step.id, (StepState.PENDING.value, 0.0, ""))
        match role:
            case self.StepId:
                return step.id
            case self.Title:
                return step.title
            case self.Description:
                return step.description
            case self.Group:
                return step.group or ""
            case self.Checked:
                return self._checked.get(step.id, step.default)
            case self.Locked:
                return self._locked.get(step.id, step.required)
            case self.Status:
                return status
            case self.StatusLabel:
                return _STATUS_LABELS.get(status, status)
            case self.Root:
                return step.root
            case self.Duration:
                return duration
            case self.Required:
                return step.required
            case self.AutoAdded:
                return self._auto.get(step.id, False)
            case self.Reason:
                return reason
        return None

    # -- API do bridge ---------------------------------------------------
    def load(self, script: Script) -> None:
        self.beginResetModel()
        self._steps = list(script.steps)
        self._checked = {step.id: (step.default or step.required) for step in self._steps}
        self._locked = {step.id: step.required for step in self._steps}
        self._auto = {}
        self._status = {}
        self.endResetModel()

    def set_auto_added(self, ids: set[str]) -> None:
        changed = [i for i, step in enumerate(self._steps) if self._auto.get(step.id, False) != (step.id in ids)]
        for row in changed:
            self._auto[self._steps[row].id] = self._steps[row].id in ids
        if changed:
            self._changed(changed)

    def set_checked(self, step_id: str, checked: bool, locked: bool | None = None) -> None:
        row = self._row(step_id)
        if row is None:
            return
        self._checked[step_id] = checked
        if locked is not None:
            self._locked[step_id] = locked
        self._changed([row])

    def set_locked(self, step_id: str, locked: bool) -> None:
        row = self._row(step_id)
        if row is None:
            return
        self._locked[step_id] = locked
        self._changed([row])

    def set_status(self, step_id: str, status: str, duration: float = 0.0, reason: str = "") -> None:
        row = self._row(step_id)
        if row is None:
            return
        self._status[step_id] = (status, duration, reason)
        self._changed([row])

    def reset_status(self) -> None:
        if not self._steps:
            return
        self._status = {}
        self._changed(list(range(len(self._steps))))

    def steps(self) -> list[Step]:
        return list(self._steps)

    def checked_ids(self) -> list[str]:
        return [step.id for step in self._steps if self._checked.get(step.id, step.default)]

    def failed_ids(self) -> list[str]:
        return [step_id for step_id, values in self._status.items() if values[0] == StepState.FAILED.value]

    def step(self, step_id: str) -> Step | None:
        row = self._row(step_id)
        return self._steps[row] if row is not None else None

    def title(self, step_id: str) -> str:
        step = self.step(step_id)
        return step.title if step else step_id

    def _row(self, step_id: str) -> int | None:
        for index, step in enumerate(self._steps):
            if step.id == step_id:
                return index
        return None

    def _changed(self, rows: list[int]) -> None:
        for row in rows:
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, list(self._NAMES))


class OptionModel(QAbstractListModel):
    """§10.3 — roles: optId, type, label, value, choices, required, error, …, url.

    Inclui ``paragraph``/``link`` (só exibem; §4.3): o QML decide o widget pelo
    ``type`` e nenhum deles tem valor.
    """

    OptId = _role("optId", 1)
    Type = _role("type", 2)
    Label = _role("label", 3)
    Value = _role("value", 4)
    Choices = _role("choices", 5)
    Required = _role("required", 6)
    Error = _role("error", 7)
    Help = _role("help", 8)
    Default = _role("default", 9)
    Minimum = _role("minimum", 10)
    Maximum = _role("maximum", 11)
    Step = _role("step", 12)
    Filters = _role("filters", 13)
    Pattern = _role("pattern", 14)
    Minlen = _role("minlen", 15)
    Maxlen = _role("maxlen", 16)
    Multiple = _role("multiple", 17)
    Visible = _role("visible", 18)
    Url = _role("url", 19)

    _NAMES = {
        OptId: b"optId",
        Type: b"type",
        Label: b"label",
        Value: b"value",
        Choices: b"choices",
        Required: b"required",
        Error: b"error",
        Help: b"help",
        Default: b"default",
        Minimum: b"minimum",
        Maximum: b"maximum",
        Step: b"step",
        Filters: b"filters",
        Pattern: b"pattern",
        Minlen: b"minlen",
        Maxlen: b"maxlen",
        Multiple: b"multiple",
        Visible: b"visible",
        Url: b"url",
    }

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._script: Script | None = None
        self._values: dict[str, str] = {}
        self._errors: dict[str, str] = {}

    def roleNames(self) -> dict[int, QByteArray]:  # noqa: N802
        return {role: QByteArray(name) for role, name in self._NAMES.items()}

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() or self._script is None else len(self._script.options)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or self._script is None:
            return None
        try:
            option = self._script.options[index.row()]
        except IndexError:
            return None
        match role:
            case self.OptId:
                return option.id
            case self.Type:
                return option.type
            case self.Label:
                return option.label
            case self.Value:
                return self._values.get(option.id, option.default or "")
            case self.Choices:
                return list(option.choices)
            case self.Required:
                return option.required
            case self.Error:
                return self._errors.get(option.id, "")
            case self.Help:
                return option.help
            case self.Default:
                return option.default or ""
            case self.Minimum:
                return option.minimum or ""
            case self.Maximum:
                return option.maximum or ""
            case self.Step:
                return option.step or ""
            case self.Filters:
                return list(option.filters)
            case self.Pattern:
                return option.pattern
            case self.Minlen:
                return option.minlen or ""
            case self.Maxlen:
                return option.maxlen or ""
            case self.Multiple:
                return option.multiple
            case self.Visible:
                return option_visible(self._script, self._effective_values(), option)
            case self.Url:
                return option.url
        return None

    def load(self, script: Script, values: dict[str, str]) -> None:
        self.beginResetModel()
        self._script = script
        self._values = dict(values)
        self._errors = {}
        self.endResetModel()

    def set_value(self, option_id: str, value: str) -> None:
        if self._values.get(option_id) == value:
            return
        self._values[option_id] = value
        row = self._row(option_id)
        if row is not None:
            self.dataChanged.emit(self.index(row, 0), self.index(row, 0), [self.Value])
        self._refresh_visibility()

    def _effective_values(self) -> dict[str, str]:
        """Valores atuais completados com defaults (para `show_if`, §4.3)."""
        effective: dict[str, str] = {}
        if self._script is not None:
            for option in self._script.options:
                effective[option.id] = option.default or ""
        effective.update(self._values)
        return effective

    def _refresh_visibility(self) -> None:
        """Reavalia `show_if` de todas as linhas (§4.3)."""
        if self._script is None:
            return
        for row, option in enumerate(self._script.options):
            self.dataChanged.emit(self.index(row, 0), self.index(row, 0), [self.Visible])

    def values(self) -> dict[str, str]:
        return dict(self._values)

    def set_errors(self, errors: dict[str, str]) -> None:
        self._errors = dict(errors)

    def error(self, option_id: str) -> str:
        return self._errors.get(option_id, "")

    def _row(self, option_id: str) -> int | None:
        if self._script is None:
            return None
        for index, option in enumerate(self._script.options):
            if option.id == option_id:
                return index
        return None

    def reload_errors(self) -> None:
        for row in range(self.rowCount()):
            self.dataChanged.emit(self.index(row, 0), self.index(row, 0), [self.Error])


class SelectedStepsProxy(QSortFilterProxyModel):
    """§10.2 — execução e resultado listam só as etapas selecionadas."""

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        source = self.sourceModel()
        if source is None:
            return False
        index = source.index(source_row, 0, source_parent)
        return bool(source.data(index, StepListModel.Checked))


class LogModel(QAbstractListModel):
    """§10.3 — buffer circular com atualização em lote a cada ~50 ms."""

    Text = _role("text", 1)
    Stream = _role("stream", 2)
    Level = _role("level", 3)
    StepId = _role("stepId", 4)

    _NAMES = {Text: b"text", Stream: b"stream", Level: b"level", StepId: b"stepId"}

    def __init__(self, parent: Any = None, capacity: int = LOG_BUFFER) -> None:
        super().__init__(parent)
        self._capacity = capacity
        self._lines: deque[tuple[str, str, str, str]] = deque()
        self._incoming: list[tuple[str, str, str, str]] = []
        self._lock = threading.Lock()
        self._dropped = 0

    def roleNames(self) -> dict[int, QByteArray]:  # noqa: N802
        return {role: QByteArray(name) for role, name in self._NAMES.items()}

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._lines)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._lines):
            return None
        text, stream, level, step_id = self._lines[index.row()]
        match role:
            case self.Text:
                return text
            case self.Stream:
                return stream
            case self.Level:
                return level
            case self.StepId:
                return step_id
        return None

    # -- escrita (qualquer thread) / leitura (thread da GUI) -------------
    def push(self, text: str, stream: str, level: str, step_id: str) -> None:
        with self._lock:
            self._incoming.append((text, stream, level, step_id or ""))

    def flush(self) -> int:
        """Aplica o lote pendente. Deve ser chamado na thread da GUI."""
        with self._lock:
            if not self._incoming:
                return 0
            batch, self._incoming = self._incoming, []
        if len(batch) > self._capacity:
            self._dropped += len(batch) - self._capacity
            batch = batch[-self._capacity:]
        overflow = len(self._lines) + len(batch) - self._capacity
        if overflow > 0:  # §10.3 — buffer circular: descarta as mais antigas
            self.beginRemoveRows(QModelIndex(), 0, overflow - 1)
            for _ in range(overflow):
                self._lines.popleft()
            self.endRemoveRows()
            self._dropped += overflow
        start = len(self._lines)
        self.beginInsertRows(QModelIndex(), start, start + len(batch) - 1)
        self._lines.extend(batch)
        self.endInsertRows()
        return len(batch)

    def clear(self) -> None:
        self.beginResetModel()
        self._lines.clear()
        self._incoming.clear()
        self._dropped = 0
        self.endResetModel()

    def text(self) -> str:
        return "\n".join(
            f"[{step_id}] {text}" if step_id else text for text, _s, _l, step_id in self._lines
        )

    @property
    def dropped(self) -> int:
        return self._dropped

    def to_file(self, path: str, header: str = "") -> None:
        """Salva no mesmo formato de text() (usado em copiar/ver log)."""
        with open(path, "w", encoding="utf-8") as handle:
            if header:
                handle.write(header + "\n")
            content = self.text()
            if content:
                handle.write(content + "\n")

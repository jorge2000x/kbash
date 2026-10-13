"""Planner: seleção, dependências e ordem de execução (SPEC.md §6)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .errors import ValidationError
from .model import Option, RunPlan, Script, Step, is_valid_date, is_valid_number, is_valid_time

__all__ = [
    "Resolution",
    "resolve",
    "build_plan",
    "dependents",
    "can_uncheck",
    "set_checked",
    "default_selection",
    "default_options",
    "expand_value",
    "option_errors",
    "option_visible",
    "validate_options",
    "value_options",
]


@dataclass
class Resolution:
    """Resultado de :func:`resolve`."""

    steps: list[Step] = field(default_factory=list)
    auto_added: set[str] = field(default_factory=set)

    @property
    def ids(self) -> list[str]:
        return [step.id for step in self.steps]


def _index(script: Script) -> dict[str, Step]:
    return {step.id: step for step in script.steps}


def _order_index(script: Script) -> dict[str, int]:
    return {step.id: number for number, step in enumerate(script.steps)}


def resolve(script: Script, selected_ids: list[str] | None = None) -> Resolution:
    """§6: adiciona dependências transitivas e ``required``, ordena topologicamente.

    Empates na ordenação são desfeitos pela ordem de declaração dos steps.
    """
    by_id = _index(script)
    order = _order_index(script)
    explicit: set[str] = (
        set(selected_ids)
        if selected_ids is not None
        else {step.id for step in script.steps if step.default}
    )
    unknown = explicit - by_id.keys()
    if unknown:
        raise ValidationError(
            "step(s) inexistente(s) na seleção: " + ", ".join(sorted(unknown)), script.path, None
        )

    wanted: set[str] = set(explicit)
    for step in script.steps:
        if step.required:
            wanted.add(step.id)

    auto_added: set[str] = set()
    pending = list(wanted)
    while pending:
        current = pending.pop()
        for dependency in by_id[current].depends:
            if dependency not in wanted:
                if dependency not in by_id:
                    raise ValidationError(
                        f"step {current!r} depende de {dependency!r}, que não existe",
                        script.path,
                        by_id[current].line,
                    )
                wanted.add(dependency)
                auto_added.add(dependency)
                pending.append(dependency)

    return Resolution(steps=_topological(script, wanted, by_id, order), auto_added=auto_added)


def _topological(
    script: Script,
    wanted: set[str],
    by_id: dict[str, Step],
    order: dict[str, int],
) -> list[Step]:
    remaining = {step_id: set(by_id[step_id].depends) & wanted for step_id in wanted}
    result: list[Step] = []
    while remaining:
        ready = [step_id for step_id, deps in remaining.items() if not deps]
        if not ready:  # ciclo — garantido por parser.check_cycles, mas não confie
            raise ValidationError(
                "ciclo nas dependências entre " + ", ".join(sorted(remaining)), script.path, None
            )
        ready.sort(key=lambda step_id: order.get(step_id, 0))
        for step_id in ready:
            result.append(by_id[step_id])
            del remaining[step_id]
        for deps in remaining.values():
            deps.difference_update(ready)
    return result


def dependents(script: Script, step_id: str) -> list[str]:
    """§6: steps que (transitivamente) dependem de ``step_id``."""
    by_id = _index(script)
    if step_id not in by_id:
        return []
    blocked: set[str] = set()
    frontier = [step_id]
    while frontier:
        current = frontier.pop()
        for step in script.steps:
            if current in step.depends and step.id not in blocked and step.id != step_id:
                blocked.add(step.id)
                frontier.append(step.id)
    return [step.id for step in script.steps if step.id in blocked]


def can_uncheck(script: Script, step_id: str, selected: set[str] | None = None) -> str | None:
    """Motivo que impede desmarcar ``step_id``, ou ``None`` se possível (§6)."""
    step = script.step(step_id)
    if step is None:
        return "step inexistente"
    if step.required:
        return "step obrigatório"
    if selected is None:
        selected = {s.id for s in script.steps if s.default}
    blocking = [dep for dep in dependents(script, step_id) if dep in selected]
    if blocking:
        return "necessário para: " + ", ".join(blocking)
    return None


def set_checked(script: Script, selected: set[str], step_id: str, checked: bool) -> set[str]:
    """Liga/desliga um step respeitando §6 (obrigatórios e dependentes)."""
    new = set(selected)
    if checked:
        new.add(step_id)
        pending = list(_index(script)[step_id].depends)
        while pending:  # dependências transitivas, como em resolve()
            current = pending.pop()
            if current in new or current not in _index(script):
                continue
            new.add(current)
            pending.extend(_index(script)[current].depends)
    else:
        reason = can_uncheck(script, step_id, selected)
        if reason is not None:
            raise ValidationError(f"não é possível desmarcar {step_id!r}: {reason}", script.path, None)
        new.discard(step_id)
    return new


def default_selection(script: Script) -> list[str]:
    return [step.id for step in script.steps if step.default or step.required]


def expand_value(value: str | None, home: str | None = None) -> str:
    """§4.3 — expande ``~`` e ``$HOME`` nos valores das opções."""
    if not value:
        return ""
    root = home or os.path.expanduser("~")
    text = value
    if text == "~":
        return root
    if text.startswith("~/"):
        text = root + text[1:]
    return text.replace("${HOME}", root).replace("$HOME", root)


def value_options(script: Script) -> tuple[Option, ...]:
    """§4.3 — só as opções com valor (sem ``paragraph``/``link``)."""
    return tuple(option for option in script.options if option.carries_value)


def default_options(script: Script, home: str | None = None) -> dict[str, str]:
    """Valores iniciais de todas as opções, já expandidos."""
    values: dict[str, str] = {}
    for option in value_options(script):
        raw = option.env_value()
        values[option.id] = expand_value(raw, home) if option.type in ("path", "file") else raw
    return values


def option_errors(script: Script, values: dict[str, str]) -> dict[str, str]:
    """§6 — mapa ``option_id -> mensagem de erro`` (vazio se tudo válido)."""
    errors: dict[str, str] = {}
    for option in value_options(script):
        if not option_visible(script, values, option):
            continue
        raw = values.get(option.id, "")
        value = raw.strip() if isinstance(raw, str) else raw
        if option.required and not value:
            errors[option.id] = "campo obrigatório"
            continue
        if not value:
            continue
        if option.type in ("choice", "multi"):
            chosen = [item.strip() for item in str(value).split(",")] if option.type == "multi" else [str(value)]
            for item in chosen:
                if item and item not in option.choices:
                    errors[option.id] = f"valor inválido {item!r} (esperado um de: {', '.join(option.choices)})"
                    break
        if option.type == "bool" and str(value).lower() not in ("0", "1", "true", "false", "on", "off", "yes", "no"):
            errors[option.id] = "use 0/1 para booleano"
        if option.type in ("number", "slider"):
            if not is_valid_number(str(value)):
                errors[option.id] = f"valor {str(value)!r} não é número"
            else:
                number = float(str(value))
                if option.minimum not in (None, "") and number < float(option.minimum):
                    errors[option.id] = f"valor {str(value)!r} abaixo de min={option.minimum!r}"
                elif option.maximum not in (None, "") and number > float(option.maximum):
                    errors[option.id] = f"valor {str(value)!r} acima de max={option.maximum!r}"
        if option.type == "date" and not is_valid_date(str(value)):
            errors[option.id] = f"data {str(value)!r} inválida (use AAAA-MM-DD)"
        if option.type == "time" and not is_valid_time(str(value)):
            errors[option.id] = f"hora {str(value)!r} inválida (use HH:MM)"
        if option.type in ("string", "password", "text"):
            text = str(value)
            if option.pattern:
                try:
                    matched = re.fullmatch(option.pattern, text) is not None
                except re.error:
                    matched = True
                if not matched:
                    errors[option.id] = f"valor {text!r} não casa com pattern"
                    continue
            if option.minlen is not None and len(text) < int(option.minlen):
                errors[option.id] = f"valor menor que minlen={option.minlen!r}"
            elif option.maxlen is not None and len(text) > int(option.maxlen):
                errors[option.id] = f"valor maior que maxlen={option.maxlen!r}"
    return errors


def option_visible(script: Script, values: dict[str, str], option: Option) -> bool:
    """§4.3: `show_if` satisfeito? Compara valores normalizados (`bool` → `1`/`0`).

    ``values`` pode não ter todas as chaves: o que falta usa o `default`.
    """
    for ref_id, expected in option.show_if:
        ref = script.option(ref_id)
        if ref is None:
            return False
        current = ref.env_value(values.get(ref_id))
        if current.strip() != expected.strip():
            return False
    return True


def validate_options(script: Script, values: dict[str, str], home: str | None = None) -> dict[str, str]:
    """Valida e normaliza opções; levanta :class:`ValidationError` em caso de erro."""
    values = dict(values)
    for option in value_options(script):
        if option.show_if and not option_visible(script, values, option):
            values[option.id] = option.default or ""
    errors = option_errors(script, values)
    if errors:
        raise ValidationError("; ".join(f"{key}: {msg}" for key, msg in errors.items()), script.path, None)
    return {option.id: expand_value(values.get(option.id, ""), home) if option.type in ("path", "file")
            else values.get(option.id, "") for option in value_options(script)}


def build_plan(
    script: Script,
    selected: list[str] | None = None,
    options: dict[str, str] | None = None,
    home: str | None = None,
) -> RunPlan:
    """Monta o :class:`RunPlan` final: ordem, seleção efetiva e valores de opções."""
    resolution = resolve(script, selected)
    values = dict(default_options(script, home))
    if options:
        for key, value in options.items():
            option = script.option(key)
            if option is None:
                raise ValidationError(f"opção desconhecida: {key!r}", script.path, None)
            if not option.carries_value:
                raise ValidationError(
                    f"{key!r} é só texto/link ({option.type}) e não recebe valor", script.path, None
                )
            values[key] = value
    normalized = validate_options(script, values, home)
    return RunPlan(
        script=script,
        selected=resolution.ids,
        options=normalized,
        auto_added=resolution.auto_added,
    )

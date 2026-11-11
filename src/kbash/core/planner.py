"""Planner: seleção, dependências e ordem de execução (SPEC.md §6)."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Collection
from dataclasses import dataclass, field

from .contratos import ensure, require
from .errors import ValidationError
from .model import Option, RunPlan, Script, Step, is_valid_date, is_valid_number, is_valid_time

__all__ = [
    "Resolution",
    "build_plan",
    "can_uncheck",
    "default_options",
    "default_selection",
    "dependents",
    "expand_value",
    "option_errors",
    "option_visible",
    "resolve",
    "set_checked",
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


def _bem_formado(script: Script) -> bool:
    """Pré-condição de resolve: o que o parser garante (§4.6). Ids únicos, dependências
    existentes e sem ciclo. Script fora disso não é entrada válida do planner."""
    ids = [step.id for step in script.steps]
    if len(set(ids)) != len(ids):
        return False
    grafo = {step.id: set(step.depends) for step in script.steps}
    if any(dep not in grafo for deps in grafo.values() for dep in deps):
        return False
    # Kahn: se sobra alguém sem dependências pendentes, há ciclo
    pendentes = {k: set(v) for k, v in grafo.items()}
    while pendentes:
        prontos = [k for k, deps in pendentes.items() if not deps]
        if not prontos:
            return False
        for k in prontos:
            del pendentes[k]
        for deps in pendentes.values():
            deps.difference_update(prontos)
    return True


@require(_bem_formado, "script parseado: ids únicos, dependências existentes e sem ciclo (§4.6)")
@ensure(
    lambda script, result: set(result.ids) <= {step.id for step in script.steps},
    "resolve só devolve steps que existem",
)
@ensure(
    lambda script, result: all(
        set(step.depends) <= set(result.ids)
        for step in script.steps
        if step.id in set(result.ids)
    ),
    "o fecho é fechado: toda dependência de um step escolhido também está",
)
@ensure(
    lambda script, result: all(
        result.ids.index(dep) < result.ids.index(step_id)
        for step_id in result.ids
        for dep in next(s.depends for s in script.steps if s.id == step_id)
    ),
    "a ordem respeita as dependências",
)
def resolve(script: Script, selected_ids: list[str] | None = None) -> Resolution:
    """§6: adiciona dependências transitivas e ``required``, ordena topologicamente.

    Empates na ordenação são desfeitos pela ordem de declaração dos steps.

    :raises ValidationError: seleção com step inexistente, dependência inexistente
        ou ciclo. O parser já impede os dois últimos (§4.6); aqui é defesa.
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


_BOOLEANOS = ("0", "1", "true", "false", "on", "off", "yes", "no")


def _erro_de_escolha(option: Option, value: str) -> str | None:
    escolhidos = (
        [item.strip() for item in str(value).split(",")]
        if option.type == "multi"
        else [str(value)]
    )
    for item in escolhidos:
        if item and item not in option.choices:
            esperados = ", ".join(option.choices)
            return f"valor inválido {item!r} (esperado um de: {esperados})"
    return None


def _erro_de_booleano(option: Option, value: str) -> str | None:
    if str(value).lower() not in _BOOLEANOS:
        return "use 0/1 para booleano"
    return None


def _erro_de_numero(option: Option, value: str) -> str | None:
    texto = str(value)
    if not is_valid_number(texto):
        return f"valor {texto!r} não é número"
    numero = float(texto)
    if option.minimum not in (None, "") and numero < float(option.minimum):
        return f"valor {texto!r} abaixo de min={option.minimum!r}"
    if option.maximum not in (None, "") and numero > float(option.maximum):
        return f"valor {texto!r} acima de max={option.maximum!r}"
    return None


def _erro_de_data(option: Option, value: str) -> str | None:
    texto = str(value)
    if not is_valid_date(texto):
        return f"data {texto!r} inválida (use AAAA-MM-DD)"
    return None


def _erro_de_hora(option: Option, value: str) -> str | None:
    texto = str(value)
    if not is_valid_time(texto):
        return f"hora {texto!r} inválida (use HH:MM)"
    return None


def _erro_de_texto(option: Option, value: str) -> str | None:
    texto = str(value)
    if option.pattern:
        try:
            casa = re.fullmatch(option.pattern, texto) is not None
        except re.error:
            casa = True
        if not casa:
            return f"valor {texto!r} não casa com pattern"
    if option.minlen is not None and len(texto) < int(option.minlen):
        return f"valor menor que minlen={option.minlen!r}"
    if option.maxlen is not None and len(texto) > int(option.maxlen):
        return f"valor maior que maxlen={option.maxlen!r}"
    return None


#: Tipo → validador do valor não vazio. Tipo sem entrada aqui não tem regra de valor.
_VALIDADORES: dict[str, Callable[[Option, str], str | None]] = {
    "choice": _erro_de_escolha,
    "multi": _erro_de_escolha,
    "bool": _erro_de_booleano,
    "number": _erro_de_numero,
    "slider": _erro_de_numero,
    "date": _erro_de_data,
    "time": _erro_de_hora,
    "string": _erro_de_texto,
    "password": _erro_de_texto,
    "text": _erro_de_texto,
}


def _erro_do_valor(option: Option, value: str) -> str | None:
    """Mensagem de erro de um valor (já sem espaços nas pontas), ou ``None``."""
    if option.required and not value:
        return "campo obrigatório"
    if not value:
        return None
    validador = _VALIDADORES.get(option.type)
    return validador(option, value) if validador is not None else None


def option_errors(
    script: Script, values: dict[str, str], selected: Collection[str] | None = None
) -> dict[str, str]:
    """§6 — mapa ``option_id -> mensagem de erro`` (vazio se tudo válido)."""
    errors: dict[str, str] = {}
    for option in value_options(script):
        if not option_visible(script, values, option, selected):
            continue
        raw = values.get(option.id, "")
        value = raw.strip() if isinstance(raw, str) else raw
        mensagem = _erro_do_valor(option, value)
        if mensagem is not None:
            errors[option.id] = mensagem
    return errors

def option_visible(
    script: Script,
    values: dict[str, str],
    option: Option,
    selected: Collection[str] | None = None,
) -> bool:
    """§4.3: a opção aparece? Vale `needs_step` e `show_if`.

    - ``needs_step``: o step dono precisa estar em ``selected`` (seleção efetiva).
      Sem ``selected`` (``None``) a opção ligada a step fica oculta.
    - ``show_if``: compara valores normalizados (`bool` → `1`/`0`).

    ``values`` pode não ter todas as chaves: o que falta usa o `default`.
    """
    if option.needs_step is not None and (selected is None or option.needs_step not in selected):
        return False
    for ref_id, expected in option.show_if:
        ref = script.option(ref_id)
        if ref is None:
            return False
        current = ref.env_value(values.get(ref_id))
        if current.strip() != expected.strip():
            return False
    return True


def _ocultar_ate_estabilizar(
    script: Script, values: dict[str, str], selected: Collection[str] | None
) -> None:
    """Opção oculta volta ao default, até não mudar mais nada (ponto fixo).

    Esconder uma opção pode esconder outra que dependia dela, e isso não pode
    depender da ordem de declaração. Cada opção oculta muda uma vez, então o
    laço termina.
    """
    mudou = True
    while mudou:
        mudou = False
        for option in value_options(script):
            if not _oculta(script, values, option, selected):
                continue
            padrao = option.default or ""
            if values.get(option.id, "") != padrao:
                values[option.id] = padrao
                mudou = True


def _oculta(script: Script, values: dict[str, str], option: Option, selected: Collection[str] | None) -> bool:
    condicionada = option.show_if or option.needs_step is not None
    return bool(condicionada) and not option_visible(script, values, option, selected)


def validate_options(
    script: Script,
    values: dict[str, str],
    home: str | None = None,
    selected: Collection[str] | None = None,
) -> dict[str, str]:
    """Valida e normaliza opções; levanta :class:`ValidationError` em caso de erro.

    Opção oculta (por ``show_if`` ou ``needs_step``) volta ao ``default``.
    """
    values = dict(values)
    _ocultar_ate_estabilizar(script, values, selected)
    errors = option_errors(script, values, selected)
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
    normalized = validate_options(script, values, home, resolution.ids)
    return RunPlan(
        script=script,
        selected=resolution.ids,
        options=normalized,
        auto_added=resolution.auto_added,
    )

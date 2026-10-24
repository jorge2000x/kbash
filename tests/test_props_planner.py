"""Propriedades do planner (INVARIANTS.md, seção Planner; SPEC §6, §16.3).

O oráculo é força bruta e deliberadamente simples: repetir a expansão de
dependências até não mudar mais, sem ordenação nem cache.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from kbash.core.errors import ValidationError
from kbash.core.model import Script, Step
from kbash.core.planner import resolve


@st.composite
def scripts_dag(draw: st.DrawFn) -> Script:
    """Steps s0..sN-1; dependências só para índices menores (sem ciclo)."""
    n = draw(st.integers(1, 7))
    steps = []
    for i in range(n):
        deps = draw(st.lists(st.integers(0, i), max_size=i, unique=True)) if i else []
        deps = [d for d in deps if d != i]
        steps.append(
            Step(
                id=f"s{i}",
                function=f"s{i}",
                title=f"s{i}",
                depends=tuple(f"s{d}" for d in deps),
                default=draw(st.booleans()),
                required=draw(st.booleans()) and draw(st.integers(0, 4)) == 0,
                line=i + 1,
            )
        )
    return Script(path=Path("x.kbash"), sha256="", runtime_version=1, name="x", id="x", steps=tuple(steps))


@st.composite
def script_e_selecao(draw: st.DrawFn) -> tuple[Script, list[str] | None]:
    script = draw(scripts_dag())
    ids = [s.id for s in script.steps]
    selecao = draw(st.one_of(st.none(), st.lists(st.sampled_from(ids), unique=True)))
    return script, selecao


def _oraculo(script: Script, selecao: list[str] | None) -> set[str]:
    """Fecho por força bruta: repete a expansão até não crescer mais."""
    by_id = {s.id: s for s in script.steps}
    wanted = (
        set(selecao) if selecao is not None else {s.id for s in script.steps if s.default}
    )
    wanted |= {s.id for s in script.steps if s.required}
    mudou = True
    while mudou:
        mudou = False
        for atual in list(wanted):
            for dep in by_id[atual].depends:
                if dep not in wanted:
                    wanted.add(dep)
                    mudou = True
    return wanted


@settings(max_examples=300)
@given(script_e_selecao())
def test_fecho_igual_ao_oraculo(par: tuple[Script, list[str] | None]) -> None:
    script, selecao = par
    assert set(resolve(script, selecao).ids) == _oraculo(script, selecao)


@settings(max_examples=300)
@given(script_e_selecao())
def test_dependencias_antes(par: tuple[Script, list[str] | None]) -> None:
    script, selecao = par
    ids = resolve(script, selecao).ids
    posicao = {sid: n for n, sid in enumerate(ids)}
    by_id = {s.id: s for s in script.steps}
    for sid in ids:
        for dep in by_id[sid].depends:
            assert posicao[dep] < posicao[sid]


@settings(max_examples=300)
@given(script_e_selecao())
def test_idempotencia(par: tuple[Script, list[str] | None]) -> None:
    script, selecao = par
    primeira = resolve(script, selecao).ids
    assert resolve(script, primeira).ids == primeira


@settings(max_examples=300)
@given(script_e_selecao())
def test_auto_added_exato(par: tuple[Script, list[str] | None]) -> None:
    script, selecao = par
    resultado = resolve(script, selecao)
    explicitos = set(selecao) if selecao is not None else {s.id for s in script.steps if s.default}
    explicitos |= {s.id for s in script.steps if s.required}
    assert resultado.auto_added == set(resultado.ids) - explicitos


@settings(max_examples=200)
@given(scripts_dag(), st.text(alphabet="xyz", min_size=1, max_size=3))
def test_selecao_desconhecida_erra(script: Script, inexistente: str) -> None:
    if any(s.id == inexistente for s in script.steps):
        pytest.skip("id existe")
    with pytest.raises(ValidationError):
        resolve(script, [inexistente])

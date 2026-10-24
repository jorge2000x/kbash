"""Propriedades do parser (INVARIANTS.md, seção Parser; SPEC §16.3).

Usa Hypothesis em dois sentidos: texto arbitrário feito de pedaços do formato
(para "nunca levanta outra exceção") e scripts gerados com declarações conhecidas
(para o oráculo "o que se declara é o que se obtém").
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

from hypothesis import given, settings
from hypothesis import strategies as st

from kbash.core.errors import ParseError, ValidationError
from kbash.core.parser import parse_text

FRAGMENTOS = [
    "#@", "#@step ", "#@option ", "#@action ", "#@title T", "#@group G", "#@group ",
    "#@timeout ", "#@timeout 0", "#@root true", "#@function ", "#@button ", "#@default on",
    "#@depends ", "#@needs_step ", "#@runtime 1", "#@runtime x", "#@name N", "#@id i.d",
    "type=choice ", "type=bool ", "type=number ", "min=", "max=", "default=", "group=",
    "needs_step=", "show_if=", "choices=", 'label="L" ', "=", '"', "'", "\n", "\n#!/bin/sh\n",
    "{", "}", "(", ")", "f() { :; }\n", "x", "a1", "_", " ", "\t", "#", "# c\n", "\\",
]


@st.composite
def textos_do_formato(draw: st.DrawFn) -> str:
    partes = draw(st.lists(st.sampled_from(FRAGMENTOS), max_size=40))
    return "".join(partes)


IDS = st.from_regex(r"[a-z][a-z0-9_]{0,6}", fullmatch=True)
GRUPOS = st.sampled_from(["Alvo", "Verificar", "Limpar", "Sistema"])


@dataclass(frozen=True)
class Declarado:
    """O que o gerador escreveu; o oráculo compara com o que o parser devolve."""

    texto: str
    opcoes: tuple[str, ...]
    steps: tuple[str, ...]
    acoes: tuple[str, ...]
    grupos_na_ordem: tuple[str, ...]


@st.composite
def scripts_validos(draw: st.DrawFn) -> Declarado:
    ids = draw(st.lists(IDS, min_size=1, max_size=8, unique=True))
    n_opc = draw(st.integers(0, len(ids)))
    n_step = draw(st.integers(0, len(ids) - n_opc))
    opcoes, steps, acoes = ids[:n_opc], ids[n_opc:n_opc + n_step], ids[n_opc + n_step:]
    if not opcoes and not steps and not acoes:
        opcoes = [ids[0]]
    linhas = ["#!/usr/bin/env bash", "#@runtime 1", "#@name Gerado"]
    grupos: list[str] = []
    for opcao in opcoes:
        grupo = draw(st.one_of(st.none(), GRUPOS))
        extra = f' group="{grupo}"' if grupo else ""
        linhas.append(f'#@option {opcao} type=string label="L" default=v{extra}')
        grupos.append(grupo or "")
    for step in steps:
        grupo = draw(st.one_of(st.none(), GRUPOS))
        # anotações de um bloco vêm logo depois da linha que o abre (§4.4)
        linhas += [f"#@step {step}"]
        if grupo:
            linhas.append(f"#@group {grupo}")
        linhas.append(f"{step}() {{ :; }}")
        grupos.append(grupo or "")
    for acao in acoes:
        grupo = draw(st.one_of(st.none(), GRUPOS))
        linhas += [f"#@action {acao}"]
        if grupo:
            linhas.append(f"#@group {grupo}")
        linhas.append(f"{acao}() {{ :; }}")
        grupos.append(grupo or "")
    ordem: list[str] = []
    for grupo in grupos:
        if grupo not in ordem:
            ordem.append(grupo)
    return Declarado(
        texto="\n".join(linhas) + "\n",
        opcoes=tuple(opcoes),
        steps=tuple(steps),
        acoes=tuple(acoes),
        grupos_na_ordem=tuple(ordem),
    )


@settings(max_examples=300)
@given(textos_do_formato())
def test_nunca_levanta_outra_excecao(texto: str) -> None:
    # erro de domínio, com arquivo:linha (§4.6); qualquer outra exceção é bug e aparece
    with contextlib.suppress(ParseError, ValidationError):
        parse_text(texto)


@settings(max_examples=200)
@given(textos_do_formato())
def test_determinismo(texto: str) -> None:
    def resultado() -> tuple[str, object]:
        try:
            return ("ok", parse_text(texto).script)
        except (ParseError, ValidationError) as erro:
            return ("erro", type(erro).__name__)

    assert resultado() == resultado()


@settings(max_examples=200)
@given(scripts_validos())
def test_declarado_e_obtido(declarado: Declarado) -> None:
    script = parse_text(declarado.texto).script
    assert tuple(o.id for o in script.options) == declarado.opcoes
    assert tuple(s.id for s in script.steps) == declarado.steps
    assert tuple(a.id for a in script.actions) == declarado.acoes


@settings(max_examples=200)
@given(scripts_validos())
def test_ids_unicos(declarado: Declarado) -> None:
    script = parse_text(declarado.texto).script
    ids = [o.id for o in script.options] + [s.id for s in script.steps] + [a.id for a in script.actions]
    assert len(ids) == len(set(ids))


@settings(max_examples=200)
@given(scripts_validos())
def test_ordem_dos_grupos(declarado: Declarado) -> None:
    script = parse_text(declarado.texto).script
    assert script.groups == declarado.grupos_na_ordem


@settings(max_examples=100)
@given(scripts_validos())
def test_shebang_nao_muda_resultado(declarado: Declarado) -> None:
    com = parse_text(declarado.texto).script
    sem = parse_text(declarado.texto.split("\n", 1)[1]).script
    assert com.groups == sem.groups
    assert com.steps == sem.steps and com.actions == sem.actions and com.options == sem.options


@settings(max_examples=300)
@given(textos_do_formato())
def test_timeout_positivo(texto: str) -> None:
    try:
        script = parse_text(texto).script
    except (ParseError, ValidationError):
        return
    for step in script.steps:
        assert step.timeout is None or step.timeout > 0
    for acao in script.actions:
        assert acao.timeout > 0

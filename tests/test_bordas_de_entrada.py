"""Bordas de entrada que antes vazavam como exceção ou eram aceitas indevidamente.

- ``str.isdigit()`` aceita dígitos que ``int()`` não converte (``²``, ``¹``): o parser e o
  terminal levantavam ``ValueError`` em vez de um erro de domínio.
- ``float()`` aceita ``nan``, ``inf`` e ``1_0``; o SPEC §4.3 pede "inteiro ou decimal".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kbash.core.errors import ParseError, ValidationError
from kbash.core.model import is_valid_number
from kbash.core.parser import parse_text
from kbash.core.ui import Prompt, TerminalUi

CAB = "#!/usr/bin/env bash\n#@runtime 1\n#@name P\n"
FIM = "#@step s\ns() { :; }\n"


def _erro_do_parser(corpo: str) -> str:
    with pytest.raises((ParseError, ValidationError)) as info:
        parse_text(CAB + corpo + "\n" + FIM, Path("p.sh"))
    return info.value.diagnostic.message


@pytest.mark.parametrize("atributo", ["minlen", "maxlen"])
@pytest.mark.parametrize("digito", ["²", "¹"])
def test_tamanho_com_digito_que_int_nao_converte_e_erro_de_dominio(atributo: str, digito: str) -> None:
    mensagem = _erro_do_parser(f"#@option o type=string {atributo}={digito}")
    assert "precisa ser inteiro >= 0" in mensagem


@pytest.mark.parametrize("corpo", [
    "#@option o type=number min=nan max=3",
    "#@option o type=number min=-inf max=3",
    "#@option o type=number max=inf",
    "#@option o type=number step=inf",
    "#@option o type=slider step=nan",
])
def test_faixa_nao_aceita_nan_nem_infinito(corpo: str) -> None:
    assert "não é número" in _erro_do_parser(corpo)


@pytest.mark.parametrize("texto", ["nan", "inf", "-inf", "1_0", "", "abc"])
def test_is_valid_number_rejeita_o_que_nao_e_decimal_finito(texto: str) -> None:
    assert is_valid_number(texto) is False


@pytest.mark.parametrize("texto", ["0", "-2.5", " 7 ", "1e3", ".5"])
def test_is_valid_number_aceita_decimais_finitos(texto: str) -> None:
    assert is_valid_number(texto) is True


def test_terminal_nao_quebra_com_digito_superscrito_na_escolha() -> None:
    prompt = Prompt(id="c", kind="choice", label="Escolha", choices=("a", "b"))
    resposta = TerminalUi(input_fn=lambda _: "²").ask(prompt)
    assert resposta.value == "²"


def test_terminal_nao_quebra_com_digito_superscrito_na_multipla_escolha() -> None:
    prompt = Prompt(id="m", kind="choice", label="Vários", choices=("a", "b"), multi=True)
    resposta = TerminalUi(input_fn=lambda _: "² 2").ask(prompt)
    assert resposta.value == ("b",)


def test_terminal_pede_de_novo_quando_numero_e_nan() -> None:
    respostas = iter(["nan", "inf", "3"])
    prompt = Prompt(id="n", kind="number", label="N")
    resposta = TerminalUi(input_fn=lambda _: next(respostas)).ask(prompt)
    assert resposta.value == "3"

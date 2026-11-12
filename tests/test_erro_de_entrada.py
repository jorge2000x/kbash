"""Validação de respostas de number/date/time, a mesma para terminal e QML (bug 10).

Vazio é válido: significa "usar o padrão", como no terminal. A mensagem devolvida é a
que o terminal já mostra; o QML exibe a mesma.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from kbash.core.model import erro_de_entrada


def test_vazio_e_valido_para_qualquer_tipo() -> None:
    for kind in ("number", "date", "time"):
        assert erro_de_entrada(kind, "", "1", "10") == ""


def test_numero_dentro_da_faixa_e_valido() -> None:
    assert erro_de_entrada("number", "5", "1", "10") == ""
    assert erro_de_entrada("number", "2.5", "1", "10") == ""
    assert erro_de_entrada("number", "1", "1", "10") == ""  # limite incluso
    assert erro_de_entrada("number", "10", "1", "10") == ""


def test_numero_fora_da_faixa_tem_mensagem_de_limite() -> None:
    assert erro_de_entrada("number", "0", "1", "10") == "mínimo: 1"
    assert erro_de_entrada("number", "11", "1", "10") == "máximo: 10"
    assert erro_de_entrada("number", "-3", "1", "") == "mínimo: 1"
    assert erro_de_entrada("number", "99999", "", "10") == "máximo: 10"


def test_decimal_fora_da_faixa_e_recusado_tambem() -> None:
    # o terminal em bash só comparava inteiros; aqui a comparação é numérica
    assert erro_de_entrada("number", "0.5", "1", "10") == "mínimo: 1"
    assert erro_de_entrada("number", "10.5", "1", "10") == "máximo: 10"


def test_numero_invalido_nao_passa_pela_faixa() -> None:
    for valor in ("abc", "nan", "inf", "1e", "1_0", "--1"):
        assert erro_de_entrada("number", valor, "", "") == "digite um número"


def test_data_impossivel_e_recusada() -> None:
    assert erro_de_entrada("date", "2026-02-28", "", "") == ""
    assert erro_de_entrada("date", "2026-02-30", "", "") == "formato inválido (use AAAA-MM-DD)"
    assert erro_de_entrada("date", "2026-13-01", "", "") == "formato inválido (use AAAA-MM-DD)"
    assert erro_de_entrada("date", "26-01-01", "", "") == "formato inválido (use AAAA-MM-DD)"


def test_hora_fora_do_dia_e_recusada() -> None:
    assert erro_de_entrada("time", "23:59", "", "") == ""
    assert erro_de_entrada("time", "24:00", "", "") == "formato inválido (use HH:MM)"
    assert erro_de_entrada("time", "23:60", "", "") == "formato inválido (use HH:MM)"
    assert erro_de_entrada("time", "9:00", "", "") == "formato inválido (use HH:MM)"


def test_tipo_desconhecido_levanta_erro_claro() -> None:
    with pytest.raises(ValueError):
        erro_de_entrada("cor", "azul", "", "")


@settings(max_examples=200, deadline=None)
@given(
    minimo=st.integers(min_value=-1000, max_value=1000),
    tamanho=st.integers(min_value=0, max_value=1000),
    deslocamento=st.integers(min_value=0, max_value=1000),
)
def test_propriedade_numero_na_faixa_nunca_e_recusado(minimo: int, tamanho: int, deslocamento: int) -> None:
    """Propriedade: todo inteiro entre min e max passa; fora dele a mensagem diz o limite violado."""
    maximo = minimo + tamanho
    dentro = minimo + min(deslocamento, tamanho)
    assert erro_de_entrada("number", str(dentro), str(minimo), str(maximo)) == ""
    abaixo = erro_de_entrada("number", str(minimo - 1), str(minimo), str(maximo))
    acima = erro_de_entrada("number", str(maximo + 1), str(minimo), str(maximo))
    assert abaixo == f"mínimo: {minimo}"
    assert acima == f"máximo: {maximo}"
    assert math.isfinite(float(dentro))

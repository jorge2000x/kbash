"""Propriedades de ``option_errors``: nunca quebra e decide faixa como a aritmética."""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from kbash.core.parser import parse_text
from kbash.core.planner import option_errors

CAB = "#!/usr/bin/env bash\n#@runtime 1\n#@name P\n"
ANOTACOES = (
    '#@option n type=number label="N" min=0 max=10',
    '#@option s type=string label="S" pattern="^[a-z]+$" minlen=2 maxlen=5',
    '#@option c type=choice label="C" choices="a,b"',
    '#@option m type=multi label="M" choices="a,b,c"',
    '#@option d type=date label="D"',
    '#@option h type=time label="H"',
    '#@option b type=bool label="B"',
    '#@option r type=string label="R" required',
)
SCRIPT = parse_text(CAB + "\n".join(ANOTACOES) + "\n#@step s1\ns1() { :; }\n", Path("p.sh")).script
IDS_DE_VALOR = {option.id for option in SCRIPT.options if option.carries_value}


@settings(max_examples=300, deadline=None)
@given(
    valores=st.dictionaries(
        st.sampled_from(sorted(IDS_DE_VALOR)), st.text(max_size=40), max_size=8
    )
)
def test_option_errors_nunca_quebra_e_so_aponta_opcoes_com_valor(valores: dict[str, str]) -> None:
    erros = option_errors(SCRIPT, valores)
    assert set(erros) <= IDS_DE_VALOR
    assert all(isinstance(mensagem, str) and mensagem for mensagem in erros.values())


@settings(max_examples=300, deadline=None)
@given(numero=st.integers(min_value=-1000, max_value=1000))
def test_faixa_numerica_bate_com_a_aritmetica(numero: int) -> None:
    erros = option_errors(SCRIPT, {"n": str(numero)})
    dentro = 0 <= numero <= 10
    assert ("n" not in erros) == dentro

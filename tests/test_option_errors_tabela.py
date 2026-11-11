"""Caracterização de ``option_errors``: um tipo de opção x valores de borda.

Os esperados foram medidos no comportamento atual, antes da refatoração da função
(um ``if`` por tipo). A refatoração não pode mudar nenhuma mensagem nem a decisão de
aceitar ou recusar um valor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kbash.core.parser import parse_text
from kbash.core.planner import option_errors

CABECALHO = "#!/usr/bin/env bash\n#@runtime 1\n#@name E\n"

CASOS = [('#@option o type=bool label="B"', '', None),
 ('#@option o type=bool label="B"', '1', None),
 ('#@option o type=bool label="B"', '0', None),
 ('#@option o type=bool label="B"', 'true', None),
 ('#@option o type=bool label="B"', 'FALSE', None),
 ('#@option o type=bool label="B"', 'yes', None),
 ('#@option o type=bool label="B"', 'sim', 'use 0/1 para booleano'),
 ('#@option o type=bool label="B"', ' on ', None),
 ('#@option o type=bool label="B"', '2', 'use 0/1 para booleano'),
 ('#@option o type=string label="S" pattern="^[a-z]+$" minlen=2 maxlen=4', '', None),
 ('#@option o type=string label="S" pattern="^[a-z]+$" minlen=2 maxlen=4', 'ab', None),
 ('#@option o type=string label="S" pattern="^[a-z]+$" minlen=2 maxlen=4',
  'abcde',
  "valor maior que maxlen='4'"),
 ('#@option o type=string label="S" pattern="^[a-z]+$" minlen=2 maxlen=4',
  'A',
  "valor 'A' não casa com pattern"),
 ('#@option o type=string label="S" pattern="^[a-z]+$" minlen=2 maxlen=4',
  'a1',
  "valor 'a1' não casa com pattern"),
 ('#@option o type=string label="S" pattern="^[a-z]+$" minlen=2 maxlen=4', 'abc', None),
 ('#@option o type=string label="S" pattern="^[a-z]+$" minlen=2 maxlen=4', ' ab ', None),
 ('#@option o type=string label="S" pattern="^[a-z]+$" minlen=2 maxlen=4', 'a', "valor menor que minlen='2'"),
 ('#@option o type=password label="P" minlen=4', '', None),
 ('#@option o type=password label="P" minlen=4', 'x', "valor menor que minlen='4'"),
 ('#@option o type=password label="P" minlen=4', 'xyz', "valor menor que minlen='4'"),
 ('#@option o type=password label="P" minlen=4', 'abcd', None),
 ('#@option o type=text label="T" maxlen=3', 'abcd', "valor maior que maxlen='3'"),
 ('#@option o type=text label="T" maxlen=3', 'abc', None),
 ('#@option o type=text label="T" maxlen=3', '', None),
 ('#@option o type=text label="T" maxlen=3', '   ', None),
 ('#@option o type=choice label="C" choices="azul,verde"', '', None),
 ('#@option o type=choice label="C" choices="azul,verde"', 'azul', None),
 ('#@option o type=choice label="C" choices="azul,verde"',
  'roxo',
  "valor inválido 'roxo' (esperado um de: azul, verde)"),
 ('#@option o type=choice label="C" choices="azul,verde"', ' verde ', None),
 ('#@option o type=choice label="C" choices="azul,verde"',
  'azul,verde',
  "valor inválido 'azul,verde' (esperado um de: azul, verde)"),
 ('#@option o type=multi label="M" choices="a,b,c"', '', None),
 ('#@option o type=multi label="M" choices="a,b,c"', 'a', None),
 ('#@option o type=multi label="M" choices="a,b,c"', 'a, b', None),
 ('#@option o type=multi label="M" choices="a,b,c"', 'a,,b', None),
 ('#@option o type=multi label="M" choices="a,b,c"', 'a,z', "valor inválido 'z' (esperado um de: a, b, c)"),
 ('#@option o type=multi label="M" choices="a,b,c"', '  c  ', None),
 ('#@option o type=multi label="M" choices="a,b,c"', ',', None),
 ('#@option o type=number label="N" min=0 max=10', '', None),
 ('#@option o type=number label="N" min=0 max=10', 'abc', "valor 'abc' não é número"),
 ('#@option o type=number label="N" min=0 max=10', '-1', "valor '-1' abaixo de min='0'"),
 ('#@option o type=number label="N" min=0 max=10', '0', None),
 ('#@option o type=number label="N" min=0 max=10', '10', None),
 ('#@option o type=number label="N" min=0 max=10', '10.5', "valor '10.5' acima de max='10'"),
 ('#@option o type=number label="N" min=0 max=10', '1e1', None),
 ('#@option o type=number label="N" min=0 max=10', ' 5 ', None),
 ('#@option o type=number label="N" min=0 max=10', 'nan', None),
 ('#@option o type=slider label="V" min=0 max=100 step=5', '50', None),
 ('#@option o type=slider label="V" min=0 max=100 step=5', '101', "valor '101' acima de max='100'"),
 ('#@option o type=slider label="V" min=0 max=100 step=5', '-0.1', "valor '-0.1' abaixo de min='0'"),
 ('#@option o type=slider label="V" min=0 max=100 step=5', '100', None),
 ('#@option o type=date label="D"', '', None),
 ('#@option o type=date label="D"', '2026-12-31', None),
 ('#@option o type=date label="D"', '2026-02-30', "data '2026-02-30' inválida (use AAAA-MM-DD)"),
 ('#@option o type=date label="D"', '31/12/2026', "data '31/12/2026' inválida (use AAAA-MM-DD)"),
 ('#@option o type=date label="D"', ' 2026-01-01 ', None),
 ('#@option o type=time label="H"', '', None),
 ('#@option o type=time label="H"', '12:30', None),
 ('#@option o type=time label="H"', '25:00', "hora '25:00' inválida (use HH:MM)"),
 ('#@option o type=time label="H"', '1230', "hora '1230' inválida (use HH:MM)"),
 ('#@option o type=time label="H"', '23:59', None),
 ('#@option o type=string label="R" required', '', None),
 ('#@option o type=string label="R" required', '   ', None),
 ('#@option o type=string label="R" required', 'x', None),
 ('#@option o type=path label="Caminho"', '', None),
 ('#@option o type=path label="Caminho"', '/tmp', None)]


@pytest.mark.parametrize(("anotacao", "valor", "esperado"), CASOS)
def test_option_errors_caracterizacao(anotacao: str, valor: str, esperado: str | None) -> None:
    script = parse_text(CABECALHO + anotacao + "\n", Path("e.sh")).script
    erros = option_errors(script, {"o": valor})
    assert erros.get("o") == esperado

"""#@id do script: segmentos seguros, porque o id vira parte de caminhos (IPC, predefinições).

Achado: `#@id ../x` passava com aviso; o id entrava no nome do diretório de trabalho e do
IPC, e a execução falhava antes do primeiro step. Agora é erro de parse.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kbash.core.errors import ParseError
from kbash.core.parser import parse_text

HEADER = "#!/bin/bash\n#@runtime 1\n#@name X\n"
PASSO = "#@step a\na() { :; }\n"


@pytest.mark.parametrize("valido", ["backup", "meu-backup_2", "A1", "com.exemplo.app"])
def test_ids_seguros_sao_aceitos(valido: str) -> None:
    script = parse_text(f"{HEADER}#@id {valido}\n{PASSO}", Path("/tmp/x.sh")).script
    assert script.id == valido


@pytest.mark.parametrize(
    "invalido",
    ["../x", "a/b", "meu backup", "..", "a..b", ".oculto", "a" * 65, "com/exemplo", "ção"],
)
def test_ids_inseguros_sao_erro_de_parse(invalido: str) -> None:
    with pytest.raises(ParseError, match="#@id"):
        parse_text(f"{HEADER}#@id {invalido}\n{PASSO}", Path("/tmp/x.sh"))


def test_id_ausente_usa_o_slug_do_nome() -> None:
    script = parse_text(f"{HEADER}{PASSO}", Path("/tmp/x.sh")).script
    assert script.id == "x"

"""Hash do script é o do arquivo bruto, qualquer que seja a API usada.

Achado: `sha256_of` hashea os bytes do arquivo, mas `parse_text` hashea o texto
sem o shebang. O mesmo arquivo tinha dois hashes. Regra adotada: o hash é o
do arquivo bruto (o mesmo que a GUI grava no cabeçalho salvo).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from kbash.core.parser import parse_script, parse_text, sha256_of

CORPO = "#!/bin/bash\n#@runtime 1\n#@name X\n#@step run\nrun() { :; }\n"


def test_parse_script_hash_equals_the_file_hash(tmp_path: Path) -> None:
    arquivo = tmp_path / "x.sh"
    arquivo.write_text(CORPO, encoding="utf-8")
    assert parse_script(arquivo).sha256 == sha256_of(arquivo)


def test_parse_text_hash_is_the_hash_of_the_text_as_given() -> None:
    esperado = hashlib.sha256(CORPO.encode("utf-8")).hexdigest()
    assert parse_text(CORPO).script.sha256 == esperado


def test_hash_is_the_same_with_and_without_shebang_handling() -> None:
    # o shebang sai do parse, mas não do hash
    com_shebang = parse_text(CORPO).script.sha256
    sem_shebang = parse_text(CORPO.split("\n", 1)[1]).script.sha256
    assert com_shebang != sem_shebang

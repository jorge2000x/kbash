"""Gravação de predefinições: temporário com nome aleatório e criação exclusiva.

Achado: o temporário era `<arquivo>.json.tmp`, previsível. Um symlink plantado nesse
caminho fazia `write_text` sobrescrever o alvo do link.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from kbash.gui.presets import preset_file, write_presets


def test_symlink_no_temporario_antigo_nao_e_seguido(tmp_path: Path) -> None:
    pasta = tmp_path / "predefinicoes"
    vitima = tmp_path / "vitima.txt"
    vitima.write_text("intacto", encoding="utf-8")
    path = preset_file("meu", pasta)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(vitima, path.with_suffix(".json.tmp"))

    write_presets("meu", {"A": {"x": "1"}}, pasta)

    assert vitima.read_text(encoding="utf-8") == "intacto"
    assert json.loads(path.read_text(encoding="utf-8")) == {"A": {"x": "1"}}


def test_gravacao_nao_deixa_temporario_para_tras(tmp_path: Path) -> None:
    pasta = tmp_path / "predefinicoes"
    write_presets("meu", {"A": {}}, pasta)
    write_presets("meu", {"A": {}, "B": {}}, pasta)
    diretorio = preset_file("meu", pasta).parent
    assert sorted(item.name for item in diretorio.iterdir()) == [preset_file("meu", pasta).name]

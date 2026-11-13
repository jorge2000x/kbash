"""Ícone da janela dentro do AppImage: o SVG embutido em ``$APPDIR`` (§10.0).

Fora do bundle não há ``APPDIR``; a janela cai no ícone de tema, como antes.
"""

from __future__ import annotations

from pathlib import Path

from kbash.gui.library import icone_do_bundle

CAMINHO_DO_ICONE = Path("usr") / "share" / "icons" / "hicolor" / "scalable" / "apps" / "kbash.svg"


def test_sem_appdir_nao_ha_icone_do_bundle() -> None:
    assert icone_do_bundle({}) is None


def test_appdir_com_svg_devolve_o_caminho(tmp_path: Path) -> None:
    arquivo = tmp_path / CAMINHO_DO_ICONE
    arquivo.parent.mkdir(parents=True)
    arquivo.write_text("<svg/>", encoding="utf-8")
    assert icone_do_bundle({"APPDIR": str(tmp_path)}) == arquivo


def test_appdir_sem_o_arquivo_cai_para_none(tmp_path: Path) -> None:
    assert icone_do_bundle({"APPDIR": str(tmp_path)}) is None


def test_appdir_vazio_e_ignorado() -> None:
    assert icone_do_bundle({"APPDIR": ""}) is None

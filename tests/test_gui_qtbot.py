"""Smoke tests da GUI com pytest-qt (``qtbot``): a janela sobe, o tema Breeze fica ativo e
a navegação entre páginas responde.

Diferente de ``test_gui.py``, não percorre a árvore de itens QML: esse percurso derrubava o
processo com segfault no ambiente de desenvolvimento (Kirigami do Ubuntu 26.04 com PySide6
do pip). Aqui só se usam propriedades e sinais estáveis.

Precisa do módulo Kirigami instalado (ver ``tools/build-appimage.sh``). Sem ele, os testes
são pulados com o motivo, em vez de falharem.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="GUI exige PySide6")
pytest.importorskip("pytestqt", reason="estes testes usam pytest-qt")

from PySide6.QtQuickControls2 import QQuickStyle

from kbash.gui import app as gui_app

SCRIPT = """#!/usr/bin/env bash
#@runtime 1
#@name Smoke
#@title Smoke
#@step a
#@title Passo A
a() { :; }

#@step b
#@depends a
#@title Passo B
b() { :; }
"""


@pytest.fixture()
def janela(qtbot, tmp_path: Path):
    """Cria a aplicação Qt de verdade e devolve (engine, roots, bridge)."""
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QGuiApplication

    existente = QCoreApplication.instance()
    if existente is not None and not isinstance(existente, QGuiApplication):
        # outro teste criou uma QCoreApplication neste processo; a GUI precisa de
        # QGuiApplication. Rode tests/test_gui_qtbot.py em processo próprio.
        pytest.skip("QCoreApplication já criada por outro teste neste processo")
    script = tmp_path / "smoke.sh"
    script.write_text(SCRIPT, encoding="utf-8")
    try:
        application, engine, roots = gui_app.create_engine(script)
    except RuntimeError as erro:
        if "Kirigami indisponível" in str(erro):
            pytest.skip(str(erro))
        raise
    bridge = engine.rootContext().contextProperty("bridge")
    yield application, roots, bridge
    bridge.shutdown()
    application.processEvents()


def test_janela_principal_sobe(qtbot, janela) -> None:
    _application, roots, _bridge = janela
    assert roots, "main.qml não produziu nenhuma janela"
    qtbot.waitUntil(lambda: bool(roots[0].property("visible")), timeout=10_000)


def test_tema_breeze_fica_ativo(qtbot, janela) -> None:
    """O tema escolhido pelo código é o que o Qt Quick Controls está usando de fato."""
    _application, roots, _bridge = janela
    qtbot.waitUntil(lambda: bool(roots[0].property("visible")), timeout=10_000)
    esperado = "org.kde.breeze" if gui_app._breeze_disponivel() else "Basic"
    assert gui_app._style() == esperado
    assert QQuickStyle.name() == esperado


def test_navegacao_entre_paginas(qtbot, janela) -> None:
    _application, roots, bridge = janela
    qtbot.waitUntil(lambda: bool(roots[0].property("visible")), timeout=10_000)
    bridge.goToPage(1)
    qtbot.waitUntil(lambda: bridge.page == 1, timeout=10_000)
    bridge.goToPage(0)
    qtbot.waitUntil(lambda: bridge.page == 0, timeout=10_000)

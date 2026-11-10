"""Fixtures compartilhadas pelos testes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture()
def fake_pkexec_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Coloca um ``pkexec`` falso no PATH (SPEC.md §9.2).

    ``pkexec true`` (autorização) é aceito; qualquer outro argv é executado sem
    elevação, o que preserva o ``env -i`` com as variáveis ``RT_*``/``OPT_*``.
    Assim os testes exercitam o wrapping real sem depender do polkit do host.
    """
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    tool = bin_dir / "pkexec"
    tool.write_text('#!/bin/sh\n[ "$1" = true ] && exit 0\nexec "$@"\n', encoding="utf-8")
    tool.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return bin_dir


@pytest.fixture(autouse=True)
def bridges_encerrados_ao_fim_do_teste(monkeypatch: pytest.MonkeyPatch):
    """Encerra todo bridge que o teste criou com ``load_bridge``.

    O bridge tem um QTimer de 50 ms e threads de ação. Sem ``shutdown()``, eles seguem
    vivos entre testes e o ``processEvents`` do pytest-qt pode cair com segfault
    (medido: 13 de 40 execuções caíam sem isso; 0 de 40 com isso). Os testes precisam
    chamar ``bridge_module.load_bridge`` (pelo módulo) para serem rastreados.
    Sem PySide6 instalado, a fixture não faz nada.
    """
    try:
        from kbash.gui import bridge as bridge_module
    except ImportError:
        yield
        return
    criados: list[Any] = []
    original = bridge_module.load_bridge

    def rastreado(*args: Any, **kwargs: Any) -> Any:
        bridge = original(*args, **kwargs)
        criados.append(bridge)
        return bridge

    monkeypatch.setattr(bridge_module, "load_bridge", rastreado)
    yield
    for bridge in criados:
        bridge.shutdown()


@pytest.fixture(scope="session")
def qt_core_app():
    """QCoreApplication viva até o fim da sessão.

    Sem esta referência, um fixture de módulo que devolvia a aplicação a deixava ser
    coletada ao fim do módulo; o ``processEvents`` do pytest-qt, no teste seguinte,
    caía com segfault (intermitente, dependia do coletor de lixo).
    """
    from PySide6.QtCore import QCoreApplication

    return QCoreApplication.instance() or QCoreApplication([])


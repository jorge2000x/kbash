"""Fixtures compartilhadas pelos testes."""

from __future__ import annotations

import os
from pathlib import Path

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


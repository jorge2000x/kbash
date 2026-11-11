"""Diretório do IPC: XDG_RUNTIME_DIR inutilizável cai para o temporário do sistema.

Achado: com XDG_RUNTIME_DIR apontando para um lugar que não aceita escrita, a
criação levantava OSError cru e a execução abortava antes de emitir eventos.
"""

from __future__ import annotations

import stat
import tempfile
from pathlib import Path

import pytest

from kbash.core.errors import KbashError
from kbash.core.ipc import IpcChannel, IpcError


def _bloqueado(caminho: Path) -> Path:
    """Caminho que não pode virar diretório: um arquivo comum no meio dele."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("arquivo", encoding="utf-8")
    return caminho / "sub"


@pytest.fixture
def temporario(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    alvo = tmp_path / "tmpdir"
    alvo.mkdir()
    monkeypatch.setenv("TMPDIR", str(alvo))
    monkeypatch.setattr(tempfile, "tempdir", None)  # gettempdir relê TMPDIR
    return alvo


def test_xdg_usavel_e_usado(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, temporario: Path) -> None:
    xdg = tmp_path / "run"
    xdg.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(xdg))
    diretorio = IpcChannel._make_dir("")
    assert diretorio.parent == xdg
    assert stat.S_IMODE(diretorio.stat().st_mode) == 0o700


def test_xdg_inutilizavel_cai_para_o_temporario(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, temporario: Path
) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(_bloqueado(tmp_path / "ruim")))
    diretorio = IpcChannel._make_dir("")
    assert diretorio.parent == temporario
    assert stat.S_IMODE(diretorio.stat().st_mode) == 0o700


def test_sem_nenhum_lugar_gravavel_vira_ipc_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, temporario: Path
) -> None:
    # gettempdir já tem o próprio fallback (cai para /tmp), então o temporário
    # bloqueado é simulado na própria função, não pela variável de ambiente.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(_bloqueado(tmp_path / "ruim")))
    bloqueado_tmp = str(_bloqueado(tmp_path / "tmp-ruim"))
    monkeypatch.setattr(tempfile, "gettempdir", lambda: bloqueado_tmp)
    with pytest.raises(IpcError) as erro:
        IpcChannel._make_dir("")
    assert isinstance(erro.value, KbashError)
    assert "IPC" in str(erro.value) or "ipc" in str(erro.value)

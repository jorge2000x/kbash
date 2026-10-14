"""Predefinições pelo bridge (salvar, carregar, apagar), sem gravar no repositório."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6", reason="GUI exige PySide6")

from PySide6.QtCore import QCoreApplication

from kbash.gui.bridge import load_bridge

SCRIPT = (
    "#!/usr/bin/env bash\n#@runtime 1\n#@name Backup Nuvem\n#@id backup\n"
    '#@option pasta type=string label="Pasta" default=/padrao\n'
    '#@option conta type=string label="Conta" default=\n'
    '#@option senha type=password label="Senha"\n'
    "#@step a\na() { :; }\n"
)


@pytest.fixture(scope="module")
def app():
    return QCoreApplication.instance() or QCoreApplication([])


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    """Pasta do programa temporária: o ``kbash-config`` vai para aqui."""
    program = tmp_path / "programa"
    program.mkdir()
    monkeypatch.setenv("APPIMAGE", str(program / "kbash.AppImage"))
    return program


def _bridge(tmp_path: Path, app) -> object:  # noqa: ARG001
    script = tmp_path / "backup.kbash"
    script.write_text(SCRIPT, encoding="utf-8")
    return load_bridge(script)


def test_save_skips_passwords_and_writes_the_config_folder(app, tmp_path: Path, home: Path) -> None:
    bridge = _bridge(tmp_path, app)
    bridge.setOption("pasta", "/home/ana/Docs")
    bridge.setOption("conta", "ana@x.com")
    bridge.setOption("senha", "segredo")
    assert bridge.savePreset("Backup casa") is True

    data = json.loads((home / "kbash-config" / "backup.json").read_text(encoding="utf-8"))
    assert data["Backup casa"]["pasta"] == "/home/ana/Docs"
    assert data["Backup casa"]["conta"] == "ana@x.com"
    assert "senha" not in data["Backup casa"]
    assert "segredo" not in json.dumps(data)


def test_names_are_listed_and_load_restores_values(app, tmp_path: Path, home: Path) -> None:
    bridge = _bridge(tmp_path, app)
    bridge.setOption("pasta", "/a")
    bridge.savePreset("Casa")
    bridge.setOption("pasta", "/b")
    bridge.savePreset("Trabalho")
    assert list(bridge.property("presetNames")) == ["Casa", "Trabalho"]

    bridge.setOption("pasta", "/outra-coisa")
    assert bridge.loadPreset("Casa") is True
    assert bridge._options_model.values()["pasta"] == "/a"


def test_load_does_not_touch_passwords(app, tmp_path: Path, home: Path) -> None:
    bridge = _bridge(tmp_path, app)
    bridge.setOption("senha", "digitada-agora")
    bridge.setOption("pasta", "/a")
    bridge.savePreset("Casa")
    bridge.loadPreset("Casa")
    assert bridge._options_model.values()["senha"] == "digitada-agora"


def test_delete_removes_only_that_preset(app, tmp_path: Path, home: Path) -> None:
    bridge = _bridge(tmp_path, app)
    bridge.savePreset("Um")
    bridge.savePreset("Dois")
    assert bridge.deletePreset("Um") is True
    assert list(bridge.property("presetNames")) == ["Dois"]
    assert bridge.deletePreset("Inexistente") is False


def test_bad_name_is_refused_without_writing(app, tmp_path: Path, home: Path) -> None:
    bridge = _bridge(tmp_path, app)
    assert bridge.savePreset("   ") is False
    assert not (home / "kbash-config").exists()


def test_corrupt_file_is_reported_and_app_keeps_working(app, tmp_path: Path, home: Path) -> None:
    (home / "kbash-config").mkdir()
    (home / "kbash-config" / "backup.json").write_text("{quebrado", encoding="utf-8")
    bridge = _bridge(tmp_path, app)
    assert list(bridge.property("presetNames")) == []
    # salvar recusa: não apaga o que o usuário escreveu no arquivo
    assert bridge.savePreset("Novo") is False
    assert (home / "kbash-config" / "backup.json").read_text(encoding="utf-8") == "{quebrado"

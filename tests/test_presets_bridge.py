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


def _bridge(tmp_path: Path, app) -> object:
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


CHOICE_SCRIPT = (
    "#!/usr/bin/env bash\n#@runtime 1\n#@name Escolha\n#@id escolha\n"
    '#@option perfil type=choice label="Perfil" choices="rapido,completo" default=rapido\n'
    "#@step a\na() { :; }\n"
)


def test_unknown_option_ids_in_the_file_are_ignored_on_load(app, tmp_path: Path, home: Path) -> None:
    bridge = _bridge(tmp_path, app)
    (home / "kbash-config").mkdir()
    (home / "kbash-config" / "backup.json").write_text(
        json.dumps({"Estranha": {"pasta": "/ok", "nao_existe": "x"}}), encoding="utf-8")
    bridge._reload_presets()
    assert bridge.loadPreset("Estranha") is True
    assert "nao_existe" not in bridge._options_model.values()
    assert bridge._options_model.values()["pasta"] == "/ok"


def test_invalid_choice_from_a_preset_is_reported_as_an_option_error(app, tmp_path: Path, home: Path) -> None:
    script = tmp_path / "escolha.kbash"
    script.write_text(CHOICE_SCRIPT, encoding="utf-8")
    bridge = load_bridge(script)
    (home / "kbash-config").mkdir()
    (home / "kbash-config" / "escolha.json").write_text(
        json.dumps({"Antiga": {"perfil": "removido-da-versao-nova"}}), encoding="utf-8")
    bridge._reload_presets()
    bridge.loadPreset("Antiga")
    assert bridge._options_model.error("perfil") != ""


def test_unicode_name_and_spaced_script_id_round_trip(app, tmp_path: Path, home: Path) -> None:
    script = tmp_path / "x.kbash"
    script.write_text(SCRIPT.replace("#@id backup", "#@id meu backup"), encoding="utf-8")
    bridge = load_bridge(script)
    bridge.setOption("pasta", "/pão/açúcar")
    assert bridge.savePreset("Família — casa ✓") is True
    assert list(bridge.property("presetNames")) == ["Família — casa ✓"]
    bridge.setOption("pasta", "/outra")
    assert bridge.loadPreset("Família — casa ✓") is True
    assert bridge._options_model.values()["pasta"] == "/pão/açúcar"


def test_saving_the_same_name_overwrites_it(app, tmp_path: Path, home: Path) -> None:
    bridge = _bridge(tmp_path, app)
    bridge.setOption("pasta", "/um")
    bridge.savePreset("Casa")
    bridge.setOption("pasta", "/dois")
    bridge.savePreset("Casa")
    assert list(bridge.property("presetNames")) == ["Casa"]
    bridge.setOption("pasta", "/x")
    bridge.loadPreset("Casa")
    assert bridge._options_model.values()["pasta"] == "/dois"


def test_unwritable_config_folder_reports_error_and_keeps_state(app, tmp_path: Path, home: Path) -> None:
    (home / "kbash-config").write_text("sou um arquivo, não uma pasta", encoding="utf-8")
    bridge = _bridge(tmp_path, app)
    assert bridge.savePreset("Casa") is False
    assert list(bridge.property("presetNames")) == []


def test_preset_file_is_valid_json_with_only_text_values(app, tmp_path: Path, home: Path) -> None:
    bridge = _bridge(tmp_path, app)
    bridge.setOption("senha", "nao-grava")
    bridge.savePreset("Teste")
    data = json.loads((home / "kbash-config" / "backup.json").read_text(encoding="utf-8"))
    assert all(isinstance(v, str) for values in data.values() for v in values.values())

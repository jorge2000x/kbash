"""Predefinições em JSON (gui/presets.py): leitura, escrita e recusas. Sem Qt."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kbash.gui.presets import (
    CONFIG_DIR_NAME,
    PresetError,
    check_name,
    preset_file,
    program_folder,
    read_presets,
    write_presets,
)


def test_round_trip_keeps_names_and_values(tmp_path: Path) -> None:
    data = {"Backup casa": {"pasta": "/home/ana/Docs", "conta": "ana@x.com"}}
    write_presets("backup", data, tmp_path)
    assert read_presets("backup", tmp_path) == data


def test_file_lives_in_kbash_config_next_to_the_program(tmp_path: Path) -> None:
    path = write_presets("backup", {"a": {"x": "1"}}, tmp_path)
    assert path == tmp_path / CONFIG_DIR_NAME / "backup.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": {"x": "1"}}


def test_missing_file_is_no_presets(tmp_path: Path) -> None:
    assert read_presets("nada", tmp_path) == {}


def test_corrupt_file_raises_preset_error(tmp_path: Path) -> None:
    preset_file("bad", tmp_path).parent.mkdir(parents=True)
    preset_file("bad", tmp_path).write_text("{não é json", encoding="utf-8")
    with pytest.raises(PresetError):
        read_presets("bad", tmp_path)


def test_root_must_be_an_object(tmp_path: Path) -> None:
    preset_file("lista", tmp_path).parent.mkdir(parents=True)
    preset_file("lista", tmp_path).write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(PresetError):
        read_presets("lista", tmp_path)


def test_values_are_coerced_and_nested_garbage_is_dropped(tmp_path: Path) -> None:
    preset_file("mix", tmp_path).parent.mkdir(parents=True)
    preset_file("mix", tmp_path).write_text(
        json.dumps({
            "ok": {"n": 3, "b": True, "t": "x", "lista": [1], "nulo": None},
            "lixo": "não é objeto",
        }),
        encoding="utf-8",
    )
    assert read_presets("mix", tmp_path) == {"ok": {"n": "3", "b": "1", "t": "x"}}


def test_script_id_cannot_escape_the_config_folder(tmp_path: Path) -> None:
    path = preset_file("../../etc/passwd", tmp_path)
    assert path.parent == tmp_path / CONFIG_DIR_NAME
    assert "/" not in path.name and ".." not in path.name


@pytest.mark.parametrize("name", ["", "   ", "linha\numa", "x" * 61])
def test_bad_names_are_refused(name: str) -> None:
    with pytest.raises(PresetError):
        check_name(name)


def test_name_is_trimmed() -> None:
    assert check_name("  Backup casa  ") == "Backup casa"


def test_program_folder_follows_the_appimage(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APPIMAGE", str(tmp_path / "kbash.AppImage"))
    assert program_folder() == tmp_path
    monkeypatch.delenv("APPIMAGE")
    assert program_folder().name != ""

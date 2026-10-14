"""Biblioteca da tela inicial (gui/library.py): leitura estática, sem Qt."""

from __future__ import annotations

from pathlib import Path

from kbash.gui.library import DEV_SCRIPTS_DIR, list_library, program_scripts_dir

GOOD = (
    "#!/usr/bin/env bash\n#@runtime 1\n#@name Bom\n#@desc Faz algo\n"
    "#@step a\na() { :; }\n"
)


def test_lists_kbash_files_sorted_with_name_and_description(tmp_path: Path) -> None:
    (tmp_path / "b.kbash").write_text(GOOD.replace("Bom", "Segundo"), encoding="utf-8")
    (tmp_path / "a.kbash").write_text(GOOD, encoding="utf-8")
    entries = list_library(tmp_path)
    assert [e.path.name for e in entries] == ["a.kbash", "b.kbash"]
    assert entries[0].name == "Bom" and entries[0].description == "Faz algo"
    assert all(e.valid for e in entries)


def test_ignores_sh_and_other_files(tmp_path: Path) -> None:
    (tmp_path / "x.sh").write_text(GOOD, encoding="utf-8")
    (tmp_path / "notas.txt").write_text("oi", encoding="utf-8")
    assert list_library(tmp_path) == []


def test_invalid_script_is_listed_disabled_and_does_not_break_the_list(tmp_path: Path) -> None:
    (tmp_path / "quebrado.kbash").write_text("sem cabeçalho\n", encoding="utf-8")
    (tmp_path / "bom.kbash").write_text(GOOD, encoding="utf-8")
    entries = {e.path.name: e for e in list_library(tmp_path)}
    assert entries["quebrado.kbash"].valid is False
    assert entries["quebrado.kbash"].name == "quebrado"
    assert entries["bom.kbash"].valid is True


def test_directories_named_like_scripts_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "pasta.kbash").mkdir()
    assert list_library(tmp_path) == []


def test_missing_folder_is_an_empty_list(tmp_path: Path) -> None:
    assert list_library(tmp_path / "nao-existe") == []


def test_outside_appimage_the_program_folder_is_the_repo_examples(monkeypatch) -> None:
    monkeypatch.delenv("APPIMAGE", raising=False)
    assert program_scripts_dir() == DEV_SCRIPTS_DIR
    names = [e.path.name for e in list_library()]
    assert "fedora-superpoderoso.kbash" in names


def test_inside_appimage_the_program_folder_is_where_the_appimage_lives(
    tmp_path: Path, monkeypatch
) -> None:
    app = tmp_path / "Pasta"
    app.mkdir()
    (app / "kbash-x86_64.AppImage").write_text("", encoding="utf-8")
    (app / "meu.kbash").write_text(GOOD, encoding="utf-8")
    monkeypatch.setenv("APPIMAGE", str(app / "kbash-x86_64.AppImage"))
    assert program_scripts_dir() == app
    assert [e.path.name for e in list_library()] == ["meu.kbash"]

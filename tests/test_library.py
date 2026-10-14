"""Biblioteca da tela inicial (gui/library.py): leitura estática, sem Qt."""

from __future__ import annotations

from pathlib import Path

from kbash.gui.library import PROGRAM_SCRIPTS_DIR, list_library

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


def test_program_folder_points_to_the_repo_examples() -> None:
    assert PROGRAM_SCRIPTS_DIR.name == "examples"
    names = [e.path.name for e in list_library(PROGRAM_SCRIPTS_DIR)]
    assert "fedora-superpoderoso.kbash" in names

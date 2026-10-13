"""§10.2.0 — três formas de dar um script ao runtime: embutido, argumento e home."""

from __future__ import annotations

from pathlib import Path

import pytest

from rt.cli import embedded_script, main
from rt.core.model import placeholder_script

SCRIPT = "#!/usr/bin/env bash\n#@runtime 1\n#@name Demo\n#@step a\na() { :; }\n"


def write(path: Path, text: str = SCRIPT) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_placeholder_script_has_no_steps_options_or_sha() -> None:
    script = placeholder_script()
    assert script.steps == () and script.options == ()
    assert script.sha256 == ""  # é assim que a GUI sabe que não há script


def test_embedded_script_is_found_under_appdir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("APPDIR", raising=False)
    assert embedded_script() is None
    (tmp_path / "payload").mkdir()
    monkeypatch.setenv("APPDIR", str(tmp_path))
    assert embedded_script() is None  # APPDIR sem payload = home
    write(tmp_path / "payload" / "script.sh")
    assert embedded_script() == tmp_path / "payload" / "script.sh"


def test_bare_script_path_runs_headless_like_rt_run(tmp_path: Path, capsys) -> None:
    path = write(tmp_path / "a.sh")
    assert main([str(path), "--headless", "--yes"]) == 0


def test_check_still_works_with_the_shortcut_disabled_for_commands(tmp_path: Path, capsys) -> None:
    path = write(tmp_path / "b.sh")
    assert main(["check", str(path)]) == 0
    assert "ok" in capsys.readouterr().out



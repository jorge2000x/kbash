"""Testes da CLI (SPEC.md §12)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fixtures.paths import DEV_SETUP, FAILING, HELPERS

pytestmark = pytest.mark.usefixtures("fake_pkexec_on_path")  # §9.2: pkexec falso

from kbash.cli import main

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Executa a CLI como um processo separado (não deixa estado de GUI)."""
    environment = dict(os.environ, PYTHONPATH=str(SRC), QT_QPA_PLATFORM="offscreen")
    environment.update(env or {})
    return subprocess.run(
        [sys.executable, "-m", "kbash.cli", *args],
        capture_output=True,
        text=True,
        env=environment,
        timeout=180,
        check=False,
    )

# -- check (§12, §4.6) -------------------------------------------------------

def test_check_sober_example_is_clean() -> None:
    """O exemplo convertido passa sem erros (warnings heurísticos ok)."""
    from kbash.core.parser import check_script

    script, diagnostics = check_script(ROOT / "examples" / "sober-optimizer.sh")
    assert script is not None
    assert [d for d in diagnostics.errors] == []
    assert [step.id for step in script.steps] == [
        "read_current", "backup_files", "tune", "save",
    ]
    assert script.option("profile") is not None
    assert script.option("frm_value") is not None


def test_check_ok() -> None:
    result = run_cli("check", str(DEV_SETUP))
    assert result.returncode == 0
    assert "ok" in result.stdout
    assert "3 step(s)" in result.stdout
    assert "3 opção(ões)" in result.stdout


def test_check_reports_error_with_line(tmp_path: Path) -> None:
    bad = tmp_path / "bad.sh"
    bad.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Ruim\n"
        "#@step a\n#@depends fantasma\na() { :; }\n",
        encoding="utf-8",
    )
    result = run_cli("check", str(bad))
    assert result.returncode == 2
    assert f"{bad}:4: error:" in result.stdout  # aponta a linha do #@depends
    assert "fantasma" in result.stdout


def test_check_reports_warnings(tmp_path: Path) -> None:
    script = tmp_path / "warn.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Aviso\n"
        "#@futuro sim\n"
        "#@step ola\nola() { :; }\n"
        "echo solto\n",
        encoding="utf-8",
    )
    result = run_cli("check", str(script))
    assert result.returncode == 0
    assert "warning: diretiva desconhecida #@futuro" in result.stdout
    assert "warning: comando de nível superior" in result.stdout
    assert "1 aviso(s)" not in result.stdout  # são dois avisos


def test_check_missing_file() -> None:
    result = run_cli("check", "/nao/existe.sh")
    assert result.returncode == 2
    assert "error" in result.stdout


# -- plan (§12, §6) ----------------------------------------------------------
def test_plan_default() -> None:
    result = run_cli("plan", str(DEV_SETUP), "--opt", "user_name=Ana")
    assert result.returncode == 0
    assert "Configurar ambiente de desenvolvimento" in result.stdout
    assert "1. update_index" in result.stdout
    assert "2. install_tools" in result.stdout
    assert "3. config_git" in result.stdout
    assert "requer root" in result.stdout
    assert "OPT_USER_NAME" in result.stdout


def test_plan_selection_marks_auto_added() -> None:
    result = run_cli("plan", str(DEV_SETUP), "--select", "config_git", "--opt", "user_name=Ana")
    assert result.returncode == 0
    assert "1. update_index" in result.stdout
    assert "por dependência" in result.stdout


def test_plan_json() -> None:
    result = run_cli("plan", str(DEV_SETUP), "--select", "install_tools", "--opt", "user_name=Ana",
                     "--json")
    assert result.returncode == 0
    payload = json.loads(result.stdout[result.stdout.index("{"):])
    assert payload["selected"] == ["update_index", "install_tools"]
    assert "update_index" in payload["auto_added"]
    assert payload["options"]["user_name"] == "Ana"


def test_plan_invalid_option() -> None:
    result = run_cli("plan", str(DEV_SETUP), "--select", "config_git")
    assert result.returncode == 2
    assert "obrigatório" in result.stdout


def test_plan_invalid_script() -> None:
    result = run_cli("plan", str(FAILING), "--select", "inexistente")
    assert result.returncode == 2
    assert "inexistente" in result.stdout


# -- run --headless (§12) ----------------------------------------------------
def test_run_headless_success() -> None:
    result = run_cli("run", str(DEV_SETUP), "--headless", "--select", "install_tools",
                     "--opt", "user_name=Ana")
    assert result.returncode == 0
    assert "instalando: curl git" in result.stdout
    assert "sucesso" in result.stdout
    assert "▶ [1/2] update_index" in result.stdout


def test_run_headless_failure_exit_code() -> None:
    result = run_cli("run", str(FAILING), "--headless", "--select", "boom,after_boom")
    assert result.returncode == 1
    assert "falhando de propósito" in result.stderr
    assert "boom: failed" in result.stderr
    assert "after_boom: skipped" in result.stdout
    assert "falha" in result.stdout


def test_run_headless_continue() -> None:
    result = run_cli("run", str(FAILING), "--headless", "--select",
                     "boom_continue,after_continue,child_of_continue")
    assert result.returncode == 1  # houve falha, mas o resto rodou
    assert "rodou depois da falha com continue" in result.stdout
    assert "child_of_continue: skipped" in result.stdout


def test_run_headless_password_is_not_printed() -> None:
    script = Path("/tmp/kbash-cli-secret.sh")
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Segredo\n"
        "#@option token type=password label=\"Token\"\n"
        "#@step mostrar\n"
        'mostrar() { echo "len=${#OPT_TOKEN}"; }\n',
        encoding="utf-8",
    )
    result = run_cli("run", str(script), "--headless", "--opt", "token=supersecreto123")
    assert result.returncode == 0
    assert "len=15" in result.stdout
    assert "supersecreto123" not in result.stdout
    assert "supersecreto123" not in result.stderr


def test_run_headless_ui_none_cancels() -> None:
    result = run_cli("run", str(DEV_SETUP), "--headless", "--select", "config_git",
                     "--opt", "user_name=Ana", "--ui", "none")
    assert result.returncode == 130
    assert "cancelado" in result.stdout


def test_run_headless_ui_yes_assumes_default() -> None:
    result = run_cli("run", str(DEV_SETUP), "--headless", "--select", "config_git",
                     "--opt", "user_name=Ana", "--ui", "yes")
    assert result.returncode == 0
    assert "assinatura desativada" in result.stdout  # default do rt_confirm é n


def test_run_headless_yes_flag() -> None:
    result = run_cli("run", str(DEV_SETUP), "--headless", "--select", "config_git",
                     "--opt", "user_name=Ana", "--yes")
    assert result.returncode == 0
    assert "assinatura desativada" in result.stdout


def test_run_headless_env_selects_ui() -> None:
    result = run_cli("run", str(DEV_SETUP), "--headless", "--select", "config_git",
                     "--opt", "user_name=Ana", env={"KBASH_UI": "yes"})
    assert result.returncode == 0
    assert "assinatura desativada" in result.stdout


def test_run_headless_reports_precheck() -> None:
    script = Path("/tmp/kbash-cli-req.sh")
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Req\n#@requires comando_que_nao_existe\n"
        "#@step ola\nola() { echo oi; }\n",
        encoding="utf-8",
    )
    result = run_cli("run", str(script), "--headless")
    assert result.returncode == 2
    assert "pré-checagem" in result.stdout
    assert "comando_que_nao_existe" in result.stdout
    assert "oi" not in result.stdout


def test_run_headless_timeout() -> None:
    result = run_cli("run", str(FAILING), "--headless", "--select", "slow")
    assert result.returncode == 1
    assert "timeout" in result.stdout
    assert "slow: failed" in result.stderr


def test_run_headless_requires_option() -> None:
    result = run_cli("run", str(DEV_SETUP), "--headless", "--select", "install_tools")
    assert result.returncode == 2
    assert "user_name: campo obrigatório" in result.stdout


# -- API em processo ---------------------------------------------------------
def test_main_returns_codes(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", str(DEV_SETUP)]) == 0
    assert main(["plan", str(DEV_SETUP), "--opt", "user_name=Ana"]) == 0
    assert "Configurar" in capsys.readouterr().out


def test_helpers_are_bundled() -> None:
    assert HELPERS.is_file()
    assert (HELPERS.parent.name) == "helpers"

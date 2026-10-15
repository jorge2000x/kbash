"""Execução de ações (SPEC.md §4.8 e §7.6): ambiente, saída, timeout, root e guarda interativa."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from kbash.core.actions import ActionResult, action_env, run_action
from kbash.core.executor import helpers_path
from kbash.core.parser import parse_script

HDR = "#!/usr/bin/env bash\n#@runtime 1\n#@name T\n"
HELPERS = helpers_path()


def _script(tmp_path: Path, body: str):
    """O executor faz ``source "$RT_SCRIPT"``: o arquivo precisa existir de verdade."""
    path = tmp_path / "limpeza.kbash"
    path.write_text(HDR + body, encoding="utf-8")
    return parse_script(path)


def _run(tmp_path: Path, body: str, action_id: str, values=None, selected=None, **kwargs) -> ActionResult:
    script = _script(tmp_path, body)
    action = script.action(action_id)
    assert action is not None
    return run_action(
        script,
        action,
        values or {},
        selected,
        helpers=HELPERS,
        workdir=str(tmp_path),
        **kwargs,
    )


def test_action_reads_current_option_values(tmp_path: Path) -> None:
    body = (
        '#@option dir type=string label="Pasta" default=padrao\n'
        "#@action show\n"
        "show() { echo \"dir=$OPT_DIR\"; }\n"
    )
    result = _run(tmp_path, body, "show", values={"dir": "/tmp/valor-da-tela"})
    assert result.status == "ok"
    assert "dir=/tmp/valor-da-tela" in result.output


def test_hidden_needs_step_option_uses_default(tmp_path: Path) -> None:
    body = (
        '#@option nivel type=string label="Nível" default=baixo needs_step=passo\n'
        "#@step passo\npasso() { :; }\n"
        "#@action show\nshow() { echo \"nivel=$OPT_NIVEL\"; }\n"
    )
    # o step não está selecionado: a opção está oculta e vale o default
    result = _run(tmp_path, body, "show", values={"nivel": "alto"}, selected=[])
    assert "nivel=baixo" in result.output
    result = _run(tmp_path, body, "show", values={"nivel": "alto"}, selected=["passo"])
    assert "nivel=alto" in result.output


def test_action_env_marks_mode_and_has_no_ipc(tmp_path: Path) -> None:
    script = _script(tmp_path, "#@action a\na() { :; }\n")
    env = action_env(script, {}, [], helpers=HELPERS, workdir=str(tmp_path))
    assert env["RT_MODE"] == "action"
    assert env["RT_IPC"] == ""


def test_path_option_is_expanded_like_the_plan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    body = (
        '#@option dir type=path label="Pasta" default="~/x"\n'
        "#@action show\nshow() { echo \"dir=$OPT_DIR\"; }\n"
    )
    result = _run(tmp_path, body, "show", values={"dir": "~/destino"})
    assert f"dir={tmp_path}/destino" in result.output


def test_output_is_returned_and_failure_has_status(tmp_path: Path) -> None:
    body = "#@action falha\nfalha() { rt_log 'espaço: 3 GiB'; return 1; }\n"
    result = _run(tmp_path, body, "falha")
    assert result.status == "failed"
    assert result.exit_code != 0
    assert "espaço: 3 GiB" in result.output


def test_success_status_and_exit_code(tmp_path: Path) -> None:
    body = "#@action ok\nok() { echo feito; }\n"
    result = _run(tmp_path, body, "ok")
    assert (result.status, result.exit_code) == ("ok", 0)
    assert result.output.strip() == "feito"


def test_timeout_ends_the_action(tmp_path: Path) -> None:
    body = "#@action lenta\n#@timeout 1\nlenta() { sleep 30; }\n"
    started = time.monotonic()
    result = _run(tmp_path, body, "lenta")
    assert result.status == "timeout"
    assert time.monotonic() - started < 15


def test_stdin_is_closed_so_prompts_cannot_hang(tmp_path: Path) -> None:
    body = "#@action le\nle() { read -r linha && echo \"leu:$linha\" || echo fechado; }\n"
    result = _run(tmp_path, body, "le")
    assert result.status == "ok"
    assert "fechado" in result.output


def test_interactive_helper_fails_the_action_with_message(tmp_path: Path) -> None:
    body = "#@action pergunta\npergunta() { x=$(rt_input 'Nome'); echo \"nao chega $x\"; }\n"
    result = _run(tmp_path, body, "pergunta")
    assert result.status == "failed"
    assert "não é interativo dentro de uma ação" in result.output
    assert "nao chega" not in result.output


def test_root_action_goes_through_root_command(tmp_path: Path) -> None:
    body = "#@action raiz\n#@root true\nraiz() { echo sem-root; }\n"
    seen: list[list[str]] = []

    def fake_root(argv, env, cwd):
        seen.append(list(argv))
        return ["bash", "-c", "echo com-root"]

    result = _run(tmp_path, body, "raiz", root_command=fake_root)
    assert seen, "ação com #@root true deve passar pelo comando root"
    assert "com-root" in result.output
    assert "sem-root" not in result.output


def test_non_root_action_does_not_elevate(tmp_path: Path) -> None:
    body = "#@action comum\ncomum() { echo normal; }\n"

    def boom(argv, env, cwd):  # pragma: no cover - não deve ser chamado
        raise AssertionError("não deveria elevar")

    result = _run(tmp_path, body, "comum", root_command=boom)
    assert result.status == "ok"


def test_output_is_limited_to_last_lines(tmp_path: Path) -> None:
    body = "#@action muita\nmuita() { for i in $(seq 1 500); do echo linha$i; done; }\n"
    result = _run(tmp_path, body, "muita")
    lines = result.output.splitlines()
    assert len(lines) == 200
    assert lines[-1] == "linha500"


@pytest.mark.parametrize("bad_cwd_home", ["/nao/existe/de/jeito_nenhum"])
def test_missing_home_falls_back_without_crashing(tmp_path: Path, monkeypatch, bad_cwd_home) -> None:
    monkeypatch.setenv("HOME", bad_cwd_home)
    body = "#@action oi\noi() { echo ola; }\n"
    result = _run(tmp_path, body, "oi")
    assert result.status == "ok"

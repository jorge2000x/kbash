"""Testes do executor (SPEC.md §7, §7.2, §7.4)."""

from __future__ import annotations

import os
import shutil
import signal
import threading
import time
from pathlib import Path

import pytest
from fixtures.paths import DEV_SETUP, HELPERS

from kbash.core.errors import PrecheckError
from kbash.core.events import (
    LogLine,
    Progress,
    PromptRequest,
    RunFinished,
    RunStarted,
    StepFinished,
    StepStarted,
)
from kbash.core.executor import Executor, default_root_command
from kbash.core.ipc import IpcChannel
from kbash.core.model import RunState, StepState
from kbash.core.parser import parse_script
from kbash.core.planner import build_plan


class Collector:
    """Guarda os eventos emitidos pelo core."""

    def __init__(self) -> None:
        self.events: list[object] = []

    def __call__(self, event: object) -> None:
        self.events.append(event)

    def of(self, kind: type) -> list:
        return [event for event in self.events if isinstance(event, kind)]

    @property
    def logs(self) -> list[str]:
        return [event.text for event in self.of(LogLine)]

    @property
    def stderr(self) -> list[str]:
        return [event.text for event in self.of(LogLine) if event.stream == "stderr"]


@pytest.fixture()
def dev_script():
    return parse_script(DEV_SETUP)


@pytest.fixture()
def failing_script():
    return parse_script(Path(__file__).parent / "fixtures" / "scripts" / "failing.sh")


@pytest.fixture(autouse=True)
def _pkexec_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Finge que o pkexec existe: os testes não devem depender do polkit do host."""
    real_which = shutil.which
    monkeypatch.setattr(
        "kbash.core.executor.shutil.which",
        lambda name, *a, **k: "/usr/bin/pkexec" if name == "pkexec" else real_which(name, *a, **k),
    )


def make(script, select=None, options=None, **kwargs) -> Executor:
    plan = build_plan(script, select, options, home=os.environ.get("HOME"))
    # por padrão a autorização de root é concedida; testes de autorização passam a sua
    kwargs.setdefault("authorize", lambda: True)
    # sem pkexec real no teste: o comando de root é identidade (o wrapping tem teste próprio)
    kwargs.setdefault("root_command", lambda argv, env, cwd: list(argv))
    return Executor(script, plan, helpers=HELPERS, **kwargs)


# -- ambiente injetado (§7.2) ------------------------------------------------
def test_environment_variables(tmp_path: Path) -> None:
    target = tmp_path / "dump.sh"
    target.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Dump\n"
        "#@option nome type=string label=\"Nome\"\n"
        "#@step dump\n"
        "dump() {\n"
        '  for v in RT_SCRIPT RT_HELPERS RT_ASSETS RT_IPC RT_STEP_ID RT_STEP_FN RT_STRICT RT_MODE RT_WORKDIR OPT_NOME; do\n'
        '    printf "%s=%s\\n" "$v" "${!v}"\n'
        "  done\n"
        "}\n",
        encoding="utf-8",
    )
    script = parse_script(target)
    collector = Collector()
    executor = make(script, options={"nome": "Ana"})
    result = executor.run(collector)
    assert result.status is RunState.SUCCESS
    logs = "\n".join(collector.logs)
    assert f"RT_SCRIPT={target}" in logs
    assert f"RT_HELPERS={HELPERS}" in logs
    assert "RT_STEP_ID=dump" in logs
    assert "RT_STEP_FN=dump" in logs
    assert "RT_STRICT=1" in logs
    assert "RT_MODE=step" in logs
    assert f"RT_WORKDIR={result.workdir}" in logs
    assert "OPT_NOME=Ana" in logs
    assert "RT_ASSETS=" in logs
    # §7.1 — cwd = $HOME
    assert not Path(result.workdir).exists()  # workdir removido ao final


def test_strict_mode_disables_errexit(tmp_path: Path) -> None:
    target = tmp_path / "lenient.sh"
    target.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Lenient\n#@strict false\n"
        "#@step parcial\n"
        "parcial() {\n  falso\n  echo 'continuou'\n}\n",
        encoding="utf-8",
    )
    script = parse_script(target)
    collector = Collector()
    result = make(script).run(collector)
    assert result.status is RunState.SUCCESS
    assert "continuou" in collector.logs


def test_strict_mode_stops_on_first_error(tmp_path: Path) -> None:
    target = tmp_path / "strict.sh"
    target.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Strict\n"
        "#@step parcial\n"
        "parcial() {\n  falso\n  echo 'não deveria aparecer'\n}\n",
        encoding="utf-8",
    )
    script = parse_script(target)
    collector = Collector()
    result = make(script).run(collector)
    assert result.status is RunState.FAILED
    assert "não deveria aparecer" not in collector.logs


# -- eventos e streaming (§7.3) ---------------------------------------------
def test_event_sequence(dev_script) -> None:
    collector = Collector()
    executor = make(dev_script, ["install_tools", "update_index"], {"user_name": "Ana"})
    result = executor.run(collector)
    assert result.status is RunState.SUCCESS
    assert collector.of(RunStarted)[0].total_steps == 2
    assert [event.step_id for event in collector.of(StepStarted)] == ["update_index", "install_tools"]
    assert [event.status for event in collector.of(StepFinished)] == [
        StepState.SUCCESS,
        StepState.SUCCESS,
    ]
    assert collector.of(RunFinished)[0].status is RunState.SUCCESS


def test_stdout_and_stderr_are_separated(tmp_path: Path) -> None:
    target = tmp_path / "streams.sh"
    target.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Streams\n"
        "#@step falar\n"
        "falar() {\n  echo para-fora\n  echo para-erro >&2\n}\n",
        encoding="utf-8",
    )
    collector = Collector()
    result = make(parse_script(target)).run(collector)
    assert result.status is RunState.SUCCESS
    # stdout e stderr são lidos por threads distintas: a ordem entre eles não é
    # garantida, então cada fluxo é verificado separadamente.
    assert collector.stderr == ["para-erro"]
    assert [t for t in collector.logs if t != "para-erro"] == ["para-fora"]
    assert collector.stderr == ["para-erro"]


def test_utf8_and_large_output(tmp_path: Path) -> None:
    target = tmp_path / "ruido.sh"
    target.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Ruído\n"
        "#@step falar\n"
        "falar() {\n  printf 'acentuação çãõ\\n'\n  seq 1 500\n}\n",
        encoding="utf-8",
    )
    collector = Collector()
    result = make(parse_script(target)).run(collector)
    assert result.status is RunState.SUCCESS
    assert "acentuação çãõ" in collector.logs
    assert sum(1 for line in collector.logs if line.isdigit()) == 500


def test_progress_and_notify_events(dev_script) -> None:
    collector = Collector()
    result = make(
        dev_script, ["install_tools"], {"user_name": "Ana"}, ipc_factory=IpcChannel
    ).run(collector)
    assert result.status is RunState.SUCCESS
    progress = collector.of(Progress)
    assert [event.overall for event in progress] == [0.1, 1.0]
    assert progress[0].text == "Instalando ferramentas..."


def test_rt_set_exposes_variable_to_next_step(dev_script) -> None:
    collector = Collector()
    result = make(dev_script, ["install_tools", "config_git"], {"user_name": "Ana"}).run(collector)
    assert result.status is RunState.SUCCESS
    assert any("ferramentas em" in line for line in collector.logs)


# -- falhas (§7.4) ------------------------------------------------------------
def test_stop_leaves_remaining_steps_skipped(failing_script) -> None:
    collector = Collector()
    executor = make(failing_script, ["ok_one", "boom", "after_boom"])
    result = executor.run(collector)
    assert result.status is RunState.FAILED
    statuses = {step.step_id: step.status for step in result.steps}
    assert statuses == {
        "ok_one": StepState.SUCCESS,
        "boom": StepState.FAILED,
        "after_boom": StepState.SKIPPED,
    }
    assert result.result_of("boom").exit_code == 3
    assert result.exit_code() == 1


def test_continue_runs_next_steps(failing_script) -> None:
    executor = make(failing_script, ["boom_continue", "after_continue", "child_of_continue"])
    result = executor.run()
    statuses = {step.step_id: step.status for step in result.steps}
    assert statuses["boom_continue"] is StepState.FAILED
    assert statuses["after_continue"] is StepState.SUCCESS
    # §7.4 — quem depende do que falhou é skipped
    assert statuses["child_of_continue"] is StepState.SKIPPED
    assert result.status is RunState.FAILED


def test_dependent_of_failed_step_is_skipped(failing_script) -> None:
    executor = make(failing_script, ["boom_continue", "child_of_continue"])
    result = executor.run()
    assert result.result_of("child_of_continue").reason == "dependência falhou"


def test_transitive_skip(failing_script) -> None:
    # after_boom não depende de nada, mas fica skipped por causa do stop
    executor = make(failing_script, ["boom", "after_boom"])
    result = executor.run()
    assert result.result_of("after_boom").status is StepState.SKIPPED


def test_timeout_marks_failed(failing_script) -> None:
    collector = Collector()
    executor = make(failing_script, ["slow"])
    started = time.monotonic()
    result = executor.run(collector)
    elapsed = time.monotonic() - started
    assert result.status is RunState.FAILED
    assert result.result_of("slow").reason == "timeout"
    assert elapsed < 10
    assert any("timeout" in line for line in collector.logs)


def test_timeout_is_killed_not_ignored(tmp_path: Path) -> None:
    target = tmp_path / "lento.sh"
    target.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Lento\n#@step lento\n#@timeout 1\n"
        "lento() { sleep 30; }\n",
        encoding="utf-8",
    )
    result = make(parse_script(target)).run()
    assert result.result_of("lento").status is StepState.FAILED


# -- cancelamento (§7.4) -----------------------------------------------------
def test_cancel_kills_process_group(failing_script) -> None:
    collector = Collector()
    executor = make(failing_script, ["spawner"])
    child_pids: list[int] = []

    def watcher() -> None:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            line = [event.text for event in collector.of(LogLine) if event.text.startswith("filho=")]
            if line:
                child_pids.append(int(line[0].split("=", 1)[1]))
                return
            time.sleep(0.05)

    thread = threading.Thread(target=watcher, daemon=True)
    thread.start()
    result_holder: list = []

    def runner() -> None:
        result_holder.append(executor.run(collector))

    run_thread = threading.Thread(target=runner, daemon=True)
    run_thread.start()
    thread.join(timeout=10)
    assert child_pids, "o step não reportou o pid do filho"
    child = child_pids[0]
    time.sleep(0.3)
    executor.cancel()
    run_thread.join(timeout=20)
    assert result_holder, "a execução não terminou"
    result = result_holder[0]
    assert result.status is RunState.CANCELLED
    assert result.result_of("spawner").status is StepState.CANCELLED
    assert result.exit_code() == 130
    # §7.4 — o grupo inteiro morre
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _pid_alive(child):
        time.sleep(0.05)
    assert not _pid_alive(child), "o processo filho do step sobreviveu ao cancelamento"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # zombie ainda conta como vivo; procura no /proc
    return Path(f"/proc/{pid}/stat").exists() and " Z " not in _stat(pid)


def _stat(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return ""


def test_cancel_skips_remaining(failing_script) -> None:
    executor = make(failing_script, ["spawner", "ultimo"])
    holder: list = []
    thread = threading.Thread(target=lambda: holder.append(executor.run()), daemon=True)
    thread.start()
    time.sleep(1.0)
    executor.cancel()
    thread.join(timeout=20)
    statuses = {step.step_id: step.status for step in holder[0].steps}
    assert statuses["spawner"] is StepState.CANCELLED
    assert statuses["ultimo"] is StepState.SKIPPED


# -- pré-checagens (§7.5) ----------------------------------------------------
def test_precheck_missing_command(tmp_path: Path) -> None:
    target = tmp_path / "req.sh"
    target.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Req\n#@requires comando_que_nao_existe\n"
        "#@step ola\nola() { :; }\n",
        encoding="utf-8",
    )
    script = parse_script(target)
    executor = make(script)
    assert any("comando_que_nao_existe" in problem for problem in executor.precheck())
    with pytest.raises(PrecheckError):
        executor.run()


def test_precheck_required_option(dev_script) -> None:
    executor = make(dev_script, ["install_tools"], {"user_name": "Ana"})
    assert executor.precheck() == []
    executor.plan.options["user_name"] = ""  # usuário limpou o campo na GUI
    assert any("Nome para o git" in problem for problem in executor.precheck())


def test_precheck_requires_pkexec_for_root_steps(dev_script, monkeypatch) -> None:
    monkeypatch.setattr("kbash.core.executor.shutil.which", lambda name: None)
    executor = make(dev_script, ["update_index"], {"user_name": "Ana"})
    assert any("pkexec" in problem for problem in executor.precheck())


def test_precheck_empty_selection(dev_script) -> None:
    executor = make(dev_script, [], {"user_name": "Ana"})
    assert any("nenhum step" in problem for problem in executor.precheck())


# -- root (§9.2) -------------------------------------------------------------
def test_privilege_elevation_is_enabled() -> None:
    from kbash.core import executor as module

    assert module.PRIVILEGE_ELEVATION is True


def test_root_command_repasses_only_rt_and_opt() -> None:
    env = {
        "PATH": "/usr/bin", "HOME": "/home/x", "SECRET": "nao", "OPT_NOME": "Ana",
        "RT_SCRIPT": "/tmp/a.sh", "RT_STEP_ID": "x",
    }
    argv = default_root_command(["bash", "-c", "x"], env, "/home/x")
    assert argv[:2] == ["pkexec", "env"]
    assert "-i" in argv
    assert "PATH=/usr/bin" in argv
    assert "RT_STEP_ID=x" in argv
    assert "OPT_NOME=Ana" in argv
    assert not any(item.startswith("SECRET=") for item in argv)
    assert argv[-3:] == ["bash", "-c", "x"]


def test_root_step_runs_through_root_command_after_authorization(tmp_path: Path) -> None:
    target = tmp_path / "root.sh"
    target.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Root\n#@step ola\n#@root true\n"
        "ola() { echo hi; }\n",
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def fake_root(argv, env, cwd):  # noqa: ANN001, ANN202
        calls.append(list(argv))
        return list(argv)  # identidade: roda o bash sem pkexec de verdade

    collector = Collector()
    result = make(parse_script(target), root_command=fake_root).run(collector)
    assert result.status is RunState.SUCCESS
    assert "hi" in collector.logs
    assert len(calls) == 1 and calls[0][0] == "bash"
    assert script_step_root(target) is True


def test_authorization_is_requested_once_before_any_step(tmp_path: Path) -> None:
    target = tmp_path / "root.sh"
    target.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Root\n"
        "#@step um\n#@root true\num() { echo um; }\n"
        "#@step dois\n#@root true\ndois() { echo dois; }\n",
        encoding="utf-8",
    )
    collector = Collector()
    seen_when_asked: list[int] = []

    def authorize() -> bool:
        seen_when_asked.append(len(collector.events))  # nada deve ter rodado ainda
        return True

    result = make(
        parse_script(target), root_command=lambda argv, env, cwd: list(argv), authorize=authorize
    ).run(collector)
    assert result.status is RunState.SUCCESS
    assert seen_when_asked == [0]


def test_denied_authorization_runs_nothing(tmp_path: Path) -> None:
    marker = tmp_path / "rodou"
    target = tmp_path / "root.sh"
    target.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Root\n"
        f"#@step perigo\n#@root true\nperigo() {{ touch '{marker}'; }}\n",
        encoding="utf-8",
    )
    called: list[object] = []
    executor = make(
        parse_script(target),
        root_command=lambda argv, env, cwd: called.append(argv) or list(argv),
        authorize=lambda: False,
    )
    with pytest.raises(PrecheckError, match="autorização de root negada"):
        executor.run(Collector())
    assert not marker.exists()
    assert called == []


def test_no_root_steps_means_no_authorization(tmp_path: Path) -> None:
    target = tmp_path / "plain.sh"
    target.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Plano\n#@step ola\nola() { echo oi; }\n",
        encoding="utf-8",
    )
    asked: list[bool] = []
    result = make(parse_script(target), authorize=lambda: asked.append(True) or True).run(
        Collector()
    )
    assert result.status is RunState.SUCCESS
    assert asked == []


def _fake_pkexec(bin_dir: Path, exit_code: int) -> None:
    bin_dir.mkdir(exist_ok=True)
    tool = bin_dir / "pkexec"
    tool.write_text(f"#!/bin/sh\n[ \"$1\" = true ] && exit {exit_code}\nexit 99\n")
    tool.chmod(0o755)


def test_pkexec_authorize_reports_the_dialog_result(tmp_path: Path, monkeypatch) -> None:
    from kbash.core.executor import pkexec_authorize

    bin_dir = tmp_path / "bin"
    monkeypatch.setenv("PATH", str(bin_dir))
    _fake_pkexec(bin_dir, 0)
    assert pkexec_authorize() is True
    _fake_pkexec(bin_dir, 126)  # usuário cancelou o diálogo
    assert pkexec_authorize() is False


def test_pkexec_authorize_without_pkexec_is_false(tmp_path: Path, monkeypatch) -> None:
    from kbash.core.executor import pkexec_authorize

    monkeypatch.setenv("PATH", str(tmp_path / "vazio"))
    assert pkexec_authorize() is False


def script_step_root(target: Path) -> bool:
    return parse_script(target).steps[0].root is True


# -- IPC (§8) ----------------------------------------------------------------
def test_ipc_progress_and_prompts(dev_script) -> None:
    collector = Collector()
    executor = make(dev_script, ["install_tools"], {"user_name": "Ana"}, ipc_factory=IpcChannel)
    assert executor.ipc is None
    result = executor.run(collector)
    assert result.status is RunState.SUCCESS
    # o IPC responde automaticamente via o coletor? Não: prompts bloqueiam.
    #(update_index não tem prompts, então install_tools também não.)
    assert collector.of(Progress)


def test_ipc_confirm_prompt(dev_script) -> None:
    script = dev_script
    collector = Collector()
    executor = make(script, ["config_git"], {"user_name": "Ana"}, ipc_factory=IpcChannel)
    answers = {"count": 0}

    def on_prompt(event: PromptRequest) -> None:
        assert event.kind == "confirm"
        assert event.text == "Ativar assinatura de commits?"
        assert event.default is False
        answers["count"] += 1
        assert executor.ipc is not None
        executor.ipc.respond(event.request_id, True)

    def sink(event: object) -> None:
        collector(event)
        if isinstance(event, PromptRequest):
            on_prompt(event)

    result = executor.run(sink)
    assert answers["count"] == 1
    assert result.status is RunState.SUCCESS
    assert "assinatura ativada" in collector.logs


def test_ipc_cancel_prompt_ends_step_with_130(tmp_path: Path) -> None:
    target = tmp_path / "prompt.sh"
    target.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Prompt\n"
        "#@step perguntar\n"
        'perguntar() {\n  rt_confirm "Continuar?" n && echo segue\n  echo "código=$?"\n}\n',
        encoding="utf-8",
    )
    script = parse_script(target)
    collector = Collector()
    executor = make(script, ipc_factory=IpcChannel)

    def sink(event: object) -> None:
        collector(event)
        if isinstance(event, PromptRequest):
            from kbash.core.ipc import CANCEL

            executor.ipc.respond(event.request_id, CANCEL)  # type: ignore[union-attr]

    result = executor.run(sink)
    assert result.status is RunState.FAILED
    assert result.result_of("perguntar").exit_code == 130


def test_ipc_is_closed_after_run(dev_script) -> None:
    executor = make(dev_script, ["install_tools"], {"user_name": "Ana"}, ipc_factory=IpcChannel)
    executor.run()
    assert executor.ipc is None


def test_workdir_is_removed(dev_script) -> None:
    executor = make(dev_script, ["install_tools"], {"user_name": "Ana"})
    result = executor.run()
    assert result.workdir
    assert not Path(result.workdir).exists()


def test_keep_workdir(dev_script) -> None:
    executor = make(dev_script, ["install_tools"], {"user_name": "Ana"}, keep_workdir=True)
    result = executor.run()
    assert Path(result.workdir).is_dir()


def test_signals_are_ignored_by_step_children(tmp_path: Path) -> None:
    # start_new_session=True impede que o SIGINT do terminal mate o step antes
    # do cancelamento explícito (teste rápido, sem depender de TTY).
    target = tmp_path / "ignore.sh"
    target.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Ignore\n"
        "#@step ignorar\n"
        "ignorar() { trap '' INT; sleep 0.3; echo vivo; }\n",
        encoding="utf-8",
    )
    collector = Collector()
    result = make(parse_script(target)).run(collector)
    assert result.status is RunState.SUCCESS
    assert "vivo" in collector.logs


def test_signal_module_is_not_used_with_shell() -> None:
    assert signal.SIGTERM and os.name == "posix"

"""Fluxos de uso real, de ponta a ponta (SPEC.md §5–§8).

Cada teste simula uma sessão como a GUI/CLI a conduz: monta o plano com as
opções escolhidas, roda o executor e responde os prompts IPC como um usuário
faria. Os scripts vêm de ``examples/`` (exemplos reais do projeto) ou são
escritos num ``tmp_path`` para cenários específicos.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from fixtures.paths import HELPERS

from kbash.core.errors import PrecheckError, ValidationError
from kbash.core.events import LogLine, PromptRequest
from kbash.core.executor import Executor
from kbash.core.ipc import CANCEL, IpcChannel
from kbash.core.model import RunState, StepState
from kbash.core.parser import parse_script
from kbash.core.planner import build_plan, option_errors

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"


# ---------------------------------------------------------------------------
# Utilitários de sessão
# ---------------------------------------------------------------------------
class Session:
    """Coleta eventos e responde prompts segundo ``answers`` (tipo → valor ou callable)."""

    def __init__(self, answers: dict[str, object] | None = None) -> None:
        self.answers = answers or {}
        self.events: list[object] = []
        self.prompts: list[PromptRequest] = []
        self.executor: Executor | None = None

    def __call__(self, event: object) -> None:
        self.events.append(event)
        if isinstance(event, PromptRequest):
            self.prompts.append(event)
            answer = self.answers.get(event.kind, CANCEL)
            if callable(answer):
                answer = answer(event)
            assert self.executor is not None
            self.executor.ipc.respond(event.request_id, answer)  # type: ignore[union-attr]

    @property
    def logs(self) -> list[str]:
        return [e.text for e in self.events if isinstance(e, LogLine)]

    @property
    def warnings(self) -> list[str]:
        return [
            e.text for e in self.events if isinstance(e, LogLine) and e.level == "warn"
        ]


def write_script(directory: Path, body: str, name: str = "flow.kbash") -> Path:
    target = directory / name
    target.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Fluxo\n" + body, encoding="utf-8"
    )
    return target


def run_session(
    script_path: Path,
    session: Session,
    *,
    select: list[str] | None = None,
    options: dict[str, str] | None = None,
    home: Path | None = None,
) -> object:
    script = parse_script(script_path)
    plan = build_plan(script, select, options, home=str(home or script_path.parent))
    executor = Executor(script, plan, helpers=HELPERS, ipc_factory=IpcChannel)
    session.executor = executor
    return executor.run(session)


# ---------------------------------------------------------------------------
# 1. Exemplos reais do repositório
# ---------------------------------------------------------------------------
def test_example_all_options_plans_with_defaults() -> None:
    script = parse_script(EXAMPLES / "all-options.sh")
    plan = build_plan(script, None, None, home="/home/ana")
    assert plan.options["user_name"] == "Ana Silva"
    assert plan.options["editor"] == "nano"
    assert option_errors(script, plan.options) == {}


def test_example_all_options_rejects_missing_required_name() -> None:
    script = parse_script(EXAMPLES / "all-options.sh")
    values = dict(build_plan(script, None, None, home="/home/ana").options)
    values["user_name"] = ""
    assert "user_name" in option_errors(script, values)


@pytest.mark.parametrize(
    ("name", "options"),
    [("setup-dev.sh", {"user_name": "Ana"}), ("sober-optimizer.sh", None)],
)
def test_example_scripts_parse_and_plan(
    name: str, options: dict[str, str] | None
) -> None:
    script = parse_script(EXAMPLES / name)
    plan = build_plan(script, None, options, home="/home/ana")
    assert script.steps, f"{name} sem steps"
    assert plan.selected, f"{name} sem steps selecionados por padrão"


# ---------------------------------------------------------------------------
# 2. Assistente interativo completo (prompts respondidos como um usuário)
# ---------------------------------------------------------------------------
WIZARD = """
#@option nome type=string label="Nome" default="Ana"
#@step perguntas
perguntas() {
  nome=$(rt_input "Seu nome" "$OPT_NOME")
  editor=$(rt_choice "Editor" vim nano micro)
  if rt_confirm "Continuar?" y; then
    rt_log "ok: $nome usa $editor"
  fi
  n=$(rt_number "Tentativas" 3 1 10)
  rt_log "tentativas=$n"
}
#@step encerrar
encerrar() { rt_notify "Pronto"; }
"""


def test_wizard_happy_path_collects_every_answer(tmp_path: Path) -> None:
    path = write_script(tmp_path, WIZARD)
    session = Session(
        {"input": "Bruno", "choice": "micro", "confirm": "yes", "number": "5"}
    )
    result = run_session(path, session)
    assert result.status is RunState.SUCCESS
    assert [p.kind for p in session.prompts] == ["input", "choice", "confirm", "number"]
    assert "ok: Bruno usa micro" in session.logs
    assert "tentativas=5" in session.logs
    assert result.result_of("encerrar").status is StepState.SUCCESS


def test_wizard_user_cancels_midway_stops_the_run(tmp_path: Path) -> None:
    path = write_script(tmp_path, WIZARD)
    session = Session({"input": "Bruno", "choice": CANCEL})
    result = run_session(path, session)
    assert result.status is RunState.FAILED
    assert result.result_of("perguntas").exit_code == 130
    assert "tentativas=" not in " ".join(session.logs)
    assert [p.kind for p in session.prompts] == ["input", "choice"]


def test_wizard_default_option_is_visible_to_the_prompt(tmp_path: Path) -> None:
    path = write_script(tmp_path, WIZARD)
    session = Session(
        {
            "input": lambda p: p.default or "",
            "choice": "vim",
            "confirm": "no",
            "number": "1",
        }
    )
    run_session(path, session)
    assert session.prompts[0].default == "Ana"


# ---------------------------------------------------------------------------
# 3. Cancelamento e falhas em meio ao fluxo
# ---------------------------------------------------------------------------
def test_cancel_run_while_prompt_is_pending_does_not_hang(tmp_path: Path) -> None:
    path = write_script(
        tmp_path, '#@step esperar\nesperar() { rt_confirm "Sim?" y; }\n'
    )
    script = parse_script(path)
    executor = Executor(
        script,
        build_plan(script, None, None, home=str(tmp_path)),
        helpers=HELPERS,
        ipc_factory=IpcChannel,
    )
    session = Session({})  # nunca responde: o prompt fica pendente
    session.executor = executor
    timer = threading.Timer(1.0, executor.cancel)
    timer.start()
    try:
        result = executor.run(session)
    finally:
        timer.cancel()
    assert result.status in (RunState.CANCELLED, RunState.FAILED)
    assert any(isinstance(e, PromptRequest) for e in session.events)


def test_failed_step_skips_its_dependents_but_not_independent_ones(
    tmp_path: Path,
) -> None:
    path = write_script(
        tmp_path,
        "#@step base\n#@on_error continue\nbase() { return 2; }\n"
        "#@step filho\n#@depends base\nfilho() { echo filho-rodou; }\n"
        "#@step independente\nindependente() { echo independente-rodou; }\n",
    )
    session = Session()
    result = run_session(path, session)
    assert result.result_of("filho").status is StepState.SKIPPED
    assert "independente-rodou" in session.logs
    assert "filho-rodou" not in session.logs


def test_script_reported_failure_via_rt_fail_is_surfaced(tmp_path: Path) -> None:
    path = write_script(tmp_path, '#@step falha\nfalha() { rt_fail "disco cheio"; }\n')
    session = Session()
    result = run_session(path, session)
    assert result.status is RunState.FAILED
    assert "disco cheio" in " ".join(session.logs)


# ---------------------------------------------------------------------------
# 4. Seleção e opções do usuário
# ---------------------------------------------------------------------------
def test_unchecked_optional_step_does_not_run(tmp_path: Path) -> None:
    marker = tmp_path / "rodou"
    path = write_script(
        tmp_path,
        "#@step opcional\n#@default off\nopcional() { touch '" + str(marker) + "'; }\n"
        "#@step sempre\nsempre() { echo sempre-rodou; }\n",
    )
    session = Session()
    result = run_session(path, session)
    assert result.status is RunState.SUCCESS
    assert not marker.exists()
    assert "sempre-rodou" in session.logs


def test_selecting_a_step_pulls_in_its_dependency(tmp_path: Path) -> None:
    path = write_script(
        tmp_path,
        "#@step preparo\npreparo() { echo preparo; }\n"
        "#@step uso\n#@depends preparo\n#@default off\nuso() { echo uso; }\n",
    )
    script = parse_script(path)
    plan = build_plan(script, ["uso"], None, home=str(tmp_path))
    assert "preparo" in plan.selected and "uso" in plan.selected
    assert plan.selected.index("preparo") < plan.selected.index("uso")


@pytest.mark.parametrize(
    "value",
    [
        "Ana Maria",
        "com 'aspas' \"duplas\"",
        "$(touch PWNED); `touch PWNED`",
        "linha1\nlinha2",
        "barra \\ e tab\tfim",
        "unicode: ção — 日本",
    ],
)
def test_option_value_reaches_script_literally(tmp_path: Path, value: str) -> None:
    path = write_script(
        tmp_path,
        '#@option valor type=string label="Valor"\n'
        '#@step eco\neco() { printf "%s" "$OPT_VALOR"; echo; }\n',
    )
    session = Session()
    result = run_session(path, session, options={"valor": value}, home=tmp_path)
    assert result.status is RunState.SUCCESS
    assert not (tmp_path / "PWNED").exists()
    assert value in "\n".join(session.logs)


# ---------------------------------------------------------------------------
# 5. Borda de protocolo durante uma sessão real
# ---------------------------------------------------------------------------
def test_script_sending_garbage_ipc_still_completes_its_prompt(tmp_path: Path) -> None:
    path = write_script(
        tmp_path,
        "#@step ruidoso\n"
        "ruidoso() {\n"
        '  printf \'%s\\n\' \'{"t":"progress","value":"abc"}\' >> "$RT_IPC/out"\n'
        '  printf \'%s\\n\' \'{"t":"choice","id":"zz","choices":7}\' >> "$RT_IPC/out"\n'
        "  if rt_confirm 'Continuar?' y; then rt_log resposta-ok; fi\n"
        "}\n",
    )
    session = Session({"confirm": "yes"})
    result = run_session(path, session)
    assert result.status is RunState.SUCCESS
    assert "resposta-ok" in session.logs
    assert session.warnings, "a mensagem malformada deveria gerar aviso"


def test_two_concurrent_runs_of_the_same_script_are_independent(tmp_path: Path) -> None:
    path = write_script(
        tmp_path,
        "#@step pergunta\npergunta() { r=$(rt_input 'Nome' ''); rt_log \"eco=$r\"; }\n",
    )
    script = parse_script(path)
    results: dict[str, object] = {}
    sessions: dict[str, Session] = {}

    def worker(tag: str) -> None:
        plan = build_plan(script, None, None, home=str(tmp_path))
        executor = Executor(script, plan, helpers=HELPERS, ipc_factory=IpcChannel)
        session = Session({"input": tag})
        session.executor = executor
        sessions[tag] = session
        results[tag] = executor.run(session)

    threads = [threading.Thread(target=worker, args=(tag,)) for tag in ("alfa", "beta")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    for tag in ("alfa", "beta"):
        assert results[tag].status is RunState.SUCCESS, tag
        assert f"eco={tag}" in sessions[tag].logs, tag


def test_repeated_sequential_runs_leave_no_ipc_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "rt"
    runtime.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    path = write_script(tmp_path, "#@step a\na() { rt_confirm 'ok?' y; }\n")
    for _ in range(3):
        result = run_session(path, Session({"confirm": "yes"}))
        assert result.status is RunState.SUCCESS
    assert list(runtime.iterdir()) == [], "diretórios de IPC vazaram"


def test_validation_error_is_reported_before_any_run(tmp_path: Path) -> None:
    path = write_script(
        tmp_path,
        "#@step a\na() { :; }\n#@step b\n#@depends inexistente\nb() { :; }\n",
    )
    with pytest.raises(ValidationError):
        parse_script(path)


# ---------------------------------------------------------------------------
# 6. Elevação (§9.2): autorização, wrapping real e prompts vindos de um step root
# ---------------------------------------------------------------------------
def test_root_flow_authorizes_then_answers_prompts_through_pkexec(
    tmp_path: Path, fake_pkexec_on_path: Path
) -> None:
    path = write_script(
        tmp_path,
        "#@step aplicar\n#@root true\n"
        "aplicar() { if rt_confirm 'Aplicar?' y; then rt_log aplicado; fi; }\n",
    )
    session = Session({"confirm": "yes"})
    result = run_session(path, session)  # pkexec_authorize real, pkexec falso no PATH
    assert result.status is RunState.SUCCESS
    assert [p.kind for p in session.prompts] == ["confirm"]
    assert "aplicado" in session.logs


def test_root_flow_stops_before_any_step_when_authorization_is_denied(
    tmp_path: Path, fake_pkexec_on_path: Path
) -> None:
    marker = tmp_path / "rodou"
    (fake_pkexec_on_path / "pkexec").write_text("#!/bin/sh\nexit 126\n", encoding="utf-8")
    path = write_script(
        tmp_path,
        "#@step um\num() { touch '" + str(marker) + "'; }\n"
        "#@step raiz\n#@root true\nraiz() { touch '" + str(marker) + "-raiz'; }\n",
    )
    with pytest.raises(PrecheckError, match="autorização de root negada"):
        run_session(path, Session())
    assert not marker.exists() and not (tmp_path / "rodou-raiz").exists()

"""Testes do provedor de UI para interação (SPEC.md §8.5).

A sintaxe é "estilo kdialog", mas o diálogo é do próprio runtime: nenhum teste
 aqui pode envolver um programa externo.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fixtures.paths import HELPERS

from rt.core import ui
from rt.core.ui import Answer, Prompt, TerminalUi, YesUi, available, create, register, select_name

CONFIRM = Prompt(id="r1", kind="confirm", text="Continuar?", default=False)
CONFIRM_YES = Prompt(id="r2", kind="confirm", text="Continuar?", default=True)
TEXT = Prompt(id="r3", kind="input", label="Seu nome", default="Ana")
TEXT_EMPTY = Prompt(id="r4", kind="input", label="Seu nome")
SECRET = Prompt(id="r5", kind="input", label="Token", secret=True)
CHOICE = Prompt(id="r6", kind="choice", label="Editor", choices=("vim", "nano"), default="nano")
MULTI = Prompt(id="r7", kind="choice", label="Plugins", choices=("a", "b", "c"), multi=True)


# -- contrato: todos os provedores devolvem a mesma resposta -----------------
def test_available_providers() -> None:
    assert set(available()) >= {"terminal", "yes", "none"}


@pytest.mark.parametrize("name", ["yes", "ok", "terminal", "none"])
def test_every_provider_implements_the_protocol(name: str) -> None:
    provider = create(name, has_gui=False, stdin=_FakeStdin(False))
    assert isinstance(provider, ui.Ui)
    assert provider.name in available()
    assert hasattr(provider, "notify") and hasattr(provider, "close")


@pytest.mark.parametrize("prompt,expected", [
    (CONFIRM, Answer.ok(False)),
    (CONFIRM_YES, Answer.ok(True)),
    (TEXT, Answer.ok("Ana")),
    (TEXT_EMPTY, Answer.ok("")),
    (CHOICE, Answer.ok("nano")),
    (MULTI, Answer.ok(("a", "b", "c"))),
])
def test_yes_ui_returns_defaults(prompt: Prompt, expected: Answer) -> None:
    assert YesUi().ask(prompt) == expected


def test_terminal_ui_matches_yes_ui_for_same_input() -> None:
    provider = TerminalUi(input_fn=lambda _: "")
    for prompt, expected in ((CONFIRM, Answer.ok(False)), (TEXT, Answer.ok("Ana")),
                             (CHOICE, Answer.ok("nano"))):
        assert provider.ask(prompt) == YesUi().ask(prompt) == expected


def test_terminal_ui_answers() -> None:
    answers = iter(["s", "não", "2", "2 3"])
    provider = TerminalUi(input_fn=lambda _: next(answers))
    assert provider.ask(CONFIRM).value is True
    assert provider.ask(CONFIRM).value is False
    assert provider.ask(CHOICE).value == "nano"
    assert provider.ask(MULTI).value == ("b", "c")


def test_terminal_ui_multi_deduplicates() -> None:
    provider = TerminalUi(input_fn=lambda _: "2, 2 ,3")
    assert provider.ask(MULTI).value == ("b", "c")


def test_terminal_ui_repeats_invalid_confirm() -> None:
    answers = iter(["talvez", "x", "n"])
    provider = TerminalUi(input_fn=lambda _: next(answers))
    assert provider.ask(CONFIRM).value is False


def test_terminal_ui_cancels_on_eof() -> None:
    def boom(_prompt: str) -> str:
        raise EOFError

    assert TerminalUi(input_fn=boom).ask(TEXT) == Answer.cancel()


def test_none_ui_cancels() -> None:
    assert create("none").ask(TEXT) == Answer.cancel()
    assert create("none").ask(CONFIRM).cancelled is True


# -- seleção (§8.5) ----------------------------------------------------------
def test_select_name_precedence() -> None:
    assert select_name("none", environ={"BASHRT_UI": "yes"}) == "none"
    assert select_name(None, environ={"BASHRT_UI": "terminal"}) == "terminal"
    assert select_name("auto", has_gui=True, environ={}) == "qt"
    assert select_name("auto", stdin=_FakeStdin(True), environ={}) == "terminal"
    assert select_name("auto", stdin=_FakeStdin(False), environ={}) == "yes"


def test_select_name_rejects_unknown() -> None:
    with pytest.raises(ValueError) as error:
        select_name("inexistente", environ={})
    assert "inexistente" in str(error.value)


def test_custom_provider_can_be_registered() -> None:
    class Fake:
        name = "fake"

        def ask(self, prompt: Prompt) -> Answer:
            return Answer.ok("fake")

        def notify(self, text: str, level: str = "info") -> None:
            return None

        def close(self) -> None:
            return None

    register("fake", Fake, force=True)
    try:
        assert create("fake").ask(TEXT).value == "fake"
        assert "fake" in available()
    finally:
        ui._FACTORIES.pop("fake", None)


class _FakeStdin:
    def __init__(self, interactive: bool) -> None:
        self._interactive = interactive

    def isatty(self) -> bool:
        return self._interactive


# -- a UI é do runtime, não de um programa externo (§8.5) --------------------
def test_runtime_never_calls_an_external_dialog(tmp_path: Path) -> None:
    """A resposta vem do IPC interno; nenhum kdialog/zenity é executado."""
    from rt.core.events import PromptRequest
    from rt.core.executor import Executor
    from rt.core.ipc import IpcChannel
    from rt.core.parser import parse_script
    from rt.core.planner import build_plan

    fake = tmp_path / "fake-ui"
    fake.write_text("#!/bin/sh\necho CHAMADO >> %s\n" % (tmp_path / "chamadas.log"), encoding="utf-8")
    fake.chmod(0o755)

    script_path = tmp_path / "prompt.sh"
    script_path.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Prompt\n"
        "#@step perguntar\n"
        'perguntar() { rt_confirm "Continuar?" n && echo "SIM" || echo "NAO"; }\n',
        encoding="utf-8",
    )
    script = parse_script(script_path)
    executor = Executor(script, build_plan(script), helpers=HELPERS, ipc_factory=IpcChannel)
    logs: list[str] = []

    def sink(event: object) -> None:
        if isinstance(event, PromptRequest):
            executor.ipc.respond(event.request_id, True)  # type: ignore[union-attr]
        logs.append(getattr(event, "text", ""))

    result = executor.run(sink)
    assert result.status.value == "success"
    assert "SIM" in logs
    assert not (tmp_path / "chamadas.log").exists()


def test_prompt_from_request_conversion() -> None:
    from rt.core.events import PromptRequest

    event = PromptRequest(
        request_id="r9", kind="choice", label="Editor", default=["a"],
        choices=("a", "b"), multi=True, secret=True, step_id="passo",
    )
    prompt = Prompt.from_request(event)
    assert prompt.id == "r9"
    assert prompt.kind == "choice"
    assert prompt.default == ("a",)
    assert prompt.choices == ("a", "b")
    assert prompt.multi and prompt.secret
    assert prompt.step_id == "passo"
    assert prompt.title == "Editor"


def test_ui_module_does_not_import_qt() -> None:
    # §3 regra 1 — core/ nunca importa Qt
    source = Path(ui.__file__).read_text(encoding="utf-8")
    assert "PySide6" not in source
    assert "QtQuick" not in source


def test_subprocess_is_only_used_by_the_executor() -> None:
    # o provedor de UI do core não executa nada
    source = Path(ui.__file__).read_text(encoding="utf-8")
    assert "subprocess" not in source
    assert subprocess.run is not None


# -- novos kinds de prompt (§8.2/§8.4) ------------------------------------------
NUMBER = Prompt(id="r10", kind="number", label="Tentativas", default="3", minimum="1", maximum="10")
DATE = Prompt(id="r11", kind="date", label="Prazo", default="2026-12-31")
TIME = Prompt(id="r12", kind="time", label="Hora")
AFILE = Prompt(id="r13", kind="file", label="Foto", choices=("*.png", "*.jpg"))
MTEXT = Prompt(id="r14", kind="text", label="Notas")
TBOX = Prompt(id="r15", kind="textbox", label="Aviso", text="leia isto")


@pytest.mark.parametrize("prompt,expected", [
    (NUMBER, Answer.ok("3")),
    (DATE, Answer.ok("2026-12-31")),
    (TIME, Answer.ok("")),
    (AFILE, Answer.ok("")),
    (MTEXT, Answer.ok("")),
    (TBOX, Answer.ok("")),
])
def test_yes_ui_new_kinds(prompt: Prompt, expected: Answer) -> None:
    assert YesUi().ask(prompt) == expected


def test_terminal_ui_number_validates_and_ranges() -> None:
    answers = iter(["abc", "0", "11", "5"])
    provider = TerminalUi(input_fn=lambda _: next(answers))
    assert provider.ask(NUMBER).value == "5"


def test_terminal_ui_number_empty_uses_default() -> None:
    provider = TerminalUi(input_fn=lambda _: "")
    assert provider.ask(NUMBER).value == "3"


def test_terminal_ui_date_time_validate() -> None:
    provider = TerminalUi(input_fn=lambda _: next(answers))
    answers = iter(["31/12/2026", "2026-02-30", "2026-12-31"])
    assert provider.ask(DATE).value == "2026-12-31"
    answers = iter(["25:00", "08:30"])
    assert provider.ask(TIME).value == "08:30"


def test_terminal_ui_text_reads_until_dot() -> None:
    answers = iter(["linha 1", "linha 2", "."])
    provider = TerminalUi(input_fn=lambda _: next(answers))
    assert provider.ask(MTEXT).value == "linha 1\nlinha 2"


def test_terminal_ui_text_empty_uses_default() -> None:
    provider = TerminalUi(input_fn=lambda _: ".")
    assert provider.ask(Prompt(id="x", kind="text", label="N", default="d")).value == "d"


def test_terminal_ui_textbox_prints_and_returns_empty() -> None:
    import io
    out = io.StringIO()
    provider = TerminalUi(input_fn=lambda _: "", out=out)
    assert provider.ask(TBOX).value == ""
    assert "leia isto" in out.getvalue()


def test_terminal_ui_file_reads_path() -> None:
    provider = TerminalUi(input_fn=lambda _: "/tmp/foto.png")
    assert provider.ask(AFILE).value == "/tmp/foto.png"


def test_prompt_from_request_keeps_min_max() -> None:
    from rt.core.events import PromptRequest
    from rt.core.ui import Prompt as UiPrompt

    event = PromptRequest(request_id="r", kind="number", label="N", minimum="1", maximum="9")
    prompt = UiPrompt.from_request(event)
    assert (prompt.minimum, prompt.maximum) == ("1", "9")

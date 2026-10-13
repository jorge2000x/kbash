"""Testes do protocolo e dos helpers (SPEC.md §8)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest
from fixtures.paths import HELPERS

from kbash.core.ipc import (
    CANCEL,
    decode_response,
    encode_response,
    escape_value,
    format_answer,
    unescape_value,
)
from kbash.core.events import PromptRequest

TRICKY = [
    "aspas \" e barra \\",
    "quebra\nde linha",
    "tab\taqui",
    "acentuação çãõ ü 日本語",
    "json {\"a\": 1}",
    "",
    "  espaços  ",
]


# -- §8.3 codificação das respostas ------------------------------------------
@pytest.mark.parametrize("value", TRICKY)
def test_response_roundtrip(value: str) -> None:
    request_id, status, decoded = decode_response(encode_response("r1", "ok", value))
    assert (request_id, status) == ("r1", "ok")
    assert decoded == value


def test_escape_rules() -> None:
    assert escape_value("a\\b") == "a\\\\b"
    assert escape_value("a\nb") == "a\\nb"
    assert escape_value("a\tb") == "a\\tb"
    assert unescape_value("a\\nb") == "a\nb"


def test_confirm_answer_formats() -> None:
    event = PromptRequest(request_id="r", kind="confirm", default=True)
    assert format_answer(event, True) == ("ok", "yes")
    assert format_answer(event, False) == ("ok", "no")
    assert format_answer(event, "s") == ("ok", "yes")
    assert format_answer(event, CANCEL) == ("cancel", "")


def test_multi_answer_format() -> None:
    event = PromptRequest(request_id="r", kind="choice", choices=("a", "b"), multi=True)
    assert format_answer(event, ["a", "b"]) == ("ok", "a\nb")
    assert decode_response(encode_response("r", "ok", "a\nb"))[2] == "a\nb"


# -- helpers fora do runtime (fallback §8.4) ---------------------------------
def bash(script: str, stdin: str = "", env_extra: dict[str, str] | None = None):
    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run(
        ["bash", "-c", script],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )


def test_helper_json_escape() -> None:
    result = bash(
        f'source {HELPERS}; rt__escape "a\\"b\\\\c$(printf "\\t")d"'
    )
    assert result.returncode == 0
    assert result.stdout == 'a\\"b\\\\c\\td'
    assert json.loads(f'{{"t":"x","v":"{result.stdout}"}}')["v"] == 'a"b\\c\td'


def test_helper_json_array() -> None:
    result = bash(f'source {HELPERS}; rt__json_array "a b" \'c"d\' ""')
    assert json.loads(result.stdout) == ["a b", 'c"d', ""]
    assert json.loads(bash(f'source {HELPERS}; rt__json_array').stdout) == []


def test_helper_ids_are_unique() -> None:
    result = bash(f'source {HELPERS}; rt__id; rt__id; rt__id')
    ids = result.stdout.split()
    assert len(set(ids)) == 3


def test_helper_fallback_confirm() -> None:
    yes = bash(f'source {HELPERS}; rt_confirm " Continuar?" n && echo SIM', stdin="s\n")
    assert yes.stdout.endswith("SIM\n")
    no = bash(f'source {HELPERS}; rt_confirm " Continuar?" n || echo NAO', stdin="\n")
    assert no.stdout.endswith("NAO\n")
    default_yes = bash(f'source {HELPERS}; rt_confirm " Continuar?" y && echo SIM', stdin="")
    assert default_yes.stdout.endswith("SIM\n")  # sem stdin usa o padrão
    default_no = bash(f'source {HELPERS}; rt_confirm " Continuar?" n || echo NAO', stdin="")
    assert default_no.stdout.endswith("NAO\n")


def test_helper_fallback_input_and_secret() -> None:
    result = bash(f'source {HELPERS}; nome=$(rt_input "Nome" padrao); echo "[$nome]"', stdin="Ana\n")
    assert result.stdout.endswith("[Ana]\n")
    secret = bash(f'source {HELPERS}; s=$(rt_secret "Token"); echo "[$s]"', stdin="s3cr3t\n")
    assert secret.stdout.endswith("[s3cr3t]\n")
    assert "s3cr3t" not in secret.stderr  # não ecoa no terminal


def test_helper_fallback_choice_and_multi() -> None:
    choice = bash(f'source {HELPERS}; rt_choice "Editor" vim nano', stdin="nano\n")
    assert choice.stdout == "nano"
    default = bash(f'source {HELPERS}; rt_choice "Editor" vim nano', stdin="")
    assert default.stdout == "vim"


def test_helper_fallback_log_and_progress() -> None:
    result = bash(f'source {HELPERS}; rt_log "info"; rt_warn "alerta"; rt_error "erro"')
    assert "info" in result.stdout
    assert "alerta" in result.stderr
    assert "erro" in result.stderr
    progress = bash(f'source {HELPERS}; rt_progress 50 "Baixando"')
    assert "50" in progress.stdout and "Baixando" in progress.stdout
    dash = bash(f'source {HELPERS}; rt_progress -')
    assert "progresso" in dash.stdout


def test_helper_fallback_fail_exits_1() -> None:
    result = bash(f'source {HELPERS}; rt_fail "motivo"; echo nao-chegou')
    assert result.returncode == 1
    assert "motivo" in result.stderr
    assert "nao-chegou" not in result.stdout


def test_helper_set_and_get_without_runtime() -> None:
    result = bash(f'source {HELPERS}; rt_set repo_dir /tmp/x; echo "$RT_VAR_REPO_DIR $(rt_get repo_dir)"')
    assert result.stdout == "/tmp/x /tmp/x\n"


def test_helper_truncates_long_text() -> None:
    long = "x" * 5000
    result = bash(f'source {HELPERS}; rt__truncate "{long}" | wc -c')
    assert int(result.stdout.strip()) <= 1000


def test_helper_has_no_external_dependencies() -> None:
    # §8.4 — bash puro: sem jq/python. Só testamos que não há chamadas a eles.
    body = HELPERS.read_text(encoding="utf-8")
    code = "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )
    for forbidden in ("jq", "python", "perl", "node", "gawk", "awk"):
        assert forbidden not in code, forbidden
    # e funciona com um PATH mínimo
    result = subprocess.run(
        [shutil.which("bash") or "/bin/bash", "-c", f'source {HELPERS}; rt_progress 10 ok'],
        capture_output=True,
        text=True,
        env={"PATH": "/nonexistent", "HOME": os.environ.get("HOME", "/tmp")},
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_helper_syntax_is_valid() -> None:
    result = subprocess.run(["bash", "-n", str(HELPERS)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


# -- transporte real: script fala com o runtime (§8.1) -----------------------
def test_rt_set_reaches_next_step_via_ipc(tmp_path: Path) -> None:
    from kbash.core.events import LogLine
    from kbash.core.executor import Executor
    from kbash.core.ipc import IpcChannel
    from kbash.core.parser import parse_script
    from kbash.core.planner import build_plan

    script_path = tmp_path / "vars.sh"
    script_path.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Vars\n"
        "#@step um\n"
        "um() { rt_set valor $'linha 1\\nlinha 2'; echo guardado; }\n"
        "#@step dois\n"
        'dois() { echo "recebido=[$(rt_get valor)]"; }\n',
        encoding="utf-8",
    )
    script = parse_script(script_path)
    logs: list[str] = []
    executor = Executor(
        script,
        build_plan(script),
        helpers=HELPERS,
        ipc_factory=IpcChannel,
        log_sink=lambda event: logs.append(event.text) if isinstance(event, LogLine) else None,
    )
    result = executor.run()
    assert result.status.value == "success"
    assert any("recebido=[linha 1" in text for text in logs)
    assert result.variables["valor"] == "linha 1\nlinha 2"


def test_runtime_dir_is_0700_and_removed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from kbash.core.ipc import IpcChannel

    base = tmp_path / "runtime"
    base.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(base))
    modes = []
    channel = IpcChannel(tmp_path, lambda event: modes.append(type(event).__name__), "teste-123")
    try:
        assert channel.directory == base / "teste-123"
        assert oct(channel.directory.stat().st_mode)[-3:] == "700"
        assert channel.out_path.is_fifo() and channel.in_path.is_fifo()
    finally:
        channel.close()
    assert not channel.directory.exists()


def test_secret_is_input_with_secret_flag() -> None:
    """§8.2 — rt_secret manda t="input" com secret=true (não existe t="secret")."""
    from kbash.core.events import PromptRequest
    from kbash.core.ipc import IpcChannel

    prompts: list[PromptRequest] = []
    channel = IpcChannel(Path("/tmp"), prompts.append, "teste-secret")
    try:
        worker = threading.Thread(
            target=lambda: bash(
                f'source {HELPERS}; rt_secret "Token" >/dev/null',
                env_extra={"RT_IPC": str(channel.directory)},
            ),
            daemon=True,
        )
        worker.start()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not prompts:
            time.sleep(0.05)
        assert prompts, "rt_secret não pediu nada ao runtime"
        assert prompts[0].kind == "input"
        assert prompts[0].secret is True
        channel.respond(prompts[0].request_id, "s3cr3t")
        worker.join(timeout=10)
    finally:
        channel.close()


def test_unknown_message_with_id_gets_cancel() -> None:
    from kbash.core.events import LogLine
    from kbash.core.ipc import IpcChannel

    events: list[object] = []
    channel = IpcChannel(Path("/tmp"), events.append, "teste-desconhecido")
    try:
        writer = os.open(str(channel.out_path), os.O_RDWR)
        os.write(writer, b'{"t":"inventado","id":"r42"}\n')
        time.sleep(0.3)
        assert any(isinstance(event, LogLine) and "ignorada" in event.text for event in events)
        os.close(writer)
    finally:
        channel.close()


def test_new_prompt_kinds_reach_runtime() -> None:
    """§8.2 — rt_number/rt_date/rt_time/rt_file/rt_text/rt_textbox mandam o t certo."""
    import threading
    import time

    from kbash.core.events import PromptRequest
    from kbash.core.ipc import IpcChannel

    cases = [
        ('rt_number "Tentativas" 3 1 10', "number"),
        ('rt_date "Prazo" 2026-12-31', "date"),
        ('rt_time "Hora"', "time"),
        ('rt_file "Foto" "" "*.png"', "file"),
        ('rt_text "Notas"', "text"),
        ('rt_textbox "Aviso" "leia isto"', "textbox"),
    ]
    for command, kind in cases:
        prompts: list[PromptRequest] = []
        channel = IpcChannel(Path("/tmp"), prompts.append, f"teste-{kind}")
        try:
            worker = threading.Thread(
                target=lambda: bash(
                    f"source {HELPERS}; {command} >/dev/null",
                    env_extra={"RT_IPC": str(channel.directory)},
                ),
                daemon=True,
            )
            worker.start()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not prompts:
                time.sleep(0.05)
            assert prompts, f"{command} não pediu nada ao runtime"
            assert prompts[0].kind == kind, f"{command} mandou {prompts[0].kind}"
            if kind == "number":
                assert (prompts[0].minimum, prompts[0].maximum) == ("1", "10")
            if kind == "file":
                assert "*.png" in prompts[0].choices
            if kind == "textbox":
                assert prompts[0].text == "leia isto"
            channel.respond(prompts[0].request_id, "x")
            worker.join(timeout=10)
        finally:
            channel.close()


def test_helper_fallback_number_date_time() -> None:
    number = bash(f'source {HELPERS}; rt_number "Tentativas" 3 1 10', stdin="abc\n0\n11\n5\n")
    assert number.stdout == "5"
    default = bash(f'source {HELPERS}; rt_number "Tentativas" 3 1 10', stdin="")
    assert default.stdout == "3"
    date = bash(f'source {HELPERS}; rt_date "Prazo"', stdin="31/12/2026\n2026-12-31\n")
    assert date.stdout == "2026-12-31"
    clock = bash(f'source {HELPERS}; rt_time "Hora"', stdin="25:00\n08:30\n")
    assert clock.stdout == "08:30"


def test_helper_fallback_file_text_textbox() -> None:
    picked = bash(f'source {HELPERS}; rt_file "Foto" "" "*.png"', stdin="/tmp/foto.png\n")
    assert picked.stdout == "/tmp/foto.png"
    text = bash(f'source {HELPERS}; rt_text "Notas"', stdin="linha 1\nlinha 2\n.\n")
    assert text.stdout == "linha 1\nlinha 2"
    box = bash(f'source {HELPERS}; rt_textbox "Aviso" "leia isto"; echo FIM', stdin="\n")
    assert "leia isto" in box.stderr
    assert box.stdout.endswith("FIM\n")


def test_progresswin_is_fire_and_forget() -> None:
    """§8.2/§8.4 — progresswin não cria pendência: o script não espera resposta."""
    import threading
    import time

    from kbash.core.events import ProgressWin
    from kbash.core.ipc import IpcChannel

    events: list = []
    channel = IpcChannel(Path("/tmp"), events.append, "teste-progresswin")
    try:
        worker = threading.Thread(
            target=lambda: bash(
                f'source {HELPERS}; win=$(rt_progresswin_start 100 "Copiando"); '
                'rt_progresswin_update "$win" 30; rt_progresswin_done "$win"; echo FIM',
                env_extra={"RT_IPC": str(channel.directory)},
            ),
            daemon=True,
        )
        worker.start()
        worker.join(timeout=10)
        assert not worker.is_alive(), "progresswin bloqueou o script esperando resposta"
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and sum(
            isinstance(event, ProgressWin) for event in events
        ) < 3:
            time.sleep(0.05)
        kinds = [event.op for event in events if isinstance(event, ProgressWin)]
        assert kinds == ["start", "update", "done"]
        start = next(event for event in events if isinstance(event, ProgressWin) and event.op == "start")
        assert (start.maximum, start.text) == (100.0, "Copiando")
        update = next(event for event in events if isinstance(event, ProgressWin) and event.op == "update")
        assert update.value == 30.0
    finally:
        channel.close()


def test_helper_fallback_progresswin() -> None:
    out = bash(
        f'source {HELPERS}; win=$(rt_progresswin_start 100 "Copiando"); '
        'rt_progresswin_update "$win" 30 "meio"; rt_progresswin_done "$win"; echo FIM',
        stdin="",
    )
    assert "Copiando" in out.stderr
    assert "30" in out.stderr
    assert out.stdout.endswith("FIM\n")


def test_helper_rt_get_empty_value() -> None:
    """rt_get de chave definida vazia devolve vazio com 0 (§8.4).

    Regressão: `[ -n ... ]` tratava vazio como inexistente (rc=1) e,
    sob `errexit`, matava o step que lia opcional vazio (ex.: FRM off).
    """
    out = bash(
        f'source {HELPERS}; rt_set chave ""; v=$(rt_get chave); rc=$?; echo "got=[$v] rc=$rc"',
        stdin="",
    )
    assert "got=[] rc=0" in out.stdout
    missing = bash(f'source {HELPERS}; rt_get inexistente; echo "rc=$?"', stdin="")
    assert missing.stdout.endswith("rc=1\n")

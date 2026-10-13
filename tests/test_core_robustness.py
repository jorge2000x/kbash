"""Testes de robustez do core: entradas hostis e casos de borda.

Cobrem os achados da revisão (SPEC.md §4.6, §7.4, §8.1–§8.3): exportações do
``errors``, leitor IPC que não pode morrer, diretório IPC seguro e único,
codificação de respostas e o parser sob entradas inválidas.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from kbash.core import errors, ipc
from kbash.core.errors import KbashError, ValidationError
from kbash.core.events import LogLine
from kbash.core.ipc import IpcChannel, IpcError, decode_response, encode_response
from kbash.core.parser import parse_text


# ---------------------------------------------------------------------------
# Exportações públicas
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("module", [errors, ipc])
def test_every_name_in_all_exists(module) -> None:
    """Regressão: ``errors.__all__`` listava ``ParseResult``, que não existe."""
    missing = [name for name in module.__all__ if not hasattr(module, name)]
    assert missing == []


def test_star_import_of_errors_works() -> None:
    namespace: dict[str, object] = {}
    exec("from kbash.core.errors import *", namespace)  # noqa: S102 — teste de __all__
    assert "KbashError" in namespace and "ValidationError" in namespace


# ---------------------------------------------------------------------------
# Leitor IPC: mensagens malformadas não podem matar a thread
# ---------------------------------------------------------------------------
def _write_out(channel: IpcChannel, payload: bytes) -> None:
    fd = os.open(channel.out_path, os.O_RDWR)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)


@pytest.mark.parametrize(
    "message",
    [
        {"t": "progress", "value": "abc"},
        {"t": "progresswin", "op": "start", "value": "x", "max": "y"},
        {"t": "confirm", "id": "a1", "choices": 5},
        {"t": "set"},
        {"t": "log", "text": None, "level": ["x"]},
    ],
)
def test_reader_survives_malformed_message(tmp_path: Path, message: dict) -> None:
    events: list[object] = []
    channel = IpcChannel(tmp_path, events.append, "robust-" + os.urandom(3).hex())
    try:
        _write_out(channel, (json.dumps(message) + "\n").encode())
        time.sleep(0.2)
        _write_out(channel, b'{"t":"notify","text":"depois"}\n')
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not any(
            getattr(event, "text", "") == "depois" for event in events
        ):
            time.sleep(0.02)
        assert channel._reader.is_alive(), "a thread do leitor morreu"
        assert any(getattr(event, "text", "") == "depois" for event in events)
    finally:
        channel.close()


def test_malformed_prompt_gets_cancel_and_is_not_left_pending(tmp_path: Path) -> None:
    """Prompt com ``choices`` inválido: o script recebe ``cancel`` para o próprio id."""
    events: list[object] = []
    channel = IpcChannel(tmp_path, events.append, "prompt-" + os.urandom(3).hex())
    try:
        _write_out(channel, b'{"t":"choice","id":"r77","choices":5}\n')
        reply = b""
        deadline = time.monotonic() + 3
        reader = os.open(channel.in_path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            while time.monotonic() < deadline and b"\n" not in reply:
                try:
                    reply += os.read(reader, 256)
                except BlockingIOError:
                    time.sleep(0.02)
        finally:
            os.close(reader)
        assert decode_response(reply) == ("r77", "cancel", "")
        assert channel._pending == {}
    finally:
        channel.close()


def test_reader_logs_the_malformed_message(tmp_path: Path) -> None:
    events: list[object] = []
    channel = IpcChannel(tmp_path, events.append, "log-" + os.urandom(3).hex())
    try:
        _write_out(channel, b'{"t":"progress","value":"abc"}\n')
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not any(
            isinstance(event, LogLine) and "malformada" in event.text
            for event in events
        ):
            time.sleep(0.02)
        assert any(
            isinstance(event, LogLine) and "malformada" in event.text
            for event in events
        )
    finally:
        channel.close()


# ---------------------------------------------------------------------------
# Diretório IPC: único, exclusivo e nunca seguindo symlink
# ---------------------------------------------------------------------------
def test_symlink_planted_at_ipc_path_is_refused(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "rt"
    base.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir(mode=0o755)
    (base / "fixo").symlink_to(victim)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(base))
    with pytest.raises(IpcError):
        IpcChannel(tmp_path, lambda event: None, "fixo")
    assert oct(victim.stat().st_mode & 0o777) == "0o755", (
        "o alvo do symlink foi alterado"
    )


def test_second_channel_with_same_owner_does_not_steal_fifos(
    tmp_path: Path, monkeypatch
) -> None:
    """Regressão: duas execuções com o mesmo nome compartilhavam o diretório e,
    ao fechar a segunda, os FIFOs da primeira eram apagados."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "rt"))
    first = IpcChannel(tmp_path, lambda event: None, "mesmo")
    try:
        with pytest.raises(IpcError):
            IpcChannel(tmp_path, lambda event: None, "mesmo")
        assert first.out_path.is_fifo() and first.in_path.is_fifo()
    finally:
        first.close()


def test_auto_owner_names_are_unique(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "rt"))
    channels = [IpcChannel(tmp_path, lambda event: None) for _ in range(5)]
    try:
        directories = {channel.directory for channel in channels}
        assert len(directories) == 5
        assert all(oct(d.stat().st_mode)[-3:] == "700" for d in directories)
    finally:
        for channel in channels:
            channel.close()


# ---------------------------------------------------------------------------
# Codificação das respostas (§8.3)
# ---------------------------------------------------------------------------
def test_truncated_response_stays_one_well_formed_line() -> None:
    payload = encode_response("r1", "ok", "x" * 10_000)
    assert payload.count(b"\n") == 1 and payload.endswith(b"\n")
    rid, status, value = decode_response(payload)
    assert (rid, status) == ("r1", "ok")
    assert 0 < len(value) <= 4000


def test_response_with_separators_round_trips() -> None:
    value = 'linha 1\nlinha\t2 \\ "aspas" $(x)'
    assert decode_response(encode_response("r9", "ok", value)) == ("r9", "ok", value)


# ---------------------------------------------------------------------------
# Parser sob entradas hostis (§4.6): só pode levantar KbashError
# ---------------------------------------------------------------------------
HDR = "#!/usr/bin/env bash\n#@runtime 1\n#@name T\n"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "\x00\x00\x00",
        "#@runtime 1\n",
        "#@runtime 1\n#@name\n",
        "#@runtime 99\n#@name X\n",
        HDR + "#@step\nf() { :; }\n",
        HDR + "#@step a\n#@depends a\na() { :; }\n",
        HDR + "#@step a\n#@depends b\na() { :; }\n#@step b\n#@depends a\nb() { :; }\n",
        HDR + "#@option x type=choice\n",
        HDR + "#@option x type=number min=9 max=1 default=5\n",
        HDR + '#@option x type=string default="sem fechar\n',
        HDR + "#@step a\n#@timeout -5\na() { :; }\n",
        HDR + "#@step a\n#@timeout abc\na() { :; }\n",
        HDR + "#@step a\n#@timeout 0\na() { :; }\n",
        HDR + "#@step a\n#@depends ,,\na() { :; }\n",
        HDR + "#@step a\n#@depends\na() { :; }\n",
        "﻿" + HDR,
        HDR.replace("\n", "\r\n") + "#@step a\r\na() { :; }\r\n",
        HDR + "#@option 1bad type=string\n",
        HDR + "#@option " + "x" * 100_000 + " type=string\n",
        HDR + "".join(f"#@step s{i}\ns{i}() {{ :; }}\n" for i in range(2000)),
        HDR + "f() {" * 500 + "}" * 500 + "\n",
        HDR + "#@step a\na() { :; }\n" * 3,
    ],
)
def test_parser_raises_only_kbash_errors(text: str) -> None:
    try:
        parse_text(text)
    except KbashError:
        pass


def test_dependency_cycle_is_a_validation_error() -> None:
    text = (
        HDR + "#@step a\n#@depends b\na() { :; }\n#@step b\n#@depends a\nb() { :; }\n"
    )
    with pytest.raises(ValidationError):
        parse_text(text)

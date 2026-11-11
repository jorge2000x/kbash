"""Processo compartilhado (§7.1/§7.4): spawn em sessão nova, sinal ao grupo, encerramento com carência.

Executor (steps) e actions usavam cópias quase iguais disso; agora usam `core.proc`.
"""

from __future__ import annotations

import os
import signal
import time

from kbash.core import proc


def test_start_merges_stderr_into_stdout_when_asked() -> None:
    processo = proc.start(
        ["bash", "-c", "echo a; echo b >&2"], env=dict(os.environ), cwd="/", merge_stderr=True
    )
    saida, _ = processo.communicate(timeout=10)
    assert b"a" in saida and b"b" in saida


def test_start_keeps_stderr_separate_by_default() -> None:
    processo = proc.start(["bash", "-c", "echo a; echo b >&2"], env=dict(os.environ), cwd="/")
    saida, erro = processo.communicate(timeout=10)
    assert saida.strip() == b"a"
    assert erro.strip() == b"b"


def test_start_runs_in_a_new_session() -> None:
    processo = proc.start(["bash", "-c", "sleep 5"], env=dict(os.environ), cwd="/")
    try:
        assert os.getpgid(processo.pid) == processo.pid
    finally:
        proc.stop(processo, grace=2)


def test_stop_kills_the_whole_group() -> None:
    processo = proc.start(["bash", "-c", "sleep 30 & sleep 30"], env=dict(os.environ), cwd="/")
    time.sleep(0.2)
    inicio = time.monotonic()
    proc.stop(processo, grace=3)
    assert time.monotonic() - inicio < 6
    assert processo.poll() is not None


def test_signal_group_on_a_finished_process_does_not_raise() -> None:
    processo = proc.start(["bash", "-c", "true"], env=dict(os.environ), cwd="/")
    processo.wait(timeout=10)
    proc.signal_group(processo, signal.SIGTERM)  # não pode levantar


def test_signal_group_suppresses_system_errors(monkeypatch) -> None:
    def falha(*_args, **_kwargs):
        raise PermissionError("negado")

    class Processo:
        pid = 1

        def send_signal(self, _sig):
            raise OSError("também falha")

    monkeypatch.setattr(os, "killpg", falha)
    proc.signal_group(Processo(), 15)  # não pode levantar

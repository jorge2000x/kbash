"""Processo de step e de ação (§7.1/§7.4): spawn em sessão nova, sinal ao grupo, encerramento.

Usado pelo executor (steps) e por ``actions.run_action``. Argumentos sempre em
lista e sem shell (AGENTS.md). ``start_new_session`` deixa o processo líder do
próprio grupo, para que o sinal alcance também os filhos dele.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
from collections.abc import Mapping

#: §7.4 — segundos entre SIGTERM e SIGKILL, e entre SIGKILL e desistir.
GRACE_PERIOD = 5.0


def start(
    argv: list[str],
    *,
    env: Mapping[str, str],
    cwd: str,
    merge_stderr: bool = False,
    entrada: bytes | None = None,
) -> subprocess.Popen[bytes]:
    """Inicia ``argv`` numa sessão nova; saída e erro em pipes.

    Sem ``entrada`` o stdin fica fechado. Com ela, o stdin é um pipe que recebe esses
    bytes e fecha: é assim que segredos chegam a um comando root sem aparecer no argv.
    ``merge_stderr`` manda o erro para a mesma saída (uma ação não separa os dois).
    """
    process = subprocess.Popen(  # noqa: S603 - argv em lista, sem shell
        argv,
        env=dict(env),
        cwd=cwd,
        stdin=subprocess.DEVNULL if entrada is None else subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
        start_new_session=True,
    )
    if entrada is not None and process.stdin is not None:
        with contextlib.suppress(BrokenPipeError):  # o comando pode ter morrido antes de ler
            process.stdin.write(entrada)
            process.stdin.flush()
        with contextlib.suppress(BrokenPipeError):
            process.stdin.close()
        process.stdin = None  # fechado aqui: o Popen não pode tentar usá-lo de novo
    return process


def signal_group(process: subprocess.Popen[bytes], sig: int) -> None:
    """Envia ``sig`` ao grupo do processo; se o grupo não existe, ao processo. Nunca levanta."""
    with contextlib.suppress(OSError):
        os.killpg(process.pid, sig)
        return
    with contextlib.suppress(OSError, ValueError):
        process.send_signal(sig)


def stop(process: subprocess.Popen[bytes], grace: float = GRACE_PERIOD) -> int | None:
    """§7.4 — SIGTERM no grupo; se não sair em ``grace``, SIGKILL. Devolve o código, ou None."""
    signal_group(process, signal.SIGTERM)
    try:
        return process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        signal_group(process, signal.SIGKILL)
    try:
        return process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        return None

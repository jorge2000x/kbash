"""Prioridades da revisão de segurança do helper ``rt.sh``.

1. Canal IPC que é symlink é recusado: o helper não abre o alvo com ``>``, que
   truncaria um arquivo arbitrário, nem lê um alvo trocado por outro processo.
2. ``rt__id`` tem 128 bits de ``/dev/urandom``, não ``PID-RANDOM-contador``, que
   um processo do mesmo usuário consegue adivinhar.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from fixtures.paths import HELPERS


def bash(script: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=env, check=False, timeout=30
    )


# -- 1. symlink nos canais IPC -------------------------------------------------
# O ataque real: o canal é symlink para um FIFO que outro processo do mesmo usuário
# controla. ``-p`` segue o link e passa, então sem a checagem de ``-L`` o helper
# escreveria no FIFO alheio. Symlink para arquivo comum já cai em ``-p`` falso.
@pytest.mark.parametrize("canal", ["out", "in"])
def test_rt_recusa_canal_ipc_que_e_symlink_para_fifo_alheio(tmp_path: Path, canal: str) -> None:
    ipc = tmp_path / "ipc"
    ipc.mkdir(mode=0o700)
    alheio = tmp_path / "fifo-alheio"
    os.mkfifo(alheio, 0o600)
    outro = "in" if canal == "out" else "out"
    os.mkfifo(ipc / outro, 0o600)
    (ipc / canal).symlink_to(alheio)
    # descritores O_RDWR do próprio teste: leitor e escritor existem, então nenhuma
    # abertura bloqueia; o que o helper escrever no FIFO alheio fica visível aqui
    segura = os.open(ipc / outro, os.O_RDWR | os.O_NONBLOCK)
    espiao = os.open(alheio, os.O_RDWR | os.O_NONBLOCK)
    try:
        result = bash(f"source {HELPERS}; rt_log info oi", env_extra={"RT_IPC": str(ipc)})
        try:
            vazado = os.read(espiao, 4096)
        except BlockingIOError:
            vazado = b""
    finally:
        os.close(segura)
        os.close(espiao)
    # recusado: nada chega ao FIFO alheio e o helper cai no fallback, que imprime na tela
    assert vazado == b""
    assert "oi" in result.stdout


# -- 2. id de requisição aleatório ---------------------------------------------
def test_rt_id_tem_128_bits_aleatorios_e_nao_se_repete() -> None:
    result = bash(f"source {HELPERS}; rt__id; rt__id")
    ids = result.stdout.split()
    assert len(ids) == 2, result.stderr
    for id_ in ids:
        assert re.fullmatch(r"[0-9a-f]{32}-\d+", id_), id_
    assert ids[0] != ids[1]

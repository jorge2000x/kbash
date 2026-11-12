"""Helpers rt.sh: progresso em centésimos, senha sem eco no fallback, multi no fallback.

Os testes trocam rt__send e rt__ask_terminal depois do `source`, para ver o que
o helper enviaria e em que modo pediria a entrada, sem depender de terminal.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "src" / "kbash" / "helpers" / "rt.sh"
BASH = shutil.which("bash") or "/bin/bash"


def rodar(trecho: str, entrada: str = "") -> str:
    script = f"source {HELPERS}\nrt__send() {{ printf 'ENVIO %s\\n' \"$1\"; }}\n{trecho}"
    completed = subprocess.run(
        [BASH, "-c", script], input=entrada, capture_output=True, text=True, timeout=10, check=False,
    )
    return completed.stdout  # o menu do fallback vai para o stderr


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("0", "0.00"), ("1", "0.01"), ("5", "0.05"), ("9", "0.09"),
        ("10", "0.10"), ("50", "0.50"), ("100", "1.00"),
    ],
)
def test_rt_progress_envia_fracao_em_centesimos(valor: str, esperado: str) -> None:
    assert f'"value":{esperado}' in rodar(f'rt_progress {valor} "x"')


def test_rt_secret_pede_sem_eco_no_fallback_de_terminal() -> None:
    trecho = (
        "rt__ask_terminal() { printf 'MODO=%s\\n' \"$3\"; printf 'x'; }\n"
        "rt_secret 'senha'\n"
    )
    assert "MODO=secret" in rodar(trecho)


def test_rt_input_normal_no_fallback_nao_pede_sem_eco() -> None:
    trecho = (
        "rt__ask_terminal() { printf 'MODO=%s\\n' \"${3-normal}\"; printf 'x'; }\n"
        "rt_input 'nome'\n"
    )
    assert "MODO=normal" in rodar(trecho)


def test_rt_multi_no_fallback_aceita_varias_escolhas_por_numero() -> None:
    trecho = "rt__ask_terminal() { printf '1 3\\n'; }\nrt_multi 'x' a b c\n"
    assert rodar(trecho).splitlines() == ["a", "c"]


def test_rt_multi_no_fallback_aceita_nomes_separados_por_virgula() -> None:
    trecho = "rt__ask_terminal() { printf 'b,c\\n'; }\nrt_multi 'x' a b c\n"
    assert rodar(trecho).splitlines() == ["b", "c"]


def test_rt_choice_no_fallback_continua_escolha_unica() -> None:
    trecho = "rt__ask_terminal() { printf '2\\n'; }\nrt_choice 'x' a b c\n"
    assert rodar(trecho) == "b"

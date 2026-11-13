"""Ação em andamento pode ser encerrada de fora (fechar a janela).

Achado: a ação roda numa thread daemon e numa sessão própria; fechar a janela não a
encerrava. Agora run_action avisa o processo que iniciou (on_start), e quem fecha
encerra o grupo com proc.stop.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from kbash.core import proc
from kbash.core.actions import run_action
from kbash.core.executor import helpers_path
from kbash.core.parser import parse_script

HDR = "#!/bin/bash\n#@runtime 1\n#@name limpeza\n#@id limpeza\n"


def test_on_start_recebe_o_processo_e_stop_encerra_a_acao(tmp_path: Path) -> None:
    path = tmp_path / "lenta.kbash"
    path.write_text(HDR + "#@action lenta\n#@timeout 120\nlenta() { sleep 60; }\n", encoding="utf-8")
    script = parse_script(path)
    action = script.action("lenta")
    assert action is not None
    iniciados: list[object] = []
    resultado: list[object] = []

    def executar() -> None:
        resultado.append(
            run_action(
                script, action, {}, None,
                helpers=helpers_path(), workdir=str(tmp_path),
                on_start=iniciados.append,
            )
        )

    thread = threading.Thread(target=executar, daemon=True)
    thread.start()
    limite = time.monotonic() + 10
    while not iniciados and time.monotonic() < limite:
        time.sleep(0.02)
    assert iniciados, "on_start não foi chamado"

    inicio = time.monotonic()
    proc.stop(iniciados[0], grace=2)  # o que o fechamento da janela faz
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert time.monotonic() - inicio < 10
    assert iniciados[0].poll() is not None

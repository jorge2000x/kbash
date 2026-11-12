"""Segredos fora do argv do pkexec, entrada pelo stdin e respostas de rt_secret escondidas (§8.2, §9.2).

Não depende de pkexec: o comando root é injetado (``root_command``) e devolve o argv
inalterado, então o que se testa é o que o runtime *passa* para o comando root.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path
from typing import ClassVar

import subprocess

from fixtures.paths import HELPERS
from kbash.core import proc
from kbash.core.events import LogLine, PromptRequest
from kbash.core.executor import Executor
from kbash.core.ipc import IpcChannel
from kbash.core.parser import parse_script
from kbash.core.planner import build_plan
from kbash.core.redacao import MASCARA, redige

SEGREDO = "s3nh4-muito-secreta"


def bash(script: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=env, check=False, timeout=30
    )


# -- 1. proc.start entrega a entrada pelo stdin ------------------------------
def test_proc_start_entrega_entrada_pelo_stdin(tmp_path: Path) -> None:
    process = proc.start(["cat"], env=dict(os.environ), cwd=str(tmp_path), entrada=b"ola\n")
    saida, _ = process.communicate(timeout=10)
    assert saida == b"ola\n"


def test_proc_start_sem_entrada_continua_com_stdin_fechado(tmp_path: Path) -> None:
    process = proc.start(["cat"], env=dict(os.environ), cwd=str(tmp_path))
    saida, _ = process.communicate(timeout=10)
    assert saida == b""


# -- 2. resposta de rt_secret vira segredo ------------------------------------
def test_canal_registra_resposta_de_rt_secret(tmp_path: Path) -> None:
    prompts: list[PromptRequest] = []
    channel = IpcChannel(Path(tempfile.gettempdir()), prompts.append, "teste-segredo-registro")
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
        assert prompts and prompts[0].secret is True
        channel.respond(prompts[0].request_id, SEGREDO)
        worker.join(timeout=10)
        assert channel.segredos == [SEGREDO]
    finally:
        channel.close()


def test_executor_esconde_resposta_de_rt_secret_no_log(tmp_path: Path) -> None:
    path = tmp_path / "segredo.kbash"
    path.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name S\n#@step um\num() { :; }\n",
        encoding="utf-8",
    )
    script = parse_script(path)
    executor = Executor(script, build_plan(script), helpers=HELPERS)

    class Canal:
        directory = tmp_path
        variables: ClassVar[dict[str, str]] = {}
        step_id = ""

        segredos: ClassVar[list[str]] = [SEGREDO]

    executor._ipc = Canal()  # type: ignore[assignment] - canal mínimo, só o que o log consulta
    textos: list[str] = []
    executor.log_sink = lambda event: textos.append(event.text) if isinstance(event, LogLine) else None
    executor._log("um", "stdout", f"o token é {SEGREDO}")
    assert textos == [f"o token é {MASCARA}"]
    assert redige(SEGREDO, executor._segredos()) == MASCARA


# -- 3. senha fora do argv e do ambiente do comando root -----------------------
def _script_root(tmp_path: Path, saida: Path) -> Path:
    path = tmp_path / "root.kbash"
    path.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name R\n"
        '#@option senha type=password label="Senha" default=' + SEGREDO + "\n"
        "#@step um\n#@root true\n"
        f'um() {{ printf %s "$OPT_SENHA" > "{saida}"; }}\n',
        encoding="utf-8",
    )
    return path


def test_senha_nao_vai_para_o_argv_do_root_mas_o_script_recebe(tmp_path: Path) -> None:
    saida = tmp_path / "recebido.txt"
    script = parse_script(_script_root(tmp_path, saida))
    chamadas: list[tuple[list[str], dict[str, str]]] = []

    def comando_root(argv: list[str], env: dict[str, str], cwd: str) -> list[str]:
        chamadas.append((list(argv), dict(env)))
        return list(argv)  # sem pkexec: executa direto, mas o argv e o env já foram registrados

    executor = Executor(
        script,
        build_plan(script),
        helpers=HELPERS,
        root_command=comando_root,
        authorize=lambda: True,
    )
    # check=False: a pré-checagem exige pkexec instalado; o comando root aqui é injetado
    executor.run(check=False)

    assert chamadas, "o comando root deveria ter sido usado"
    argv, env = chamadas[0]
    assert SEGREDO not in " ".join(argv)
    assert SEGREDO not in env.values()
    assert "OPT_SENHA" not in env
    assert saida.read_text(encoding="utf-8") == SEGREDO  # o script ainda recebe o valor


def test_acao_root_nao_leva_senha_no_argv(tmp_path: Path) -> None:
    from kbash.core.actions import run_action

    saida = tmp_path / "acao.txt"
    path = tmp_path / "acao.kbash"
    path.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name A\n"
        '#@option senha type=password label="Senha" default=' + SEGREDO + "\n"
        "#@action mostra\n#@root true\n"
        f'mostra() {{ printf %s "$OPT_SENHA" > "{saida}"; }}\n',
        encoding="utf-8",
    )
    script = parse_script(path)
    action = script.action("mostra")
    assert action is not None
    chamadas: list[list[str]] = []

    def comando_root(argv: list[str], env: dict[str, str], cwd: str) -> list[str]:
        chamadas.append(list(argv))
        return list(argv)

    result = run_action(
        script,
        action,
        {"senha": SEGREDO},
        None,
        helpers=HELPERS,
        workdir=str(tmp_path),
        root_command=comando_root,
    )
    assert result.status == "ok"
    assert chamadas and SEGREDO not in " ".join(chamadas[0])
    assert saida.read_text(encoding="utf-8") == SEGREDO

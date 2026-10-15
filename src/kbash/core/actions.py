"""Ações (mini-scripts, SPEC.md §4.8 e §7.6), executadas fora do plano.

Uma ação roda como um step, mas sob demanda: sem canal IPC, com ``stdin``
em ``/dev/null``, com as ``OPT_*`` que a tela mostra no momento do clique e
com a saída devolvida inteira (últimas linhas) para a GUI. Nada daqui toca o
plano, ``RunResult`` ou o log persistente.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from collections import deque
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from pathlib import Path

from .executor import (
    GRACE_PERIOD,
    PRIVILEGE_ELEVATION,
    STEP_COMMAND,
    default_root_command,
)
from .model import Action, Script
from .planner import default_options, expand_value, option_visible

__all__ = ["OUTPUT_LINES", "ActionResult", "action_env", "run_action"]

#: §4.8 — só as últimas linhas da saída voltam para a tela.
OUTPUT_LINES = 200

RootCommand = Callable[[Sequence[str], dict[str, str], str], list[str]]


@dataclass
class ActionResult:
    """§4.8 — resultado de um clique em ação."""

    action_id: str
    #: ``ok`` (código 0) · ``failed`` (código ≠ 0) · ``timeout`` · ``error`` (não rodou).
    status: str
    exit_code: int | None = None
    output: str = ""
    duration: float = 0.0


def action_env(
    script: Script,
    values: dict[str, str],
    selected: Collection[str] | None,
    *,
    helpers: Path,
    assets: Path | None = None,
    workdir: str = "",
    home: str | None = None,
) -> dict[str, str]:
    """§7.6 — ``OPT_*`` a partir dos valores atuais da tela.

    Opção oculta (``needs_step`` fora da seleção, ``show_if`` falso) entra com o
    ``default``, como no plano. Valores ausentes também caem no ``default``.
    """
    defaults = default_options(script, home)
    env: dict[str, str] = {}
    for option in script.options:
        if not option.carries_value:
            continue
        if option_visible(script, values, option, selected):
            raw = values.get(option.id, defaults.get(option.id, ""))
            if option.type in ("path", "file"):  # mesma expansão do plano
                raw = expand_value(raw, home)
        else:
            raw = defaults.get(option.id, "")
        env[f"OPT_{option.id.upper()}"] = raw
    env.update(
        {
            "RT_SCRIPT": str(script.path),
            "RT_HELPERS": str(helpers),
            "RT_ASSETS": str(assets) if assets else "",
            "RT_IPC": "",  # §4.8: ação não é interativa
            "RT_WORKDIR": workdir,
            "RT_STRICT": "1" if script.strict else "0",
            "RT_MODE": "action",
        }
    )
    return env


def _cwd(env: dict[str, str], workdir: str) -> str:
    """§7.1 — ``$HOME``, com o mesmo fallback do executor."""
    home = env.get("HOME") or str(Path.home())
    if Path(home).is_dir():
        return home
    if workdir and Path(workdir).is_dir():
        return workdir
    return str(Path.cwd())


def _tail(text: str) -> str:
    return "\n".join(deque(text.splitlines(), maxlen=OUTPUT_LINES))


def run_action(
    script: Script,
    action: Action,
    values: dict[str, str],
    selected: Collection[str] | None,
    *,
    helpers: Path,
    assets: Path | None = None,
    workdir: str = "",
    root_command: RootCommand = default_root_command,
) -> ActionResult:
    """§4.8/§7.6 — roda a ação e espera (até ``action.timeout``).

    Bloqueante: a GUI chama numa thread. ``#@root true`` passa pelo pkexec
    (§9.2); a autorização é pedida antes, pela GUI.
    """
    started = time.monotonic()
    env = action_env(
        script,
        values,
        selected,
        helpers=helpers,
        assets=assets,
        workdir=workdir,
        home=os.environ.get("HOME"),
    )
    env.update(
        {
            "RT_STEP_ID": action.id,
            "RT_STEP_FN": action.function,
        }
    )
    cwd = _cwd(env, workdir)
    argv: list[str] = ["bash", "--noprofile", "--norc", "-c", STEP_COMMAND]
    if action.root and PRIVILEGE_ELEVATION:
        argv = root_command(argv, env, cwd)
    try:
        process = subprocess.Popen(  # argv em lista, sem shell
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except (OSError, ValueError) as error:
        return ActionResult(action.id, "error", None, f"não foi possível iniciar: {error}")

    status = "ok"
    try:
        raw, _ = process.communicate(timeout=action.timeout)
    except subprocess.TimeoutExpired:
        status = "timeout"
        _signal_group(process, signal.SIGTERM)
        try:
            raw, _ = process.communicate(timeout=GRACE_PERIOD)
        except subprocess.TimeoutExpired:
            _signal_group(process, signal.SIGKILL)
            raw, _ = process.communicate()
    code = process.returncode
    if status == "ok" and code != 0:
        status = "failed"
    return ActionResult(
        action_id=action.id,
        status=status,
        exit_code=code,
        output=_tail(raw.decode("utf-8", errors="replace")),
        duration=time.monotonic() - started,
    )


def _signal_group(process: subprocess.Popen[bytes], sig: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(process.pid, sig)

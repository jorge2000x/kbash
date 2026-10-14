"""Executor: roda cada step em um subprocesso ``bash`` (SPEC.md §7).

Invariantes (SPEC.md §3/§7/§14):
* subprocesso sem ``shell=True`` — argumentos sempre em lista;
* ``start_new_session=True`` para poder sinalizar o grupo inteiro (§7.1/§7.4);
* stdout/stderr lidos em streaming por threads, um :class:`LogLine` por linha;
* toda decisão de lógica fica aqui; a GUI só consome eventos (§3 regra 4).
"""

from __future__ import annotations

import os
import secrets
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol

from .errors import PrecheckError
from .events import (
    Event,
    EventSink,
    LogLine,
    RunFinished,
    RunStarted,
    StepFinished,
    StepStarted,
)
from .model import RunPlan, RunState, Script, Step, StepState
from .planner import build_plan, option_errors

__all__ = [
    "StepResult",
    "RunResult",
    "Executor",
    "IpcChannel",
    "precheck",
    "helpers_path",
    "default_root_command",
    "GRACE_PERIOD",
    "STEP_COMMAND",
    "PRIVILEGE_ELEVATION",
]

#: §7.4 — 5 s entre SIGTERM e SIGKILL.
GRACE_PERIOD = 5.0

#: §7.1 — comando de execução de um step.
STEP_COMMAND = (
    'set -o pipefail; [ "$RT_STRICT" = 1 ] && set -o errexit; '
    'source "$RT_HELPERS"; source "$RT_SCRIPT"; "$RT_STEP_FN"'
)

#: §9.2 — variáveis repassadas ao pkexec além de RT_* / OPT_*.
ROOT_PASSTHROUGH = (
    "PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TERM", "DISPLAY",
    "XAUTHORITY", "XDG_RUNTIME_DIR", "XDG_DATA_DIRS",
)

#: Elevação de privilégio (SPEC.md §9.2) **desligada por enquanto**: os steps
#: ``#@root true`` rodam como qualquer outro, e o usuário nunca vê um pedido de
#: senha. Com a elevação ligada, o pkexec mostra o diálogo do sistema (polkit) uma
#: vez, logo antes do primeiro step, depois que o usuário revisou o plano.
PRIVILEGE_ELEVATION = True


class IpcChannel(Protocol):
    """Transporte de interação (§8) visto pelo executor."""

    directory: Path

    def close(self) -> None: ...


def helpers_path() -> Path:
    """Caminho do ``rt.sh`` empacotado (§3, estrutura de pastas)."""
    return Path(__file__).resolve().parent.parent / "helpers" / "rt.sh"


#: §9.2 — tempo máximo para o usuário digitar a senha no diálogo do sistema.
AUTH_TIMEOUT = 300


def pkexec_authorize() -> bool:
    """§9.2 — pede autorização de root pelo diálogo do sistema (polkit), antes de começar.

    ``pkexec true`` sem ``--disable-internal-agent`` deixa o agente gráfico do
    desktop mostrar o diálogo. Devolve ``False`` se o pkexec não existir, se o
    usuário cancelar ou se a senha estiver errada.
    """
    try:
        done = subprocess.run(  # argv fixo, sem shell
            ["pkexec", "true"],
            stdin=subprocess.DEVNULL,
            timeout=AUTH_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def default_root_command(argv: Sequence[str], env: dict[str, str], cwd: str) -> list[str]:
    """§9.2 — ``pkexec env <vars> bash ...``, repassando só o necessário."""
    exported = [f"{key}={env[key]}" for key in ROOT_PASSTHROUGH if key in env]
    exported += [
        f"{key}={value}"
        for key, value in sorted(env.items())
        if key.startswith(("RT_", "OPT_"))
    ]
    return ["pkexec", "env", "-i", *exported, *argv]


@dataclass
class StepResult:
    """§5 — estado final de um step."""

    step_id: str
    status: StepState
    exit_code: int | None = None
    duration: float = 0.0
    reason: str = ""


@dataclass
class RunResult:
    status: RunState = RunState.PENDING
    steps: list[StepResult] = field(default_factory=list)
    duration: float = 0.0
    variables: dict[str, str] = field(default_factory=dict)
    workdir: str = ""

    def result_of(self, step_id: str) -> StepResult | None:
        for result in self.steps:
            if result.step_id == step_id:
                return result
        return None

    def exit_code(self) -> int:
        """§12 — 0 sucesso · 1 falha · 130 cancelado."""
        if self.status is RunState.CANCELLED:
            return 130
        return 0 if self.status is RunState.SUCCESS else 1


def precheck(
    script: Script,
    plan: RunPlan | None = None,
    *,
    options: dict[str, str] | None = None,
    steps: Iterable[Step] | None = None,
    check_root: bool = True,
) -> list[str]:
    """§7.5 — devolve a lista de falhas que impedem iniciar a execução."""
    problems: list[str] = []
    for command in script.requires:
        if shutil.which(command) is None:
            problems.append(f"comando obrigatório ausente no PATH: {command}")
    values = options if options is not None else (plan.options if plan else {})
    for option_id, message in option_errors(script, values).items():
        option = script.option(option_id)
        label = option.label if option else option_id
        problems.append(f"opção {label!r}: {message}")
    if steps is None:
        selected_ids = set(plan.selected) if plan else set()
        selected = [step for step in script.steps if step.id in selected_ids]
    else:
        selected = list(steps)
    if not selected:
        problems.append("nenhum step selecionado")
    if PRIVILEGE_ELEVATION and check_root and any(step.root for step in selected):
        if shutil.which("pkexec") is None:
            problems.append(
                "steps pedem privilégios de root (#@root true) mas o pkexec não está instalado"
            )
    return problems


class Executor:
    """Executa um :class:`RunPlan` emitindo eventos (§7.3)."""

    def __init__(
        self,
        script: Script,
        plan: RunPlan | None = None,
        *,
        helpers: Path | None = None,
        assets: Path | None = None,
        ipc_factory: Callable[[Path, EventSink, str], IpcChannel] | None = None,
        root_command: Callable[[Sequence[str], dict[str, str], str], list[str]] = default_root_command,
        log_sink: Callable[[LogLine], None] | None = None,
        keep_workdir: bool = False,
        strict: bool | None = None,
        authorize: Callable[[], bool] | None = None,
    ) -> None:
        self.script = script
        self.plan = plan or build_plan(script)
        self.helpers = Path(helpers) if helpers else helpers_path()
        self.assets = Path(assets) if assets else None
        self.ipc_factory = ipc_factory
        self.root_command = root_command
        self.log_sink = log_sink
        self.keep_workdir = keep_workdir
        self.strict = self.script.strict if strict is None else strict
        #: §9.2 — autorização de root, pedida uma vez antes do primeiro step.
        self.authorize = authorize or pkexec_authorize
        self.variables: dict[str, str] = {}
        self._emitter: EventSink = lambda event: None
        self._process: subprocess.Popen[bytes] | None = None
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._ipc: IpcChannel | None = None
        self._tempdir: TemporaryDirectory[str] | None = None
        self._kept_workdir: TemporaryDirectory[str] | None = None

    # -- API pública -----------------------------------------------------
    @property
    def ipc(self) -> IpcChannel | None:
        """Canal §8 aberto para a execução atual (``None`` sem ``ipc_factory``)."""
        return self._ipc

    @property
    def steps(self) -> list[Step]:
        by_id = {step.id: step for step in self.script.steps}
        return [by_id[step_id] for step_id in self.plan.selected if step_id in by_id]

    def precheck(self, *, check_root: bool = True) -> list[str]:
        return precheck(self.script, self.plan, check_root=check_root)

    def cancel(self) -> None:
        """§7.4 — SIGTERM no grupo; SIGKILL se não sair em ``GRACE_PERIOD``."""
        self._cancel.set()
        with self._lock:
            process = self._process
        if process is not None and process.poll() is None:
            self._signal_group(process, signal.SIGTERM)
        ipc = self._ipc
        if ipc is not None:
            ipc.close()

    def run(self, emit: EventSink | None = None, *, check: bool = True) -> RunResult:
        """Executa o plano inteiro. Uma instância = uma execução."""
        if emit is not None:
            self._emitter = emit
        if check:
            problems = self.precheck()
            if problems:
                raise PrecheckError("; ".join(problems))
        # §9.2 — o diálogo do sistema aparece aqui: depois da revisão do plano
        # (quem chama já mostrou a lista) e antes de qualquer step rodar.
        if PRIVILEGE_ELEVATION and any(step.root for step in self.steps):
            if not self.authorize():
                raise PrecheckError(
                    "autorização de root negada ou cancelada; nenhum step foi executado"
                )
        result = RunResult()
        started = time.monotonic()
        self._tempdir = TemporaryDirectory(prefix="kbash-")  # noqa: SIM115 - limpo no finally
        workdir = Path(self._tempdir.name)
        result.workdir = str(workdir)
        if self.ipc_factory is not None:
            # sufixo aleatório: uma execução nunca reutiliza o diretório de outra
            channel = self.ipc_factory(
                workdir, self._emit, f"{self.script.id}-{os.getpid()}-{secrets.token_hex(4)}"
            )
            self._ipc = channel
            # §7.2 — rt_set alimenta as variáveis dos steps seguintes.
            setattr(channel, "variables", self.variables)
        self._emit(
            RunStarted(self.script.id, self.script.name, len(self.plan.selected), str(workdir))
        )
        halt = False
        bad: set[str] = set()
        try:
            for index, step in enumerate(self.steps):
                if self._cancel.is_set():
                    break
                # §7.4 — quem depende (direta ou indiretamente) de um step que
                # falhou é skipped, mesmo com on_error=continue.
                if self._reaches(step, bad):
                    result.steps.append(
                        StepResult(step.id, StepState.SKIPPED, reason="dependência falhou")
                    )
                    self._emit(
                        StepFinished(step.id, StepState.SKIPPED, None, 0.0, "dependência falhou")
                    )
                    bad.add(step.id)
                    continue
                outcome = self._run_step(step, index)
                if self._ipc is not None:
                    # §7.2 — rt_set do step que acabou deve valer para o próximo
                    settle = getattr(self._ipc, "settle", None)
                    if callable(settle):
                        settle()
                result.steps.append(outcome)
                if outcome.status is StepState.FAILED:
                    bad.add(step.id)
                    if step.on_error == "stop":
                        halt = True
                        break
            if halt or self._cancel.is_set():
                self._skip_remaining(result)
        finally:
            if self._ipc is not None:
                self._ipc.close()
                self._ipc = None
            if self.keep_workdir:
                self._kept_workdir = self._tempdir  # impede a limpeza do GC
                self._tempdir = None
            elif self._tempdir is not None:
                self._tempdir.cleanup()
                self._tempdir = None
        result.status = self._final_status(result)
        result.variables = dict(self.variables)
        result.duration = time.monotonic() - started
        self._emit(RunFinished(result.status, result.duration))
        return result

    # -- execução de um step --------------------------------------------
    def _run_step(self, step: Step, index: int) -> StepResult:
        started = time.monotonic()
        env = self._build_env(step)
        argv, cwd = self._build_argv(step, env)
        if self._ipc is not None:
            setattr(self._ipc, "step_id", step.id)
        self._emit(StepStarted(step.id, index, len(self.plan.selected)))
        try:
            process = subprocess.Popen(  # noqa: S603 - argv em lista, sem shell
                argv,
                env=env,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as exc:
            self._log(step.id, "kbash", f"não foi possível iniciar o step: {exc}", "error")
            return self._finish(step, StepState.FAILED, None, started, str(exc))
        with self._lock:
            self._process = process
        readers = (
            threading.Thread(target=self._pump, args=(process.stdout, step.id, "stdout"), daemon=True),
            threading.Thread(target=self._pump, args=(process.stderr, step.id, "stderr"), daemon=True),
        )
        for reader in readers:
            reader.start()
        code, reason = self._wait(process, step)
        for reader in readers:
            reader.join(timeout=GRACE_PERIOD)
        with self._lock:
            self._process = None
        if self._cancel.is_set():
            status = StepState.CANCELLED
        elif reason or code not in (0, None):
            status = StepState.FAILED
        else:
            status = StepState.SUCCESS
        return self._finish(step, status, code, started, reason)

    def _finish(
        self, step: Step, status: StepState, code: int | None, started: float, reason: str
    ) -> StepResult:
        duration = time.monotonic() - started
        self._emit(StepFinished(step.id, status, code, duration, reason))
        return StepResult(step.id, status, code, duration, reason)

    def _wait(self, process: subprocess.Popen[bytes], step: Step) -> tuple[int | None, str]:
        """Espera o step terminar respeitando timeout (§7.4) e cancelamento."""
        deadline = time.monotonic() + step.timeout if step.timeout else None
        while True:
            try:
                return process.wait(timeout=0.05), ""
            except subprocess.TimeoutExpired:
                pass
            if self._cancel.is_set():
                return self._terminate(process), "cancelado"
            if deadline is not None and time.monotonic() >= deadline:
                self._log(step.id, "kbash", f"timeout de {step.timeout}s expirado", "error")
                return self._terminate(process), "timeout"

    def _terminate(self, process: subprocess.Popen[bytes]) -> int | None:
        """§7.4 — SIGTERM no grupo, SIGKILL depois de ``GRACE_PERIOD``."""
        self._signal_group(process, signal.SIGTERM)
        try:
            return process.wait(timeout=GRACE_PERIOD)
        except subprocess.TimeoutExpired:
            self._signal_group(process, signal.SIGKILL)
        try:
            return process.wait(timeout=GRACE_PERIOD)
        except subprocess.TimeoutExpired:
            return None

    def _signal_group(self, process: subprocess.Popen[bytes], sig: int) -> None:
        try:
            os.killpg(os.getpgid(process.pid), sig)
        except (ProcessLookupError, PermissionError, AttributeError):
            try:
                process.send_signal(sig)
            except (ProcessLookupError, ValueError):
                pass

    # -- ambiente e comando ---------------------------------------------
    def _build_env(self, step: Step) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            {
                "RT_SCRIPT": str(self.script.path),
                "RT_HELPERS": str(self.helpers),
                "RT_ASSETS": str(self.assets) if self.assets else "",
                "RT_IPC": str(self._ipc.directory) if self._ipc is not None else "",
                "RT_STEP_ID": step.id,
                "RT_STEP_FN": step.function,
                "RT_STRICT": "1" if self.strict else "0",
                "RT_MODE": "step",  # §4.5
                "RT_WORKDIR": str(self._tempdir.name) if self._tempdir else str(Path.cwd()),
            }
        )
        for option_id, value in self.plan.options.items():
            env[f"OPT_{option_id.upper()}"] = value
        for key, value in self.variables.items():
            env[f"RT_VAR_{key.upper()}"] = value
        return env

    def _step_cwd(self, env: dict[str, str]) -> str:
        """§7.1 — cwd do step: ``$HOME``.

        Só que um ``cwd`` inexistente faz ``Popen`` estourar ``FileNotFoundError``
        antes do bash existir, e o step morre com ``[Errno 2] ... $HOME`` — que
        não parece erro de diretório. Num AppImage isso aparece sempre que
        ``$HOME`` aponta pra algo que não está lá (home deletado, container sem
        home, wrapper que exporta ``HOME`` errado). Nesses casos cai para
        ``$RT_WORKDIR`` e, no último caso, para o diretório de trabalho do
        processo, para o step sempre ter onde nascer.
        """
        home = env.get("HOME") or str(Path.home())
        if Path(home).is_dir():
            return home
        workdir = env.get("RT_WORKDIR") or ""
        if workdir and Path(workdir).is_dir():
            return workdir
        return str(Path.cwd())

    def _build_argv(self, step: Step, env: dict[str, str]) -> tuple[list[str], str]:
        home = self._step_cwd(env)
        argv = ["bash", "--noprofile", "--norc", "-c", STEP_COMMAND]
        if step.root and PRIVILEGE_ELEVATION:  # §9.2 — desligado por enquanto
            argv = self.root_command(argv, env, home)
        return argv, home  # §7.1 — cwd = $HOME

    # -- leitura de streams ---------------------------------------------
    def _pump(self, stream: Any, step_id: str, name: str) -> None:
        if stream is None:
            return
        with stream:
            for raw in iter(stream.readline, b""):
                text = raw.decode("utf-8", errors="replace").rstrip("\n")
                self._log(step_id, name, text, "error" if name == "stderr" else "info")

    def _log(self, step_id: str | None, stream: str, text: str, level: str = "info") -> None:
        event = LogLine(step_id, stream, text, level)  # type: ignore[arg-type]
        if self.log_sink is not None:
            self.log_sink(event)
        self._emit(event)

    def _emit(self, event: Event) -> None:
        self._emitter(event)

    # -- estado da execução ----------------------------------------------
    def _skip_remaining(self, result: RunResult) -> None:
        """§7.4 — ``on_error=stop``/cancelamento deixam o resto como ``skipped``."""
        bad = {step.step_id for step in result.steps if step.status is StepState.FAILED}
        done = {step.step_id for step in result.steps}
        cancelled = self._cancel.is_set()
        for step in self.steps:
            if step.id in done:
                continue
            blocked = self._reaches(step, bad)
            if blocked:
                reason = "dependência falhou"
            elif cancelled:
                reason = "cancelado"
            else:
                reason = "execução interrompida"
            result.steps.append(StepResult(step.id, StepState.SKIPPED, reason=reason))
            self._emit(StepFinished(step.id, StepState.SKIPPED, None, 0.0, reason))
            if blocked:
                bad.add(step.id)  # propaga para quem depende deste step

    def _reaches(self, step: Step, bad: set[str]) -> bool:
        """``True`` se ``step`` (ou uma dependência sua) está em ``bad``."""
        stack: list[str] = [step.id]
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current != step.id and current in bad:
                return True
            if current in seen:
                continue
            seen.add(current)
            node = self.script.step(current)
            if node is not None:
                stack.extend(node.depends)
        return False

    def _final_status(self, result: RunResult) -> RunState:
        statuses = {step.status for step in result.steps}
        if self._cancel.is_set() or StepState.CANCELLED in statuses:
            return RunState.CANCELLED
        if StepState.FAILED in statuses:
            return RunState.FAILED
        return RunState.SUCCESS

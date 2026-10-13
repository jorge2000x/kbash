"""CLI do kbash (SPEC.md §12).

Códigos de saída: ``0`` sucesso · ``1`` falha de step · ``2`` erro de
parse/validação · ``130`` cancelado.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

from .core.errors import KbashError, ParseError, PrecheckError, ValidationError
from .core.events import (
    Event,
    LogLine,
    Notify,
    Progress,
    ProgressWin,
    PromptRequest,
    RunFinished,
    RunStarted,
    StepFinished,
    StepStarted,
)
from .core.executor import Executor, helpers_path
from .core.model import RunState, Script, StepState
from .core.parser import check_script, parse_script
from .core.planner import build_plan, value_options
from .core.ui import YesUi

EXIT_OK = 0
EXIT_STEP_FAILED = 1
EXIT_INVALID = 2
EXIT_CANCELLED = 130


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
def cmd_check(args: argparse.Namespace, out: TextIO) -> int:
    target = Path(args.script)
    if not target.is_file():
        print(f"{target}: error: arquivo não encontrado", file=out)
        return EXIT_INVALID
    script, diagnostics = check_script(target)
    for diagnostic in diagnostics:
        print(diagnostic, file=out)
    path = args.script
    if script is None:
        print(f"{path}: inválido ({len(diagnostics.errors)} erro(s))", file=out)
        return EXIT_INVALID
    print(
        f"{path}: ok — {len(script.steps)} step(s), {len(script.options)} opção(ões),"
        f" sha256 {script.sha256[:12]}…"
    )
    if diagnostics.warnings:
        print(f"{path}: {len(diagnostics.warnings)} aviso(s)")
    return EXIT_OK


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------
def cmd_plan(args: argparse.Namespace, out: TextIO) -> int:
    script = parse_script(Path(args.script))
    plan = build_plan(script, _split(args.select), _parse_opts(args.opt), home=str(Path.home()))
    print(f"{script.name} [{script.id}] v{script.version or '—'}", file=out)
    if script.description:
        print(f"  {script.description}", file=out)
    print("steps:", file=out)
    for index, step_id in enumerate(plan.selected, start=1):
        step = script.step(step_id)
        assert step is not None
        badges = []
        if step_id in plan.auto_added:
            badges.append("por dependência")
        if step.required:
            badges.append("obrigatório")
        if step.root:
            badges.append("requer root")
        if step.timeout:
            badges.append(f"timeout {step.timeout}s")
        if step.on_error == "continue":
            badges.append("on_error=continue")
        suffix = f"  [{', '.join(badges)}]" if badges else ""
        print(f"  {index}. {step.id} — {step.title}{suffix}", file=out)
        if step.description:
            print(f"       {step.description.splitlines()[0]}", file=out)
    if plan.options:
        print("opções:", file=out)
        for option in value_options(script):
            value = plan.options.get(option.id, "")
            shown = "•" if option.type == "password" else value
            print(f"  {option.id} = {shown!r}  (OPT_{option.id.upper()})", file=out)
    if args.json:
        print(json.dumps({"selected": plan.selected, "auto_added": sorted(plan.auto_added),
                          "options": plan.options}, indent=2, ensure_ascii=False), file=out)
    return EXIT_OK


# ---------------------------------------------------------------------------
# run --headless
# ---------------------------------------------------------------------------
class HeadlessPrinter:
    """Imprime os eventos do core no terminal (§12, mesmo core da GUI)."""

    def __init__(self, script: Script, out: TextIO, err: TextIO, ui: Any = None,
                 assume_yes: bool = False) -> None:
        self.script = script
        self.out = out
        self.err = err
        self.ui = ui if ui is not None else YesUi()
        self.assume_yes = assume_yes
        self.executor: Executor | None = None
        self._last_progress: tuple[str, str] | None = None
        self._pwin_max = 100.0
        self._tty = bool(getattr(out, "isatty", lambda: False)())

    # -- prompts: delegates ao provedor de UI (§8.5) --------------------
    def _answer(self, event: PromptRequest) -> Any:
        from .core.ipc import CANCEL
        from .core.ui import Prompt

        provider = YesUi() if self.assume_yes else self.ui
        try:
            answer = provider.ask(Prompt.from_request(event))
        except (EOFError, KeyboardInterrupt):
            print(file=self.err)
            if self.executor is not None:
                self.executor.cancel()
            return CANCEL
        if not answer.accepted:
            if self.executor is not None:
                self.executor.cancel()
            return CANCEL
        return answer.value

    # -- eventos -------------------------------------------------------
    def handle(self, event: Event) -> None:
        if isinstance(event, RunStarted):
            print(f"▶ {event.script_name}: {event.total_steps} step(s)", file=self.out)
        elif isinstance(event, StepStarted):
            step = self.script.step(event.step_id)
            title = step.title if step else event.step_id
            print(f"\n▶ [{event.index + 1}/{event.total}] {event.step_id} — {title}", file=self.out)
        elif isinstance(event, LogLine):
            stream = self.err if event.stream == "stderr" else self.out
            print(f"    {event.text}", file=stream)
        elif isinstance(event, Progress):
            self._progress(event)
        elif isinstance(event, ProgressWin):
            self._progress_win(event)
        elif isinstance(event, Notify):
            self.ui.notify(event.text, event.level)
        elif isinstance(event, PromptRequest):
            channel = self.executor.ipc if self.executor else None
            if channel is not None:
                channel.respond(event.request_id, self._answer(event))
        elif isinstance(event, StepFinished):
            self._finished(event)
        elif isinstance(event, RunFinished):
            self._summary(event)

    def _progress(self, event: Progress) -> None:
        text = f"{int((event.value or 0) * 100)}%" if event.value is not None else "…"
        current = (event.step_id or "", text)
        if current == self._last_progress:
            return
        self._last_progress = current
        message = f"    ↳ {text} {event.text}".rstrip()
        if self._tty:
            print("\r\033[K" + message, end="", file=self.out, flush=True)
        else:
            print(message, file=self.out)

    def _progress_win(self, event: ProgressWin) -> None:
        """Janela de progresso dirigida pelo script (§8.4): no terminal vira linha."""
        if event.op == "done":
            print("    ↳ concluído", file=self.out)
            return
        # o update não manda max (só o start): mantém o da sessão
        if event.op == "start" or event.maximum:
            maximum = event.maximum if event.maximum else 100.0
            self._pwin_max = maximum if maximum > 0 else 100.0
        text = f"{event.value:g}/{self._pwin_max:g}"
        message = f"    ↳ {text} {event.text}".rstrip()
        if self._tty:
            print("\r\033[K" + message, end="", file=self.out, flush=True)
        else:
            print(message, file=self.out)

    def _finished(self, event: StepFinished) -> None:
        marks = {
            StepState.SUCCESS: "✔",
            StepState.FAILED: "✖",
            StepState.CANCELLED: "⊘",
            StepState.SKIPPED: "⤼",
        }
        reason = f" — {event.reason}" if event.reason else ""
        code = "" if event.exit_code is None else f" (exit {event.exit_code})"
        line = f"  {marks.get(event.status, '•')} {event.step_id}: {event.status.value} em {event.duration:.1f}s{code}{reason}"
        print(line, file=self.err if event.status is StepState.FAILED else self.out)

    def _summary(self, event: RunFinished) -> None:
        labels = {
            RunState.SUCCESS: "sucesso",
            RunState.FAILED: "falha",
            RunState.CANCELLED: "cancelado",
        }
        print(f"\n{labels.get(event.status, event.status.value)} em {event.duration:.1f}s", file=self.out)


def cmd_run_headless(args: argparse.Namespace, out: TextIO, err: TextIO) -> int:
    from .core import ipc  # import tardio: o core de §7 não depende de FIFOs
    from .core.ui import YesUi, create

    script = parse_script(Path(args.script))
    plan = build_plan(script, _split(args.select), _parse_opts(args.opt), home=str(Path.home()))
    try:
        ui = create("yes" if args.yes else args.ui, has_gui=False)
    except ValueError as exc:
        print(exc, file=out)
        return EXIT_INVALID
    if not args.yes and ui.name == "yes":
        print("aviso: sem terminal e sem --ui, os prompts usam os padrões", file=err)
    printer = HeadlessPrinter(script, out, err, ui=ui, assume_yes=args.yes)
    executor = Executor(
        script,
        plan,
        helpers=helpers_path(),
        assets=Path(args.assets) if args.assets else None,
        ipc_factory=ipc.IpcChannel,
    )
    printer.executor = executor

    def on_signal(number: int, frame: Any) -> None:  # noqa: ARG001
        executor.cancel()

    previous = signal.getsignal(signal.SIGINT)
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, on_signal)
    try:
        result = executor.run(printer.handle)
    finally:
        signal.signal(signal.SIGINT, previous)
        signal.signal(signal.SIGTERM, previous)
        ui.close()
    return result.exit_code()


# ---------------------------------------------------------------------------
# run (GUI) e modo bundle — implementados nas Fases 3 e 5
# ---------------------------------------------------------------------------
def cmd_run_gui(args: argparse.Namespace) -> int:
    try:
        from .gui.app import launch
    except ImportError as exc:
        print(f"GUI indisponível: {exc}", file=sys.stderr)
        return EXIT_INVALID
    return launch(script=Path(args.script), assets=Path(args.assets) if args.assets else None)


def cmd_bundle(args: argparse.Namespace) -> int:
    """Sem subcomando: script embutido no bundle, senão a tela inicial (home).

    Ordem de escolha (SPEC §10.2.0):
    1. ``$APPDIR/payload/script.sh`` (bundle com script embutido, o AppRun define APPDIR);
    2. sem script embutido: a home, onde o usuário escolhe um ``.sh`` (portal ou arrastar).
    """
    from .gui.app import launch

    embedded = embedded_script()
    return launch(script=embedded) if embedded is not None else launch()


def embedded_script() -> Path | None:
    """§10.2.0 — o script empacotado no bundle, se houver."""
    appdir = os.environ.get("APPDIR", "")
    if not appdir:
        return None
    candidate = Path(appdir) / "payload" / "script.sh"
    return candidate if candidate.is_file() else None


def cmd_home(args: argparse.Namespace) -> int:
    """`kbash home`: abre a tela inicial mesmo quando há script embutido."""
    from .gui.app import launch

    return launch()


def _split(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_opts(values: Sequence[str] | None) -> dict[str, str] | None:
    if not values:
        return None
    options: dict[str, str] = {}
    for item in values:
        key, _, value = item.partition("=")
        options[key.strip()] = value
    return options


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kbash", description="kbash — runtime de scripts bash anotados")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="executa um script (GUI, ou --headless no terminal)")
    run.add_argument("script", help="caminho do script anotado")
    run.add_argument("--headless", action="store_true", help="executa no terminal, sem GUI")
    run.add_argument("--select", help="lista de steps separados por vírgula")
    run.add_argument("--opt", action="append", help="opção no formato chave=valor (repetível)")
    run.add_argument("--yes", action="store_true", help="responde aos prompts com os padrões")
    run.add_argument(
        "--ui",
        choices=["auto", "qt", "terminal", "yes", "none"],
        default="auto",
        help="provedor de UI para as perguntas do script (§8.5); padrão: auto",
    )
    run.add_argument("--assets", help="diretório de assets (RT_ASSETS)")

    sub.add_parser("home", help="abre a tela inicial (escolher um script por arquivo ou arrastando)")

    check = sub.add_parser("check", help="valida o script e mostra erros/warnings")
    check.add_argument("script")

    plan = sub.add_parser("plan", help="mostra o plano de execução")
    plan.add_argument("script")
    plan.add_argument("--select", help="lista de steps separados por vírgula")
    plan.add_argument("--opt", action="append", help="opção no formato chave=valor (repetível)")
    plan.add_argument("--json", action="store_true", help="saída em JSON ao final")

    return parser


_COMMANDS = frozenset({"run", "check", "plan", "home"})


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    raw = list(argv) if argv is not None else sys.argv[1:]
    # atalho: `kbash arquivo.sh` é o mesmo que `kbash run arquivo.sh` (SPEC §10.2.0)
    if raw and not raw[0].startswith("-") and raw[0] not in _COMMANDS and Path(raw[0]).is_file():
        raw = ["run", *raw]
    args = parser.parse_args(raw)
    if args.command is None:
        return cmd_bundle(args)
    if args.command == "home":
        return cmd_home(args)
    try:
        if args.command == "check":
            return cmd_check(args, sys.stdout)
        if args.command == "plan":
            return cmd_plan(args, sys.stdout)
        if args.command == "run":
            if args.headless:
                return cmd_run_headless(args, sys.stdout, sys.stderr)
            return cmd_run_gui(args)
    except (ParseError, ValidationError) as exc:
        print(exc, file=sys.stdout)  # §4.6 — sempre com arquivo:linha, em stdout
        return EXIT_INVALID
    except PrecheckError as exc:
        print(f"pré-checagem falhou: {exc}", file=sys.stdout)
        return EXIT_INVALID
    except KbashError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return EXIT_STEP_FAILED
    except FileNotFoundError as exc:
        print(f"erro: {exc.filename}: arquivo não encontrado", file=sys.stdout)
        return EXIT_INVALID
    except IsADirectoryError as exc:
        print(f"erro: {exc.filename}: é um diretório", file=sys.stdout)
        return EXIT_INVALID
    except PermissionError as exc:
        print(f"erro: sem permissão para ler {exc.filename}", file=sys.stdout)
        return EXIT_INVALID
    except KeyboardInterrupt:
        return EXIT_CANCELLED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
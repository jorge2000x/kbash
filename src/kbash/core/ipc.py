"""Transporte de interação runtime ↔ script (SPEC.md §8.1–§8.3).

Dois FIFOs por execução, num diretório ``0700`` (§8.1):

* ``out`` — script → runtime, uma mensagem JSON por linha;
* ``in``  — runtime → script, ``<id>\\t<status>\\t<valor>``.

O runtime abre os dois com ``O_RDWR`` para que nenhuma ponta veja EOF nem
bloqueie na abertura. Usamos caminho (e não FDs herdados) porque ``pkexec``
não repassa descritores extras (§8.1).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from .errors import KbashError
from .events import EventSink, LogLine, Notify, Progress, ProgressWin, PromptRequest

__all__ = [
    "IpcChannel",
    "IpcError",
    "CANCEL",
    "escape_value",
    "unescape_value",
    "encode_response",
    "decode_response",
    "PROMPT_KINDS",
    "STATUS_OK",
    "STATUS_CANCEL",
]

#: Chave de variável aceita por rt_set: vira RT_VAR_<CHAVE> no ambiente (§7.2).
VAR_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def valid_var_key(key: str) -> bool:
    return VAR_KEY_RE.fullmatch(key) is not None


PROMPT_KINDS = ("confirm", "input", "choice", "number", "date", "time", "file", "text", "textbox")
STATUS_OK = "ok"
STATUS_CANCEL = "cancel"

#: Valor que a GUI/CLI devolve para abortar um prompt (§7.4).
CANCEL = "\x00cancel"


class IpcError(KbashError):
    """Falha no transporte de interação."""


# ---------------------------------------------------------------------------
# §8.3 — codificação das respostas runtime → script
# ---------------------------------------------------------------------------
def escape_value(value: str) -> str:
    """``\\`` → ``\\\\``, quebra de linha → ``\\n``, TAB → ``\\t``."""
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")


def unescape_value(value: str) -> str:
    """Inverso de :func:`escape_value` (o helper usa ``printf '%b'``)."""
    out: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 1 < len(value):
            nxt = value[index + 1]
            out.append({"n": "\n", "t": "\t", "r": "\r", "\\": "\\"}.get(nxt, "\\" + nxt))
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def encode_response(request_id: str, status: str, value: str) -> bytes:
    """§8.3 — ``<id>\\t<status>\\t<valor>`` + quebra de linha."""
    line = f"{request_id}\t{status}\t{escape_value(value)}"
    return (line[:4000] + "\n").encode("utf-8")


def decode_response(raw: bytes | str) -> tuple[str, str, str]:
    """Inverso de :func:`encode_response` (usado nos testes do protocolo)."""
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    parts = text.rstrip("\n").split("\t", 2)
    while len(parts) < 3:
        parts.append("")
    request_id, status, value = parts
    return request_id, status, unescape_value(value)


def format_answer(event: PromptRequest, value: Any) -> tuple[str, str]:
    """Converte a resposta da GUI/terminal no par ``(status, valor)`` (§8.3)."""
    if isinstance(value, str) and value == CANCEL:
        return STATUS_CANCEL, ""
    if event.kind == "confirm":
        truthy = (
            value.strip().lower() in ("1", "true", "yes", "y", "s", "sim", "on")
            if isinstance(value, str)
            else bool(value)
        )
        return STATUS_OK, "yes" if truthy else "no"
    if event.kind == "choice" and event.multi:
        if isinstance(value, (list, tuple)):
            return STATUS_OK, "\n".join(str(item) for item in value)
        return STATUS_OK, str(value)
    if value is None:
        return STATUS_OK, ""
    return STATUS_OK, str(value)


# ---------------------------------------------------------------------------
# Canal
# ---------------------------------------------------------------------------
class _Pending:
    __slots__ = ("event", "done")

    def __init__(self, event: PromptRequest) -> None:
        self.event = event
        self.done = threading.Event()


class IpcChannel:
    """Fifos da execução (§8.1). Usado pelo executor via ``ipc_factory``."""

    def __init__(self, workdir: Path, emit: EventSink, owner: str = "") -> None:
        self.workdir = Path(workdir)
        self.step_id = ""
        #: Preenchido pelo executor com o mesmo dict que ele injeta no ambiente (§7.2).
        self.variables: dict[str, str] = {}
        self._emit = emit
        self._processed = 0  # mensagens já lidas (usado por settle)
        self._pending: dict[str, _Pending] = {}
        self._lock = threading.RLock()
        self._closed = False
        self._directory = self._make_dir(owner)
        self.out_path = self._directory / "out"
        self.in_path = self._directory / "in"
        for path in (self.out_path, self.in_path):
            if path.exists():
                path.unlink()
            os.mkfifo(path, 0o600)
        # §8.1 — O_RDWR evita bloqueio na abertura e EOF em nenhum dos lados.
        self._out_fd = os.open(self.out_path, os.O_RDWR | os.O_NONBLOCK)
        self._in_fd = os.open(self.in_path, os.O_RDWR | os.O_NONBLOCK)
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    @property
    def directory(self) -> Path:
        return self._directory

    # -- ciclo de vida --------------------------------------------------
    @staticmethod
    def _make_dir(owner: str) -> Path:
        """§8.1 — cria um diretório novo ``0700``, exclusivo desta execução.

        ``mkdir`` sem ``exist_ok`` é atômico: se o caminho já existir (inclusive
        como symlink plantado em ``/tmp``), a criação falha em vez de reutilizar
        ou alterar o alvo. Nomes únicos por execução evitam que duas execuções
        simultâneas do mesmo script apaguem os FIFOs uma da outra.
        """
        # /tmp só sem XDG_RUNTIME_DIR: o mkdir sem exist_ok falha em qualquer
        # caminho já existente (inclusive symlink plantado), então não há reuso
        base = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp")  # noqa: S108
        base.mkdir(parents=True, exist_ok=True)
        ipc_dir = base / (owner or f"kbash-{os.getpid()}-{secrets.token_hex(4)}")
        try:
            ipc_dir.mkdir(mode=0o700)
        except FileExistsError:
            raise IpcError(f"diretório de IPC já existe: {ipc_dir}") from None
        os.chmod(ipc_dir, 0o700)  # recém-criado por nós: não é um alvo de symlink
        return ipc_dir

    def close(self) -> None:
        """§7.4 — prompts pendentes recebem ``cancel`` ao encerrar."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            pending = list(self._pending.values())
            self._pending.clear()
        for item in pending:
            self._write(item.event.request_id, STATUS_CANCEL, "")
            item.done.set()
        self._reader.join(timeout=2.0)
        for fd in (self._out_fd, self._in_fd):
            with contextlib.suppress(OSError):
                os.close(fd)
        for path in (self.out_path, self.in_path):
            with contextlib.suppress(OSError):
                path.unlink()
        with contextlib.suppress(OSError):
            self._directory.rmdir()

    def __enter__(self) -> "IpcChannel":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- escrita (runtime → script) --------------------------------------
    def _write(self, request_id: str, status: str, value: str) -> None:
        payload = encode_response(request_id, status, value)
        view = memoryview(payload)
        while view:
            try:
                view = view[os.write(self._in_fd, view) :]
            except BlockingIOError:
                threading.Event().wait(0.01)
            except OSError as exc:
                raise IpcError(f"falha ao responder no FIFO: {exc}") from exc

    def respond(self, request_id: str, value: Any = CANCEL) -> None:
        """Responde um :class:`PromptRequest` e libera o script."""
        with self._lock:
            item = self._pending.pop(request_id, None)
        if item is None:
            return
        status, raw = format_answer(item.event, value)
        self._write(request_id, status, raw)
        item.done.set()

    def settle(self, max_wait: float = 0.5) -> None:
        """Espera o que já chegou no FIFO ser processado.

        Chamado entre dois steps: sem isso, um ``rt_set`` do step que acabou
        poderia ser lido só depois do próximo step já ter recebido o ambiente
        (§7.2 — ``RT_VAR_<KEY>``).
        """
        deadline = time.monotonic() + max_wait
        last = self._processed
        quiet = 0.0
        while time.monotonic() < deadline and quiet < 0.05:
            time.sleep(0.01)
            if self._processed != last:
                last = self._processed
                quiet = 0.0
            else:
                quiet += 0.01

    # -- leitura (script → runtime) --------------------------------------
    def _read_loop(self) -> None:
        buffer = b""
        while not self._closed:
            try:
                chunk = os.read(self._out_fd, 65536)
            except BlockingIOError:
                threading.Event().wait(0.02)
                continue
            except OSError:
                break
            if not chunk:
                threading.Event().wait(0.02)
                continue
            buffer += chunk
            while b"\n" in buffer:
                line, _, buffer = buffer.partition(b"\n")
                self._handle_line(line)
        if buffer.strip():
            self._handle_line(buffer)

    def _handle_line(self, raw: bytes) -> None:
        """Processa uma linha; nenhuma mensagem malformada pode matar o leitor.

        Se a linha for inválida e tiver ``id``, o script recebe ``cancel`` para
        não ficar esperando resposta para sempre (§7.4).
        """
        self._processed += 1
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            self._emit(LogLine(None, "kbash", f"mensagem IPC inválida: {text[:120]}", "warn"))
            return
        if not isinstance(message, dict):
            return
        try:
            self._dispatch_message(message)
        except Exception as exc:  # noqa: BLE001 — o leitor não pode morrer
            self._emit(LogLine(self.step_id or None, "kbash",
                               f"mensagem IPC malformada ignorada: {exc}", "warn"))
            request_id = str(message.get("id", ""))
            if request_id and str(message.get("t", "")) in PROMPT_KINDS:
                with self._lock:
                    self._pending.pop(request_id, None)
                with contextlib.suppress(IpcError):
                    self._write(request_id, STATUS_CANCEL, "")

    def _dispatch_message(self, message: dict[str, Any]) -> None:
        kind = str(message.get("t", ""))
        if kind == "progress":
            value = message.get("value")
            self._emit(Progress(self.step_id or None, None if value is None else float(value),
                                str(message.get("text", ""))))
        elif kind == "notify":
            self._emit(Notify(str(message.get("text", ""))))
        elif kind == "progresswin":
            op = str(message.get("op", ""))
            if op not in ("start", "update", "done"):
                op = "update"
            try:
                value = float(message.get("value", 0.0) or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            maximum: float | None = None
            if "max" in message:
                try:
                    maximum = float(message.get("max") or 0.0) or None
                except (TypeError, ValueError):
                    maximum = None
            self._emit(ProgressWin(op, value, maximum,
                                   str(message.get("text", "")), self.step_id or None))
        elif kind == "log":
            self._emit(LogLine(self.step_id or None, "kbash", str(message.get("text", "")),
                               str(message.get("level", "info"))))
        elif kind == "fail":
            text = str(message.get("text", "falha reportada pelo script"))
            self._emit(LogLine(self.step_id or None, "kbash", text, "error"))
            self._emit(Notify(text, "error"))
        elif kind == "set":
            key = str(message.get("key", ""))
            if not valid_var_key(key):
                # chave com espaço ou `=` não vira variável de ambiente (ValueError no Popen)
                self._emit(LogLine(self.step_id or None, "kbash",
                                   f"rt_set ignorado: chave inválida {key!r}", "warn"))
                return
            # rt_get é case-insensitive (usa ^^): `lower` e `LOWER` são a mesma
            # variável; a última escrita vence e a chave guardada é a dela
            for existing in [k for k in self.variables if k.upper() == key.upper()]:
                del self.variables[existing]
            self.variables[key] = str(message.get("value", ""))
        elif kind in PROMPT_KINDS:
            self._dispatch(kind, message)
        elif str(message.get("id", "")):
            # Mensagem com id que não conhecemos: responde cancel para o script
            # não ficar esperando para sempre (§7.4).
            self._write(str(message["id"]), STATUS_CANCEL, "")
            self._emit(
                LogLine(self.step_id or None, "kbash", f"mensagem IPC ignorada: t={kind!r}", "warn")
            )
        else:
            self._emit(LogLine(None, "kbash", f"mensagem IPC desconhecida: t={kind!r}", "warn"))

    def _dispatch(self, kind: str, message: dict[str, Any]) -> None:
        request_id = str(message.get("id", ""))
        raw_choices = message.get("choices", ()) or ()
        if not isinstance(raw_choices, (list, tuple)):
            raise TypeError(f"choices deve ser uma lista, veio {type(raw_choices).__name__}")
        choices = tuple(str(item) for item in raw_choices)
        event = PromptRequest(
            request_id=request_id,
            kind=kind,  # type: ignore[arg-type]
            text=str(message.get("text", "")),
            default=message.get("default"),
            choices=choices,
            multi=bool(message.get("multi", False)),
            secret=bool(message.get("secret", False)),
            label=str(message.get("label", "")),
            minimum=str(message.get("min", "") or ""),
            maximum=str(message.get("max", "") or ""),
            step_id=self.step_id or None,
        )
        pending = _Pending(event)
        with self._lock:
            if self._closed:
                self._write(request_id, STATUS_CANCEL, "")
                return
            self._pending[request_id] = pending
        self._emit(event)
        while not pending.done.wait(0.05) and not self._closed:
            pass
        if not pending.done.is_set():
            with self._lock:
                self._pending.pop(request_id, None)
            self._write(request_id, STATUS_CANCEL, "")
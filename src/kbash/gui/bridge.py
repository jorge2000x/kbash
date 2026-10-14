"""Bridge entre o core e o QML (SPEC.md §3 regra 2, §10.3, §10.4).

O core emite dataclasses; aqui elas viram sinais Qt. A GUI **nunca** chama
``subprocess`` nem lê o script — só fala com este objeto.

Regra do Qt respeitada: a execução acontece numa thread separada, que apenas
*enfileira* eventos. Um timer de 50 ms na thread da GUI drena a fila e altera
modelos/propriedades — nenhum ``QAbstractListModel`` é tocado de fora (§10.3).
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from ..core.errors import PrecheckError
from ..core.events import (
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
from ..core.errors import KbashError
from ..core.executor import Executor, StepResult, helpers_path, precheck
from ..core.parser import parse_script
from ..core.ipc import IpcChannel
from ..core.model import RunPlan, RunState, Script, StepState, is_allowed_link, placeholder_script
from ..core.planner import (
    build_plan,
    can_uncheck,
    default_options,
    option_errors,
    resolve,
    set_checked,
)
from ..core.ui import Prompt
from .models import LogModel, OptionModel, SelectedStepsProxy, StepListModel
from .ui_qt import QtUi

__all__ = ["Bridge", "PAGE_WELCOME", "PAGE_SELECT", "PAGE_RUN", "PAGE_RESULT", "TICK_MS"]

PAGE_WELCOME, PAGE_SELECT, PAGE_RUN, PAGE_RESULT = 0, 1, 2, 3

#: §10.3 — lote de atualização da GUI a cada ~50 ms.
TICK_MS = 50
_MAX_EVENTS_PER_TICK = 2000

#: §10.1 — portal de arquivos no session bus (constantes separadas
#: para os testes apontarem um serviço mockado sem UI).
#: Extensões aceitas como script: `.kbash` é a do programa; `.sh` continua valendo.
SCRIPT_SUFFIXES = (".kbash", ".sh")
PORTAL_SERVICE = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
PORTAL_IFACE = "org.freedesktop.portal.FileChooser"
PORTAL_REQUEST_IFACE = "org.freedesktop.portal.Request"
#: tempo máximo esperando a resposta do portal antes de liberar o pedido
PORTAL_TIMEOUT_MS = 120_000
#: Slot string no formato do Qt (`1 + nome + tipos normalizados`).
#: Medido: `uint` faz o connect retornar False; `int` casa
#: (o QtDBus converte o uint32 do signal na entrega).
#: O portal manda o código como `uint32` (`u`). Um slot `int` não recebe
#: esse sinal: o Qt não entrega e nada aparece no log (bug de cancelar).
PORTAL_RESPONSE_SLOT = "1_on_portal_response(uint,QVariantMap)"


def _portal_service_available() -> bool:
    """Session bus conectado com o portal registrado? (§10.1)"""
    from PySide6.QtDBus import QDBusConnection

    try:
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return False
        registered = bus.interface().isServiceRegistered(PORTAL_SERVICE)
        return bool(registered.value())
    except Exception:
        return False


def _log_portal(message: str) -> None:
    """Diagnóstico do portal no stderr (cai no log de erro do AppImage)."""
    import sys

    print(f"kbash portal: {message}", file=sys.stderr, flush=True)


class Bridge(QObject):
    """Estado e comandos da GUI."""

    # -- sinais para o QML ----------------------------------------------
    promptRequested = Signal(str, str, str, str, "QVariant", "QStringList", bool, bool, str, str)
    notifyRaised = Signal(str, str)
    # -- portal de arquivos (§10.1): (token, caminhos); vazio = cancelado/falha
    filePicked = Signal(str, "QStringList")
    runStartedSignal = Signal()
    runFinishedSignal = Signal(str, str)
    stepStateChanged = Signal(str, str)
    progressSignal = Signal(float, str)
    logFlushed = Signal()
    # -- gaveta de log (§10.2.5): abre/fecha sem painel fixo
    logDrawerOpenChanged = Signal()

    def __init__(self, script: Script | None = None, assets: Path | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # sem script = tela inicial (home): o placeholder não tem etapas nem opções
        script = script if script is not None else placeholder_script()
        self._script = script
        self._assets = assets
        self._page = PAGE_WELCOME
        self._running = False
        self._executor: Executor | None = None
        self._thread: threading.Thread | None = None
        self._queue: queue.SimpleQueue[Event] = queue.SimpleQueue()
        self._completed = 0
        self._total = 0
        self._overall = 0.0
        self._step_progress = 0.0
        self._step_progress_text = ""
        self._current_step = ""
        self._current_title = ""
        self._result_status = ""
        self._result_message = ""
        self._workdir = ""
        self._gui_kit = "kirigami"  # §10.1 — fachada em uso
        self._blocked: dict[str, str] = {}
        self._precheck_problems: list[str] = []
        self._shutdown_done = False
        # -- portal de arquivos (§10.1): um pedido por vez (o diálogo
        # nativo é modal, então não há concorrência real)
        self._portal_token: str | None = None
        self._portal_conn: tuple | None = None
        # se o portal nunca responder, o pedido não pode travar os próximos
        self._portal_watchdog = QTimer(self)
        self._portal_watchdog.setSingleShot(True)
        self._portal_watchdog.setInterval(PORTAL_TIMEOUT_MS)
        self._portal_watchdog.timeout.connect(self._on_portal_timeout)
        # -- gaveta de log (§10.2.5)
        self._log_drawer_open = False
        # -- progresso dirigido pelo script (§8.4)
        self._progress_win_visible = False
        self._progress_win_maximum = 100.0
        self._progress_win_value = 0.0
        self._progress_win_text = ""

        # §8.5 — a GUI é um provedor de UI entre os possíveis (qt/terminal/yes/none)
        self.ui = QtUi(self)
        self.ui.promptRequested.connect(self._on_prompt_requested)
        self.ui.notifyRaised.connect(self.notifyRaised)
        self._steps_model = StepListModel(self)
        self._options_model = OptionModel(self)
        self._log_model = LogModel(self)
        self._run_steps = SelectedStepsProxy(self)
        self._run_steps.setSourceModel(self._steps_model)
        self._steps_model.load(script)
        self._options_model.load(script, default_options(script))
        self._refresh_selection()
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._drain)
        self._timer.start()  # §10.3 — lote de ~50 ms mesmo com o log parado

    # ------------------------------------------------------------------
    # Propriedades expostas ao QML
    # ------------------------------------------------------------------
    pageChanged = Signal()

    def _get_page(self) -> int:
        return self._page

    def _set_page(self, value: int) -> None:
        if value != self._page:
            self._page = value
            self.pageChanged.emit()

    page = Property(int, _get_page, _set_page, notify=pageChanged)

    # -- gaveta de log (§10.2.5) --------------------------------------
    def _get_log_drawer_open(self) -> bool:
        return self._log_drawer_open

    def _set_log_drawer_open(self, value: bool) -> None:
        if bool(value) != self._log_drawer_open:
            self._log_drawer_open = bool(value)
            self.logDrawerOpenChanged.emit()

    logDrawerOpen = Property(bool, _get_log_drawer_open, _set_log_drawer_open, notify=logDrawerOpenChanged)

    # -- progresso dirigido pelo script (§8.4 rt_progresswin_*) -----------
    progressWinVisibleChanged = Signal()
    progressWinChanged = Signal()

    def _get_progress_win_visible(self) -> bool:
        return self._progress_win_visible

    progressWinVisible = Property(bool, _get_progress_win_visible, notify=progressWinVisibleChanged)

    def _get_progress_win_maximum(self) -> float:
        return self._progress_win_maximum

    progressWinMaximum = Property(float, _get_progress_win_maximum, notify=progressWinChanged)

    def _get_progress_win_value(self) -> float:
        return self._progress_win_value

    progressWinValue = Property(float, _get_progress_win_value, notify=progressWinChanged)

    def _get_progress_win_text(self) -> str:
        return self._progress_win_text

    progressWinText = Property(str, _get_progress_win_text, notify=progressWinChanged)

    #: `False` na tela inicial (sem script escolhido ainda)
    hasScriptChanged = Signal()
    hasScript = Property(bool, lambda self: self._has_script(), notify=hasScriptChanged)

    scriptNameChanged = Signal()
    scriptName = Property(str, lambda self: self._script.name, notify=scriptNameChanged)

    scriptDescriptionChanged = Signal()
    scriptDescription = Property(str, lambda self: self._script.description, notify=scriptDescriptionChanged)

    scriptVersionChanged = Signal()
    scriptVersion = Property(str, lambda self: self._script.version, notify=scriptVersionChanged)

    scriptAuthorChanged = Signal()
    scriptAuthor = Property(str, lambda self: self._script.author, notify=scriptAuthorChanged)

    scriptIdChanged = Signal()
    scriptId = Property(str, lambda self: self._script.id, notify=scriptIdChanged)

    scriptIconChanged = Signal()
    scriptIcon = Property(str, lambda self: self._icon_name(), notify=scriptIconChanged)

    scriptIconFileChanged = Signal()
    scriptIconFile = Property(str, lambda self: self._icon_file(), notify=scriptIconFileChanged)

    scriptShaShortChanged = Signal()
    scriptShaShort = Property(str, lambda self: self._script.sha256[:12], notify=scriptShaShortChanged)

    scriptPathChanged = Signal()
    scriptPath = Property(str, lambda self: self._script_path_text(), notify=scriptPathChanged)

    scriptShaChanged = Signal()
    scriptSha = Property(str, lambda self: self._script.sha256, notify=scriptShaChanged)

    canRunChanged = Signal()
    canRun = Property(bool, lambda self: self._can_run(), notify=canRunChanged)

    precheckProblemsChanged = Signal()
    precheckProblems = Property("QStringList", lambda self: list(self._precheck_problems), notify=precheckProblemsChanged)

    rootStepsChanged = Signal()
    rootSteps = Property("QStringList", lambda self: self._root_steps(), notify=rootStepsChanged)

    runningChanged = Signal()
    running = Property(bool, lambda self: self._running, notify=runningChanged)

    overallProgressChanged = Signal()
    overallProgress = Property(float, lambda self: self._overall, notify=overallProgressChanged)

    stepProgressChanged = Signal()
    stepProgress = Property(float, lambda self: self._step_progress, notify=stepProgressChanged)

    stepProgressTextChanged = Signal()
    stepProgressText = Property(str, lambda self: self._step_progress_text, notify=stepProgressTextChanged)

    currentStepTitleChanged = Signal()
    currentStepTitle = Property(str, lambda self: self._current_title, notify=currentStepTitleChanged)

    resultStatusChanged = Signal()
    resultStatus = Property(str, lambda self: self._result_status, notify=resultStatusChanged)

    resultMessageChanged = Signal()
    resultMessage = Property(str, lambda self: self._result_message, notify=resultMessageChanged)

    workdirChanged = Signal()
    workdir = Property(str, lambda self: self._workdir, notify=workdirChanged)

    canRetryChanged = Signal()
    canRetry = Property(bool, lambda self: bool(self._steps_model.failed_ids()), notify=canRetryChanged)

    guiKitChanged = Signal()
    guiKit = Property(str, lambda self: self._gui_kit, notify=guiKitChanged)

    logCountChanged = Signal()
    logCount = Property(int, lambda self: self._log_count(), notify=logCountChanged)

    stepCountChanged = Signal()
    stepCount = Property(int, lambda self: self._steps_model.rowCount(), notify=stepCountChanged)

    selectedCountChanged = Signal()
    selectedCount = Property(int, lambda self: len(self._steps_model.checked_ids()), notify=selectedCountChanged)

    optionCountChanged = Signal()
    optionCount = Property(int, lambda self: self._options_model.rowCount(), notify=optionCountChanged)
    # opções gerais (sem needs_step): o cartão Opções da seleção usa esta contagem
    generalOptionCount = Property(
        int, lambda self: self._options_model.general_count(), notify=optionCountChanged
    )

    # Modelos expostos ao QML. Precisam ser Property: atributos Python puros
    # são invisíveis para o QML (a view lia 0 linhas). Como o objeto nunca é
    # trocado (só o conteúdo muda, via sinais do próprio modelo), constant.
    steps = Property(QObject, lambda self: self._steps_model, constant=True)
    options = Property(QObject, lambda self: self._options_model, constant=True)
    log = Property(QObject, lambda self: self._log_model, constant=True)
    runSteps = Property(QObject, lambda self: self._run_steps, constant=True)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    @Slot(int)
    def goToPage(self, page: int) -> None:  # noqa: N802
        """§10.2 — troca de tela a pedido de um botão.

        Ignora destinos fora do conjunto (§10.2 tem 4 telas) e, enquanto a
        execução está em andamento, ignora qualquer saída da tela de execução:
        sair dela esconde o log e o botão Cancelar justamente quando o usuário
        precisa dos dois.
        """
        if int(page) not in (PAGE_WELCOME, PAGE_SELECT, PAGE_RUN, PAGE_RESULT):
            return
        if self._running and int(page) != PAGE_RUN:
            return
        self._set_page(int(page))

    def setGuiKit(self, kit: str) -> None:  # noqa: N802
        self._gui_kit = kit
        self.guiKitChanged.emit()

    # -- tela inicial (home) ------------------------------------------------
    def _has_script(self) -> bool:
        """Script real tem SHA-256; o placeholder da home não tem."""
        return bool(self._script.sha256)

    def _script_path_text(self) -> str:
        return str(self._script.path) if self._has_script() else ""

    def _local_path(self, location: str) -> Path:
        """Aceita caminho ou URL ``file://`` (o que o arrastar-e-soltar entrega)."""
        if location.startswith("file:"):
            from PySide6.QtCore import QUrl

            return Path(QUrl(location).toLocalFile())
        return Path(location)

    @Slot(str, result=bool)
    def loadScript(self, location: str) -> bool:  # noqa: N802
        """§10.2.0 — abre um ``.sh`` escolhido no portal ou arrastado para a home.

        Recusa com aviso se houver execução em andamento, se não for ``.kbash`` ou ``.sh``, se
        não puder ser lido ou se o parse falhar. Em caso de sucesso, troca o
        script inteiro (etapas, opções, cabeçalho) e volta à tela de boas-vindas.
        """
        if self._running:
            self.notifyRaised.emit("espere a execução terminar antes de abrir outro script", "warn")
            return False
        path = self._local_path(str(location or "").strip())
        if path.suffix.lower() not in SCRIPT_SUFFIXES:
            self.notifyRaised.emit(
                f"escolha um arquivo .kbash ou .sh (recebido: {path.name or location})", "error")
            return False
        try:
            script = parse_script(path)
        except OSError as exc:
            self.notifyRaised.emit(f"não foi possível ler {path}: {exc.strerror or exc}", "error")
            return False
        except KbashError as exc:
            self.notifyRaised.emit(f"script inválido: {exc}", "error")
            return False
        self._set_script(script)
        self.notifyRaised.emit(f"script aberto: {script.name}", "info")
        return True

    def _set_script(self, script: Script) -> None:
        """Troca o script em uso e reconstrói os modelos (sem reiniciar a Bridge)."""
        self._script = script
        self._blocked = {}
        self._precheck_problems = []
        self._steps_model.load(script)
        self._options_model.load(script, default_options(script))
        self._refresh_selection()
        self._set_page(PAGE_WELCOME)
        for name in (
            "hasScriptChanged", "scriptNameChanged", "scriptDescriptionChanged",
            "scriptVersionChanged", "scriptAuthorChanged", "scriptIdChanged",
            "scriptIconChanged", "scriptIconFileChanged", "scriptShaShortChanged",
            "scriptPathChanged", "scriptShaChanged", "stepCountChanged",
            "optionCountChanged", "precheckProblemsChanged",
        ):
            getattr(self, name).emit()

    # -- ícone (§4.2) ----------------------------------------------------
    def _icon_name(self) -> str:
        """Nome de ícone do tema; ``#@icon`` pode ser um caminho em assets/."""
        icon = self._script.icon or ""
        if icon and "/" in icon:
            return "application-x-executable"  # é um arquivo: usa scriptIconFile
        return icon or "application-x-executable"

    def _icon_file(self) -> str:
        """Caminho do ícone quando ``#@icon`` aponta para um arquivo do payload."""
        icon = self._script.icon or ""
        if not icon or "/" not in icon:
            return ""
        candidate = Path(icon)
        if not candidate.is_absolute():
            candidate = (self._assets or self._script.path.parent / "assets") / candidate
        return str(candidate) if candidate.is_file() else ""

    @Slot(str, bool, result=bool)
    def setStepChecked(self, step_id: str, checked: bool) -> bool:  # noqa: N802
        selected = set(self._steps_model.checked_ids())
        try:
            new = set_checked(self._script, selected, step_id, bool(checked))
        except Exception as exc:  # §6 — obrigatórios e dependentes bloqueiam
            self.notifyRaised.emit(str(exc), "warn")
            return False
        self._apply_selection(new)
        return True

    @Slot(str, str)
    def setOption(self, option_id: str, value: str) -> None:  # noqa: N802
        # id vazio nunca é opção válida (parser exige `[a-z][a-z0-9_]*`):
        # um delegate transitório (bindings ainda montando no startup)
        # pode disparar o handler com optId vazio; ignorar evita
        # sujar o modelo e travar o start com "opção desconhecida".
        if not option_id:
            return
        self._options_model.set_value(option_id, value)
        self._refresh_selection()

    @Slot(str, result=str)
    def uncheckReason(self, step_id: str) -> str:  # noqa: N802
        return self._blocked.get(step_id, "")

    # -- portal de arquivos (§10.1) ----------------------------------
    @Slot(str, str)
    def pickFolder(self, token: str, title: str) -> None:  # noqa: N802
        """Abre o seletor de pastas nativo (portal `OpenFile` + `directory`)."""
        self._portal_open("folder", token, title, {"directory": True})

    @Slot(str, str, bool)
    def pickOpenFile(self, token: str, title: str, multiple: bool) -> None:  # noqa: N802
        """Abre o seletor de arquivos nativo (portal `OpenFile`, sem filtro:
        o QtDBus não expressa a estrutura aninhada `a(sa(su))` a partir
        de Python, então o portal mostra todos os arquivos)."""
        self._portal_open("open", token, title, {"multiple": bool(multiple)})

    @Slot(str, str, str)
    def pickSaveFile(self, token: str, title: str, name: str) -> None:  # noqa: N802
        """Abre o salvamento nativo (portal `SaveFile`)."""
        self._portal_open("save", token, title, {"current_name": str(name or "")})
    def _portal_open(self, kind: str, token: str, title: str, options: dict[str, object]) -> None:
        """Chama o portal de forma assíncrona e assina a resposta.

        Falha graciosamente (aviso + resultado vazio). O `call`
        bloqueante congelaria a thread da GUI enquanto o backend
        do portal inicializa; `asyncCall` + watcher não.
        """
        from PySide6.QtDBus import (
            QDBusConnection,
            QDBusMessage,
            QDBusPendingCallWatcher,
        )

        if self._portal_token is not None:
            # antes ignorava em silêncio, e o botão parecia quebrado
            self.notifyRaised.emit("já há uma seleção de arquivo aberta", "warn")
            _log_portal(f"pedido {token!r} ignorado: {self._portal_token!r} ainda pendente")
            return

        def fail() -> None:
            _log_portal(f"portal indisponível para {token!r}")
            self.notifyRaised.emit("seleção de arquivos indisponível (portal)", "warn")
            self.filePicked.emit(token, [])

        try:
            bus = QDBusConnection.sessionBus()
            if not _portal_service_available():
                fail()
                return
        except Exception:
            fail()
            return
        method = {"folder": "OpenFile", "open": "OpenFile", "save": "SaveFile"}.get(kind, "OpenFile")
        try:
            # mensagem montada à mão: QDBusInterface.asyncCall desta
            # build só aceita o nome do método, sem argumentos
            message = QDBusMessage.createMethodCall(PORTAL_SERVICE, PORTAL_PATH, PORTAL_IFACE, method)
            message.setArguments(["", str(title), dict(options)])
            watcher = QDBusPendingCallWatcher(bus.asyncCall(message), self)
        except Exception:
            fail()
            return
        self._portal_token = token
        self._portal_watchdog.start()
        _log_portal(f"pedido {token!r} enviado ({method})")
        watcher.finished.connect(self._on_portal_call_done)

    def _on_portal_call_done(self, watcher: object) -> None:
        """Resposta (handle) da chamada ao portal; assina o `Response`."""
        from PySide6.QtDBus import QDBusConnection, QDBusMessage

        try:
            watcher.deleteLater()
        except Exception:
            pass
        token = self._portal_token
        if token is None:
            return
        fail = False
        handle_path = ""
        try:
            reply = watcher.reply()
            if reply.type() != QDBusMessage.MessageType.ReplyMessage or not reply.arguments():
                fail = True
            else:
                handle = reply.arguments()[0]
                handle_path = handle.path() if hasattr(handle, "path") else str(handle)
        except Exception:
            fail = True
        if fail or not handle_path:
            _log_portal(f"resposta inválida do portal para {token!r}")
            self._portal_watchdog.stop()
            self._portal_token = None
            self.notifyRaised.emit("seleção de arquivos indisponível (portal)", "warn")
            self.filePicked.emit(token, [])
            return
        try:
            bus = QDBusConnection.sessionBus()
            connected = bus.connect("", handle_path, PORTAL_REQUEST_IFACE,
                                    "Response", self, PORTAL_RESPONSE_SLOT)
        except Exception:
            connected = False
        if not connected:
            _log_portal(f"não consegui assinar Response em {handle_path}")
            self._portal_watchdog.stop()
            self._portal_token = None
            self.notifyRaised.emit("seleção de arquivos indisponível (portal)", "warn")
            self.filePicked.emit(token, [])
            return
        self._portal_conn = ("", handle_path, PORTAL_REQUEST_IFACE, "Response")

    @Slot("uint", "QVariantMap")
    def _on_portal_response(self, response: int, results: dict) -> None:
        """Resposta do portal: `0` = ok com `uris`; o resto é cancelado."""
        from PySide6.QtCore import QUrl

        self._portal_watchdog.stop()
        token, self._portal_token = self._portal_token, None
        conn, self._portal_conn = self._portal_conn, None
        _log_portal(f"resposta {response} para {token!r}")
        if conn is not None:
            try:
                from PySide6.QtDBus import QDBusConnection

                QDBusConnection.sessionBus().disconnect(
                    *conn, self, PORTAL_RESPONSE_SLOT)
            except Exception:
                pass
        if token is None:
            return
        paths: list[str] = []
        if response == 0 and isinstance(results, dict):
            uris = results.get("uris", [])
            if isinstance(uris, (list, tuple)):
                for uri in uris:
                    text = str(uri)
                    local = QUrl(text).toLocalFile()
                    paths.append(local if local else text)
        self.filePicked.emit(token, paths)

    def _on_portal_timeout(self) -> None:
        """O portal não respondeu no prazo: libera o pedido para o próximo clique."""
        token, self._portal_token = self._portal_token, None
        conn, self._portal_conn = self._portal_conn, None
        _log_portal(f"sem resposta do portal em {PORTAL_TIMEOUT_MS // 1000}s para {token!r}")
        if conn is not None:
            try:
                from PySide6.QtDBus import QDBusConnection

                QDBusConnection.sessionBus().disconnect(*conn, self, PORTAL_RESPONSE_SLOT)
            except Exception:
                pass
        if token is None:
            return
        self.notifyRaised.emit("a janela de seleção não respondeu; tente de novo", "warn")
        self.filePicked.emit(token, [])

    @Slot(result=bool)
    def start(self) -> bool:
        if self._running:
            return False
        if self._thread is not None and self._thread.is_alive():
            return False
        if not self._has_script():
            self.notifyRaised.emit("abra um script antes de executar", "warn")
            return False
        try:
            plan = self._build_plan()
        except Exception as exc:
            self.notifyRaised.emit(str(exc), "error")
            return False
        # §7.5 — pré-checagens antes de iniciar qualquer coisa
        problems = precheck(self._script, plan)
        if problems:
            message = "; ".join(problems)
            self.notifyRaised.emit(message, "error")
            self.precheckProblemsChanged.emit()
            return False
        self._prepare_run(plan)
        self._running = True
        self.runningChanged.emit()
        self._set_page(PAGE_RUN)
        # §10.2.5 — a gaveta NÃO abre sozinha: só por clique do usuário
        # (cabeçalho, Ctrl+L ou "Ver log")
        try:
            self._executor = Executor(
                self._script,
                plan,
                helpers=helpers_path(),
                assets=self._assets,
                ipc_factory=IpcChannel,
            )
        except Exception as exc:
            self._running = False
            self.runningChanged.emit()
            self._set_page(PAGE_SELECT)
            self.notifyRaised.emit(f"não foi possível iniciar a execução: {exc}", "error")
            return False
        self._thread = threading.Thread(target=self._run, name="kbash-run", daemon=True)
        self._thread.start()
        return True

    @Slot()
    def cancel(self) -> None:
        if self._executor is not None:
            self._executor.cancel()
        self.ui.close()  # §7.4 — prompts pendentes viram cancel, sem travar o fim

    @Slot(str, "QVariant")
    def answer(self, request_id: str, value: Any) -> None:
        """Resposta do QML ao diálogo (§8.5)."""
        self.ui.resolve(request_id, value)

    @Slot(str)
    def cancelPrompt(self, request_id: str) -> None:  # noqa: N802
        """O usuário fechou o diálogo: o script recebe ``cancel`` (§7.4)."""
        from ..core.ui import CANCEL_SENTINEL

        self.ui.resolve(request_id, CANCEL_SENTINEL)

    @Slot(str, str, str, str, "QVariant", "QStringList", bool, bool, str, str)
    def _on_prompt_requested(  # noqa: N802
        self, request_id: str, kind: str, text: str, label: str, default: Any,
        choices: list[str], multi: bool, secret: bool, minimum: str = "", maximum: str = "",
    ) -> None:
        self.promptRequested.emit(request_id, kind, text, label, default, choices, multi, secret,
                                   minimum, maximum)

    def _ask_ui(self, event: PromptRequest) -> None:
        """Pergunta ao provedor de UI e devolve a resposta ao script (§8.5).

        ``ui.ask`` bloqueia; por isso roda numa thread curta — a thread da GUI
        nunca fica esperando o usuário (§10.4).
        """
        prompt = Prompt.from_request(event)
        channel = self._executor.ipc if self._executor is not None else None

        def worker() -> None:
            answer = self.ui.ask(prompt)
            if channel is not None:
                from ..core.ipc import CANCEL

                channel.respond(prompt.id, CANCEL if not answer.accepted else answer.value)

        threading.Thread(target=worker, name="kbash-prompt", daemon=True).start()

    @Slot()
    def retryFailed(self) -> None:  # noqa: N802
        failed = self._steps_model.failed_ids()
        if not failed:
            return
        # só os que falharam (dependências entram via resolve); os que já
        # deram certo saem da seleção
        self._apply_selection(set(failed))
        self.start()

    @Slot()
    def closeApp(self) -> None:  # noqa: N802
        self.cancel()
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.quit()

    @Slot(str, result=bool)
    def saveLog(self, path: str) -> bool:  # noqa: N802
        try:
            header = f"# {self._script.name} ({self._script.id}) sha256={self._script.sha256}"
            self._log_model.to_file(path, header)
        except OSError as exc:
            self.notifyRaised.emit(f"não foi possível salvar o log: {exc}", "error")
            return False
        self.notifyRaised.emit(f"log salvo em {path}", "info")
        return True

    @Slot(str, result=bool)
    def openLink(self, url: str) -> bool:  # noqa: N802
        """§4.3 — ``type=link``: abre o endereço declarado no script no navegador
        padrão. Só ``http``/``https``; qualquer outro esquema é recusado."""
        if not is_allowed_link(url):
            self.notifyRaised.emit(f"link recusado (só http/https): {url}", "error")
            return False
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        opened = bool(QDesktopServices.openUrl(QUrl(url.strip())))
        if not opened:
            self.notifyRaised.emit("não foi possível abrir o link no navegador", "warn")
        return opened

    @Slot(result=str)
    def logText(self) -> str:  # noqa: N802
        self._log_model.flush()  # garante que o texto salvo/copiado está completo
        # sem logCountChanged aqui: emitir signal de dentro do getter
        # durante a avaliação de um binding (`text: bridge.logText()`)
        # é o padrão que gerava o loop de notificação
        return self._log_model.text()

    @Slot(str)
    def copyToClipboard(self, text: str) -> None:  # noqa: N802
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication.instance()
        if app is not None:
            app.clipboard().setText(text)

    # ------------------------------------------------------------------
    # Thread de execução — apenas enfileira eventos
    # ------------------------------------------------------------------
    def _run(self) -> None:
        executor = self._executor
        assert executor is not None
        try:
            result = executor.run(self._queue.put, check=True)
        except PrecheckError as exc:
            self._queue.put(_PrecheckFailed(str(exc)))
            return
        except Exception as exc:  # pragma: no cover - rede de segurança
            self._queue.put(_RunCrashed(f"falha interna na execução: {exc}"))
            return
        self._queue.put(_RunDone(result.status, result.steps, result.workdir))

    # ------------------------------------------------------------------
    # Thread da GUI — consome a fila
    # ------------------------------------------------------------------
    def _drain(self) -> None:
        if self._log_model.flush():
            self.logCountChanged.emit()
            self.logFlushed.emit()
        for _ in range(_MAX_EVENTS_PER_TICK):
            try:
                event = self._queue.get_nowait()
            except queue.Empty:
                return
            self._apply(event)

    def _apply(self, event: Event) -> None:
        match event:
            case RunStarted():
                self._workdir = event.workdir
                self.workdirChanged.emit()
                self.runStartedSignal.emit()
            case StepStarted():
                self._current_step = event.step_id
                self._current_title = self._steps_model.title(event.step_id)
                self._step_progress = 0.0
                self._step_progress_text = ""
                self._steps_model.set_status(event.step_id, StepState.RUNNING.value)
                self.stepStateChanged.emit(event.step_id, StepState.RUNNING.value)
                self.currentStepTitleChanged.emit()
                self.stepProgressChanged.emit()
            case StepFinished():
                self._completed += 1
                self._steps_model.set_status(event.step_id, event.status.value, event.duration, event.reason)
                self.stepStateChanged.emit(event.step_id, event.status.value)
                self._overall = self._ratio()
                self._step_progress = 1.0 if event.status is StepState.SUCCESS else self._step_progress
                self.overallProgressChanged.emit()
                self.stepProgressChanged.emit()
                self.canRetryChanged.emit()
            case LogLine():
                self._log_model.push(event.text, event.stream, event.level, event.step_id or "")
            case Progress():
                self._step_progress = float(event.overall or 0.0)
                self._step_progress_text = event.text
                self._overall = self._ratio()
                self.stepProgressChanged.emit()
                self.stepProgressTextChanged.emit()
                self.overallProgressChanged.emit()
                self.progressSignal.emit(self._step_progress, event.text)
            case PromptRequest():
                self._ask_ui(event)
            case Notify():
                self.notifyRaised.emit(event.text, event.level)
            case ProgressWin():
                before = (
                    self._progress_win_visible, self._progress_win_maximum,
                    self._progress_win_value, self._progress_win_text,
                )
                if event.op == "start":
                    maximum = event.maximum if event.maximum else 100.0
                    self._progress_win_visible = True
                    self._progress_win_maximum = maximum if maximum > 0 else 100.0
                    self._progress_win_value = max(0.0, min(event.value, self._progress_win_maximum))
                    self._progress_win_text = event.text
                elif event.op == "done":
                    self._progress_win_visible = False
                else:
                    if event.maximum:
                        self._progress_win_maximum = event.maximum if event.maximum > 0 else 100.0
                    self._progress_win_value = max(0.0, min(event.value, self._progress_win_maximum))
                    self._progress_win_text = event.text or self._progress_win_text
                after = (
                    self._progress_win_visible, self._progress_win_maximum,
                    self._progress_win_value, self._progress_win_text,
                )
                if after != before:
                    if after[0] != before[0]:
                        self.progressWinVisibleChanged.emit()
                    self.progressWinChanged.emit()
            case RunFinished():
                self._overall = self._ratio()
                self.overallProgressChanged.emit()
            case _RunDone():
                self._log_model.flush()  # o log final aparece de uma vez
                self.logCountChanged.emit()
                self._running = False
                self.runningChanged.emit()
                # a janela de progresso do script não sobrevive ao fim
                if self._progress_win_visible:
                    self._progress_win_visible = False
                    self.progressWinVisibleChanged.emit()
                self._result_status = event.status.value
                self._result_message = self._summarize(event.status, event.steps)
                self.resultStatusChanged.emit()
                self.resultMessageChanged.emit()
                self.canRetryChanged.emit()
                self._set_page(PAGE_RESULT)
                self.runFinishedSignal.emit(event.status.value, self._result_message)
            case _PrecheckFailed():
                self._running = False
                self.runningChanged.emit()
                self.notifyRaised.emit(event.message, "error")
                self._set_page(PAGE_SELECT)
                self.precheckProblemsChanged.emit()
            case _RunCrashed():
                self._log_model.flush()
                self.logCountChanged.emit()
                self._running = False
                self.runningChanged.emit()
                self._result_status = RunState.FAILED.value
                self._result_message = event.message
                self.resultStatusChanged.emit()
                self.resultMessageChanged.emit()
                self.canRetryChanged.emit()
                self._set_page(PAGE_RESULT)
                self.runFinishedSignal.emit(RunState.FAILED.value, event.message)

    def _ratio(self) -> float:
        if not self._total:
            return 0.0
        return min(1.0, (self._completed + self._step_progress) / self._total)

    @staticmethod
    def _summarize(status: RunState, steps: list[StepResult]) -> str:
        done = sum(1 for step in steps if step.status is StepState.SUCCESS)
        failed = [step.step_id for step in steps if step.status is StepState.FAILED]
        skipped = sum(1 for step in steps if step.status is StepState.SKIPPED)
        if status is RunState.CANCELLED:
            return "Execução cancelada pelo usuário."
        if status is RunState.SUCCESS:
            return f"{done} etapa(s) concluída(s) com sucesso."
        message = f"{done} etapa(s) concluída(s), {len(failed)} com falha"
        if skipped:
            message += f", {skipped} ignorada(s)"
        if failed:
            message += ": " + ", ".join(failed)
        return message + "."

    # ------------------------------------------------------------------
    # Seleção e validação (§6, §7.5)
    # ------------------------------------------------------------------
    def _prepare_run(self, plan: RunPlan) -> None:
        self._log_model.clear()
        self._steps_model.reset_status()
        self._completed = 0
        self._total = len(plan.selected)
        self._overall = 0.0
        self._step_progress = 0.0
        self._step_progress_text = ""
        self._result_status = ""
        self._result_message = ""
        self._current_step = ""
        self._current_title = ""
        self.logCountChanged.emit()
        self.overallProgressChanged.emit()
        self.stepProgressChanged.emit()
        self.stepProgressTextChanged.emit()
        self.currentStepTitleChanged.emit()
        self.resultStatusChanged.emit()
        self.resultMessageChanged.emit()
        self.canRetryChanged.emit()

    def _apply_selection(self, selected: set[str]) -> None:
        for step in self._steps_model.steps():
            if step.id in selected:
                self._steps_model.set_checked(step.id, True)
            elif not step.required:
                self._steps_model.set_checked(step.id, False)
        self._refresh_selection()

    def _refresh_selection(self) -> None:
        """Recalcula seleção, bloqueios e selos 'por dependência' (§6)."""
        selected = set(self._steps_model.checked_ids())
        for step in self._steps_model.steps():
            if step.required:
                selected.add(step.id)
        resolution = resolve(self._script, list(selected))
        selected = set(resolution.ids)
        self._blocked = {}
        for step in self._steps_model.steps():
            reason = can_uncheck(self._script, step.id, selected) if step.id in selected else None
            locked = step.required or (step.id in selected and reason is not None)
            if locked and step.id in selected:
                self._blocked[step.id] = reason or "obrigatório"
            self._steps_model.set_checked(step.id, step.id in selected, locked=locked)
        self._steps_model.set_auto_added(resolution.auto_added)
        self._options_model.set_selected(selected)
        self._options_model.set_errors(option_errors(self._script, self._options_model.values(), selected))
        self._options_model.reload_errors()
        self._precheck_problems = self._prechecks()
        self.canRunChanged.emit()
        self.precheckProblemsChanged.emit()
        self.rootStepsChanged.emit()
        self.stepCountChanged.emit()
        self.optionCountChanged.emit()
        self.selectedCountChanged.emit()

    def _can_run(self) -> bool:
        if self._running or not self._steps_model.checked_ids():
            return False
        return not option_errors(
            self._script, self._options_model.values(), set(self._steps_model.checked_ids())
        )

    def _prechecks(self) -> list[str]:
        try:
            plan = self._build_plan()
        except Exception:
            return []
        return precheck(self._script, plan)

    def _root_steps(self) -> list[str]:
        return [
            step.title
            for step in self._steps_model.steps()
            if step.root and step.id in set(self._steps_model.checked_ids())
        ]

    def _build_plan(self) -> RunPlan:
        errors = option_errors(
            self._script, self._options_model.values(), set(self._steps_model.checked_ids())
        )
        self._options_model.set_errors(errors)
        self._options_model.reload_errors()
        if errors:
            raise ValueError("preencha as opções obrigatórias antes de executar")
        return build_plan(self._script, self._steps_model.checked_ids(), self._options_model.values())

    def _log_count(self) -> int:
        return self._log_model.rowCount()

    @Slot()
    def shutdown(self) -> None:
        """Encerra tudo (usado no fechamento da janela e nos testes)."""
        if self._shutdown_done:
            return
        self._shutdown_done = True
        self.cancel()
        self.ui.close()  # §7.4 — prompts pendentes viram cancel
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._timer.stop()


class _RunDone:
    """Evento interno: a execução terminou."""

    __slots__ = ("status", "steps", "workdir")

    def __init__(self, status: RunState, steps: list[StepResult], workdir: str) -> None:
        self.status = status
        self.steps = steps
        self.workdir = workdir


class _PrecheckFailed:
    """Evento interno: falha antes de começar (§7.5)."""

    __slots__ = ("message",)

    def __init__(self, message: str) -> None:
        self.message = message


class _RunCrashed:
    """Evento interno: o executor quebrou no meio da execução (vai ao resultado)."""

    __slots__ = ("message",)

    def __init__(self, message: str) -> None:
        self.message = message


def load_bridge(script_path: Path, assets: Path | None = None) -> Bridge:
    """Atalho usado pela CLI e pelos testes."""
    return Bridge(parse_script_path(script_path), assets)


def parse_script_path(path: Path) -> Script:
    from ..core.parser import parse_script

    return parse_script(path)

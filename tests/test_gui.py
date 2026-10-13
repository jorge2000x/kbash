"""Testes da GUI (SPEC.md §10, Fase 3).

Roda com ``QT_QPA_PLATFORM=offscreen``: não precisa de display.
"""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Basic de propósito: o Breeze offscreen é ordens de magnitude mais lento
# e tem bugs próprios de estilo (ex.: ProgressBar); regressão visual
# Breeze-somente não é coberta aqui — smoke manual na sessão com display.
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from fixtures.paths import DEV_SETUP, FAILING  # noqa: E402

pytest.importorskip("PySide6", reason="GUI exige PySide6")

from PySide6.QtCore import QCoreApplication, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from rt.core.model import StepState  # noqa: E402
from rt.gui.app import create_engine, qml_dir  # noqa: E402
from rt.gui.models import LOG_BUFFER, LogModel  # noqa: E402

#: Valores mínimos para instanciar cada fachada num smoke test.
#: Valores mínimos (expressões QML) para instanciar cada fachada no smoke test.
_FACADE_DEFAULTS: dict[str, dict[str, str]] = {
    "AppPage": {"heading": "'x'", "subheading": "''"},
    "AppCard": {"title": "'x'", "subtitle": "''"},
    "AppDialog": {"dialogTitle": "'x'", "message": "''"},
    "AppHeader": {"title": "'x'", "subtitle": "''", "iconName": "''", "iconFile": "''"},
    "AppButton": {"text": "'x'", "variant": "'primary'"},
    "AppCheckBox": {},
    "AppPlaceholder": {"text": "'x'", "explanation": "''", "iconName": "''"},
    "StepBadge": {"text": "'x'", "tone": "'info'"},
    "InlineMessage": {"text": "'x'", "tone": "'error'"},
    "AppIcon": {"name": "'edit'", "source": "''"},
    "AppTextField": {},
    "AppSwitch": {},
    "AppComboBox": {},
    "AppProgressBar": {},
    "LogPanel": {},
    "StepRow": {
        "stepId": "'a'", "title": "'t'", "description": "''", "group": "''",
        "checked": "true", "locked": "false", "status": "'pending'", "needsRoot": "false",
        "duration": "0", "required": "false", "autoAdded": "false", "reason": "''",
        "statusLabel": "''",
    },
    "OptionField": {
        "optId": "'a'", "type": "'string'", "label": "'l'", "value": "'v'", "choices": "[]",
        "required": "false", "error": "''", "help": "''",
    },
    "PromptDialog": {
        "requestId": "'r'", "kind": "'confirm'", "promptText": "''", "promptLabel": "''",
        "promptDefault": "''", "promptChoices": "[]", "promptMulti": "false",
        "promptSecret": "false",
    },
}


def _smoke_qml(names: Sequence[str]) -> str:
    """QML que instancia todas as fachadas dentro de um Item neutro.

    Todas em um único arquivo: o Qt reclama de "File name case mismatch" quando
    o mesmo componente é carregado de arquivos diferentes com o mesmo conteúdo.
    """
    body = ""
    for name in names:
        properties = "".join(
            f"\n        {key}: {value}" for key, value in _FACADE_DEFAULTS.get(name, {}).items()
        )
        body += f"\n    {name} {{{properties}\n    }}"
    return f"import QtQuick\nimport BashRT\n\nItem {{{body}\n}}\n"


LONG_SCRIPT = """\
#!/usr/bin/env bash
#@runtime 1
#@name GUI de teste

#@option nome type=string label="Nome" required=true
#@option editor type=choice label="Editor" choices="vim,nano" default=nano
#@option seg type=bool label="Segredo" default=false

#@step primeiro
#@title Primeira etapa
#@desc Uma descrição qualquer
primeiro() { echo "linha 1"; echo "erro" >&2; }

#@step segundo
#@group Grupo
#@depends primeiro
segundo() { rt_confirm "Continuar?" y && echo "confirmado"; }

#@step terceiro
#@depends segundo
#@timeout 1
terceiro() { sleep 30; }
"""


@pytest.fixture(scope="session")
def app():
    instance = QGuiApplication.instance() or QGuiApplication([])
    yield instance
    instance.processEvents()


def answer_prompts(bridge, value=True):  # noqa: ANN001, ANN201
    """Liga o provedor de UI da GUI a uma resposta automática (§8.5)."""
    bridge.promptRequested.connect(
        lambda request_id, *_rest: bridge.answer(request_id, value)
    )
    return bridge


def spin(app, predicate, timeout: float = 60.0) -> bool:  # noqa: ANN001
    """Roda o event loop do Qt até a condição valer (§10.4 — nada na thread GUI)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return False


@pytest.fixture()
def gui(app, tmp_path: Path):
    script = tmp_path / "gui.sh"
    script.write_text(LONG_SCRIPT, encoding="utf-8")
    application, engine, roots = create_engine(script)
    bridge = engine.rootContext().contextProperty("bridge")
    yield application, engine, roots, bridge
    bridge.shutdown()
    application.processEvents()


# -- carregamento ------------------------------------------------------------
def test_main_window_loads(gui) -> None:
    _app, _engine, roots, bridge = gui
    assert len(roots) == 1
    assert bridge.page == 0
    assert bridge.scriptName == "GUI de teste"
    assert bridge.steps.rowCount() == 3
    assert bridge.options.rowCount() == 3


def test_qml_module_is_declared() -> None:
    qmldir = qml_dir() / "kirigami" / "BashRT" / "qmldir"
    assert qmldir.is_file()
    text = qmldir.read_text(encoding="utf-8")
    assert "module BashRT" in text
    for component in ("AppPage", "AppButton", "AppCard", "AppDialog", "PromptDialog"):
        assert f"{component} 1.0" in text, component


def test_pages_fill_the_window_width(gui) -> None:
    """Regressão de layout: os cartões ficavam na largura do conteúdo.

    A tela inteira colapsava numa faixa de ~325 px numa janela de 940 px, com
    o texto cortado. Três coisas causaram isso e qualquer uma delas volta a
    quebrar: `ScrollView` como `contentItem` da `Kirigami.Page` (a Page é um
    Flickable e o ScrollView fica com largura 0), `Layout.alignment:
    Qt.AlignHCenter` na coluna (faz o Layout medir pelo conteúdo) e a
    `ApplicationWindow` sem `ColumnLayout` ancorada em volta do conteúdo.
    """
    from PySide6.QtQuick import QQuickItem

    _app, _engine, roots, bridge = gui
    bridge.goToPage(1)
    assert spin(_app, lambda: bridge.page == 1)

    def widest_card() -> int:
        widest = 0

        def walk(item: object, depth: int = 0) -> None:
            nonlocal widest
            if depth > 40 or not isinstance(item, QQuickItem):
                return
            if "AppCard_QMLTYPE" in item.metaObject().className() and item.isVisible():
                widest = max(widest, int(item.width()))
            for child in item.childItems():
                walk(child, depth + 1)

        walk(roots[0].property("contentItem"))
        return widest

    assert spin(_app, lambda: widest_card() > 0), "nenhum cartão visível"
    window_width = int(roots[0].property("width"))
    card_width = widest_card()
    # o cartão ocupa a coluna de leitura: perto da janela, nunca estreito
    assert card_width >= window_width - 2 * 120, f"cartão com {card_width}px numa janela de {window_width}px"
    assert card_width <= window_width, "cartão maior que a janela"


def test_pages_are_declared_as_a_module() -> None:
    """main.qml instancia as telas por nome: elas precisam ser um módulo."""
    qmldir = qml_dir() / "pages" / "qmldir"
    assert qmldir.is_file()
    text = qmldir.read_text(encoding="utf-8")
    assert "module pages" in text
    for page in ("WelcomePage", "SelectPage", "RunPage", "ResultPage"):
        assert f"{page} 1.0" in text, page
        assert (qml_dir() / "pages" / f"{page}.qml").is_file()
    assert "import pages" in (qml_dir() / "main.qml").read_text(encoding="utf-8")


def test_pages_survive_navigation(app, gui) -> None:
    """§10.2 — as telas nascem uma vez: navegar não recria a tela.

    Com um `Loader` por página, voltar da Seleção para as Boas-vindas
    destruiria tudo que estava montado (scroll, auto-scroll do log, o diálogo
    de log aberto). O StackLayout só troca o índice.
    """
    import re

    from PySide6.QtQuick import QQuickItem

    _app, _engine, roots, bridge = gui

    def page_items() -> dict:
        found: dict = {}

        def walk(item: object, depth: int = 0) -> None:
            if depth > 40 or not isinstance(item, QQuickItem):
                return
            # QML registra como `Nome_QMLTYPE_<id>`
            match = re.match(r"^(\w+)_QMLTYPE", item.metaObject().className())
            if match and match.group(1).endswith("Page"):
                found[match.group(1)] = item
            for child in item.childItems():
                walk(child, depth + 1)

        walk(roots[0].property("contentItem"))
        return found

    before = page_items()
    assert {"WelcomePage", "SelectPage", "RunPage", "ResultPage"} <= set(before), sorted(before)

    bridge.goToPage(1)
    assert spin(app, lambda: bridge.page == 1)
    bridge.goToPage(0)
    assert spin(app, lambda: bridge.page == 0)

    after = page_items()
    for name, item in before.items():
        assert after.get(name) is item, f"{name} foi recriada ao navegar"


def test_go_to_page_ignores_unknown_destinations(gui) -> None:
    """§10.2 tem 4 telas: um índice fora delas não pode trocar a tela."""
    _app, _engine, _roots, bridge = gui
    for bad in (-1, 4, 99):
        bridge.goToPage(bad)
        _app.processEvents()
        assert bridge.page == 0, bad
    bridge.goToPage(1)
    _app.processEvents()
    assert bridge.page == 1


def test_go_to_page_cannot_leave_the_run_screen(gui) -> None:
    """Durante a execução a tela é a de execução: é onde ficam o log e o Cancelar."""
    _app, _engine, _roots, bridge = gui
    bridge._running = True  # noqa: SLF001 — o guarda é justamente sobre esse estado
    for page in (0, 1, 3):
        bridge.goToPage(page)
        _app.processEvents()
        assert bridge.page == 0, page
    bridge.goToPage(2)
    _app.processEvents()
    assert bridge.page == 2


# -- modelos (§10.3) ---------------------------------------------------------
def test_step_model_roles(gui) -> None:
    _app, _engine, _roots, bridge = gui
    model = bridge.steps
    names = {bytes(value).decode() for value in model.roleNames().values()}
    assert {"stepId", "title", "description", "group", "checked", "locked", "status",
            "root", "duration"} <= names
    index = model.index(0, 0)
    assert model.data(index, model.StepId) == "primeiro"
    assert model.data(index, model.Title) == "Primeira etapa"
    assert model.data(index, model.Description) == "Uma descrição qualquer"
    assert model.data(index, model.Checked) is True
    assert model.data(index, model.Status) == StepState.PENDING.value
    assert model.data(index, model.Root) is False


def test_option_model_roles(gui) -> None:
    _app, _engine, _roots, bridge = gui
    model = bridge.options
    names = {bytes(value).decode() for value in model.roleNames().values()}
    assert {"optId", "type", "label", "value", "choices", "required", "error"} <= names
    index = model.index(1, 0)
    assert model.data(index, model.OptId) == "editor"
    assert model.data(index, model.Type) == "choice"
    assert model.data(index, model.Choices) == ["vim", "nano"]
    assert model.data(index, model.Value) == "nano"


def test_log_model_overflow_keeps_newest() -> None:
    """§10.3 — com o buffer cheio, o flush descarta as antigas e mantém as novas."""
    model = LogModel(capacity=5)
    for number in range(5):
        model.push(f"antiga {number}", "stdout", "info", "s")
    assert model.flush() == 5
    inserted: list[tuple[int, int]] = []
    model.rowsInserted.connect(lambda _p, first, last: inserted.append((first, last)))
    for number in range(3):
        model.push(f"nova {number}", "stdout", "info", "s")
    assert model.flush() == 3
    assert model.rowCount() == 5
    assert model.data(model.index(0, 0), model.Text) == "antiga 3"
    assert model.data(model.index(4, 0), model.Text) == "nova 2"
    assert model.dropped == 3
    assert inserted and inserted[-1][0] == 2  # novas entram no fim, não na posição 0


def test_log_model_batches_and_caps() -> None:
    model = LogModel(capacity=1000)
    for number in range(100_000):  # §10.3 — não pode travar com saída volumosa
        model.push(f"linha {number}", "stdout", "info", "step")
    assert model.rowCount() == 0  # nada aplicado antes do flush
    started = time.monotonic()
    inserted = model.flush()
    elapsed = time.monotonic() - started
    assert inserted == 1000
    assert model.rowCount() == 1000
    assert model.dropped == 99_000
    assert elapsed < 2.0
    assert model.data(model.index(0, 0), model.Text) == "linha 99000"
    assert model.text().startswith("[step] linha 99000")
    assert LOG_BUFFER >= 20_000


def test_copy_to_clipboard(gui) -> None:
    """RunPage.qml usa bridge.copyToClipboard (não existe `clipboard` no QML)."""
    from PySide6.QtGui import QGuiApplication

    _app, _engine, _roots, bridge = gui
    bridge.copyToClipboard("texto copiado")
    assert QGuiApplication.clipboard().text() == "texto copiado"


def test_theme_follows_the_system_palette(app) -> None:
    """§10.1 — a paleta vem do Kirigami e o log acompanha o esquema.

    Não existe troca de tema em tempo de execução: este build do Kirigami não
    expõe `Theme.colorScheme` e ignora
    `QGuiApplication.styleHints().setColorScheme()`, então um botão que
    "forçasse" o esquema mentiria para o usuário. O garantido é seguir o
    sistema — e as cores desenhadas à mão precisam acompanhar.
    """
    from PySide6.QtGui import QColor
    from PySide6.QtQml import QQmlEngine

    from rt.gui.app import _create_theme

    engine = QQmlEngine()
    theme = _create_theme(engine, "kirigami")

    background = QColor(theme.property("base"))
    assert theme.property("isDark") is (background.lightnessF() < 0.5)

    # o `forcedScheme` que o botão de tema escrevia saiu: não há mais o que
    # "forçar", e sem ele a cor do log acompanha `isDark` de verdade.
    assert theme.metaObject().indexOfProperty("forcedScheme") == -1
    log_base = QColor(theme.property("logBase"))
    for role in ("logText", "logError", "logWarn"):
        assert QColor(theme.property(role)).lightnessF() != log_base.lightnessF(), role


def test_toast_never_paints_fixed_white_on_a_saturated_background() -> None:
    """Regressão de contraste: o toast pinava o fundo com a cor do nível.

    As cores de texto do Kirigami são escuras no tema claro e claras no
    escuro; usá-las como fundo com `#ffffff` por cima deixava o texto
    ilegível justamente no tema escuro. O fundo é `surface` e o texto é a cor
    do nível, pelas duas pontas da paleta.
    """
    main = (qml_dir() / "main.qml").read_text(encoding="utf-8")
    toast = main[main.index("id: toast") :]
    assert "theme.onSurface(toast.level)" in toast, "o toast precisa pintar o texto pelo nível"
    assert 'color: theme.surface' in toast, "o fundo do toast não pode ser a cor do nível"
    assert "#ffffff" not in toast and "#000000" not in toast, "cor fixa no toast"


def test_log_model_streams_are_distinguished(gui) -> None:
    _app, _engine, _roots, bridge = gui
    model = bridge.log
    model.push("normal", "stdout", "info", "s1")
    model.push("problema", "stderr", "error", "s1")
    model.flush()
    assert model.data(model.index(0, 0), model.Stream) == "stdout"
    assert model.data(model.index(1, 0), model.Stream) == "stderr"
    assert model.data(model.index(1, 0), model.Level) == "error"


# -- seleção (§6) ------------------------------------------------------------
def test_required_option_blocks_run(gui) -> None:
    _app, _engine, _roots, bridge = gui
    assert bridge.canRun is False
    bridge.goToPage(1)
    bridge.setOption("nome", "Ana")
    assert bridge.canRun is True


def test_unchecking_dependent_is_blocked(gui) -> None:
    _app, _engine, _roots, bridge = gui
    assert bridge.setStepChecked("primeiro", False) is False
    assert "primeiro" in bridge.steps.checked_ids()
    # desmarcar o último da cadeia é permitido
    assert bridge.setStepChecked("terceiro", False) is True
    assert "terceiro" not in bridge.steps.checked_ids()


def test_checking_pulls_dependencies(gui) -> None:
    _app, _engine, _roots, bridge = gui
    assert bridge.setStepChecked("terceiro", False) is True
    assert bridge.setStepChecked("segundo", False) is True
    assert bridge.setStepChecked("primeiro", False) is True
    assert bridge.steps.checked_ids() == []
    bridge.setStepChecked("terceiro", True)
    assert set(bridge.steps.checked_ids()) == {"terceiro", "segundo", "primeiro"}


# -- execução (§10.2) --------------------------------------------------------
def test_end_to_end_run(app) -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        script = Path(folder) / "e2e.sh"
        script.write_text(
            "#!/usr/bin/env bash\n#@runtime 1\n#@name E2E\n#@strict false\n"
            "#@option nome type=string label=\"Nome\" required=true\n"
            "#@step um\num() { echo \"o valor é $OPT_NOME\"; }\n",
            encoding="utf-8",
        )
        application, engine, _roots = create_engine(script)
        bridge = engine.rootContext().contextProperty("bridge")
        bridge.setOption("nome", "Ana")
        bridge.setStepChecked("um", True)
        assert bridge.start() is True
        assert bridge.page == 2  # §10.2.3
        assert spin(application, lambda: bridge.page == 3), "a execução não terminou"
        assert bridge.resultStatus == "success"
        assert "1 etapa(s)" in bridge.resultMessage
        assert "o valor é Ana" in bridge.logText()
        bridge.shutdown()
        application.processEvents()


def test_run_updates_step_states_and_progress(app) -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        script = Path(folder) / "prog.sh"
        script.write_text(
            "#!/usr/bin/env bash\n#@runtime 1\n#@name Progresso\n"
            "#@step a\na() { echo a; }\n"
            "#@step b\nb() { echo b; }\n",
            encoding="utf-8",
        )
        application, engine, _roots = create_engine(script)
        bridge = engine.rootContext().contextProperty("bridge")
        bridge.setStepChecked("b", True)
        bridge.start()
        assert spin(application, lambda: bridge.resultStatus == "success")
        assert bridge.overallProgress == 1.0
        statuses = {}
        for row in range(bridge.steps.rowCount()):
            index = bridge.steps.index(row, 0)
            statuses[bridge.steps.data(index, bridge.steps.StepId)] = (
                bridge.steps.data(index, bridge.steps.Status)
            )
        assert statuses == {"a": StepState.SUCCESS.value, "b": StepState.SUCCESS.value}
        assert bridge.canRetry is False
        bridge.shutdown()
        application.processEvents()


def test_prompt_is_answered_through_bridge(app) -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        script = Path(folder) / "prompt.sh"
        script.write_text(
            "#!/usr/bin/env bash\n#@runtime 1\n#@name Prompt\n"
            "#@step perguntar\n"
            'perguntar() { rt_confirm "Continuar?" n && echo "SIM" || echo "NAO"; }\n',
            encoding="utf-8",
        )
        application, engine, _roots = create_engine(script)
        bridge = engine.rootContext().contextProperty("bridge")
        seen: list[tuple] = []
        pending: list[str] = []

        def on_prompt(rid, kind, text, label, default, choices, multi, secret):  # noqa: ANN001
            seen.append((kind, text, default))
            pending.append(rid)
            bridge.answer(rid, True)

        bridge.promptRequested.connect(on_prompt)
        bridge.start()
        assert spin(application, lambda: bridge.resultStatus == "success")
        assert seen == [("confirm", "Continuar?", False)]
        assert "SIM" in bridge.logText()
        assert not pending[0] == ""
        bridge.shutdown()
        application.processEvents()


def test_failures_show_result_and_allow_retry(app) -> None:
    application, _engine, _roots = create_engine(FAILING)
    bridge = _engine.rootContext().contextProperty("bridge")
    bridge.setStepChecked("boom", True)
    bridge.setStepChecked("after_boom", True)
    bridge.start()
    assert spin(application, lambda: bridge.resultStatus == "failed")
    assert bridge.page == 3
    assert "boom" in bridge.resultMessage
    assert bridge.canRetry is True
    assert bridge.logText().count("falhando de propósito") == 1
    failed_before = set(bridge._steps_model.failed_ids())
    assert failed_before == {"boom"}
    bridge.retryFailed()  # só os que falharam voltam; o resto sai da seleção
    assert set(bridge._steps_model.checked_ids()) == failed_before
    assert spin(application, lambda: bridge.resultStatus == "failed")
    bridge.shutdown()
    application.processEvents()


def test_cancel_marks_cancelled(app, tmp_path: Path) -> None:
    """§7.4 — cancelar durante a execução encerra o step em `cancelled`.

    O script tem um único step que dorme: o cancelamento só é determinístico
    depois que o step entrou em "running" (é quando existe processo para
    matar). Cancelar logo após `start()` disputava com um `boom` que falha em
    milissegundos, e o teste virava uma moeda — o `cancelled` só aparecia por
    acaso, não por causa do cancel.
    """
    script = tmp_path / "cancel.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Cancelamento\n"
        "#@step slow\nslow() { sleep 30; }\n",
        encoding="utf-8",
    )
    application, engine, _roots = create_engine(script)
    bridge = engine.rootContext().contextProperty("bridge")

    states: list[tuple[str, str]] = []
    bridge.stepStateChanged.connect(lambda step_id, status: states.append((step_id, status)))

    assert bridge.start() is True
    assert spin(application, lambda: bridge.page == 2)
    assert spin(application, lambda: ("slow", "running") in states), states

    bridge.cancel()
    assert spin(application, lambda: bridge.resultStatus == "cancelled", timeout=30)
    assert bridge.resultMessage.startswith("Execução cancelada")
    bridge.shutdown()
    application.processEvents()


def test_dev_mode_shows_path_and_sha(gui) -> None:
    _app, _engine, _roots, bridge = gui
    assert bridge.scriptPath.endswith("gui.sh")
    assert len(bridge.scriptSha) == 64


def test_precheck_reports_missing_requirements(app, tmp_path: Path) -> None:
    script = tmp_path / "req.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Req\n#@requires comando_inexistente_xyz\n"
        "#@step ola\nola() { echo oi; }\n",
        encoding="utf-8",
    )
    application, engine, _roots = create_engine(script)
    bridge = engine.rootContext().contextProperty("bridge")
    bridge.setStepChecked("ola", True)
    assert any("comando_inexistente_xyz" in item for item in bridge.precheckProblems)
    assert bridge.start() is False  # §7.5 — não inicia nada
    bridge.shutdown()
    application.processEvents()


def test_run_steps_lists_only_checked(gui) -> None:
    """Execução/resultado escondem as etapas não selecionadas (§10.2)."""
    _app, _engine, _roots, bridge = gui
    assert bridge.runSteps.rowCount() == 3
    assert bridge.setStepChecked("terceiro", False) is True
    assert bridge.runSteps.rowCount() == 2
    assert bridge.steps.rowCount() == 3  # seleção continua listando tudo


def test_run_crash_goes_to_result(gui) -> None:
    """Crash do executor vai ao resultado como falha, não à seleção."""
    from rt.gui.bridge import PAGE_RESULT, _RunCrashed

    _app, _engine, _roots, bridge = gui
    bridge._apply(_RunCrashed("falha interna na execução: boom"))
    assert bridge.running is False
    assert bridge.page == PAGE_RESULT
    assert bridge.resultStatus == "failed"
    assert "boom" in bridge.resultMessage


def test_precheck_problems_updates_on_option_change(app, tmp_path: Path) -> None:
    """precheckProblems é recalculado quando seleção/opções mudam (§7.5)."""
    script = tmp_path / "req2.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Req2\n#@requires comando_inexistente_xyz\n"
        "#@step ola\nola() { echo oi; }\n",
        encoding="utf-8",
    )
    application, engine, _roots = create_engine(script)
    bridge = engine.rootContext().contextProperty("bridge")
    try:
        missing = "comando obrigatório ausente no PATH: comando_inexistente_xyz"
        assert bridge.precheckProblems == [missing]
        assert bridge.precheckProblems == [missing]  # leitura repetida: estável
        bridge.setStepChecked("ola", False)
        assert bridge.precheckProblems == [missing, "nenhum step selecionado"]
    finally:
        bridge.shutdown()
        application.processEvents()


def test_shutdown_is_idempotent_and_fast(gui) -> None:
    """Fechar duas vezes não trava nem repete (§7.4)."""
    _app, _engine, _roots, bridge = gui
    bridge.shutdown()
    bridge.shutdown()
    assert bridge._shutdown_done is True


def test_start_rolls_back_when_executor_fails(app, tmp_path: Path, monkeypatch) -> None:
    """Se o Executor falhar, a GUI não fica presa em Executando."""
    import rt.gui.bridge as bridge_module

    script = tmp_path / "boom.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Boom\n#@step ola\nola() { echo oi; }\n",
        encoding="utf-8",
    )
    application, engine, _roots = create_engine(script)
    bridge = engine.rootContext().contextProperty("bridge")
    try:
        bridge.goToPage(bridge_module.PAGE_SELECT)
        bridge.setStepChecked("ola", True)

        def _boom(*args: object, **kwargs: object) -> object:
            raise OSError("sem executor")

        monkeypatch.setattr(bridge_module, "Executor", _boom)
        assert bridge.start() is False
        assert bridge.running is False
        assert bridge.page == bridge_module.PAGE_SELECT
    finally:
        bridge.shutdown()
        application.processEvents()


def test_root_steps_are_flagged_without_asking_privileges(app) -> None:
    application, engine, _roots = create_engine(DEV_SETUP)
    bridge = engine.rootContext().contextProperty("bridge")
    assert "Atualizar índice de pacotes" in bridge.rootSteps
    assert bridge.precheckProblems == []  # sem pkexec (§9.2 desligado)
    bridge.shutdown()
    application.processEvents()


def test_save_log(app, tmp_path: Path) -> None:
    application, engine, _roots = create_engine(DEV_SETUP)
    bridge = answer_prompts(engine.rootContext().contextProperty("bridge"), True)
    bridge.setOption("user_name", "Ana")
    bridge.setStepChecked("install_tools", True)
    bridge.setStepChecked("config_git", True)
    bridge.start()
    assert spin(application, lambda: bridge.resultStatus in ("success", "failed"))
    target = tmp_path / "run.log"
    assert bridge.saveLog(str(target)) is True
    content = target.read_text(encoding="utf-8")
    assert "sha256=" in content
    assert content.count("sha256=") == 1  # salvar 2x no mesmo arquivo não duplica
    assert bridge.saveLog(str(target)) is True
    assert target.read_text(encoding="utf-8").count("sha256=") == 1
    assert "[config_git]" in content or "[update_index]" in content  # formato de text()
    bridge.shutdown()
    application.processEvents()


def test_quit_is_safe_without_run(gui) -> None:
    _app, _engine, _roots, bridge = gui
    assert QCoreApplication.instance() is not None
    bridge.shutdown()


# -- Fase 4: só Kirigami (§10.1, §3 regra 5) --------------------------------
def test_facade_declares_its_api() -> None:
    """Os tipos do qmldir precisam existir como arquivo (§3 regra 5)."""
    folder = qml_dir() / "kirigami" / "BashRT"
    declared = {
        line.split()[0]
        for line in (folder / "qmldir").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#") and not line.startswith("module")
    }
    assert len(declared) > 0
    for name in sorted(declared):
        assert (folder / f"{name}.qml").is_file(), name


def test_pages_only_use_facades() -> None:
    """§3 regra 5 — as páginas não podem depender de um toolkit específico."""
    import re

    for page in (qml_dir() / "pages").glob("*.qml"):
        source = page.read_text(encoding="utf-8")
        assert "import BashRT" in source, page.name
        controls = set(re.findall(r"^\s*(\w+)\s*\{", source, re.MULTILINE))
        forbidden = controls & {
            "Button", "TextField", "TextArea", "TextEdit", "CheckBox", "RadioButton",
            "ComboBox", "Switch", "Slider", "ProgressBar", "ScrollView",
            "Dialog", "Page", "ToolButton", "ApplicationWindow", "AbstractCard",
        }
        assert not forbidden, f"{page.name} usa {sorted(forbidden)} diretamente"


def test_runtime_uses_kirigami(gui) -> None:
    _app, _engine, _roots, bridge = gui
    assert bridge.guiKit == "kirigami"


def test_missing_kirigami_fails_loudly(app, tmp_path: Path, monkeypatch) -> None:
    """Sem Kirigami no sistema, erro alto com diagnóstico (§10.1)."""
    script = tmp_path / "kit.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Kit\n#@step ola\nola() { echo oi; }\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("rt.gui.app.kirigami_available", lambda *a, **k: False)
    with pytest.raises(RuntimeError, match="Kirigami indisponível"):
        create_engine(script)


def test_kirigami_works_end_to_end(app, tmp_path: Path) -> None:
    script = tmp_path / "kit2.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Kit2\n"
        "#@step ola\nola() { echo \"funciona\"; }\n",
        encoding="utf-8",
    )
    application, engine, roots = create_engine(script)
    bridge = engine.rootContext().contextProperty("bridge")
    try:
        assert bridge.guiKit == "kirigami"
        bridge.setStepChecked("ola", True)
        bridge.start()
        assert spin(application, lambda: bridge.resultStatus == "success")
        assert "funciona" in bridge.logText()
    finally:
        bridge.shutdown()
        application.processEvents()


def test_kirigami_facade_is_syntactically_valid(app) -> None:
    """Sem Kirigami instalado não dá para instanciar, mas o QML precisa compilar."""
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    from rt.gui.app import qml_dir

    folder = qml_dir() / "kirigami" / "BashRT"
    engine = QQmlEngine()
    engine.addImportPath(str(qml_dir() / "kirigami"))
    broken: list[str] = []
    for qml in sorted(folder.glob("*.qml")):
        component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml)))
        errors = [error.toString() for error in component.errors()]
        # O único erro aceitável é a ausência do Kirigami nesta máquina.
        real = [
            error
            for error in errors
            if "org.kde.kirigami" not in error and "is not a type" not in error
            and "is not installed" not in error and "Required property" not in error
        ]
        if real:
            broken.append(f"{qml.name}: {real[0]}")
    assert not broken, "\n".join(broken)


def test_every_facade_instantiates(app, tmp_path: Path) -> None:
    """Nenhuma fachada pode falhar ao ser instanciada (§3 regra 5).

    Erros de import faltando (ex.: usar Layout.* sem importar QtQuick.Layouts)
    só aparecem em runtime — por isso este teste cria cada tipo de verdade.
    """
    from PySide6.QtQml import QQmlComponent

    from rt.gui.app import qml_dir

    script = tmp_path / "smoke.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Smoke\n#@step ola\nola() { :; }\n",
        encoding="utf-8",
    )
    application, _engine, _roots = create_engine(script)
    assert len(_engine.rootObjects()) == 1
    context = _engine.rootContext()
    bridge = context.contextProperty("bridge")
    theme = context.contextProperty("theme")
    folder = qml_dir() / "kirigami" / "BashRT"
    declared = [
        line.split()[0]
        for line in (folder / "qmldir").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#") and not line.startswith("module")
    ]
    path = tmp_path / "smoke_all.qml"
    path.write_text(_smoke_qml([name for name in declared if name != "Theme"]), encoding="utf-8")
    component = QQmlComponent(_engine, QUrl.fromLocalFile(str(path)))
    obj = component.create()
    assert obj is not None, [error.toString() for error in component.errors()]
    del obj
    try:
        pass
    finally:
        bridge.shutdown()
        application.processEvents()
        del theme


def test_confirm_dialog_answers_no_without_cancelling(app, tmp_path: Path) -> None:
    """§8.5 — `rt_confirm` precisa de Sim, **Não** e Cancelar.

    Regressão: o diálogo tinha só "Confirmar" e "Cancelar", então responder
    "não" era impossível e o "Cancelar" virava o único caminho. "Não" tem de
    mandar o valor `false` (o script recebe "no" e segue), enquanto "Cancelar"
    continua mandando a sentinela de cancelamento.
    """
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    from rt.core.parser import parse_script
    from rt.core.ui import CANCEL_SENTINEL
    from rt.gui.app import _create_theme, kirigami_available, qml_dir
    from rt.gui.bridge import Bridge

    if not kirigami_available():
        pytest.skip("sem Kirigami nesta máquina")

    script = tmp_path / "confirm.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name C\n#@step a\na() { :; }\n",
        encoding="utf-8",
    )
    bridge = Bridge(parse_script(script))
    engine = QQmlEngine()
    engine.addImportPath(str(qml_dir() / "kirigami"))
    engine.addImportPath(str(qml_dir()))
    theme = _create_theme(engine, "kirigami")
    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("bridge", bridge)
    bridge.setParent(engine)
    theme.setParent(engine)

    component = QQmlComponent(
        engine, QUrl.fromLocalFile(str(qml_dir() / "kirigami" / "BashRT" / "PromptDialog.qml"))
    )
    dialog = component.create()
    assert dialog is not None, [error.toString() for error in component.errors()]

    dialog.setProperty("requestId", "r1")
    dialog.setProperty("kind", "confirm")
    dialog.setProperty("promptText", "Continuar?")
    assert dialog.property("acceptText") == "Sim"
    assert dialog.property("refuseText") == "Não"
    assert dialog.property("rejectText") == "Cancelar"
    assert dialog.property("refuseVisible") is True

    # o botão do default do script é o destacado
    dialog.setProperty("promptDefault", False)
    assert dialog.property("refuseVariant") == "primary"
    assert dialog.property("acceptVariant") == "default"
    dialog.setProperty("promptDefault", True)
    assert dialog.property("acceptVariant") == "primary"
    assert dialog.property("refuseVariant") == "default"

    # "Não" existe fora do confirm
    dialog.setProperty("kind", "input")
    assert dialog.property("refuseVisible") is False

    def button(label: str):
        """Acha um botão do rodapé pelo texto (o rodapé é um RowLayout)."""
        from PySide6.QtQuick import QQuickItem

        found: list = []

        def walk(item: object, depth: int = 0) -> None:
            if depth > 10 or not isinstance(item, QQuickItem):
                return
            try:
                if item.property("text") == label:
                    found.append(item)
            except Exception:  # noqa: BLE001
                pass
            for child in item.childItems():
                walk(child, depth + 1)

        walk(dialog.property("footer"))
        assert found, f"não achei o botão {label!r}"
        return found[0]

    seen: list = []
    bridge.ui.resolve = lambda request_id, value: seen.append((request_id, value))

    dialog.setProperty("kind", "confirm")
    dialog.setProperty("promptDefault", False)
    button("Não").clicked.emit()
    app.processEvents()
    assert seen == [("r1", False)], "Não tem de responder false, não cancelar"

    seen.clear()
    button("Cancelar").clicked.emit()
    app.processEvents()
    assert seen == [("r1", CANCEL_SENTINEL)]

    seen.clear()
    button("Sim").clicked.emit()
    app.processEvents()
    assert seen == [("r1", True)]

    bridge.shutdown()
    dialog.deleteLater()
    theme.deleteLater()


def test_prompt_choice_delegates_show_text(app, tmp_path: Path) -> None:
    """rt_choice mostra as opções em RadioButton exclusivo; rt_multi em CheckBox."""
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    from rt.core.parser import parse_script
    from rt.gui.app import _create_theme, kirigami_available, qml_dir
    from rt.gui.bridge import Bridge

    kit = "kirigami"
    if not kirigami_available():
        pytest.skip("sem Kirigami nesta máquina")

    script = tmp_path / "choice.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name C\n#@step a\na() { :; }\n",
        encoding="utf-8",
    )
    bridge = Bridge(parse_script(script))
    engine = QQmlEngine()
    engine.addImportPath(str(qml_dir() / kit))
    theme = _create_theme(engine, kit)
    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("bridge", bridge)
    bridge.setParent(engine)
    theme.setParent(engine)
    component = QQmlComponent(
        engine, QUrl.fromLocalFile(str(qml_dir() / kit / "BashRT" / "PromptDialog.qml"))
    )
    dialog = component.create()
    assert dialog is not None, [error.toString() for error in component.errors()]
    dialog.setProperty("kind", "choice")
    dialog.setProperty("promptChoices", ["vim", "nano", "micro"])

    def controls() -> list:
        found: list = []

        def walk(item: object, depth: int = 0) -> None:
            if depth > 20:
                return
            if isinstance(item, QQuickItem):
                classname = item.metaObject().className()
                if "RadioButton_QMLTYPE" in classname or "CheckBox_QMLTYPE" in classname:
                    found.append(item)
                children = list(item.childItems())
                try:
                    content = item.property("contentItem")
                except Exception:  # noqa: BLE001
                    content = None
                if isinstance(content, QQuickItem):
                    children.append(content)
            else:
                # Dialog/Popup não é QQuickItem: entra pelo contentItem
                try:
                    content = item.property("contentItem")  # type: ignore[union-attr]
                except Exception:  # noqa: BLE001
                    return
                children = [content] if isinstance(content, QQuickItem) else []
            for child in children:
                walk(child, depth + 1)

        walk(dialog)
        return found

    assert spin(app, lambda: len(controls()) == 3)
    radios = controls()
    assert all("RadioButton_QMLTYPE" in item.metaObject().className() for item in radios)
    assert [item.property("text") for item in radios] == ["vim", "nano", "micro"]

    dialog.setProperty("promptMulti", True)
    assert spin(
        app,
        lambda: len(controls()) == 3
        and all("CheckBox_QMLTYPE" in item.metaObject().className() for item in controls()),
    )
    assert [item.property("text") for item in controls()] == ["vim", "nano", "micro"]


def test_resolve_consumes_pending(app) -> None:
    """Resposta repetida para o mesmo id é ignorada (§8.5)."""
    import threading

    from rt.core.ui import Prompt
    from rt.gui.ui_qt import QtUi

    ui = QtUi()
    prompt = Prompt(id="r1", kind="confirm", text="?", default=True)
    answers: list = []
    worker = threading.Thread(target=lambda: answers.append(ui.ask(prompt)), daemon=True)
    worker.start()
    assert spin(app, lambda: ui.pending_count() == 1)
    ui.resolve("r1", True)
    ui.resolve("r1", False)  # repetida: não pode sobrescrever nem recontar
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert len(answers) == 1 and answers[0].accepted and answers[0].value is True
    assert ui.pending_count() == 0


def test_choice_empty_value_selects_nothing(app, tmp_path: Path) -> None:
    """Choice sem valor não pode exibir a 1ª opção como selecionada."""
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    from rt.core.parser import parse_script
    from rt.gui.app import _create_theme, kirigami_available, qml_dir
    from rt.gui.bridge import Bridge

    if not kirigami_available():
        pytest.skip("sem Kirigami nesta máquina")

    script = tmp_path / "combo.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Cb\n#@step a\na() { :; }\n",
        encoding="utf-8",
    )
    bridge = Bridge(parse_script(script))
    engine = QQmlEngine()
    engine.addImportPath(str(qml_dir() / "kirigami"))
    theme = _create_theme(engine, "kirigami")
    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("bridge", bridge)
    bridge.setParent(engine)
    theme.setParent(engine)
    component = QQmlComponent(
        engine, QUrl.fromLocalFile(str(qml_dir() / "kirigami" / "BashRT" / "OptionField.qml"))
    )
    _KEEPALIVE.append((engine, bridge, theme, component))
    field = component.create()
    assert field is not None, [error.toString() for error in component.errors()]
    field.setProperty("optId", "editor")
    field.setProperty("type", "choice")
    field.setProperty("label", "Editor")
    field.setProperty("value", "")
    field.setProperty("choices", ["vim", "nano"])

    def combo() -> object:
        found: list = []

        def walk(item: object, depth: int = 0) -> None:
            if depth > 20 or not isinstance(item, QQuickItem):
                return
            if "ComboBox_QMLTYPE" in item.metaObject().className():
                found.append(item)
            for child in item.childItems():
                walk(child, depth + 1)

        walk(field)
        return found[0] if found else None

    assert spin(app, lambda: combo() is not None)
    assert combo().property("currentIndex") == -1
    field.setProperty("value", "nano")
    assert spin(app, lambda: combo().property("currentIndex") == 1)


def test_password_typing_is_not_cleared(app, tmp_path: Path) -> None:
    """Digitar a senha não pode apagar o campo a cada tecla (§4.3)."""
    from PySide6.QtQuick import QQuickItem

    script = tmp_path / "pw.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Pw\n"
        '#@option segredo type=password label="Senha"\n'
        "#@step a\na() { :; }\n",
        encoding="utf-8",
    )
    application, engine, roots = create_engine(script)
    bridge = engine.rootContext().contextProperty("bridge")
    try:
        bridge.goToPage(1)
        assert spin(app, lambda: bridge.page == 1)

        def fields() -> list:
            """O campo de senha é o `Kirigami.PasswordField` (o nativo)."""
            found: list = []

            def inner(item: object, depth: int = 0) -> None:
                if depth > 10 or not isinstance(item, QQuickItem):
                    return
                if "PasswordField_QMLTYPE" in item.metaObject().className():
                    found.append(item)
                    return
                for child in item.childItems():
                    inner(child, depth + 1)

            def walk(item: object, depth: int = 0) -> None:
                if depth > 40 or not isinstance(item, QQuickItem):
                    return
                if "OptionField_QMLTYPE" in item.metaObject().className():
                    try:
                        if item.property("type") == "password":
                            inner(item)
                    except Exception:  # noqa: BLE001
                        pass
                for child in item.childItems():
                    walk(child, depth + 1)

            walk(roots[0].property("contentItem"))
            return found

        assert spin(app, lambda: len(fields()) == 1)
        field = fields()[0]
        # valor inicial propaga com o campo desfocado
        bridge.setOption("segredo", "abc123")
        assert spin(app, lambda: field.property("text") == "abc123")
        # atualização externa com foco: não pode apagar o que está digitado
        field.forceActiveFocus()
        assert spin(app, lambda: field.property("activeFocus") is True)
        bridge.setOption("segredo", "externo")
        for _ in range(20):
            application.processEvents()
        assert bridge.options.values().get("segredo") == "externo"
        assert field.property("text") == "abc123"
    finally:
        bridge.shutdown()
        application.processEvents()


#: Guarda engine/bridge/theme dos componentes isolados: sem referência
#: viva o C++ deleta os itens no meio do teste (shiboken).
_KEEPALIVE: list = []


def _option_field(app, tmp_path: Path, **props: object):
    """Instancia um OptionField isolado com as propriedades dadas (§4.3)."""
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    from rt.core.parser import parse_script
    from rt.gui.app import _create_theme, kirigami_available, qml_dir
    from rt.gui.bridge import Bridge

    if not kirigami_available():
        pytest.skip("sem Kirigami nesta máquina")

    script = tmp_path / "tipos.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Tipos\n#@step a\na() { :; }\n",
        encoding="utf-8",
    )
    bridge = Bridge(parse_script(script))
    engine = QQmlEngine()
    engine.addImportPath(str(qml_dir() / "kirigami"))
    theme = _create_theme(engine, "kirigami")
    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("bridge", bridge)
    bridge.setParent(engine)
    theme.setParent(engine)
    component = QQmlComponent(
        engine, QUrl.fromLocalFile(str(qml_dir() / "kirigami" / "BashRT" / "OptionField.qml"))
    )
    _KEEPALIVE.append((engine, bridge, theme, component))
    field = component.create()
    assert field is not None, [error.toString() for error in component.errors()]
    for key, value in props.items():
        field.setProperty(key, value)
    return field


def _visible_text_fields(field: object) -> list:
    """AppTextFields visíveis dentro do OptionField."""
    from PySide6.QtQuick import QQuickItem

    found: list = []

    def walk(item: object, depth: int = 0) -> None:
        if depth > 20 or not isinstance(item, QQuickItem):
            return
        if "AppTextField_QMLTYPE" in item.metaObject().className() and item.property("visible"):
            found.append(item)
        for child in item.childItems():
            walk(child, depth + 1)

    walk(field)
    return found


def test_option_number_renders_validated_field(app, tmp_path: Path) -> None:
    field = _option_field(app, tmp_path, optId="n", type="number", label="N", value="3")
    assert spin(app, lambda: len(_visible_text_fields(field)) == 1)
    assert _visible_text_fields(field)[0].property("validator") is not None


def test_option_date_time_render_masked_fields(app, tmp_path: Path) -> None:
    field = _option_field(app, tmp_path, optId="d", type="date", label="D", value="2026-12-31")
    assert spin(app, lambda: len(_visible_text_fields(field)) == 1)
    assert _visible_text_fields(field)[0].property("inputMask").startswith("0000-00-00")
    field.setProperty("type", "time")
    assert spin(app, lambda: _visible_text_fields(field)[0].property("inputMask").startswith("00:00"))


def test_option_slider_renders_slider_and_value(app, tmp_path: Path) -> None:
    from PySide6.QtQuick import QQuickItem

    field = _option_field(
        app, tmp_path, optId="v", type="slider", label="V",
        value="50", minimum="0", maximum="100", step="5",
    )

    def sliders() -> list:
        found: list = []

        def walk(item: object, depth: int = 0) -> None:
            if depth > 20 or not isinstance(item, QQuickItem):
                return
            if "Slider" in item.metaObject().className() and item.property("visible"):
                found.append(item)
            for child in item.childItems():
                walk(child, depth + 1)

        walk(field)
        return found

    assert spin(app, lambda: len(sliders()) == 1)
    assert sliders()[0].property("from") == 0
    assert sliders()[0].property("to") == 100
    assert sliders()[0].property("stepSize") == 5


def test_option_file_renders_picker_with_filters(app, tmp_path: Path) -> None:
    from PySide6.QtQuick import QQuickItem

    field = _option_field(
        app, tmp_path, optId="f", type="file", label="F", value="", filters=["*.png"],
    )
    assert spin(app, lambda: len(_visible_text_fields(field)) == 1)

    def no_native_dialog() -> bool:
        # portal XDG (§10.1): sem FileDialog/FolderDialog QML na árvore
        from PySide6.QtCore import QObject

        for item in field.findChildren(QObject):
            cn = item.metaObject().className()
            if "FileDialog" in cn and "Options" not in cn:
                return False
        return True

    assert spin(app, lambda: no_native_dialog())

    def picker_button() -> object:
        from PySide6.QtQuick import QQuickItem

        found: list = []

        def walk(item: object, depth: int = 0) -> None:
            if depth > 20 or not isinstance(item, QQuickItem):
                return
            cn = item.metaObject().className()
            if "AppButton" in cn and item.property("visible") and item.property("text") == "Procurar…":
                found.append(item)
            for child in item.childItems():
                walk(child, depth + 1)

        walk(field)
        return found[0] if found else None

    assert spin(app, lambda: picker_button() is not None)


def test_option_text_renders_textarea(app, tmp_path: Path) -> None:
    from PySide6.QtQuick import QQuickItem

    field = _option_field(app, tmp_path, optId="t", type="text", label="T", value="a\nb")

    def areas() -> list:
        found: list = []

        def walk(item: object, depth: int = 0) -> None:
            if depth > 20 or not isinstance(item, QQuickItem):
                return
            if "TextArea" in item.metaObject().className() and item.property("visible"):
                found.append(item)
            for child in item.childItems():
                walk(child, depth + 1)

        walk(field)
        return found

    assert spin(app, lambda: len(areas()) == 1)


def _prompt_dialog(app, tmp_path: Path, **props: object):
    """Instancia um PromptDialog isolado (sem abrir) com as propriedades dadas."""
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    from rt.core.parser import parse_script
    from rt.gui.app import _create_theme, kirigami_available, qml_dir
    from rt.gui.bridge import Bridge

    if not kirigami_available():
        pytest.skip("sem Kirigami nesta máquina")

    script = tmp_path / "prompt.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name P\n#@step a\na() { :; }\n",
        encoding="utf-8",
    )
    bridge = Bridge(parse_script(script))
    engine = QQmlEngine()
    engine.addImportPath(str(qml_dir() / "kirigami"))
    theme = _create_theme(engine, "kirigami")
    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("bridge", bridge)
    bridge.setParent(engine)
    theme.setParent(engine)
    component = QQmlComponent(
        engine, QUrl.fromLocalFile(str(qml_dir() / "kirigami" / "BashRT" / "PromptDialog.qml"))
    )
    _KEEPALIVE.append((engine, bridge, theme, component))
    dialog = component.create()
    assert dialog is not None, [error.toString() for error in component.errors()]
    for key, value in props.items():
        dialog.setProperty(key, value)
    return dialog


def test_prompt_new_kinds_render_their_fields(app, tmp_path: Path) -> None:
    """Cada kind novo de prompt mostra o controle certo (§8.2).

    Emite `promptRequested` direto no bridge (como o QtUi faria) com
    janela real: popup sem janela lê `visible` sempre falso, então
    instanciar o diálogo isolado não serve para este teste.
    """
    from PySide6.QtCore import QObject
    from PySide6.QtQuick import QQuickItem

    script = tmp_path / "promptkinds.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name P\n#@step a\na() { :; }\n",
        encoding="utf-8",
    )
    application, engine, roots = create_engine(script)
    bridge = engine.rootContext().contextProperty("bridge")
    try:
        window = roots[0]

        def visible(needle: str) -> list:
            found: list = []
            for item in window.findChildren(QObject):
                if not isinstance(item, QQuickItem):
                    continue
                if needle in item.metaObject().className() and item.property("visible"):
                    found.append(item)
            return found

        def ask(kind: str, **kwargs: object) -> None:
            bridge.promptRequested.emit(
                "r-" + kind,
                kind,
                kwargs.get("text", ""),
                kwargs.get("label", "L"),
                kwargs.get("default", ""),
                kwargs.get("choices", []),
                False,
                False,
                kwargs.get("minimum", ""),
                kwargs.get("maximum", ""),
            )

        ask("number", default="3", minimum="1", maximum="10")
        assert spin(app, lambda: len(visible("AppTextField_QMLTYPE")) == 1)
        assert visible("AppTextField_QMLTYPE")[0].property("validator") is not None

        ask("date")
        assert spin(app, lambda: visible("AppTextField_QMLTYPE")
                   and visible("AppTextField_QMLTYPE")[0].property("inputMask").startswith("0000-00-00"))

        ask("time")
        assert spin(app, lambda: visible("AppTextField_QMLTYPE")
                   and visible("AppTextField_QMLTYPE")[0].property("inputMask").startswith("00:00"))

        ask("file", choices=["*.png"])
        assert spin(app, lambda: len(visible("AppTextField_QMLTYPE")) == 1)

        ask("text")
        assert spin(app, lambda: len(visible("TextArea")) == 1)

        ask("textbox", text="leia isto")
        assert spin(app, lambda: len(visible("ScrollView")) >= 1)
        dialogs = [item for item in window.findChildren(QObject)
                   if "PromptDialog" in item.metaObject().className()]
        assert dialogs
        assert dialogs[0].property("rejectVisible") is False
        assert dialogs[0].property("acceptText") == "OK"
    finally:
        bridge.shutdown()
        application.processEvents()


def test_log_drawer_opens_and_closes(app, tmp_path: Path) -> None:
    """Gaveta de log (§10.2.5): o bridge abre/fecha, a gaveta obedece."""
    from PySide6.QtCore import QObject
    from PySide6.QtQuick import QQuickItem

    script = tmp_path / "drawer.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name D\n#@step a\na() { :; }\n",
        encoding="utf-8",
    )
    application, engine, roots = create_engine(script)
    bridge = engine.rootContext().contextProperty("bridge")
    try:
        window = roots[0]

        def drawer() -> object:
            found = [
                item for item in window.findChildren(QObject)
                if item.metaObject().className().startswith("LogDrawer")
            ]
            return found[0] if found else None

        assert spin(app, lambda: drawer() is not None)
        # a gaveta nasce fechada (o template abre sozinho no
        # completion; o LogDrawer fecha via callLater)
        assert spin(app, lambda: drawer().property("drawerOpen") is False)
        assert bridge.property("logDrawerOpen") is False
        bridge.setProperty("logDrawerOpen", True)
        assert spin(app, lambda: drawer().property("drawerOpen") is True)
        # o LogPanel viaja junto dentro da gaveta
        panels = [
            item for item in drawer().findChildren(QObject)
            if item.metaObject().className().startswith("LogPanel")
        ]
        assert len(panels) == 1
        bridge.setProperty("logDrawerOpen", False)
        assert spin(app, lambda: drawer().property("drawerOpen") is False)
    finally:
        bridge.shutdown()
        application.processEvents()


def test_progresswin_dialog_follows_events(app, tmp_path: Path) -> None:
    """Janela de progresso do script (§8.4): eventos abrem/atualizam/fecham."""
    from PySide6.QtCore import QObject

    from rt.core.events import ProgressWin

    script = tmp_path / "pwin.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name W\n#@step a\na() { :; }\n",
        encoding="utf-8",
    )
    application, engine, roots = create_engine(script)
    bridge = engine.rootContext().contextProperty("bridge")
    try:
        window = roots[0]
        assert bridge.property("progressWinVisible") is False
        bridge._queue.put(ProgressWin("start", 10.0, 100.0, "Copiando"))
        assert spin(app, lambda: bridge.property("progressWinVisible") is True)
        assert bridge.property("progressWinValue") == 10.0
        assert bridge.property("progressWinMaximum") == 100.0
        assert bridge.property("progressWinText") == "Copiando"
        dialogs = [
            item for item in window.findChildren(QObject)
            if item.metaObject().className().startswith("ProgressWinDialog")
        ]
        assert len(dialogs) == 1
        bridge._queue.put(ProgressWin("update", 50.0, 100.0, ""))
        assert spin(app, lambda: bridge.property("progressWinValue") == 50.0)
        assert bridge.property("progressWinText") == "Copiando"
        bridge._queue.put(ProgressWin("done", 0.0, 100.0, ""))
        assert spin(app, lambda: bridge.property("progressWinVisible") is False)
    finally:
        bridge.shutdown()
        application.processEvents()


def test_conditional_option_hides_and_shows(app, tmp_path: Path) -> None:
    """`show_if` esconde/mostra a opção no formulário (§4.3)."""
    from PySide6.QtCore import QObject
    from PySide6.QtQuick import QQuickItem

    script = tmp_path / "cond.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name C\n"
        '#@option modo type=choice label="Modo" choices="a,b" default=a\n'
        '#@option detalhe type=string label="Detalhe" show_if="modo=b"\n'
        "#@step s\ns() { :; }\n",
        encoding="utf-8",
    )
    application, engine, roots = create_engine(script)
    bridge = engine.rootContext().contextProperty("bridge")
    try:
        window = roots[0]
        bridge.goToPage(1)
        assert spin(app, lambda: bridge.page == 1)

        def visible(opt_id: str) -> object:
            # childItems, não findChildren: delegates de Repeater
            # têm pai visual correto mas fora da subárvore QObject,
            # então findChildren nunca os acha
            found = []

            def walk(item: object, depth: int = 0) -> None:
                if depth > 40 or not isinstance(item, QQuickItem):
                    return
                if item.metaObject().className().startswith("OptionField") and item.property(
                    "optId"
                ) == opt_id:
                    found.append(item.property("visible"))
                for child in item.childItems():
                    walk(child, depth + 1)

            walk(window.property("contentItem"))
            return found[0] if found else None

        assert spin(app, lambda: visible("detalhe") is False)
        bridge.setOption("modo", "b")
        assert spin(app, lambda: visible("detalhe") is True)
        bridge.setOption("modo", "a")
        assert spin(app, lambda: visible("detalhe") is False)
    finally:
        bridge.shutdown()
        application.processEvents()


def test_portal_without_bus_fails_gracefully(app, tmp_path: Path, monkeypatch) -> None:
    """Sem session bus, o pick avisa e devolve vazio — sem travar (§10.1)."""
    from PySide6.QtDBus import QDBusConnection

    from rt.core.parser import parse_script
    from rt.gui.bridge import Bridge

    class _DeadBus:
        def isConnected(self) -> bool:
            return False

    monkeypatch.setattr(QDBusConnection, "sessionBus", staticmethod(lambda: _DeadBus()))
    script = tmp_path / "portal.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name P\n#@step a\na() { :; }\n",
        encoding="utf-8",
    )
    bridge = Bridge(parse_script(script))
    picked: list = []
    bridge.filePicked.connect(lambda token, paths: picked.append((token, list(paths))))
    try:
        bridge.pickFolder("opt", "Pasta")
        assert spin(app, lambda: len(picked) == 1)
        assert picked[0] == ("opt", [])
        bridge.pickOpenFile("opt", "Arquivo", False)
        assert spin(app, lambda: len(picked) == 2)
        bridge.pickSaveFile("save-log", "Salvar", "x.log")
        assert spin(app, lambda: len(picked) == 3)
    finally:
        bridge.shutdown()
        app.processEvents()


def test_portal_response_converts_uris(app, tmp_path: Path) -> None:
    """Resposta do portal vira caminhos locais no filePicked (§10.1)."""
    from rt.core.parser import parse_script
    from rt.gui.bridge import Bridge

    script = tmp_path / "portal2.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name P\n#@step a\na() { :; }\n",
        encoding="utf-8",
    )
    bridge = Bridge(parse_script(script))
    picked: list = []
    bridge.filePicked.connect(lambda token, paths: picked.append((token, list(paths))))
    try:
        bridge._portal_token = "opt"
        bridge._on_portal_response(0, {"uris": ["file:///tmp/foto%20x.png", "file:///tmp/b"]})
        assert picked == [("opt", ["/tmp/foto x.png", "/tmp/b"])]
        bridge._portal_token = "opt"
        bridge._on_portal_response(1, {})
        assert picked[-1] == ("opt", [])
    finally:
        bridge.shutdown()
        app.processEvents()


def test_portal_call_failure_is_graceful(app, tmp_path: Path) -> None:
    """Falha na chamada assíncrona ao portal: aviso + vazio, sem travar (§10.1)."""
    from rt.core.parser import parse_script
    from rt.gui.bridge import Bridge

    script = tmp_path / "portal3.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name P\n#@step a\na() { :; }\n",
        encoding="utf-8",
    )
    bridge = Bridge(parse_script(script))
    picked: list = []
    bridge.filePicked.connect(lambda token, paths: picked.append((token, list(paths))))

    class _BadReply:
        def reply(self):
            raise RuntimeError("bus quebrou")

        def deleteLater(self):
            pass

    try:
        bridge._portal_token = "opt"
        bridge._on_portal_call_done(_BadReply())
        assert spin(app, lambda: len(picked) == 1)
        assert picked[0] == ("opt", [])
        assert bridge._portal_token is None
    finally:
        bridge.shutdown()
        app.processEvents()


def test_portal_full_loop_without_ui(app, tmp_path: Path, monkeypatch) -> None:
    """Loop sem UI: erro async + watcher dublado + subscribe real (§10.1).

    Não dá para exportar serviço D-Bus no PySide6 (sem Q_CLASSINFO),
    então: (A) serviço inexistente exercita asyncCall → erro → falha
    graciosa, sem abrir nada; (B) watcher dublado com reply válido
    exercita subscribe (match rule em path falso é aceita no bus),
    roteamento e parsing da resposta.
    """
    from PySide6.QtDBus import QDBusMessage, QDBusObjectPath

    import rt.gui.bridge as bmod
    from rt.core.parser import parse_script
    from rt.gui.bridge import Bridge

    PATH = "/org/test/fakereq9"
    monkeypatch.setattr(bmod, "_portal_service_available", lambda: True)

    class FakeReply:
        def __init__(self, ok: bool) -> None:
            self._ok = ok

        def type(self):  # noqa: ANN204
            return (QDBusMessage.MessageType.ReplyMessage if self._ok
                    else QDBusMessage.MessageType.ErrorMessage)

        def arguments(self):  # noqa: ANN204
            return [QDBusObjectPath(PATH)] if self._ok else []

    class FakeWatcher:
        def __init__(self, reply):  # noqa: ANN204
            self._reply = reply

        def reply(self):  # noqa: ANN204
            return self._reply

        def deleteLater(self):  # noqa: ANN204
            pass

    script = tmp_path / "portal4.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name P\n#@step a\na() { :; }\n",
        encoding="utf-8",
    )
    bridge = Bridge(parse_script(script))
    picked: list = []
    bridge.filePicked.connect(lambda token, paths: picked.append((token, list(paths))))
    try:
        # A: serviço inexistente → asyncCall erra → falha graciosa
        monkeypatch.setattr(bmod, "PORTAL_SERVICE", "org.test.NoSuchService")
        bridge.pickOpenFile("opt", "Escolher", False)
        assert spin(app, lambda: len(picked) == 1)
        assert picked[0] == ("opt", [])
        assert bridge._portal_token is None
        # B: reply válido → assina, token segura, resposta roteia
        bridge._portal_token = "opt"
        bridge._on_portal_call_done(FakeWatcher(FakeReply(True)))
        assert spin(app, lambda: bridge._portal_conn is not None)
        bridge._on_portal_response(0, {"uris": ["file:///tmp/a.png"]})
        assert spin(app, lambda: len(picked) == 2)
        assert picked[1] == ("opt", ["/tmp/a.png"])
        assert bridge._portal_token is None
    finally:
        bridge.shutdown()
        app.processEvents()


def _visible_with_text(field: object, text: str) -> list:
    """Itens visíveis dentro do OptionField cujo `text` é o dado (§4.3 paragraph/link)."""
    from PySide6.QtQuick import QQuickItem

    found: list = []

    def walk(item: object, depth: int = 0) -> None:
        if depth > 20 or not isinstance(item, QQuickItem):
            return
        if item.property("text") == text and item.property("visible"):
            found.append(item)
        for child in item.childItems():
            walk(child, depth + 1)

    walk(field)
    return found


def test_option_paragraph_shows_text_and_no_opt_row(app, tmp_path: Path) -> None:
    field = _option_field(app, tmp_path, optId="p", type="paragraph", label="Texto de aviso")
    assert spin(app, lambda: len(_visible_with_text(field, "Texto de aviso")) == 1)
    assert field.property("isDisplay") is True


def test_option_link_renders_button_with_label(app, tmp_path: Path) -> None:
    field = _option_field(
        app, tmp_path, optId="ajuda", type="link", label="Abrir docs", url="https://example.org",
    )
    # o Button repete o texto no próprio item, no ícone e no rótulo interno
    assert spin(app, lambda: len(_visible_with_text(field, "Abrir docs")) >= 1)
    assert field.property("url") == "https://example.org"


def test_bridge_open_link_accepts_only_http_and_https(app, tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtGui import QDesktopServices

    from rt.core.parser import parse_script
    from rt.gui.bridge import Bridge

    opened: list[str] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    script = tmp_path / "link.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name L\n"
        '#@option ajuda type=link label="Docs" url="https://example.org/docs"\n'
        "#@step s\ns() { :; }\n",
        encoding="utf-8",
    )
    bridge = Bridge(parse_script(script))
    assert bridge.openLink("file:///etc/passwd") is False
    assert bridge.openLink("javascript:alert(1)") is False
    assert opened == []
    assert bridge.openLink("https://example.org/docs") is True
    assert opened == ["https://example.org/docs"]


def test_home_bridge_has_no_script_and_refuses_to_run(app, tmp_path: Path) -> None:
    from rt.gui.bridge import Bridge

    bridge = Bridge()
    assert bridge.hasScript is False
    assert bridge.scriptPath == ""
    assert bridge.stepCount == 0
    assert bridge.start() is False


def test_bridge_loads_a_script_chosen_by_path_or_file_url(app, tmp_path: Path) -> None:
    from rt.gui.bridge import Bridge

    script = tmp_path / "demo.sh"
    script.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name Demo\n#@step a\na() { :; }\n", encoding="utf-8",
    )
    bridge = Bridge()
    changed: list[str] = []
    bridge.hasScriptChanged.connect(lambda: changed.append("has"))
    assert bridge.loadScript(str(script)) is True
    assert bridge.hasScript is True and bridge.scriptName == "Demo"
    assert bridge.stepCount == 1 and bridge.page == 0
    assert changed == ["has"]
    assert bridge.loadScript(script.as_uri()) is True  # o arrastar entrega file://


def test_bridge_load_refuses_wrong_or_broken_files(app, tmp_path: Path) -> None:
    from rt.gui.bridge import Bridge

    bridge = Bridge()
    notes = []
    bridge.notifyRaised.connect(lambda text, level: notes.append((text, level)))
    txt = tmp_path / "notas.txt"
    txt.write_text("x", encoding="utf-8")
    assert bridge.loadScript(str(txt)) is False
    broken = tmp_path / "quebrado.sh"
    broken.write_text("#!/usr/bin/env bash\n#@step a\na() { :; }\n", encoding="utf-8")  # sem #@runtime/#@name
    assert bridge.loadScript(str(broken)) is False
    assert bridge.hasScript is False
    assert [level for _text, level in notes] == ["error", "error"]

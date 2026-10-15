"""Grupos de exibição e ações pelo bridge (SPEC.md §4.8, §4.8.1, §10.2.2), sem QML.

Confere o que a tela consome: ``groupNames`` na ordem de declaração, os proxies
de ``optionsFor``/``stepsFor`` filtrados por grupo, e ``runAction`` com o
resultado devolvido pela thread da ação.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6", reason="GUI exige PySide6")

from PySide6.QtCore import QCoreApplication

from kbash.gui import bridge as bridge_module
from kbash.gui.bridge import load_bridge
from kbash.gui.models import OptionModel, StepListModel

SCRIPT = (
    "#!/usr/bin/env bash\n#@runtime 1\n#@name Limpeza\n#@id limpeza\n"
    '#@option destino type=string label="Destino" default=/tmp group="Destino"\n'
    '#@option nivel type=string label="Nível" default=baixo needs_step=limpar\n'
    "#@step limpar\n#@group Limpeza\nlimpar() { :; }\n"
    "#@step cache\n#@group Cache\ncache() { :; }\n"
    "#@action espaco\n#@group Limpeza\n#@button Ver espaço\n"
    "espaco() { echo \"destino=$OPT_DESTINO nivel=$OPT_NIVEL\"; }\n"
)


@pytest.fixture(scope="module")
def app():
    return QCoreApplication.instance() or QCoreApplication([])


def _bridge(tmp_path: Path, app, text: str = SCRIPT):
    script = tmp_path / "limpeza.kbash"
    script.write_text(text, encoding="utf-8")
    return load_bridge(script)


def _names(model) -> list[str]:
    return [model.data(model.index(row, 0), StepListModel.StepId) for row in range(model.rowCount())]


def test_group_names_follow_declaration_order(app, tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, app)
    assert list(bridge.groupNames) == ["Destino", "Limpeza", "Cache"]


def test_options_for_group_hide_step_owned_options(app, tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, app)
    proxy = bridge.optionsFor("Destino")
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 0), OptionModel.OptId) == "destino"
    # nivel pertence ao step "limpar": não aparece como opção geral de nenhum grupo
    assert bridge.optionsFor("Limpeza").rowCount() == 0


def test_steps_for_group_are_filtered(app, tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, app)
    assert _names(bridge.stepsFor("Limpeza")) == ["limpar"]
    assert _names(bridge.stepsFor("Cache")) == ["cache"]


def test_proxies_are_reused_between_calls(app, tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, app)
    assert bridge.stepsFor("Cache") is bridge.stepsFor("Cache")


def test_actions_are_listed_with_group_and_idle_state(app, tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, app)
    [action] = bridge.actions
    assert action["id"] == "espaco"
    assert action["button"] == "Ver espaço"
    assert action["group"] == "Limpeza"
    assert action["running"] is False and action["status"] == ""


def _wait_for(predicate, seconds: float = 10.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("tempo esgotado esperando a ação terminar")


def test_run_action_delivers_output_with_current_option_values(app, tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, app)
    bridge.setOption("destino", "/var/alvo")
    bridge.runAction("espaco")
    _wait_for(lambda: bridge.actions[0]["status"] != "")
    state = bridge.actions[0]
    assert state["status"] == "ok"
    assert "destino=/var/alvo" in state["output"]
    assert state["running"] is False


def test_run_action_refuses_while_another_runs(app, tmp_path: Path, monkeypatch) -> None:
    bridge = _bridge(tmp_path, app)
    started: list[str] = []
    original = bridge_module.run_action  # antes do patch: evita recursão no próprio patch

    def slow_run(*args, **kwargs):
        started.append("x")
        time.sleep(0.3)
        return original(*args, **kwargs)

    monkeypatch.setattr(bridge_module, "run_action", slow_run)
    bridge.runAction("espaco")
    bridge.runAction("espaco")  # segundo clique enquanto roda: ignorado
    _wait_for(lambda: bridge.actions[0]["status"] != "")
    assert started == ["x"]


def test_run_action_root_denied_reports_error(app, tmp_path: Path, monkeypatch) -> None:
    text = SCRIPT.replace("#@action espaco\n", "#@action espaco\n#@root true\n")
    bridge = _bridge(tmp_path, app, text)
    monkeypatch.setattr(bridge_module, "pkexec_authorize", lambda: False)
    bridge.runAction("espaco")
    _wait_for(lambda: bridge.actions[0]["status"] != "")
    assert bridge.actions[0]["status"] == "error"
    assert "negada" in bridge.actions[0]["output"]


def test_script_without_groups_has_single_untitled_block(app, tmp_path: Path) -> None:
    bridge = _bridge(
        tmp_path,
        app,
        "#!/usr/bin/env bash\n#@runtime 1\n#@name S\n#@id s\n#@step a\na() { :; }\n",
    )
    assert list(bridge.groupNames) == [""]

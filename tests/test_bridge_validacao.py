"""``bridge.validateAnswer``: o QML consulta a mesma regra do terminal antes de aceitar (bug 10)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6", reason="GUI exige PySide6")

from kbash.gui import bridge as bridge_module

SCRIPT = (
    "#!/usr/bin/env bash\n#@runtime 1\n#@name V\n#@id validacao\n"
    "#@step a\na() { :; }\n"
)


@pytest.fixture(scope="module")
def app(qt_core_app):
    return qt_core_app


def _bridge(tmp_path: Path, app):
    script = tmp_path / "validacao.kbash"
    script.write_text(SCRIPT, encoding="utf-8")
    return bridge_module.load_bridge(script)


def test_numero_fora_da_faixa_devolve_a_mensagem_do_terminal(app, tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, app)
    assert bridge.validateAnswer("number", "5", "1", "10") == ""
    assert bridge.validateAnswer("number", "11", "1", "10") == "máximo: 10"
    assert bridge.validateAnswer("number", "0", "1", "10") == "mínimo: 1"


def test_data_impossivel_e_recusada_no_qml(app, tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, app)
    assert bridge.validateAnswer("date", "2026-02-28", "", "") == ""
    assert bridge.validateAnswer("date", "2026-02-30", "", "") == "formato inválido (use AAAA-MM-DD)"


def test_hora_fora_do_dia_e_recusada_no_qml(app, tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, app)
    assert bridge.validateAnswer("time", "23:59", "", "") == ""
    assert bridge.validateAnswer("time", "24:00", "", "") == "formato inválido (use HH:MM)"


def test_tipo_sem_validacao_nao_derruba_o_bridge(app, tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, app)
    assert bridge.validateAnswer("cor", "azul", "", "") == "tipo de resposta desconhecido"

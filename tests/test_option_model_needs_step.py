"""OptionModel (gui/models.py) com opções ligadas a step — sem precisar do Kirigami."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6", reason="GUI exige PySide6")

from PySide6.QtCore import QCoreApplication

from kbash.core.parser import parse_script
from kbash.core.planner import default_options
from kbash.gui.models import OptionModel

SCRIPT = (
    "#!/usr/bin/env bash\n#@runtime 1\n#@name T\n"
    '#@option geral type=string label="Geral" default=x\n'
    '#@option compressao type=choice label="Compressão" choices="lz4,zstd" default=lz4 needs_step=zram_passo\n'
    "#@step zram_passo\nzram_passo() { :; }\n"
)


@pytest.fixture(scope="module")
def app():
    return QCoreApplication.instance() or QCoreApplication([])


def _rows(model: OptionModel) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for row in range(model.rowCount()):
        index = model.index(row, 0)
        out[model.data(index, OptionModel.OptId)] = {
            "visible": model.data(index, OptionModel.Visible),
            "owner": model.data(index, OptionModel.Owner),
        }
    return out


def test_step_option_visibility_follows_selection(app, tmp_path: Path) -> None:
    path = tmp_path / "m.kbash"
    path.write_text(SCRIPT, encoding="utf-8")
    script = parse_script(path)
    model = OptionModel()
    model.load(script, default_options(script))

    rows = _rows(model)
    assert rows["geral"] == {"visible": True, "owner": ""}
    assert rows["compressao"] == {"visible": False, "owner": "zram_passo"}

    model.set_selected({"zram_passo"})
    assert _rows(model)["compressao"]["visible"] is True

    model.set_selected(set())
    assert _rows(model)["compressao"]["visible"] is False


def test_general_count_excludes_step_options(app, tmp_path: Path) -> None:
    """Regressão: com todas as opções ligadas a step, o cartão Opções ficava vazio
    mas dizia "Preencha antes de executar"."""
    path = tmp_path / "g.kbash"
    path.write_text(SCRIPT, encoding="utf-8")
    script = parse_script(path)
    model = OptionModel()
    assert model.general_count() == 0
    model.load(script, default_options(script))
    assert model.general_count() == 1  # só `geral`; `compressao` é de step

    only_step = tmp_path / "s.kbash"
    only_step.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name S\n"
        '#@option c type=choice label="C" choices="a,b" default=a needs_step=passo\n'
        "#@step passo\npasso() { :; }\n",
        encoding="utf-8",
    )
    script2 = parse_script(only_step)
    model.load(script2, default_options(script2))
    assert model.general_count() == 0
    assert model.rowCount() == 1


def test_visibility_signals_only_rows_that_change(app, tmp_path: Path) -> None:
    """Regressão de desempenho: cada digitação emitia `Visible` para todas as
    opções e cada linha de step relia isso pelo Python."""
    path = tmp_path / "v.kbash"
    path.write_text(SCRIPT, encoding="utf-8")
    script = parse_script(path)
    model = OptionModel()
    model.load(script, default_options(script))

    emitted: list[tuple[int, list[int]]] = []

    def record(top, _bottom, roles) -> None:
        if OptionModel.Visible in roles:
            emitted.append((top.row(), list(roles)))

    model.dataChanged.connect(record)
    model.set_value("geral", "outro")  # não muda visibilidade de ninguém
    assert emitted == []

    model.set_selected({"zram_passo"})  # só `compressao` (linha 1) muda
    assert emitted == [(1, [OptionModel.Visible])]

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

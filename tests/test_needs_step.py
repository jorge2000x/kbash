"""Opções ligadas a um step (`needs_step`, SPEC.md §4.3 e §6).

A opção só aparece, só é validada e só vale quando o step dono está
selecionado (efetivamente, incluindo dependências adicionadas automaticamente).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kbash.core.errors import ParseError, ValidationError
from kbash.core.parser import parse_script, parse_text
from kbash.core.planner import build_plan, option_errors, option_visible

HDR = "#!/usr/bin/env bash\n#@runtime 1\n#@name T\n"

SCRIPT = HDR + (
    '#@option compressao type=choice label="Compressão" choices="lz4,zstd" default=lz4 needs_step=zram_passo\n'
    '#@option chave type=string label="Chave" required=true needs_step=zram_passo\n'
    '#@option global type=string label="Global" default=x\n'
    "#@step zram_passo\nzram_passo() { :; }\n"
    "#@step base\nbase() { :; }\n"
    "#@step topo\n#@depends base\n#@default off\ntopo() { :; }\n"
    "#@option sabor type=choice label=\"Sabor\" choices=\"doce,salgado\" default=doce needs_step=base\n"
)


def _script(tmp_path: Path, text: str = SCRIPT) -> Path:
    path = tmp_path / "ns.kbash"
    path.write_text(text, encoding="utf-8")
    return path


def test_needs_step_is_parsed(tmp_path: Path) -> None:
    script = parse_script(_script(tmp_path))
    assert script.option("compressao").needs_step == "zram_passo"
    assert script.option("global").needs_step is None


def test_needs_step_must_reference_an_existing_step() -> None:
    text = HDR + '#@option x type=string label="X" needs_step=nao_existe\n#@step a\na() { :; }\n'
    with pytest.raises((ParseError, ValidationError), match="step inexistente"):
        parse_text(text)


def test_option_hidden_until_its_step_is_selected(tmp_path: Path) -> None:
    script = parse_script(_script(tmp_path))
    compressao = script.option("compressao")
    assert option_visible(script, {}, compressao, {"zram_passo"}) is True
    assert option_visible(script, {}, compressao, {"base"}) is False
    assert option_visible(script, {}, compressao, None) is False


def test_hidden_required_option_does_not_block(tmp_path: Path) -> None:
    script = parse_script(_script(tmp_path))
    assert "chave" not in option_errors(script, {}, {"base"})
    assert "chave" in option_errors(script, {}, {"zram_passo"})


def test_hidden_option_falls_back_to_default(tmp_path: Path) -> None:
    script = parse_script(_script(tmp_path))
    plan = build_plan(script, ["base"], {"compressao": "zstd", "chave": "k"}, home=str(tmp_path))
    assert plan.options["compressao"] == "lz4"  # zram_passo não selecionado: default
    assert plan.options["sabor"] == "doce"


def test_selected_option_takes_the_user_value(tmp_path: Path) -> None:
    script = parse_script(_script(tmp_path))
    plan = build_plan(script, ["zram_passo"], {"compressao": "zstd", "chave": "k"}, home=str(tmp_path))
    assert plan.options["compressao"] == "zstd"


def test_dependency_added_automatically_brings_its_options(tmp_path: Path) -> None:
    """Selecionar `topo` puxa `base` (dependência): a opção de `base` passa a valer."""
    script = parse_script(_script(tmp_path))
    plan = build_plan(script, ["topo"], {"sabor": "salgado"}, home=str(tmp_path))
    assert "base" in plan.selected and "base" in plan.auto_added
    assert plan.options["sabor"] == "salgado"


def test_invalid_value_in_selected_step_is_reported(tmp_path: Path) -> None:
    script = parse_script(_script(tmp_path))
    with pytest.raises(ValidationError, match="compressao"):
        build_plan(script, ["zram_passo"], {"compressao": "gzip", "chave": "k"}, home=str(tmp_path))


def test_invalid_value_in_unselected_step_is_ignored(tmp_path: Path) -> None:
    script = parse_script(_script(tmp_path))
    plan = build_plan(script, ["base"], {"compressao": "gzip"}, home=str(tmp_path))
    assert plan.options["compressao"] == "lz4"

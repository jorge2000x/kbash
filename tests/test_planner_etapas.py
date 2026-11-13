"""Etapas do planner como funções separadas: visibilidade, normalização e validação.

`build_plan` compõe: resolve_steps → resolve_visibility → (erros) → normalize_options.
Cada etapa é testada sozinha; o resultado do plano não muda.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from kbash.core.errors import ValidationError
from kbash.core.parser import parse_text
from kbash.core.planner import (
    build_plan,
    normalize_options,
    resolve_visibility,
    validate_options,
)

HEADER = "#!/bin/bash\n#@runtime 1\n#@name X\n"
CADEIA = (
    "#@option r\n#@type text\n#@default sim\n"
    "#@option m\n#@type text\n#@show_if r=sim\n"
    "#@option f\n#@type text\n#@show_if m=x\n"
    "#@option pasta\n#@type path\n#@default ~/x\n"
    "#@step s\ns() { :; }\n"
)


def _script(corpo: str = CADEIA):
    return parse_text(HEADER + corpo, Path("/tmp/x.sh")).script


def test_resolve_visibility_resets_hidden_options_to_default() -> None:
    script = _script()
    visivel = resolve_visibility(script, {"r": "nao", "m": "x", "f": "segredo"}, None)
    assert visivel["m"] == ""
    assert visivel["f"] == ""
    assert visivel["r"] == "nao"


def test_resolve_visibility_keeps_visible_values() -> None:
    script = _script()
    visivel = resolve_visibility(script, {"r": "sim", "m": "x", "f": "ok"}, None)
    assert visivel["m"] == "x"
    assert visivel["f"] == "ok"


@given(st.sampled_from(["sim", "nao", ""]), st.sampled_from(["x", "y", ""]), st.text(max_size=8))
def test_resolve_visibility_is_idempotent(r: str, m: str, f: str) -> None:
    script = _script()
    valores = {"r": r, "m": m, "f": f}
    uma = resolve_visibility(script, valores, None)
    assert resolve_visibility(script, uma, None) == uma


def test_normalize_options_expands_paths_and_keeps_text() -> None:
    script = _script()
    normal = normalize_options(script, {"r": "sim", "m": "", "f": "", "pasta": "~/x"}, "/casa")
    assert normal["pasta"] == "/casa/x"
    assert normal["r"] == "sim"


def test_validate_options_raises_on_visible_invalid_value() -> None:
    script = parse_text(
        HEADER + "#@option n\n#@type number\n#@default 1\n#@step s\ns() { :; }\n", Path("/tmp/x.sh")
    ).script
    try:
        validate_options(script, {"n": "abc"}, "/casa", None)
    except ValidationError:
        return
    raise AssertionError("valor inválido deveria falhar")


def test_build_plan_equals_the_composition_of_the_stages() -> None:
    script = _script()
    valores = {"r": "nao", "m": "x", "f": "segredo", "pasta": "~/x"}
    plano = build_plan(script, None, valores, "/casa")
    esperado = normalize_options(script, resolve_visibility(script, valores, None), "/casa")
    assert plano.options["m"] == esperado["m"] == ""
    assert plano.options["f"] == esperado["f"] == ""
    assert plano.options["pasta"] == esperado["pasta"] == "/casa/x"

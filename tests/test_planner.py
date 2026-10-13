"""Testes do planner (SPEC.md §6)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fixtures import text
from fixtures.paths import DEV_SETUP

from rt.core.errors import ValidationError
from rt.core.parser import parse_text
from rt.core.planner import (
    build_plan,
    can_uncheck,
    default_options,
    default_selection,
    dependents,
    expand_value,
    option_errors,
    resolve,
    set_checked,
)

DEPS = """\
#@runtime 1
#@name Grafo
#@option dir type=path label="Pasta" default="$HOME/dev"
#@option editor type=choice label="Editor" choices="vim,nano" default=nano
#@option nome type=string required=true

#@step c
c() { :; }

#@step a
#@depends c
a() { :; }

#@step b
#@depends c
b() { :; }

#@step d
#@depends a,b
d() { :; }

#@step obrigatorio
#@required
obrigatorio() { :; }
"""


@pytest.fixture()
def script():
    return parse_text(DEPS, Path("x.sh")).script


# -- ordem e dependências (§6) ------------------------------------------------
def test_dependencies_are_added(script) -> None:
    result = resolve(script, ["d"])
    # "obrigatorio" sempre entra (§6) e vem antes por ordem de declaração
    assert result.ids == ["c", "obrigatorio", "a", "b", "d"]
    assert result.auto_added == {"c", "a", "b"}


def test_declaration_order_is_the_tiebreaker(script) -> None:
    result = resolve(script, ["d", "c"])
    assert result.ids == ["c", "obrigatorio", "a", "b", "d"]  # a antes de b por declaração


def test_required_steps_are_always_included(script) -> None:
    result = resolve(script, ["c"])
    assert result.ids == ["c", "obrigatorio"]
    assert result.auto_added == set()  # required não é "incluído por dependência"


def test_default_selection_uses_default_and_required(script) -> None:
    assert set(default_selection(script)) == {"c", "a", "b", "d", "obrigatorio"}


def test_unknown_selection_is_error(script) -> None:
    with pytest.raises(ValidationError) as error:
        resolve(script, ["nao_existe"])
    assert "nao_existe" in str(error.value)


def test_dependents(script) -> None:
    assert dependents(script, "c") == ["a", "b", "d"]
    assert dependents(script, "d") == []
    assert dependents(script, "obrigatorio") == []


def test_can_uncheck(script) -> None:
    selected = {"c", "a", "b", "d", "obrigatorio"}
    assert can_uncheck(script, "d", selected) is None
    assert "obrigatório" in (can_uncheck(script, "obrigatorio", selected) or "")
    assert "necessário" in (can_uncheck(script, "c", selected) or "")


def test_set_checked_adds_dependencies(script) -> None:
    selected = set_checked(script, set(), "d", True)
    assert selected == {"d", "a", "b", "c"}


def test_set_checked_blocks_uncheck_with_dependents(script) -> None:
    with pytest.raises(ValidationError):
        set_checked(script, {"c", "a", "b", "d"}, "c", False)


def test_set_checked_removes_when_safe(script) -> None:
    assert set_checked(script, {"c", "a", "b", "d"}, "d", False) == {"c", "a", "b"}


# -- opções (§6, §4.3) --------------------------------------------------------
def test_expand_value() -> None:
    assert expand_value("$HOME/dev", "/home/x") == "/home/x/dev"
    assert expand_value("~/dev", "/home/x") == "/home/x/dev"
    assert expand_value("~", "/home/x") == "/home/x"
    assert expand_value("${HOME}/x", "/home/x") == "/home/x/x"
    assert expand_value("/tmp", "/home/x") == "/tmp"


def test_default_options_expands_paths(script) -> None:
    values = default_options(script, "/home/tester")
    assert values["dir"] == "/home/tester/dev"
    assert values["editor"] == "nano"
    assert values["nome"] == ""


def test_option_errors_required(script) -> None:
    errors = option_errors(script, {"nome": ""})
    assert "nome" in errors
    assert "obrigatório" in errors["nome"]


def test_option_errors_choice(script) -> None:
    assert option_errors(script, {"nome": "x", "editor": "emacs"})
    assert not option_errors(script, {"nome": "x", "editor": "vim"})


def test_build_plan(script) -> None:
    plan = build_plan(script, ["d"], {"nome": "Fulano"}, home="/home/tester")
    assert plan.selected == ["c", "obrigatorio", "a", "b", "d"]
    assert plan.options["nome"] == "Fulano"
    assert plan.options["dir"] == "/home/tester/dev"
    assert plan.auto_added == {"c", "a", "b"}


def test_build_plan_rejects_unknown_option(script) -> None:
    with pytest.raises(ValidationError) as error:
        build_plan(script, ["c"], {"inexistente": "1"})
    assert "inexistente" in str(error.value)


def test_build_plan_rejects_invalid_option(script) -> None:
    with pytest.raises(ValidationError):
        build_plan(script, ["c"], {"nome": "x", "editor": "emacs"})


def test_plan_of_dev_setup_fixture() -> None:
    script = parse_text(DEV_SETUP.read_text(encoding="utf-8"), DEV_SETUP).script
    plan = build_plan(script, ["config_git"], {"user_name": "Ana"}, home="/home/ana")
    assert plan.selected == ["update_index", "install_tools", "config_git"]
    assert plan.auto_added == {"update_index", "install_tools"}
    assert plan.options["editor"] == "nano"
    assert plan.options["telemetry"] == "0"


def test_attribute_fixture_plan() -> None:
    script = parse_text(text.ATTRIBUTES, Path("x.sh")).script
    plan = build_plan(script, ["install_tools"], {"name": "Ana"}, home="/home/ana")
    # install_tools é required e depende de update_index (default off)
    assert plan.selected == ["update_index", "install_tools"]
    assert plan.auto_added == {"update_index"}
    assert plan.options["plugins"] == "a"
    # com a seleção padrão nada é "incluído por dependência"
    default_plan = build_plan(script, None, {"name": "Ana"}, home="/home/ana")
    assert default_plan.auto_added == set()


# -- novos tipos de opção (§4.3) -------------------------------------------------
TYPED = """\
#@runtime 1
#@name Tipos
#@option retries type=number label="Tentativas" min=1 max=10 default=3
#@option volume type=slider label="Volume" default=50
#@option avatar type=file label="Foto" default="~/foto.png"
#@option deadline type=date label="Prazo"
#@option alarm type=time label="Hora"

#@step s
s() { :; }
"""


def typed_script():
    return parse_text(TYPED, Path("tipos.sh")).script


def test_option_errors_number() -> None:
    script = typed_script()
    assert "retries" in option_errors(script, {"retries": "abc"})
    assert "retries" in option_errors(script, {"retries": "0"})
    assert "retries" in option_errors(script, {"retries": "11"})
    assert "retries" in option_errors(script, {"retries": "1,2"})
    assert not option_errors(script, {"retries": "1"})
    assert not option_errors(script, {"retries": "10"})
    assert not option_errors(script, {"retries": "2.5"})
    assert "volume" in option_errors(script, {"volume": "101"})
    assert not option_errors(script, {"volume": "0"})


def test_option_errors_date_time() -> None:
    script = typed_script()
    assert "deadline" in option_errors(script, {"deadline": "31/12/2026"})
    assert "deadline" in option_errors(script, {"deadline": "2026-02-30"})
    assert not option_errors(script, {"deadline": "2026-12-31"})
    assert "alarm" in option_errors(script, {"alarm": "25:00"})
    assert "alarm" in option_errors(script, {"alarm": "8:30"})
    assert not option_errors(script, {"alarm": "08:30"})


def test_file_expands_like_path() -> None:
    script = typed_script()
    values = default_options(script, "/home/tester")
    assert values["avatar"] == "/home/tester/foto.png"
    plan = build_plan(
        script, ["s"],
        {"retries": "5", "avatar": "~/outra.png", "deadline": "2026-01-15", "alarm": "09:00"},
        home="/home/tester",
    )
    assert plan.options["retries"] == "5"
    assert plan.options["avatar"] == "/home/tester/outra.png"
    assert plan.options["deadline"] == "2026-01-15"
    assert plan.options["alarm"] == "09:00"


def test_build_plan_rejects_invalid_typed_option() -> None:
    script = typed_script()
    with pytest.raises(ValidationError):
        build_plan(script, ["s"], {"retries": "x"})
    with pytest.raises(ValidationError):
        build_plan(script, ["s"], {"deadline": "2026-13-01"})


def test_option_errors_pattern_minlen_maxlen() -> None:
    source = (
        "#@runtime 1\n#@name T\n"
        '#@option slug type=string label=S pattern="^[a-z-]+$" minlen=2 maxlen=4\n'
        "#@step s\ns() { :; }\n"
    )
    script = parse_text(source, Path("t.sh")).script
    assert "slug" in option_errors(script, {"slug": "ABC"})
    assert "slug" in option_errors(script, {"slug": "a"})
    assert "slug" in option_errors(script, {"slug": "abcde"})
    assert not option_errors(script, {"slug": "abc"})
    assert not option_errors(script, {"slug": ""})


def test_option_visible_conditions() -> None:
    from rt.core.planner import option_visible

    source = (
        "#@runtime 1\n#@name T\n"
        '#@option modo type=choice label=M choices="a,b" default=a\n'
        '#@option detalhe type=string label=D show_if="modo=b"\n'
        "#@step s\ns() { :; }\n"
    )
    script = parse_text(source, Path("t.sh")).script
    detalhe = script.option("detalhe")
    assert detalhe is not None
    assert option_visible(script, {}, detalhe) is False
    assert option_visible(script, {"modo": "b"}, detalhe) is True
    assert option_visible(script, {"modo": "a"}, detalhe) is False


def test_hidden_option_skips_required_and_uses_default() -> None:
    source = (
        "#@runtime 1\n#@name T\n"
        '#@option modo type=choice label=M choices="a,b" default=a\n'
        '#@option detalhe type=string label=D required=true default="padrão" show_if="modo=b"\n'
        "#@step s\ns() { :; }\n"
    )
    script = parse_text(source, Path("t.sh")).script
    assert not option_errors(script, {"modo": "a"})
    plan = build_plan(script, ["s"], {"modo": "a", "detalhe": "ignorado"})
    assert plan.options["detalhe"] == "padrão"
    assert "detalhe" in option_errors(script, {"modo": "b", "detalhe": ""})

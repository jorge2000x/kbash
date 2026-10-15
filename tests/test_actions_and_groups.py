"""Ações (mini-scripts, SPEC.md §4.8) e grupos de exibição (§4.8.1).

Cobre o parser: ``#@action`` com defaults, avisos, erros de função e id; o
``group=`` de opções; e a ordem dos grupos pela primeira declaração.
"""

from __future__ import annotations

import pytest

from kbash.core.errors import ParseError, ValidationError
from kbash.core.parser import parse_text

HDR = "#!/usr/bin/env bash\n#@runtime 1\n#@name T\n"


def _parse(body: str):
    return parse_text(HDR + body)


def _warnings(result) -> str:
    return " | ".join(str(w) for w in result.warnings)


def test_action_parses_with_defaults() -> None:
    result = _parse(
        "#@action check_space\n"
        "#@title Ver espaço\n"
        "#@desc Mede o cache.\n"
        "check_space() { rt_log ok; }\n"
    )
    action = result.script.action("check_space")
    assert action is not None
    assert action.title == "Ver espaço"
    assert action.description == "Mede o cache."
    assert action.button == "Executar"
    assert action.root is False
    assert action.timeout == 60
    assert action.group is None
    assert result.script.steps == ()  # ação não é step


def test_action_button_group_root_and_timeout() -> None:
    result = _parse(
        "#@action clean\n#@button Limpar agora\n#@group Limpeza\n#@root true\n#@timeout 120\n"
        "clean() { :; }\n"
    )
    action = result.script.action("clean")
    assert (action.button, action.group, action.root, action.timeout) == (
        "Limpar agora",
        "Limpeza",
        True,
        120,
    )


@pytest.mark.parametrize("value", ["0", "-5", "abc"])
def test_action_invalid_timeout_warns_and_uses_default(value: str) -> None:
    result = _parse(f"#@action a\n#@timeout {value}\na() {{ :; }}\n")
    assert result.script.action("a").timeout == 60
    assert "usando 60 s" in _warnings(result)


@pytest.mark.parametrize(
    "directive",
    ["#@default on", "#@required true", "#@depends x", "#@on_error continue"],
)
def test_action_ignored_directives_warn(directive: str) -> None:
    result = _parse(f"#@action a\n{directive}\na() {{ :; }}\n")
    assert "não vale em #@action" in _warnings(result)
    assert result.script.action("a") is not None


def test_action_without_function_is_error() -> None:
    with pytest.raises((ParseError, ValidationError)):
        _parse("#@action a\n#@title sem função\n")


def test_action_pending_block_followed_by_code_is_error() -> None:
    with pytest.raises(ParseError):
        _parse("#@action a\nrt_log solto\n")


def test_action_function_mismatch_is_error() -> None:
    with pytest.raises(ValidationError):
        _parse("#@action a\nfoo() { :; }\n")


def test_action_function_directive_allows_other_name() -> None:
    result = _parse("#@action a\n#@function real_fn\nreal_fn() { :; }\n")
    assert result.script.action("a").function == "real_fn"


def test_action_id_cannot_repeat_a_step_id() -> None:
    with pytest.raises(ValidationError):
        _parse("#@step x\nx() { :; }\n#@action x\nx() { :; }\n")


def test_option_group_is_parsed_and_optional() -> None:
    result = _parse(
        '#@option dest type=path label="Destino" group="Destino"\n'
        '#@option plain type=string label="Livre"\n'
    )
    assert result.script.option("dest").group == "Destino"
    assert result.script.option("plain").group is None


def test_group_on_needs_step_option_warns_and_is_ignored() -> None:
    result = _parse(
        '#@option x type=string label="X" needs_step=s group="Nada"\n'
        "#@step s\ns() { :; }\n"
    )
    assert result.script.option("x").group is None
    assert "group em #@option" in _warnings(result)


def test_groups_follow_first_declaration_order_across_kinds() -> None:
    result = _parse(
        '#@option dest type=path label="Destino" group="Destino"\n'
        "#@step backup\n#@group Backup\nbackup() { :; }\n"
        '#@option sem_grupo type=string label="Sem grupo"\n'
        "#@action check\n#@group Limpeza\ncheck() { :; }\n"
        "#@step backup2\n#@group Backup\nbackup2() { :; }\n"
    )
    assert result.script.groups == ("Destino", "Backup", "", "Limpeza")


def test_groups_treat_missing_group_as_untitled_block() -> None:
    result = _parse("#@step a\na() { :; }\n#@step b\n#@group G\nb() { :; }\n")
    assert result.script.groups == ("", "G")


def test_needs_step_option_does_not_create_a_group() -> None:
    result = _parse(
        '#@option x type=string label="X" needs_step=s group="Escondido"\n'
        "#@step s\n#@group Real\ns() { :; }\n"
    )
    assert result.script.groups == ("Real",)

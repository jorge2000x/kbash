"""Testes do parser (SPEC.md §4, §4.6)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fixtures import text
from fixtures.paths import DEV_SETUP

from kbash.core.errors import ParseError, ValidationError
from kbash.core.model import is_valid_id
from kbash.core.parser import check_script, parse_script, parse_text


def parse(source: str):
    return parse_text(source, Path("test.sh")).script


# -- cabeçalho ---------------------------------------------------------------
def test_minimal_script() -> None:
    script = parse(text.MINIMAL)
    assert script.name == "Mínimo"
    assert script.id == "mnimo"  # §4.2 — slug do nome (sem acentos)
    assert script.runtime_version == 1
    assert script.strict is True
    assert len(script.steps) == 1
    step = script.steps[0]
    assert (step.id, step.function, step.title) == ("ola", "ola", "Saudação")
    assert step.default is True and step.required is False and step.on_error == "stop"


def test_missing_runtime_is_error() -> None:
    with pytest.raises(ParseError) as error:
        parse(text.NO_RUNTIME)
    assert "#@runtime" in str(error.value)
    assert "error:" in str(error.value)


def test_future_runtime_is_error() -> None:
    with pytest.raises(ValidationError) as error:
        parse(text.FUTURE_RUNTIME)
    assert "mais novo" in str(error.value)


def test_missing_name_is_error() -> None:
    with pytest.raises(ParseError) as error:
        parse(text.NO_NAME)
    assert "#@name" in str(error.value)


def test_shebang_is_not_an_annotation() -> None:
    script = parse_text(text.MINIMAL, Path("x.sh")).script
    assert script.name == "Mínimo"


def test_attributes() -> None:
    script = parse(text.ATTRIBUTES)
    assert script.id == "com.exemplo.attrs"
    assert script.description == "Uma linha. Outra linha."
    assert script.version == "2.1.0"
    assert script.author == "Fulano"
    assert script.icon == "computer"
    assert script.requires == ("curl", "git")
    assert script.strict is False
    # §4.8.1: opções sem group e steps sem #@group formam o bloco sem título ("")
    assert script.groups == ("", "Preparação", "Ferramentas")
    assert [option.id for option in script.options] == [
        "editor", "name", "token", "dir", "plugins", "telemetry",
    ]
    editor = script.option("editor")
    assert editor is not None
    assert (editor.type, editor.label, editor.default, editor.choices) == (
        "choice", "Editor", "nano", ("vim", "nano"),
    )
    assert editor.help == "Usado pelo git"
    assert script.option("name").required is True
    assert script.option("token").type == "password"
    assert script.option("dir").default == "$HOME/dev"
    assert script.option("plugins").choices == ("a", "b", "c")
    assert script.option("telemetry").env_value() == "0"


def test_step_attributes_and_line_numbers() -> None:
    script = parse(text.ATTRIBUTES)
    update = script.step("update_index")
    assert update is not None
    assert update.title == "Atualizar índice"
    assert update.description == "Primeira linha.\nSegunda linha."
    assert update.group == "Preparação"
    assert update.root is True
    assert update.timeout == 900
    assert update.on_error == "continue"
    assert update.line == 19  # linha da diretiva #@step
    install = script.step("install_tools")
    assert install is not None
    assert install.default is False
    assert install.required is True
    assert install.depends == ("update_index",)


# -- validação (§4.6) --------------------------------------------------------
def test_duplicate_step_id() -> None:
    with pytest.raises(ValidationError) as error:
        parse(text.DUPLICATE_STEP)
    assert "duplicado" in str(error.value)
    assert error.value.diagnostic.line is not None


def test_duplicate_option_id() -> None:
    with pytest.raises(ValidationError) as error:
        parse(text.DUPLICATE_OPTION)
    assert "duplicado" in str(error.value)


def test_option_and_step_with_same_id() -> None:
    with pytest.raises(ValidationError):
        parse(text.OPTION_STEP_ID_CLASH)


def test_multiline_option_block() -> None:
    script = parse(text.OPTION_MULTILINE)
    editor = script.option("editor")
    assert editor is not None
    assert (editor.label, editor.choices, editor.default) == ("Editor", ("vim", "nano"), "nano")
    name = script.option("nome")
    assert name is not None
    assert name.required is True and name.help == "Usado no git"


def test_step_function_not_found() -> None:
    with pytest.raises(ValidationError) as error:
        parse(text.MISSING_FUNCTION)
    assert "fantasma" in str(error.value)


def test_depends_on_unknown_step() -> None:
    with pytest.raises(ValidationError) as error:
        parse(text.BAD_DEPENDS)
    assert "fantasma" in str(error.value)


def test_dependency_cycle() -> None:
    with pytest.raises(ValidationError) as error:
        parse(text.CYCLE)
    assert "ciclo" in str(error.value)


def test_choice_without_choices() -> None:
    with pytest.raises(ValidationError) as error:
        parse(text.CHOICE_NO_CHOICES)
    assert "choices" in str(error.value)


def test_default_outside_choices() -> None:
    with pytest.raises(ValidationError) as error:
        parse(text.DEFAULT_OUTSIDE_CHOICES)
    assert "emacs" in str(error.value)


def test_unknown_directive_is_warning() -> None:
    result = parse_text(text.UNKNOWN_DIRECTIVE, Path("x.sh"))
    assert len(result.warnings) == 1
    assert "frobnicate" in result.warnings[0].message
    assert result.warnings[0].severity == "warning"


def test_invalid_id_pattern() -> None:
    with pytest.raises(ParseError) as error:
        parse("#@runtime 1\n#@name X\n#@step Com_espaco\nCom_espaco() { :; }\n")
    assert "id inválido" in str(error.value)


@pytest.mark.parametrize("value", ["a", "a1", "a_b", "step_1"])
def test_valid_ids(value: str) -> None:
    assert is_valid_id(value)


@pytest.mark.parametrize("value", ["A", "1a", "a-b", "", "a b"])
def test_invalid_ids(value: str) -> None:
    assert not is_valid_id(value)


def test_block_without_function_definition() -> None:
    with pytest.raises(ParseError) as error:
        parse(text.BLOCK_WITHOUT_FUNCTION)
    assert "seguido" in str(error.value)


def test_step_annotation_after_code_is_accepted_with_warning() -> None:
    # Não é erro: §4.1 só exige que as anotações de cabeçalho venham antes.
    result = parse_text(text.LATE_ANNOTATION, Path("x.sh"))
    assert [step.id for step in result.script.steps] == ["ola"]
    assert any("echo" in warning.message for warning in result.warnings)


# -- warnings heurísticos (§4.5) ---------------------------------------------
def test_loose_top_level_warnings() -> None:
    result = parse_text(text.LOOSE_TOP_LEVEL, Path("x.sh"))
    messages = [warning.message for warning in result.warnings]
    assert any("echo" in message for message in messages)
    assert any("date" in message for message in messages)


def test_no_loose_warning_for_definitions() -> None:
    result = parse_text(
        "#@runtime 1\n#@name X\n"
        "export FOO=1\nPATH=/opt/bin:$PATH\nset -u\n"
        "#@step ola\nola() {\n  local x=1\n  [ -n \"$x\" ] && echo ok\n}\n",
        Path("x.sh"),
    )
    assert result.warnings == ()


def test_ignores_comments_that_look_like_annotations() -> None:
    result = parse_text(
        '#@runtime 1\n#@name X\n#@step ola\nola() {\n  echo "#@nao sou anotacao"\n}\n',
        Path("x.sh"),
    )
    assert result.warnings == ()


# -- arquivos reais ----------------------------------------------------------
def test_parse_dev_setup_fixture() -> None:
    script = parse_script(DEV_SETUP)
    assert script.name == "Configurar ambiente de desenvolvimento"
    assert [step.id for step in script.steps] == ["update_index", "install_tools", "config_git"]
    assert script.step("install_tools").depends == ("update_index",)
    assert script.step("update_index").root is True
    assert script.option("user_name").required is True
    assert len(script.sha256) == 64


def test_check_script_reports_errors_with_line(tmp_path: Path) -> None:
    target = tmp_path / "ruim.sh"
    target.write_text(text.BAD_DEPENDS, encoding="utf-8")
    script, diagnostics = check_script(target)
    assert script is None
    assert len(diagnostics.errors) == 1
    diagnostic = diagnostics.errors[0]
    assert diagnostic.line is not None
    assert str(diagnostic).startswith(f"{target}:{diagnostic.line}: error:")


def test_check_script_ok_with_warnings(tmp_path: Path) -> None:
    target = tmp_path / "aviso.sh"
    target.write_text(text.LOOSE_TOP_LEVEL, encoding="utf-8")
    script, diagnostics = check_script(target)
    assert script is not None
    assert not diagnostics.errors
    assert len(diagnostics.warnings) == 2


def test_unbalanced_quote_is_parse_error() -> None:
    with pytest.raises(ParseError) as error:
        parse('#@runtime 1\n#@name "sem fim\n#@step ola\nola() { :; }\n')
    assert "tokenizar" in str(error.value)


# -- novos tipos de opção (§4.3) ----------------------------------------------
NEW_TYPES = """\
#@runtime 1
#@name Tipos
#@option retries type=number label="Tentativas" min=1 max=10 default=3
#@option volume type=slider label="Volume" default=50
#@option avatar type=file label="Foto" filters="*.png,*.jpg"
#@option notes type=text label="Notas"
#@option deadline type=date label="Prazo" default="2026-12-31"
#@option alarm type=time label="Hora" default="08:30"

#@step s
s() { :; }
"""


def test_option_new_types_parsed() -> None:
    script = parse(NEW_TYPES)
    retries = script.option("retries")
    assert retries is not None
    assert (retries.type, retries.minimum, retries.maximum, retries.default) == (
        "number", "1", "10", "3",
    )
    volume = script.option("volume")
    assert volume is not None
    # faixa padrão do slider (§4.3)
    assert (volume.type, volume.minimum, volume.maximum, volume.step) == (
        "slider", "0", "100", "1",
    )
    avatar = script.option("avatar")
    assert avatar is not None
    assert (avatar.type, avatar.filters) == ("file", ("*.png", "*.jpg"))
    assert script.option("notes").type == "text"
    assert script.option("deadline").default == "2026-12-31"
    assert script.option("alarm").default == "08:30"


def test_option_number_range_errors() -> None:
    base = "#@runtime 1\n#@name T\n#@option n type=number label=N %%\n#@step s\ns() { :; }\n"
    for attrs in ("min=10 max=1", "step=0", "step=-2", "min=abc", "max=1.2.3"):
        with pytest.raises(ValidationError):
            parse(base.replace("%%", attrs))


def test_option_number_default_errors() -> None:
    base = "#@runtime 1\n#@name T\n#@option n type=number label=N min=1 max=10 default=%%\n#@step s\ns() { :; }\n"
    for default in ("abc", "0", "99", "1,2"):
        with pytest.raises(ValidationError):
            parse(base.replace("%%", default))
    assert parse(base.replace("%%", "1").replace("min=1 max=10 ", "")).option("n").default == "1"


def test_option_date_default_errors() -> None:
    base = "#@runtime 1\n#@name T\n#@option d type=date label=D default=%%\n#@step s\ns() { :; }\n"
    for default in ("31/12/2026", "2026-13-01", "2026-02-30", "20261231", "hoje"):
        with pytest.raises(ValidationError):
            parse(base.replace("%%", default))
    assert parse(base.replace("%%", "2024-02-29")).option("d").default == "2024-02-29"


def test_option_time_default_errors() -> None:
    base = "#@runtime 1\n#@name T\n#@option h type=time label=H default=%%\n#@step s\ns() { :; }\n"
    for default in ("25:00", "08:60", "8:30", "manhã"):
        with pytest.raises(ValidationError):
            parse(base.replace("%%", default))
    assert parse(base.replace("%%", "00:00")).option("h").default == "00:00"


def test_option_range_attrs_warn_on_other_types() -> None:
    source = (
        "#@runtime 1\n#@name T\n"
        '#@option nome type=string label=S min=1 filters="*.png"\n'
        "#@step s\ns() { :; }\n"
    )
    result = parse_text(source, Path("test.sh"))
    messages = [warning.message for warning in result.warnings]
    assert any("min/max/step" in message for message in messages)
    assert any("filters" in message for message in messages)
    assert result.script.option("nome").minimum is None


def test_option_unknown_type_still_falls_back_to_string() -> None:
    result = parse_text(
        '#@runtime 1\n#@name T\n#@option x type=quantum label=X\n#@step s\ns() { :; }\n',
        Path("test.sh"),
    )
    assert result.script.option("x").type == "string"
    assert any("desconhecido" in warning.message for warning in result.warnings)


def test_option_pattern_minlen_maxlen_parsed() -> None:
    script = parse(
        "#@runtime 1\n#@name T\n"
        '#@option slug type=string label=S pattern="^[a-z-]+$" minlen=2 maxlen=10\n'
        "#@step s\ns() { :; }\n"
    )
    option = script.option("slug")
    assert option is not None
    assert (option.pattern, option.minlen, option.maxlen) == ("^[a-z-]+$", "2", "10")


def test_option_pattern_errors() -> None:
    base = "#@runtime 1\n#@name T\n#@option slug type=string label=S %%\n#@step s\ns() { :; }\n"
    with pytest.raises(ValidationError):
        parse(base.replace("%%", 'pattern="([a-z"'))
    with pytest.raises(ValidationError):
        parse(base.replace("%%", 'pattern="^[a-z]+$" default="ABC"'))
    with pytest.raises(ValidationError):
        parse(base.replace("%%", "minlen=-1"))
    with pytest.raises(ValidationError):
        parse(base.replace("%%", "minlen=5 maxlen=2"))
    with pytest.raises(ValidationError):
        parse(base.replace("%%", 'minlen=3 default="ab"'))
    with pytest.raises(ValidationError):
        parse(base.replace("%%", 'maxlen=2 default="abc"'))
    ok = parse(base.replace("%%", 'pattern="^[a-z]+$" minlen=1 maxlen=3 default="ab"'))
    assert ok.option("slug").pattern == "^[a-z]+$"


def test_option_pattern_warns_on_other_types() -> None:
    result = parse_text(
        "#@runtime 1\n#@name T\n#@option n type=number label=N pattern=x multiple=true\n#@step s\ns() { :; }\n",
        Path("test.sh"),
    )
    messages = [warning.message for warning in result.warnings]
    assert any("pattern/minlen/maxlen" in message for message in messages)
    assert any("multiple" in message for message in messages)
    assert result.script.option("n").pattern == ""
    assert result.script.option("n").multiple is False


def test_option_file_multiple_parsed() -> None:
    script = parse(
        "#@runtime 1\n#@name T\n#@option f type=file label=F multiple=true\n#@step s\ns() { :; }\n"
    )
    assert script.option("f").multiple is True


def test_option_show_if_parsed() -> None:
    script = parse(
        "#@runtime 1\n#@name T\n"
        '#@option modo type=choice label=M choices="a,b" default=a\n'
        '#@option detalhe type=string label=D show_if="modo=b"\n'
        '#@option ambos type=string label=A show_if="modo=b,detalhe=x"\n'
        "#@step s\ns() { :; }\n"
    )
    assert script.option("detalhe").show_if == (("modo", "b"),)
    assert script.option("ambos").show_if == (("modo", "b"), ("detalhe", "x"))
    assert script.option("modo").show_if == ()


def test_option_show_if_errors() -> None:
    base = "#@runtime 1\n#@name T\n#@option a type=string label=A %%\n#@step s\ns() { :; }\n"
    with pytest.raises(ValidationError):
        parse(base.replace("%%", 'show_if="fantasma=x"'))
    with pytest.raises(ValidationError):
        parse(base.replace("%%", 'show_if="a=x"'))
    with pytest.raises(ValidationError):
        parse(base.replace("%%", 'show_if="sem-igual"'))
    cycled = (
        "#@runtime 1\n#@name T\n"
        '#@option a type=string label=A show_if="b=x"\n'
        '#@option b type=string label=B show_if="a=y"\n'
        "#@step s\ns() { :; }\n"
    )
    with pytest.raises(ValidationError) as error:
        parse(cycled)
    assert "ciclo" in str(error.value)

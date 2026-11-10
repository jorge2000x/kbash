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
    base = (
        "#@runtime 1\n#@name T\n"
        "#@option n type=number label=N min=1 max=10 default=%%\n"
        "#@step s\ns() { :; }\n"
    )
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
        "#@runtime 1\n#@name T\n"
        "#@option n type=number label=N pattern=x multiple=true\n"
        "#@step s\ns() { :; }\n",
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


@pytest.mark.parametrize("linha", ["#@ ", "#@   ", "#@\xa0", "#@\t"])
def test_anotacao_so_com_espaco_e_erro_de_parse_nao_crash(linha: str) -> None:
    """Regressão (crosshair): ``#@`` seguido só de espaço causava IndexError em
    ``parts[0]``. Tem de virar aviso ("anotação vazia"), não exceção nua."""
    texto = "#!/usr/bin/env bash\n#@runtime 1\n#@name X\n" + linha + "\n"
    result = parse_text(texto)
    assert any("anotação vazia" in str(w) for w in result.warnings)


# -- diagnósticos com mensagem e linha exatas (mata mutantes de texto e de linha)
_HDR = "#@runtime 1\n#@name T\n"

ERROS_EXATOS = [
    (_HDR + '#@option x type=string label="sem fechar\n#@step s\ns() { :; }\n', ParseError, 3,
     "não foi possível tokenizar a anotação: No closing quotation"),
    (_HDR + "#@step\ns() { :; }\n", ParseError, 3, "#@step sem id"),
    (_HDR + "#@step 1x\n1x() { :; }\n", ParseError, 3,
     "id inválido '1x' (esperado [a-z][a-z0-9_]*)"),
    (_HDR + "#@step a\na() { :; }\n#@step a\na2() { :; }\n", ValidationError, 5,
     "id duplicado 'a' (já declarado em #@step)"),
    (_HDR + "#@step a\n#@option o type=string\n", ParseError, 3,
     "bloco #@step 'a' sem definição de função (apareceu #@option antes)"),
    (_HDR + "#@step a\n", ParseError, 3, "bloco #@step 'a' sem definição de função"),
    (_HDR + "#@option o type=string\n#@option o type=string\n", ValidationError, 4,
     "id duplicado 'o' (já declarado em #@option)"),
    (_HDR + "#@step s\nvalor=1\n", ParseError, 3,
     "#@step 's' deve ser seguido da definição da função (encontrado: 'valor=1')"),
    ("#@name T\n#@step s\ns() { :; }\n", ParseError, None,
     "diretiva obrigatória ausente: #@runtime"),
    ("#@runtime 1\n#@step s\ns() { :; }\n", ParseError, None,
     "diretiva obrigatória ausente: #@name"),
    ("#@runtime x\n#@name T\n", ParseError, 1, "#@runtime inválido: 'x'"),
    ("#@runtime 9\n#@name T\n", ValidationError, 1,
     "#@runtime 9 é mais novo que a versão suportada (1)"),
    (_HDR + "#@option p type=paragraph\n#@step s\ns() { :; }\n", ValidationError, 3,
     "#@option 'p' type=paragraph exige label (o texto mostrado)"),
    (_HDR + "#@option l type=link\n#@step s\ns() { :; }\n", ValidationError, 3,
     "#@option 'l' type=link exige url"),
    (_HDR + '#@option l type=link url="ftp://x"\n#@step s\ns() { :; }\n', ValidationError, 3,
     "url='ftp://x' de #@option 'l' precisa começar com http:// ou https://"),
    (_HDR + '#@option o type=string show_if="abc"\n#@step s\ns() { :; }\n', ValidationError, 3,
     "show_if='abc' de #@option 'o' precisa ser id=valor"),
    (_HDR + '#@option o type=string show_if="1x=2"\n#@step s\ns() { :; }\n', ValidationError, 3,
     "show_if referencia id inválido '1x' em #@option 'o'"),
    (_HDR + '#@option o type=string show_if="zz=2"\n#@step s\ns() { :; }\n', ValidationError, 3,
     "show_if de #@option 'o' aponta para opção inexistente 'zz'"),
]

AVISOS_EXATOS = [
    (_HDR + "#@step s extra\ns() { :; }\n", [(3, "argumento extra 'extra' ignorado em #@step")]),
    (_HDR + "#@foo bar\n#@step s\ns() { :; }\n", [(3, "diretiva desconhecida #@foo")]),
    (_HDR + "#@\n#@step s\ns() { :; }\n", [(3, "anotação vazia")]),
    (_HDR + "#@step s\n#@title A\n#@title B\ns() { :; }\n",
     [(5, "#@title repetido no bloco 's'")]),
    (_HDR + "#@name X\n#@step s\ns() { :; }\n", [(3, "#@name repetido no cabeçalho")]),
    (_HDR + "#@step s\n#@name X\ns() { :; }\n", [(4, "#@name não é válido em #@step")]),
    (_HDR + "echo oi\n#@step s\ns() { :; }\n",
     [(3, "comando de nível superior 'echo' roda a cada step (mova-o para dentro de uma função)")]),
    (_HDR + '#@option l type=link url="https://x" default=1\n#@step s\ns() { :; }\n',
     [(3, "default= de #@option 'l' não se aplica a type=link (ignorado)")]),
]


@pytest.mark.parametrize(("text", "exc_type", "line", "message"), ERROS_EXATOS)
def test_erro_com_mensagem_e_linha_exatas(text: str, exc_type: type, line, message: str) -> None:
    with pytest.raises(exc_type) as exc:
        parse_text(text, Path("t.sh"))
    assert exc.value.diagnostic.message == message
    assert exc.value.diagnostic.line == line
    assert exc.value.diagnostic.path == Path("t.sh")


@pytest.mark.parametrize(("text", "esperados"), AVISOS_EXATOS)
def test_aviso_com_linha_e_mensagem_exatas(text: str, esperados: list) -> None:
    result = parse_text(text, Path("t.sh"))
    assert [(w.line, w.message) for w in result.warnings] == esperados


ERROS_OPCAO = [
    (_HDR + "#@option o type=choice\n" + "#@step s\ns() { :; }\n", ValidationError, 3,
     "#@option 'o' type=choice exige choices"),
    (_HDR + "#@option o type=multi\n" + "#@step s\ns() { :; }\n", ValidationError, 3,
     "#@option 'o' type=multi exige choices"),
    (_HDR + '#@option o type=choice choices="a,b" default=c\n' + "#@step s\ns() { :; }\n",
     ValidationError, 3, "default='c' de #@option 'o' não está em choices (a, b)"),
    (_HDR + "#@option o type=date default=\"31/12/2026\"\n" + "#@step s\ns() { :; }\n",
     ValidationError, 3, "default='31/12/2026' de #@option 'o' não é data ISO (AAAA-MM-DD)"),
    (_HDR + '#@option o type=time default="8:30"\n' + "#@step s\ns() { :; }\n",
     ValidationError, 3, "default='8:30' de #@option 'o' não é hora (HH:MM)"),
    (_HDR + "#@option o type=string needs_step=zz\n" + "#@step s\ns() { :; }\n",
     ValidationError, 3, "needs_step de #@option 'o' aponta para step inexistente 'zz'"),
]

AVISOS_OPCAO = [
    (_HDR + "#@option o type=zzz\n#@step s\ns() { :; }\n",
     [(3, "type='zzz' desconhecido em #@option 'o'; usando 'string'")]),
    (_HDR + "#@option o type=bool default=talvez\n#@step s\ns() { :; }\n",
     [(3, "default='talvez' de #@option 'o' (bool) não é booleano")]),
    (_HDR + "#@option o type=bool required=true\n#@step s\ns() { :; }\n",
     [(3, "#@option 'o' é required mas do tipo bool")]),
    (_HDR + '#@option o type=string filters="*.png"\n#@step s\ns() { :; }\n',
     [(3, "filters de #@option 'o' só vale para type=file")]),
    (_HDR + '#@option o type=string needs_step=s group="G"\n#@step s\ns() { :; }\n',
     [(3, "group em #@option 'o' ignorado: a opção fica na linha do step")]),
]


@pytest.mark.parametrize(("text", "exc_type", "line", "message"), ERROS_OPCAO)
def test_erro_de_opcao_com_mensagem_e_linha_exatas(text: str, exc_type: type, line, message: str) -> None:
    with pytest.raises(exc_type) as exc:
        parse_text(text, Path("t.sh"))
    assert exc.value.diagnostic.message == message
    assert exc.value.diagnostic.line == line


@pytest.mark.parametrize(("text", "esperados"), AVISOS_OPCAO)
def test_aviso_de_opcao_com_linha_e_mensagem_exatas(text: str, esperados: list) -> None:
    result = parse_text(text, Path("t.sh"))
    assert [(w.line, w.message) for w in result.warnings] == esperados


ERROS_FAIXA_E_TEXTO = [
    (_HDR + '#@option o type=number min=abc\n#@step s\ns() { :; }\n', ValidationError, 3,
     "min='abc' de #@option 'o' não é número"),
    (_HDR + '#@option o type=number max=abc\n#@step s\ns() { :; }\n', ValidationError, 3,
     "max='abc' de #@option 'o' não é número"),
    (_HDR + '#@option o type=number step=abc\n#@step s\ns() { :; }\n', ValidationError, 3,
     "step='abc' de #@option 'o' não é número"),
    (_HDR + "#@option o type=number step=0\n#@step s\ns() { :; }\n", ValidationError, 3,
     "step='0' de #@option 'o' precisa ser > 0"),
    (_HDR + "#@option o type=number min=5 max=1\n#@step s\ns() { :; }\n", ValidationError, 3,
     "min='5' maior que max='1' em #@option 'o'"),
    (_HDR + "#@option o type=number default=abc\n#@step s\ns() { :; }\n", ValidationError, 3,
     "default='abc' de #@option 'o' não é número"),
    (_HDR + "#@option o type=number min=2 default=1\n#@step s\ns() { :; }\n", ValidationError, 3,
     "default='1' de #@option 'o' abaixo de min='2'"),
    (_HDR + "#@option o type=number max=2 default=3\n#@step s\ns() { :; }\n", ValidationError, 3,
     "default='3' de #@option 'o' acima de max='2'"),
    (_HDR + '#@option o type=string pattern="["\n#@step s\ns() { :; }\n', ValidationError, 3,
     "pattern='[' de #@option 'o' é regex inválida: unterminated character set at position 0"),
    (_HDR + '#@option o type=string pattern="^[a-z]+$" default=ABC\n#@step s\ns() { :; }\n',
     ValidationError, 3, "default='ABC' de #@option 'o' não casa com pattern"),
    (_HDR + "#@option o type=string minlen=x\n#@step s\ns() { :; }\n", ValidationError, 3,
     "minlen='x' de #@option 'o' precisa ser inteiro >= 0"),
    (_HDR + "#@option o type=string maxlen=-1\n#@step s\ns() { :; }\n", ValidationError, 3,
     "maxlen='-1' de #@option 'o' precisa ser inteiro >= 0"),
    (_HDR + "#@option o type=string minlen=5 maxlen=2\n#@step s\ns() { :; }\n", ValidationError, 3,
     "minlen='5' maior que maxlen='2' em #@option 'o'"),
    (_HDR + "#@option o type=string minlen=3 default=ab\n#@step s\ns() { :; }\n", ValidationError, 3,
     "default de #@option 'o' menor que minlen='3'"),
    (_HDR + "#@option o type=string maxlen=2 default=abc\n#@step s\ns() { :; }\n", ValidationError, 3,
     "default de #@option 'o' maior que maxlen='2'"),
]

AVISOS_FAIXA_E_TEXTO = [
    (_HDR + '#@option p type=paragraph label="x" url="https://x"\n#@step s\ns() { :; }\n',
     [(3, "url de #@option 'p' só vale para type=link")]),
    (_HDR + "#@option o type=string min=1\n#@step s\ns() { :; }\n",
     [(3, "min/max/step de #@option 'o' só vale para type=number/slider")]),
    (_HDR + '#@option o type=number pattern="a"\n#@step s\ns() { :; }\n',
     [(3, "pattern/minlen/maxlen de #@option 'o' só vale para string/password/text")]),
    (_HDR + "#@option o type=string multiple=true\n#@step s\ns() { :; }\n",
     [(3, "multiple de #@option 'o' só vale para type=file")]),
]


@pytest.mark.parametrize(("text", "exc_type", "line", "message"), ERROS_FAIXA_E_TEXTO)
def test_erro_de_faixa_e_texto_com_mensagem_exata(text: str, exc_type: type, line, message: str) -> None:
    with pytest.raises(exc_type) as exc:
        parse_text(text, Path("t.sh"))
    assert exc.value.diagnostic.message == message
    assert exc.value.diagnostic.line == line


@pytest.mark.parametrize(("text", "esperados"), AVISOS_FAIXA_E_TEXTO)
def test_aviso_de_faixa_e_texto_com_linha_exata(text: str, esperados: list) -> None:
    result = parse_text(text, Path("t.sh"))
    assert [(w.line, w.message) for w in result.warnings] == esperados


ERROS_STEP_E_CICLO = [
    (_HDR + "#@step s\ns2() { :; }\n", ValidationError, 3,
     "step 's': a função definida é 's2', o id deve ser igual ao nome da função (ou use #@function)"),
    (_HDR + "#@step s\n#@function nope\ns() { :; }\n", ValidationError, 3,
     "função 'nope' do step 's' não encontrada no script"),
    (_HDR + "#@step a\n#@depends zz\na() { :; }\n", ValidationError, 4,
     "#@depends 'zz' do step 'a' aponta para um step inexistente"),
    (_HDR + "#@step a\n#@depends b\na() { :; }\n#@step b\n#@depends a\nb() { :; }\n",
     ValidationError, 3, "ciclo nas dependências: a -> b -> a"),
    (_HDR + '#@option o type=string show_if="o=1"\n#@step s\ns() { :; }\n', ValidationError, 3,
     "show_if de #@option 'o' referencia a si mesma"),
    (_HDR + '#@option a type=string show_if="b=1"\n#@option b type=string show_if="a=1"\n'
     + "#@step s\ns() { :; }\n", ValidationError, 4, "ciclo em show_if: a -> b -> a"),
]

AVISOS_STEP = [
    (_HDR + "#@step a\n#@timeout abc\na() { :; }\n",
     [(4, "#@timeout 'abc' inválido; step sem timeout")]),
    (_HDR + "#@step a\n#@timeout 0\na() { :; }\n",
     [(4, "#@timeout 0 precisa ser > 0; step sem timeout")]),
    (_HDR + "#@step a\n#@on_error talvez\na() { :; }\n",
     [(4, "#@on_error 'talvez' inválido (use stop|continue); usando 'stop'")]),
    (_HDR + "#@step a\n#@default talvez\na() { :; }\n",
     [(4, "#@default 'talvez' inválido (use on|off)")]),
]


@pytest.mark.parametrize(("text", "exc_type", "line", "message"), ERROS_STEP_E_CICLO)
def test_erro_de_step_e_ciclo_com_mensagem_exata(text: str, exc_type: type, line, message: str) -> None:
    with pytest.raises(exc_type) as exc:
        parse_text(text, Path("t.sh"))
    assert exc.value.diagnostic.message == message
    assert exc.value.diagnostic.line == line


@pytest.mark.parametrize(("text", "esperados"), AVISOS_STEP)
def test_aviso_de_step_com_linha_exata(text: str, esperados: list) -> None:
    result = parse_text(text, Path("t.sh"))
    assert [(w.line, w.message) for w in result.warnings] == esperados


CAMPOS_STEP = [
    (_HDR + "#@step a\n#@function f\nf() { :; }\n", "function", "f"),
    (_HDR + "#@step a\na() { :; }\n", "function", "a"),
    (_HDR + '#@step a\n#@title "Olá"\na() { :; }\n', "title", "Olá"),
    (_HDR + "#@step a\na() { :; }\n", "title", "a"),
    (_HDR + '#@step a\n#@group "G"\na() { :; }\n', "group", "G"),
    (_HDR + "#@step a\na() { :; }\n", "group", None),
    (_HDR + "#@step a\n#@timeout 5\na() { :; }\n", "timeout", 5),
    (_HDR + "#@step a\n#@timeout 1\na() { :; }\n", "timeout", 1),
    (_HDR + "#@step a\na() { :; }\n", "timeout", None),
    (_HDR + "#@step a\n#@on_error continue\na() { :; }\n", "on_error", "continue"),
    (_HDR + "#@step a\na() { :; }\n", "on_error", "stop"),
    (_HDR + "#@step a\n#@on_error talvez\na() { :; }\n", "on_error", "stop"),
    (_HDR + "#@step a\n#@on_error   \na() { :; }\n", "on_error", "stop"),
    (_HDR + "#@step a\n#@default on\na() { :; }\n", "default", True),
    (_HDR + "#@step a\n#@default ON\na() { :; }\n", "default", True),
    (_HDR + "#@step a\n#@default off\na() { :; }\n", "default", False),
    (_HDR + "#@step a\na() { :; }\n", "default", True),
    (_HDR + "#@step a\n#@required\na() { :; }\n", "required", True),
    (_HDR + "#@step a\na() { :; }\n", "required", False),
    (_HDR + "#@step a\n#@root\na() { :; }\n", "root", True),
    (_HDR + "#@step a\na() { :; }\n", "root", False),
    (_HDR + "#@step b\nb() { :; }\n#@step c\nc() { :; }\n#@step a\n#@depends b, c\na() { :; }\n",
     "depends", ("b", "c")),
]

AVISOS_STEP_LIMITE = [
    (_HDR + "#@step a\n#@timeout 1\na() { :; }\n", []),
    (_HDR + "#@step a\n#@default ON\na() { :; }\n", []),
    (_HDR + "#@step a\n#@on_error   \na() { :; }\n", []),
    (_HDR + "#@step b\nb() { :; }\n#@step a\n#@depends b\na() { :; }\n", []),
]


@pytest.mark.parametrize(("text", "campo", "esperado"), CAMPOS_STEP)
def test_campo_do_step(text: str, campo: str, esperado: object) -> None:
    script = parse_text(text, Path("t.sh")).script
    step = next(s for s in script.steps if s.id == "a")
    assert getattr(step, campo) == esperado


@pytest.mark.parametrize(("text", "esperados"), AVISOS_STEP_LIMITE)
def test_sem_aviso_nos_valores_de_borda_do_step(text: str, esperados: list) -> None:
    result = parse_text(text, Path("t.sh"))
    assert [(w.line, w.message) for w in result.warnings] == esperados

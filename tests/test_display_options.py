"""§4.3 — `paragraph` e `link`: só exibem texto; não têm valor nem `OPT_*`."""

from __future__ import annotations

from pathlib import Path

import pytest

from kbash.core.errors import ValidationError
from kbash.core.model import is_allowed_link
from kbash.core.parser import parse_text
from kbash.core.planner import build_plan, default_options, option_errors, value_options

SRC = """#!/usr/bin/env bash
#@runtime 1
#@name Demo
#@option intro type=paragraph label="Texto na tela"
#@option ajuda type=link label="Documentação" url="https://example.org/docs"
#@option nome type=string label="Nome" default=ana
#@step s
#@title S
s() { :; }
"""


def parse(source: str):
    return parse_text(source, Path("demo.sh"))


def option_src(line: str) -> str:
    return f"#!/usr/bin/env bash\n#@runtime 1\n#@name X\n{line}\n#@step s\ns() {{ :; }}\n"


def test_display_options_parse_with_their_fields() -> None:
    script = parse(SRC).script
    intro = script.option("intro")
    link = script.option("ajuda")
    assert intro is not None and link is not None
    assert intro.type == "paragraph" and intro.label == "Texto na tela"
    assert link.type == "link" and link.label == "Documentação"
    assert link.url == "https://example.org/docs"
    assert not intro.carries_value and not link.carries_value
    assert script.option("nome").carries_value


def test_display_options_have_no_value_and_no_env() -> None:
    script = parse(SRC).script
    assert [o.id for o in value_options(script)] == ["nome"]
    assert set(default_options(script)) == {"nome"}
    plan = build_plan(script)
    assert plan.options == {"nome": "ana"}
    assert "intro" not in option_errors(script, {"nome": "ana"})


def test_display_option_rejects_a_value_on_the_command_line() -> None:
    script = parse(SRC).script
    with pytest.raises(ValidationError) as error:
        build_plan(script, options={"intro": "x"})
    assert "não recebe valor" in str(error.value)


def test_paragraph_needs_label() -> None:
    with pytest.raises(ValidationError) as error:
        parse(option_src('#@option aviso type=paragraph'))
    assert "exige label" in str(error.value)


def test_link_needs_url() -> None:
    with pytest.raises(ValidationError) as error:
        parse(option_src('#@option ajuda type=link label="Ajuda"'))
    assert "exige url" in str(error.value)


@pytest.mark.parametrize(
    "url",
    ["ftp://example.org/x", "javascript:alert(1)", "file:///etc/passwd", "example.org", "https://", "https://a b.org"],
)
def test_link_refuses_other_schemes(url: str) -> None:
    with pytest.raises(ValidationError) as error:
        parse(option_src(f'#@option ajuda type=link label="Ajuda" url="{url}"'))
    assert "http://" in str(error.value) or "https://" in str(error.value) or "exige" in str(error.value)


@pytest.mark.parametrize("url", ["https://example.org", "http://localhost:8080/a?b=c", "HTTPS://Example.org/x"])
def test_allowed_links(url: str) -> None:
    assert is_allowed_link(url)


@pytest.mark.parametrize("url", ["", "ftp://x", "javascript:alert(1)", "https://", "https://a b", "x"])
def test_refused_links(url: str) -> None:
    assert not is_allowed_link(url)


def test_value_attributes_on_display_options_are_warnings() -> None:
    result = parse(option_src('#@option aviso type=paragraph label="Oi" default=x required=true'))
    messages = " | ".join(str(getattr(w, "message", w)) for w in result.warnings)
    assert "default=" in messages and "required=" in messages

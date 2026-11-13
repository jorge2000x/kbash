"""Léxico mínimo de Bash: heredoc, aspas com escape, comentários e funções sem corpo.

Regressões dos achados da análise do parser: anotação dentro de heredoc virava
metadado; `function f` sem `{` era aceita; `\\"` abria aspa fantasma; `$#` era
cortado como comentário.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kbash.core.errors import ParseError
from kbash.core.parser import parse_text

HEADER = "#!/bin/bash\n#@runtime 1\n#@name X\n"


def parse(body: str):
    return parse_text(HEADER + body, Path("/tmp/x.sh")).script


def opcoes(body: str) -> list[str]:
    return [option.id for option in parse(body).options]


def passos(body: str) -> list[str]:
    return [step.id for step in parse(body).steps]


# -- heredoc: o corpo não é código nem anotação ---------------------------


def test_annotation_inside_heredoc_is_not_metadata() -> None:
    body = "cat <<EOF\n#@option fantasma\n#@type text\nEOF\n"
    assert opcoes(body) == []


def test_annotation_after_heredoc_is_metadata_again() -> None:
    body = "cat <<EOF\n#@option fantasma\nEOF\n#@option real\n#@type text\nreal() { :; }\n"
    assert opcoes(body) == ["real"]


def test_quoted_heredoc_delimiter_is_recognized() -> None:
    body = "cat <<'FIM'\n#@option fantasma\nFIM\n#@option real\n#@type text\nreal() { :; }\n"
    assert opcoes(body) == ["real"]


def test_dash_heredoc_accepts_tab_indented_terminator() -> None:
    body = "cat <<-FIM\n\t#@option fantasma\n\tFIM\n#@option real\n#@type text\nreal() { :; }\n"
    assert opcoes(body) == ["real"]


def test_braces_inside_heredoc_do_not_count() -> None:
    from kbash.core.shell_lex import ShellLexer

    lexer = ShellLexer()
    linhas = ["cat <<EOF", "}", "}", "{", "EOF", "echo ok"]
    assert sum(lexer.feed(linha).brace_delta for linha in linhas) == 0


# -- função sem corpo ------------------------------------------------------


def test_function_head_without_body_is_refused() -> None:
    with pytest.raises(ParseError):
        parse("#@step run\nfunction run\necho hi\n")


def test_function_head_at_end_of_file_is_refused() -> None:
    with pytest.raises(ParseError):
        parse("#@step run\nfunction run\n")


def test_brace_on_next_line_is_accepted() -> None:
    assert passos("#@step run\nfunction run\n{\n:\n}\n") == ["run"]


def test_brace_after_blank_line_is_accepted() -> None:
    assert passos("#@step run\nrun()\n\n{\n:\n}\n") == ["run"]


# -- aspas, escapes e comentários -----------------------------------------


def test_escaped_quote_does_not_open_a_string() -> None:
    # bash aceita: \" é literal, e a chave de fechamento está na mesma linha
    assert passos('#@step f\nf() { echo \\" ; }\n') == ["f"]


def test_comment_after_escaped_quote_is_removed() -> None:
    from kbash.core.shell_lex import ShellLexer

    assert ShellLexer().feed('echo \\" # comentario').code.rstrip() == 'echo \\"'


def test_dollar_hash_is_not_a_comment() -> None:
    from kbash.core.shell_lex import ShellLexer

    assert ShellLexer().feed('echo $# x').code == "echo $# x"


def test_hash_inside_word_is_not_a_comment() -> None:
    from kbash.core.shell_lex import ShellLexer

    assert ShellLexer().feed("echo a#b").code == "echo a#b"


def test_ansi_c_quote_with_escaped_quote_keeps_braces_balanced() -> None:
    from kbash.core.shell_lex import ShellLexer

    assert ShellLexer().feed("echo $'a\\'}'").brace_delta == 0


def test_annotation_inside_multiline_string_is_not_metadata() -> None:
    body = 'echo "linha 1\n#@option fantasma\nlinha 2"\n'
    assert opcoes(body) == []


# -- propriedade: linha sem caracteres especiais é código inalterado ------

_SEGURO = st.text(
    alphabet=st.characters(blacklist_characters="'\"\\#$<{}`", blacklist_categories=("Cs",)),
    max_size=40,
)


@given(_SEGURO)
def test_plain_line_is_returned_unchanged(line: str) -> None:
    from kbash.core.shell_lex import ShellLexer

    scanned = ShellLexer().feed(line)
    assert scanned.code == line
    assert scanned.brace_delta == 0
    assert scanned.literal is False

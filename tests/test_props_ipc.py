"""Propriedades do protocolo IPC (INVARIANTS.md, seção IPC; SPEC §8.3, §16.3)."""

from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st

from kbash.core.ipc import decode_response, encode_response, escape_value, unescape_value, valid_var_key

TEXTO = st.text(max_size=300)
ID_CURTO = st.from_regex(r"[a-z0-9_]{1,12}", fullmatch=True)


@settings(max_examples=500)
@given(TEXTO)
def test_escape_roundtrip(texto: str) -> None:
    assert unescape_value(escape_value(texto)) == texto


@settings(max_examples=300)
@given(st.text(max_size=5000))
def test_uma_linha(texto: str) -> None:
    payload = encode_response("r1", "ok", texto)
    assert payload.endswith(b"\n")
    assert payload.count(b"\n") == 1


# exemplo fixo: a linha passa de 4000 e o corte cai no meio de "\\n" (escape),
# o caso que a propriedade pegaria só por sorte
@example("a" * 3993 + "\n")
@settings(max_examples=300)
@given(st.text(max_size=5000))
def test_truncamento_preserva_prefixo(texto: str) -> None:
    _, _, valor = decode_response(encode_response("r1", "ok", texto))
    assert texto.startswith(valor)


@settings(max_examples=300)
@given(ID_CURTO, st.sampled_from(["ok", "cancel", "error"]), TEXTO)
def test_roundtrip_curto(request_id: str, status: str, valor: str) -> None:
    assert decode_response(encode_response(request_id, status, valor)) == (request_id, status, valor)


@settings(max_examples=300)
@given(st.text(max_size=40))
def test_chave_de_variavel(chave: str) -> None:
    esperado = len(chave) > 0 and chave.isascii() and (
        chave[0].isalpha() or chave[0] == "_"
    ) and all(c.isalnum() or c == "_" for c in chave)
    assert valid_var_key(chave) == esperado

"""Contrato de ``encode_response``: id e status são tokens do §8.3 e não podem quebrar a linha.

Achado do crosshair: ``encode_response("", "\\n", "")`` devolvia duas linhas, porque só o
valor era escapado. TAB e quebra de linha no id ou no status quebram a estrutura; a
pré-condição rejeita esses casos antes de montar a resposta. ``\\r`` não é separador do
§8.3 e fica fora.
"""

from __future__ import annotations

import icontract
import pytest

from kbash.core.ipc import encode_response


@pytest.mark.parametrize(
    ("request_id", "status"),
    [
        ("", "\n"),
        ("r\t1", "ok"),
        ("r1", "o\nk"),
        ("r1", "o\tk"),
        ("a\nb", "ok"),
    ],
)
def test_id_ou_status_com_controle_de_linha_viola_o_contrato(request_id: str, status: str) -> None:
    with pytest.raises(icontract.ViolationError):
        encode_response(request_id, status, "valor")


def test_tokens_validos_continuam_aceitos() -> None:
    assert encode_response("r1", "ok", "a\nb") == b"r1\tok\ta\\nb\n"

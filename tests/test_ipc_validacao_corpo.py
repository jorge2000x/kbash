"""``encode_response`` valida id e status no próprio corpo (§8.3), sem depender de icontract.

Os decoradores ``require`` só checam quando icontract está instalado (dev/CI) e viram
no-op no AppImage. Sem a checagem no corpo, um id com TAB passaria e quebraria o
protocolo. Os testes chamam o corpo cru via ``__wrapped__``.
"""

from __future__ import annotations

import inspect

import pytest

from kbash.core.ipc import IpcError, encode_response

CORPO = inspect.unwrap(encode_response)


@pytest.mark.parametrize(
    ("request_id", "status"),
    [
        ("r\t1", "ok"),
        ("r\n1", "ok"),
        ("r1", "o\tk"),
        ("r1", "o\nk"),
        ("", "\n"),
    ],
)
def test_corpo_recusa_id_ou_status_com_separador(request_id: str, status: str) -> None:
    with pytest.raises(IpcError):
        CORPO(request_id, status, "valor")


def test_corpo_aceita_tokens_validos() -> None:
    assert CORPO("r1", "ok", "a\nb") == b"r1\tok\ta\\nb\n"

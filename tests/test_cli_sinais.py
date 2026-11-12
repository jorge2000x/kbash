"""Cancelamento por sinal no modo headless: cada sinal volta ao seu handler anterior."""

from __future__ import annotations

import signal
from collections.abc import Callable, Iterator
from typing import Any, cast

import pytest

from kbash.cli import _cancela_ao_sinal


def _handler_sentinela(number: int, frame: Any) -> None:  # pragma: no cover - só identidade
    pass


@pytest.fixture
def sinais_originais() -> Iterator[None]:
    """Garante que o teste não deixa handlers instalados no processo do pytest."""
    antigos = {n: signal.getsignal(n) for n in (signal.SIGINT, signal.SIGTERM)}
    try:
        yield
    finally:
        for n, h in antigos.items():
            signal.signal(n, h)


def test_restaura_o_handler_anterior_de_cada_sinal(sinais_originais: None) -> None:
    # SIGTERM e SIGINT com handlers diferentes: o bug restaurava o de SIGINT no SIGTERM
    signal.signal(signal.SIGTERM, _handler_sentinela)
    antes_int = signal.getsignal(signal.SIGINT)

    restaura = _cancela_ao_sinal(lambda: None)
    assert signal.getsignal(signal.SIGTERM) is not _handler_sentinela
    assert signal.getsignal(signal.SIGINT) is not antes_int

    restaura()
    assert signal.getsignal(signal.SIGTERM) is _handler_sentinela
    assert signal.getsignal(signal.SIGINT) is antes_int


def test_sinal_chama_o_cancelamento(sinais_originais: None) -> None:
    chamadas: list[str] = []
    restaura = _cancela_ao_sinal(lambda: chamadas.append("cancelado"))
    try:
        handler = cast(Callable[[int, Any], None], signal.getsignal(signal.SIGTERM))
        handler(signal.SIGTERM, None)
    finally:
        restaura()
    assert chamadas == ["cancelado"]

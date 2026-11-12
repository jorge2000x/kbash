"""Limite de bytes por linha nos leitores de stream (bug 9).

Sem limite, uma linha sem quebra cresce sem parar na memória. Aqui uma linha acima
do limite é descartada (IPC, onde o id só vale com a linha inteira) ou truncada com
marcador (log). A linha seguinte sempre passa.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import IO

from .contratos import ensure, require

__all__ = ["MAX_IPC_LINE", "MAX_LOG_LINE", "LeitorDeLinhas", "linhas_limitadas"]

#: Pedido IPC é um JSON pequeno; acima disso é protocolo inválido.
MAX_IPC_LINE = 256 * 1024
#: Linha de log acima disso é truncada na exibição.
MAX_LOG_LINE = 64 * 1024


class LeitorDeLinhas:
    """Separa linhas de um fluxo de bytes com teto por linha.

    Memória limitada: o pendente nunca passa de ``limite`` bytes entre chamadas.
    ``descartadas`` conta as linhas que estouraram o limite.
    """

    def __init__(self, limite: int) -> None:
        if limite <= 0:
            raise ValueError("limite deve ser positivo")
        self._limite = limite
        self._resto = b""
        self._descartando = False
        self.descartadas = 0

    @ensure(
        lambda self, result: all(len(linha) <= self._limite for linha in result),
        "linha devolvida cabe no limite",
    )
    def alimenta(self, data: bytes) -> list[bytes]:
        """Devolve as linhas completas (sem ``\\n``) que couberam no limite."""
        saida: list[bytes] = []
        buf = data
        while True:
            idx = buf.find(b"\n")
            if idx < 0:
                break
            pedaco, buf = buf[:idx], buf[idx + 1 :]
            if self._descartando:  # fim da linha longa que já foi descartada
                self._descartando = False
                self._resto = b""
                continue
            linha = self._resto + pedaco
            self._resto = b""
            if len(linha) > self._limite:
                self.descartadas += 1
            else:
                saida.append(linha)
        if not self._descartando:
            self._resto += buf
            if len(self._resto) > self._limite:
                self.descartadas += 1
                self._resto = b""
                self._descartando = True
        return saida

    def fecha(self) -> list[bytes]:
        """Fim do fluxo: devolve o pendente sem quebra final, se couber no limite."""
        pendente = [] if self._descartando or not self._resto else [self._resto]
        self._resto = b""
        self._descartando = False
        return pendente


@require(lambda limite: limite > 0, "limite de linha deve ser positivo")
def linhas_limitadas(stream: IO[bytes], limite: int) -> Iterator[tuple[bytes, bool]]:
    """Lê ``stream`` linha a linha, com teto de ``limite`` bytes por linha.

    Devolve ``(conteúdo, truncada)``. Linha truncada é a que passou do limite:
    o resto dela é lido e descartado até a quebra, sem voltar à memória.
    """
    while True:
        bruto = stream.readline(limite)
        if not bruto:
            return
        truncada = not bruto.endswith(b"\n") and len(bruto) >= limite
        if truncada:
            while True:
                resto = stream.readline(limite)
                if not resto or resto.endswith(b"\n"):
                    break
        yield bruto, truncada

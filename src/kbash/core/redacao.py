"""Redação de segredos na saída: valores de opções ``password`` não vão para o log nem para a tela."""

from __future__ import annotations

from collections.abc import Iterable

__all__ = ["MASCARA", "redige"]

#: Texto que substitui o segredo. Não pode aparecer em nenhum segredo real para a
#: garantia valer (ver o teste de propriedade).
MASCARA = "***"


def redige(texto: str, segredos: Iterable[str]) -> str:
    """Troca cada segredo não vazio por ``MASCARA``, do mais longo para o mais curto."""
    for segredo in sorted({valor for valor in segredos if valor}, key=len, reverse=True):
        texto = texto.replace(segredo, MASCARA)
    return texto

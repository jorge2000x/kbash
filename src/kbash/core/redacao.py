"""Redação de segredos na saída: valores de opções ``password`` não vão para o log nem para a tela."""

from __future__ import annotations

from collections.abc import Iterable

from .model import Script

__all__ = ["MASCARA", "redige", "segredos_do_script"]

#: Texto que substitui o segredo. Não pode aparecer em nenhum segredo real para a
#: garantia valer (ver o teste de propriedade).
MASCARA = "***"


def redige(texto: str, segredos: Iterable[str]) -> str:
    """Troca cada segredo não vazio por ``MASCARA``, do mais longo para o mais curto."""
    for segredo in sorted({valor for valor in segredos if valor}, key=len, reverse=True):
        texto = texto.replace(segredo, MASCARA)
    return texto


def segredos_do_script(script: Script, env: dict[str, str]) -> list[str]:
    """Valores em ``env`` (``OPT_*``) das opções ``password`` do script."""
    return [env.get(f"OPT_{option.id.upper()}", "") for option in script.options if option.type == "password"]

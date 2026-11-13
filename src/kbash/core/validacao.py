"""Validação de respostas de prompt number/date/time (§4.3), fonte única para terminal e QML."""

from __future__ import annotations

from .model import is_valid_date, is_valid_number, is_valid_time

__all__ = ["erro_de_entrada"]


# equivalente (mutantes nos padrões): limite não numérico é ignorado, igual a ""
def erro_de_entrada(kind: str, value: str, minimum: str = "", maximum: str = "") -> str:  # pragma: no mutate
    """Mensagem de erro para a resposta de um prompt ``number``/``date``/``time``; ``""`` se válida.

    Vazio é válido: significa "usar o padrão". Limite não numérico é ignorado.
    Usado pelo terminal (``core/ui.py``) e pelo QML (via ``bridge.validateAnswer``).
    """
    texto = value.strip()
    if kind == "number":
        return _erro_numero(texto, minimum, maximum)
    if kind == "date":
        return "" if texto == "" or is_valid_date(texto) else "formato inválido (use AAAA-MM-DD)"
    if kind == "time":
        return "" if texto == "" or is_valid_time(texto) else "formato inválido (use HH:MM)"
    raise ValueError(f"tipo de prompt sem validação: {kind!r}")


def _erro_numero(texto: str, minimum: str, maximum: str) -> str:
    if texto == "":
        return ""
    if not is_valid_number(texto):
        return "digite um número"
    numero = float(texto)
    if _limite_valido(minimum) and numero < float(minimum):
        return f"mínimo: {minimum}"
    if _limite_valido(maximum) and numero > float(maximum):
        return f"máximo: {maximum}"
    return ""


def _limite_valido(limite: str) -> bool:
    # equivalente (mutante "XXXX"): não é número, então já cai em is_valid_number
    return limite != "" and is_valid_number(limite)  # pragma: no mutate

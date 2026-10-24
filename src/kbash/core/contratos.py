"""Contratos do core (SPEC §16.3).

``icontract`` é ferramenta de verificação (``dev``): em testes e no CI os
contratos são checados; no AppImage, que não instala a dependência, os
decoradores viram no-op. Assim o runtime não ganha dependência nova.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:  # dev-only: ver docstring
    import icontract as _icontract
except ImportError:  # pragma: no cover - depende do ambiente de instalação
    _icontract = None

__all__ = ["ensure", "require"]


def require(condition: Callable[..., bool], description: str | None = None) -> Callable[[Any], Any]:
    """Pré-condição: checada na entrada da função."""
    if _icontract is None:
        return lambda func: func
    return _icontract.require(condition, description)


def ensure(condition: Callable[..., bool], description: str | None = None) -> Callable[[Any], Any]:
    """Pós-condição: checada na saída; ``result`` é o valor devolvido."""
    if _icontract is None:
        return lambda func: func
    return _icontract.ensure(condition, description)

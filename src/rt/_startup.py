"""Ajustes de interpretador na partida do `rt` (antes de qualquer import Qt)."""

from __future__ import annotations

import os
import site
import sys

__all__ = ["hide_user_site"]


def hide_user_site() -> bool:
    """Tira o site-packages do usuário (`~/.local`) do `sys.path`.

    O PySide6 do pip mora ali e **não enxerga** os módulos QML do sistema
    (Kirigami, estilo Breeze): o plugin C++ dele exige o Qt da distro.
    Sem isso, a GUI falha com `module "org.kde.kirigami" is not installed`
    mesmo com tudo instalado. Com o site do usuário fora do caminho, vale o
    PySide6 da distro, que carrega o Kirigami normalmente.

    Devolve `True` se removeu algo. `RT_ALLOW_USER_SITE=1` desliga a trava
    (para quem sabe o que está fazendo). Idempotente.
    """
    if os.environ.get("RT_ALLOW_USER_SITE"):
        return False
    try:
        user_base = os.path.realpath(site.getuserbase())
    except (AttributeError, OSError):
        return False
    before = len(sys.path)
    sys.path[:] = [
        entry
        for entry in sys.path
        if os.path.realpath(entry or ".") != user_base
        and not os.path.realpath(entry or ".").startswith(user_base + os.sep)
    ]
    return len(sys.path) != before

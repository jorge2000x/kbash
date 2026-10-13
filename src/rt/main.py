"""Ponto de entrada do `rt`: trava de interpretador + CLI."""

from __future__ import annotations

from . import _startup

_startup.hide_user_site()

from .cli import main  # noqa: E402

__all__ = ["main"]


if __name__ == "__main__":
    import sys

    sys.exit(main())

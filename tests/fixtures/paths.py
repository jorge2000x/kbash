"""Caminhos dos scripts de exemplo usados pelos testes (SPEC.md §13)."""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "scripts"
DEV_SETUP = FIXTURES / "dev-setup.sh"
FAILING = FIXTURES / "failing.sh"
HELPERS = Path(__file__).resolve().parents[2] / "src" / "kbash" / "helpers" / "rt.sh"

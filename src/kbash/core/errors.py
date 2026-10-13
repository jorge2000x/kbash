"""Erros de parse/validação do core (SPEC.md §4.6, §12).

Todos carregam ``arquivo:linha`` para que a CLI e a GUI possam apresentá-los.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "KbashError",
    "Diagnostic",
    "ParseError",
    "ValidationError",
    "PrecheckError",
    "RunCancelled",
    "Diagnostics",
    "ParseResult",
]


class KbashError(Exception):
    """Base de todos os erros do runtime."""


@dataclass(frozen=True)
class Diagnostic:
    """Mensagem localizada com severidade (SPEC.md §4.6)."""

    path: Path | None
    line: int | None
    severity: str  # "error" | "warning"
    message: str

    def __str__(self) -> str:
        where = str(self.path) if self.path is not None else "<script>"
        if self.line is not None:
            where = f"{where}:{self.line}"
        return f"{where}: {self.severity}: {self.message}"

    @property
    def is_error(self) -> bool:
        return self.severity == "error"


class ParseError(KbashError):
    """Erro de sintaxe/anotação; sempre com linha."""

    def __init__(self, message: str, path: Path | None = None, line: int | None = None) -> None:
        super().__init__(message)
        self.diagnostic = Diagnostic(path, line, "error", message)

    def __str__(self) -> str:
        return str(self.diagnostic)


class ValidationError(KbashError):
    """Erro de consistência entre anotações (duplicados, ciclos, Choice...)."""

    def __init__(self, message: str, path: Path | None = None, line: int | None = None) -> None:
        super().__init__(message)
        self.diagnostic = Diagnostic(path, line, "error", message)

    def __str__(self) -> str:
        return str(self.diagnostic)


class PrecheckError(KbashError):
    """Falha das pré-checagens do §7.5 (antes de iniciar qualquer coisa)."""


class RunCancelled(KbashError):
    """Cancelamento pedido pela GUI/CLI."""


class Diagnostics:
    """Acumulador de diagnósticos; usado por ``check`` para listar tudo."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.items: list[Diagnostic] = []

    def error(self, message: str, line: int | None = None) -> None:
        self.items.append(Diagnostic(self.path, line, "error", message))

    def warning(self, message: str, line: int | None = None) -> None:
        self.items.append(Diagnostic(self.path, line, "warning", message))

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.items if d.is_error]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.items if not d.is_error]

    def __bool__(self) -> bool:
        return bool(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> "object":
        return iter(self.items)

"""Biblioteca da tela inicial: os ``.kbash`` da pasta do programa (sem Qt).

Pasta do programa: a pasta onde está o ``.AppImage`` (variável ``APPIMAGE``,
definida pelo runtime do AppImage); fora dele, ``examples/`` do projeto.
Só leitura estática: cada arquivo passa pelo parser, que não executa nada.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import KbashError
from ..core.parser import parse_script

#: Extensão que a biblioteca lista. ``.sh`` continua aceito ao abrir pelo seletor.
LIBRARY_SUFFIX = ".kbash"

#: Fora do AppImage (desenvolvimento): ``src/kbash/gui/library.py`` → raiz → ``examples/``.
DEV_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "examples"


def program_scripts_dir() -> Path:
    """Pasta de onde o programa foi executado: a do ``.AppImage``, se houver."""
    appimage = os.environ.get("APPIMAGE", "")
    if appimage:
        return Path(appimage).resolve().parent
    return DEV_SCRIPTS_DIR


@dataclass(frozen=True)
class LibraryEntry:
    path: Path
    name: str
    description: str
    valid: bool


def list_library(folder: Path | None = None) -> list[LibraryEntry]:
    """Lista os ``.kbash`` de ``folder`` (não recursivo), em ordem de nome.

    Arquivo que não passa no parser aparece desabilitado, com aviso; nunca derruba a lista.
    Pasta inexistente vira lista vazia.
    """
    folder = folder if folder is not None else program_scripts_dir()
    if not folder.is_dir():
        return []
    entries: list[LibraryEntry] = []
    for path in sorted(folder.glob(f"*{LIBRARY_SUFFIX}")):
        if not path.is_file():
            continue
        try:
            script = parse_script(path)
        except (KbashError, OSError):
            entries.append(LibraryEntry(path, path.stem, "não pôde ser lido", valid=False))
            continue
        entries.append(LibraryEntry(path, script.name, script.description, valid=True))
    return entries

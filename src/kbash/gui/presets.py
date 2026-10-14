"""Predefinições de opções, em JSON (sem Qt).

Pasta: ``kbash-config/`` ao lado do programa (a pasta do ``.AppImage``, via
``APPIMAGE``; em desenvolvimento, a raiz do projeto). Um arquivo por script:
``kbash-config/<id-do-script>.json``, com sintaxe simples::

    {
      "Backup casa": {"pasta": "/home/ana/Docs", "conta": "ana@gmail.com"},
      "Backup trabalho": {"pasta": "/home/ana/Trabalho"}
    }

Cada chave externa é o nome da predefinição; cada chave interna é o id de uma
opção (``OPT_<ID>``) e o valor é texto. Senhas (``type=password``) nunca entram:
quem chama filtra antes de salvar.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

CONFIG_DIR_NAME = "kbash-config"
MAX_NAME_LENGTH = 60

#: Raiz do projeto quando o programa não roda de um AppImage.
DEV_ROOT = Path(__file__).resolve().parents[3]


class PresetError(Exception):
    """Predefinição inválida, arquivo corrompido ou nome recusado."""


def program_folder() -> Path:
    """Pasta de onde o programa foi executado: a do ``.AppImage``, se houver."""
    appimage = os.environ.get("APPIMAGE", "")
    if appimage:
        return Path(appimage).resolve().parent
    return DEV_ROOT


def config_dir(folder: Path | None = None) -> Path:
    return (folder if folder is not None else program_folder()) / CONFIG_DIR_NAME


def _file_stem(script_id: str) -> str:
    """Id do script como nome de arquivo seguro (sem separadores de caminho)."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", script_id).strip("_") or "script"


def preset_file(script_id: str, folder: Path | None = None) -> Path:
    return config_dir(folder) / f"{_file_stem(script_id)}.json"


def check_name(name: str) -> str:
    """Nome de predefinição: sem espaços nas pontas, não vazio, uma linha só."""
    cleaned = (name or "").strip()
    if not cleaned:
        raise PresetError("dê um nome à predefinição")
    if "\n" in cleaned or "\r" in cleaned:
        raise PresetError("o nome deve ter uma linha só")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise PresetError(f"o nome passa de {MAX_NAME_LENGTH} caracteres")
    return cleaned


def _as_text(value: object) -> str | None:
    """Valor de JSON → texto de opção; listas, objetos e nulos são recusados."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    return None


def read_presets(script_id: str, folder: Path | None = None) -> dict[str, dict[str, str]]:
    """Predefinições do script. Arquivo ausente é ``{}``; arquivo inválido levanta ``PresetError``."""
    path = preset_file(script_id, folder)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PresetError(f"{path.name} não pôde ser lido: {exc}") from exc
    if not isinstance(data, dict):
        raise PresetError(f"{path.name}: a raiz deve ser um objeto JSON")
    presets: dict[str, dict[str, str]] = {}
    for name, values in data.items():
        if not isinstance(values, dict):
            continue
        clean = {}
        for option_id, value in values.items():
            text = _as_text(value)
            if text is not None and isinstance(option_id, str):
                clean[option_id] = text
        presets[str(name)] = clean
    return presets


def write_presets(
    script_id: str, presets: dict[str, dict[str, str]], folder: Path | None = None
) -> Path:
    """Grava o arquivo do script de forma atômica (arquivo temporário + troca)."""
    path = preset_file(script_id, folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(presets, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path

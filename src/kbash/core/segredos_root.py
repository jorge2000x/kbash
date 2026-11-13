"""Segredos no caminho root (§9.2): as senhas vão pelo stdin do comando root, nunca no argv."""

from __future__ import annotations

import base64
from collections.abc import Callable, Collection, Sequence

from .model import Script

__all__ = ["ROOT_PRELUDE", "nomes_secretos", "prepara_root", "separa_segredos_root"]

#: Prelúdio do comando root: lê as senhas do stdin (uma por linha, ``NOME base64``,
#: terminada por ``END``), exporta-as e fecha o stdin antes de o script rodar.
ROOT_PRELUDE = (
    'while IFS= read -r linha && [ "$linha" != END ]; do '
    'nome=${linha%% *}; valor=$(printf %s "${linha#* }" | base64 -d); export "$nome=$valor"; done; '
    "exec 0</dev/null; "
)


def nomes_secretos(script: Script) -> set[str]:
    """Nomes ``OPT_*`` das opções ``password`` do script."""
    return {f"OPT_{option.id.upper()}" for option in script.options if option.type == "password"}


def separa_segredos_root(env: dict[str, str], nomes: Collection[str]) -> tuple[dict[str, str], bytes]:
    """Separa o ambiente público das senhas. Devolve (público, entrada do stdin)."""
    publico = {chave: valor for chave, valor in env.items() if chave not in nomes}
    linhas = [
        f"{chave} {base64.b64encode(env[chave].encode()).decode()}"
        for chave in sorted(nomes)
        if chave in env
    ]
    return publico, ("\n".join([*linhas, "END"]) + "\n").encode()


RootCommand = Callable[[Sequence[str], dict[str, str], str], list[str]]


def prepara_root(
    step_command: str,
    script: Script,
    env: dict[str, str],
    cwd: str,
    root_command: RootCommand,
) -> tuple[list[str], dict[str, str], bytes]:
    """Monta o comando root de um step ou ação (§9.2).

    Devolve (argv do comando root, ambiente público do processo, entrada do stdin).
    """
    publico, entrada = separa_segredos_root(env, nomes_secretos(script))
    comando = ["bash", "--noprofile", "--norc", "-c", ROOT_PRELUDE + step_command]
    return root_command(comando, publico, cwd), publico, entrada

#!/usr/bin/env python3
"""Métricas de código com radon, com ratchet (só não pode piorar).

* complexidade ciclomática (CC) por função/método, via ``radon cc``;
* índice de manutenibilidade (MI) por arquivo, via ``radon mi``.

Regras do portão:

* uma função **já conhecida** no baseline não pode subir acima do valor registrado;
* uma função **nova** não pode passar de ``--limite-novo`` (padrão 10);
* qualquer função passando de ``--limite-absoluto`` (padrão 40, rank F) falha, mesmo
  que esteja no baseline;
* o MI de um arquivo não pode cair mais que 1 ponto em relação ao baseline.

Atualizar o baseline (depois de uma melhoria, ou de um aumento aprovado)::

    python tools/metricas.py --atualizar

O baseline fica em ``tools/metricas-baseline.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from radon.complexity import cc_visit
from radon.metrics import mi_visit

RAIZ = Path(__file__).resolve().parent.parent
ALVO = RAIZ / "src" / "kbash"
BASELINE = RAIZ / "tools" / "metricas-baseline.json"


Medidas = dict[str, dict[str, Any]]


def coletar(alvo: Path) -> Medidas:
    funcoes: dict[str, int] = {}
    manutenibilidade: dict[str, float] = {}
    for arquivo in sorted(alvo.rglob("*.py")):
        rel = arquivo.relative_to(RAIZ).as_posix()
        codigo = arquivo.read_text(encoding="utf-8")
        for bloco in cc_visit(codigo):
            # bloco.fullname é "Classe.metodo" ou "funcao"; o nome completo evita colisões
            funcoes[f"{rel}::{bloco.fullname}"] = int(bloco.complexity)
        manutenibilidade[rel] = round(float(mi_visit(codigo, multi=True)), 2)
    return {"cc": dict(sorted(funcoes.items())), "mi": dict(sorted(manutenibilidade.items()))}


def comparar(atual: Medidas, base: Medidas, limite_novo: int, limite_absoluto: int) -> list[str]:
    problemas: list[str] = []
    cc_base, mi_base = base["cc"], base["mi"]
    cc_atual, mi_atual = atual["cc"], atual["mi"]

    for nome, valor in cc_atual.items():
        if valor > limite_absoluto:
            problemas.append(f"CC {valor} > {limite_absoluto} (absoluto): {nome}")
        elif nome in cc_base:
            if valor > cc_base[nome]:
                problemas.append(f"CC subiu {cc_base[nome]} -> {valor}: {nome}")
        elif valor > limite_novo:
            problemas.append(f"função nova com CC {valor} > {limite_novo}: {nome}")

    for arquivo, valor in mi_atual.items():
        if arquivo in mi_base and valor < mi_base[arquivo] - 1.0:
            problemas.append(f"MI caiu {mi_base[arquivo]} -> {valor}: {arquivo}")
    return problemas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--atualizar", action="store_true", help="regrava o baseline com o estado atual")
    parser.add_argument("--limite-novo", type=int, default=10)
    parser.add_argument("--limite-absoluto", type=int, default=40)
    args = parser.parse_args(argv)

    atual = coletar(ALVO)
    if args.atualizar:
        BASELINE.write_text(json.dumps(atual, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"baseline gravado: {BASELINE.relative_to(RAIZ)}")
        return 0
    if not BASELINE.exists():
        print("erro: sem baseline; rode com --atualizar", file=sys.stderr)
        return 2
    base: Medidas = json.loads(BASELINE.read_text(encoding="utf-8"))
    problemas = comparar(atual, base, args.limite_novo, args.limite_absoluto)
    maior = max(atual["cc"].values(), default=0)
    print(f"funções: {len(atual['cc'])}, maior CC: {maior}, arquivos: {len(atual['mi'])}")
    for linha in problemas:
        print(f"falha: {linha}", file=sys.stderr)
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())

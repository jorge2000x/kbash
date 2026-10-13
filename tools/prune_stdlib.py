#!/usr/bin/env python3
"""Remove do stdlib do AppDir os módulos que o app não alcança.

    python3 prune_stdlib.py <AppDir> [--trace arquivo.txt] [--dry-run]

Módulos mantidos = união de três fontes:
  1. imports estáticos (AST) de rt/, PySide6/ e shiboken6/ — e, a partir deles,
     os imports dos módulos do stdlib que eles usam (fecho transitivo);
  2. o rastreio de uma execução real (--trace), gerado por tools/trace_stdlib.py
     — cobre imports feitos em C ou por string (importlib), que a análise
     estática não vê;
  3. SEEDS: o mínimo que o interpretador importa na partida.

Quem ficar de fora é removido. Lição do build: "import não exercitado ≠ import
inexistente" — por isso o rastreio é obrigatório e o build roda a checagem de
GUI depois da poda.
"""
import ast
import sys
from pathlib import Path

SEEDS = {
    "site", "os", "stat", "posixpath", "genericpath", "abc", "codecs", "io",
    "encodings", "_collections_abc", "_sitebuiltins", "_sysconfigdata__linux_x86_64-linux-gnu",
    "zipimport", "importlib", "types", "functools", "operator", "keyword",
    "reprlib", "collections", "re", "enum", "warnings", "linecache", "traceback",
    "tokenize", "token", "weakref", "copyreg", "struct", "sre_compile",
    "sre_parse", "sre_constants", "zipfile", "_weakrefset", "_py_abc", "contextlib",
}


def imports_of(path: Path) -> set:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, ValueError):
        return set()
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.add(node.module.split(".")[0])
    return out


def stdlib_files(std: Path, name: str):
    pkg = std / name / "__init__.py"
    if pkg.exists():
        return list((std / name).rglob("*.py"))
    mod = std / f"{name}.py"
    return [mod] if mod.exists() else []


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    app = Path(sys.argv[1]).resolve()
    dry = "--dry-run" in sys.argv
    trace = None
    if "--trace" in sys.argv:
        trace = Path(sys.argv[sys.argv.index("--trace") + 1])

    std = app / "usr/lib/python3.11"
    site = std / "site-packages"
    dyn = std / "lib-dynload"

    # 1. imports estáticos de rt/ e dos pacotes Python do bundle
    alvo = []
    alvo += list((app / "rt").rglob("*.py"))
    alvo += list((site / "PySide6").rglob("*.py"))
    alvo += list((site / "shiboken6").rglob("*.py"))
    nomes = set(SEEDS)
    for f in alvo:
        nomes |= imports_of(f)

    # 2. rastreio de execução real
    if trace and trace.exists():
        nomes |= {l.strip() for l in trace.read_text().splitlines() if l.strip()}

    # fecho transitivo pelo próprio stdlib
    alcancados = set()
    pilha = list(nomes)
    while pilha:
        n = pilha.pop()
        if n in alcancados:
            continue
        alcancados.add(n)
        for f in stdlib_files(std, n):
            pilha.extend(imports_of(f))

    removidos, bytes_rem = [], 0
    for e in sorted(std.iterdir()):
        if e.name in ("site-packages", "lib-dynload"):
            continue
        nome = e.name[:-3] if e.name.endswith(".py") else e.name
        if nome in alcancados or e.name.startswith("__pycache__"):
            continue
        if e.name == "__pycache__":
            pass
        tam = sum(f.stat().st_size for f in e.rglob("*") if f.is_file()) if e.is_dir() else e.stat().st_size
        removidos.append(e.name)
        bytes_rem += tam
        if not dry:
            if e.is_dir():
                import shutil
                shutil.rmtree(e)
            else:
                e.unlink()

    if dyn.exists():
        for so in sorted(dyn.glob("*.so")):
            modulo = so.name.split(".")[0]
            if modulo in alcancados:
                continue
            removidos.append(f"lib-dynload/{so.name}")
            bytes_rem += so.stat().st_size
            if not dry:
                so.unlink()

    acao = "removeria" if dry else "removeu"
    print(f"prune_stdlib: {acao} {len(removidos)} entradas, {bytes_rem/1e6:.1f} MB")
    for n in removidos:
        print(f"  - {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Remove do AppDir as bibliotecas .so que nada carregado pelo app alcança.

    python3 prune_unused_libs.py <AppDir> [--dry-run]

Raízes = o que o app REALMENTE carrega: módulos de extensão do PySide6/shiboken,
plugins Qt (platforms, imageformats, styles...), módulos QML e plugins QML.
A partir delas, segue-se o NEEDED (readelf -d) transitivamente. Todo .so de
bibliotecas que não é alcançado é removido (com seus symlinks).

Por que não é só uma lista fixa: o conjunto muda com a versão do Qt/KF6 e com
o que o app importa. A análise mede isso a cada build.

Limite conhecido: dlopen() por nome em código que não é plugin nem módulo
(não existe no caminho deste app). Se um dia existir, o app falha ao carregar
aquilo — por isso o build roda a suíte de smoke depois.
"""
import re
import subprocess
import sys
from pathlib import Path


def needed(elf: Path):
    out = subprocess.run(["readelf", "-d", str(elf)],
                         capture_output=True, text=True).stdout
    return re.findall(r"Shared library: \[(.*?)\]", out)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    app = Path(sys.argv[1]).resolve()
    dry = "--dry-run" in sys.argv
    site = app / "usr/lib/python3.11/site-packages"
    ps = site / "PySide6"
    lib_dirs = [app / "usr/lib/x86_64-linux-gnu", ps / "Qt/lib"]

    roots = []
    roots += list(ps.glob("*.abi3.so")) + list((site / "shiboken6").glob("*.so*"))
    roots += list((ps / "Qt/plugins").rglob("*.so"))
    roots += list((app / "usr/lib/qtplugins").rglob("*.so"))
    roots += list((app / "usr/lib/qml").rglob("*.so"))
    roots += list((ps / "Qt/qml").rglob("*.so"))

    def find(name):
        for d in lib_dirs:
            p = d / name
            if p.exists():
                return p.resolve()
        return None

    alcancadas = set()
    pilha = [r.resolve() for r in roots if r.is_file()]
    while pilha:
        f = pilha.pop()
        if f in alcancadas:
            continue
        alcancadas.add(f)
        for n in needed(f):
            p = find(n)
            if p is not None and p not in alcancadas:
                pilha.append(p)

    removidas, bytes_livres = [], 0
    for d in lib_dirs:
        for f in sorted(d.glob("*.so*")):
            if f.is_symlink():
                continue
            if f.resolve() in alcancadas:
                continue
            tam = f.stat().st_size
            links = [l for l in d.glob("*.so*") if l.is_symlink() and l.resolve() == f.resolve()]
            removidas.append(f.name)
            bytes_livres += tam
            if not dry:
                f.unlink()
                for l in links:
                    l.unlink()

    acao = "removeria" if dry else "removeu"
    print(f"prune: {acao} {len(removidas)} libs não alcançadas, {bytes_livres/1e6:.1f} MB")
    for n in removidas:
        print(f"  - {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

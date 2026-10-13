#!/usr/bin/env bash
# build-icu-data.sh — libicudata.so.73 do ICU 73.2 com dados só de en, pt e root.
#
#   ./build-icu-data.sh <pasta-de-trabalho> <saida-libicudata.so.73>
#
# Por quê: o libicudata do wheel do PySide6 (Qt 6.10) tem ~32 MB, quase tudo de
# locales que o app não usa. Recompilado com ~2.950 itens a menos, fica com
# ~13,7 MB. Mesmo soname (libicudata.so.73) e mesmo símbolo exportado
# (icudt73_dat): o Qt carrega sem mudar nada. Medido: pt-BR, en-US, colação e
# caixa alta dão saída idêntica com a lib antiga e com a nova.
#
# Limite: locales fora de en/pt caem para root (inglês neutro). Este app é pt/en.
#
# Como: o tarball do ICU traz data/in/icudt73l.dat (o pacote binário completo).
# O icupkg remove dele os locales que não são root/en/pt; depois o build normal
# do ICU gera a lib a partir desse pacote. Custo: ~30 min em 2 núcleos.
set -euo pipefail

TRAB="${1:?uso: build-icu-data.sh <pasta-de-trabalho> <saida.so>}"
SAIDA="${2:?uso: build-icu-data.sh <pasta-de-trabalho> <saida.so>}"
TGZ="icu4c-73_2-src.tgz"
URL="https://github.com/unicode-org/icu/releases/download/release-73-2/$TGZ"

mkdir -p "$TRAB" && cd "$TRAB"
[ -f "$TGZ" ] || curl -sSfL -o "$TGZ" "$URL"
[ -d icu/source ] || tar xzf "$TGZ"
SRC="$TRAB/icu/source"

# 1. ferramentas do ICU (icupkg) — precisam estar compiladas
if [ ! -x "$SRC/bin/icupkg" ]; then
    (cd "$SRC" && ./runConfigureICU Linux --enable-shared --disable-static \
        --disable-tests --disable-samples --disable-extras --disable-layoutex \
        --disable-icuio --disable-dyload > "$TRAB/configure.log" 2>&1 \
     && make -j"$(nproc)" tools > "$TRAB/tools.log" 2>&1)
fi
export LD_LIBRARY_PATH="$SRC/lib:$SRC/stubdata"

# 2. filtra o pacote: mantém root, en e pt; remove outros locales.
#    O nome do arquivo tem de ser icudt73l.dat (o icupkg usa o nome como prefixo).
mkdir -p "$TRAB/filtro/out"
cp -f "$SRC/data/in/icudt73l.dat" "$TRAB/filtro/icudt73l.dat"
"$SRC/bin/icupkg" -l -o "$TRAB/filtro/itens.txt" "$TRAB/filtro/icudt73l.dat"
python3 - "$TRAB/filtro" <<'PY'
import re, sys
from pathlib import Path
d = Path(sys.argv[1])
LOC_DIRS = {'curr','zone','lang','region','unit','coll','rbnf','brkitr','translit'}
remover = []
for it in (d/'itens.txt').read_text().split():
    nome = it.split('/', 1)[1] if it.startswith('icudt73l/') else it
    partes = nome.split('/')
    base = partes[-1]
    if not base.endswith('.res'):
        continue
    lang = base[:-4].split('_')[0]
    if (len(partes) == 1 or partes[0] in LOC_DIRS) and lang != 'root' \
            and lang not in ('en', 'pt') and re.fullmatch(r'[a-z]{2,3}', lang):
        remover.append(it)
(d/'remover.txt').write_text('\n'.join(remover) + '\n')
print(f"icupkg: removendo {len(remover)} itens de locale")
PY
"$SRC/bin/icupkg" -r "$TRAB/filtro/remover.txt" "$TRAB/filtro/icudt73l.dat" "$TRAB/filtro/out/icudt73l.dat"

# 3. usa o pacote filtrado como fonte e compila a lib
cp -f "$TRAB/filtro/out/icudt73l.dat" "$SRC/data/in/icudt73l.dat"
rm -rf "$SRC/data/out"
(cd "$SRC" && make -j"$(nproc)" > "$TRAB/build.log" 2>&1)

ACHADO="$SRC/lib/libicudata.so.73.2"
[ -f "$ACHADO" ] || { echo "erro: libicudata não gerado — veja $TRAB/build.log" >&2; exit 1; }
cp -L "$ACHADO" "$SAIDA"
strip --strip-unneeded "$SAIDA" 2>/dev/null || true
echo "ok: $SAIDA ($(du -h "$SAIDA" | cut -f1))"

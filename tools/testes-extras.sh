#!/usr/bin/env bash
# testes-extras.sh — checagens que complementam o portão (tools/verificar.sh):
#
#   1. fuzzing do parser (tools/fuzz_parser.py) com sementes fixas: reprodutível;
#   2. métricas radon com ratchet (tools/metricas.py): nenhuma função piora no baseline;
#   3. testes de GUI com pytest-qt (tests/test_gui_qtbot.py): pulados, com motivo,
#      quando o Kirigami do sistema não existe.
#
# Rode a cada mudança grande, antes do PR:
#     tools/testes-extras.sh
# Variáveis: PYTHON (padrão: python3), FUZZ_ITERACOES (padrão 5000), FUZZ_SEMENTES
# (padrão "1 2 3"). Sai com código != 0 no primeiro passo que falhar.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
RAIZ="$(cd "$HERE/.." && pwd)"
PY="${PYTHON:-python3}"
ITERACOES="${FUZZ_ITERACOES:-5000}"
SEMENTES="${FUZZ_SEMENTES:-1 2 3}"
cd "$RAIZ"
export PYTHONPATH="$RAIZ/src${PYTHONPATH:+:$PYTHONPATH}"
# pytest-qt sem display: offscreen. Em máquina com X/Wayland, basta exportar antes.
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"

echo "== 1/3 fuzzing do parser ($ITERACOES entradas por semente; sementes: $SEMENTES)"
for semente in $SEMENTES; do
    "$PY" tools/fuzz_parser.py --iteracoes "$ITERACOES" --semente "$semente" \
        --saida "$RAIZ/.fuzz-crashes" --relatorio "$RAIZ/.fuzz-relatorio-$semente.json" >/dev/null || {
        echo "falha: fuzzing encontrou problema com semente $semente. Casos em .fuzz-crashes/" >&2
        exit 1
    }
    echo "   semente $semente: ok"
done

echo "== 2/3 métricas radon (ratchet contra tools/metricas-baseline.json)"
"$PY" tools/metricas.py

echo "== 3/3 testes de GUI com pytest-qt"
"$PY" -m pytest tests/test_gui_qtbot.py -q -rs -p no:cacheprovider --timeout=120

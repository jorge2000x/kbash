#!/usr/bin/env bash
# Portão único de verificação do core (SPEC.md §16.4). Para no primeiro erro.
#
#   tools/verificar.sh                 # portão completo, mutmut incluso (§16)
#   PULAR_MUTMUT=1 tools/verificar.sh  # sem o passo 5 (mutmut é opcional no CI)
#   BASE=HEAD~3 tools/verificar.sh     # base usada só no cálculo de mutmut incremental
#
# Requer: pip install -e ".[dev]" (ruff, pyright, pytest, hypothesis, icontract,
# crosshair-tool, mutmut). PYTHON aponta o interpretador (padrão: python3).
set -euo pipefail

cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
BASE="${BASE:-origin/main}"
export PYTHONNOUSERSITE=1 QT_QPA_PLATFORM=offscreen

# funções puras que o crosshair analisa (§16.3)
CROSSHAIR_ALVOS=(
    kbash.core.planner.resolve
    kbash.core.parser.parse_text
    kbash.core.ipc.encode_response
    kbash.core.ipc.escape_value
    kbash.core.ipc.unescape_value
    kbash.core.actions.action_env
)

echo "== 1/5 ruff (repositório inteiro)"
"$PY" -m ruff check .

echo "== 2/5 pyright (core)"
"$PY" -m pyright --pythonpath "$(command -v "$PY")"

echo "== 3/5 pytest (core; a GUI exige Kirigami e display)"
"$PY" -m pytest tests/ -q --ignore=tests/test_gui.py --ignore=tests/test_ui.py

echo "== 4/5 crosshair (funções puras, tempo limitado por condição)"
(cd src && "$PY" -m crosshair check "${CROSSHAIR_ALVOS[@]}" \
    --per_condition_timeout 8 --per_path_timeout 2)

if [ "${PULAR_MUTMUT:-0}" = "1" ]; then
    echo "== 5/5 mutmut: pulado (PULAR_MUTMUT=1; ver a job opcional no CI)"
    echo "verificação ok (sem mutmut)"
    exit 0
fi
echo "== 5/5 mutmut (módulos críticos; sobrevivente é falha)"
"$PY" -m mutmut run
SOBREVIVENTES=$("$PY" -m mutmut results | grep -cE "survived|no tests" || true)
if [ "$SOBREVIVENTES" -ne 0 ]; then
    echo "falha: $SOBREVIVENTES mutante(s) sobreviveram. Veja: mutmut results / mutmut show <id>" >&2
    echo "Mutante equivalente? Marque com '# pragma: no mutate' e o motivo (§16.4)." >&2
    exit 1
fi
echo "verificação ok"

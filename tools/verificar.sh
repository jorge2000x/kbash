#!/usr/bin/env bash
# Portão único de verificação do core (SPEC.md §16.4). Para no primeiro erro.
#
#   tools/verificar.sh            # compara com origin/main e checa só o que mudou
#   BASE=HEAD~3 tools/verificar.sh
#
# Requer: pip install -e ".[dev]" (ruff, pyright, pytest, hypothesis, icontract,
# crosshair-tool, mutmut). PYTHON aponta o interpretador (padrão: python3).
set -euo pipefail

cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
BASE="${BASE:-origin/main}"
export PYTHONNOUSERSITE=1 QT_QPA_PLATFORM=offscreen

# módulos críticos (§16.1) e funções puras que o crosshair analisa (§16.3)
CRITICOS=(
    src/kbash/core/parser.py
    src/kbash/core/planner.py
    src/kbash/core/ipc.py
    src/kbash/core/actions.py
)
CROSSHAIR_ALVOS=(
    kbash.core.planner.resolve
    kbash.core.parser.parse_text
    kbash.core.ipc.encode_response
    kbash.core.ipc.escape_value
    kbash.core.ipc.unescape_value
    kbash.core.actions.action_env
)

# arquivos Python alterados em relação à base, somados aos críticos
ALTERADOS=$(git diff --name-only --diff-filter=ACMR "$BASE" -- '*.py' 2>/dev/null || true)
ALVOS_LINT=$(printf '%s\n' "${CRITICOS[@]}" $ALTERADOS | sort -u | grep -E '\.py$' || true)

echo "== 1/5 ruff (alterados + críticos)"
# shellcheck disable=SC2086  # a lista é de caminhos sem espaços
"$PY" -m ruff check $ALVOS_LINT

echo "== 2/5 pyright (core)"
"$PY" -m pyright

echo "== 3/5 pytest (core; a GUI exige Kirigami e display)"
"$PY" -m pytest tests/ -q --ignore=tests/test_gui.py --ignore=tests/test_ui.py

echo "== 4/5 crosshair (funções puras, tempo limitado por condição)"
(cd src && "$PY" -m crosshair check "${CROSSHAIR_ALVOS[@]}" \
    --per_condition_timeout 8 --per_path_timeout 2)

echo "== 5/5 mutmut (módulos críticos; sobrevivente é falha)"
"$PY" -m mutmut run
SOBREVIVENTES=$("$PY" -m mutmut results | grep -cE "survived|no tests" || true)
if [ "$SOBREVIVENTES" -ne 0 ]; then
    echo "falha: $SOBREVIVENTES mutante(s) sobreviveram. Veja: mutmut results / mutmut show <id>" >&2
    echo "Mutante equivalente? Marque com '# pragma: no mutate' e o motivo (§16.4)." >&2
    exit 1
fi
echo "verificação ok"

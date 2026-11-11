#!/usr/bin/env bash
# gui-completo.sh — roda a suíte de GUI (test_gui, test_ui, test_gui_qtbot) contra o Kirigami
# do Ubuntu 26.04, no mesmo ambiente do AppImage:
#
#   1. constrói o AppImage com tools/build-appimage.sh (baixa os .deb de breeze-debs.txt);
#   2. extrai o AppImage e carrega as variáveis do AppRun (QML, Qt, bibliotecas);
#   3. roda o pytest da GUI com QT_QPA_PLATFORM dado (padrão offscreen).
#
# Requer: Python 3.11 com ``pip install -e ".[dev]" pytest-qt pytest-timeout``, e o
# appimagetool extraído em $APPIMAGETOOL (ver .github/workflows/verificacao.yml).
# Variáveis: PYTHON, DEBS (pasta com os .deb), SAIDA (padrão ./dist-gui), QT_QPA_PLATFORM.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"
# O build copia o Python e a stdlib do interpretador deste venv (no runner, não há
# /usr/bin/python3.11). readlink segue o symlink até o binário real.
export PY_BIN="${PY_BIN:-$(readlink -f "$PY")}"
export PY_STD="${PY_STD:-$("$PY" -c 'import sysconfig; print(sysconfig.get_paths()["stdlib"])')}"
SAIDA="${SAIDA:-$RAIZ/dist-gui}"
mkdir -p "$SAIDA"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"

echo "== 1/3 AppImage (tools/build-appimage.sh)"
"$RAIZ/tools/build-appimage.sh" "$RAIZ" "$SAIDA/kbash-gui.AppImage"

echo "== 2/3 extração e ambiente do AppRun"
rm -rf "$SAIDA/appdir"
(cd "$SAIDA" && ./kbash-gui.AppImage --appimage-extract >/dev/null && mv squashfs-root appdir)
APPDIR="$SAIDA/appdir"
HERE="$APPDIR"
# shellcheck disable=SC2046  # só linhas "export ..." do AppRun, sem substituições perigosas
# PYTHONHOME/PYTHONPATH do AppRun apontam para a stdlib podada; o venv precisa da sua
eval "$(grep '^export' "$APPDIR/AppRun" | grep -v -E 'RT_PLATFORM|PYTHONHOME|PYTHONPATH')"
export PYTHONPATH="$RAIZ/src:$APPDIR${PYTHONPATH:+:$PYTHONPATH}"

echo "== 3/3 pytest da GUI (um processo por arquivo: um abort do Qt não esconde os outros)"
cd "$RAIZ"
falhou=0
# Os testes de portal (D-Bus) precisam de um barramento de sessão próprio. Sem
# dbus-run-session eles são pulados com o motivo, em vez de travarem esperando o bus.
envolve=()
if command -v dbus-run-session >/dev/null 2>&1; then
    envolve=(dbus-run-session --)
fi
for arquivo in tests/test_gui.py tests/test_ui.py tests/test_gui_qtbot.py; do
    set +e
    "${envolve[@]}" "$PY" -m pytest "$arquivo" -q -rs -p no:cacheprovider --timeout=180
    codigo=$?
    set -e
    if [ "$codigo" -ne 0 ]; then
        echo "falha: $arquivo terminou com código $codigo" >&2
        falhou=1
    fi
done
exit "$falhou"

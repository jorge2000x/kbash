#!/usr/bin/env bash
# build-appimage.sh — monta o AppDir enxuto do `rt` e gera o AppImage.
#
#   ./build-appimage.sh <repo-rt> <saida.AppImage>
#
# Estratégia: AppImage AUTOCONTIDO (Plano A caminho C do handoff).
#   * PySide6 **do pip, pinado em 6.10.2** — o Qt tem de ser o MESMO dos
#     pacotes Ubuntu (qt6-base-private-abi 6.10.2), senão o Breeze/KF6 não carrega
#   * Kirigami + Breeze + libs KF6 dos .deb do Ubuntu 26.04 (tools/breeze-debs.txt)
#   * Python da distro, embutido e podado pelo que o runtime realmente importa
#
# O que este script NÃO faz (e por quê):
#   * não corta ICU (libicudata, 30 MB): exige recompilar o Qt. B5 do plano.
#   * não faz UPX: quebra o carregador de plugins do Qt.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="${1:?uso: build-appimage.sh <repo-rt> <saida.AppImage>}"
SAIDA="${2:?uso: build-appimage.sh <repo-rt> <saida.AppImage>}"
VENV="${VENV:-/tmp/venv}"
DEBS="${DEBS:-/tmp/debs/x}"
BUILD="${BUILD:-/tmp/appdir}"
SP="$VENV/lib/python3.14/site-packages"
# O Qt do PySide6 TEM de ser o mesmo dos pacotes Ubuntu (6.10.2), senão os
# plugins do Breeze/KF6 não carregam (qt6-base-private-abi). Falha cedo, aqui.
QT_ESPERADO=6.10.2
ls -d "$SP"/[Pp]y[Ss]ide6*-"$QT_ESPERADO".dist-info >/dev/null 2>&1 || {
    echo "erro: o VENV precisa de PySide6 == $QT_ESPERADO (Qt dos pacotes Ubuntu)" >&2
    echo "  $VENV/bin/pip install PySide6-Essentials==$QT_ESPERADO" >&2
    exit 1
}
# PAYLOAD vazio (PAYLOAD=) gera um bundle sem script: abre a tela inicial (home)
PAYLOAD="${PAYLOAD-$REPO/examples/sober-optimizer.sh}"

APP="$BUILD/usr"
log() { printf '\033[36m==>\033[0m %s\n' "$*"; }

# ---------------------------------------------------------------------------
# 1. Python embutido
# ---------------------------------------------------------------------------
log "Python (binário estático: não precisa de libpython.so)"
rm -rf "$BUILD"; mkdir -p "$APP/bin" "$APP/lib/python3.14"
cp /usr/bin/python3.14 "$APP/bin/python3"
ln -sf python3 "$APP/bin/python"

log "stdlib do Python, podada (§A2.3/A2.4)"
cp -a /usr/lib/python3.14/. "$APP/lib/python3.14/"
find "$APP/lib/python3.14" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$APP/lib/python3.14" -name '*.pyc' -delete 2>/dev/null || true

# Estratégia de poda do stdlib: lista de REMOÇÃO, não de keep-list.
#
# A primeira versão deste script derivou a keep-list do fluxo headless
# (modprobe_battery: 133 módulos) e QUEBROU a GUI: shiboken6 importa zipfile,
# que o headless nunca toca, e o bundle morria com "No module named zipfile".
# Lição: import não exercitado ≠ import inexistente. A GUI carrega bem mais.
#
# Então: remove-se só o que é inerte por construção (REPL, TUI, multimídia,
# servidores de rede) e MANTÉM-SE TUDO O MAIS. O stdlib inteiro são 20 MB; a
# poda agressiva economizava ~5 MB e custava a GUI inteira. Não vale.
readonly REMOVER_STDLIB="
tkinter idlelib turtledemo turtle ensurepip curses sqlite3 cgi imghdr sndhdr
sunau aifc wave audioop pydoc pydoc_data doctest test venv distutils lib2to3
curses smtpd ftplib imaplib poplib nntplib telnetlib wsgiref xmlrpc pdb bdb
cProfile profile pstats difflib netrc
"
prune_dir() {
    local dir="$1"; shift
    for e in "$dir"/*; do
        [ -e "$e" ] || continue
        local nome
        nome="$(basename "$e")"; nome="${nome%.py}"
        for k in "$@"; do
            k="${k%.py}"
            if [ "$nome" = "$k" ]; then rm -rf "$e"; break; fi
        done
    done
}
prune_dir "$APP/lib/python3.14" $REMOVER_STDLIB

# ---------------------------------------------------------------------------
# 2. PySide6 (do pip) podado
# ---------------------------------------------------------------------------
log "PySide6 do pip + shiboken6"
mkdir -p "$APP/lib/python3.14/site-packages"
cp -a "$SP/PySide6" "$SP/shiboken6" "$SP/PySide6_Essentials"*.dist-info \
      "$APP/lib/python3.14/site-packages/" 2>/dev/null || \
cp -a "$SP/PySide6" "$SP/shiboken6" "$APP/lib/python3.14/site-packages/"
rm -rf "$APP/lib/python3.14/site-packages"/__pycache__

# 2.1 traduções: 196 arquivos, 14 MB → só pt_BR + en + os base
log "A2.6 traduções do Qt (14 MB → ~1 MB)"
TR="$APP/lib/python3.14/site-packages/PySide6/Qt/translations"
if [ -d "$TR" ]; then
    find "$TR" -name '*.qm' ! -name 'qtbase_pt_BR*' ! -name 'qtbase_en*' \
         ! -name 'qt_*.qm' ! -name 'qtdeclarative_pt_BR*' -delete
fi

# 2.2 módulos QML: mantém só o fecho do projeto (medido: QtQuick, Controls,
#     Layouts, org.kde.kirigami) + Templates/Window/Shapes, deps de Controls.
log "B2 módulos QML"
QM="$APP/lib/python3.14/site-packages/PySide6/Qt/qml"
# mesma lógica: remove o que é certo, mantém o resto do QtQuick
prune_dir "$QM" QtTest QtMultimedia QtWebEngine QtWebSockets QtCharts QtDataVis \
              QtQuick3D QtPositioning QtBluetooth QtSerialPort QtTextToSpeech
[ -d "$QM/QtQuick" ] && prune_dir "$QM/QtQuick" VirtualKeyboard Pdf Particles \
              Timeline VectorImage tooling
# estilos QQC: só o Basic. Atenção: tem MUITO mais do que se imagina —
# FluentWinUI3 sozinho tem 8,2 MB, e nem aparece na lista "óbvia"
# (Basic, Fusion, Material, Universal, Imagine, Windows, macOS).
if [ -d "$QM/QtQuick/Controls" ]; then
    prune_dir "$QM/QtQuick/Controls" FluentWinUI3 FluentWinUI Material Fusion \
              Imagine Universal Windows MacOS designer
fi
rm -rf "$QM/QtQuick/VirtualKeyboard" "$QM/QtQuick/Pdf" "$QM/QtQuick/Particles" \
       "$QM/QtQuick/Timeline" "$QM/QtQuick/VectorImage" "$QM/QtQuick/tooling" \
       "$QM/Qt/labs" "$QM/QtTest" "$QM/QtNetwork" "$QM/QtWayland" \
       "$QM/QtMultimedia" "$QM/QtWebEngine" 2>/dev/null || true

# 2.3 .so do Qt: poda por lista.
#     FORA: Widgets (o projeto não importa QtWidgets — medido), Designer*,
#     estilos QQC além do Basic, WaylandCompositor (somos app, não compositor),
#     QmlCompiler (é ferramenta de build, não runtime).
#     DENTRO: libicudata/libicui18n/libicuuc (37 MB!). O QtCore linka neles e
#     morre com "cannot open shared object file" se sumirem. Cortar o ICU é o
#     corte B5 do plano e exige RECOMPILAR o Qt com dados filtrados — não dá
#     para fazer pós-hoc. É o maior item que sobrou, e é o preço da GUI.
log "B3 .so do Qt (corte por lista — ICU fica)"
QL="$APP/lib/python3.14/site-packages/PySide6/Qt/lib"
for lib in libQt6Widgets.so.6 libQt6Designer.so.6 libQt6DesignerComponents.so.6 \
           libQt6QuickControls2Imagine.so.6 libQt6QuickControls2Material.so.6 \
           libQt6QuickControls2Universal.so.6 libQt6QuickControls2Fusion.so.6 \
           libQt6LabsStyleKit.so.6 libQt6WaylandCompositor.so.6 \
           libQt6QmlCompiler.so.6; do
    rm -f "$QL/$lib" "$QL/$lib".* 2>/dev/null || true
done

# 2.4 plugins de plataforma: mantém xcb, wayland, offscreen, imageformats
log "B1 plugins de plataforma"
PL="$APP/lib/python3.14/site-packages/PySide6/Qt/plugins"
if [ -d "$PL" ]; then
    for d in "$PL"/*/; do
        b="$(basename "$d")"
        case "$b" in
            platforms|platformthemes|platforminputcontexts|generic|imageformats|iconengines|\
            xcbglintegrations|wayland-*|tls|networkinformation|styles|sqldrivers|printsupport) ;;
            *) rm -rf "$d" ;;
        esac
    done
    # dentro de platforms/: só o que roda
    [ -d "$PL/platforms" ] && find "$PL/platforms" -name '*.so' \
        ! -name 'libqxcb.so' ! -name 'libqwayland*.so' ! -name 'libqoffscreen.so' -delete
fi

# 2.5 bindings Python: só os 5 módulos que o projeto importa
log "B4 bindings PySide6 (só QtCore/QtGui/QtQml/QtQuick/QtDBus)"
PS="$APP/lib/python3.14/site-packages/PySide6"
KEEP="QtCore.py QtGui.py QtQml.py QtQuick.py QtDBus.py QtNetwork.py Qt.py __init__.py"
for f in "$PS"/*.py; do
    b="$(basename "$f")"
    case " $KEEP " in *" $b "*) ;; *) rm -f "$f" ;; esac
done
rm -rf "$PS"/QtWebEngine* "$PS"/Qt3D* "$PS"/QtCharts* "$PS"/QtMultimedia* \
       "$PS"/QtQuick3D* "$PS"/QtPrintSupport* "$PS"/QtSql* "$PS"/QtTest* \
       "$PS"/QtDesigner* "$PS"/QtHelp* "$PS"/QtBluetooth* "$PS"/QtPositioning* \
       "$PS"/QtSerialPort* "$PS"/QtWebSockets* "$PS"/QtWebChannel* \
       "$PS"/QtTextToSpeech* "$PS"/QtSensors* "$PS"/QtSpatialAudio* \
       "$PS"/QtHttpServer* "$PS"/QtScxml* "$PS"/QtStateMachine* \
       "$PS"/QtStateMachine* "$PS"/QtUiTools* "$PS"/QtPdf* "$PS"/QtQuickWidgets* \
       "$PS"/typesystems 2>/dev/null || true
find "$PS" -maxdepth 1 -name '*.pyi' -delete 2>/dev/null || true
# Os bindings são .abi3.so — a poda por nome de MÓDULO acima não pega eles.
# QtWidgets (5,8 MB) e QtOpenGL (8,5 MB) saem: o projeto não importa nenhum dos
# dois, e o QtQuick renderiza por RHI, não por OpenGL. Medido: zero referência.
BIND_KEEP="QtCore QtGui QtQml QtQuick QtDBus QtNetwork"  # QtNetwork: o binding QtQml importa, mesmo sem uso direto no app
for b in "$PS"/*.abi3.so; do
    [ -e "$b" ] || continue
    n="$(basename "$b" .abi3.so)"
    case " $BIND_KEEP " in *" $n "*) ;; *) rm -f "$b" ;; esac
done

# 2.6 ferramentas de DESENVOLVAMENTO do PySide6. Medido no bundle anterior:
#     qmlls 4,8 MB · qmlformat 2,7 · assistant 1,9 · linguist 1,4 · lupdate 1,1
#     · scripts 863K · include 876K (headers C++) · libexec 1,4 MB
#     Nenhuma é usada em runtime. Numa wheel de PySide6 elas vêm por padrão.
log "B4bis ferramentas de dev do PySide6"
rm -rf "$PS"/qmlls "$PS"/qmlformat "$PS"/qmlscene "$PS"/qmltestrunner \
       "$PS"/assistant "$PS"/linguist "$PS"/lupdate "$PS"/pyside6-uic \
       "$PS"/pyside6-rcc "$PS"/scripts "$PS"/include "$PS"/doc \
       "$PS"/designer "$PS"/glue "$PS"/*.json "$PS"/__pycache__ 2>/dev/null || true
rm -rf "$QL/../libexec" 2>/dev/null || true
# metatypes: 65 .json (7,2 MB) de introspecção para qmllint/qmlls. Verificado
# por A/B: com e sem eles a GUI carrega igual. Não é runtime.
rm -rf "$QL/../metatypes" 2>/dev/null || true

# 2.7 libs Qt sem uso (medido no bundle anterior)
for lib in libQt6Help.so.6 libQt6UiTools.so.6 libQt6PrintSupport.so.6 \
           libQt6Test.so.6 libQt6Lottie.so.6 libQt6Sql.so.6 \
           libQt6QuickEffects.so.6 libQt6QuickControls2MaterialStyleImpl.so.6 \
           libQt6LabsPlatform.so.6 libQt6QuickParticles.so.6 \
           libQt6DesignerPrivate.so.6 libQt6StateMachine.so.6; do
    rm -f "$QL/$lib" "$QL/$lib".* 2>/dev/null || true
done

# 2.8 plugins: sqldrivers (2,3 MB — o projeto não tem SQL), tls,
#     wayland-*-server (só compositor), platforminputcontexts.
if [ -d "$PL" ]; then
    # NÃO remove wayland-graphics-integration-client: é o plugin que dá a
    # integração EGL/GL ao backend Wayland. Sem ele, em sessão Wayland o Qt
    # aborta em vez de cair para render por software.
    for d in sqldrivers tls wayland-graphics-integration-server \
             platforminputcontexts qtwebenginecore; do
        rm -rf "$PL/$d" 2>/dev/null || true
    done
fi

# ---------------------------------------------------------------------------
# 3. Kirigami + Breeze (Ubuntu 26.04 "resolute", Qt 6.10.2)
# ---------------------------------------------------------------------------
# Lista de pacotes: tools/breeze-debs.txt. DEBS é a raiz extraída desses .deb
# (dpkg-deb -x de cada um). Ver docs/BREEZE.md para o diagnóstico.
#
# Por que este conjunto (medido, não estimado):
#  * o estilo QQC2 "Breeze" é o módulo QML org.kde.breeze — o nome do estilo
#    (QT_QUICK_CONTROLS_STYLE) é esse URI, não "Breeze";
#  * ele importa org.kde.kirigami e org.kde.guiaddons;
#  * org.kde.guiaddons linka libKF6GuiAddons, que precisa de libwayland-client
#    >= 1.23 e das libs KF6 da cadeia (ColorScheme, ConfigCore, IconThemes…).
#  * libBreezeStyle.so e impl/libBreezeImpl.so só precisam de Qt.
#  * o plugin de plataforma do Kirigami (kf6/kirigami/platform/org.kde.breeze.so)
#    é o que dá a Kirigami.Theme (cores do KDE do usuário) e Kirigami.Units
#    (escala e fonte). Sem ele o app cai num fallback claro e pequeno. Ele
#    linka IconThemes -> BreezeIcons (~3 MB comprimido, mantido para os ícones
#    funcionarem fora do KDE), ColorScheme, ConfigCore/Gui, I18n, Archive.
log "Kirigami + Breeze (Ubuntu 26.04, Qt 6.10.2)"
LIBDIR="$APP/lib/x86_64-linux-gnu"
mkdir -p "$LIBDIR" "$APP/lib/qml/org/kde"
for pat in 'libKirigami*.so.6*' 'libKF6*.so.6*' 'libwayland-client.so.0*'; do
    cp -a "$DEBS"/usr/lib/x86_64-linux-gnu/$pat "$LIBDIR/" 2>/dev/null || true
done
for modulo in kirigami breeze guiaddons; do
    origem="$DEBS/usr/lib/x86_64-linux-gnu/qt6/qml/org/kde/$modulo"
    [ -d "$origem" ] || { echo "erro: módulo QML org.kde.$modulo ausente em \$DEBS" >&2; exit 1; }
    cp -a "$origem" "$APP/lib/qml/org/kde/"
done
[ -f "$APP/lib/qml/org/kde/breeze/qmldir" ] || { echo "erro: org.kde.breeze sem qmldir" >&2; exit 1; }

mkdir -p "$APP/lib/qtplugins/kf6/kirigami/platform"
cp -a "$DEBS/usr/lib/x86_64-linux-gnu/qt6/plugins/kf6/kirigami/platform/org.kde.breeze.so" \
      "$APP/lib/qtplugins/kf6/kirigami/platform/" \
    || { echo "erro: plugin de plataforma do Kirigami (org.kde.breeze.so) ausente" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 4. O projeto
# ---------------------------------------------------------------------------
log "projeto (src/rt) + payload"
mkdir -p "$BUILD/rt" "$BUILD/payload"
cp -a "$REPO/src/rt/." "$BUILD/rt/"
find "$BUILD/rt" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
if [ -n "$PAYLOAD" ]; then
    cp "$PAYLOAD" "$BUILD/payload/script.sh"
fi

# ---------------------------------------------------------------------------
# 5. AppRun
# ---------------------------------------------------------------------------
log "AppRun"
cat > "$BUILD/AppRun" <<APPRUN
#!/usr/bin/env bash
# AppRun do Sober Optimizer (rt). Montado por build-appimage.sh.
set -euo pipefail
HERE="\$(dirname "\$(readlink -f "\${0}")")"
APPDIR="\$HERE"

export PYTHONHOME="\$APPDIR/usr"
export PYTHONPATH="\$APPDIR:\$APPDIR/usr/lib/python3.14/site-packages"
export LD_LIBRARY_PATH="\$APPDIR/usr/lib/x86_64-linux-gnu:\$APPDIR/usr/lib/python3.14/site-packages/PySide6/Qt/lib\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
export QML2_IMPORT_PATH="\$APPDIR/usr/lib/qml:\$APPDIR/usr/lib/python3.14/site-packages/PySide6/Qt/qml\${QML2_IMPORT_PATH:+:\$QML2_IMPORT_PATH}"
export QT_PLUGIN_PATH="\$APPDIR/usr/lib/qtplugins:\$APPDIR/usr/lib/python3.14/site-packages/PySide6/Qt/plugins"
export QT_QPA_PLATFORM_PLUGIN_PATH="\$QT_PLUGIN_PATH/platforms"
# Estilo: NÃO é fixado aqui. gui/app.py escolhe org.kde.breeze quando o módulo
# existe no bundle (que é o caso) e cai para Basic se não existir. Para forçar
# outro estilo, exporte QT_QUICK_CONTROLS_STYLE antes de rodar o AppImage.
export QT_LOGGING_RULES="qt.qml.binding*=false"

# --- escolha de plataforma -----------------------------------------------------
# Um AppImage roda numa máquina desconhecida. A autodetecção do Qt prefere
# wayland se WAYLAND_DISPLAY existir e, se o plugin não inicializar, chama
# qFatal em libQt6Core e ABORTA — sem fallback e sem chance de recovery
# (foi o coredump observado numa distro GNOME/Fedora real).
# Aqui: testa de verdade e usa o primeiro que abrir.
if [ -z "\${RT_PLATFORM_SET:-}" ]; then
    _probe() {
        "\$APPDIR/usr/bin/python3" -c '
import os, sys
os.environ["QT_QPA_PLATFORM"] = sys.argv[1]
from PySide6.QtGui import QGuiApplication
try:
    QGuiApplication([])
except Exception:
    sys.exit(1)
' "\$1" >/dev/null 2>&1
    }
    for _p in \${RT_PLATFORM_LIST:-wayland xcb offscreen}; do
        if _probe "\$_p"; then export QT_QPA_PLATFORM="\$_p"; break; fi
    done
    export RT_PLATFORM_SET=1
fi

# sem argumentos: o runtime escolhe (SPEC §10.2.0): script embutido em
# \$APPDIR/payload, ou a tela inicial se não houver um.
# --- recuperação de abort ------------------------------------------------------
# A init de plataforma passar NÃO garante que a RENDERIZAÇÃO suba. O Qt abre a
# janela e só depois falha no backend gráfico (EGL/Vulkan/drm contra um driver
# que não combina) — e aí é qFatal em libQt6Core, com SIGABRT, derrubando a
# sessão junto. Foi exatamente o formato do coredump observado em Fedora.
#
# Se abortar, tenta uma vez com render por software, que só depende de
# libEGL/libGL genéricos. E grava o stderr num log ao lado do payload: o
# coredump do systemd NÃO tem o stderr, que é a parte que diz a causa.
# O AppImage é montado em squashfs — o mount é SOMENTE LEITURA. Gravar o log
# ao lado do payload morre com "Sistema de arquivos somente para leitura", e
# como o AppRun roda com `set -e`, esse redirect derrubava o app ANTES da GUI
# existir. Vai para o state dir do usuário, com queda para \$TMPDIR, e se não
# houver lugar gravável, para /dev/null: melhor sem log que sem aplicativo.
_rt_log_dir() {
    local base
    # mkdir -p é a autoridade: se o diretório não existe ainda mas o pai é
    # gravável, ele é criado. Testar "-d" antes pulava um XDG_STATE_HOME
    # legível porém ainda não criado — e caía no /tmp sem querer.
    for base in "\${XDG_STATE_HOME:-\$HOME/.local/state}" "\${TMPDIR:-/tmp}" "/tmp"; do
        [ -n "\$base" ] || continue
        if mkdir -p "\$base/sober-optimizer" 2>/dev/null; then
            echo "\$base/sober-optimizer"
            return 0
        fi
    done
    echo /dev/null
}
RT_LOG="\$(_rt_log_dir)/sober-optimizer.err.log"
[ -w "\$(dirname "\$RT_LOG")" ] || RT_LOG=/dev/null
# só a última execução interessa: trunca a cada start
if [ "\$RT_LOG" != /dev/null ]; then : >"\$RT_LOG"; fi
_run() {
    "\$APPDIR/usr/bin/python3" -m rt "\$@" 2>>"\$RT_LOG" || return \$?
    return 0
    return \$?
}

_run "\$@"; _rc=\$?

if [ "\$_rc" = 134 ] && [ -z "\${RT_SOFTWARE_RETRY:-}" ]; then
    {
        echo ""
        echo "--- qt ABORTOU com a plataforma \${QT_QPA_PLATFORM:-<auto>}; retry em software ---"
    } >>"\$RT_LOG"
    export QT_QUICK_BACKEND=software
    export LIBGL_ALWAYS_SOFTWARE=1
    export RT_SOFTWARE_RETRY=1
    _run "\$@"; _rc=\$?
    [ "\$_rc" = 134 ] && echo "sobrevive ao retry em software; o log tem o qFatal original." >&2
fi

exit \$_rc
APPRUN
chmod +x "$BUILD/AppRun"

# o icone: PNG 256x256 gerado na hora (o .desktop aponta pra sober-optimizer)
log "ícone"
python3 - "$BUILD/sober-optimizer.png" <<'ICO'
import zlib, struct, sys
W = H = 256
px = bytearray()
for y in range(H):
    px.append(0)
    for x in range(W):
        d = ((x - 128) ** 2 + (y - 128) ** 2) ** 0.5
        if d < 96:   px += bytes((26, 32, 44, 255))
        elif d < 112: px += bytes((61, 174, 233, 255))
        else:        px += bytes((0, 0, 0, 0))
def chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
open(sys.argv[1], "wb").write(
    b"\x89PNG\r\n\x1a\n"
    + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 6, 0, 0, 0))
    + chunk(b"IDAT", zlib.compress(bytes(px), 9))
    + chunk(b"IEND", b""))
ICO
cat > "$BUILD/sober-optimizer.desktop" <<'DESK'
[Desktop Entry]
Type=Application
Name=Sober Optimizer
Exec=AppRun
Icon=sober-optimizer
Categories=Game;
DESK

# ---------------------------------------------------------------------------
# 5b. Cortes de tamanho (medidos; ver docs/BREEZE.md, seção "Tamanho")
# ---------------------------------------------------------------------------
# ICU: se ICU_DATA_SO apontar para um libicudata.so.73 recompilado com dados
# só de en/pt (tools/build-icu-data.sh), ele substitui o do wheel. Mesmo soname
# e símbolos _73: o Qt carrega sem mudança. Corte: ~25 MB.
PS_LIB="$APP/lib/python3.14/site-packages/PySide6/Qt/lib"
if [ -n "${ICU_DATA_SO:-}" ]; then
    [ -f "$ICU_DATA_SO" ] || { echo "erro: ICU_DATA_SO não existe: $ICU_DATA_SO" >&2; exit 1; }
    log "ICU filtrado (en+pt) no lugar do libicudata do wheel"
    cp -f "$ICU_DATA_SO" "$PS_LIB/libicudata.so.73"
fi

# Libs que nada carregado alcança (KF6 de tema/config, Quick extras, EGL...).
# A análise é feita a cada build a partir de plugins/módulos QML/PySide reais,
# então acompanha a versão do Qt e o que o app importa. Medido: ~31 MB.
log "poda de libs não alcançadas"
python3 "$HERE/prune_unused_libs.py" "$BUILD"

# Stdlib: o que nada alcança sai (fecho de imports + rastreio de execução real,
# tools/stdlib-trace.txt). Inclui a pasta config-3.11-*, que é o libpython.a
# estático de build (~24 MB) e não é usada em runtime: o binário é estático.
log "poda do stdlib (fecho de imports + rastreio)"
python3 "$HERE/prune_stdlib.py" "$BUILD" --trace "$HERE/stdlib-trace.txt"
find "$APP/lib/python3.14" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

# ---------------------------------------------------------------------------
# 6. strip + appimagetool
# ---------------------------------------------------------------------------
log "strip nos binários"
find "$APP" -name '*.so*' -type f -exec strip --strip-unneeded {} + 2>/dev/null || true
strip --strip-unneeded "$APP/bin/python3" 2>/dev/null || true
strip --strip-unneeded "$LIBDIR"/libKirigami*.so.6.* 2>/dev/null || true

log "tamanho do AppDir"
du -sh "$BUILD"

log "appimagetool"
# appimagetool não é pacote pip: é um AppImage. Use um já baixado e extraído
# (sem FUSE em CI), ou um no PATH.
APPIMAGETOOL="${APPIMAGETOOL:-/tmp/squashfs-root/AppRun}"
# zstd nível 22 + blocos de 1M: ~9% menor que o padrão (medido: 38,4 -> 35,0 MB).
# O mksquashfs embutido só aceita zstd (xz não é suportado pelo appimagetool).
MKSQ=(--mksquashfs-opt -Xcompression-level --mksquashfs-opt 22
      --mksquashfs-opt -b --mksquashfs-opt 1M)
if [ -n "${APPIMAGETOOL:-}" ] && [ -x "$APPIMAGETOOL" ]; then
    if [ -n "${RUNTIME_FILE:-}" ]; then
        ARCH=x86_64 "$APPIMAGETOOL" --no-appstream "${MKSQ[@]}" --runtime-file "$RUNTIME_FILE" "$BUILD" "$SAIDA"
    else
        ARCH=x86_64 "$APPIMAGETOOL" --no-appstream "${MKSQ[@]}" "$BUILD" "$SAIDA"
    fi
elif command -v appimagetool >/dev/null 2>&1; then
    ARCH=x86_64 appimagetool --no-appstream "${MKSQ[@]}" "$BUILD" "$SAIDA"
else
    echo "erro: appimagetool não encontrado. Baixe de" >&2
    echo "  https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage" >&2
    echo "e extraia com --appimage-extract, ou aponte APPIMAGETOOL=<caminho>." >&2
    echo "O AppDir está pronto em $BUILD — só falta empacotar." >&2
    exit 1
fi

log "pronto: $SAIDA"
du -sh "$SAIDA"

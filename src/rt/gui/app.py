"""Ponto de entrada da GUI (SPEC.md §10.1).

Carrega o QML e registra o :class:`~rt.gui.bridge.Bridge` como propriedade
de contexto. Só existe a implementação Kirigami: sem o módulo
``org.kde.kirigami`` no sistema, o runtime erra alto com diagnóstico.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from ..core.errors import BashRTError
from ..core.parser import parse_script

__all__ = [
    "launch",
    "qml_dir",
    "create_engine",
    "kirigami_available",
    "QML_IMPORT_NAME",
    "KIRIGAMI_VERSION",
]

QML_IMPORT_NAME = "BashRT"
#: O Kirigami se importa SEM versão (`import org.kde.kirigami as Kirigami`):
#: `3.0` não existe nas builds testadas (KF6 6.30 expõe até `2.20`).
KIRIGAMI_VERSION = ""
#: Única fachada (SPEC.md §10.1).
KIT = "kirigami"


def _breeze_disponivel() -> bool:
    """O módulo QML org.kde.breeze está num caminho de import? (não carrega nada)."""
    caminhos = [c for c in os.environ.get("QML2_IMPORT_PATH", "").split(os.pathsep) if c]
    caminhos += ["/usr/lib/x86_64-linux-gnu/qt6/qml", "/usr/lib64/qt6/qml", "/usr/lib/qt6/qml"]
    return any((Path(c) / "org" / "kde" / "breeze" / "qmldir").is_file() for c in caminhos)


def _style() -> str:
    """Breeze (org.kde.breeze, o estilo QQC2) para parecer KDE nativo.

    Respeita QT_QUICK_CONTROLS_STYLE se já estiver definido. Sem o módulo
    Breeze, cai para Basic em vez de deixar o QML quebrar.
    """
    if "QT_QUICK_CONTROLS_STYLE" in os.environ:
        return os.environ["QT_QUICK_CONTROLS_STYLE"]
    return "org.kde.breeze" if _breeze_disponivel() else "Basic"

#: Piso da fonte base, em pt. Sem o tema de plataforma do KDE, o Qt cai em
#: ~9 pt (12 px) e os botões/títulos do Kirigami ficam pequenos. Se o sistema
#: der mais que isso, prevalece o do sistema.
FONTE_MINIMA_PT = 11.0


def _fonte_base(app: Any) -> None:
    """Aplica o piso de fonte base (ver FONTE_MINIMA_PT)."""
    fonte = app.font()
    tamanho = fonte.pointSizeF()
    if tamanho > 0 and tamanho < FONTE_MINIMA_PT:
        fonte.setPointSizeF(FONTE_MINIMA_PT)
        app.setFont(fonte)


_PROBE = """
import QtQuick
import org.kde.kirigami as Kirigami
QtObject { property color probe: Kirigami.Theme.textColor }
"""


def qml_dir() -> Path:
    return Path(__file__).resolve().parent / "qml"


def kirigami_available(engine: Any = None, version: str = KIRIGAMI_VERSION) -> bool:
    """§10.1 — ``True`` se o módulo ``org.kde.kirigami`` carrega nesta máquina.

    Faz um *probe* de verdade: compila e instancia um ``QtObject`` que importa
    o Kirigami. Precisa de QGuiApplication (com QCoreApplication o processo
    aborta) e do PySide6 da distro (o do pip não carrega o Kirigami do sistema).
    """
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    if QGuiApplication.instance() is None:
        raise RuntimeError("kirigami_available precisa de QGuiApplication viva")
    local_engine = None
    try:
        if engine is None:
            local_engine = QQmlEngine()
        probe = QQmlComponent(engine or local_engine)
        probe_text = (
            _PROBE if not version
            else _PROBE.replace(
                "import org.kde.kirigami as Kirigami",
                f"import org.kde.kirigami {version} as Kirigami",
            )
        )
        probe.setData(probe_text.encode("utf-8"), QUrl("qrc:/rt-probe.qml"))
        if probe.isError():
            return False
        return probe.create() is not None
    finally:
        del local_engine


def create_engine(
    script_path: Path | None,
    assets: Path | None = None,
) -> tuple[Any, Any, list[str]]:
    """Monta QGuiApplication + QQmlApplicationEngine. Usado também nos testes (§10.1).

    ``script_path=None`` abre a tela inicial (home): o usuário escolhe o script depois.
    """
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine

    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", _style())
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    app.setApplicationName(script_path.stem if script_path is not None else "BashRT")
    app.setApplicationDisplayName("BashRT")
    app.setOrganizationName("rt")
    app.setApplicationVersion("0.1.0")
    app.setWindowIcon(QIcon.fromTheme("system-software-install"))
    _fonte_base(app)

    from ..core.model import placeholder_script
    from .bridge import Bridge

    engine = QQmlApplicationEngine()
    # §10.1 — só existe a fachada Kirigami; sem o módulo no sistema, erro alto
    # antes de criar o Bridge (que já ligaria timer e threads).
    if not kirigami_available(engine):
        raise RuntimeError(
            "Kirigami indisponível: instale o Kirigami do sistema e use o "
            "PySide6 da distro. " + _qt_diagnostics()
        )
    script = parse_script(script_path) if script_path is not None else placeholder_script()
    bridge = Bridge(script, assets)
    try:
        roots = _load_ui(engine, bridge, KIT)
    except Exception as exc:  # noqa: BLE001 — qualquer falha na fachada
        raise RuntimeError(f"falha ao carregar a interface: {exc}") from exc
    if not roots:
        raise RuntimeError("falha ao carregar o QML principal")
    return app, engine, roots


def _load_ui(engine: Any, bridge: Any, kit: str) -> list[Any]:
    """Aponta os import paths e carrega o ``main.qml``."""
    from PySide6.QtCore import QUrl

    # qml/<kit>  — as fachadas (módulo BashRT)
    # qml/       — as telas (módulo pages); main.qml as instancia por nome no
    #              StackLayout, e um módulo só é achado em um import path.
    engine.addImportPath(str(qml_dir() / kit))
    engine.addImportPath(str(qml_dir()))
    theme = _create_theme(engine, kit)
    engine.rootContext().setContextProperty("theme", theme)
    engine.rootContext().setContextProperty("bridge", bridge)
    bridge.setGuiKit(kit)

    # O context property do Qt guarda só o ponteiro C++: sem um parent, o
    # objeto morre quando o Python libera a referência.
    bridge.setParent(engine)
    theme.setParent(engine)
    engine.load(QUrl.fromLocalFile(str(qml_dir() / "main.qml")))
    return engine.rootObjects()


#: Mantém vivos os QQmlComponent que criam o Theme (o dono do objeto QML).
_THEME_COMPONENTS: list[Any] = []


def _create_theme(engine: Any, kit: str) -> Any:
    """Carrega o Theme.qml da implementação escolhida (§10.1)."""
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml_dir() / kit / "BashRT" / "Theme.qml")))
    theme = component.create()
    if theme is None:
        raise RuntimeError(f"não foi possível carregar {kit}/BashRT/Theme.qml: {component.errorString()}")
    _THEME_COMPONENTS.append(component)
    return theme


def launch(script: Path | None = None, assets: Path | None = None) -> int:
    """Abre a GUI. ``script=None`` abre a tela inicial (home, §10.2.0)."""
    try:
        app, engine, _roots = create_engine(Path(script) if script is not None else None, assets)
    except BashRTError as exc:
        print(exc, file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"erro de interface: {exc}", file=sys.stderr)
        print(_qt_diagnostics(), file=sys.stderr)
        return 2
    bridge = engine.rootContext().contextProperty("bridge")
    app.aboutToQuit.connect(bridge.shutdown)
    return int(app.exec())


def _qt_diagnostics() -> str:
    """Diz qual PySide6/Qt está em uso — o culpado usual é o do pip."""
    try:
        import PySide6
        from PySide6.QtCore import qVersion
    except ImportError as exc:
        return f"diagnóstico: PySide6 não importável ({exc})"
    return (
        f"diagnóstico: PySide6 em {PySide6.__file__}, Qt {qVersion()} "
        "(precisa ser o da distro para carregar o Kirigami do sistema)"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(launch(Path(sys.argv[1]) if len(sys.argv) > 1 else None))

// Gaveta de log — Kirigami (SPEC.md §10.2.5).
//
// O painel de log mora aqui em vez de ocupar a tela de Execução:
// `OverlayDrawer` inferior não-modal, que abre sozinha quando a
// execução começa e abre/fecha pelo botão do cabeçalho, `Ctrl+L`
// ou `bridge.logDrawerOpen`. Auto-scroll e Copiar viajam junto,
// dentro do próprio LogPanel.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.OverlayDrawer {
    id: root

    edge: Qt.BottomEdge
    modal: false

    height: Math.min(420, parent ? parent.height * 0.55 : 420)

    // OverlayDrawer não-modal nasce com position=1 (drawerOpen
    // true): fecha de verdade depois que tudo montou, senão o
    // log já vem aberto e o bridge herda `true` pela volta
    // abaixo. `callLater` roda depois dos handlers internos.
    Component.onCompleted: Qt.callLater(root.close)

    // bridge manda; a gaveta obedece. O setter do bridge só
    // emite quando muda, então a volta (drawer → bridge) não
    // faz loop: abrir o já-aberto é no-op.
    Connections {
        target: bridge
        function onLogDrawerOpenChanged() {
            if (bridge.logDrawerOpen) root.open()
            else root.close()
        }
    }
    onDrawerOpenChanged: bridge.logDrawerOpen = drawerOpen

    LogPanel {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing
        onCopyRequested: bridge.copyToClipboard(bridge.logText())
    }
}

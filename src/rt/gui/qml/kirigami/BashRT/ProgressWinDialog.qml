// Janela de progresso dirigida pelo script — Kirigami (§8.4).
//
// `rt_progresswin_start/update/done` (estilo `kdialog --progressbar`):
// fire-and-forget, o script não espera resposta. Barra desenhada
// à mão (a do Breeze cospe TypeError). Fechar (X ou Cancelar)
// aborta a execução inteira (130, §7.4); `done` fecha sozinho.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.Dialog {
    id: root

    title: qsTr("Progresso")
    modal: true
    standardButtons: Kirigami.Dialog.NoButton
    width: Math.min(480, parent ? parent.width - 80 : 480)

    padding: Kirigami.Units.largeSpacing

    closePolicy: Popup.NoAutoClose
    onClosed: {
        // `done` fecha via Connections (visible já falso); X fecha
        // com a janela ainda marcada visível → aborta a execução
        if (bridge.progressWinVisible)
            bridge.cancel()
    }

    Connections {
        target: bridge
        function onProgressWinVisibleChanged() {
            if (bridge.progressWinVisible) root.open()
            else root.close()
        }
    }

    contentItem: ColumnLayout {
        spacing: Kirigami.Units.smallSpacing

        Label {
            text: bridge.progressWinText
            visible: text !== ""
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        AppProgressBar {
            Layout.fillWidth: true
            value: bridge.progressWinMaximum > 0
                ? bridge.progressWinValue / bridge.progressWinMaximum : 0
        }

        Label {
            text: "%1 / %2".arg(Math.round(bridge.progressWinValue))
                           .arg(Math.round(bridge.progressWinMaximum))
            opacity: 0.7
            font.pixelSize: theme.smallFont
            Layout.alignment: Qt.AlignRight
        }
    }

    footer: RowLayout {
        spacing: theme.smallSpacing

        Item { Layout.fillWidth: true }

        AppButton {
            text: qsTr("Cancelar")
            variant: "danger"
            Layout.topMargin: theme.smallSpacing
            Layout.bottomMargin: theme.smallSpacing
            Layout.rightMargin: theme.smallSpacing
            onClicked: bridge.cancel()
        }
    }
}

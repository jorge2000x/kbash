// Ação (mini-script, SPEC.md §4.8): título, botão e a saída embaixo dele.
//
// A ação roda fora do plano, com os valores atuais da tela. Enquanto roda, o
// botão fica desabilitado e nenhuma outra ação nem a execução do plano
// começam (o bridge recusa). O resultado fica no próprio bloco do grupo.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import kbash

ColumnLayout {
    id: row

    // dict vindo de bridge.actions: id, title, description, button, running,
    // status, exitCode, output
    property var action: ({})

    readonly property bool _hasStatus: action.status !== undefined && action.status !== ""

    function statusText(): string {
        switch (action.status) {
        case "ok": return qsTr("Concluído")
        case "failed": return qsTr("Falhou (código %1)").arg(action.exitCode)
        case "timeout": return qsTr("Tempo esgotado: a ação foi encerrada")
        default: return qsTr("Não foi possível executar a ação")
        }
    }

    Layout.fillWidth: true
    spacing: Kirigami.Units.smallSpacing

    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.largeSpacing

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0

            Label {
                text: row.action.title || ""
                font.bold: true
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            Label {
                visible: text !== ""
                text: row.action.description || ""
                opacity: 0.7
                font.pixelSize: theme.smallFont
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }

        AppButton {
            text: row.action.button || qsTr("Executar")
            enabled: !row.action.running && !bridge.running
            onClicked: bridge.runAction(row.action.id)
        }
    }

    Label {
        visible: !!row.action.running
        text: qsTr("Executando…")
        opacity: 0.7
        font.pixelSize: theme.smallFont
    }

    InlineMessage {
        Layout.fillWidth: true
        visible: row._hasStatus && !row.action.running
        tone: row.action.status === "ok" ? "positive" : "error"
        text: row.statusText()
    }

    TextArea {
        Layout.fillWidth: true
        visible: text !== "" && !row.action.running
        readOnly: true
        wrapMode: TextArea.NoWrap
        font.family: "monospace"
        font.pixelSize: theme.smallFont
        text: row.action.output || ""
        Layout.preferredHeight: Math.min(contentHeight + topPadding + bottomPadding, 240)
    }
}

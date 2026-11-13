// Saída somente-leitura com rolagem e "Copiar" (HIG: texto que o usuário pode
// ler e copiar, sem TextArea editável). Usado pela saída de #@action.
// Altura cresce com o conteúdo até `maxHeight`, depois rola.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import kbash

ColumnLayout {
    id: panel

    property string text: ""
    property int maxHeight: 240

    Layout.fillWidth: true
    spacing: Kirigami.Units.smallSpacing
    visible: text !== ""

    RowLayout {
        Layout.fillWidth: true
        Item { Layout.fillWidth: true }
        AppButton {
            text: qsTr("Copiar")
            iconGlyph: "edit-copy"
            variant: "flat"
            onClicked: bridge.copyToClipboard(panel.text)
        }
    }

    AppScrollView {
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(output.implicitHeight + Kirigami.Units.smallSpacing * 2, panel.maxHeight)

        TextEdit {
            id: output
            readOnly: true
            selectByMouse: true
            wrapMode: TextEdit.NoWrap
            font.family: "monospace"
            font.pixelSize: theme.smallFont
            color: theme.text
            text: panel.text
            Accessible.role: Accessible.StaticText
            Accessible.name: qsTr("Saída da ação")
        }
    }
}

// Cabeçalho da janela — Kirigami (SPEC.md §10.2).
//
// A `Kirigami.ApplicationWindow` só desenha a barra nativa quando o
// `pageStack` tem páginas; como o conteúdo das telas é um `StackLayout`
// (o ColumnView do pageStack não assenta numa coluna só sozinho), a barra
// precisa sair daqui. É um `ToolBar` com `Kirigami.Heading` — sem
// `anchors.fill` em item de Layout, que é o que truncava o título.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

ToolBar {
    id: root

    property string title: ""
    property string subtitle: ""
    property string iconName: ""
    property string iconFile: ""

    visible: root.title !== ""

    // esquema de cores de cabeçalho do Kirigami, como a barra de uma janela KDE
    Kirigami.Theme.colorSet: Kirigami.Theme.Header
    Kirigami.Theme.inherit: false

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Kirigami.Units.largeSpacing * 2
        anchors.rightMargin: Kirigami.Units.largeSpacing * 2
        anchors.topMargin: Kirigami.Units.smallSpacing
        anchors.bottomMargin: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.largeSpacing

        AppIcon {
            name: root.iconName
            source: root.iconFile
            Layout.alignment: Qt.AlignVCenter
        }

        // Só o nome: a descrição do script já aparece na tela de boas-vindas,
        // e repeti-la aqui espremia a barra (uma barra KDE tem ícone e título).
        Kirigami.Heading {
            level: 2
            text: root.title
            elide: Text.ElideRight
            Layout.fillWidth: true
        }

        // botão voltar (fluxo linear): mesmo efeito do item Exibir > Voltar
        AppButton {
            // só ícone: o texto vira o nome acessível (leitor de tela) e o tooltip
            text: qsTr("Voltar")
            display: AbstractButton.IconOnly
            iconGlyph: "go-previous"
            variant: "flat"
            visible: bridge.page > 0
            Layout.alignment: Qt.AlignVCenter
            onClicked: bridge.goToPage(bridge.page - 1)
            ToolTip.text: qsTr("Voltar (Esc)")
            ToolTip.visible: hovered
        }

        // gaveta de log (§10.2.5): abre/fecha sem painel fixo
        AppButton {
            text: qsTr("Log da execução")
            display: AbstractButton.IconOnly
            iconGlyph: "utilities-log-viewer"
            visible: bridge.page >= 2  // só há log na execução e no resultado
            variant: "flat"
            Layout.alignment: Qt.AlignVCenter
            onClicked: bridge.logDrawerOpen = !bridge.logDrawerOpen
            ToolTip.text: qsTr("Log (Ctrl+L)")
            ToolTip.visible: hovered
        }
    }
}

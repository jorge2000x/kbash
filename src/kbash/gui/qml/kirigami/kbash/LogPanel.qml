// Painel de log — Kirigami (SPEC.md §10.2.3).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Rectangle {
    id: root

    property alias autoScroll: scrollToggle.checked
    signal copyRequested()

    color: theme.logBase
    radius: theme.cornerRadius
    // altura padrão: com `Layout.fillHeight` numa coluna de altura
    // livre, a falta de implicitHeight deixa o painel com 0 — hoje
    // só se salva pelo minimumHeight em RunPage.
    implicitHeight: 260
    border.width: 1
    border.color: theme.hairline(theme.text)
    Layout.fillWidth: true
    Layout.fillHeight: true

    ListView {
        id: view
        anchors.fill: parent
        // margem em cima: os controles (Auto/Copiar) ficam
        // sobrepostos à lista e cobriam a primeira linha
        anchors.topMargin: theme.smallSpacing + theme.smallFont + theme.largeSpacing
        anchors.leftMargin: theme.smallSpacing
        anchors.rightMargin: theme.smallSpacing
        anchors.bottomMargin: theme.smallSpacing
        clip: true
        spacing: 1
        model: bridge.log
        cacheBuffer: 400
        boundsBehavior: Flickable.StopAtBounds

        onCountChanged: if (root.autoScroll) positionViewAtEnd()

        ScrollBar.vertical: ScrollBar {}

        delegate: Item {
            id: line
            required property int index
            required property string text
            required property string stream
            required property string level
            required property string stepId

            width: view.width
            implicitHeight: textLabel.implicitHeight

            Text {
                id: textLabel
                text: line.stepId !== "" ? "[" + line.stepId + "] " + line.text : line.text
                color: line.stream === "stderr" ? theme.logError
                     : line.level === "error" ? theme.logError
                     : line.level === "warn" ? theme.logWarn
                     : theme.logText
                font.family: "monospace"
                font.pixelSize: theme.smallFont
                wrapMode: Text.NoWrap
                width: line.width
                elide: Text.ElideRight
            }

            HoverHandler {
                id: lineHover
            }
            ToolTip {
                visible: lineHover.hovered && line.width < textLabel.implicitWidth
                text: line.text
                delay: 500
            }
        }
    }

    RowLayout {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: theme.smallSpacing
        spacing: theme.smallSpacing

        AppCheckBox {
            id: scrollToggle
            text: qsTr("Auto")
            checked: true
        }
        AppButton {
            text: qsTr("Copiar")
            variant: "flat"
            onClicked: root.copyRequested()
        }
    }

    Label {
        anchors.centerIn: parent
        text: qsTr("O log aparece aqui")
        color: theme.logText
        opacity: 0.5
        visible: bridge.logCount === 0
    }
}

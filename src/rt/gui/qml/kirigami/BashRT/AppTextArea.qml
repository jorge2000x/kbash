// Fachada de área de texto — desenho próprio sobre tipos básicos.
// O TextArea do Breeze quebra nesta build: o MobileTextActionsToolBar
// interno só aceita QQuickTextInput como target e cospe TypeError até
// com TextArea puro. ScrollView + TextEdit + placeholder, sem delegate
// de estilo (mesmo motivo do AppProgressBar).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root

    property alias text: edit.text
    property alias placeholderText: placeholder.text
    property alias wrapMode: edit.wrapMode
    property alias selectByMouse: edit.selectByMouse
    property alias font: edit.font

    implicitWidth: 200
    implicitHeight: 120

    // foco vai para o campo de verdade, não para a moldura
    onActiveFocusChanged: if (activeFocus) edit.forceActiveFocus()

    Rectangle {
        anchors.fill: parent
        radius: theme.cornerRadius
        color: theme.base
        border.width: 1
        border.color: edit.activeFocus ? theme.accent : theme.hairline(theme.text)
    }

    ScrollView {
        id: scroll
        anchors.fill: parent
        anchors.margins: 1
        clip: true
        ScrollBar.vertical.policy: ScrollBar.AsNeeded

        TextEdit {
            id: edit
            width: scroll.availableWidth
            height: Math.max(scroll.availableHeight, implicitHeight)
            padding: theme.smallSpacing
            wrapMode: TextEdit.WordWrap
            selectByMouse: true
            color: theme.text
        }
    }

    Label {
        id: placeholder
        anchors.fill: parent
        anchors.margins: 1 + theme.smallSpacing
        visible: edit.text === ""
        opacity: 0.5
        wrapMode: TextEdit.WordWrap
        verticalAlignment: Text.AlignTop
    }
}

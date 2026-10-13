// Fachada de ícone — Kirigami (SPEC.md §3 regra 5): nome de tema ou arquivo.
import QtQuick
import org.kde.kirigami as Kirigami

Item {
    id: root

    property string name: ""
    property string source: ""
    property real glyphSize: Kirigami.Units.iconSizes.small
    property color color: theme.text

    // se o arquivo sumir entre o parse e a renderização, o Image
    // dá Error e a caixa ficava vazia sem indicação: cai pro ícone
    property bool _fileOk: true

    implicitWidth: glyphSize
    implicitHeight: glyphSize

    Kirigami.Icon {
        anchors.fill: parent
        source: (root.source === "" || !root._fileOk) ? root.name : ""
        visible: (root.source === "" || !root._fileOk) && root.name !== ""
        color: root.color
    }

    Image {
        anchors.fill: parent
        source: root.source
        visible: root.source !== "" && root._fileOk
        fillMode: Image.PreserveAspectFit
        asynchronous: true
        cache: true
        onStatusChanged: if (status === Image.Error) root._fileOk = false
    }
}

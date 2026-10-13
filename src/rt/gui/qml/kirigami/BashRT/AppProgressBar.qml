// Fachada de barra de progresso (§10.2).
// Retângulos próprios: sem Kirigami.ProgressBar (não existe) e sem QQC
// ProgressBar (o Breeze 6.7.5 cospe 16 TypeErrors por barra criada).
import QtQuick
import QtQuick.Layouts

Item {
    id: control

    property real value: 0
    property bool indeterminate: false
    property real pulse: 0

    Layout.fillWidth: true
    implicitHeight: 8

    NumberAnimation on pulse {
        running: control.indeterminate && control.visible
        from: 0
        to: 1
        duration: 1400
        loops: Animation.Infinite
    }

    Rectangle {
        anchors.fill: parent
        radius: 3
        color: theme.faint(theme.text)
    }

    Rectangle {
        width: control.indeterminate
            ? parent.width * 0.35 * (0.6 + 0.4 * Math.sin(control.pulse * Math.PI * 2))
            : parent.width * Math.max(0, Math.min(1, control.value))
        x: control.indeterminate
            ? parent.width * control.pulse * 0.65
            : 0
        height: parent.height
        radius: 3
        color: theme.accent
        Behavior on width { NumberAnimation { duration: 120 } }
    }
}

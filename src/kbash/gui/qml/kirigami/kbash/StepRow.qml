// Item da lista de steps — Kirigami (SPEC.md §10.2.2).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import kbash

Rectangle {
    id: root

    property string stepId
    property string title
    property string description
    property string group
    property bool checked
    property bool locked
    property string status
    property bool needsRoot
    property real duration
    property bool required
    property bool autoAdded
    property string reason
    property string statusLabel

    readonly property bool _running: status === "running"
    readonly property bool _success: status === "success"
    readonly property bool _failed: status === "failed"
    readonly property bool _skipped: status === "skipped"
    readonly property bool _settled: _running || _success || _failed || _skipped

    Layout.fillWidth: true
    implicitHeight: layout.implicitHeight + 2 * theme.smallSpacing
    radius: theme.cornerRadius
    // fundo/borda só quando há estado: uma etapa que ainda não rodou não
    // precisa de moldura, e o ícone genérico ao lado do checkbox só poluía
    color: _running ? theme.surfaceAccent
         : _failed ? theme.surfaceError
         : "transparent"
    border.width: _running || _failed ? 1 : 0
    border.color: _running ? theme.lineAccent : theme.lineError

    RowLayout {
        id: layout
        anchors.fill: parent
        anchors.margins: theme.smallSpacing
        spacing: theme.smallSpacing

        // ícone só quando há estado; pendente é o checkbox que fala
        AppIcon {
            name: root._running ? "chronometer-running"
                 : root._success ? "object-select-symbolic"
                 : root._failed ? "dialog-error"
                 : "view-remove"
            visible: root._settled
            color: root._success ? theme.accent
                 : root._failed ? theme.error
                 : theme.muted
        }

        AppCheckBox {
            id: box
            visible: !root._running
            checked: root.checked
            enabled: !root.locked
            onToggled: {
                // o modelo pode recusar (obrigatória/dependência,
                // com aviso): reverte na hora em vez de deixar o
                // clique mentir até a próxima mudança externa
                if (!bridge.setStepChecked(root.stepId, checked))
                    box.checked = root.checked
            }
            // o clique acima quebra o binding de `checked`; este
            // Connections resincroniza nas mudanças vindas do modelo
            // (ex.: dependência auto-adicionada por outra linha)
            Connections {
                target: root
                function onCheckedChanged() { box.checked = root.checked }
            }
            ToolTip {
                visible: box.hovered && root.locked
                text: bridge.uncheckReason(root.stepId) || qsTr("Etapa obrigatória")
            }
        }

        ColumnLayout {
            spacing: 2
            Layout.fillWidth: true

            RowLayout {
                spacing: theme.smallSpacing
                Label {
                    text: root.title
                    opacity: root.checked || root.locked ? 1 : 0.55
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Label {
                    visible: root._success || root._failed || root._skipped
                    text: root.duration > 0 ? root.duration.toFixed(1) + "s" : root.statusLabel
                    opacity: 0.6
                    font.pixelSize: theme.smallFont
                }
            }

            Label {
                text: root.description
                visible: text !== ""
                opacity: 0.7
                font.pixelSize: theme.smallFont
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            InlineMessage {
                visible: root.reason !== "" && (root._failed || root._skipped)
                tone: "error"
                text: root.reason
                showCloseButton: false
                Layout.fillWidth: true
            }

            Flow {
                visible: root.needsRoot || root.required || root.autoAdded
                spacing: theme.smallSpacing
                StepBadge {
                    text: qsTr("requer root")
                    visible: root.needsRoot
                    tone: "warn"
                }
                StepBadge {
                    text: qsTr("obrigatório")
                    visible: root.required
                    tone: "info"
                }
                StepBadge {
                    text: qsTr("por dependência")
                    visible: root.autoAdded
                    tone: "muted"
                }
            }
        }
    }
}

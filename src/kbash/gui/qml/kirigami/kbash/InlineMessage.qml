// Fachada de mensagem inline — Kirigami (erro/aviso/info/estado vazio).
import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.InlineMessage {
    id: root

    property string tone: "info" // info | warning | error | positive
    default property alias content: extra.data

    readonly property int messageType: tone === "error" ? Kirigami.MessageType.Error
                                  : tone === "warning" ? Kirigami.MessageType.Warning
                                  : tone === "positive" ? Kirigami.MessageType.Positive
                                  : Kirigami.MessageType.Information

    type: root.messageType
    // `children` não notifica: ligar a `data` (que o Item emite ao
    // ganhar/pedir filhos) é o que faz o `visible` reavaliar quando
    // conteúdo entra depois da criação.
    visible: text !== "" || extra.data.length > 0
    Layout.fillWidth: true

    ColumnLayout {
        id: extra
        spacing: theme.smallSpacing
        Layout.fillWidth: true
    }
}

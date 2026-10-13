// Estado vazio — Kirigami (SPEC.md §3 regra 5, §10.4).
// `Kirigami.PlaceholderMessage` é o componente nativo para "aqui não tem
// nada": ícone opcional, título e explicação, com a escala do Kirigami.
import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.PlaceholderMessage {
    id: root

    property string explanation: ""
    property string iconName: ""

    Layout.fillWidth: true
    icon.name: root.iconName
    visible: text !== ""
}

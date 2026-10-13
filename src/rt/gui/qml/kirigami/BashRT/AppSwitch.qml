// Fachada de interruptor — Kirigami (SPEC.md §3 regra 5).
// Sem Kirigami.Switch (não existe): QtQuick.Controls com estilo Breeze.
//
// Indicador do Breeze (`Impl.SwitchIndicator`) com cores ajustadas para
// contraste no escuro: trilho desligado com borda a 60% do texto, trilho ligado
// em azul cheio (destaque do Kirigami). Só usa Kirigami.Theme.
import QtQuick
import QtQuick.Controls
import org.kde.kirigami as Kirigami
import org.kde.breeze.impl as Impl

Switch {
    id: control

    // rótulo padrão só enquanto o chamador não definir `text`
    // próprio: depois o dele manda.
    property bool _defaultLabel: text === ""

    Component.onCompleted: if (_defaultLabel) text = checked ? qsTr("Sim") : qsTr("Não")
    onToggled: if (_defaultLabel) text = checked ? qsTr("Sim") : qsTr("Não")

    function _mistura(a, b, t) {
        return Qt.rgba(a.r + (b.r - a.r) * t, a.g + (b.g - a.g) * t, a.b + (b.b - a.b) * t, 1)
    }

    indicator: Impl.SwitchIndicator {
        control: control

        Kirigami.Theme.backgroundColor: control._mistura(
            control.Kirigami.Theme.backgroundColor, control.Kirigami.Theme.textColor, 0.18)
        Kirigami.Theme.alternateBackgroundColor: control.Kirigami.Theme.highlightColor
        Kirigami.Theme.focusColor: control.Kirigami.Theme.highlightColor
    }
}

// Fachada de botão de rádio — Kirigami (SPEC.md §3 regra 5).
// `RadioButton` do QtQuick.Controls com o estilo Breeze.
// Sem política de Layout embutida: quem usa decide (§10.1).
import QtQuick
import QtQuick.Controls

RadioButton {
    id: control

    focusPolicy: Qt.StrongFocus
}

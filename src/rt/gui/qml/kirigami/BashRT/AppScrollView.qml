// Fachada de área rolável — Kirigami (SPEC.md §3 regra 5).
// `ScrollView` do QtQuick.Controls com o estilo Breeze.
// Sem política de Layout embutida: quem usa decide (§10.1).
import QtQuick
import QtQuick.Controls

ScrollView {
    id: control

    clip: true
    ScrollBar.vertical.policy: ScrollBar.AsNeeded
}

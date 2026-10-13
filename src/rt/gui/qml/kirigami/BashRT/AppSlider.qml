// Fachada de controle deslizante — Kirigami (SPEC.md §3 regra 5).
// `Slider` do QtQuick.Controls com o estilo Breeze.
// Sem política de Layout embutida: quem usa decide (§10.1).
import QtQuick
import QtQuick.Controls

Slider {
    id: control

    focusPolicy: Qt.StrongFocus
}

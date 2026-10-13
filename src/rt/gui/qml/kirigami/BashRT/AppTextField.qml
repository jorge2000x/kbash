// Fachada de campo de texto — Kirigami (SPEC.md §3 regra 5).
// Sem Kirigami.TextField (não existe): QtQuick.Controls com estilo Breeze.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

TextField {
    id: control
    selectByMouse: true
    Layout.fillWidth: true
}

// Fachada de botão — Kirigami (SPEC.md §3 regra 5, §10.1).
// Button nativo, sem background/contentItem próprios: quem pinta é o
// estilo Breeze (primary = highlighted, flat = flat).
// variant: "default" | "primary" | "danger" | "flat"
import QtQuick
import QtQuick.Controls

Button {
    id: control

    property string variant: "default"
    property string iconGlyph: ""

    // O Breeze não tem um papel "destrutivo" (§10.1: sem background/contentItem
    // próprios, quem pinta é o estilo), então "danger" reusa o destaque de
    // "primary": é o que o run traz de atenção. O rótulo é que diz o que é.
    highlighted: variant === "primary" || variant === "danger"
    flat: variant === "flat"
    focusPolicy: Qt.StrongFocus

    icon.name: control.iconGlyph
}

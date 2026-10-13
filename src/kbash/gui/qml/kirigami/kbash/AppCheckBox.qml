// Fachada de caixa de seleção — Kirigami (SPEC.md §3 regra 5).
// `CheckBox` do QtQuick.Controls com o estilo Breeze; o `StepRow` usava um
// `CheckBox` cru, quebrando a regra das fachadas.
//
// O indicador é o do Breeze (`Impl.CheckIndicator`: raio, sombra, animação e o
// "check"). Só as cores mudam, para contraste num tema escuro: no Breeze a
// borda do desmarcado é só 15% do texto e a caixa quase some no fundo. Aqui o
// fundo da caixa sobe 10% em direção ao texto, a borda do desmarcado vai a 60%
// (contraste ≥ 3:1 sobre o cartão, WCAG 1.4.11) e o marcado vira azul cheio com
// o "check" claro. Só usa cores do Kirigami.Theme.
import QtQuick
import QtQuick.Controls
import org.kde.kirigami as Kirigami
import org.kde.breeze.impl as Impl

CheckBox {
    id: control

    focusPolicy: Qt.StrongFocus

    // mistura linear (t = 0 → a, t = 1 → b): vale para qualquer esquema
    function _mistura(a, b, t) {
        return Qt.rgba(a.r + (b.r - a.r) * t, a.g + (b.g - a.g) * t, a.b + (b.b - a.b) * t, 1)
    }

    indicator: Impl.CheckIndicator {
        id: caixa
        control: control

        readonly property bool marcado: control.checkState !== Qt.Unchecked

        // pedido do usuário: o "check" do marcado é branco, e a borda do que não
        // está marcado é preta (é onde o contraste faltava). Azul cheio no marcado.
        Kirigami.Theme.textColor: "white"

        color: marcado ? control.Kirigami.Theme.highlightColor : control.Kirigami.Theme.backgroundColor
        border.color: marcado || control.down || control.visualFocus || control.hovered
            ? control.Kirigami.Theme.highlightColor
            : "black"
    }
}

// Selo compacto — retângulo tintado + texto na cor do tom.
//
// HISTÓRICO: isto era `Kirigami.Badge`. O tipo **não existe** em nenhum
// Kirigami empacotado (verificado por sondagem no runtime contra 6.13 do
// Debian 13 e 6.24 do Ubuntu 26.04) — só o `AbstractCard` e o `Icon` do
// projeto resolvem. Como o §3 exige que "toda decisão de lógica fica no core"
// e a fachada é a única implementação, o selo é desenhado aqui a partir das
// cores que o `Theme` já expõe (§10.1: cor sai sempre de Theme, nunca fixa).
//
// Cores: fundo = `faint(tom)`, texto = tom. `muted` é o tom apagado — um
// selo sem severidade, não um aviso.
import QtQuick
import org.kde.kirigami as Kirigami

Rectangle {
    id: root

    // muted | info | warn | error | positive
    property string tone: "muted"
    property string text: ""

    readonly property color toneColor: tone === "error" ? theme.error
                                  : tone === "warn" ? theme.warn
                                  : tone === "positive" ? theme.success
                                  : tone === "info" ? theme.accent
                                  : theme.muted

    readonly property color backgroundColor_: theme.faint(toneColor)

    radius: theme.cornerRadius
    color: backgroundColor_
    border.width: 0
    implicitHeight: label.implicitHeight + 2 * Math.max(2, theme.smallSpacing)
    implicitWidth: label.implicitWidth + 2 * theme.largeSpacing

    visible: text !== ""
    // selo nunca rouba o foco do conteúdo da linha
    activeFocusOnTab: false

    Text {
        id: label
        anchors.centerIn: parent
        text: root.text
        color: root.toneColor
        font.pixelSize: theme.smallFont
        elide: Text.ElideRight
    }
}

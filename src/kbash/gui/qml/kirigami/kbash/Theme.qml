// Paleta via Kirigami.Theme (SPEC.md §10.1 — tema claro/escuro do sistema).
//
// Regra: o app NÃO tem paleta própria. As cores saem do Kirigami, que já
// segue o tema do sistema, e o Breeze desenha os controles com a paleta dele.
// Painéis desenhados à mão (toast, selo, log) usam as funções daqui para
// combinar com essa paleta em vez de inventar cor.
import QtQuick
import org.kde.kirigami as Kirigami

QtObject {
    id: theme

    readonly property color text: Kirigami.Theme.textColor
    readonly property color base: Kirigami.Theme.backgroundColor
    readonly property color surface: Kirigami.Theme.alternateBackgroundColor
    readonly property color muted: Kirigami.Theme.disabledTextColor

    readonly property color highlight: Kirigami.Theme.highlightColor
    readonly property color accent: Kirigami.Theme.highlightColor
    readonly property color error: Kirigami.Theme.negativeTextColor
    readonly property color success: Kirigami.Theme.positiveTextColor
    // "neutral" é o papel de aviso do Kirigami (âmbar), não um cinza neutro.
    readonly property color warn: Kirigami.Theme.neutralTextColor

    // QML color não tem `luminance` (dava undefined → isDark sempre false).
    // As cores de TEXTO do Kirigami são escuras no claro e claras no escuro,
    // então o fundo é o indicador confiável.
    readonly property bool isDark: Kirigami.Theme.backgroundColor.hslLightness < 0.5

    // Cor do texto de um aviso/erro, para desenhar no `surface` (fundo chapado).
    function onSurface(level) {
        return level === "error" ? error
             : level === "warn" ? warn
             : level === "success" ? success
             : text
    }

    // O log acompanha o esquema, como uma tela de terminal: deriva
    // das cores do próprio Kirigami em vez de hex fixos, então segue
    // qualquer highlight/negative do sistema, não só claro/escuro.
    readonly property color logBase: isDark ? Qt.darker(Kirigami.Theme.backgroundColor, 1.8)
                                            : Qt.lighter(Kirigami.Theme.backgroundColor, 1.03)
    readonly property color logText: Kirigami.Theme.textColor
    readonly property color logError: Kirigami.Theme.negativeTextColor
    readonly property color logWarn: Kirigami.Theme.neutralTextColor

    // espaçamento e raio do Kirigami
    readonly property int smallSpacing: Math.round(Kirigami.Units.smallSpacing)
    readonly property int largeSpacing: Math.round(Kirigami.Units.largeSpacing)
    readonly property int cornerRadius: Math.round(Kirigami.Units.largeSpacing)
    // segue a fonte do sistema (o defaultFont do Kirigami já vem
    // com o pixel size dele); 12 fixo ignorava escala e fonte.
    readonly property int smallFont: Math.max(10, Math.round(Kirigami.Theme.defaultFont.pixelSize * 0.9))

    // Misturas sobre a cor do texto: funcionam nos dois esquemas, ao contrário
    // de um cinza fixo (que some no escuro) ou de um preto fixo no claro.
    function faint(base) {
        return Qt.rgba(base.r, base.g, base.b, 0.12)
    }
    function hairline(base) {
        return Qt.rgba(base.r, base.g, base.b, 0.45)
    }

    // superfícies e linhas por nível, prontas (evitam repetir
    // faint()/hairline() espalhados; casos dinâmicos por nível
    // continuam usando as funções acima)
    readonly property color surfaceAccent: faint(accent)
    readonly property color surfaceError: faint(error)
    readonly property color surfaceWarn: faint(warn)
    readonly property color surfacePositive: faint(success)
    readonly property color lineAccent: hairline(accent)
    readonly property color lineError: hairline(error)
    readonly property color lineWarn: hairline(warn)
    readonly property color linePositive: hairline(success)
}

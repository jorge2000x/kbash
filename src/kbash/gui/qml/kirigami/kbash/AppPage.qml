// Fachada de página — Kirigami (SPEC.md §3 regra 5, §10.1).
//
// A `Kirigami.Page` é um Flickable, e usá-la como `contentItem` de um
// ScrollView deixa o ScrollView com **largura 0** — a coluna encolhe para a
// largura do conteúdo e os cartões ficam estreitos com o texto cortado (era
// exatamente o que achatava a tela). Aqui a página é um Item simples e o
// ScrollView é filho dele, com `anchors.fill`: largura previsível, e a rolagem
// continua sendo a do ScrollView.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Item {
    id: root

    property string heading: ""
    property string subheading: ""

    default property alias content: contentArea.data

    readonly property int contentMargin: Math.round(theme.largeSpacing * 1.5)
    // linha de leitura: acima disso o texto fica longo demais
    readonly property int maxContentWidth: 820

    // Sem `implicitWidth` atado ao ScrollView: isso seria circular (a página
    // mediria o filho, que mediria a página) e o Layout acabaria com largura
    // 0. Quem dá a largura é o StackLayout da janela.

    ScrollView {
        id: scroll
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth
        ScrollBar.vertical.policy: ScrollBar.AsNeeded

        Item {
            id: pageBody
            width: scroll.availableWidth
            height: contentArea.implicitHeight + 2 * root.contentMargin
            // o ScrollView mede o conteúdo pelo implicitHeight dos
            // filhos diretos: sem isto o Item valia 0, a barra nunca
            // aparecia e a página não rolava (só se via com poucas
            // opções, quando tudo cabia na janela)
            implicitHeight: contentArea.implicitHeight + 2 * root.contentMargin

            ColumnLayout {
                id: contentArea
                // largura e centralização feitas aqui, e não com
                // Layout.maximumWidth/alignment: alignment faz o Layout
                // dimensionar pelo conteúdo e a coluna larga de novo.
                width: Math.min(pageBody.width - 2 * root.contentMargin, root.maxContentWidth)
                x: Math.max(root.contentMargin, (pageBody.width - width) / 2)
                // respiro no topo: a página não gruda na barra
                y: root.contentMargin
                spacing: theme.largeSpacing

                // O título da janela (AppHeader) já mostra o nome do script.
                // Repeti-lo aqui na página dava o mesmo nome duas vezes.
                Kirigami.Heading {
                    level: 2
                    visible: root.heading !== "" && root.heading !== bridge.scriptName
                    text: root.heading
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                }

                Label {
                    Layout.fillWidth: true
                    visible: root.subheading !== ""
                    text: root.subheading
                    opacity: 0.7
                    font.pixelSize: theme.smallFont
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}

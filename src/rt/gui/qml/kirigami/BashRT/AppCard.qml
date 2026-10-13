// Fachada de cartão — Kirigami (SPEC.md §3 regra 5).
//
// O `contentItem` + `padding` são o mecanismo do próprio AbstractCard: ele
// mede o conteúdo e dá o espaçamento. Duas coisas quebram o cartão aqui:
// usar `anchors.fill` num item que também é filho de um Layout (o
// gerenciador de geometria e os anchors se brigam e tudo colapsa na largura
// mínima) e medir a altura à mão em vez de deixar o card medir pelo
// `implicitContentHeight`.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.AbstractCard {
    id: root

    property string title: ""
    property string subtitle: ""

    default property alias content: extra.data

    Layout.fillWidth: true
    padding: Math.round(Kirigami.Units.largeSpacing * 1.5)

    contentItem: ColumnLayout {
        id: layout
        spacing: Kirigami.Units.largeSpacing

        Kirigami.Heading {
            level: 4
            text: root.title
            visible: root.title !== ""
            Layout.fillWidth: true
        }

        Label {
            text: root.subtitle
            opacity: 0.7
            font.pixelSize: theme.smallFont
            wrapMode: Text.WordWrap
            visible: text !== ""
            Layout.fillWidth: true
        }

        ColumnLayout {
            id: extra
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing
        }
    }
}

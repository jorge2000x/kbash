// Fachada de diálogo modal — Kirigami (SPEC.md §3 regra 5).
// Rodapé via QtQuick.Controls (sem DialogButtonBox no Kirigami).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.Dialog {
    id: root

    property string dialogTitle: qsTr("Confirmar")
    property string message: ""
    default property alias content: bodyColumn.data
    property alias acceptText: acceptButton.text
    property alias rejectText: rejectButton.text
    property alias refuseText: refuseButton.text
    property bool acceptVisible: true
    property bool rejectVisible: true
    // Terceiro botão, no meio: o "Não" do confirm (§8.5). Sem ele o diálogo
    // de Sim/Não só tinha "Sim" e "Cancelar", e responder não era impossível.
    property bool refuseVisible: false
    property string acceptVariant: "primary"
    property string rejectVariant: "flat"
    property string refuseVariant: "default"
    // para foco de teclado: Enter confirma (§8.2 — o input já
    // tinha Enter; choice/confirm não tinham nada focado).
    property alias defaultButton: acceptButton

    // O QML não distingue "recusar" de "rejeitar": quem responde é o Signal.
    signal refused()

    title: root.dialogTitle
    modal: true
    // o padding padrão do Kirigami.Dialog é 0: sem isto o
    // texto encosta na moldura (o contentItem sobrescrito não
    // herda margem nenhuma)
    padding: Kirigami.Units.largeSpacing
    standardButtons: Kirigami.Dialog.NoButton
    // Math.max: parent estreito (janela < 80px de folga) dava
    // largura negativa e geometria inválida
    width: Math.max(0, Math.min(560, parent ? parent.width - 80 : 560))

    // `ColumnLayout` (QtQuick.Layouts) não tem topPadding/bottomPadding/
    // leftPadding/rightPadding: atribuir essas propriedades é erro de
    // compilação ("Cannot assign to non-existent property") e a janela
    // inteira deixava de carregar. As margens do diálogo vêm do padding
    // próprio do Kirigami.Dialog.
    contentItem: ColumnLayout {
        spacing: Kirigami.Units.smallSpacing

        Label {
            text: root.message
            wrapMode: Text.WordWrap
            visible: text !== ""
            Layout.fillWidth: true
        }
        ColumnLayout {
            id: bodyColumn
            spacing: Kirigami.Units.smallSpacing
            Layout.fillWidth: true
        }
    }

    // RowLayout e não DialogButtonBox: o DialogButtonBox reescreve o
    // `highlighted` dos filhos conforme o papel dele, e o botão de default do
    // diálogo (Sim/Não) ficava sem destaque.
    footer: RowLayout {
        visible: root.acceptVisible || root.rejectVisible || root.refuseVisible
        spacing: theme.smallSpacing

        Item { Layout.fillWidth: true }

        AppButton {
            id: rejectButton
            Layout.leftMargin: theme.smallSpacing
            text: root.rejectText
            variant: root.rejectVariant
            visible: root.rejectVisible
            Layout.topMargin: theme.smallSpacing
            Layout.bottomMargin: theme.smallSpacing
            onClicked: root.reject()
        }
        AppButton {
            id: refuseButton
            text: root.refuseText
            variant: root.refuseVariant
            visible: root.refuseVisible
            Layout.topMargin: theme.smallSpacing
            Layout.bottomMargin: theme.smallSpacing
            onClicked: {
                root.refused()
                root.close()
            }
        }
        AppButton {
            id: acceptButton
            text: qsTr("OK")
            variant: root.acceptVariant
            visible: root.acceptVisible
            Layout.topMargin: theme.smallSpacing
            Layout.bottomMargin: theme.smallSpacing
            Layout.rightMargin: theme.smallSpacing
            onClicked: root.accept()
        }
    }
}

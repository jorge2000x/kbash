// 4. Resultado (SPEC.md §10.2.4)
// Estrutura fixa: veredito · etapas · ações.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import kbash

AppPage {
    id: page
    heading: {
        if (bridge.resultStatus === "success") return qsTr("Concluído")
        if (bridge.resultStatus === "cancelled") return qsTr("Cancelado")
        if (bridge.resultStatus === "failed") return qsTr("Falhou")
        return qsTr("Resultado")
    }
    subheading: qsTr("Revise o que aconteceu antes de fechar.")

    // -- veredito: sempre o mesmo formato, muda o tom ------------------
    InlineMessage {
        Layout.fillWidth: true
        tone: bridge.resultStatus === "success" ? "positive"
            : bridge.resultStatus === "cancelled" ? "warning"
            : bridge.resultStatus === "failed" ? "error" : "info"
        text: bridge.resultMessage !== ""
            ? bridge.resultMessage
            : qsTr("A execução terminou sem resumo.")
    }

    // -- etapas ---------------------------------------------------------
    AppCard {
        Layout.fillWidth: true
        title: qsTr("Resumo por etapa")

        ListView {
            id: resultSteps
            // reaproveita as linhas ao rolar (cache de delegates) em vez de recriar StepRow
            reuseItems: true
            cacheBuffer: 400
            Layout.fillWidth: true
            // mesma regra da Seleção: acompanha o conteúdo até 400
            Layout.preferredHeight: Math.min(contentHeight, 400)
            Layout.minimumHeight: 60
            clip: true
            spacing: 2
            model: bridge.runSteps
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}

            delegate: StepRow {
                width: resultSteps.width
                stepId: model.stepId
                title: model.title
                description: model.description
                group: model.group
                checked: model.checked
                locked: true
                status: model.status
                needsRoot: model.root
                duration: model.duration
                required: model.required
                autoAdded: model.autoAdded
                reason: model.reason
                statusLabel: model.statusLabel
            }
        }

        AppPlaceholder {
            Layout.fillWidth: true
            visible: bridge.stepCount === 0
            text: qsTr("Nenhuma etapa foi executada")
            explanation: qsTr("Nada foi selecionado ou a execução não começou.")
        }
    }

    // -- ver log --------------------------------------------------------
    // Reusa o LogPanel (o mesmo da gaveta): antes era ScrollView +
    // TextEdit desenhados aqui, duplicando código e visual.
    AppDialog {
        id: logDialog
        dialogTitle: qsTr("Log da execução")
        width: Math.max(0, Math.min(900, page.width - 80))
        height: Math.max(0, Math.min(560, page.height - 120))
        acceptVisible: false
        rejectText: qsTr("Fechar")

        LogPanel {
            Layout.fillWidth: true
            Layout.preferredHeight: 380
            autoScroll: false
            onCopyRequested: bridge.copyToClipboard(bridge.logText())
        }
    }

    // portal XDG (§10.1): o caminho volta em filePicked e o
    // salvamento usa o log lido na hora (está parado no Resultado)
    Connections {
        target: bridge
        function onFilePicked(token, paths) {
            if (token !== "save-log" || paths.length === 0)
                return
            bridge.saveLog(bridge.logText(), paths[0])
        }
    }

    // -- ações ---------------------------------------------------------
    RowLayout {
        Layout.fillWidth: true
        spacing: theme.largeSpacing

        AppButton {
            text: qsTr("Ver log")
            enabled: bridge.logCount > 0
            onClicked: logDialog.open()
        }
        AppButton {
            text: qsTr("Salvar log")
            enabled: bridge.logCount > 0
            onClicked: bridge.pickSaveFile("save-log", qsTr("Salvar log"), "execucao.log")
        }

        Item { Layout.fillWidth: true }

        AppButton {
            text: qsTr("Tentar novamente")
            visible: bridge.canRetry
            enabled: bridge.canRetry && !bridge.running
            onClicked: bridge.retryFailed()
        }
        AppButton {
            text: qsTr("Fechar")
            variant: "primary"
            onClicked: bridge.closeApp()
        }
    }
}

// 3. Execução (SPEC.md §10.2.3)
// Estrutura fixa: progresso · etapas · log · ações, sempre os quatro cartões.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import kbash

AppPage {
    id: page
    heading: qsTr("Executando")
    subheading: bridge.currentStepTitle !== "" ? bridge.currentStepTitle : qsTr("aguardando…")

    // -- progresso (§7.3) ----------------------------------------------
    AppCard {
        Layout.fillWidth: true

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing

            RowLayout {
                Layout.fillWidth: true
                Label {
                    text: qsTr("Progresso geral")
                    font.pixelSize: theme.smallFont
                    opacity: 0.7
                }
                Item { Layout.fillWidth: true }
                Label {
                    text: Math.round(bridge.overallProgress * 100) + "%"
                    font.pixelSize: theme.smallFont
                    opacity: 0.7
                }
            }

            AppProgressBar {
                Layout.fillWidth: true
                value: bridge.overallProgress
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: theme.largeSpacing
                Label {
                    text: bridge.currentStepTitle
                    font.pixelSize: theme.smallFont
                    opacity: 0.7
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Label {
                    text: bridge.stepProgressText
                    visible: text !== ""
                    opacity: 0.7
                    font.pixelSize: theme.smallFont
                    elide: Text.ElideRight
                }
            }

            AppProgressBar {
                Layout.fillWidth: true
                value: bridge.stepProgress
                indeterminate: bridge.running && bridge.stepProgress <= 0
            }
        }
    }

    // -- etapas com estado e duração -----------------------------------
    AppCard {
        Layout.fillWidth: true
        title: qsTr("Etapas")

        ListView {
            id: runSteps
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
                width: runSteps.width
                stepId: model.stepId
                title: model.title
                description: ""
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
            visible: bridge.stepCount === 0
            text: qsTr("Nenhuma etapa para executar")
        }
    }

    // -- log: mora na gaveta inferior (§10.2.5), não mais fixa aqui --
    // (o LogPanel com auto-scroll e Copiar está no LogDrawer)

    // -- ações ---------------------------------------------------------
    RowLayout {
        Layout.fillWidth: true
        spacing: theme.largeSpacing

        Label {
            text: bridge.precheckProblems.length > 0
                ? qsTr("A execução não começou: ") + bridge.precheckProblems.join("; ")
                : (bridge.running ? qsTr("Pode cancelar a qualquer momento.")
                                  : qsTr("Execução encerrada."))
            opacity: 0.7
            font.pixelSize: theme.smallFont
            elide: Text.ElideRight
            Layout.fillWidth: true
        }

        AppButton {
            text: qsTr("Ver log")
            onClicked: bridge.logDrawerOpen = true
        }
        AppButton {
            text: qsTr("Cancelar")
            variant: "danger"
            enabled: bridge.running
            onClicked: bridge.cancel()
        }
    }
}

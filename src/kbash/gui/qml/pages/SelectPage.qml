// 2. Seleção (SPEC.md §10.2.2).
// Não há cartões fixos de *Opções* e *Etapas*: o autor do script decide o
// agrupamento com `group=` (opções) e `#@group` (steps e ações) — §4.8.1.
// Dentro de um bloco a ordem é fixa: opções gerais, etapas e depois ações.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import kbash

AppPage {
    id: page
    heading: bridge.scriptName
    subheading: qsTr("Escolha as opções e as etapas")

    // predefinições (§9.4): escolher, salvar e apagar; sem cartão próprio
    RowLayout {
        Layout.fillWidth: true
        visible: bridge.optionCount > 0
        spacing: theme.smallSpacing

        Label {
            text: qsTr("Predefinição")
            opacity: 0.8
        }
        AppComboBox {
            id: presetBox
            Layout.fillWidth: true
            model: bridge.presetNames
            displayText: count === 0 ? qsTr("nenhuma salva") : currentText
            currentIndex: -1
            onActivated: bridge.loadPreset(currentText)
        }
        AppButton {
            text: qsTr("Apagar")
            enabled: presetBox.currentIndex >= 0
            onClicked: {
                bridge.deletePreset(presetBox.currentText)
                presetBox.currentIndex = -1
            }
        }
        AppButton {
            text: qsTr("Salvar como…")
            variant: "primary"
            onClicked: {
                presetName.text = ""
                saveDialog.open()
            }
        }
    }

    // salvar: nome da predefinição; senhas nunca entram (ver gui/presets.py)
    AppDialog {
        id: saveDialog
        dialogTitle: qsTr("Salvar predefinição")
        message: qsTr("Os valores atuais das opções ficam salvos em kbash-config/. Senhas não são salvas.")
        acceptText: qsTr("Salvar")
        onAccepted: {
            if (bridge.savePreset(presetName.text))
                presetBox.currentIndex = -1
        }

        AppTextField {
            id: presetName
            placeholderText: qsTr("Nome, ex.: Backup casa")
            onAccepted: saveDialog.accept()
        }
    }

    // -- blocos definidos pelo script (§4.8.1) --------------------------
    AppCard {
        Layout.fillWidth: true
        visible: bridge.optionCount > 0 || bridge.stepCount > 0 || bridge.actions.length > 0

        Repeater {
            model: bridge.groupNames
            delegate: ColumnLayout {
                id: block
                // nome do grupo; "" é o bloco sem título
                required property string modelData
                readonly property string groupName: modelData

                Layout.fillWidth: true
                spacing: theme.smallSpacing

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: theme.largeSpacing
                    visible: block.groupName !== ""
                    spacing: theme.smallSpacing

                    Label {
                        text: block.groupName
                        font.pixelSize: theme.smallFont
                        opacity: 0.7
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    Kirigami.Separator {
                        Layout.fillWidth: true
                    }
                }

                // opções gerais do bloco (sem needs_step)
                Repeater {
                    model: bridge.optionsFor(block.groupName)
                    delegate: OptionField {
                        visible: model.visible
                        optId: model.optId
                        type: model.type
                        label: model.label
                        value: model.value
                        choices: model.choices
                        required: model.required
                        error: model.error
                        help: model.help
                        minimum: model.minimum
                        maximum: model.maximum
                        step: model.step
                        filters: model.filters
                        url: model.url
                        pattern: model.pattern
                        minlen: model.minlen
                        maxlen: model.maxlen
                        multiple: model.multiple
                    }
                }

                // etapas do bloco; as opções de cada uma aparecem dentro da linha
                Repeater {
                    model: bridge.stepsFor(block.groupName)
                    delegate: StepRow {
                        Layout.fillWidth: true
                        stepId: model.stepId
                        title: model.title
                        description: model.description
                        group: model.group
                        checked: model.checked
                        locked: model.locked
                        status: model.status
                        needsRoot: model.root
                        duration: model.duration
                        required: model.required
                        autoAdded: model.autoAdded
                        reason: model.reason
                        statusLabel: model.statusLabel
                    }
                }

                // ações (§4.8): só as do próprio grupo
                Repeater {
                    model: bridge.actions
                    delegate: ActionRow {
                        required property var modelData
                        visible: modelData.group === block.groupName
                        action: modelData
                    }
                }
            }
        }

        AppPlaceholder {
            Layout.fillWidth: true
            visible: bridge.optionCount === 0 && bridge.stepCount === 0 && bridge.actions.length === 0
            text: qsTr("Nada para configurar")
            explanation: qsTr("Um script declara opções com #@option, etapas com #@step e ações com #@action.")
        }
    }

    // -- pré-checagens (§7.5) ------------------------------------------
    AppCard {
        Layout.fillWidth: true
        title: qsTr("Antes de executar")

        InlineMessage {
            Layout.fillWidth: true
            visible: bridge.precheckProblems.length === 0 && bridge.rootSteps.length === 0
            tone: "positive"
            text: qsTr("Tudo pronto: nenhum comando obrigatório em falta.")
        }

        InlineMessage {
            Layout.fillWidth: true
            tone: "warning"
            visible: bridge.rootSteps.length > 0
            text: qsTr("Etapas que pedem privilégios de root: ") + bridge.rootSteps.join(", ")
        }

        InlineMessage {
            Layout.fillWidth: true
            tone: "error"
            visible: bridge.precheckProblems.length > 0
            text: bridge.precheckProblems.join("\n")
        }
    }

    // -- ações da tela ---------------------------------------------------
    RowLayout {
        Layout.fillWidth: true
        spacing: theme.largeSpacing

        Label {
            text: bridge.stepCount > 0
                ? bridge.selectedCount + "/" + bridge.stepCount + " " + qsTr("etapas selecionadas")
                : ""
            opacity: 0.7
            font.pixelSize: theme.smallFont
            elide: Text.ElideRight
            Layout.fillWidth: true
        }

        // "Voltar" não existe mais: o botão do cabeçalho nativo do Kirigami
        // faz isso, e dois "voltar" na tela é um a mais.
        AppButton {
            text: qsTr("Executar")
            variant: "primary"
            enabled: bridge.canRun
            onClicked: bridge.start()
        }
    }
}

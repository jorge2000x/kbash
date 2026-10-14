// 2. Seleção (SPEC.md §10.2.2).
// A estrutura é sempre a mesma: Opções · Etapas · Antes de executar · Ações.
// O que muda é só o conteúdo de cada cartão — nada some, nada salta (§10.4).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import kbash

AppPage {
    id: page
    heading: bridge.scriptName
    subheading: qsTr("Escolha as opções e as etapas")

    // -- opções (§4.3) --------------------------------------------------
    AppCard {
        Layout.fillWidth: true
        title: qsTr("Opções")
        // o cartão fica sempre (estrutura estável, §10.4); sem opções gerais, diz onde estão
        subtitle: bridge.generalOptionCount > 0
            ? qsTr("Preencha antes de executar.")
            : bridge.optionCount > 0
                ? qsTr("As opções ficam junto das etapas que configuram.")
                : qsTr("Este script não pede opções.")

        // só as opções gerais; as ligadas a um step ficam dentro da linha do step
        Repeater {
            model: bridge.options
            delegate: OptionField {
                visible: model.visible && model.owner === ""
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

        AppPlaceholder {
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.smallSpacing
            visible: bridge.optionCount === 0
            text: qsTr("Nenhuma opção declarada")
            explanation: qsTr("Um script declara opções com #@option no cabeçalho.")
        }

        // predefinições (kbash-config/, gui/presets.py): escolher, salvar e apagar
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

    // -- etapas agrupadas (§4.4) ---------------------------------------
    AppCard {
        Layout.fillWidth: true
        title: qsTr("Etapas")
        subtitle: qsTr("Etapas marcadas como dependência entram automaticamente.")

        ListView {
            id: stepsView
            // reaproveita as linhas ao rolar (cache de delegates) em vez de recriar StepRow
            reuseItems: true
            cacheBuffer: 400
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(contentHeight, 400)
            Layout.minimumHeight: 60
            visible: count > 0
            clip: true
            spacing: 2
            model: bridge.steps
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}

            section.property: "group"
            section.criteria: ViewSection.FullString
            section.delegate: Item {
                width: stepsView.width
                height: section !== "" ? sectionLabel.implicitHeight + 2 * theme.largeSpacing : 0
                visible: section !== ""
                Label {
                    id: sectionLabel
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: sectionLine.top
                    anchors.bottomMargin: theme.smallSpacing
                    anchors.leftMargin: theme.smallSpacing
                    text: section
                    font.pixelSize: theme.smallFont
                    opacity: 0.7
                    elide: Text.ElideRight
                }
                Kirigami.Separator {
                    id: sectionLine
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                }
            }

            delegate: StepRow {
                width: stepsView.width
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

        AppPlaceholder {
            Layout.fillWidth: true
            visible: bridge.stepCount === 0
            text: qsTr("Nenhuma etapa declarada")
            explanation: qsTr("Um script declara etapas com #@step. Nada será executado.")
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

    // -- ações ---------------------------------------------------------
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

// Diálogo de prompt do protocolo §8.2 — Kirigami.
// Entradas via QtQuick.Controls (sem TextField/CheckBox no Kirigami).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

AppDialog {
    id: root

    property string requestId: ""
    property string kind: ""
    property string promptText: ""
    property string promptLabel: ""
    property var promptDefault: ""
    property var promptChoices: []
    property bool promptMulti: false
    property bool promptSecret: false
    property string promptMin: ""
    property string promptMax: ""
    property var selected: promptChoices.length > 0 ? promptChoices[0] : ""
    property var selectedList: []

    readonly property bool isConfirm: kind === "confirm"

    // erro da resposta number/date/time, na mesma regra do terminal (bridge.validateAnswer)
    property string fieldError: ""

    function fieldText(): string {
        if (kind === "number") return numberField.text
        if (kind === "date") return dateField.text
        if (kind === "time") return timeField.text
        return ""
    }

    // o aceite só fecha o diálogo se a resposta for válida: o terminal recusaria o mesmo valor
    beforeAccept: function () {
        if (kind !== "number" && kind !== "date" && kind !== "time") {
            fieldError = ""
            return true
        }
        fieldError = bridge.validateAnswer(kind, fieldText(), promptMin, promptMax)
        return fieldError === ""
    }

    function tryAccept(): void {
        if (beforeAccept())
            root.accept()
    }
    // informativo: fechar (X ou Esc) é ok, não cancel (§8.2 —
    // kdialog --textbox também só tem OK)
    readonly property bool isTextbox: kind === "textbox"
    // rt.sh manda y/n já como booleano (§8.4): o botão do meio vira o
    // "padrão" (destacado), igual ao hint [S/n] do terminal.
    readonly property bool defaultYes: promptDefault === true

    dialogTitle: isConfirm ? qsTr("Confirmação")
        : isTextbox ? (root.promptLabel !== "" ? root.promptLabel : qsTr("Informação"))
        : qsTr("Resposta necessária")
    message: isConfirm ? promptText : (isTextbox ? "" : promptLabel)

    // "Não" só faz sentido no confirm; nos demais some para não sobrar botão.
    // O textbox fecha pelo OK ou pelo X (resposta vazia, nunca cancel).
    refuseVisible: isConfirm
    refuseText: qsTr("Não")
    acceptVisible: true
    rejectVisible: !isTextbox
    acceptText: isConfirm ? qsTr("Sim") : isTextbox ? qsTr("OK") : qsTr("Confirmar")
    rejectText: qsTr("Cancelar")
    acceptVariant: !isConfirm || defaultYes ? "primary" : "default"
    refuseVariant: defaultYes ? "default" : "primary"
    // sem fechamento por Esc/clique fora: só os botões respondem, senão o
    // script fica preso esperando (§7.4). O textbox é informativo: Esc fecha.
    closePolicy: isTextbox ? Popup.CloseOnEscape : Popup.NoAutoClose
    onRejected: bridge.cancelPrompt(requestId)
    // O "x" do cabeçalho do Kirigami.Dialog fecha sem passar por `rejected`.
    // Sem isto o script ficava esperando resposta até o timeout de 1 h (§7.4).
    // Respondendo duas vezes não faz mal: o provedor já não tem a pendência.
    // No textbox, fechar é responder vazio (nunca cancel).
    onClosed: isTextbox ? bridge.answer(requestId, "") : bridge.cancelPrompt(requestId)
    onRefused: {
        // Responder "não" NÃO é cancelar: o script recebe status "ok" com o
        // valor "no" (core/ipc.py §8.3) e segue o seu caminho normal.
        bridge.answer(requestId, false)
    }

    AppTextField {
        id: inputField
        visible: root.kind === "input"
        text: root.promptDefault === undefined || root.promptDefault === null ? "" : String(root.promptDefault)
        echoMode: root.promptSecret ? TextInput.Password : TextInput.Normal
        onAccepted: root.tryAccept()
    }

    AppTextField {
        id: numberField
        onTextEdited: root.fieldError = ""
        visible: root.kind === "number"
        text: root.promptDefault === undefined || root.promptDefault === null ? "" : String(root.promptDefault)
        placeholderText: (root.promptMin !== "" || root.promptMax !== "")
            ? qsTr("entre %1 e %2").arg(root.promptMin || "…").arg(root.promptMax || "…") : ""
        validator: DoubleValidator { locale: "C"; notation: DoubleValidator.StandardNotation }
        onAccepted: root.tryAccept()
    }

    AppTextField {
        id: dateField
        onTextEdited: root.fieldError = ""
        visible: root.kind === "date"
        text: root.promptDefault === undefined || root.promptDefault === null ? "" : String(root.promptDefault)
        placeholderText: qsTr("AAAA-MM-DD")
        inputMask: "0000-00-00"
        onAccepted: root.tryAccept()
    }

    AppTextField {
        id: timeField
        onTextEdited: root.fieldError = ""
        visible: root.kind === "time"
        text: root.promptDefault === undefined || root.promptDefault === null ? "" : String(root.promptDefault)
        placeholderText: qsTr("HH:MM")
        inputMask: "00:00"
        onAccepted: root.tryAccept()
    }

    Label {
        id: fieldErrorLabel
        visible: root.fieldError !== ""
        text: root.fieldError
        color: Kirigami.Theme.negativeTextColor
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
        Accessible.role: Accessible.AlertMessage
        Accessible.name: text
    }

    RowLayout {
        visible: root.kind === "file"
        Layout.fillWidth: true
        spacing: theme.smallSpacing

        AppTextField {
            id: fileField
            Layout.fillWidth: true
            text: root.promptDefault === undefined || root.promptDefault === null ? "" : String(root.promptDefault)
            placeholderText: qsTr("Caminho do arquivo")
            onAccepted: root.tryAccept()
        }
        AppButton {
            text: qsTr("Procurar…")
            variant: "flat"
            // portal XDG (§10.1): preenche o campo, sem aceitar sozinho
            onClicked: bridge.pickOpenFile("prompt:" + requestId, root.promptLabel, false)
        }
    }

    Connections {
        target: bridge
        function onFilePicked(token, paths) {
            if (token !== "prompt:" + requestId || paths.length === 0)
                return
            fileField.text = paths[0]
        }
    }

    AppTextArea {
        id: textArea
        visible: root.kind === "text"
        Layout.fillWidth: true
        Layout.preferredHeight: 140
        placeholderText: root.promptLabel
        text: root.promptDefault === undefined || root.promptDefault === null ? "" : String(root.promptDefault)
    }

    AppScrollView {
        visible: root.isTextbox
        Layout.fillWidth: true
        Layout.preferredHeight: 300

        TextEdit {
            id: textboxArea
            readOnly: true
            selectByMouse: true
            wrapMode: TextEdit.WordWrap
            font.family: "monospace"
            font.pointSize: Kirigami.Theme.defaultFont.pointSize
            color: theme.text
            width: parent.width
            text: root.promptText
        }
    }

    ColumnLayout {
        visible: root.kind === "choice"
        Layout.fillWidth: true
        spacing: theme.smallSpacing

        ButtonGroup {
            id: choiceGroup
            exclusive: !root.promptMulti
        }

        // escolha única: RadioButton exclusivo; múltipla: CheckBox
        Repeater {
            model: root.promptMulti ? [] : root.promptChoices
            delegate: AppRadioButton {
                text: modelData
                ButtonGroup.group: choiceGroup
                checked: root.selected === modelData
                onToggled: if (checked) root.selected = modelData
            }
        }
        Repeater {
            model: root.promptMulti ? root.promptChoices : []
            delegate: AppCheckBox {
                text: modelData
                checked: root.selectedList.indexOf(modelData) >= 0
                onToggled: {
                    var current = root.selectedList.slice()
                    var at = current.indexOf(modelData)
                    if (at >= 0) current.splice(at, 1); else current.push(modelData)
                    root.selectedList = current
                }
            }
        }
    }

    onOpened: {
        if (kind === "choice") {
            if (promptMulti) {
                selectedList = Array.isArray(promptDefault) ? promptDefault.slice() : []
            } else {
                selected = (promptDefault !== undefined && promptDefault !== null && promptDefault !== "")
                    ? promptDefault
                    : (promptChoices.length > 0 ? promptChoices[0] : "")
            }
        }
        if (kind === "input") inputField.forceActiveFocus()
        else if (kind === "number") numberField.forceActiveFocus()
        else if (kind === "date") dateField.forceActiveFocus()
        else if (kind === "time") timeField.forceActiveFocus()
        else if (kind === "file") fileField.forceActiveFocus()
        else if (kind === "text") textArea.forceActiveFocus()
        // confirmação com padrão Não: o foco vai para o Não, para que Enter não
        // confirme uma ação destrutiva por engano (HIG: o padrão é o botão focado)
        else if (isConfirm && !defaultYes) refuseFocusItem.forceActiveFocus()
        // teclado: Enter aceita; sem foco inicial só o mouse responde
        else defaultButton.forceActiveFocus()
    }

    onAccepted: {
        if (kind === "confirm")
            bridge.answer(requestId, true)
        else if (kind === "choice")
            bridge.answer(requestId, promptMulti ? selectedList : selected)
        else if (kind === "number")
            bridge.answer(requestId, numberField.text)
        else if (kind === "date")
            bridge.answer(requestId, dateField.text)
        else if (kind === "time")
            bridge.answer(requestId, timeField.text)
        else if (kind === "file")
            bridge.answer(requestId, fileField.text)
        else if (kind === "text")
            bridge.answer(requestId, textArea.text)
        else if (kind === "textbox")
            bridge.answer(requestId, "")
        else
            bridge.answer(requestId, inputField.text)
        root.close()
    }
}

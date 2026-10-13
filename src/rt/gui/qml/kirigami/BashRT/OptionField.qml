// Campo de opção por tipo — Kirigami (SPEC.md §4.3, §10.2.2).
// Entradas via QtQuick.Controls com o estilo Breeze; senha via
// `Kirigami.PasswordField`, que é o campo nativo e tem o botão de mostrar.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

ColumnLayout {
    id: root

    property string optId
    property string type
    property string label
    property string value
    property var choices
    property bool required
    property string error
    property string help
    // §4.3: faixa e passo (number/slider), globs (file)
    property string minimum: ""
    property string maximum: ""
    property string step: ""
    property var filters
    // §4.3: validação de texto e file múltiplo
    property string pattern: ""
    property string minlen: ""
    property string maxlen: ""
    property bool multiple: false
    // §4.3: endereço do tipo `link` (o runtime só abre http/https)
    property string url: ""

    // §4.3: `paragraph` e `link` só exibem; não têm valor nem linha OPT_*
    readonly property bool isDisplay: root.type === "paragraph" || root.type === "link"

    spacing: Kirigami.Units.smallSpacing
    Layout.fillWidth: true

    // O valor do modelo entra no campo na criação e quando muda com o campo
    // sem foco. Com binding direto em `text`, cada tecla chamaria setOption, o
    // modelo devolveria `value` de volta e o campo apagaria o que está sendo
    // digitado — na senha, que o modelo sempre devolve vazio, apagava sempre.
    function syncField(field) {
        if (!field.activeFocus)
            field.text = root.value === undefined || root.value === null ? "" : root.value
    }

    // Slider: como no combo, a interação quebra o binding de
    // `value`; fora do arrasto o modelo manda.
    function syncSlider(slider) {
        if (!slider.pressed) {
            var at = root.value === undefined || root.value === null || root.value === ""
                ? slider.from : Number(root.value)
            slider.value = at
        }
    }

    // ComboBox: a interação do usuário quebra o binding de
    // `currentIndex`, e mudança externa do modelo ficava sem
    // refletir (o campo mostrava uma opção que não é o valor).
    // Enquanto o popup está aberto a escolha é do usuário; fora
    // dele o modelo manda. Valor vazio = nada selecionado:
    // `indexOf` devolve -1, mas o ComboBox normaliza -1 para 0,
    // então a ausência de valor tem que ser explícita.
    function syncCombo(combo) {
        if (combo.popupVisible)
            return
        if (root.value === undefined || root.value === null || root.value === "")
            combo.currentIndex = -1
        else
            combo.currentIndex = root.choices ? root.choices.indexOf(root.value) : -1
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing
        visible: !root.isDisplay

        Label {
            text: root.label + (root.required ? " *" : "")
            elide: Text.ElideRight
            Layout.fillWidth: true
        }
        Label {
            text: "OPT_" + root.optId.toUpperCase()
            opacity: 0.5
            font.pixelSize: theme.smallFont
            font.family: "monospace"
        }
    }

    // Um campo para string/path/file/number e um para senha (o
    // `Kirigami.PasswordField`, que é o nativo e tem o botão de
    // mostrar). O `visible` do pai esconde o que não serve, então
    // foco e teclado nunca caem no campo errado. `number` valida
    // na digitação (o planner é a autoridade, no Executar).
    DoubleValidator {
        id: numberValidator
        locale: "C"
        notation: DoubleValidator.StandardNotation
    }

    // Validador de pattern: Python `re` é superconjunto do JS
    // RegExp; o que o JS não compila valida só no planner
    // (autoridade final, no Executar).
    RegularExpressionValidator {
        id: patternValidator
        Component.onCompleted: applyPattern()
        function applyPattern() {
            if (root.pattern === "")
                return
            try {
                regularExpression = new RegExp("^(?:" + root.pattern + ")$")
            } catch (e) { /* planner valida; GUI ignora */ }
        }
    }
    Connections {
        target: root
        function onPatternChanged() { patternValidator.applyPattern() }
    }

    AppTextField {
        id: textField
        visible: root.type === "string" || root.type === "path"
              || root.type === "file" || root.type === "number"
        placeholderText: root.help
        validator: root.type === "number" ? numberValidator
                 : (root.pattern !== "" ? patternValidator : null)
        maximumLength: root.maxlen !== "" ? Number(root.maxlen) : 32767
        onTextEdited: bridge.setOption(root.optId, text)
        Component.onCompleted: root.syncField(textField)
        Connections {
            target: root
            // id explícito: dentro do handler, `text` não resolve para o
            // campo e a sincronia silenciosamente não acontecia
            function onValueChanged() { root.syncField(textField) }
        }
    }

    AppTextField {
        id: dateField
        visible: root.type === "date"
        placeholderText: qsTr("AAAA-MM-DD")
        inputMask: "0000-00-00"
        onTextEdited: bridge.setOption(root.optId, text)
        Component.onCompleted: root.syncField(dateField)
        Connections {
            target: root
            function onValueChanged() { root.syncField(dateField) }
        }
    }

    AppTextField {
        id: timeField
        visible: root.type === "time"
        placeholderText: qsTr("HH:MM")
        inputMask: "00:00"
        onTextEdited: bridge.setOption(root.optId, text)
        Component.onCompleted: root.syncField(timeField)
        Connections {
            target: root
            function onValueChanged() { root.syncField(timeField) }
        }
    }

    AppTextArea {
        id: textArea
        visible: root.type === "text"
        Layout.fillWidth: true
        Layout.preferredHeight: 120
        placeholderText: root.help
        // sem maximumLength na área: o planner barra no Executar
        onTextChanged: if (textArea.activeFocus) bridge.setOption(root.optId, text)
        Component.onCompleted: root.syncField(textArea)
        Connections {
            target: root
            function onValueChanged() { root.syncField(textArea) }
        }
    }

    Kirigami.PasswordField {
        id: passwordField
        visible: root.type === "password"
        placeholderText: root.help
        validator: root.pattern !== "" ? patternValidator : null
        maximumLength: root.maxlen !== "" ? Number(root.maxlen) : 32767
        onTextEdited: bridge.setOption(root.optId, text)
        Component.onCompleted: root.syncField(passwordField)
        Connections {
            target: root
            function onValueChanged() { root.syncField(passwordField) }
        }
    }

    AppButton {
        visible: root.type === "path" || root.type === "file"
        text: qsTr("Procurar…")
        variant: "default"
        Layout.alignment: Qt.AlignLeft
        // seleção pelo portal XDG (§10.1): o diálogo nativo abre
        // fora do processo; o resultado volta em filePicked
        onClicked: {
            if (root.type === "file")
                bridge.pickOpenFile(root.optId, qsTr("Escolher arquivo"), root.multiple)
            else
                bridge.pickFolder(root.optId, qsTr("Escolher pasta"))
        }
    }

    Connections {
        target: bridge
        function onFilePicked(token, paths) {
            if (token !== root.optId || paths.length === 0)
                return
            if (root.type === "path" || !root.multiple)
                bridge.setOption(root.optId, paths[0])
            else
                bridge.setOption(root.optId, paths.join(","))
        }
    }

    RowLayout {
        visible: root.type === "slider"
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        AppSlider {
            id: sliderField
            Layout.fillWidth: true
            from: root.minimum !== "" ? Number(root.minimum) : 0
            to: root.maximum !== "" ? Number(root.maximum) : 100
            stepSize: root.step !== "" ? Number(root.step) : 1
            onMoved: bridge.setOption(root.optId, String(value))
            Component.onCompleted: root.syncSlider(sliderField)
            Connections {
                target: root
                function onValueChanged() { root.syncSlider(sliderField) }
            }
        }
        Label {
            text: String(Math.round(sliderField.value * 100) / 100)
            font.pixelSize: theme.smallFont
            opacity: 0.7
            Layout.minimumWidth: 48
            horizontalAlignment: Text.AlignRight
        }
    }

    AppSwitch {
        visible: root.type === "bool"
        checked: root.value === "1"
        onToggled: bridge.setOption(root.optId, checked ? "1" : "0")
    }

    AppComboBox {
        id: comboField
        visible: root.type === "choice"
        model: root.choices
        // `indexOf` devolve -1 para valor vazio, mas o
        // ComboBox normaliza -1 para 0 ao medir: só a
        // atribuição imperativa segura o -1 depois que
        // tudo está montado (ver syncCombo).
        currentIndex: root.value === undefined || root.value === null || root.value === ""
            ? -1
            : (root.choices ? root.choices.indexOf(root.value) : -1)
        Component.onCompleted: root.syncCombo(comboField)
        Connections {
            target: root
            function onValueChanged() { root.syncCombo(comboField) }
        }
        // o modelo só entra depois do `Component.onCompleted`:
        // reavalia a sincronia quando ele fica pronto.
        onModelChanged: root.syncCombo(comboField)
        onCountChanged: root.syncCombo(comboField)
        // parâmetro formal (Qt 6 não injeta `index` sozinho no handler)
        onActivated: function (idx) { bridge.setOption(root.optId, root.choices[idx]) }
    }

    Flow {
        visible: root.type === "multi"
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing
        Repeater {
            model: root.choices
            delegate: AppCheckBox {
                text: modelData
                checked: root.value !== undefined && root.value !== null && root.value !== ""
                       && String(root.value).split(",").indexOf(modelData) >= 0
                onToggled: {
                    var current = root.value ? String(root.value).split(",").filter(function (x) { return x !== ""; }) : []
                    var at = current.indexOf(modelData)
                    if (at >= 0) current.splice(at, 1); else current.push(modelData)
                    bridge.setOption(root.optId, current.join(","))
                }
            }
        }
    }

    // §4.3 type=paragraph: texto só para leitura, na largura do formulário
    Label {
        visible: root.type === "paragraph"
        text: root.label
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }

    // §4.3 type=link: botão nativo que abre o endereço declarado no script
    Button {
        visible: root.type === "link"
        flat: true
        icon.name: "internet-web-browser"
        text: root.label
        onClicked: bridge.openLink(root.url)
    }

    Label {
        text: root.help
        visible: text !== "" && (root.type === "bool" || root.type === "choice"
                || root.type === "multi" || root.type === "slider")
        opacity: 0.65
        font.pixelSize: theme.smallFont
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }

    // erro do campo: uma linha vermelha discreta. `InlineMessage` aqui
    // ocupava a largura toda com um ícone grande e empurrava o formulário.
    Label {
        Layout.fillWidth: true
        visible: root.error !== ""
        text: root.error
        color: theme.error
        font.pixelSize: theme.smallFont
        wrapMode: Text.WordWrap
    }
}

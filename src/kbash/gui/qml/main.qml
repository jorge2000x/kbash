// Janela principal do kbash (SPEC.md §10.1/§10.2).
//
// A janela é a `Kirigami.ApplicationWindow`: é dela que vem a barra de
// ferramentas nativa (ícone, título, botão voltar). O conteúdo das quatro
// telas NÃO vai pelo `pageStack`: o `ColumnView` que ele usa em modo largo
// deixa a tela anterior espremida ao lado da atual e não settle sozinho — o
// `StackLayout` troca o índice e pronto.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtCore
import pages
import org.kde.kirigami as Kirigami
import kbash

Kirigami.ApplicationWindow {
    id: window

    width: 940
    height: 700
    minimumWidth: 620
    minimumHeight: 480
    visible: true
    title: bridge.scriptName

    // -- geometria da janela (HIG: a janela volta como foi fechada) ------
    // Gravada ao fechar, restaurada ao abrir. O Qt limita o tamanho ao mínimo.
    Settings {
        id: geometria
        category: "janela"
        property int largura: 940
        property int altura: 700
        property int posX: 0
        property int posY: 0
        property bool temPosicao: false
    }

    Component.onCompleted: {
        window.width = geometria.largura
        window.height = geometria.altura
        if (geometria.temPosicao) {
            window.x = geometria.posX
            window.y = geometria.posY
        }
    }

    // a barra da janela (§10.2): ícone, título e subtítulo
    header: AppHeader {
        title: bridge.scriptName
        subtitle: bridge.scriptDescription
        iconName: bridge.scriptIcon
        iconFile: bridge.scriptIconFile
    }

    // -- ações da barra de menus (HIG do KDE: Arquivo, Editar, Configurações e Ajuda no
    // mínimo; toda função com atalho aparece aqui). O atalho fica na Action, porque o
    // MenuItem do QtQuick.Controls 6 não tem a propriedade `shortcut`.
    Action {
        id: quitAction
        text: qsTr("Sair")
        icon.name: "application-exit"
        shortcut: StandardKey.Quit
        onTriggered: window.close()
    }
    Action {
        id: copyLogAction
        text: qsTr("Copiar log")
        icon.name: "edit-copy"
        enabled: bridge.page >= 2  // execução e resultado têm log
        onTriggered: bridge.copyToClipboard(bridge.logText())
    }
    Action {
        id: logAction
        text: qsTr("Log da execução")
        icon.name: "utilities-log-viewer"
        shortcut: "Ctrl+L"
        checkable: true
        checked: bridge.logDrawerOpen
        onTriggered: bridge.logDrawerOpen = !bridge.logDrawerOpen
    }
    Action {
        id: backAction
        text: qsTr("Voltar")
        icon.name: "go-previous"
        shortcut: "Escape"
        enabled: bridge.page > 0
        // o goToPage ignora saída da execução em andamento e índices fora de 0..3
        onTriggered: bridge.goToPage(bridge.page - 1)
    }
    Action {
        id: configureShortcutsAction
        text: qsTr("Configurar atalhos…")
        icon.name: "configure-shortcuts"
        enabled: false  // ainda não implementado; desabilitado, não escondido
    }
    Action {
        id: aboutAction
        text: qsTr("Sobre o kbash")
        icon.name: "help-about"
        enabled: false  // ainda não implementado; desabilitado, não escondido
    }

    menuBar: MenuBar {
        Menu {
            title: qsTr("Arquivo")
            MenuItem { action: quitAction }
        }
        Menu {
            title: qsTr("Editar")
            MenuItem { action: copyLogAction }
        }
        Menu {
            title: qsTr("Exibir")
            MenuItem { action: logAction }
            MenuItem { action: backAction }
        }
        Menu {
            title: qsTr("Configurações")
            MenuItem { action: configureShortcutsAction }
        }
        Menu {
            title: qsTr("Ajuda")
            MenuItem { action: aboutAction }
        }
    }

    // A `ApplicationWindow` não põe Layout nenhum nos filhos diretos: sem
    // esta ColumnLayout ancorada, o StackLayout ficava com 0x0 e as telas
    // sumiam.
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        StackLayout {
            id: pageStack
            // `bridge.page` manda; o clamp protege contra índice solto.
            currentIndex: Math.max(0, Math.min(3, bridge.page))
            Layout.fillWidth: true
            Layout.fillHeight: true

            // SEM fade aqui: animar opacity da página inteira com o
            // log cheio engasga a troca (cada frame repinta tudo);
            // o StackLayout troca o índice seco e pronto
            onCurrentIndexChanged: {
                var item = pageStack.children[pageStack.currentIndex]
                if (item)
                    item.forceActiveFocus()
            }

            WelcomePage {}
            SelectPage {}
            RunPage {}
            ResultPage {}
        }
    }

    // [removido] `window.icon` não existe no Kirigami 6.10: atribuir
    // `window.icon.source`/`.name` dá "TypeError: Value is undefined"
    // no startup. O ícone da janela já vem de app.setWindowIcon (app.py).

    // -- prompts do protocolo (§8.2) -----------------------------------
    PromptDialog {
        id: promptDialog
    }

    // -- progresso dirigido pelo script (§8.4 rt_progresswin_*) ----------
    ProgressWinDialog {
        id: progressWinDialog
    }

    Connections {
        target: bridge
        function onPromptRequested(requestId, kind, text, label, defaultValue, choices, multi, secret, minimum, maximum) {
            promptDialog.requestId = requestId
            promptDialog.kind = kind
            promptDialog.promptText = text
            promptDialog.promptLabel = label
            promptDialog.promptDefault = defaultValue
            promptDialog.promptChoices = choices
            promptDialog.promptMulti = multi
            promptDialog.promptSecret = secret
            promptDialog.promptMin = minimum || ""
            promptDialog.promptMax = maximum || ""
            promptDialog.open()
        }
    }

    // -- avisos (rt_notify / §9.2, fim de execução, exclusão) -------------
    // Notificação passiva do Kirigami (HIG: avisos que não pedem decisão).
    // Erro e aviso ficam mais tempo na tela; o sucesso e a informação saem rápido.
    Connections {
        target: bridge
        function onNotifyRaised(text, level) {
            window.showPassiveNotification(text, level === "error" || level === "warn" ? "long" : "short")
        }
        function onRunFinishedSignal(status, message) {
            window.showPassiveNotification(message, status === "failed" || status === "cancelled" ? "long" : "short")
        }
        // "Desfazer" reverte a exclusão de predefinição (bridge.undoDeletePreset)
        function onPresetDeleted(name) {
            window.showPassiveNotification(qsTr("Predefinição excluída: %1").arg(name), "long",
                qsTr("Desfazer"), function () { bridge.undoDeletePreset() })
        }
    }

    // -- gaveta de log (§10.2.5): abre/fecha, sem painel fixo --------
    LogDrawer {
        id: logDrawer
    }

    onClosing: {
        geometria.largura = window.width
        geometria.altura = window.height
        geometria.posX = window.x
        geometria.posY = window.y
        geometria.temPosicao = true
        bridge.shutdown()
    }
}

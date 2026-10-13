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

    // a barra da janela (§10.2): ícone, título e subtítulo
    header: AppHeader {
        title: bridge.scriptName
        subtitle: bridge.scriptDescription
        iconName: bridge.scriptIcon
        iconFile: bridge.scriptIconFile
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

    // -- avisos como toast (rt_notify / §9.2) --------------------------
    Rectangle {
        id: toast
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: theme.largeSpacing * 3
        width: Math.min(toastText.implicitWidth + 32, window.width - 60)
        height: toastText.implicitHeight + 20
        radius: theme.cornerRadius
        opacity: 0
        visible: opacity > 0
        // fundo no `surface` e texto na cor do nível: pintar o fundo com a
        // cor de texto do nível deixava o branco ilegível no tema escuro.
        color: theme.surface
        border.width: 1
        border.color: theme.hairline(theme.onSurface(toast.level))

        property string level: "info"

        Behavior on opacity { NumberAnimation { duration: 180 } }

        Timer {
            id: toastTimer
            interval: 4000
            onTriggered: toast.opacity = 0
        }

        function show(text, level) {
            toastText.text = text
            toast.level = level || "info"
            toast.opacity = 1
            toastTimer.restart()
        }

        Label {
            id: toastText
            anchors.centerIn: parent
            width: toast.width - 32
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            color: theme.onSurface(toast.level)
        }
    }

    Connections {
        target: bridge
        function onNotifyRaised(text, level) { toast.show(text, level) }
        function onRunFinishedSignal(status, message) {
            toast.show(message, status === "failed" ? "error"
                              : status === "cancelled" ? "warn" : "success")
        }
    }

    // -- gaveta de log (§10.2.5): abre/fecha, sem painel fixo --------
    LogDrawer {
        id: logDrawer
    }

    Shortcut {
        sequence: "Ctrl+L"
        onActivated: bridge.logDrawerOpen = !bridge.logDrawerOpen
    }

    // Esc volta uma tela; o goToPage ignora saída da execução
    // em andamento e índices fora de 0..3, então é seguro aqui
    Shortcut {
        sequence: "Escape"
        onActivated: {
            if (bridge.page > 0)
                bridge.goToPage(bridge.page - 1)
        }
    }

    onClosing: bridge.shutdown()
}

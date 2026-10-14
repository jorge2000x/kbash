// 1. Boas-vindas (SPEC.md §10.2.1) e tela inicial sem script (§10.2.0)
//
// Sem script escolhido (`bridge.hasScript == false`): a home pede um `.sh` pelo
// portal de arquivos ou arrastado para a janela. Com script: a boas-vindas de
// sempre (ícone, nome, integridade, *Começar*).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import kbash

AppPage {
    id: page
    // sem heading: o cabeçalho rico (ícone + nome + descrição)
    // abaixo já diz tudo; o AppPage desenharia o nome duplicado
    subheading: ""

    // -- tela inicial (§10.2.0) ----------------------------------------
    ColumnLayout {
        visible: !bridge.hasScript
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: theme.largeSpacing

        Item { Layout.fillHeight: true }

        AppIcon {
            name: "system-software-install"
            glyphSize: 80
            Layout.alignment: Qt.AlignHCenter
            color: theme.accent
        }

        Kirigami.Heading {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignHCenter
            level: 1
            text: qsTr("Abra um script")
            horizontalAlignment: Text.AlignHCenter
        }

        Label {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignHCenter
            text: qsTr("Escolha um arquivo .sh anotado com o botão, ou arraste-o para esta janela.")
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            opacity: 0.8
        }

        // zona de arrastar: o DropArea só aceita links de arquivo (text/uri-list)
        Rectangle {
            id: dropZone
            Layout.fillWidth: true
            Layout.preferredHeight: Kirigami.Units.gridUnit * 8
            radius: theme.cornerRadius
            color: "transparent"
            border.width: dropArea.containsDrag ? 2 : 1
            border.color: dropArea.containsDrag ? theme.accent : theme.muted

            Label {
                anchors.centerIn: parent
                text: dropArea.containsDrag ? qsTr("Solte o script aqui") : qsTr("Arraste um script .sh para cá")
                opacity: 0.7
            }

            DropArea {
                id: dropArea
                anchors.fill: parent
                keys: ["text/uri-list"]
                onDropped: (drop) => {
                    if (drop.hasUrls && drop.urls.length > 0)
                        bridge.loadScript(drop.urls[0])
                }
            }
        }

        AppButton {
            Layout.alignment: Qt.AlignHCenter
            text: qsTr("Escolher script…")
            variant: "primary"
            // seleção pelo portal XDG (§10.1), o mesmo seletor das opções de arquivo
            onClicked: bridge.pickOpenFile("home-open", qsTr("Escolher script"), false)
        }

        // scripts .kbash da pasta do programa (gui/library.py), abaixo do que já existe
        AppCard {
            Layout.fillWidth: true
            visible: bridge.libraryEntries.length > 0
            title: qsTr("Scripts do programa")
            subtitle: qsTr("Abra direto um script desta pasta.")

            Repeater {
                model: bridge.libraryEntries
                delegate: ItemDelegate {
                    Layout.fillWidth: true
                    enabled: modelData.valid
                    text: modelData.description !== ""
                        ? modelData.name + " — " + modelData.description
                        : modelData.name
                    onClicked: bridge.loadScript(modelData.path)
                }
            }
        }

        Item { Layout.fillHeight: true }
    }

    Connections {
        target: bridge
        function onFilePicked(token, paths) {
            if (token === "home-open" && paths.length > 0)
                bridge.loadScript(paths[0])
        }
    }

    // -- boas-vindas do script escolhido ---------------------------------
    ColumnLayout {
        visible: bridge.hasScript
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: theme.largeSpacing

        Item { Layout.fillHeight: true }

        AppIcon {
            name: bridge.scriptIcon
            source: bridge.scriptIconFile
            glyphSize: 80
            Layout.alignment: Qt.AlignHCenter
            color: theme.accent
        }

        Kirigami.Heading {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignHCenter
            level: 1
            text: bridge.scriptName
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }

        Label {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignHCenter
            visible: bridge.scriptDescription !== ""
            text: bridge.scriptDescription
            horizontalAlignment: Text.AlignHCenter
            opacity: 0.8
            wrapMode: Text.WordWrap
        }

        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: theme.largeSpacing * 2
            visible: bridge.scriptVersion !== "" || bridge.scriptAuthor !== ""
            Label {
                visible: bridge.scriptVersion !== ""
                text: qsTr("versão ") + bridge.scriptVersion
                opacity: 0.7
            }
            Label {
                visible: bridge.scriptAuthor !== ""
                text: bridge.scriptAuthor
                opacity: 0.7
            }
        }

        // §9.1 — modo dev: caminho e SHA-256 antes de executar
        AppCard {
            title: qsTr("Integridade do script")
            subtitle: qsTr("Nenhum código é executado antes de você conferir isto aqui.")

            Label {
                Layout.fillWidth: true
                text: bridge.scriptPath
                font.family: "monospace"
                font.pixelSize: theme.smallFont
                wrapMode: Text.WrapAnywhere
                color: theme.muted
            }
            Label {
                Layout.fillWidth: true
                text: "SHA-256: " + bridge.scriptSha
                font.family: "monospace"
                font.pixelSize: theme.smallFont
                wrapMode: Text.WrapAnywhere
                color: theme.muted
            }
        }

        // §10.2.4 — o que fazer se o script não tem etapas
        InlineMessage {
            Layout.fillWidth: true
            tone: "warning"
            text: qsTr("Este script não declara nenhuma etapa (#@step).")
            visible: bridge.stepCount === 0
        }

        Item { Layout.fillHeight: true }

        RowLayout {
            Layout.fillWidth: true
            spacing: theme.largeSpacing

            Label {
                Layout.fillWidth: true
                text: {
                    if (bridge.stepCount === 0) return qsTr("Nada será executado.")
                    if (bridge.optionCount === 0) return qsTr("%1 etapa(s), sem opções.").arg(bridge.stepCount)
                    return qsTr("%1 etapa(s), %2 opção(ões).").arg(bridge.stepCount).arg(bridge.optionCount)
                }
                opacity: 0.7
                font.pixelSize: theme.smallFont
                elide: Text.ElideRight
            }

            AppButton {
                text: qsTr("Abrir outro…")
                onClicked: bridge.pickOpenFile("home-open", qsTr("Escolher script"), false)
            }

            AppButton {
                text: qsTr("Começar")
                variant: "primary"
                onClicked: bridge.goToPage(1)
            }
        }
    }
}

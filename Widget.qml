import QtQuick
import QtQuick.Controls as QQC
import QtQuick.Layouts
import QtQuick.Dialogs
import Quickshell
import "I18n.js" as I18n
import qs.Commons
import qs.Ui as Ui

Ui.Panel {
    id: root
    moduleName: "io.github.vitorpacheco.mega"
    ipcTarget: "mega"
    implicitWidth: barButton.implicitWidth
    implicitHeight: barButton.implicitHeight
    property int tab: 0
    property string form: ""
    property int formRevision: 0
    property string cancelTag: ""
    readonly property color ink: Color.foreground
    readonly property color muted: Qt.alpha(ink, 0.6)
    readonly property color line: Qt.alpha(ink, 0.12)
    readonly property color red: "#e65359"
    readonly property var statusData: mega.snapshot
    readonly property var locale: Qt.locale(mega.language === "pt" ? "pt_BR" : mega.language === "es" ? "es_ES" : "en_US")
    function tr(source, args) { return I18n.translate(mega.language, source, args) }
    function translatedError(source) { return I18n.error(mega.language, source) }
    function progress(value) {
        var match = /^([\d.]+)% of\s+(.+)$/.exec(String(value))
        return match ? tr("%1% de %2", [Number(match[1]).toLocaleString(locale, 'f', 1), match[2]]) : value
    }

    function bytes(n) {
        if (n === undefined || n === null) return "—"
        var units = ["B", "KB", "MB", "GB", "TB"]
        var i = 0
        while (n >= 1024 && i < 4) { n /= 1024; i++ }
        return Number(n).toLocaleString(root.locale, 'f', i === 0 ? 0 : 1) + " " + units[i]
    }
    function startForm(kind) {
        formRevision += 1
        form = kind
        mega.message = ""
        localField.text = ""
        remoteField.text = kind === "download" ? "" : "/"
    }
    function submit() {
        mega.act(form, {local: localField.text, remote: remoteField.text, formRevision: formRevision})
    }
    function filename(path) { return String(path || "").split("/").filter(p => p !== "").pop() || path }

    Service {
        id: mega
        settings: root.settings
        panelOpen: root.opened
        onActionSucceeded: function(action, request) {
            if (root.form === action && request.formRevision === root.formRevision) {
                root.form = ""
                root.tab = action === "sync-add" ? 1 : 0
            }
        }
    }

    component Label: Text {
        color: root.ink
        font.family: Style.font.family
        font.pixelSize: Style.space(12)
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
    }
    component Action: Ui.Button {
        focusable: true
        fontSize: Style.space(11)
        foreground: root.ink
        accent: root.red
        verticalPadding: Style.space(7)
        horizontalPadding: Style.space(9)
    }
    component Field: QQC.TextField {
        color: root.ink
        placeholderTextColor: root.muted
        font.family: Style.font.family
        font.pixelSize: Style.space(11)
        selectByMouse: true
        implicitHeight: Style.space(36)
        background: Rectangle {
            color: Qt.alpha(root.ink, 0.035)
            radius: Style.space(5)
            border.color: parent.activeFocus ? root.red : root.line
        }
    }
    component Rule: Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: root.line }

    Ui.BarIconButton {
        id: barButton
        anchors.fill: parent
        bar: root.bar
        tooltipText: "MEGA · " + mega.stateLabel
        iconComponent: Component {
            Item {
                Rectangle {
                    anchors.centerIn: parent
                    width: Style.space(14); height: width; radius: width / 2
                    color: "transparent"; border.color: barButton.foreground; border.width: 1.5
                    Text { anchors.centerIn: parent; text: "M"; color: barButton.foreground; font.pixelSize: Style.space(9); font.bold: true }
                }
                Rectangle {
                    anchors.right: parent.right; anchors.bottom: parent.bottom
                    width: Style.space(4); height: width; radius: width / 2
                    color: mega.healthy ? "#67bf9b" : root.red
                }
            }
        }
        onPressed: function(button) {
            if (button === Qt.MiddleButton) mega.refresh()
            else root.toggle()
        }
    }

    FileDialog {
        id: filePicker
        title: root.tr("Selecionar arquivo para enviar ao MEGA")
        onAccepted: localField.text = decodeURIComponent(selectedFile.toString().replace(/^file:\/\//, ""))
    }
    FolderDialog {
        id: folderPicker
        title: root.form === "download" ? root.tr("Pasta de destino") : root.tr("Selecionar pasta")
        onAccepted: localField.text = decodeURIComponent(selectedFolder.toString().replace(/^file:\/\//, ""))
    }

    Ui.KeyboardPanel {
        id: popup
        anchorItem: barButton
        owner: root
        bar: root.bar
        open: root.opened
        focusTarget: content
        contentWidth: fittedContentWidth(Style.space(410))
        contentHeight: cappedContentHeight(Style.space(570))

        FocusScope {
            id: content
            anchors.fill: parent
            Keys.onEscapePressed: {
                if (root.form !== "") root.form = ""
                else root.close()
            }
            ColumnLayout {
                anchors.fill: parent
                spacing: Style.space(12)
                RowLayout {
                    Layout.fillWidth: true
                    Rectangle {
                        implicitWidth: Style.space(34); implicitHeight: width; radius: width / 2; color: root.red
                        Text { anchors.centerIn: parent; text: "M"; color: "white"; font.bold: true; font.pixelSize: Style.space(20) }
                    }
                    ColumnLayout {
                        spacing: Style.space(2)
                        Layout.fillWidth: true
                        Label { text: "MEGA"; font.bold: true; font.pixelSize: Style.space(16) }
                        Label { text: root.statusData.connected ? root.tr("Sua nuvem, por perto") : root.tr("Arquivos em sincronia"); color: root.muted; font.pixelSize: Style.space(10) }
                    }
                    Action { text: "↗"; tooltipText: root.tr("Upgrade da conta"); onClicked: Qt.openUrlExternally("https://mega.nz/pro") }
                    Action { text: "⋮"; tooltipText: root.tr("Conta e opções"); onClicked: options.open() }
                    QQC.Menu {
                        id: options
                        QQC.MenuItem { text: root.tr("Abrir MEGA na web"); onTriggered: Qt.openUrlExternally("https://mega.nz/fm") }
                        QQC.MenuItem { text: root.tr("Conta / terminal MEGA"); enabled: !!root.statusData.installed; onTriggered: { root.close(); mega.terminal() } }
                        QQC.MenuItem { text: root.tr("Atualizar"); onTriggered: mega.refresh() }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Repeater {
                        model: [root.tr("Transferências"), root.tr("Sincronizações"), root.tr("Atividade")]
                        Action {
                            required property int index
                            required property string modelData
                            Layout.fillWidth: true
                            text: modelData
                            selected: root.tab === index
                            onClicked: { root.tab = index; root.form = "" }
                        }
                    }
                }
                Rule {}
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Style.space(18)
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Style.space(5)
                        Label { text: root.tr("Armazenamento"); font.pixelSize: Style.space(11) }
                        Label {
                            visible: mega.storageError !== ""
                            text: root.tr(mega.storageValue ? "Último valor conhecido" : "Armazenamento indisponível")
                            color: root.muted; font.pixelSize: Style.space(9)
                        }
                        Label {
                            text: mega.storageValue ? root.bytes(mega.storageValue.used) + " / " + root.bytes(mega.storageValue.total) : "— / —"
                            color: root.muted; font.pixelSize: Style.space(10)
                        }
                        Rectangle {
                            Layout.fillWidth: true; implicitHeight: Style.space(4); radius: height / 2; color: root.line
                            Rectangle {
                                height: parent.height; radius: height / 2; color: root.red
                                width: parent.width * (mega.storageValue && mega.storageValue.total > 0 ? Math.min(1, mega.storageValue.used / mega.storageValue.total) : 0)
                            }
                        }
                    }
                    Rectangle { implicitWidth: 1; implicitHeight: Style.space(40); color: root.line }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Style.space(5)
                        Label { text: root.tr("Transferências"); font.pixelSize: Style.space(11) }
                        Label { text: root.statusData.connected ? root.tr("%1 na fila", [root.statusData.transfers.length]) : "—"; color: root.muted; font.pixelSize: Style.space(10) }
                        Label { text: root.tr("Sessão MEGAcmd"); color: root.muted; font.pixelSize: Style.space(9) }
                    }
                }
                Rule {}
                QQC.ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: parent.width
                        spacing: Style.space(10)
                        ColumnLayout {
                            visible: !root.statusData.connected
                            Layout.fillWidth: true
                            spacing: Style.space(14)
                            Item { implicitHeight: Style.space(15) }
                            Label { Layout.alignment: Qt.AlignHCenter; text: "☁"; color: root.red; font.pixelSize: Style.space(70) }
                            Label { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; text: mega.stateLabel; font.pixelSize: Style.space(17) }
                            Label {
                                Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; color: root.muted
                                text: root.statusData.state === "missing"
                                    ? root.tr("Instale o MEGAcmd para conectar este painel à sua conta.")
                                    : root.tr("O painel usa uma sessão MEGAcmd própria. Entre pelo terminal; sua senha fica fora do plugin.")
                            }
                            Action {
                                Layout.alignment: Qt.AlignHCenter
                                text: root.statusData.state === "missing" ? root.tr("Como instalar") : root.tr("Entrar no MEGA")
                                onClicked: {
                                    if (root.statusData.state === "missing") Qt.openUrlExternally("https://mega.nz/cmd")
                                    else { root.close(); mega.terminal() }
                                }
                            }
                            Action { Layout.alignment: Qt.AlignHCenter; text: root.tr("Verificar conexão"); enabled: !mega.refreshing; onClicked: mega.refresh() }
                        }
                        ColumnLayout {
                            visible: root.form !== "" && root.statusData.connected
                            Layout.fillWidth: true
                            Label { text: root.form === "upload" ? root.tr("Enviar para o MEGA") : root.form === "download" ? root.tr("Baixar do MEGA") : root.tr("Sincronizar uma pasta"); font.bold: true }
                            Label { text: root.form === "download" ? root.tr("Origem no MEGA ou link público") : root.tr("Pasta de destino no MEGA (existente)"); color: root.muted; font.pixelSize: Style.space(10) }
                            Field { id: remoteField; Layout.fillWidth: true; placeholderText: root.form === "download" ? root.tr("https://mega.nz/file/… ou /Arquivo") : root.tr("/Documentos") }
                            Label { text: root.form === "download" ? root.tr("Salvar na pasta local") : root.tr("Arquivo ou pasta local"); color: root.muted; font.pixelSize: Style.space(10) }
                            Field { id: localField; Layout.fillWidth: true; placeholderText: "/home/…" }
                            RowLayout {
                                Action { text: root.tr("Arquivo…"); visible: root.form === "upload"; onClicked: filePicker.open() }
                                Action { text: root.tr("Pasta…"); onClicked: folderPicker.open() }
                            }
                            Label {
                                visible: root.form === "sync-add"; Layout.fillWidth: true; color: root.muted; font.pixelSize: Style.space(10)
                                text: root.tr("A sincronização é bidirecional, incluindo exclusões. Escolha uma pasta que não esteja sincronizada pelo MEGAsync.")
                            }
                            RowLayout {
                                Action { text: root.tr("Voltar"); onClicked: root.form = "" }
                                Action { text: mega.busy ? root.tr("Enviando…") : root.tr("Confirmar"); bordered: true; enabled: !mega.busy && localField.text !== "" && remoteField.text !== ""; onClicked: root.submit() }
                            }
                            Rule {}
                        }
                        ColumnLayout {
                            visible: root.statusData.connected && root.form === "" && root.tab === 0
                            Layout.fillWidth: true
                            RowLayout {
                                Action { text: root.tr("↑ Enviar"); onClicked: root.startForm("upload") }
                                Action { text: root.tr("↓ Baixar"); onClicked: root.startForm("download") }
                                Item { Layout.fillWidth: true }
                                Action { text: "Ⅱ"; tooltipText: root.tr("Pausar todas as transferências"); enabled: !mega.busy; onClicked: mega.act("pause-all") }
                                Action { text: "▷"; tooltipText: root.tr("Retomar todas as transferências"); enabled: !mega.busy; onClicked: mega.act("resume-all") }
                            }
                            ColumnLayout {
                                visible: root.statusData.transfers.length === 0
                                Layout.fillWidth: true
                                Item { implicitHeight: Style.space(22) }
                                Label { Layout.alignment: Qt.AlignHCenter; text: "☁"; color: Qt.alpha(root.ink, 0.22); font.pixelSize: Style.space(80) }
                                Label { Layout.alignment: Qt.AlignHCenter; text: root.statusData.state === "ready" ? root.tr("Tudo em dia") : root.tr("Dados indisponíveis"); font.pixelSize: Style.space(17) }
                                Label { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; text: root.statusData.state === "ready" ? root.tr("Seus próximos arquivos começam aqui.") : root.tr("Atualize para consultar a fila novamente."); color: root.muted; font.pixelSize: Style.space(11) }
                                Action { Layout.alignment: Qt.AlignHCenter; text: root.tr("Enviar para o MEGA"); onClicked: root.startForm("upload") }
                            }
                            Repeater {
                                model: root.statusData.transfers
                                ColumnLayout {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    spacing: Style.space(4)
                                    Label { Layout.fillWidth: true; text: modelData.TYPE + "  " + root.filename(modelData.SOURCEPATH); maximumLineCount: 2; elide: Text.ElideMiddle }
                                    Label { Layout.fillWidth: true; text: root.progress(modelData.PROGRESS) + " · " + root.tr(modelData.STATE); color: root.muted; font.pixelSize: Style.space(10) }
                                    Rectangle {
                                        Layout.fillWidth: true; implicitHeight: Style.space(3); color: root.line
                                        Rectangle { height: parent.height; color: root.red; width: parent.width * Math.max(0, Math.min(1, (parseFloat(modelData.PROGRESS) || 0) / 100)) }
                                    }
                                    RowLayout {
                                        Action { text: root.tr("Pausar"); enabled: !mega.busy; onClicked: mega.act("pause", {id: modelData.TAG}) }
                                        Action { text: root.tr("Retomar"); enabled: !mega.busy; onClicked: mega.act("resume", {id: modelData.TAG}) }
                                        Action { text: root.cancelTag === modelData.TAG ? root.tr("Confirmar cancelamento") : "×"; enabled: !mega.busy; tooltipText: root.tr("Cancelar transferência"); onClicked: {
                                            if (root.cancelTag === modelData.TAG) { mega.act("cancel", {id: modelData.TAG}); root.cancelTag = "" }
                                            else root.cancelTag = modelData.TAG
                                        } }
                                    }
                                    Rule {}
                                }
                            }
                            Label { visible: root.statusData.transfers.length >= 100; text: root.tr("Mostrando até 100 transferências."); color: root.muted }
                        }
                        ColumnLayout {
                            visible: root.statusData.connected && root.form === "" && root.tab === 1
                            Layout.fillWidth: true
                            Action { text: root.tr("+ Sincronizar pasta"); onClicked: root.startForm("sync-add") }
                            Label { visible: root.statusData.syncs.length === 0; Layout.fillWidth: true; text: root.tr("Nenhuma pasta nesta sessão MEGAcmd. As pastas do aplicativo MEGAsync são gerenciadas separadamente."); color: root.muted }
                            Repeater {
                                model: root.statusData.syncs
                                ColumnLayout {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    Label { Layout.fillWidth: true; text: "↔ " + root.filename(modelData.LOCALPATH); font.bold: true }
                                    Label { Layout.fillWidth: true; text: modelData.LOCALPATH + "\n↔ " + modelData.REMOTEPATH; color: root.muted; font.pixelSize: Style.space(10) }
                                    Label { Layout.fillWidth: true; text: root.tr(modelData.RUN_STATE) + " · " + root.tr(modelData.STATUS); font.pixelSize: Style.space(10) }
                                    Label { visible: modelData.ERROR !== "NO" && modelData.ERROR !== "NO_SYNC_ERROR" && modelData.ERROR !== "None" && modelData.ERROR !== ""; Layout.fillWidth: true; text: root.translatedError(modelData.ERROR); color: root.red }
                                    RowLayout {
                                        Action { text: modelData.RUN_STATE === "Running" ? root.tr("Pausar") : root.tr("Retomar"); enabled: !mega.busy; onClicked: mega.act(modelData.RUN_STATE === "Running" ? "sync-pause" : "sync-resume", {id: modelData.ID}) }
                                        Action { text: root.tr("Abrir pasta"); onClicked: mega.openFolder(modelData.LOCALPATH) }
                                    }
                                    Rule {}
                                }
                            }
                        }
                        ColumnLayout {
                            visible: root.tab === 2
                            Layout.fillWidth: true
                            Label { text: root.tr("Nesta sessão do painel"); color: root.muted; font.pixelSize: Style.space(10) }
                            Label { visible: mega.activity.length === 0; Layout.fillWidth: true; text: root.tr("Nenhuma atividade por enquanto."); color: root.muted }
                            Repeater {
                                model: mega.activity
                                Label { required property var modelData; Layout.fillWidth: true; text: new Date(modelData.time).toLocaleTimeString(root.locale, "HH:mm:ss") + "  " + (modelData.state ? root.tr("Estado do MEGA: %1", [root.tr(modelData.state)]) : root.translatedError(modelData.text)); color: modelData.failed ? root.red : root.ink; font.pixelSize: Style.space(11) }
                            }
                        }
                        Label { visible: root.statusData.errors.length > 0 && root.statusData.state !== "login"; Layout.fillWidth: true; text: root.statusData.errors.map(e => root.translatedError(e)).join("\n"); color: root.red; font.pixelSize: Style.space(10) }
                        Label {
                            visible: mega.storageError !== ""
                            Layout.fillWidth: true
                            text: root.tr("Armazenamento") + ": " + root.translatedError(mega.storageError)
                            color: root.muted; font.pixelSize: Style.space(10)
                        }
                        Label { visible: mega.message !== ""; Layout.fillWidth: true; text: root.translatedError(mega.message); color: root.muted; font.pixelSize: Style.space(11) }
                    }
                }
                Rule {}
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: mega.healthy ? "✓" : "○"; color: mega.healthy ? "#67bf9b" : root.red }
                    Label { text: mega.stateLabel; Layout.fillWidth: true; color: root.muted; font.pixelSize: Style.space(10) }
                    Action { text: mega.refreshing ? "…" : "↻"; tooltipText: root.tr("Atualizar agora"); enabled: !mega.refreshing; onClicked: mega.refresh() }
                }
            }
        }
    }
}

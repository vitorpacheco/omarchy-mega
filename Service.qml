import QtQuick
import Quickshell
import "I18n.js" as I18n
import Quickshell.Io

Item {
    id: root
    property var settings: ({})
    property bool panelOpen: false
    readonly property string language: I18n.resolve(settings.language, Qt.locale().name)
    function tr(source, args) { return I18n.translate(language, source, args) }
    property var snapshot: ({state: "loading", installed: false, connected: false, transfers: [], syncs: [], errors: []})
    property var activity: []
    property string message: ""
    property var storageValue: null
    property string storageError: ""
    property double storageUpdatedAt: 0
    property double nextStorageRefresh: 0
    property int storageFailures: 0
    property int storageEpoch: 0
    property bool forceStoragePending: false
    readonly property bool storageRefreshing: storagePoll.running
    signal actionSucceeded(string action, var request)
    readonly property bool busy: actionProcess.running
    readonly property bool refreshing: poll.running
    readonly property bool syncIssue: snapshot.syncs.some(s => s.RUN_STATE !== "Running" || s.STATUS !== "Synced")
    readonly property bool healthy: snapshot.state === "ready" && !syncIssue
    readonly property string executable: String(settings.execPath || "mega-exec")
    readonly property string bridge: decodeURIComponent(Qt.resolvedUrl("bin/mega_bridge.py").toString().replace(/^file:\/\//, ""))
    readonly property string stateLabel: {
        if (snapshot.state === "loading") return root.tr("Conectando…")
        if (snapshot.state === "missing") return root.tr("Instale o MEGAcmd")
        if (snapshot.state === "login") return root.tr("Entre na sua conta")
        if (snapshot.state === "error" || snapshot.state === "partial") return root.tr("Verifique a conexão")
        if (snapshot.transfers.length) return root.tr(snapshot.transfers.length === 1 ? "%1 transferência" : "%1 transferências", [snapshot.transfers.length])
        if (syncIssue) return root.tr("Verifique as sincronizações")
        return root.tr("Atualizado")
    }
    function record(text, failed, state) {
        activity = [{text: text, failed: failed, state: state || "", time: Date.now()}].concat(activity).slice(0, 40)
    }
    function clearStorage() {
        storageEpoch += 1
        storageValue = null
        storageError = ""
        storageUpdatedAt = 0
        nextStorageRefresh = 0
        storageFailures = 0
    }
    function refresh(forceStorage) {
        forceStoragePending = forceStoragePending || forceStorage !== false
        if (!poll.running) {
            poll.requestExecutable = executable
            poll.running = true
        }
    }
    function refreshStorage(force) {
        if (!snapshot.connected || storagePoll.running) return
        if (!force && Date.now() < nextStorageRefresh) return
        storagePoll.requestExecutable = executable
        storagePoll.requestEpoch = storageEpoch
        storagePoll.running = true
    }
    function act(action, values) {
        if (busy) return
        var request = Object.assign({}, values || {}, {action: action})
        actionProcess.request = JSON.stringify(request)
        message = "Enviando solicitação…"
        actionProcess.running = true
    }
    function terminal() {
        var cmd = executable === "mega-exec" ? "mega-cmd" : executable.replace(/mega-exec$/, "mega-cmd")
        Quickshell.execDetached(["omarchy", "launch", "tui", "--app-id=omarchy-mega", cmd])
        message = "No terminal MEGA, use login seu@email.com. A senha será solicitada lá."
    }
    Timer {
        interval: root.panelOpen ? 5000 : Math.max(5, Number(root.settings.refreshIntervalSec) || 15) * 1000
        running: true; repeat: true; triggeredOnStart: true
        onTriggered: root.refresh(false)
    }
    onPanelOpenChanged: if (panelOpen) refresh(false)
    onExecutableChanged: {
        clearStorage()
        snapshot = {state: "loading", installed: false, connected: false, transfers: [], syncs: [], errors: []}
        refresh(false)
    }
    Process {
        id: poll
        property string requestExecutable: ""
        command: ["python3", root.bridge, "--exec", requestExecutable, "status", "--skip-storage"]
        stdout: StdioCollector { id: pollOutput; waitForEnd: true }
        onExited: function(code) {
            if (requestExecutable !== root.executable) { root.refresh(false); return }
            try {
                var next = JSON.parse(pollOutput.text)
                if (code !== 0 || !next.state) throw new Error(next.error || "Resposta inválida")
                if (root.snapshot.state !== "loading" && root.snapshot.state !== next.state)
                    root.record(next.state === "ready" ? "Conexão com o MEGA estabelecida." : "Estado do MEGA: %1", next.state === "error", next.state === "ready" ? "" : next.state)
                var old = root.snapshot.transfers || []
                if (next.state === "ready" && old.length > 0 && next.transfers.length === 0)
                    root.record("A fila de transferências ficou vazia.", false)
                if (!next.connected || next.account !== root.snapshot.account) root.clearStorage()
                root.snapshot = next
                var force = root.forceStoragePending
                root.forceStoragePending = false
                root.refreshStorage(force)
            } catch (e) {
                root.clearStorage()
                root.snapshot = {state: "error", installed: true, connected: false, storage: null, transfers: [], syncs: [], errors: [String(e)]}
            }
        }
    }
    Process {
        id: storagePoll
        property string requestExecutable: ""
        property int requestEpoch: 0
        command: ["python3", root.bridge, "--exec", requestExecutable, "storage"]
        stdout: StdioCollector { id: storageOutput; waitForEnd: true }
        onExited: function(code) {
            if (requestEpoch !== root.storageEpoch || requestExecutable !== root.executable || !root.snapshot.connected) return
            try {
                var result = JSON.parse(storageOutput.text)
                if (code !== 0 || !result.ok || !result.storage) throw new Error(result.error || "Resposta inválida")
                root.storageValue = result.storage
                root.storageError = ""
                root.storageUpdatedAt = Date.now()
                root.storageFailures = 0
                root.nextStorageRefresh = Date.now() + 60000
            } catch (e) {
                root.storageError = String(e).replace(/^Error: /, "")
                root.storageFailures += 1
                root.nextStorageRefresh = Date.now() + Math.min(300000, 60000 * Math.pow(2, root.storageFailures - 1))
            }
        }
    }
    Process {
        id: actionProcess
        property string request: ""
        command: ["python3", root.bridge, "--exec", root.executable, "action"]
        stdinEnabled: true
        onStarted: { write(request); stdinEnabled = false }
        onRunningChanged: if (!running) stdinEnabled = true
        stdout: StdioCollector { id: actionOutput; waitForEnd: true }
        onExited: function(code) {
            try {
                var result = JSON.parse(actionOutput.text)
                var succeeded = code === 0 && result.ok === true
                root.message = succeeded ? result.message : (result.error || "Não foi possível executar a ação. Tente novamente.")
                root.record(root.message, !succeeded)
                if (succeeded) {
                    var request = JSON.parse(actionProcess.request)
                    root.actionSucceeded(request.action, request)
                }
            } catch (e) {
                root.message = "Não foi possível executar a ação. Tente novamente."
                root.record(root.message, true)
            }
            root.refresh()
        }
    }
}

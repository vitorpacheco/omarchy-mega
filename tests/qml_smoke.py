"""Run with python3 tests/qml_smoke.py in an Omarchy Wayland session.
Uses a fake MEGAcmd executable; never changes the user's account or syncs.
"""
from pathlib import Path
import subprocess
import tempfile

from qml_fixture import stage

with tempfile.TemporaryDirectory(prefix="mega-qml-test-") as folder:
    temp = Path(folder)
    stage(temp, '''#!/usr/bin/env python3
import sys
if sys.argv[1] == "whoami": print("test@example.com")
elif sys.argv[1] == "df": print("USED STORAGE: 7 7% of 100")
elif sys.argv[1] == "sync" and "/Fail" in sys.argv:
    print("Rejected", file=sys.stderr)
    sys.exit(1)
''')
    (temp / "shell.qml").write_text('''import QtQuick
import Quickshell
import "Plugin"
ShellRoot {
    property int stage: 0
    property var service: null
    Widget { id: widget; settings: ({language: "en"}) }
    function fail(text) { console.error("TEST_FAILED: " + text); Qt.quit() }
    Timer {
        interval: 100; running: true; repeat: true
        onTriggered: {
            if (!service) service = widget.children.find(c => c.snapshot !== undefined)
            if (!service) return
            if (stage === 0) {
                if (widget.tr("Transferências") !== "Transfers" || widget.bytes(1536) !== "1.5 KB") return fail("English")
                widget.settings = {language: "es"}
                stage = 1
            } else if (stage === 1) {
                if (widget.tr("Transferências") !== "Transferencias" || widget.bytes(1536) !== "1,5 KB") return fail("Spanish")
                widget.startForm("sync-add")
                service.act("sync-add", {local: "/tmp", remote: "/Fixture", formRevision: widget.formRevision})
                stage = 2
            } else if (stage === 2 && !service.busy) {
                if (widget.form !== "") return fail("Successful sync left the confirmation form open")
                if (widget.tab !== 1) return fail("Did not return to sync list")
                widget.startForm("sync-add")
                service.act("sync-add", {local: "/tmp", remote: "/Fail", formRevision: widget.formRevision})
                stage = 3
            } else if (stage === 3 && !service.busy) {
                if (widget.form !== "sync-add") return fail("Failed sync closed the form")
                service.act("sync-add", {local: "/tmp", remote: "/Fixture", formRevision: widget.formRevision})
                widget.startForm("sync-add")
                stage = 4
            } else if (stage === 4 && !service.busy) {
                if (widget.form !== "sync-add") return fail("Late success closed a newly opened form")
                console.log("QML_TESTS_OK")
                Qt.quit()
            }
        }
    }
    Timer { interval: 7000; running: true; onTriggered: fail("Timeout") }
}
''')
    result = subprocess.run(["quickshell", "-p", str(temp)], capture_output=True, text=True, timeout=15)
    output = result.stdout + result.stderr
    print(output)
    if "QML_TESTS_OK" not in output or "TEST_FAILED" in output:
        raise SystemExit(1)

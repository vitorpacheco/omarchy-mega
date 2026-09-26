"""Storage latency/recovery regression using a fake MEGAcmd (no account access)."""
from pathlib import Path
import subprocess
import tempfile

from qml_fixture import stage

with tempfile.TemporaryDirectory(prefix="mega-storage-test-") as folder:
    temp = Path(folder)
    fakes = stage(temp, '''#!/usr/bin/env python3
import sys,time
from pathlib import Path
if sys.argv[1] == 'whoami': print('fixture@example.com')
elif sys.argv[1] == 'df':
    counter = Path(__file__).with_name('calls')
    count = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(count))
    if count == 1: time.sleep(2)
    if count == 2:
        print('Storage endpoint unavailable', file=sys.stderr)
        sys.exit(1)
    print('USED STORAGE: ' + ('42' if count == 1 else '43') + ' 42% of 100')
''')
    (temp / "shell.qml").write_text('''import QtQuick
import Quickshell
import Quickshell.Io
import "Plugin"
ShellRoot {
    property int stage: 0
    Service { id: service; settings: ({}) }
    Process { id: uninstall; command: ["/usr/bin/touch", "MISSING"]; onExited: service.refresh(false) }
    function fail(text) { console.error("TEST_FAILED: " + text); Qt.quit() }
    Timer {
        interval: 800; running: true
        onTriggered: {
            if (!service.snapshot.connected || service.snapshot.state !== "ready") return fail("Slow storage blocked transfers and syncs")
            stage = 1
        }
    }
    Timer {
        interval: 100; running: true; repeat: true
        onTriggered: {
            if (stage === 1 && service.storageValue) {
                if (service.storageValue.used !== 42) return fail("Initial storage")
                service.refreshStorage(true)
                stage = 2
            } else if (stage === 2 && service.storageError !== "") {
                if (service.storageValue.used !== 42) return fail("Lost last known storage")
                if (service.snapshot.state !== "ready") return fail("Storage failure invalidated live sync data")
                service.refreshStorage(false)
                if (service.storageRefreshing) return fail("Automatic retry ignored backoff")
                service.refreshStorage(true)
                stage = 3
            } else if (stage === 3 && service.storageValue.used === 43) {
                if (service.storageError !== "") return fail("Recovery did not clear warning")
                uninstall.running = true
                stage = 4
            } else if (stage === 4 && service.snapshot.state === "missing") {
                if (service.storageValue !== null) return fail("Storage leaked after MEGAcmd disappeared")
                console.log("STORAGE_TESTS_OK"); Qt.quit()
            }
        }
    }
    Timer { interval: 6500; running: true; onTriggered: fail("Timeout") }
}
'''.replace("MISSING", str(fakes / "missing")))
    result = subprocess.run(["quickshell", "-p", str(temp)], capture_output=True, text=True, timeout=10)
    output = result.stdout + result.stderr
    print(output)
    if "STORAGE_TESTS_OK" not in output or "TEST_FAILED" in output:
        raise SystemExit(1)

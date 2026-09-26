"""Stage the plugin for QML tests with a fake MEGAcmd in place of the trusted system one."""
from pathlib import Path
import shutil

repo = Path(__file__).resolve().parents[1]


def stage(temp, fake_source):
    """Create shell root `temp` with Plugin/ backed by a fake mega-exec. Returns the fake's directory.

    The shipped bridge only runs MEGAcmd from root-owned system directories, so the staged
    bridge wraps it and resolves tools from the fixture directory instead. A `missing` file
    there simulates MEGAcmd being uninstalled.
    """
    for name in ("Commons", "Ui"):
        (temp / name).symlink_to(Path("/usr/share/omarchy/shell") / name)
    plugin = temp / "Plugin"
    (plugin / "bin").mkdir(parents=True)
    for name in ("Service.qml", "Widget.qml", "I18n.js", "manifest.json"):
        shutil.copy(repo / name, plugin / name)
    fakes = temp / "fakes"
    fakes.mkdir()
    fake = fakes / "mega-exec"
    fake.write_text(fake_source)
    fake.chmod(0o755)
    (plugin / "bin/mega_bridge.py").write_text(f'''import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("bridge", {str(repo / "bin/mega_bridge.py")!r})
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
def find_tool(name, fakes={str(fakes)!r}):
    path = os.path.join(fakes, name)
    return path if os.path.exists(path) and not os.path.exists(os.path.join(fakes, "missing")) else None
bridge.find_tool = find_tool
sys.exit(bridge.main())
''')
    return fakes

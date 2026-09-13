# MEGA Sync for Omarchy

A native Quickshell plugin that brings MEGA storage, transfers, and folder synchronization to the Omarchy bar. Inspired by the MEGAsync panel, it follows your Omarchy theme, fonts, and scaling.

The plugin uses **MEGAcmd only**. The MEGAsync desktop application is not required.

## Features

- Account storage usage and capacity.
- Transfer queue and progress, with pause, resume, and cancellation controls.
- File and folder uploads, plus downloads from remote paths or public links.
- Bidirectional folder syncs, with pause, resume, and local folder shortcuts.
- In-memory activity history for panel actions and connection changes.
- Shortcuts to MEGA on the web, account upgrades, and the MEGAcmd terminal.
- English, Portuguese, and Spanish localization, with English as the fallback.

## Requirements

- Omarchy with `omarchy-shell` and plugin support.
- Python 3.
- Qt Quick Dialogs, provided by the desktop's Qt installation.
- [MEGAcmd](https://mega.nz/cmd), including `mega-exec` and `mega-cmd` on your `PATH`.
- Git to clone this repository.

## Installation

### 1. Install MEGAcmd

Install the official MEGAcmd package for your distribution using the [MEGA download page](https://mega.nz/cmd). If you use the Arch AUR package, you can install it through Omarchy:

```bash
omarchy pkg aur add megacmd-bin
```

Check that both executables are available:

```bash
command -v mega-exec
command -v mega-cmd
```

### 2. Install the plugin

Use Omarchy's native plugin manager:

```bash
omarchy plugin add https://github.com/vitorpacheco/omarchy-mega.git --enable
```

Review the code when prompted. Omarchy clones the public repository into `~/.config/omarchy/plugins/io.github.vitorpacheco.mega`, validates the manifest, and enables the **M** icon in the right section of the bar. It does not run installation hooks or install MEGAcmd automatically.

For local development, you can instead install a copy from a checkout:

```bash
git clone https://github.com/vitorpacheco/omarchy-mega.git
cd omarchy-mega
./install.sh
```

The local installer validates the manifest, copies the runtime files, backs up an existing `shell.json`, and enables the plugin through Omarchy. It honors `XDG_CONFIG_HOME` when set and refuses to overwrite an existing plugin directory. Choose one installation method; they use the same plugin ID and destination.

Run either installation method as your normal desktop user.

### 3. Sign in

Click **M → Sign in to MEGA**. In the MEGAcmd terminal, enter:

```text
login your@email.com
```

MEGAcmd prompts for your password and, if enabled, your two-factor authentication code. The plugin does not handle or store your credentials.

Once signed in, close only the terminal while leaving the background service running:

```text
quit --only-shell
```

The panel detects the session automatically. You can reopen the terminal from **⋮ → Account / MEGA terminal**, or launch `mega-cmd` from a regular terminal.

## Configuration

Open the widget settings in Omarchy, or edit its existing entry under `bar.layout` in `~/.config/omarchy/shell.json`:

```json
{
  "id": "io.github.vitorpacheco.mega",
  "refreshIntervalSec": 15,
  "execPath": "mega-exec",
  "language": "auto"
}
```

This is a single widget entry, not a replacement for the entire `shell.json` file.

| Setting | Default | Description |
| --- | --- | --- |
| `refreshIntervalSec` | `15` | Polling interval while the panel is closed, in seconds. The settings editor accepts 5–300. |
| `execPath` | `mega-exec` | Executable name on `PATH`, or an absolute path to `mega-exec`. For a custom path, keep `mega-cmd` in the same directory. |
| `language` | `auto` | `auto`, `en` (English), `pt` (Portuguese), or `es` (Spanish). |

With `auto`, the panel follows the system locale. Unsupported locales and missing translations fall back to English. The selected language also applies to plugin messages, known status labels, numbers, and activity timestamps. Unknown MEGAcmd diagnostics remain verbatim, and native file chooser controls follow the system language.

While the panel is open, transfers and syncs refresh every 5 seconds. Storage is queried separately once per minute, so a slow storage response does not block the rest of the panel. Failed storage requests retry after 1–5 minutes; manual refresh can retry sooner. The last successful storage value remains visible with a “Last known value” label after a failure and is cleared when the account or backend changes. Each MEGAcmd command has a 25-second timeout, and overlapping polls are avoided. Settings changes are picked up by the shell automatically.

## Usage

### Upload and download

On the **Transfers** tab:

- Choose **Upload**, select a local file or folder, and enter an existing destination folder in MEGA.
- Choose **Download**, enter a remote path or public MEGA link, and select an existing local destination folder.
- Use the transfer controls to pause, resume, or cancel queued work. Cancellation requires a second click to confirm.

Remote paths start with `/`, such as `/Documents`. Create remote destination folders on the MEGA website or in the MEGAcmd terminal:

```text
mkdir /Documents
```

The queue displays up to 100 transfers. Its counter is not the account's transfer quota.

### Synchronize a folder

1. Create or choose an existing local folder.
2. Create or choose an existing remote folder in MEGA.
3. Open **Syncs → + Sync folder**.
4. Enter the remote path and select the local folder.
5. Click **Confirm**.

After a successful request, the form closes and returns to the sync list. If the request fails, the form stays open with the error message. Use **Pause**, **Resume**, or **Open folder** on the sync entry as needed.

Synchronization is bidirectional: changes and deletions propagate between the local and remote folders. MEGAcmd and MEGAsync have separate sessions, queues, and sync configurations; the plugin does not import the desktop application's configuration. Avoid syncing the same local folder with both clients simultaneously.

### Activity and keyboard controls

**Activity** records panel actions and connection changes in memory. It is not MEGA's account notification inbox and is cleared when the plugin reloads.

- **Escape:** close the current form or panel.
- **Tab:** move between controls.
- **Middle-click the bar icon:** refresh.

You can also toggle the panel through IPC:

```bash
omarchy-shell mega toggle
```

## Troubleshooting

**MEGAcmd is not detected:** check `command -v mega-exec`. If it is installed outside your `PATH`, set `execPath` to its absolute path.

**The panel asks you to sign in:** run `mega-cmd` and use `login your@email.com`. Being signed in to the MEGAsync desktop application does not sign you in to MEGAcmd.

**A sync reports that its local folder is unavailable:** check whether the folder was moved, renamed, or deleted. Restore the intended local folder before resuming, or remove the obsolete sync configuration and create a new one. To remove only a sync configuration, use a regular terminal:

```bash
mega-sync
mega-sync --delete <SYNC_ID>
```

Replace `<SYNC_ID>` with the ID shown by the first command. This removes the sync configuration, not the files in MEGA.

**A sync already exists:** check the **Syncs** tab or run `mega-sync` before submitting the same folder again.

**Plugin changes do not appear:** rescan the plugins:

```bash
omarchy-shell shell rescanPlugins
```

If the shell still uses cached code, restart it and ensure the plugin is enabled:

```bash
omarchy restart shell
omarchy plugin enable io.github.vitorpacheco.mega
```

## Updating

If you installed through `omarchy plugin add`, use the native update command:

```bash
omarchy plugin update io.github.vitorpacheco.mega
```

Omarchy fetches the repository, lets you review the changes, and updates the installed checkout.

### Updating a local copy

The installer copies files; it does not link the installed plugin to this checkout. To update, back up the installed plugin directory, update this checkout, and copy the runtime files again from the repository root:

```bash
git pull --ff-only
plugin_dir="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins/io.github.vitorpacheco.mega"
omarchy plugin validate .
cp I18n.js Service.qml Widget.qml manifest.json README.md LICENSE "$plugin_dir/"
cp bin/mega_bridge.py "$plugin_dir/bin/"
omarchy-shell shell rescanPlugins
```

## Disabling or removing the plugin

```bash
omarchy plugin disable io.github.vitorpacheco.mega
```

To uninstall the plugin files:

```bash
omarchy plugin remove io.github.vitorpacheco.mega
```

Disabling or removing the panel does not stop MEGAcmd or remove its sync configurations. Manage those separately through MEGAcmd.

## Permissions and background service

Like other Omarchy shell plugins, this plugin runs unsandboxed with your desktop user's permissions. Its QML files run inside the existing `omarchy-shell` process; it does not start another shell instance during normal use.

The panel invokes Python 3 and the local `mega-exec` command. MEGAcmd owns authentication, network connections to MEGA, file transfers, and the persistent `mega-cmd-server` background process. Commands run with the current user's file access. The plugin itself does not require root, read MEGAcmd's credential cache, or store passwords or transfer links in a plugin log.

The account shortcut opens `mega-cmd` through `omarchy launch tui`. Folder shortcuts use `xdg-open`, and web shortcuts open MEGA URLs in the default browser. Installing system dependencies may require administrator authentication; that is separate from installing or running this plugin. There are no remote build steps or downloaded scripts executed by the plugin.

## Development checks

Run these commands from the repository root. Node.js is required only for the localization checks. The QML smoke test requires an active Omarchy Wayland session and uses a fake MEGAcmd executable.

```bash
omarchy plugin validate .
python3 -m unittest discover -s tests -v
node tests/test_i18n.cjs
python3 tests/qml_smoke.py
python3 tests/qml_storage.py
```

To inspect the actual backend response, run:

```bash
python3 bin/mega_bridge.py status
```

Tests cover parsing, errors, timeouts, command construction, localization, and form completion. Real transfers require an authenticated session and user-selected files.

## References

- [MEGAcmd user guide](https://github.com/meganz/MEGAcmd/blob/master/UserGuide.md)
- [MEGAcmd command implementation](https://github.com/meganz/MEGAcmd/blob/master/src/megacmdexecuter.cpp)

## License

[MIT](LICENSE)

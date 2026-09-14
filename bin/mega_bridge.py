#!/usr/bin/env python3
"""Bounded, shell-free MEGAcmd adapter. No credentials or account cache access."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import time

SEPARATOR = "\x1f"
TRANSFER_COLS = ["TYPE", "TAG", "SOURCEPATH", "DESTINYPATH", "PROGRESS", "STATE"]
SYNC_COLS = ["ID", "LOCALPATH", "REMOTEPATH", "RUN_STATE", "STATUS", "ERROR"]

# Every MEGAcmd call is bounded in time and memory; MEGA-controlled names flow through here.
TIMEOUT = 25                 # seconds, whole process lifetime
KILL_GRACE = 2               # seconds between SIGTERM and SIGKILL
CHUNK = 65536
MAX_STDOUT = 2 * 1024 * 1024  # 100 transfers x two 4096-char paths fits comfortably
MAX_STDERR = 64 * 1024
MAX_ROWS = 100               # per table returned to QML
MAX_FIELD = 4096             # characters per table cell (matches --path-display-size)
MAX_ID = 64
MAX_ERRORS = 8
MAX_ERROR_CHARS = 800


class MegaError(Exception):
    pass


class _Overflow(Exception):
    pass


def _stop(proc):
    """Terminate, then kill, the whole process group and always reap the leader.

    The leader is not reaped until after SIGKILL: its zombie keeps the PID (and so the
    process group ID) reserved, so killpg can never hit an unrelated recycled group.
    """
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    grace_end = time.monotonic() + KILL_GRACE
    while time.monotonic() < grace_end:
        try:
            if os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT):
                break
        except ChildProcessError:
            break
        time.sleep(0.02)
    # Unconditional: descendants may outlive or ignore SIGTERM even after the leader exits.
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    proc.wait()


def run(executable, *args, timeout=TIMEOUT):
    """Run MEGAcmd with a whole-process deadline and hard stdout/stderr byte ceilings."""
    deadline = time.monotonic() + timeout
    try:
        proc = subprocess.Popen([executable, *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True,
                                env={**os.environ, "LC_ALL": "C", "LANG": "C"})
    except (OSError, ValueError) as exc:
        raise MegaError("Não foi possível executar o MEGAcmd.") from exc
    out_fd, err_fd = proc.stdout.fileno(), proc.stderr.fileno()
    buffers = {out_fd: bytearray(), err_fd: bytearray()}
    limits = {out_fd: MAX_STDOUT, err_fd: MAX_STDERR}
    finished = False
    try:
        with selectors.DefaultSelector() as selector:
            for fd in buffers:
                os.set_blocking(fd, False)
                selector.register(fd, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(executable, timeout)
                for key, _ in selector.select(remaining):
                    fd = key.fd
                    buffer = buffers[fd]
                    # Never read more than one byte past the ceiling.
                    try:
                        chunk = os.read(fd, min(CHUNK, limits[fd] + 1 - len(buffer)))
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(fd)
                        continue
                    buffer += chunk
                    if len(buffer) > limits[fd]:
                        raise _Overflow()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(executable, timeout)
        returncode = proc.wait(timeout=remaining)
        finished = True
    except subprocess.TimeoutExpired as exc:
        raise MegaError("O MEGAcmd não respondeu em 25 segundos. Confira a conexão e tente novamente.") from exc
    except _Overflow as exc:
        raise MegaError("A resposta do MEGAcmd excedeu o limite de tamanho permitido.") from exc
    finally:
        if not finished:
            _stop(proc)
        proc.stdout.close()
        proc.stderr.close()
    stdout = buffers[out_fd].decode("utf-8", "replace")
    stderr = buffers[err_fd].decode("utf-8", "replace")
    if returncode:
        raise MegaError((stderr or stdout or "O comando MEGA falhou.").strip()[-800:])
    return stdout


def table(raw, columns, max_rows=MAX_ROWS):
    """Parse MEGAcmd tabular output. Returns (rows, truncated)."""
    rows = []
    truncated = False
    for line in raw.splitlines():
        # splitlines also splits ASCII record separators, but not our unit separator.
        parts = [part.strip() for part in line.split(SEPARATOR)]
        if len(parts) != len(columns):
            if SEPARATOR in line:
                raise MegaError("Resposta tabular incompleta do MEGAcmd.")
            continue
        # MEGAcmd leaves unused header names blank when a transfer list is empty.
        if any(value == name for name, value in zip(columns, parts)):
            continue
        row = dict(zip(columns, parts))
        identifier = row.get("TAG", row.get("ID", ""))
        if not re.fullmatch(r"[\w-]{1,%d}" % MAX_ID, identifier):
            raise MegaError("Identificador inválido na resposta do MEGAcmd.")
        if len(rows) >= max_rows:
            truncated = True
            break
        for name, value in row.items():
            if len(value) > MAX_FIELD:
                row[name] = value[:MAX_FIELD - 1] + "…"
                truncated = True
        rows.append(row)
    # Empty output is valid; nonempty unfamiliar output must not become 'all synced'.
    if not rows and raw.strip() and SEPARATOR not in raw and not re.search(
            r"no (?:active |ongoing |configured )?(?:transfers|syncs|synchronizations)", raw, re.I):
        raise MegaError("Formato de resposta não reconhecido. Atualize o MEGAcmd.")
    return rows, truncated


def storage(raw):
    match = re.search(r"USED STORAGE:\s*([\d,]+)\s*(?:B|Bytes)?\s+.*?\bof\s+([\d,]+)", raw)
    if not match:
        raise MegaError("Não foi possível interpretar o armazenamento informado pelo MEGA.")
    return {"used": int(match[1].replace(",", "")), "total": int(match[2].replace(",", ""))}


def status(executable, include_storage=True):
    base = {"installed": bool(shutil.which(executable)), "connected": False,
            "storage": None, "transfers": [], "syncs": [], "errors": []}
    if not base["installed"]:
        base["state"] = "missing"
        return base
    try:
        who = run(executable, "whoami")
    except MegaError as exc:
        base["state"] = "login" if "not logged in" in str(exc).lower() else "error"
        base["errors"] = [str(exc)[:MAX_ERROR_CHARS]]
        return base
    base.update(connected=True, state="ready")
    account = re.search(r"[\w.+-]{1,64}@[\w.-]{1,255}", who)
    base["account"] = account[0] if account else "Conta MEGA"
    jobs = {
        "storage": ("df",),
        "transfers": ("transfers", "--show-syncs", "--limit=100", "--path-display-size=4096",
                      "--col-separator=" + SEPARATOR, "--output-cols=" + ",".join(TRANSFER_COLS)),
        "syncs": ("sync", "--path-display-size=4096", "--col-separator=" + SEPARATOR,
                  "--output-cols=" + ",".join(SYNC_COLS)),
    }
    if not include_storage:
        del jobs["storage"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {key: pool.submit(run, executable, *args) for key, args in jobs.items()}
        for key, future in futures.items():
            try:
                raw = future.result()
                if key == "storage":
                    base[key] = storage(raw)
                else:
                    base[key], truncated = table(raw, TRANSFER_COLS if key == "transfers" else SYNC_COLS)
                    base["truncated"] = base.get("truncated", False) or truncated
            except MegaError as exc:
                base["errors"].append(f"{key}: {exc}"[:MAX_ERROR_CHARS])
    base["errors"] = base["errors"][:MAX_ERRORS]
    if base["errors"]:
        base["state"] = "partial"
    return base


def safe_value(value):
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        raise MegaError("Preencha os caminhos sem caracteres de controle.")
    if value.startswith("-"):
        raise MegaError("Use um caminho absoluto, começando por /.")
    return value


def local_path(value, directory=False):
    path = Path(safe_value(value)).expanduser()
    if not path.is_absolute() or not path.exists() or (directory and not path.is_dir()):
        raise MegaError("Selecione um caminho local existente e absoluto.")
    return str(path)


def remote_path(value):
    value = safe_value(value)
    if not value.startswith("/"):
        raise MegaError("O caminho no MEGA deve começar por /.")
    return value


def action_args(action, values):
    if action in ("pause", "resume", "cancel"):
        tag = values.get("id", "")
        if not re.fullmatch(r"\d+", tag):
            raise MegaError("Transferência inválida.")
        return ["transfers", {"pause": "-p", "resume": "-r", "cancel": "-c"}[action], tag]
    if action in ("pause-all", "resume-all"):
        return ["transfers", "-p" if action == "pause-all" else "-r", "-a"]
    if action in ("sync-pause", "sync-resume"):
        ident = safe_value(values.get("id", ""))
        if not re.fullmatch(r"[\w-]+", ident):
            raise MegaError("Sincronização inválida.")
        return ["sync", "-p" if action == "sync-pause" else "-e", ident]
    if action == "upload":
        return ["put", "-q", local_path(values.get("local", "")), remote_path(values.get("remote", ""))]
    if action == "download":
        source = safe_value(values.get("remote", ""))
        if not source.startswith("/") and not re.match(r"^https://mega\.(nz|co\.nz)/", source):
            raise MegaError("Informe um caminho no MEGA ou um link https://mega.nz/.")
        return ["get", "-q", source, local_path(values.get("local", ""), True)]
    if action == "sync-add":
        return ["sync", local_path(values.get("local", ""), True), remote_path(values.get("remote", ""))]
    raise MegaError("Ação desconhecida.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exec", default="mega-exec", dest="executable")
    parser.add_argument("operation", choices=["status", "storage", "action"])
    parser.add_argument("--skip-storage", action="store_true")
    args = parser.parse_args()
    try:
        if args.operation == "status":
            result = status(args.executable, include_storage=not args.skip_storage)
        elif args.operation == "storage":
            result = {"ok": True, "storage": storage(run(args.executable, "df"))}
        else:
            request = json.load(sys.stdin)
            command = action_args(request["action"], request)
            run(args.executable, *command)
            result = {"ok": True, "message": "Solicitação aceita pelo MEGA."}
        print(json.dumps(result, ensure_ascii=False))
    except (MegaError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

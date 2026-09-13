#!/usr/bin/env python3
"""Bounded, shell-free MEGAcmd adapter. No credentials or account cache access."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

SEPARATOR = "\x1f"
TRANSFER_COLS = ["TYPE", "TAG", "SOURCEPATH", "DESTINYPATH", "PROGRESS", "STATE"]
SYNC_COLS = ["ID", "LOCALPATH", "REMOTEPATH", "RUN_STATE", "STATUS", "ERROR"]


class MegaError(Exception):
    pass


def run(executable, *args):
    try:
        result = subprocess.run([executable, *args], capture_output=True, text=True,
                                timeout=25, env={**os.environ, "LC_ALL": "C", "LANG": "C"})
    except subprocess.TimeoutExpired as exc:
        raise MegaError("O MEGAcmd não respondeu em 25 segundos. Confira a conexão e tente novamente.") from exc
    except OSError as exc:
        raise MegaError("Não foi possível executar o MEGAcmd.") from exc
    if result.returncode:
        raise MegaError((result.stderr or result.stdout or "O comando MEGA falhou.").strip()[-800:])
    return result.stdout


def table(raw, columns):
    rows = []
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
        if not identifier or not re.fullmatch(r"[\w-]+", identifier):
            raise MegaError("Identificador inválido na resposta do MEGAcmd.")
        rows.append(row)
    # Empty output is valid; nonempty unfamiliar output must not become 'all synced'.
    if not rows and raw.strip() and SEPARATOR not in raw and not re.search(
            r"no (?:active |ongoing |configured )?(?:transfers|syncs|synchronizations)", raw, re.I):
        raise MegaError("Formato de resposta não reconhecido. Atualize o MEGAcmd.")
    return rows


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
        base["errors"] = [str(exc)]
        return base
    base.update(connected=True, state="ready")
    account = re.search(r"[\w.+-]+@[\w.-]+", who)
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
                base[key] = storage(raw) if key == "storage" else table(
                    raw, TRANSFER_COLS if key == "transfers" else SYNC_COLS)
            except MegaError as exc:
                base["errors"].append(f"{key}: {exc}")
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

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("bridge", Path(__file__).parents[1] / "bin/mega_bridge.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class BridgeTests(unittest.TestCase):
    def test_storage_bytes_and_zero(self):
        self.assertEqual(b.storage("USED STORAGE:  1468006   0.00% of 53687091200"),
                         {"used": 1468006, "total": 53687091200})
        self.assertEqual(b.storage("USED STORAGE: 0 0.00% of 100")["used"], 0)
        with self.assertRaises(b.MegaError):
            b.storage("Connection failed")

    def test_columns_preserve_spaces_and_unicode(self):
        row = ["⇑", "47", "/home/me/Olá mundo ' $(touch nope).txt", "/Backup", "52.10% of 2 MB", "ACTIVE"]
        text = b.SEPARATOR.join(b.TRANSFER_COLS) + "\n" + b.SEPARATOR.join(row)
        result = b.table(text, b.TRANSFER_COLS)
        self.assertEqual(result[0]["SOURCEPATH"], row[2])
        self.assertEqual(result[0]["TAG"], "47")

    def test_empty_transfer_header_and_truncated_rows(self):
        empty = b.SEPARATOR.join(["", "", "SOURCEPATH", "DESTINYPATH", "", ""])
        self.assertEqual(b.table(empty, b.TRANSFER_COLS), [])
        with self.assertRaises(b.MegaError):
            b.table(b.SEPARATOR.join(["upload", "3", "truncated"]), b.TRANSFER_COLS)

    def test_unrecognized_response_is_not_empty_success(self):
        self.assertEqual(b.table("", b.SYNC_COLS), [])
        with self.assertRaises(b.MegaError):
            b.table("Unexpected server error", b.SYNC_COLS)

    def test_paths_are_argv_and_cannot_inject_options(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "a ' $(touch sentinel).txt"
            path.touch()
            args = b.action_args("upload", {"local": str(path), "remote": "/Pasta com espaços"})
            self.assertEqual(args, ["put", "-q", str(path), "/Pasta com espaços"])
        for value in ("--help", "/ok\nbad", "", "relative"):
            with self.subTest(value=value), self.assertRaises(b.MegaError):
                b.action_args("upload", {"local": value, "remote": "/"})

    def test_transfer_and_sync_controls(self):
        self.assertEqual(b.action_args("pause", {"id": "123"}), ["transfers", "-p", "123"])
        self.assertEqual(b.action_args("resume-all", {}), ["transfers", "-r", "-a"])
        self.assertEqual(b.action_args("sync-resume", {"id": "abc_123"}), ["sync", "-e", "abc_123"])
        with self.assertRaises(b.MegaError):
            b.action_args("cancel", {"id": "-a"})

    def test_download_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(b.action_args("download", {"remote": "https://mega.nz/file/a#b", "local": folder}),
                             ["get", "-q", "https://mega.nz/file/a#b", folder])
            with self.assertRaises(b.MegaError):
                b.action_args("download", {"remote": "https://mega.nz.evil/file/a", "local": folder})

    def test_missing_and_logged_out(self):
        with patch.object(b.shutil, "which", return_value=None):
            self.assertEqual(b.status("mega-exec")["state"], "missing")
        with patch.object(b.shutil, "which", return_value="/bin/mega-exec"), \
             patch.object(b, "run", side_effect=b.MegaError("Not logged in.")):
            state = b.status("mega-exec")
            self.assertEqual(state["state"], "login")
            self.assertFalse(state["connected"])
            self.assertIsNone(state["storage"])

    def test_partial_failure_preserves_only_successful_sections(self):
        def fake_run(executable, command, *args):
            if command == "whoami": return "Account: user@example.com"
            if command == "df": return "USED STORAGE: 42 42.0% of 100"
            if command == "transfers": raise b.MegaError("offline")
            return ""
        with patch.object(b.shutil, "which", return_value="/bin/mega-exec"), patch.object(b, "run", side_effect=fake_run):
            state = b.status("mega-exec")
            self.assertEqual(state["state"], "partial")
            self.assertEqual(state["storage"]["used"], 42)
            self.assertEqual(state["transfers"], [])
            self.assertTrue(state["errors"])

    def test_timeout_and_nonzero_exit(self):
        with patch.object(b.subprocess, "run", side_effect=subprocess.TimeoutExpired("mega-exec", 25)):
            with self.assertRaises(b.MegaError): b.run("mega-exec", "df")
        with patch.object(b.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "offline")):
            with self.assertRaisesRegex(b.MegaError, "offline"): b.run("mega-exec", "df")

    def test_real_subprocess_protocol(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = Path(folder) / "mega-exec"
            fake.write_text('#!/usr/bin/env python3\nimport sys\nif sys.argv[1] == "whoami": print("user@example.com")\nelif sys.argv[1] == "df": print("USED STORAGE: 7 7% of 100")\n')
            fake.chmod(0o755)
            result = b.status(str(fake))
            self.assertEqual(result["state"], "ready")
            self.assertEqual(result["storage"], {"used": 7, "total": 100})


if __name__ == "__main__":
    unittest.main()

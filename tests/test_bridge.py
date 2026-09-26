import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
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
        result, truncated = b.table(text, b.TRANSFER_COLS)
        self.assertFalse(truncated)
        self.assertEqual(result[0]["SOURCEPATH"], row[2])
        self.assertEqual(result[0]["TAG"], "47")

    def test_empty_transfer_header_and_truncated_rows(self):
        empty = b.SEPARATOR.join(["", "", "SOURCEPATH", "DESTINYPATH", "", ""])
        self.assertEqual(b.table(empty, b.TRANSFER_COLS), ([], False))
        with self.assertRaises(b.MegaError):
            b.table(b.SEPARATOR.join(["upload", "3", "truncated"]), b.TRANSFER_COLS)

    def test_unrecognized_response_is_not_empty_success(self):
        self.assertEqual(b.table("", b.SYNC_COLS), ([], False))
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
        self.assertEqual(b.status(None)["state"], "missing")
        with patch.object(b, "run", side_effect=b.MegaError("Not logged in.")):
            state = b.status("/bin/mega-exec")
            self.assertEqual(state["state"], "login")
            self.assertFalse(state["connected"])
            self.assertIsNone(state["storage"])

    def test_partial_failure_preserves_only_successful_sections(self):
        def fake_run(executable, command, *args):
            if command == "whoami": return "Account: user@example.com"
            if command == "df": return "USED STORAGE: 42 42.0% of 100"
            if command == "transfers": raise b.MegaError("offline")
            return ""
        with patch.object(b, "run", side_effect=fake_run):
            state = b.status("/bin/mega-exec")
            self.assertEqual(state["state"], "partial")
            self.assertEqual(state["storage"]["used"], 42)
            self.assertEqual(state["transfers"], [])
            self.assertTrue(state["errors"])

    def fake_exec(self, folder, body):
        fake = Path(folder) / "mega-exec"
        fake.write_text("#!/usr/bin/env python3\nimport os, signal, subprocess, sys, time\n" + body)
        fake.chmod(0o755)
        return str(fake)

    def assertGroupGone(self, pidfile):
        pid = int(Path(pidfile).read_text())
        for _ in range(100):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.02)
        self.fail(f"descendant {pid} survived cleanup")

    def test_nonzero_exit_and_missing_executable(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = self.fake_exec(folder, 'sys.stderr.write("offline\\n"); sys.exit(1)\n')
            with self.assertRaisesRegex(b.MegaError, "offline"): b.run(fake, "df")
            with self.assertRaises(b.MegaError): b.run(str(Path(folder) / "absent"), "df")

    def test_deadline_kills_whole_process_group(self):
        with tempfile.TemporaryDirectory() as folder:
            pidfile = Path(folder) / "child.pid"
            # Leader ignores SIGTERM and a grandchild holds the pipes open.
            fake = self.fake_exec(folder, f'signal.signal(signal.SIGTERM, signal.SIG_IGN)\n'
                                  f'c = subprocess.Popen([sys.executable, "-c", "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"])\n'
                                  f'open({str(pidfile)!r}, "w").write(str(c.pid))\nprint("partial", flush=True)\ntime.sleep(60)\n')
            started = time.monotonic()
            with self.assertRaisesRegex(b.MegaError, "não respondeu"): b.run(fake, "df", timeout=1)
            self.assertLess(time.monotonic() - started, 1 + b.KILL_GRACE + 2)
            self.assertGroupGone(pidfile)

    def test_deadline_applies_after_leader_exits(self):
        with tempfile.TemporaryDirectory() as folder:
            pidfile = Path(folder) / "child.pid"
            fake = self.fake_exec(folder, f'c = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])\n'
                                  f'open({str(pidfile)!r}, "w").write(str(c.pid))\n')
            with self.assertRaisesRegex(b.MegaError, "não respondeu"): b.run(fake, "df", timeout=1)
            self.assertGroupGone(pidfile)

    def test_stdout_and_stderr_byte_ceilings(self):
        with tempfile.TemporaryDirectory() as folder:
            for stream in ("stdout", "stderr"):
                with self.subTest(stream=stream):
                    pidfile = Path(folder) / f"{stream}.pid"
                    fake = self.fake_exec(folder, f'open({str(pidfile)!r}, "w").write(str(os.getpid()))\n'
                                          f'out = sys.{stream}.buffer\nwhile True: out.write(b"x" * 65536)\n')
                    started = time.monotonic()
                    received = []
                    def reader(fd, size, real=os.read):
                        chunk = real(fd, size)
                        received.append((size, len(chunk)))
                        return chunk
                    with patch.object(b, "MAX_STDOUT", 200000), patch.object(b, "MAX_STDERR", 50000), \
                         patch.object(b.os, "read", side_effect=reader):
                        with self.assertRaisesRegex(b.MegaError, "limite"): b.run(fake, "df")
                    limit = 200000 if stream == "stdout" else 50000
                    self.assertLessEqual(max(size for size, _ in received), b.CHUNK)
                    # Only the overflowing stream can have been read up to its ceiling + 1.
                    self.assertLessEqual(sum(n for _, n in received), limit + 1 + (200000 if stream == "stderr" else 0))
                    self.assertLess(time.monotonic() - started, 5)
                    self.assertGroupGone(pidfile)

    def test_output_exactly_at_ceiling_is_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = self.fake_exec(folder, 'sys.stdout.write("y" * 1000)\n')
            with patch.object(b, "MAX_STDOUT", 1000):
                self.assertEqual(len(b.run(fake, "df")), 1000)

    def test_row_and_field_caps(self):
        rows = [b.SEPARATOR.join(["⇑", str(i), "/" + "a" * 10000, "/B", "1%", "ACTIVE"]) for i in range(500)]
        result, truncated = b.table("\n".join(rows), b.TRANSFER_COLS)
        self.assertTrue(truncated)
        self.assertEqual(len(result), b.MAX_ROWS)
        self.assertEqual(len(result[0]["SOURCEPATH"]), b.MAX_FIELD)
        with self.assertRaises(b.MegaError):
            b.table(b.SEPARATOR.join(["⇑", "1" * (b.MAX_ID + 1), "/a", "/B", "1%", "ACTIVE"]), b.TRANSFER_COLS)

    def test_status_json_is_bounded(self):
        row = lambda i: b.SEPARATOR.join([str(i), "/" + "l" * 9000, "/" + "r" * 9000, "Running", "Synced", ""])
        def fake_run(executable, command, *args):
            if command == "whoami": return "user@example.com"
            if command == "transfers": raise b.MegaError("x" * 5000)
            return "\n".join(row(i) for i in range(1000))
        with patch.object(b, "run", side_effect=fake_run):
            state = b.status("/bin/mega-exec", include_storage=False)
        self.assertTrue(state["truncated"])
        self.assertEqual(len(state["syncs"]), b.MAX_ROWS)
        self.assertLessEqual(len(state["errors"][0]), b.MAX_ERROR_CHARS)
        self.assertLess(len(json.dumps(state, ensure_ascii=False).encode()),
                        2 * b.MAX_ROWS * len(b.SYNC_COLS) * b.MAX_FIELD * 4)

    def test_only_root_owned_system_executables_are_trusted(self):
        with patch.object(b, "TRUSTED_DIRS", ("/usr/bin",)):
            self.assertEqual(b.find_tool("env"), os.path.realpath("/usr/bin/env"))
            self.assertIsNone(b.find_tool("absent-mega-tool"))
            self.assertIsNone(b.find_tool("../../tmp"))
        with tempfile.TemporaryDirectory() as folder:
            fake = self.fake_exec(folder, "")
            # User-owned files and directories are rejected even when listed as trusted.
            self.assertFalse(b._trusted(fake))
            with patch.object(b, "TRUSTED_DIRS", (folder,)):
                self.assertIsNone(b.find_tool("mega-exec"))
        self.assertFalse(b._trusted("/tmp"))  # root-owned but world-writable
        self.assertTrue(b._trusted(os.path.realpath("/usr/bin/env")))

    def test_megacmd_runs_with_closed_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = self.fake_exec(folder, "import json\nprint(json.dumps(dict(os.environ)))\n")
            hostile = {"PATH": folder, "LD_PRELOAD": "/nonexistent.so", "PYTHONPATH": folder, "HOME": folder}
            with patch.dict(os.environ, hostile):
                env = json.loads(b.run(fake, "whoami"))
        self.assertEqual(set(env) - {"PWD", "SHLVL", "_"}, {"HOME", "PATH", "LC_ALL", "LANG"})
        self.assertEqual(env["PATH"], folder + ":/usr/bin")
        self.assertNotEqual(env["HOME"], folder)

    def test_executable_cannot_be_chosen_by_caller(self):
        bridge = Path(__file__).parents[1] / "bin/mega_bridge.py"
        result = subprocess.run([sys.executable, "-I", str(bridge), "--exec", "/tmp/evil", "status"],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        with patch.object(b, "find_tool", return_value=None), patch.object(sys, "argv", ["bridge", "storage"]), \
             patch("builtins.print") as printed:
            self.assertEqual(b.main(), 1)
        self.assertFalse(json.loads(printed.call_args[0][0])["ok"])

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

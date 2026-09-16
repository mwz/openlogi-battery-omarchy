"""Exercise the guard with real, synthetic producers; no hardware required."""

import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from helper_fixture import write_helper_launcher


HELPER = Path(__file__).resolve().parents[1] / "openlogi-bounded.py"
spec = importlib.util.spec_from_file_location("guard", HELPER)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
PYTHON = "/usr/bin/python3"


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="openlogi-test-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.launcher = self.directory / "helper.py"
        write_helper_launcher(self.launcher, self.directory / "openlogi")

    def collect(self, body, failure=None, timeout=1):
        children = []
        popen = subprocess.Popen

        def spawn(*args, **kwargs):
            child = popen(*args, **kwargs)
            children.append(child)
            return child

        with patch.object(guard.subprocess, "Popen", side_effect=spawn), \
                patch.object(guard, "TIMEOUT_SECONDS", timeout):
            if failure is None:
                result = guard.collect([PYTHON, "-I", "-c", body])
                self.assertLessEqual(len(result[1]), 65536)
                self.assertLessEqual(len(result[2]), 8192)
            else:
                with self.assertRaises(guard.GuardFailure) as raised:
                    guard.collect([PYTHON, "-I", "-c", body])
                self.assertEqual(raised.exception.code, failure)
                result = None

        self.assertEqual(len(children), 1)
        child = children[0]
        self.assertIsNotNone(child.returncode)
        self.assertTrue(child.stdout.closed)
        self.assertTrue(child.stderr.closed)
        # A non-None returncode alone is insufficient evidence of reaping.
        with self.assertRaises(ChildProcessError):
            os.waitpid(child.pid, os.WNOHANG)
        return result

    def executable(self, body):
        executable = self.directory / "openlogi"
        executable.write_text("#!/usr/bin/python3\n" + body)
        executable.chmod(0o700)

    def cli(self, body=None):
        if body is not None:
            self.executable(body)
        result = subprocess.run(
            [PYTHON, "-I", str(self.launcher)],
            env={**os.environ, "PATH": str(self.directory)},
            capture_output=True, timeout=8,
        )
        self.assertLessEqual(len(result.stdout), 65536)
        self.assertLessEqual(len(result.stderr), 8192)
        return result

    def test_exact_limits_and_binary_output(self):
        code, stdout, stderr = self.collect(
            "import os\nos.write(1, b'\\xff' * 65536)\nos.write(2, b'e' * 8192)"
        )
        self.assertEqual(code, 0)
        self.assertEqual(stdout, b"\xff" * 65536)
        self.assertEqual(stderr, b"e" * 8192)

    def test_child_environment_and_working_directory_are_closed(self):
        with patch.dict(os.environ, {"PATH": str(self.directory),
                                     "LD_PRELOAD": "/nonexistent/openlogi-test.so",
                                     "LD_LIBRARY_PATH": str(self.directory),
                                     "XDG_RUNTIME_DIR": str(self.directory),
                                     "OPENLOGI_TEST_SECRET": "must not leak"}):
            code, stdout, stderr = self.collect(
                "import json, os\n"
                "print(json.dumps([dict(os.environ), os.getcwd()]))"
            )
        self.assertEqual(code, 0)
        self.assertEqual(stderr, b"")
        environment, cwd = json.loads(stdout)
        self.assertEqual(environment, {"PATH": "/usr/bin", "LC_ALL": "C",
                                       "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}"})
        self.assertEqual(cwd, "/")

    def test_one_byte_over_each_limit(self):
        for fd, size, failure in ((1, 65537, 120), (2, 8193, 121)):
            with self.subTest(fd=fd):
                self.collect(f"import os\nos.write({fd}, b'x' * {size})", failure)

    def test_continuous_newline_free_floods_are_killed_and_reaped(self):
        for fd, failure in ((1, 120), (2, 121)):
            with self.subTest(fd=fd):
                self.collect(
                    f"import os, signal\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                    f"while True: os.write({fd}, b'x' * 4096)", failure,
                )

    def test_simultaneous_stream_floods(self):
        result = self.cli(
            "import os, threading\n"
            "def flood(fd):\n"
            "    while True: os.write(fd, b'x' * 4096)\n"
            "threading.Thread(target=flood, args=(2,), daemon=True).start()\n"
            "flood(1)\n"
        )
        self.assertIn(result.returncode, (120, 121))
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, guard.ERRORS[result.returncode])

    def test_timeout_with_open_and_closed_streams(self):
        for close in (False, True):
            with self.subTest(close=close):
                body = "import os, time\n"
                if close:
                    body += "os.close(1)\nos.close(2)\n"
                started = time.monotonic()
                self.collect(body + "time.sleep(30)", 122, timeout=0.2)
                self.assertLess(time.monotonic() - started, 2)

    def test_default_five_second_deadline_discards_partial_output(self):
        started = time.monotonic()
        result = self.cli("import os, time\nos.write(1, b'partial')\ntime.sleep(30)")
        elapsed = time.monotonic() - started
        self.assertGreaterEqual(elapsed, 5)
        self.assertLess(elapsed, 7)
        self.assertEqual(result.returncode, 122)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, guard.ERRORS[122])

    def assert_terminated(self, pid):
        # Grandchildren are reaped by their adopter, not the helper. A zombie
        # has terminated and cannot keep writing; direct children are checked
        # with waitpid above.
        stat = Path(f"/proc/{pid}/stat")
        until = time.monotonic() + 2
        while time.monotonic() < until:
            try:
                if stat.read_text().rsplit(")", 1)[1].split()[0] == "Z":
                    return
            except FileNotFoundError:
                return
            time.sleep(0.01)
        self.fail(f"producer {pid} is still alive")

    def test_exited_leader_with_descendant_holding_pipes(self):
        pid_file = self.directory / "descendant"
        self.collect(
            "import os, pathlib, signal, time\n"
            "if os.fork(): os._exit(0)\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()))\n"
            "time.sleep(30)\n", 122, timeout=0.3,
        )
        self.assert_terminated(int(pid_file.read_text()))

    def cancel_helper(self, signum):
        pid_file = self.directory / "producer"
        self.executable(
            "import os, pathlib, signal, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()))\n"
            "time.sleep(30)\n"
        )
        with subprocess.Popen(
            [PYTHON, "-I", str(self.launcher)],
            env={**os.environ, "PATH": str(self.directory)},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ) as helper:
            try:
                until = time.monotonic() + 2
                while not pid_file.exists() and time.monotonic() < until:
                    time.sleep(0.01)
                self.assertTrue(pid_file.exists())
                helper.send_signal(signum)
                stdout, stderr = helper.communicate(timeout=2)
            finally:
                if helper.poll() is None:
                    helper.kill()
                    helper.wait()
            self.assertEqual(helper.returncode, -signal.SIGKILL if signum == signal.SIGKILL else 123)
            self.assertEqual(stdout, b"")
            self.assertEqual(stderr, guard.ERRORS[123])
        self.assertFalse(Path(f"/proc/{int(pid_file.read_text())}").exists())

    def test_helper_cancellation_kills_producer(self):
        self.cancel_helper(signal.SIGTERM)

    def test_helper_sigkill_still_reaps_producer(self):
        self.cancel_helper(signal.SIGKILL)

    def test_dead_owner_does_not_start_producer(self):
        with patch.object(guard.subprocess, "Popen") as popen:
            with self.assertRaises(guard.GuardFailure) as raised:
                guard.collect(["openlogi", "list"], owner_pid=os.getppid() + 1)
            self.assertEqual(raised.exception.code, 123)
            popen.assert_not_called()

    def test_exit_codes_cannot_impersonate_guard_failures(self):
        for code in (0, 2, 1, 120, 121, 122, 123, 126, 127):
            with self.subTest(code=code):
                result = self.cli(
                    "import os, sys\nassert sys.argv == [sys.argv[0], 'list']\n"
                    f"os.write(1, b'output')\nos.write(2, b'diagnostic')\nsys.exit({code})"
                )
                self.assertEqual(result.returncode, code if code in (0, 2) else 1)
                self.assertEqual(result.stdout, b"output")
                self.assertEqual(result.stderr, b"diagnostic")

    def test_missing_executable_and_launch_error(self):
        result = self.cli()
        self.assertEqual(result.returncode, 127)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, guard.ERRORS[127])
        self.executable("pass")
        (self.directory / "openlogi").chmod(0o600)
        result = self.cli()
        self.assertEqual(result.returncode, 123)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, guard.ERRORS[123])


class TrustedExecutableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="openlogi-shadow-")
        self.addCleanup(self.temp.cleanup)
        self.metadata = {
            path: SimpleNamespace(st_uid=0, st_mode=stat.S_IFDIR | 0o755)
            for path in ("/", "/usr", "/usr/bin")
        }
        self.metadata["/usr/bin/openlogi"] = SimpleNamespace(
            st_uid=0, st_mode=stat.S_IFREG | 0o755
        )
        self.stdout = io.BytesIO()
        self.stderr = io.BytesIO()
        for target, replacement in (
            ("stdout", SimpleNamespace(buffer=self.stdout)),
            ("stderr", SimpleNamespace(buffer=self.stderr)),
        ):
            patcher = patch.object(guard.sys, target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(guard.os, "lstat", side_effect=self.metadata.__getitem__)
        self.lstat = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(guard.os, "access", return_value=True)
        self.access = patcher.start()
        self.addCleanup(patcher.stop)

    def assert_rejected(self, code=126):
        with patch.object(guard, "collect") as collect:
            self.assertEqual(guard.main(), code)
            collect.assert_not_called()
        self.assertEqual(self.stdout.getvalue(), b"")
        self.assertEqual(self.stderr.getvalue(), guard.ERRORS[code])
        self.stderr.seek(0)
        self.stderr.truncate()

    def test_valid_system_path_ignores_shadow_executable(self):
        shadow = Path(self.temp.name) / "openlogi"
        shadow.write_text("#!/bin/sh\necho shadow\n")
        shadow.chmod(0o755)
        with patch.dict(os.environ, {"PATH": self.temp.name}), \
                patch.object(guard, "collect", return_value=(0, b"trusted", b"")) as collect:
            self.assertEqual(guard.main(), 0)
            collect.assert_called_once_with(["/usr/bin/openlogi", "list"], None)
        self.assertEqual(self.stdout.getvalue(), b"trusted")
        self.assertEqual([call.args[0] for call in self.lstat.call_args_list],
                         ["/", "/usr", "/usr/bin", "/usr/bin/openlogi"])
        self.access.assert_called_once_with("/usr/bin/openlogi", os.X_OK)

    def test_untrusted_owner_or_writable_path_never_launches(self):
        for path, info in self.metadata.items():
            for uid, bits in ((1000, 0), (0, 0o020), (0, 0o002)):
                with self.subTest(path=path, uid=uid, bits=bits):
                    original_uid, original_mode = info.st_uid, info.st_mode
                    info.st_uid, info.st_mode = uid, original_mode | bits
                    self.assert_rejected()
                    info.st_uid, info.st_mode = original_uid, original_mode

    def test_symlinks_and_wrong_file_types_never_launch(self):
        for path, info in self.metadata.items():
            wrong_type = stat.S_IFDIR if path.endswith("openlogi") else stat.S_IFREG
            for kind in (stat.S_IFLNK, stat.S_IFIFO, wrong_type):
                with self.subTest(path=path, kind=kind):
                    original = info.st_mode
                    info.st_mode = kind | 0o755
                    self.assert_rejected()
                    info.st_mode = original

    def test_non_executable_file_never_launches(self):
        self.access.return_value = False
        self.assert_rejected()

    def test_missing_or_inaccessible_path_never_launches(self):
        for error, code in ((FileNotFoundError(), 127), (PermissionError(), 126)):
            with self.subTest(code=code):
                self.lstat.side_effect = error
                self.assert_rejected(code)


if __name__ == "__main__":
    unittest.main()

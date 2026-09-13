"""Exercise the guard with real, synthetic producers; no hardware required."""

import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch


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
            [PYTHON, "-I", str(HELPER)],
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

    def test_helper_cancellation_kills_producer(self):
        pid_file = self.directory / "producer"
        self.executable(
            "import os, pathlib, signal, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()))\n"
            "time.sleep(30)\n"
        )
        with subprocess.Popen(
            [PYTHON, "-I", str(HELPER)],
            env={**os.environ, "PATH": str(self.directory)},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ) as helper:
            try:
                until = time.monotonic() + 2
                while not pid_file.exists() and time.monotonic() < until:
                    time.sleep(0.01)
                self.assertTrue(pid_file.exists())
                helper.send_signal(signal.SIGTERM)
                stdout, stderr = helper.communicate(timeout=2)
            finally:
                if helper.poll() is None:
                    helper.kill()
                    helper.wait()
            self.assertEqual(helper.returncode, 123)
            self.assertEqual(stdout, b"")
            self.assertEqual(stderr, guard.ERRORS[123])
        self.assertFalse(Path(f"/proc/{int(pid_file.read_text())}").exists())

    def test_exit_codes_cannot_impersonate_guard_failures(self):
        for code in (0, 2, 1, 120, 121, 122, 123, 127):
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


if __name__ == "__main__":
    unittest.main()

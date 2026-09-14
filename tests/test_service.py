"""Headless Quickshell smoke tests of the real service and bundled helper."""

import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest


REPO = Path(__file__).resolve().parents[1]


class ServiceTests(unittest.TestCase):
    def smoke(self, failed_start=False):
        with tempfile.TemporaryDirectory(prefix="openlogi-service-") as directory:
            root = Path(directory)
            # Exercise local URL decoding and argv handling as well.
            plugin = root / "plugin space # %"
            plugin.mkdir()
            for name in ("Service.qml", "Model.js", "openlogi-bounded.py"):
                shutil.copyfile(REPO / name, plugin / name)
            if failed_start:
                service = plugin / "Service.qml"
                service.write_text(service.read_text().replace(
                    '"/usr/bin/python3"', '"/nonexistent/openlogi-test-python"'
                ))

            executable = root / "openlogi"
            executable.write_text(
                "#!/usr/bin/python3\n"
                "import os, pathlib, time\n"
                "counter = pathlib.Path(__file__).with_suffix('.count')\n"
                "number = int(counter.read_text()) if counter.exists() else 0\n"
                "counter.write_text(str(number + 1))\n"
                "time.sleep(0.05)\n"
                "if number == 1:\n"
                "    os.write(1, b'x' * 65537)\n"
                "else:\n"
                "    print('  └─ slot 1 ● Smoke Mouse (mouse, wpid=0000, battery=50% good)')\n"
            )
            executable.chmod(0o700)
            shell = plugin / "shell.qml"
            shell.write_text("""
import QtQuick
import Quickshell

Item {
  id: root
  property int stage: 0
  property bool failedStart: FAILED_START

  function check(condition, message) {
    if (!condition) {
      console.error("SMOKE FAIL: " + message)
      Qt.exit(1)
    }
    return condition
  }

  Service {
    id: service
    onRefreshingChanged: {
      if (refreshing || status === "loading") return
      if (root.failedStart) {
        if (!root.check(failed && lastError.indexOf("could not start") !== -1,
                        "startup failure did not finish refresh")) return
        console.log("SMOKE PASS")
        Qt.quit()
        return
      }
      if (root.stage === 1) {
        if (!root.check(failed && devices.length === 0 && lowestDevice === null
                        && lastError.indexOf("stdout limit") !== -1,
                        "overflow did not clear readings")) return
      } else {
        if (!root.check(status === "ready" && devices.length === 1
                        && lowestDevice.percentage === 50 && lastError === "",
                        "initial reading or recovery failed")) return
      }
      root.stage++
      if (root.stage === 1) {
        Qt.callLater(function() {
          service.refresh()
          service.refresh()
          service.refresh()
        })
      } else if (root.stage === 3) {
        if (!root.check(!refreshPending, "refresh requests did not coalesce")) return
        console.log("SMOKE PASS")
        Qt.quit()
      }
    }
  }

  Timer {
    running: true
    interval: 8000
    onTriggered: root.check(false, "service stuck refreshing")
  }
}
""".replace("FAILED_START", "true" if failed_start else "false"))
            runtime = root / "runtime"
            runtime.mkdir(mode=0o700)
            env = {**os.environ, "PATH": str(root) + ":" + os.environ["PATH"],
                   "XDG_RUNTIME_DIR": str(runtime), "QT_QPA_PLATFORM": "offscreen",
                   "QT_QPA_PLATFORMTHEME": "", "QT_QUICK_BACKEND": "software"}
            env.pop("DISPLAY", None)
            env.pop("WAYLAND_DISPLAY", None)
            try:
                result = subprocess.run(
                    ["qs", "--no-color", "-p", str(shell)], env=env,
                    capture_output=True, text=True, timeout=10,
                )
            except subprocess.TimeoutExpired as error:
                self.fail(f"Quickshell timed out: {error.stdout!r} {error.stderr!r}")
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, output)
            self.assertIn("SMOKE PASS", output)
            self.assertNotIn("SMOKE FAIL", output)
            if not failed_start:
                self.assertEqual((root / "openlogi.count").read_text(), "3")

    def test_refresh_overflow_recovery_and_coalescing(self):
        self.smoke()

    def test_failed_start_finishes_refresh(self):
        self.smoke(failed_start=True)

    def test_service_destruction_cleans_up_producer_group(self):
        with tempfile.TemporaryDirectory(prefix="openlogi-unload-") as directory:
            root = Path(directory)
            for name in ("Service.qml", "Model.js", "openlogi-bounded.py"):
                shutil.copyfile(REPO / name, root / name)
            pids_file = root / "producer.pids"
            executable = root / "openlogi"
            executable.write_text(
                "#!/usr/bin/python3\n"
                "import os, pathlib, signal, time\n"
                "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                "child = os.fork()\n"
                "if child == 0:\n"
                "    time.sleep(30)\n"
                "    os._exit(0)\n"
                f"pathlib.Path({str(pids_file)!r}).write_text(f'{{os.getpid()}} {{child}} {{os.getppid()}}')\n"
                "time.sleep(30)\n"
            )
            executable.chmod(0o700)
            shell = root / "shell.qml"
            shell.write_text('''import QtQuick
import Quickshell.Io

Item {
  Loader { id: loader; source: "Service.qml" }
  Timer {
    id: readiness
    running: true
    repeat: true
    interval: 50
    onTriggered: if (!checkReady.running) checkReady.running = true
  }
  Process {
    id: checkReady
    command: ["/usr/bin/test", "-s", "PID_FILE"]
    onExited: function(code) {
      if (code !== 0) return
      readiness.stop()
      loader.active = false
      console.log("SERVICE UNLOADED")
      Qt.callLater(Qt.quit)
    }
  }
  Timer { running: true; interval: 8000; onTriggered: Qt.exit(1) }
}
'''.replace("PID_FILE", str(pids_file)))
            runtime = root / "runtime"
            runtime.mkdir(mode=0o700)
            env = {**os.environ, "PATH": str(root) + ":" + os.environ["PATH"],
                   "XDG_RUNTIME_DIR": str(runtime), "QT_QPA_PLATFORM": "offscreen",
                   "QT_QPA_PLATFORMTHEME": "", "QT_QUICK_BACKEND": "software"}
            env.pop("DISPLAY", None)
            env.pop("WAYLAND_DISPLAY", None)
            try:
                result = subprocess.run(
                    ["qs", "--no-color", "-p", str(shell)], env=env,
                    capture_output=True, text=True, timeout=10,
                )
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 0, output)
                self.assertIn("SERVICE UNLOADED", output)
                producer, descendant, worker = map(int, pids_file.read_text().split())
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    states = []
                    for pid in (producer, descendant, worker):
                        try:
                            stat = Path(f"/proc/{pid}/stat").read_text()
                            states.append(stat.rsplit(")", 1)[1].split()[0])
                        except FileNotFoundError:
                            states.append("gone")
                    if states[0] == "gone" and all(state in ("gone", "Z") for state in states):
                        break
                    time.sleep(0.01)
                self.assertEqual(states[0], "gone", "producer was not reaped")
                self.assertTrue(all(state in ("gone", "Z") for state in states), states)
            finally:
                # Also clean up when running this regression against the old helper.
                if pids_file.exists():
                    producer = int(pids_file.read_text().split()[0])
                    try:
                        os.killpg(producer, signal.SIGKILL)
                    except ProcessLookupError:
                        pass


if __name__ == "__main__":
    unittest.main()

import QtQuick
import Quickshell.Io
import "Model.js" as Model

Item {
  id: root

  visible: false

  readonly property int refreshIntervalMs: 5 * 60 * 1000
  readonly property int commandTimeoutMs: 15 * 1000

  property var devices: []
  property var lowestDevice: null
  property string status: "loading"
  property string lastError: ""
  property bool refreshing: false
  property bool refreshPending: false
  property bool timedOut: false

  readonly property bool hasReadableBattery: lowestDevice !== null
  readonly property bool failed: status === "error"

  function conciseError(value, fallback) {
    var message = String(value || "").replace(/\s+/g, " ").trim()
    if (message === "") message = fallback
    return message.length > 180 ? message.substring(0, 177) + "…" : message
  }

  function fail(message) {
    devices = []
    lowestDevice = null
    status = "error"
    lastError = conciseError(message, "The plugin cannot read OpenLogi devices")
  }

  function applyOutput(output) {
    var parsed = Model.parseList(output)
    if (!parsed.ok) {
      fail(parsed.error)
      return
    }

    var connected = Model.onlineDevices(parsed.devices)
    devices = connected
    lowestDevice = Model.lowestBatteryDevice(connected)
    status = lowestDevice ? "ready" : "empty"
    lastError = ""
  }

  function refresh() {
    if (listProcess.running) {
      refreshPending = true
      return
    }

    stdoutText = ""
    stderrText = ""
    timedOut = false
    refreshing = true
    listProcess.running = true
    commandTimeout.restart()
  }

  property string stdoutText: ""
  property string stderrText: ""

  Timer {
    interval: root.refreshIntervalMs
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  Timer {
    id: commandTimeout
    interval: root.commandTimeoutMs
    repeat: false
    onTriggered: {
      if (!listProcess.running) return
      root.timedOut = true
      listProcess.running = false
    }
  }

  Process {
    id: listProcess
    running: false
    command: [
      "sh",
      "-c",
      "command -v openlogi >/dev/null 2>&1 || { echo 'openlogi command not found' >&2; exit 127; }; exec openlogi list"
    ]

    stdout: StdioCollector {
      id: stdoutCollector
      waitForEnd: true
      onStreamFinished: root.stdoutText = text
    }

    stderr: StdioCollector {
      id: stderrCollector
      waitForEnd: true
      onStreamFinished: root.stderrText = text
    }

    onExited: function(exitCode) {
      commandTimeout.stop()
      root.refreshing = false

      var stdout = String(stdoutCollector.text || root.stdoutText || "")
      var stderr = String(stderrCollector.text || root.stderrText || "")
      var result = Model.commandResult(exitCode, stdout, stderr, root.timedOut)
      if (result.ok) root.applyOutput(result.output)
      else root.fail(result.error)

      root.timedOut = false
      if (root.refreshPending) {
        root.refreshPending = false
        Qt.callLater(root.refresh)
      }
    }
  }
}

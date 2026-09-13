import QtQuick
import Quickshell.Io
import "Model.js" as Model

Item {
  id: root

  visible: false

  readonly property int refreshIntervalMs: 5 * 60 * 1000

  property var devices: []
  property var lowestDevice: null
  property string status: "loading"
  property string lastError: ""
  property bool refreshing: false
  property bool refreshPending: false

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
    if (refreshing) {
      refreshPending = true
      return
    }

    stdoutText = ""
    stderrText = ""
    refreshing = true
    listProcess.running = true
  }

  function finishRefresh() {
    refreshing = false
    if (refreshPending) {
      refreshPending = false
      Qt.callLater(root.refresh)
    }
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

  Process {
    id: listProcess
    running: false
    command: [
      "/usr/bin/python3", "-I",
      decodeURIComponent(Qt.resolvedUrl("openlogi-bounded.py").toString().substring(7))
    ]

    // Only the bundled helper reaches these collectors. It independently caps
    // both streams before forwarding anything and owns the producer deadline.
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
      var result = Model.commandResult(exitCode, root.stdoutText, root.stderrText)
      if (result.ok) root.applyOutput(result.output)
      else root.fail(result.error)
      root.finishRefresh()
    }

    onRunningChanged: {
      // FailedToStart emits runningChanged without exited. Normal exits finish
      // the refresh first, so this also avoids reusing a previous poll's output.
      if (!running && root.refreshing) {
        root.fail("OpenLogi helper could not start; check /usr/bin/python3")
        root.finishRefresh()
      }
    }
  }
}

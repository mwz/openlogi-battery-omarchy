import QtQuick
import QtTest
import "../Model.js" as Model

TestCase {
  name: "OpenLogiModel"

  // Device names and serials are synthetic. Known receiver product IDs are
  // used only where connection classification depends on them.
  readonly property string multipleDevicesOutput: [
    "(inventory read from the running agent)",
    "Logitech Wireless Mouse MX Master (—, vid=0000 pid=0001)",
    "  └─ slot 255 ● Wireless Mouse MX Master (mouse, wpid=?, battery=90% full (discharging))",
    "          model_ids=[0001,0002,0000] ext=00 serial=— unit_id=deadbeef transports=equad+btle",
    "",
    "Logi Bolt Receiver (DEADBEEFDEADBEEF, vid=0000 pid=0002)",
    "  └─ slot 1 ● MX Master 3S  (mouse, wpid=0003, battery=80% full (discharging))",
    "          model_ids=[0003,0000,0000] ext=04 serial=TESTSERIAL01 unit_id=cafebabe transports=btle"
  ].join("\n")

  function deviceLine(name, kind, battery, marker) {
    return "  └─ slot 1 " + (marker || "●") + " " + name
      + " (" + kind + ", wpid=0000, battery=" + battery + ")"
  }

  function test_parsesMultipleReceiversAndSortsNames() {
    var parsed = Model.parseList(multipleDevicesOutput)
    verify(parsed.ok)
    compare(parsed.devices.length, 2)

    var connected = Model.onlineDevices(parsed.devices)
    compare(connected.length, 2)
    compare(connected[0].name, "MX Master 3S")
    compare(connected[1].name, "Wireless Mouse MX Master")
    compare(connected[0].connectionKind, "bolt")
    compare(connected[0].connectionLabel, "Logi Bolt receiver")
    compare(connected[1].connectionKind, "bluetooth")
    compare(connected[1].connectionLabel, "Bluetooth (direct)")

    var lowest = Model.lowestBatteryDevice(connected)
    compare(lowest.name, "MX Master 3S")
    compare(lowest.percentage, 80)
    compare(Model.deviceIcon(lowest.kind), "󰍽")
  }

  function test_iconMappings() {
    compare(Model.deviceIcon("mouse"), "󰍽")
    compare(Model.deviceIcon("trackball"), "󰍽")
    compare(Model.deviceIcon("keyboard"), "󰌌")
    compare(Model.deviceIcon("numpad"), "󰌌")
    compare(Model.deviceIcon("touchpad"), "󰟸")
    compare(Model.deviceIcon("headset"), "󰋎")
    compare(Model.deviceIcon("gamepad"), "󰊖")
    compare(Model.deviceIcon("joystick"), "󰊖")
    compare(Model.deviceIcon("tablet"), "󰁹")
    compare(Model.deviceIcon("future-device"), "󰁹")
  }

  function test_connectionIconMappings() {
    compare(Model.connectionIcon("bolt"), "󱐋")
    compare(Model.connectionIcon("bluetooth"), "󰂯")
    compare(Model.connectionIcon("usb"), "󰕓")
    compare(Model.connectionIcon("unifying"), "󰖩")
    compare(Model.connectionIcon("lightspeed"), "󰖩")
    compare(Model.connectionIcon("receiver"), "󰖩")
    compare(Model.connectionIcon("future-transport"), "?")
  }

  function test_receiverConnectionKindsComeFromInventoryParent() {
    var output = [
      "Logi Bolt Receiver (DEADBEEFDEADBEEF, vid=0000 pid=0010)",
      deviceLine("Bolt Mouse", "mouse", "80% full (discharging)"),
      "",
      "Unifying Receiver (DEADBEEFDEADBEEF, vid=0000 pid=0011)",
      deviceLine("Unifying Mouse", "mouse", "70% full (discharging)"),
      "",
      "Lightspeed Receiver (DEADBEEFDEADBEEF, vid=0000 pid=0012)",
      deviceLine("Lightspeed Mouse", "mouse", "60% full (discharging)"),
      "",
      "Future Receiver (DEADBEEFDEADBEEF, vid=0000 pid=0013)",
      deviceLine("Generic Mouse", "mouse", "50% full (discharging)")
    ].join("\n")

    var connected = Model.onlineDevices(Model.parseList(output).devices)
    compare(connected[0].connectionKind, "bolt")
    compare(connected[1].connectionKind, "receiver")
    compare(connected[2].connectionKind, "lightspeed")
    compare(connected[3].connectionKind, "unifying")
  }

  function test_receiverConnectionKindsFallBackToProductId() {
    var output = [
      "Unknown Receiver (DEADBEEFDEADBEEF, vid=0000 pid=c548)",
      deviceLine("Bolt by PID", "mouse", "80% full (discharging)"),
      "",
      "Unknown Receiver (DEADBEEFDEADBEEF, vid=0000 pid=c547)",
      deviceLine("Lightspeed by PID", "mouse", "70% full (discharging)"),
      "",
      "Unknown Receiver (DEADBEEFDEADBEEF, vid=0000 pid=c539)",
      deviceLine("Unifying by PID", "mouse", "60% full (discharging)")
    ].join("\n")

    var connected = Model.onlineDevices(Model.parseList(output).devices)
    compare(connected[0].connectionKind, "bolt")
    compare(connected[1].connectionKind, "lightspeed")
    compare(connected[2].connectionKind, "unifying")
  }

  function test_directWiredConnectionUsesCurrentModelPid() {
    var output = [
      "Wired Test Mouse (—, vid=0000 pid=0020)",
      "  └─ slot 255 ● Wired Test Mouse (mouse, wpid=?, battery=100% full (charging))",
      "          model_ids=[0020,0000,0000] ext=00 serial=— unit_id=deadbeef transports=usb"
    ].join("\n")
    var device = Model.parseList(output).devices[0]
    compare(device.connectionKind, "usb")
    compare(device.connectionLabel, "Wired USB")
  }

  function test_directMultiTransportUsesMatchingModelId() {
    var output = [
      "Wired Test Mouse (—, vid=0000 pid=00a2)",
      "  └─ slot 255 ● Wired Test Mouse (mouse, wpid=?, battery=100% full (charging))",
      "          model_ids=[00a1,00a2,0000] ext=00 serial=— unit_id=deadbeef transports=usb+equad"
    ].join("\n")
    compare(Model.parseList(output).devices[0].connectionKind, "usb")
  }

  function test_directClassicBluetoothConnection() {
    var output = [
      "Bluetooth Test Mouse (—, vid=0000 pid=0021)",
      "  └─ slot 255 ● Bluetooth Test Mouse (mouse, wpid=?, battery=65% good (discharging))",
      "          model_ids=[0021,0000,0000] ext=00 serial=— unit_id=deadbeef transports=bt"
    ].join("\n")
    compare(Model.parseList(output).devices[0].connectionKind, "bluetooth")
  }

  function test_unknownDirectConnectionDoesNotGuessFromCapabilities() {
    var output = [
      "Direct Test Mouse (—, vid=0000 pid=0022)",
      "  └─ slot 255 ● Direct Test Mouse (mouse, wpid=?, battery=65% good (discharging))",
      "          model_ids=[0023,0000,0000] ext=00 serial=— unit_id=deadbeef transports=btle"
    ].join("\n")
    var device = Model.parseList(output).devices[0]
    compare(device.connectionKind, "direct")
    compare(device.connectionLabel, "Connection unknown")
  }

  function test_keyboardKindIsParsedExactly() {
    var parsed = Model.parseList(deviceLine("MX Keys", "keyboard", "72% good (discharging)"))
    verify(parsed.ok)
    compare(parsed.devices[0].kind, "keyboard")
    compare(Model.deviceIcon(parsed.devices[0].kind), "󰌌")
  }

  function test_offlineDevicesAreExcluded() {
    var output = [
      deviceLine("Sleeping Mouse", "mouse", "60% good (discharging)", "○"),
      deviceLine("Awake Keyboard", "keyboard", "70% good (discharging)", "●")
    ].join("\n")
    var connected = Model.onlineDevices(Model.parseList(output).devices)
    compare(connected.length, 1)
    compare(connected[0].name, "Awake Keyboard")
  }

  function test_unavailableBatteryStaysInConnectedListButNotMinimum() {
    var output = [
      deviceLine("No Battery", "mouse", "—"),
      deviceLine("Known Battery", "mouse", "40% low (discharging)")
    ].join("\n")
    var connected = Model.onlineDevices(Model.parseList(output).devices)
    compare(connected.length, 2)
    verify(!connected[1].batteryAvailable)
    compare(Model.lowestBatteryDevice(connected).name, "Known Battery")
  }

  function test_equalPercentagesUseAlphabeticalName() {
    var output = [
      deviceLine("Zulu Mouse", "mouse", "50% good (discharging)"),
      deviceLine("Alpha Keyboard", "keyboard", "50% good (discharging)")
    ].join("\n")
    var connected = Model.onlineDevices(Model.parseList(output).devices)
    compare(Model.lowestBatteryDevice(connected).name, "Alpha Keyboard")
  }

  function test_noHardwareOutput() {
    var parsed = Model.parseList("No Logitech HID++ devices or webcams found.\n\nNotes:\n - Nothing connected")
    verify(parsed.ok)
    verify(parsed.noHardware)
    compare(parsed.devices.length, 0)
  }

  function test_currentNoAgentNoHardwareOutput() {
    var output = [
      "(no agent reachable — reading hardware directly; macOS judges this process's Input Monitoring grant, not the agent's)",
      "No Logitech HID++ devices or webcams found.",
      "",
      "Notes:",
      "  - Nothing connected"
    ].join("\n")
    var parsed = Model.parseList(output)
    verify(parsed.ok)
    verify(parsed.noHardware)
    compare(parsed.devices.length, 0)
  }

  function test_commandResultAcceptsSuccessfulOutput() {
    var result = Model.commandResult(0, deviceLine("Mouse", "mouse", "50% good"), "", false)
    verify(result.ok)
    verify(result.output.indexOf("Mouse") !== -1)
    compare(result.error, "")
  }

  function test_commandResultAcceptsExpectedNoHardwareExit() {
    var output = "No Logitech HID++ devices or webcams found."
    var result = Model.commandResult(2, output, "diagnostic note", false)
    verify(result.ok)
    compare(result.output, output)
  }

  function test_commandResultReportsMissingCommand() {
    var result = Model.commandResult(127, "", "openlogi command not found", false)
    verify(!result.ok)
    compare(result.error, "openlogi command not found")
  }

  function test_commandResultReportsOrdinaryFailure() {
    var result = Model.commandResult(1, "partial output", "openlogi failed", false)
    verify(!result.ok)
    compare(result.error, "openlogi failed")
  }

  function test_commandResultReportsTimeoutFirst() {
    var result = Model.commandResult(0, deviceLine("Mouse", "mouse", "50% good"), "", true)
    verify(!result.ok)
    compare(result.error, "openlogi list timed out")
  }

  function test_cameraOnlyOutputHasNoBatteryDevices() {
    var parsed = Model.parseList("Cameras (1 Logitech UVC)\n └─ ● Brio (camera, vid=0000 pid=0004, id=1)")
    verify(parsed.ok)
    verify(!parsed.noHardware)
    compare(parsed.devices.length, 0)
  }

  function test_malformedDeviceRowFailsClosed() {
    var parsed = Model.parseList("  └─ slot 1 ● Changed output format")
    verify(!parsed.ok)
    compare(parsed.error, "OpenLogi returned device data that this plugin cannot read")
  }

  function test_outOfRangePercentageFailsClosed() {
    var parsed = Model.parseList(deviceLine("Impossible Mouse", "mouse", "101% full (charging)"))
    verify(!parsed.ok)
  }
}

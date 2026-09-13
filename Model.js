.pragma library

var ICON_BATTERY = "󰁹"
var ICON_MOUSE = "󰍽"
var ICON_KEYBOARD = "󰌌"
var ICON_TOUCHPAD = "󰟸"
var ICON_HEADSET = "󰋎"
var ICON_GAMEPAD = "󰊖"
var ICON_BOLT = "󱐋"
var ICON_BLUETOOTH = "󰂯"
var ICON_USB = "󰕓"
var ICON_WIRELESS = "󰖩"

// The helper enforces byte limits before QML. These bound parsing and retained
// UI data in UTF-16 code units, even when parseList is called independently.
var MAX_OUTPUT_LENGTH = 65536
var MAX_LINES = 1024
var MAX_LINE_LENGTH = 2048
var MAX_DEVICES = 24
var MAX_NAME_LENGTH = 256
var MAX_FIELD_LENGTH = 64
var MAX_BATTERY_LENGTH = 256

function invalidList(error) {
  return {
    ok: false, noHardware: false, devices: [],
    error: error || "OpenLogi returned device data that this plugin cannot read"
  }
}

function boundedLines(text) {
  if (text.length > MAX_OUTPUT_LENGTH) return null
  var lines = []
  var start = 0
  while (start <= text.length) {
    if (lines.length >= MAX_LINES) return null
    var end = text.indexOf("\n", start)
    if (end === -1) end = text.length
    var contentEnd = end
    if (end < text.length && end > start && text.charAt(end - 1) === "\r") contentEnd--
    if (contentEnd - start > MAX_LINE_LENGTH) return null
    lines.push(text.substring(start, contentEnd))
    if (end === text.length) break
    start = end + 1
  }
  return lines
}

function deviceIcon(kind) {
  switch (String(kind || "").trim().toLowerCase()) {
  case "mouse":
  case "trackball":
    return ICON_MOUSE
  case "keyboard":
  case "numpad":
    return ICON_KEYBOARD
  case "touchpad":
    return ICON_TOUCHPAD
  case "headset":
    return ICON_HEADSET
  case "gamepad":
  case "joystick":
    return ICON_GAMEPAD
  default:
    return ICON_BATTERY
  }
}

function connectionIcon(kind) {
  switch (String(kind || "").trim().toLowerCase()) {
  case "bolt":
    return ICON_BOLT
  case "bluetooth":
    return ICON_BLUETOOTH
  case "usb":
    return ICON_USB
  case "unifying":
  case "lightspeed":
  case "receiver":
    return ICON_WIRELESS
  default:
    return "?"
  }
}

function connectionLabel(kind) {
  switch (String(kind || "").trim().toLowerCase()) {
  case "bolt":
    return "Logi Bolt receiver"
  case "unifying":
    return "Logitech Unifying receiver"
  case "lightspeed":
    return "Logitech Lightspeed receiver"
  case "bluetooth":
    return "Bluetooth (direct)"
  case "usb":
    return "Wired USB"
  case "receiver":
    return "Logitech receiver"
  default:
    return "Connection unknown"
  }
}

function compareDevices(a, b) {
  var aName = String(a && a.name || "").trim()
  var bName = String(b && b.name || "").trim()
  var folded = aName.toLocaleLowerCase().localeCompare(bName.toLocaleLowerCase())
  if (folded !== 0) return folded
  var exact = aName.localeCompare(bName)
  if (exact !== 0) return exact
  return Number(a && a.order || 0) - Number(b && b.order || 0)
}

function sortedDevices(devices) {
  var result = (devices || []).slice()
  result.sort(compareDevices)
  return result
}

function onlineDevices(devices) {
  var result = []
  var source = devices || []
  for (var i = 0; i < source.length; i++) {
    if (source[i] && source[i].online === true) result.push(source[i])
  }
  return sortedDevices(result)
}

function lowestBatteryDevice(devices) {
  var result = null
  var source = devices || []
  for (var i = 0; i < source.length; i++) {
    var device = source[i]
    if (!device || device.online !== true || device.batteryAvailable !== true) continue
    if (result === null
        || device.percentage < result.percentage
        || (device.percentage === result.percentage && compareDevices(device, result) < 0)) {
      result = device
    }
  }
  return result
}

function parseDeviceLine(line, order) {
  var text = String(line || "")
  if (text.length > MAX_LINE_LENGTH) return { malformed: true }
  var row = text.match(/^\s*[├└]─\s+slot\s+(\d{1,3})\s+([●○])\s+(.+)$/)
  if (!row) return /^\s*[├└]─\s+slot\b/.test(text) ? { malformed: true } : null
  if (Number(row[1]) > 255) return { malformed: true }

  var detail = row[3].match(/^(.*?)\s+\(([^,()]+),\s*wpid=([^,]*),\s*battery=(.*)\)\s*$/)
  if (!detail) return { malformed: true }

  var name = detail[1].trim()
  var kind = detail[2].trim().toLowerCase()
  if (name.length > MAX_NAME_LENGTH || kind.length > MAX_FIELD_LENGTH
      || detail[3].length > MAX_FIELD_LENGTH || detail[4].length > MAX_BATTERY_LENGTH) {
    return { malformed: true }
  }

  var batteryText = String(detail[4] || "").trim()
  var percentageMatch = batteryText.match(/^(\d{1,3})%(?:\s|$)/)
  var percentage = percentageMatch ? Number(percentageMatch[1]) : -1
  if (percentage > 100) return { malformed: true }

  return {
    slot: Number(row[1]),
    online: row[2] === "●",
    name: name,
    kind: kind,
    batteryAvailable: percentage >= 0,
    percentage: percentage,
    order: Number(order || 0)
  }
}

function parseInventoryHeader(line) {
  var text = String(line || "")
  if (text.length > MAX_LINE_LENGTH) return { malformed: true }
  var header = text.match(/^(.+?)\s+\([^,]*,\s*vid=([0-9a-f]{4})\s+pid=([0-9a-f]{4})\)\s*$/i)
  if (!header) return null
  var name = header[1].trim()
  if (name.length > MAX_NAME_LENGTH) return { malformed: true }
  return {
    name: name,
    productId: parseInt(header[3], 16)
  }
}

function connectionFromParent(parent, slot) {
  if (!parent) return slot === 255 ? "direct" : "receiver"

  var name = String(parent.name || "").toLowerCase()
  if (name.indexOf("bolt receiver") !== -1 || parent.productId === 0xc548) return "bolt"
  if (name.indexOf("lightspeed receiver") !== -1
      || parent.productId === 0xc53f
      || parent.productId === 0xc547) {
    return "lightspeed"
  }
  if (name.indexOf("unifying receiver") !== -1
      || parent.productId === 0xc52b
      || parent.productId === 0xc532
      || parent.productId === 0xc539) {
    return "unifying"
  }
  return slot === 255 ? "direct" : "receiver"
}

function parseModelLine(line) {
  var text = String(line || "")
  if (text.length > MAX_LINE_LENGTH) return null
  var model = text.match(/\bmodel_ids=\[([0-9a-f,\s]+)\].*\btransports=([^\s]+)\s*$/i)
  if (!model) return null

  var modelIds = model[1].split(",").map(function(value) {
    return parseInt(String(value || "").trim(), 16)
  })
  var transports = String(model[2] || "").toLowerCase().split("+")
  return { modelIds: modelIds, transports: transports }
}

function directConnectionFromModel(parentProductId, model) {
  if (!model || !Number.isFinite(parentProductId)) return "direct"

  // HID++ packs model IDs in transport-bit order, not in the printed field
  // order: classic Bluetooth, BTLE, eQuad, then USB.
  var transportOrder = ["bt", "btle", "equad", "usb"]
  var enabled = []
  for (var i = 0; i < transportOrder.length; i++) {
    if (model.transports.indexOf(transportOrder[i]) !== -1) enabled.push(transportOrder[i])
  }

  for (var j = 0; j < enabled.length && j < model.modelIds.length; j++) {
    if (model.modelIds[j] !== parentProductId) continue
    if (enabled[j] === "bt" || enabled[j] === "btle") return "bluetooth"
    if (enabled[j] === "usb") return "usb"
    return "direct"
  }
  return "direct"
}

function commandResult(exitCode, stdout, stderr) {
  var code = Number(exitCode)
  var failures = {
    120: "openlogi list exceeded the stdout limit",
    121: "openlogi list exceeded the stderr limit",
    122: "openlogi list timed out",
    123: "OpenLogi helper failed or was cancelled",
    127: "openlogi command not found"
  }
  if (failures[code]) return { ok: false, output: "", error: failures[code] }

  var stdoutText = String(stdout || "")
  var stderrText = String(stderr || "")
  if (code === 0 || code === 2) {
    var parsed = parseList(stdoutText)
    if (!parsed.ok) return { ok: false, output: "", error: parsed.error }
    if (code === 0 || parsed.noHardware) {
      return { ok: true, output: stdoutText, error: "" }
    }
  }

  var detail = stderrText || stdoutText || "openlogi list failed with exit code " + exitCode
  return { ok: false, output: "", error: detail.substring(0, 180) }
}

function parseList(output) {
  var text = String(output || "")
  var lines = boundedLines(text)
  if (!lines) return invalidList("OpenLogi output exceeded the parser limits")
  var devices = []
  var order = 0
  var currentParent = null
  var lastDevice = null

  for (var i = 0; i < lines.length; i++) {
    var header = parseInventoryHeader(lines[i])
    if (header) {
      if (header.malformed) return invalidList()
      currentParent = header
      lastDevice = null
      continue
    }

    var parsed = parseDeviceLine(lines[i], order)
    if (parsed) {
      order += 1
      if (parsed.malformed) return invalidList()
      if (devices.length >= MAX_DEVICES) return invalidList("OpenLogi returned more than 24 devices")
      parsed.connectionKind = connectionFromParent(currentParent, parsed.slot)
      parsed.connectionLabel = connectionLabel(parsed.connectionKind)
      devices.push(parsed)
      lastDevice = parsed
      continue
    }

    var model = parseModelLine(lines[i])
    if (model && lastDevice && lastDevice.slot === 255) {
      var parentProductId = currentParent ? currentParent.productId : NaN
      lastDevice.connectionKind = directConnectionFromModel(parentProductId, model)
      lastDevice.connectionLabel = connectionLabel(lastDevice.connectionKind)
    }
  }

  return {
    ok: true,
    noHardware: text.indexOf("No Logitech HID++ devices or webcams found.") !== -1,
    devices: devices,
    error: ""
  }
}

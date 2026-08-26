.pragma library

var ICON_BATTERY = "󰁹"
var ICON_MOUSE = "󰍽"
var ICON_KEYBOARD = "󰌌"
var ICON_TOUCHPAD = "󰟸"
var ICON_HEADSET = "󰋎"
var ICON_GAMEPAD = "󰊖"

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
  var row = String(line || "").match(/^\s*[├└]─\s+slot\s+(\d+)\s+([●○])\s+(.+)$/)
  if (!row) return null

  var detail = row[3].match(/^(.*?)\s+\(([^,()]+),\s*wpid=([^,]*),\s*battery=(.*)\)\s*$/)
  if (!detail) return { malformed: true, line: String(line || "") }

  var batteryText = String(detail[4] || "").trim()
  var percentageMatch = batteryText.match(/^(\d{1,3})%(?:\s|$)/)
  var percentage = percentageMatch ? Number(percentageMatch[1]) : -1
  if (percentage > 100) return { malformed: true, line: String(line || "") }

  return {
    slot: Number(row[1]),
    online: row[2] === "●",
    name: String(detail[1] || "").trim(),
    kind: String(detail[2] || "").trim().toLowerCase(),
    batteryAvailable: percentage >= 0,
    percentage: percentage,
    order: Number(order || 0)
  }
}

function parseList(output) {
  var text = String(output || "")
  var lines = text.split(/\r?\n/)
  var devices = []
  var malformed = []
  var order = 0

  for (var i = 0; i < lines.length; i++) {
    var parsed = parseDeviceLine(lines[i], order)
    if (!parsed) continue
    order += 1
    if (parsed.malformed) malformed.push(parsed.line)
    else devices.push(parsed)
  }

  if (malformed.length > 0) {
    return {
      ok: false,
      noHardware: false,
      devices: [],
      error: "Unsupported openlogi list device row"
    }
  }

  return {
    ok: true,
    noHardware: text.indexOf("No Logitech HID++ devices or webcams found.") !== -1,
    devices: devices,
    error: ""
  }
}

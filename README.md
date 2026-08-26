# OpenLogi batteries for Omarchy

`mwz.openlogi` is a read-only Omarchy bar plugin for battery levels reported by
[OpenLogi](https://github.com/AprilNEA/OpenLogi).

The bar shows the lowest readable battery percentage among connected devices.
Click it to open an alphabetically sorted list of connected devices and their
battery levels. Mouse, trackball, keyboard, numpad, touchpad, headset, gamepad
and joystick device types receive matching Nerd Font glyphs; unknown types use
a battery glyph. Each popup row also shows how the device is connected:
Logi Bolt, Unifying and Lightspeed receivers, Bluetooth-direct, or wired USB.
Hover over the connection glyph for its label.

## Requirements

- Omarchy 4 with the Quickshell-based shell plugin system
- `openlogi` available on `PATH`
- A Nerd Font configured for the Omarchy bar (the Omarchy default works)

The plugin does not install OpenLogi or write device settings. It calls
`openlogi list` at startup, every five minutes, and whenever its popup opens.

## Install

Install from the Git repository and enable the bar widget:

```sh
omarchy plugin add https://github.com/mwz/openlogi-omarchy-plugin --enable
```

Omarchy places the widget in the right section by default. It can be moved with
the normal bar command:

```sh
omarchy bar move mwz.openlogi --section right
```

## Develop and verify

From this repository:

```sh
omarchy plugin validate .
QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests
qmllint -I /usr/share/omarchy/shell BarWidget.qml Service.qml
```

The OpenLogi CLI currently exposes human-readable rather than structured list
output. Parsing is isolated in `Model.js` so a future machine-readable command
can replace it without changing the UI. Its `transports=` field describes the
connections supported by the model, not necessarily the live connection; the
plugin therefore combines the inventory parent, direct-device slot and current
product ID instead of treating the first listed transport as active.

## Licence

MIT

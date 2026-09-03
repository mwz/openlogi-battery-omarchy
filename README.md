# OpenLogi Battery Indicator for Omarchy

_An Omarchy battery widget that uses the OpenLogi command-line interface (CLI)._

`mwz.openlogi-battery` is a read-only Omarchy bar plugin for battery levels
reported by [OpenLogi](https://github.com/AprilNEA/OpenLogi).

![OpenLogi battery widget showing two connected mice and their battery levels](preview.png)

The bar shows the lowest readable battery percentage among connected devices.
Click it to open an alphabetically sorted list of connected devices and their
battery levels. Mouse, trackball, keyboard, numpad, touchpad, headset, gamepad,
and joystick devices use matching Nerd Font icons. Unknown devices use a battery
icon. Each popup row also shows the connection type. The supported types are
Logi Bolt, Unifying, and Lightspeed receivers, direct Bluetooth, and wired USB.

Point to the connection icon to see its label.

## Requirements

- Omarchy 4 with its Quickshell plugin system
- OpenLogi installed and the `openlogi` command available in your shell
- A Nerd Font for the Omarchy bar (the default font works)

On Omarchy, install the community-maintained
[`openlogi-bin`](https://aur.archlinux.org/packages/openlogi-bin) package from
the Arch User Repository (AUR):

```sh
yay -S openlogi-bin
```

Alternatively, install OpenLogi with its
[official Linux instructions](https://github.com/AprilNEA/OpenLogi#installation).
Make sure that the CLI can inspect your devices:

```sh
openlogi --version
openlogi list
```

The plugin does not install OpenLogi. It does not change the device
configuration. The plugin runs `openlogi list` at startup and every five
minutes. It also runs the command each time that the popup opens.

## Install

Install from the Git repository and enable the bar widget:

```sh
omarchy plugin add https://github.com/mwz/openlogi-battery-omarchy --enable
```

Omarchy places the widget in the right section by default.

Use this command to move the widget:

```sh
omarchy bar move mwz.openlogi-battery --section center
```

## Update

Update a Git-managed installation to the latest revision:

```sh
omarchy plugin update mwz.openlogi-battery
```

## Remove

Remove the plugin from Omarchy:

```sh
omarchy plugin remove mwz.openlogi-battery
```

This does not remove OpenLogi or change its configuration.

## Privacy and security

The plugin runs only the local `openlogi list` command. The plugin keeps the
output in the memory of the Omarchy shell process. The plugin does not write the
output to disk. It does not send the output over the network. It does not
request administrator access.

## Develop and test

Run the tests from this repository:

```sh
./tests/run
```

If the Omarchy source is outside `/usr/share/omarchy`, set `OMARCHY_PATH` to its
location.

The OpenLogi CLI returns plain text instead of structured data. `Model.js`
parses this text. A future machine-readable command can replace the text-reading
code without changes to the user interface. The `transports=` field lists the
connection types that the model supports. It does not identify the current
connection. The plugin uses the parent device in the inventory, the
direct-device slot, and the current product ID to identify that connection.

This is an independent community plugin. It is not affiliated with or endorsed
by OpenLogi, Logitech or Omarchy.

## Licence

MIT

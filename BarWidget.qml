import QtQuick
import QtQuick.Controls
import qs.Commons
import qs.Ui
import "Model.js" as Model

BarWidget {
  id: root
  moduleName: "mwz.openlogi-battery"

  readonly property var openlogiService: bar && bar.shell
    ? bar.shell.serviceFor(root.moduleName)
    : null
  readonly property var devices: openlogiService ? openlogiService.devices : []
  readonly property var lowestDevice: openlogiService ? openlogiService.lowestDevice : null
  readonly property bool failed: openlogiService ? openlogiService.failed : false
  readonly property bool hasReading: lowestDevice !== null
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  property bool popupOpen: false

  readonly property bool opened: popupOpen

  function alpha(color, opacity) {
    return Qt.rgba(color.r, color.g, color.b, opacity)
  }

  function refresh() {
    if (openlogiService) openlogiService.refresh()
  }

  function open() {
    popupOpen = true
    refresh()
  }

  function close() {
    popupOpen = false
  }

  function toggle() {
    if (popupOpen) close()
    else open()
  }

  function closeForPopoutSwitch() {
    close()
  }

  visible: hasReading || failed
  implicitWidth: visible ? button.implicitWidth : 0
  implicitHeight: visible ? button.implicitHeight : 0

  onVisibleChanged: if (!visible) close()

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.failed
      ? "?"
      : Model.deviceIcon(root.lowestDevice ? root.lowestDevice.kind : "")
        + " " + String(root.lowestDevice ? root.lowestDevice.percentage : "") + "%"
    dimmed: root.failed
    tooltipText: root.failed
      ? (root.openlogiService ? root.openlogiService.lastError : "OpenLogi unavailable")
      : (root.lowestDevice
          ? root.lowestDevice.name + ": " + root.lowestDevice.percentage + "%"
          : "")
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.LeftButton) root.toggle()
    }
  }

  PopupCard {
    id: popup
    anchorItem: button
    bar: root.bar
    owner: root
    open: root.popupOpen
    contentWidth: fittedContentWidth(Style.space(340))
    contentHeight: fittedContentHeight(contentColumn.implicitHeight, Style.space(480))

    Flickable {
      anchors.fill: parent
      contentWidth: width
      contentHeight: contentColumn.implicitHeight
      clip: true
      boundsBehavior: Flickable.StopAtBounds
      flickableDirection: Flickable.VerticalFlick
      interactive: contentHeight > height

      ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

      Column {
        id: contentColumn
        width: parent.width
        spacing: Style.space(12)

        PanelHero {
          width: parent.width
          title: "OpenLogi devices"
          meta: root.failed
            ? "Unavailable"
            : root.devices.length + (root.devices.length === 1 ? " device" : " devices")
          foreground: root.foreground
          fontFamily: root.fontFamily

          iconComponent: Component {
            Item {
              width: Style.font.display
              height: Style.font.display

              Text {
                anchors.centerIn: parent
                text: "󰁹"
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.display
              }
            }
          }
        }

        PanelSeparator {
          width: parent.width
          foreground: root.foreground
        }

        BorderSurface {
          visible: root.failed
          width: parent.width
          implicitHeight: errorText.implicitHeight + Style.spacing.xl * 2
          color: root.alpha(root.urgent, 0.10)
          borderSpec: Border.flat(root.alpha(root.urgent, 0.35), 1)
          radius: Style.cornerRadius

          Text {
            id: errorText
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: Style.space(12)
            anchors.rightMargin: Style.space(12)
            text: root.openlogiService ? root.openlogiService.lastError : "OpenLogi unavailable"
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.WordWrap
          }
        }

        Column {
          visible: !root.failed
          width: parent.width
          spacing: Style.spacing.md

          PanelSectionHeader {
            width: parent.width
            text: "DEVICES"
            foreground: root.foreground
            fontFamily: root.fontFamily
          }

          Repeater {
            model: root.devices

            BorderSurface {
              id: deviceRow
              required property var modelData

              width: parent.width
              height: Math.max(deviceIcon.implicitHeight, deviceName.implicitHeight,
                connectionIcon.implicitHeight, batteryLevel.implicitHeight)
                + Style.spacing.lg
              color: root.alpha(root.foreground, 0.05)
              radius: Style.cornerRadius

              Text {
                id: deviceIcon
                anchors.left: parent.left
                anchors.leftMargin: Style.space(8)
                anchors.verticalCenter: parent.verticalCenter
                width: Style.space(22)
                text: Model.deviceIcon(deviceRow.modelData.kind)
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                horizontalAlignment: Text.AlignHCenter
              }

              Text {
                id: batteryLevel
                anchors.right: parent.right
                anchors.rightMargin: Style.space(8)
                anchors.verticalCenter: parent.verticalCenter
                text: deviceRow.modelData.batteryAvailable
                  ? deviceRow.modelData.percentage + "%"
                  : "Unavailable"
                color: deviceRow.modelData.batteryAvailable ? root.foreground : root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
              }

              Text {
                id: connectionIcon
                anchors.right: batteryLevel.left
                anchors.rightMargin: Style.space(10)
                anchors.verticalCenter: parent.verticalCenter
                width: Style.space(18)
                text: Model.connectionIcon(deviceRow.modelData.connectionKind)
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                horizontalAlignment: Text.AlignHCenter

                HoverHandler {
                  id: connectionHover
                }

                PanelToolTip {
                  visible: connectionHover.hovered
                  text: deviceRow.modelData.connectionLabel
                  fontFamily: root.fontFamily
                }
              }

              Text {
                id: deviceName
                anchors.left: deviceIcon.right
                anchors.right: connectionIcon.left
                anchors.leftMargin: Style.space(8)
                anchors.rightMargin: Style.space(12)
                anchors.verticalCenter: parent.verticalCenter
                text: deviceRow.modelData.name
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                elide: Text.ElideRight
              }
            }
          }
        }
      }
    }
  }
}

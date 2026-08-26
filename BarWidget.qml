import QtQuick
import QtQuick.Controls
import qs.Commons
import qs.Ui
import "Model.js" as Model

BarWidget {
  id: root
  moduleName: "mwz.openlogi"

  readonly property var openlogiService: bar && bar.shell
    ? bar.shell.serviceFor(root.moduleName)
    : null
  readonly property var devices: openlogiService ? openlogiService.devices : []
  readonly property var lowestDevice: openlogiService ? openlogiService.lowestDevice : null
  readonly property bool failed: openlogiService ? openlogiService.failed : false
  readonly property bool hasReading: lowestDevice !== null
  readonly property color popupForeground: bar ? bar.foreground : Color.foreground
  readonly property color popupDim: Qt.darker(popupForeground, 1.55)
  readonly property color popupUrgent: bar ? bar.urgent : Color.urgent

  property bool popupOpen: false

  readonly property bool opened: popupOpen

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
        spacing: Style.space(10)

        Row {
          width: parent.width
          spacing: Style.space(8)

          Text {
            text: "󰁹"
            color: root.popupForeground
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.pixelSize: Style.font.subtitle
          }

          Text {
            width: parent.width - Style.space(30)
            text: "OpenLogi devices"
            color: root.popupForeground
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.pixelSize: Style.font.subtitle
            font.bold: true
            elide: Text.ElideRight
          }
        }

        Text {
          visible: root.failed
          width: parent.width
          text: root.openlogiService ? root.openlogiService.lastError : "OpenLogi unavailable"
          color: root.popupUrgent
          font.family: root.bar ? root.bar.fontFamily : Style.font.family
          font.pixelSize: Style.font.bodySmall
          wrapMode: Text.WordWrap
        }

        Column {
          visible: !root.failed
          width: parent.width
          spacing: Style.space(6)

          Repeater {
            model: root.devices

            Item {
              id: deviceRow
              required property var modelData

              width: parent.width
              height: Math.max(deviceIcon.implicitHeight, deviceName.implicitHeight, batteryLevel.implicitHeight)
                + Style.space(8)

              Text {
                id: deviceIcon
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                width: Style.space(22)
                text: Model.deviceIcon(deviceRow.modelData.kind)
                color: root.popupForeground
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.body
                horizontalAlignment: Text.AlignHCenter
              }

              Text {
                id: batteryLevel
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: deviceRow.modelData.batteryAvailable
                  ? deviceRow.modelData.percentage + "%"
                  : "Unavailable"
                color: deviceRow.modelData.batteryAvailable ? root.popupForeground : root.popupDim
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.bodySmall
              }

              Text {
                id: deviceName
                anchors.left: deviceIcon.right
                anchors.right: batteryLevel.left
                anchors.leftMargin: Style.space(8)
                anchors.rightMargin: Style.space(12)
                anchors.verticalCenter: parent.verticalCenter
                text: deviceRow.modelData.name
                color: root.popupForeground
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
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

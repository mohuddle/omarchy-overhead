import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Ui
import "Model.js" as Model

Panel {
  id: root
  moduleName: "io.github.mohuddle.overhead"
  ipcTarget: "io.github.mohuddle.overhead"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  property var service: null
  property string locationDraft: ""
  readonly property var barIdentity: hostWidget || root
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color muted: Color.muted
  readonly property color accent: Color.accent
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property var listedAircraft: service && service.aircraft ? service.aircraft : []

  function closeForPopoutSwitch() {}
  function open() { controller.show() }
  function close() { controller.hide() }
  function toggle() { if (opened) close(); else open() }
  function switchPanel(direction) { return false }
  function ringOn(ring) { return service ? Model.ringActive(service, ring) : true }

  readonly property int pinTopMargin: {
    if (root.bar && root.bar.position === "top")
      return (root.bar.barSize || Style.bar.sizeHorizontal) + Style.gapsOut
    return Style.gapsOut
  }
  readonly property int pinRightMargin: {
    if (root.bar && root.bar.position === "right")
      return (root.bar.barSize || Style.bar.sizeHorizontal) + Style.gapsOut
    return Style.gapsOut
  }

  PanelWindow {
    id: panel
    visible: root.opened
    implicitWidth: Style.space(500)
    implicitHeight: Style.space(420)
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    exclusiveZone: 0

    WlrLayershell.namespace: "overhead"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: root.opened ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None

    anchors.top: true
    anchors.right: true
    margins.top: root.pinTopMargin
    margins.right: root.pinRightMargin

    BorderSurface {
      id: card
      anchors.fill: parent
      color: Color.popups.background
      borderSpec: Border.surfaceSpec("popups", "border", Color.popups.border, Math.max(1, Style.space(2)))
      radius: Style.cornerRadius
      padding: Style.spacing.popupPadding

      PanelKeyCatcher {
        id: keyCatcher
        anchors.fill: parent
        anchors.topMargin: card.contentTopInset
        anchors.rightMargin: card.contentRightInset
        anchors.bottomMargin: card.contentBottomInset
        anchors.leftMargin: card.contentLeftInset
        blocked: locationField.activeFocus
        onCloseRequested: root.close()
        onTabRequested: function(direction) { root.switchPanel(direction) }

        Column {
          anchors.fill: parent
          spacing: Style.space(10)

          Row {
            width: parent.width
            spacing: Style.space(10)
            PlaneIcon {
              size: Style.space(28)
              foreground: root.accent
              anchors.verticalCenter: parent.verticalCenter
            }
            Column {
              spacing: Style.space(2)
              width: parent.width - Style.space(40)
              Text {
                textFormat: Text.PlainText
                text: "Overhead"
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.title
                font.bold: true
              }
              Text {
                textFormat: Text.PlainText
                text: service ? (service.error !== "" ? service.error : service.nearestLine) : "Nearby aircraft"
                color: service && service.watching ? root.accent : root.muted
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                width: parent.width
                wrapMode: Text.Wrap
              }
            }
          }

          Text {
            width: parent.width
            visible: service && service.needsLocation
            textFormat: Text.PlainText
            text: "Enter a ZIP, city, or coordinates. Stored only on this machine. ADS-B feeds see a lat/lon radius, nothing else. Device location is optional and is not installed with the app."
            color: root.muted
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.Wrap
          }

          Row {
            width: parent.width
            spacing: Style.space(8)
            TextField {
              id: locationField
              width: Math.max(Style.space(200), parent.width - Style.space(service && service.canLocate ? 220 : 80))
              foreground: root.foreground
              placeholderText: "72714, Santa Monica, or 34.05, -118.24"
              text: root.locationDraft
              onTextChanged: root.locationDraft = text
            }
            Button {
              text: "Set"
              bordered: true
              foreground: root.foreground
              onClicked: if (service && root.locationDraft) service.setLocation(root.locationDraft)
            }
            Button {
              visible: service && service.canLocate
              text: "Device"
              bordered: true
              foreground: root.foreground
              tooltipText: "Optional. Uses GeoClue on this machine."
              onClicked: if (service) service.locate()
            }
          }

          Text {
            visible: service && service.hasLocation
            textFormat: Text.PlainText
            text: service ? (service.locationLabel + (service.provider ? " · " + service.provider : "")) : ""
            color: root.muted
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            width: parent.width
            wrapMode: Text.Wrap
          }

          Row {
            spacing: Style.space(8)
            Button {
              text: "1 mi"
              bordered: true
              selected: root.ringOn(1)
              foreground: root.foreground
              tooltipText: "Alert within 1 mile"
              onClicked: if (service) service.toggleRing(1)
            }
            Button {
              text: "5 mi"
              bordered: true
              selected: root.ringOn(5)
              foreground: root.foreground
              tooltipText: "Alert within 5 miles"
              onClicked: if (service) service.toggleRing(5)
            }
            Button {
              text: "10 mi"
              bordered: true
              selected: root.ringOn(10)
              foreground: root.foreground
              tooltipText: "Alert within 10 miles"
              onClicked: if (service) service.toggleRing(10)
            }
          }

          Row {
            spacing: Style.space(8)
            Button {
              text: service && service.watching ? "Stop" : "Watch"
              bordered: true
              foreground: root.foreground
              onClicked: if (service) service.toggle()
            }
            Button {
              text: service && service.notify ? "Notify on" : "Notify off"
              bordered: true
              selected: service && service.notify
              foreground: root.foreground
              onClicked: if (service) service.toggleNotify()
            }
            Button {
              text: "TUI"
              bordered: true
              foreground: root.foreground
              onClicked: if (service) service.openTui()
            }
            Button {
              visible: service && service.hasLocation
              text: "Clear"
              bordered: true
              foreground: root.foreground
              onClicked: if (service) service.clearLocation()
            }
          }

          Flickable {
            width: parent.width
            height: parent.height - Style.space(220)
            clip: true
            contentWidth: width
            contentHeight: planeColumn.implicitHeight
            boundsBehavior: Flickable.StopAtBounds

            Column {
              id: planeColumn
              width: parent.width
              spacing: Style.space(4)

              Text {
                visible: root.listedAircraft.length === 0
                width: parent.width
                textFormat: Text.PlainText
                text: service && service.hasLocation ? "No aircraft in range." : "Set a location to list nearby flights."
                color: root.muted
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                wrapMode: Text.Wrap
                opacity: 0.8
              }

              Repeater {
                model: root.listedAircraft
                delegate: Text {
                  required property var modelData
                  width: planeColumn.width
                  textFormat: Text.PlainText
                  text: Model.aircraftLine(modelData)
                  color: modelData && modelData.ring === 1 ? root.accent : root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  wrapMode: Text.Wrap
                }
              }
            }
          }
        }
      }
    }
  }
}

import QtQuick
import Quickshell
import Quickshell.Io
import "Model.js" as Model

Item {
  id: root

  property var settings: ({})
  readonly property string home: Quickshell.env("HOME")
  readonly property string statusFile: home + "/.local/state/omarchy/overhead/status.json"
  readonly property string bin: home + "/.local/bin/overhead"

  property bool ready: false
  property bool watching: false
  property string consent: "none"
  property var location: null
  property var rings: [1, 5, 10]
  property bool notify: true
  property string provider: ""
  property var aircraft: []
  property var nearest: null
  property var counts: ({ "1": 0, "5": 0, "10": 0 })
  property string error: ""
  property string lastAlert: ""
  property string lastError: ""
  property string statusText: "Overhead"
  property string tooltipText: "Overhead"
  property var pending: null
  property bool canLocate: false
  readonly property bool hasLocation: Model.hasLocation({ location: root.location })
  readonly property bool needsLocation: Model.needsLocation({ location: root.location })
  readonly property bool needsConsent: root.needsLocation
  readonly property string locationLabel: Model.locationLabel({ location: root.location })
  readonly property string nearestLine: Model.nearestLine({ nearest: root.nearest, location: root.location })

  function apply(raw) {
    var parsed = Model.parseStatus(raw)
    if (!parsed.ok) {
      lastError = parsed.lastError
      return
    }
    ready = parsed.ready
    watching = parsed.watching
    consent = parsed.consent
    location = parsed.location
    rings = parsed.rings
    notify = parsed.notify
    provider = parsed.provider
    aircraft = parsed.aircraft
    nearest = parsed.nearest
    counts = parsed.counts
    error = parsed.error
    lastAlert = parsed.last_alert
    lastError = parsed.error
    canLocate = parsed.can_locate === true
    statusText = Model.statusText(parsed)
    tooltipText = Model.tooltipText(parsed)
  }

  function run(args, kind) {
    if (kind === undefined) kind = "cmd"
    if (cmd.running) {
      if (kind !== "status") root.pending = args
      return
    }
    cmd.command = [root.bin].concat(args)
    cmd.running = true
  }

  function toggle() { run([root.watching ? "stop" : "start"]) }
  function start() { run(["start"]) }
  function stop() { run(["stop"]) }
  function refresh() { run(["status"], "status") }
  function poll() { run(["poll"]) }
  function locate() { run(["locate"]) }
  function setLocation(text) { run(["location", String(text || "")]) }
  function clearLocation() { run(["location", "--clear"]) }
  function setNotify(enabled) { run(["notify", enabled ? "on" : "off"]) }
  function toggleNotify() { setNotify(!root.notify) }
  function toggleRing(ring) {
    var next = []
    var found = false
    for (var i = 0; i < root.rings.length; i++) {
      if (Number(root.rings[i]) === Number(ring)) found = true
      else next.push(root.rings[i])
    }
    if (!found) {
      next.push(Number(ring))
      next.sort(function(a, b) { return a - b })
    }
    if (next.length === 0) next = [Number(ring)]
    run(["rings", next.join(",")])
  }
  function openTui() {
    tui.command = ["xdg-terminal-exec", root.bin, "tui"]
    tui.running = true
  }

  FileView {
    id: statusView
    path: root.statusFile
    watchChanges: true
    printErrors: false
    onLoaded: root.apply(text())
    onLoadFailed: root.lastError = ""
    onFileChanged: reload()
  }

  Process {
    id: cmd
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.apply(text)
    }
    onExited: {
      if (root.pending) {
        var next = root.pending
        root.pending = null
        root.run(next)
      }
    }
  }

  Process { id: tui }

  Timer {
    interval: 2000
    running: true
    repeat: true
    onTriggered: {
      if (!cmd.running) root.refresh()
    }
  }

  Component.onCompleted: refresh()
}

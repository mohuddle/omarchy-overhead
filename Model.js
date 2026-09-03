// Status helpers for the Overhead bar plugin. Locale- and Qt-free so
// tests/model.test.js can run it under node.

function parseStatus(raw) {
  var empty = {
    ok: false,
    ready: false,
    watching: false,
    consent: "none",
    location: null,
    rings: [1, 5, 10],
    notify: true,
    ignore_ground: true,
    provider: "",
    updated: 0,
    aircraft: [],
    nearest: null,
    counts: { "1": 0, "5": 0, "10": 0 },
    error: "",
    last_alert: "",
    lastError: "",
    can_locate: false
  }
  try {
    var data = JSON.parse(String(raw || "").trim() || "{}")
  } catch (err) {
    empty.lastError = "Could not parse overhead status"
    return empty
  }
  return {
    ok: true,
    ready: data.ready !== false,
    watching: data.watching === true,
    consent: String(data.consent || "none"),
    location: data.location && typeof data.location === "object" ? data.location : null,
    rings: normalizeRings(data.rings),
    notify: data.notify !== false,
    ignore_ground: data.ignore_ground !== false,
    provider: String(data.provider || ""),
    updated: Number(data.updated || 0),
    aircraft: Array.isArray(data.aircraft) ? data.aircraft : [],
    nearest: data.nearest && typeof data.nearest === "object" ? data.nearest : null,
    counts: normalizeCounts(data.counts),
    error: String(data.error || ""),
    last_alert: String(data.last_alert || ""),
    lastError: String(data.error || ""),
    can_locate: data.can_locate === true
  }
}

function normalizeRings(value) {
  var allowed = { 1: true, 5: true, 10: true }
  var out = []
  if (Array.isArray(value)) {
    for (var i = 0; i < value.length; i++) {
      var ring = Number(value[i])
      if (allowed[ring] && out.indexOf(ring) < 0) out.push(ring)
    }
  }
  return out.length ? out : [1, 5, 10]
}

function normalizeCounts(value) {
  var counts = { "1": 0, "5": 0, "10": 0 }
  if (!value || typeof value !== "object") return counts
  ;["1", "5", "10"].forEach(function(key) {
    var n = Number(value[key] || 0)
    counts[key] = isFinite(n) ? n : 0
  })
  return counts
}

function hasLocation(status) {
  return !!(status && status.location && status.location.lat !== undefined && status.location.lon !== undefined)
}

function needsLocation(status) {
  return !hasLocation(status)
}

function needsConsent(status) {
  return needsLocation(status)
}

function canLocate(status) {
  return !!(status && status.can_locate)
}

function formatMiles(miles) {
  var n = Number(miles)
  if (!isFinite(n)) return ""
  if (n < 10) return n.toFixed(1) + " mi"
  return Math.round(n) + " mi"
}

function formatAlt(item) {
  if (!item) return ""
  if (item.ground === true || item.alt_ft === null || item.alt_ft === undefined) return "ground"
  var n = Number(item.alt_ft)
  if (!isFinite(n)) return ""
  return Math.round(n).toLocaleString("en-US") + " ft"
}

function locationLabel(status) {
  if (!hasLocation(status)) return "No location"
  var loc = status.location
  if (loc.label) return String(loc.label)
  var lat = Number(loc.lat)
  var lon = Number(loc.lon)
  if (!isFinite(lat) || !isFinite(lon)) return "No location"
  return lat.toFixed(4) + ", " + lon.toFixed(4)
}

function nearestLine(status) {
  var nearest = status && status.nearest
  if (!nearest) return hasLocation(status) ? "No aircraft in range" : "Set a location to watch the sky"
  var callsign = String(nearest.callsign || nearest.hex || "Aircraft")
  return callsign + " · " + formatMiles(nearest.miles)
}

function statusText(status) {
  if (!status) return "Overhead"
  if (status.error) return String(status.error)
  if (!hasLocation(status)) return "Overhead · enter a ZIP or city"
  if (!status.watching) return "Overhead"
  var nearest = nearestLine(status)
  return nearest.indexOf("No aircraft") === 0 ? "Overhead · watching" : nearest
}

function tooltipText(status) {
  if (!status) return "Overhead"
  if (!hasLocation(status)) return "Overhead · enter a ZIP or city"
  if (!status.watching) return "Overhead · idle"
  return nearestLine(status)
}

function ringActive(status, ring) {
  var rings = status && status.rings ? status.rings : [1, 5, 10]
  return rings.indexOf(Number(ring)) >= 0
}

function aircraftLine(item) {
  if (!item) return ""
  var callsign = String(item.callsign || item.hex || "")
  var kind = String(item.type || "")
  var alt = formatAlt(item)
  var bits = [formatMiles(item.miles), callsign]
  if (kind) bits.push(kind)
  if (alt) bits.push(alt)
  return bits.join("  ")
}

function countIn(status, ring) {
  if (!status || !status.counts) return 0
  return Number(status.counts[String(ring)] || 0)
}

function fileUrlToPath(url) {
  var s = String(url || "")
  if (s.indexOf("file://") === 0) {
    s = s.substring(7)
    if (s.charAt(0) !== "/") s = "/" + s
    try { s = decodeURIComponent(s) } catch (e) {}
  }
  return s
}

if (typeof module !== "undefined") {
  module.exports = {
    parseStatus: parseStatus,
    normalizeRings: normalizeRings,
    normalizeCounts: normalizeCounts,
    hasLocation: hasLocation,
    needsLocation: needsLocation,
    needsConsent: needsConsent,
    canLocate: canLocate,
    formatMiles: formatMiles,
    formatAlt: formatAlt,
    locationLabel: locationLabel,
    nearestLine: nearestLine,
    statusText: statusText,
    tooltipText: tooltipText,
    ringActive: ringActive,
    aircraftLine: aircraftLine,
    countIn: countIn,
    fileUrlToPath: fileUrlToPath
  }
}

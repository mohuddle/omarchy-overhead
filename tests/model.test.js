const assert = require("node:assert/strict")
const model = require("../plugin/Model.js")

assert.equal(model.parseStatus("not-json").ok, false)
assert.match(model.parseStatus("not-json").lastError, /parse/)

const empty = model.parseStatus("{}")
assert.equal(empty.ok, true)
assert.equal(empty.watching, false)
assert.deepEqual(empty.rings, [1, 5, 10])
assert.equal(empty.notify, true)
assert.equal(model.needsLocation(empty), true)
assert.equal(model.needsConsent(empty), true)
assert.equal(model.canLocate(empty), false)
assert.equal(model.hasLocation(empty), false)
assert.equal(model.locationLabel(empty), "No location")
assert.match(model.statusText(empty), /ZIP or city/)

const live = model.parseStatus(JSON.stringify({
  ready: true,
  watching: true,
  consent: "manual",
  location: { lat: 34.0195, lon: -118.4912, label: "Santa Monica, CA", source: "manual" },
  rings: [1, 5],
  notify: true,
  provider: "adsb.fi",
  aircraft: [
    { hex: "a5d28c", callsign: "UAL2373", type: "B39M", miles: 0.8, alt_ft: 4200, ring: 1, ground: false }
  ],
  nearest: { hex: "a5d28c", callsign: "UAL2373", miles: 0.8, ring: 1 },
  counts: { "1": 1, "5": 1, "10": 3 }
}))
assert.equal(live.ok, true)
assert.equal(model.hasLocation(live), true)
assert.equal(model.needsConsent(live), false)
assert.equal(model.locationLabel(live), "Santa Monica, CA")
assert.equal(model.nearestLine(live), "UAL2373 · 0.8 mi")
assert.equal(model.statusText(live), "UAL2373 · 0.8 mi")
assert.equal(model.tooltipText(live), "UAL2373 · 0.8 mi")
assert.equal(model.ringActive(live, 1), true)
assert.equal(model.ringActive(live, 10), false)
assert.equal(model.countIn(live, 1), 1)
assert.equal(model.formatMiles(0.8), "0.8 mi")
assert.equal(model.formatMiles(12.4), "12 mi")
assert.equal(model.formatAlt({ alt_ft: 4200, ground: false }), "4,200 ft")
assert.equal(model.formatAlt({ ground: true }), "ground")
assert.match(model.aircraftLine(live.aircraft[0]), /0\.8 mi/)
assert.match(model.aircraftLine(live.aircraft[0]), /UAL2373/)
assert.match(model.aircraftLine(live.aircraft[0]), /B39M/)

assert.deepEqual(model.normalizeRings([1, 7, 5, 1]), [1, 5])
assert.deepEqual(model.normalizeRings([]), [1, 5, 10])

console.log("model tests ok")

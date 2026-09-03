# omarchy-overhead

Nearby ADS-B aircraft for Omarchy. A curses TUI and a Quattro bar plugin.
Public feeder APIs (adsb.fi, adsb.lol, OpenSky), not a scrape of globe.adsbexchange.com.

## Layout

- `overhead/` — Python package: location consent, ADS-B fetch, Unix-socket daemon, CLI, curses TUI
- `plugin/` — Omarchy bar widget `io.github.mohuddle.overhead` (Quickshell QML)
- `bin/overhead` — wrapper onto the package
- `scripts/setup.sh` — `~/.local/bin` link and plugin install

## Runtime

- Config / status: `~/.local/state/omarchy/overhead/{config.json,status.json}`
- TUI: `overhead tui` — `a` allow location, `m` set location, space watch, `1`/`5`/`0` rings, `n` notify, `q` quit
- Plugin: left click opens the panel; right click toggles watching
- Alerts fire once per aircraft per 1 / 5 / 10 mile ring until that aircraft leaves
- Toasts skip ground and <500 ft, one per poll, at most every 8 seconds
- `--exec` on omarchy-notification-send comes after title and body

## Conventions

- Do not call ADS-B Exchange's keyed API or scrape the globe page.
- Never locate without consent (`a` / Allow) or an explicit manual location. Do not use IP geolocation.
- Plugin and TUI talk to the daemon through the existing JSON-lines protocol.
- Distances are statute miles. ADS-B query radius is nautical miles internally.
- `Model.js` stays Qt-free so `node tests/model.test.js` can require it.

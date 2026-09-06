# Contributing to Overhead

Omarchy bar-widget plugin (`io.github.mohuddle.overhead`). QML + plain JavaScript, plus a stdlib Python package for the daemon, CLI, and curses TUI. No extra pip packages. No build step.

Do not put `AGENTS.md`, `CLAUDE.md`, or other coding-agent instruction files in this tree. `omarchy plugin add` clones the repository into the plugin directory, and compatible agents auto-load those names from an installed plugin.

## Verify

```bash
omarchy plugin validate .
node tests/model.test.js
python3 tests/test_overhead.py
```

Run all three before committing.

## Layout

- Root QML + `manifest.json` — bar widget `io.github.mohuddle.overhead` (marketplace clone-from-root)
- `overhead/` — Python package: location, ADS-B fetch, Unix-socket daemon, CLI, curses TUI
- `bin/overhead` — wrapper onto the package
- `scripts/setup.sh` — `~/.local/bin` link (GeoClue is never installed)

## Runtime

- Config / status: `~/.local/state/omarchy/overhead/{config.json,status.json}`
- TUI: `overhead tui` — `m` ZIP/city, `a` device location only if GeoClue is present, space watch, `1`/`5`/`0` rings, `n` notify, `q` quit
- Plugin: left click opens the panel; right click toggles watching
- Alerts fire once per aircraft per 1 / 5 / 10 mile ring until that aircraft leaves
- Toasts skip ground and <500 ft, one per poll, at most every 8 seconds
- `--exec` on omarchy-notification-send comes after title and body

## Conventions

- Do not call ADS-B Exchange's keyed API or scrape the globe page. Public feeder APIs only (`adsb.fi`, `adsb.lol`, OpenSky).
- Default location is a ZIP, city, or coordinates. Do not require or install GeoClue. Do not use IP geolocation. Device locate is optional and hidden unless GeoClue is already installed.
- Plugin and TUI talk to the daemon through the existing JSON-lines protocol.
- Distances are statute miles. ADS-B query radius is nautical miles internally.
- `Model.js` stays Qt-free so `node tests/model.test.js` can require it.

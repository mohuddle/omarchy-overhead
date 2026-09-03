from __future__ import annotations

import json
import sys

from . import client
from .geo import parse_location_text
from .protocol import RINGS
from .tui import run_tui


def _print_status(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _parse_rings(text: str) -> list[int]:
    parts = [part.strip() for part in text.replace(" ", ",").split(",") if part.strip()]
    rings = []
    for part in parts:
        ring = int(part)
        if ring in RINGS and ring not in rings:
            rings.append(ring)
    if not rings:
        raise ValueError("rings must be 1, 5, and/or 10")
    return rings


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "tui"
    rest = args[1:]

    if cmd in ("-h", "--help", "help"):
        print(
            "overhead — nearby ADS-B aircraft for Omarchy\n\n"
            "  overhead                 open the TUI\n"
            "  overhead tui\n"
            "  overhead start           watch nearby aircraft\n"
            "  overhead stop\n"
            "  overhead status\n"
            "  overhead follow          JSON events on stdout\n"
            "  overhead poll            fetch once now\n"
            "  overhead locate          optional device location (needs GeoClue)\n"
            "  overhead location …      ZIP, city, or coordinates (no GeoClue)\n"
            "  overhead location --clear\n"
            "  overhead rings 1,5,10\n"
            "  overhead notify on|off\n"
            "  overhead daemon          run the background service in the foreground\n"
        )
        return 0

    if cmd == "daemon":
        from .daemon import run_daemon

        run_daemon()
        return 0

    if cmd == "tui":
        run_tui()
        return 0

    if cmd == "follow":
        for event in client.follow():
            print(json.dumps(event, ensure_ascii=False), flush=True)
        return 0

    if cmd == "start":
        _print_status(client.request("start"))
        return 0
    if cmd == "stop":
        _print_status(client.request("stop"))
        return 0
    if cmd == "status":
        _print_status(client.request("status"))
        return 0
    if cmd == "poll":
        _print_status(client.request("poll"))
        return 0
    if cmd == "locate":
        _print_status(client.request("locate"))
        return 0
    if cmd == "location":
        if rest and rest[0] in ("-h", "--help", "help"):
            print("usage: overhead location LAT LON | overhead location PLACE | overhead location --clear")
            return 0
        if rest and rest[0] in ("--clear", "clear"):
            _print_status(client.request("location", clear=True))
            return 0
        if rest and rest[0].startswith("-"):
            print("usage: overhead location LAT LON | overhead location PLACE | overhead location --clear", file=sys.stderr)
            return 2
        if not rest:
            _print_status(client.request("status"))
            return 0
        if len(rest) >= 2:
            parsed = parse_location_text(f"{rest[0]}, {rest[1]}")
            if parsed:
                _print_status(client.request("location", lat=parsed[0], lon=parsed[1]))
                return 0
        query = " ".join(rest)
        parsed = parse_location_text(query)
        if parsed:
            _print_status(client.request("location", lat=parsed[0], lon=parsed[1]))
            return 0
        _print_status(client.request("location", query=query))
        return 0
    if cmd == "rings":
        if not rest:
            print("usage: overhead rings 1,5,10", file=sys.stderr)
            return 2
        try:
            rings = _parse_rings(",".join(rest))
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        _print_status(client.request("rings", rings=rings))
        return 0
    if cmd == "notify":
        token = (rest[0] if rest else "").lower()
        if token not in ("on", "off", "1", "0", "true", "false"):
            print("usage: overhead notify on|off", file=sys.stderr)
            return 2
        enabled = token in ("on", "1", "true")
        _print_status(client.request("notify", enabled=enabled))
        return 0

    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

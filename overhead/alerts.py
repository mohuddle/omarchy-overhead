from __future__ import annotations

from typing import Any, Iterable

from .geo import format_alt, format_miles, rings_inside
from .protocol import MIN_ALERT_ALT_FT


def alertable(item: dict[str, Any], min_alt_ft: int = MIN_ALERT_ALT_FT) -> bool:
    if item.get("ground"):
        return False
    alt = item.get("alt_ft")
    if isinstance(alt, (int, float)) and alt < min_alt_ft:
        return False
    return True


def new_alerts(
    previous: dict[str, list[int]],
    aircraft: Iterable[dict[str, Any]],
    rings: list[int],
) -> tuple[list[dict[str, Any]], dict[str, list[int]]]:
    current: dict[str, list[int]] = {}
    events: list[dict[str, Any]] = []
    for item in aircraft:
        hex_id = str(item.get("hex") or "")
        if not hex_id:
            continue
        inside = rings_inside(float(item.get("miles") or 999), rings)
        if not inside:
            continue
        current[hex_id] = inside
        already = set(previous.get(hex_id) or [])
        entered = [ring for ring in inside if ring not in already]
        if not entered:
            continue
        ring = min(entered)
        events.append(
            {
                "hex": hex_id,
                "callsign": str(item.get("callsign") or hex_id),
                "type": str(item.get("type") or ""),
                "miles": float(item.get("miles") or 0),
                "ring": ring,
                "alt_ft": item.get("alt_ft"),
                "ground": bool(item.get("ground")),
                "gs_kt": item.get("gs_kt"),
            }
        )
    events.sort(key=lambda row: (row["ring"], row["miles"]))
    return events, current


def coalesce(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(events) <= 1:
        return events
    closest = min(events, key=lambda row: (row["ring"], row["miles"]))
    return [{**closest, "extra": len(events) - 1}]


def title_for(event: dict[str, Any]) -> str:
    extra = int(event.get("extra") or 0)
    ring = int(event.get("ring") or 10)
    if extra:
        return f"{extra + 1} aircraft within {ring} mile{'s' if ring != 1 else ''}"
    if ring <= 1:
        return "Plane overhead"
    return f"Plane within {ring} miles"


def body_for(event: dict[str, Any]) -> str:
    callsign = str(event.get("callsign") or event.get("hex") or "Aircraft")
    kind = str(event.get("type") or "").strip()
    label = f"{callsign} ({kind})" if kind else callsign
    parts = [f"{label} is {format_miles(float(event.get('miles') or 0))} away"]
    alt = format_alt(event.get("alt_ft") if isinstance(event.get("alt_ft"), int) else event.get("alt_ft"), bool(event.get("ground")))
    if alt:
        parts.append(alt)
    gs = event.get("gs_kt")
    if isinstance(gs, (int, float)):
        parts.append(f"{gs:.0f} kt")
    extra = int(event.get("extra") or 0)
    text = ", ".join(parts) + "."
    if extra:
        text += f" {extra} more inside the same ring."
    return text


def urgency_for(event: dict[str, Any]) -> str:
    ring = int(event.get("ring") or 10)
    if ring <= 1:
        return "critical"
    if ring <= 5:
        return "normal"
    return "low"

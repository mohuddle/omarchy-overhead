from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from typing import Any

from .geo import bearing_deg, haversine_miles, innermost_ring, miles_to_nm
from .location import USER_AGENT
from .protocol import LIST_RADIUS_MI, MAX_AIRCRAFT, QUERY_NM

HTTP_TIMEOUT = 10


class AdsError(RuntimeError):
    pass


def _http_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _callsign(*parts: Any) -> str:
    for part in parts:
        text = str(part or "").strip()
        if text:
            return text
    return ""


def _alt_ft(value: Any) -> tuple[int | None, bool]:
    if value == "ground" or value is True:
        return None, True
    if value in (None, "", False):
        return None, False
    try:
        return int(round(float(value))), False
    except (TypeError, ValueError):
        return None, False


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_exchange(item: dict[str, Any], origin: tuple[float, float], rings: list[int]) -> dict[str, Any] | None:
    lat = _float(item.get("lat"))
    lon = _float(item.get("lon"))
    if lat is None or lon is None:
        return None
    alt_ft, ground = _alt_ft(item.get("alt_baro"))
    if not ground and alt_ft is None:
        alt_ft, ground = _alt_ft(item.get("alt_geom"))
    miles = haversine_miles(origin[0], origin[1], lat, lon)
    hex_id = str(item.get("hex") or "").strip().lower()
    if not hex_id:
        return None
    gs = _float(item.get("gs"))
    track = _float(item.get("track"))
    return {
        "hex": hex_id,
        "callsign": _callsign(item.get("flight"), item.get("r"), hex_id.upper()),
        "registration": str(item.get("r") or "").strip(),
        "type": str(item.get("t") or "").strip(),
        "desc": str(item.get("desc") or "").strip(),
        "lat": lat,
        "lon": lon,
        "alt_ft": alt_ft,
        "ground": ground,
        "gs_kt": gs,
        "track": track,
        "miles": round(miles, 2),
        "bearing": round(bearing_deg(origin[0], origin[1], lat, lon), 1),
        "ring": innermost_ring(miles, rings),
        "seen": _float(item.get("seen_pos") if item.get("seen_pos") is not None else item.get("seen")),
    }


def normalize_opensky(row: list[Any], origin: tuple[float, float], rings: list[int]) -> dict[str, Any] | None:
    if not isinstance(row, list) or len(row) < 11:
        return None
    lon = _float(row[5])
    lat = _float(row[6])
    if lat is None or lon is None:
        return None
    ground = bool(row[8])
    alt_m = _float(row[7])
    alt_ft = int(round(alt_m * 3.28084)) if alt_m is not None else None
    gs_ms = _float(row[9])
    miles = haversine_miles(origin[0], origin[1], lat, lon)
    hex_id = str(row[0] or "").strip().lower()
    if not hex_id:
        return None
    return {
        "hex": hex_id,
        "callsign": _callsign(row[1], hex_id.upper()),
        "registration": "",
        "type": "",
        "desc": "",
        "lat": lat,
        "lon": lon,
        "alt_ft": alt_ft,
        "ground": ground,
        "gs_kt": None if gs_ms is None else gs_ms * 1.94384,
        "track": _float(row[10]),
        "miles": round(miles, 2),
        "bearing": round(bearing_deg(origin[0], origin[1], lat, lon), 1),
        "ring": innermost_ring(miles, rings),
        "seen": None,
    }


def _filter(aircraft: list[dict[str, Any]], *, ignore_ground: bool) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in aircraft:
        if ignore_ground and item.get("ground"):
            continue
        seen = item.get("seen")
        if seen is not None and seen > 60:
            continue
        if item.get("miles", 999) > LIST_RADIUS_MI:
            continue
        out.append(item)
    out.sort(key=lambda row: float(row.get("miles") or 999))
    return out[:MAX_AIRCRAFT]


def _counts(aircraft: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"1": 0, "5": 0, "10": 0}
    for item in aircraft:
        miles = float(item.get("miles") or 999)
        for ring in (1, 5, 10):
            if miles <= ring:
                counts[str(ring)] += 1
    return counts


def _fetch_exchange(url: str, origin: tuple[float, float], rings: list[int], ignore_ground: bool) -> list[dict[str, Any]]:
    data = _http_json(url)
    rows = data.get("ac") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise AdsError("unexpected ADS-B payload")
    aircraft = []
    for item in rows:
        if isinstance(item, dict):
            normalized = normalize_exchange(item, origin, rings)
            if normalized:
                aircraft.append(normalized)
    return _filter(aircraft, ignore_ground=ignore_ground)


def _opensky_bbox(lat: float, lon: float, nm: float) -> str:
    dlat = nm / 60.0
    dlon = nm / max(0.2, 60.0 * abs(math.cos(math.radians(lat))))
    lamin = max(-90.0, lat - dlat)
    lamax = min(90.0, lat + dlat)
    lomin = max(-180.0, lon - dlon)
    lomax = min(180.0, lon + dlon)
    return (
        "https://opensky-network.org/api/states/all"
        f"?lamin={lamin:.4f}&lomin={lomin:.4f}&lamax={lamax:.4f}&lomax={lomax:.4f}"
    )


def fetch_nearby(
    lat: float,
    lon: float,
    rings: list[int],
    *,
    ignore_ground: bool = True,
    query_nm: int = QUERY_NM,
) -> tuple[list[dict[str, Any]], str]:
    origin = (lat, lon)
    needed = int(math.ceil(miles_to_nm(LIST_RADIUS_MI)))
    nm = max(5, min(250, max(needed, int(query_nm))))
    providers = [
        ("adsb.fi", f"https://opendata.adsb.fi/api/v3/lat/{lat:.4f}/lon/{lon:.4f}/dist/{nm}"),
        ("adsb.lol", f"https://api.adsb.lol/v2/lat/{lat:.4f}/lon/{lon:.4f}/dist/{nm}"),
    ]
    errors: list[str] = []
    empty: tuple[list[dict[str, Any]], str] | None = None
    for name, url in providers:
        try:
            aircraft = _fetch_exchange(url, origin, rings, ignore_ground)
        except (AdsError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"{name}: {exc}")
            continue
        if aircraft:
            return aircraft, name
        empty = (aircraft, name)
    try:
        data = _http_json(_opensky_bbox(lat, lon, nm))
        rows = data.get("states") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            rows = []
        aircraft = []
        for row in rows:
            if isinstance(row, list):
                normalized = normalize_opensky(row, origin, rings)
                if normalized:
                    aircraft.append(normalized)
        filtered = _filter(aircraft, ignore_ground=ignore_ground)
        if filtered or empty is None:
            return filtered, "opensky"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"opensky: {exc}")
    if empty is not None:
        return empty
    raise AdsError("ADS-B feeds failed (" + "; ".join(errors) + ")")


def summarize_counts(aircraft: list[dict[str, Any]]) -> dict[str, int]:
    return _counts(aircraft)

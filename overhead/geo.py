from __future__ import annotations

import math
import re
from typing import Iterable

EARTH_RADIUS_MI = 3958.7613
MI_PER_NM = 1.150779448
LAT_RE = r"(-?\d+(?:\.\d+)?)"
MAPS_AT_RE = re.compile(rf"@{LAT_RE}\s*,\s*{LAT_RE}")
PAIR_RE = re.compile(rf"^{LAT_RE}\s*[,/\s]\s*{LAT_RE}$")
HEMISPHERE_RE = re.compile(
    rf"^{LAT_RE}\s*([NSns])\s*[,/\s]?\s*{LAT_RE}\s*([EWew])$",
)


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlmb = math.radians(lon2 - lon1)
    x = math.sin(dlmb) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlmb)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def miles_to_nm(miles: float) -> float:
    return miles / MI_PER_NM


def nm_to_miles(nm: float) -> float:
    return nm * MI_PER_NM


def valid_coords(lat: float, lon: float) -> bool:
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0 and not (lat == 0.0 and lon == 0.0)


def parse_location_text(text: str) -> tuple[float, float] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    maps = MAPS_AT_RE.search(raw)
    if maps:
        lat, lon = float(maps.group(1)), float(maps.group(2))
        return (lat, lon) if valid_coords(lat, lon) else None
    hemi = HEMISPHERE_RE.match(raw.replace("°", " "))
    if hemi:
        lat = float(hemi.group(1))
        lon = float(hemi.group(3))
        if hemi.group(2).upper() == "S":
            lat = -abs(lat)
        else:
            lat = abs(lat)
        if hemi.group(4).upper() == "W":
            lon = -abs(lon)
        else:
            lon = abs(lon)
        return (lat, lon) if valid_coords(lat, lon) else None
    pair = PAIR_RE.match(raw)
    if pair:
        lat, lon = float(pair.group(1)), float(pair.group(2))
        return (lat, lon) if valid_coords(lat, lon) else None
    return None


def rings_inside(miles: float, enabled: Iterable[int]) -> list[int]:
    return [int(ring) for ring in enabled if miles <= float(ring)]


def innermost_ring(miles: float, enabled: Iterable[int]) -> int | None:
    inside = rings_inside(miles, enabled)
    return min(inside) if inside else None


def format_miles(miles: float) -> str:
    if miles < 10:
        return f"{miles:.1f} mi"
    return f"{miles:.0f} mi"


def format_alt(alt_ft: int | None, ground: bool) -> str:
    if ground or alt_ft is None:
        return "ground"
    return f"{int(alt_ft):,} ft"


def format_coords(lat: float, lon: float) -> str:
    return f"{lat:.4f}, {lon:.4f}"

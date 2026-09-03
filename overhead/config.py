from __future__ import annotations

import json
from typing import Any

from .paths import config_path
from .protocol import POLL_SECONDS, RINGS


DEFAULTS: dict[str, Any] = {
    "consent": "none",
    "lat": None,
    "lon": None,
    "source": "",
    "label": "",
    "accuracy_m": None,
    "rings": list(RINGS),
    "notify": True,
    "ignore_ground": True,
    "watch": False,
    "poll_seconds": POLL_SECONDS,
}


def load() -> dict[str, Any]:
    path = config_path()
    data = dict(DEFAULTS)
    if not path.is_file():
        return data
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return data
    if not isinstance(raw, dict):
        return data
    data.update({k: raw[k] for k in DEFAULTS if k in raw})
    data["rings"] = normalize_rings(data.get("rings"))
    data["consent"] = str(data.get("consent") or "none")
    data["notify"] = bool(data.get("notify"))
    data["ignore_ground"] = bool(data.get("ignore_ground", True))
    data["watch"] = bool(data.get("watch"))
    try:
        data["poll_seconds"] = max(5, int(data.get("poll_seconds") or POLL_SECONDS))
    except (TypeError, ValueError):
        data["poll_seconds"] = POLL_SECONDS
    return data


def save(data: dict[str, Any]) -> None:
    path = config_path()
    payload = dict(DEFAULTS)
    payload.update(data)
    payload["rings"] = normalize_rings(payload.get("rings"))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_rings(value: Any) -> list[int]:
    allowed = set(RINGS)
    rings: list[int] = []
    if isinstance(value, list):
        for item in value:
            try:
                ring = int(item)
            except (TypeError, ValueError):
                continue
            if ring in allowed and ring not in rings:
                rings.append(ring)
    return rings or list(RINGS)


def location_from_config(data: dict[str, Any]) -> dict[str, Any] | None:
    try:
        lat = float(data["lat"])
        lon = float(data["lon"])
    except (TypeError, ValueError, KeyError):
        return None
    if data.get("lat") is None or data.get("lon") is None:
        return None
    return {
        "lat": lat,
        "lon": lon,
        "source": str(data.get("source") or ""),
        "label": str(data.get("label") or ""),
        "accuracy_m": data.get("accuracy_m"),
    }

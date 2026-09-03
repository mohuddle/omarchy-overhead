from __future__ import annotations

import json
from typing import Any

RINGS = (1, 5, 10)
LIST_RADIUS_MI = 20.0
QUERY_NM = 25
POLL_SECONDS = 12
MAX_AIRCRAFT = 40
MIN_ALERT_ALT_FT = 500
NOTIFY_MIN_INTERVAL = 8.0
FETCH_DEDUP_SECONDS = 2.0


def encode(message: dict[str, Any]) -> bytes:
    return (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")


def decode_line(line: str) -> dict[str, Any]:
    return json.loads(line)


def empty_status() -> dict[str, Any]:
    return {
        "ready": True,
        "watching": False,
        "consent": "none",
        "location": None,
        "rings": list(RINGS),
        "notify": True,
        "ignore_ground": True,
        "provider": "",
        "updated": 0,
        "aircraft": [],
        "nearest": None,
        "counts": {"1": 0, "5": 0, "10": 0},
        "error": "",
        "last_alert": "",
    }

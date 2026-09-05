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
MAX_IPC_FRAME = 64 * 1024


class ProtocolError(RuntimeError):
    pass


def append_ipc(buf: bytes, chunk: bytes, *, limit: int = MAX_IPC_FRAME) -> bytes:
    if len(buf) + len(chunk) > limit:
        raise ProtocolError("IPC frame exceeds size limit")
    return buf + chunk


def encode(message: dict[str, Any]) -> bytes:
    return (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")


def decode_line(line: str) -> dict[str, Any]:
    return json.loads(line)


def empty_status() -> dict[str, Any]:
    return {
        "ready": True,
        "watching": False,
        "consent": "none",
        "can_locate": False,
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

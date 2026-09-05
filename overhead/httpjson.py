from __future__ import annotations

import json
import urllib.request
from typing import Any

MAX_HTTP_BYTES = 2 * 1024 * 1024
_READ_CHUNK = 64 * 1024


class HttpError(RuntimeError):
    pass


def read_json(url: str, *, timeout: int, user_agent: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw_length = resp.headers.get("Content-Length")
        if raw_length is not None:
            try:
                declared = int(raw_length)
            except ValueError as exc:
                raise HttpError("invalid Content-Length") from exc
            if declared > MAX_HTTP_BYTES:
                raise HttpError("response too large")
        buf = bytearray()
        while True:
            remaining = MAX_HTTP_BYTES + 1 - len(buf)
            chunk = resp.read(min(_READ_CHUNK, remaining))
            if not chunk:
                break
            buf += chunk
            if len(buf) > MAX_HTTP_BYTES:
                raise HttpError("response too large")
        return json.loads(bytes(buf).decode("utf-8"))

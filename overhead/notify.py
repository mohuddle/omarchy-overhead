from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Any

from .alerts import body_for, title_for, urgency_for

PLUGIN_ID = "io.github.mohuddle.overhead"
_HEX = re.compile(r"^[0-9a-f]{6}$")
_GLOBE = "https://globe.adsbexchange.com/?icao="
_OPENER = "/usr/bin/xdg-open"


def globe_url(hex_id: object) -> str:
    cleaned = str(hex_id or "").strip().lower()
    if not _HEX.fullmatch(cleaned):
        return ""
    return _GLOBE + cleaned


def _extra(event: dict[str, Any]) -> int:
    try:
        return int(event.get("extra") or 0)
    except (TypeError, ValueError):
        return 0


def alert_exec(event: dict[str, Any] | None) -> list[str]:
    summon = ["omarchy-shell", "shell", "summon", PLUGIN_ID, "{}"]
    if event is None or _extra(event) > 0:
        return summon
    url = globe_url(event.get("hex"))
    if not url:
        return summon
    return [_OPENER, "--", url]


def open_globe(hex_id: object) -> bool:
    url = globe_url(hex_id)
    if not url or not os.path.isfile(_OPENER):
        return False
    subprocess.Popen(
        [_OPENER, "--", url],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return True


def notification_argv(
    title: str,
    body: str,
    urgency: str = "normal",
    event: dict[str, Any] | None = None,
) -> list[str]:
    # --exec must follow the headline and body. omarchy-notification-send
    # treats the first non-option as the title, so putting --exec first
    # makes the toast say "--exec".
    return [
        "--app-name",
        "Overhead",
        "-u",
        urgency,
        "-g",
        "✈",
        title,
        body,
        "--exec",
        *alert_exec(event),
    ]


def send_alert(event: dict[str, Any]) -> None:
    title = title_for(event)
    body = body_for(event)
    urgency = urgency_for(event)
    omarchy = shutil.which("omarchy-notification-send")
    if omarchy:
        subprocess.Popen(
            [omarchy, *notification_argv(title, body, urgency, event)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return
    notify = shutil.which("notify-send")
    if notify:
        subprocess.Popen(
            [notify, "-a", "Overhead", "-u", urgency, title, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

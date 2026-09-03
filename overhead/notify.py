from __future__ import annotations

import shutil
import subprocess
from typing import Any

from .alerts import body_for, title_for, urgency_for

PLUGIN_ID = "io.github.mohuddle.overhead"


def notification_argv(title: str, body: str, urgency: str = "normal") -> list[str]:
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
        "omarchy-shell",
        "shell",
        "summon",
        PLUGIN_ID,
        "{}",
    ]


def send_alert(event: dict[str, Any]) -> None:
    title = title_for(event)
    body = body_for(event)
    urgency = urgency_for(event)
    omarchy = shutil.which("omarchy-notification-send")
    if omarchy:
        subprocess.Popen(
            [omarchy, *notification_argv(title, body, urgency)],
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

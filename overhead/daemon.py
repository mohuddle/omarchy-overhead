from __future__ import annotations

import json
import os
import select
import signal
import socket
import sys
import threading
import time
from typing import Any

from . import ads, alerts, config, location, notify
from .geo import format_coords, format_miles, valid_coords
from .paths import (
    PathError,
    bind_private_unix_socket,
    peer_is_self,
    pid_path,
    socket_path,
    status_path,
    unlink_socket,
)
from .protocol import (
    FETCH_DEDUP_SECONDS,
    MIN_ALERT_ALT_FT,
    NOTIFY_MIN_INTERVAL,
    RINGS,
    ProtocolError,
    append_ipc,
    encode,
    empty_status,
)


class OverheadDaemon:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.fetch_lock = threading.Lock()
        self.status: dict[str, Any] = empty_status()
        self.subscribers: list[socket.socket] = []
        self.stop = threading.Event()
        self.alerted: dict[str, list[int]] = {}
        self.sock: socket.socket | None = None
        self._last_fetch = 0.0
        self._last_notify = 0.0
        data = config.load()
        self._apply_config(data)
        self.poll_seconds = int(data.get("poll_seconds") or 12)

    def _apply_config(self, data: dict[str, Any]) -> None:
        loc = config.location_from_config(data)
        self.status.update(
            {
                "ready": True,
                "consent": str(data.get("consent") or "none"),
                "can_locate": location.device_locate_available(),
                "location": loc,
                "rings": config.normalize_rings(data.get("rings")),
                "notify": bool(data.get("notify")),
                "ignore_ground": bool(data.get("ignore_ground", True)),
                "watching": bool(data.get("watch")) and loc is not None,
            }
        )
        if loc is None and not self.status.get("error"):
            self.status["error"] = "enter a ZIP, city, or coordinates"

    def persist(self) -> None:
        loc = self.status.get("location") or {}
        config.save(
            {
                "consent": self.status.get("consent") or "none",
                "lat": None if not loc else loc.get("lat"),
                "lon": None if not loc else loc.get("lon"),
                "source": "" if not loc else loc.get("source") or "",
                "label": "" if not loc else loc.get("label") or "",
                "accuracy_m": None if not loc else loc.get("accuracy_m"),
                "rings": list(self.status.get("rings") or RINGS),
                "notify": bool(self.status.get("notify")),
                "ignore_ground": bool(self.status.get("ignore_ground", True)),
                "watch": bool(self.status.get("watching")),
                "poll_seconds": self.poll_seconds,
            }
        )

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return json.loads(json.dumps(self.status))

    def write_status(self) -> None:
        path = status_path()
        tmp = path.with_suffix(".json.tmp")
        payload = json.dumps(self.snapshot(), ensure_ascii=False, separators=(",", ":"))
        tmp.write_text(payload + "\n", encoding="utf-8")
        tmp.replace(path)

    def broadcast(self, message: dict[str, Any]) -> None:
        data = encode(message)
        dead: list[socket.socket] = []
        with self.lock:
            subs = list(self.subscribers)
        for sub in subs:
            try:
                sub.sendall(data)
            except OSError:
                dead.append(sub)
        if dead:
            with self.lock:
                self.subscribers = [s for s in self.subscribers if s not in dead]
            for sub in dead:
                try:
                    sub.close()
                except OSError:
                    pass

    def set_status(self, **fields: Any) -> None:
        with self.lock:
            self.status.update(fields)
        self.write_status()
        self.broadcast({"event": "status", **self.snapshot()})

    def refresh_traffic(self, *, force: bool = False) -> dict[str, Any]:
        if not self.fetch_lock.acquire(blocking=force):
            return self.snapshot()
        try:
            now = time.monotonic()
            if not force and now - self._last_fetch < FETCH_DEDUP_SECONDS:
                return self.snapshot()
            loc = self.status.get("location")
            if not loc:
                self.set_status(error="set a location to watch the sky", watching=False)
                return self.snapshot()
            try:
                lat, lon = float(loc["lat"]), float(loc["lon"])
            except (TypeError, ValueError, KeyError):
                self.set_status(error="location is invalid", watching=False)
                return self.snapshot()
            rings = config.normalize_rings(self.status.get("rings"))
            ignore_ground = bool(self.status.get("ignore_ground", True))
            try:
                aircraft, provider = ads.fetch_nearby(
                    lat,
                    lon,
                    rings,
                    ignore_ground=ignore_ground,
                )
            except ads.AdsError as exc:
                self.set_status(error=str(exc), provider="")
                return self.snapshot()
            counts = ads.summarize_counts(aircraft)
            nearest = aircraft[0] if aircraft else None
            candidates = [item for item in aircraft if alerts.alertable(item, MIN_ALERT_ALT_FT)]
            with self.lock:
                previous = dict(self.alerted)
            events, current = alerts.new_alerts(previous, candidates, rings)
            with self.lock:
                self.alerted = current
            last_alert = self.status.get("last_alert") or ""
            if self.status.get("notify") and events:
                gap = time.monotonic() - self._last_notify
                if gap >= NOTIFY_MIN_INTERVAL:
                    for event in alerts.coalesce(events):
                        notify.send_alert(event)
                        last_alert = f"{event.get('callsign')} {format_miles(float(event.get('miles') or 0))}"
                    self._last_notify = time.monotonic()
            self._last_fetch = time.monotonic()
            self.set_status(
                aircraft=aircraft,
                nearest=nearest,
                counts=counts,
                provider=provider,
                updated=time.time(),
                error="",
                last_alert=last_alert,
            )
            return self.snapshot()
        finally:
            self.fetch_lock.release()

    def start_watch(self) -> dict[str, Any]:
        if not self.status.get("location"):
            self.set_status(watching=False, error="set a location to watch the sky")
            self.persist()
            return self.snapshot()
        self.set_status(watching=True, error="")
        self.persist()
        return self.refresh_traffic(force=True)

    def stop_watch(self) -> dict[str, Any]:
        self.set_status(watching=False)
        self.persist()
        return self.snapshot()

    def set_rings(self, rings: Any) -> dict[str, Any]:
        self.set_status(rings=config.normalize_rings(rings))
        self.persist()
        if self.status.get("watching"):
            return self.refresh_traffic(force=True)
        return self.snapshot()

    def set_notify(self, enabled: bool) -> dict[str, Any]:
        self.set_status(notify=bool(enabled))
        self.persist()
        return self.snapshot()

    def set_location(self, loc: dict[str, Any], consent: str) -> dict[str, Any]:
        lat, lon = float(loc["lat"]), float(loc["lon"])
        if not valid_coords(lat, lon):
            self.set_status(error="location is invalid")
            return self.snapshot()
        payload = {
            "lat": lat,
            "lon": lon,
            "source": str(loc.get("source") or "manual"),
            "label": str(loc.get("label") or format_coords(lat, lon)),
            "accuracy_m": loc.get("accuracy_m"),
        }
        self.set_status(location=payload, consent=consent, error="")
        self.persist()
        return self.start_watch()

    def locate(self) -> dict[str, Any]:
        can = location.device_locate_available()
        self.set_status(can_locate=can)
        if not can:
            self.set_status(
                error="Enter a ZIP, city, or coordinates. Device location is optional (omarchy pkg add geoclue)."
            )
            return self.snapshot()
        self.set_status(error="requesting device location…")
        try:
            loc = location.locate_auto()
        except location.LocationError as exc:
            self.set_status(error=str(exc), can_locate=can)
            return self.snapshot()
        return self.set_location(loc, "granted")

    def apply_query(self, text: str) -> dict[str, Any]:
        query = str(text or "").strip()
        if not query:
            self.set_status(error="enter a ZIP, city, or coordinates")
            return self.snapshot()
        try:
            loc = location.geocode_place(query)
        except location.LocationError as exc:
            self.set_status(error=str(exc))
            return self.snapshot()
        return self.set_location(loc, "manual")

    def clear_location(self) -> dict[str, Any]:
        self.alerted = {}
        self.set_status(
            location=None,
            consent="none",
            watching=False,
            aircraft=[],
            nearest=None,
            counts={"1": 0, "5": 0, "10": 0},
            provider="",
            last_alert="",
            error="location permission needed",
        )
        self.persist()
        return self.snapshot()

    def handle(self, message: dict[str, Any], conn: socket.socket) -> None:
        op = str(message.get("op") or "")
        if op == "subscribe":
            with self.lock:
                self.subscribers.append(conn)
            conn.sendall(encode({"event": "status", **self.snapshot()}))
            return
        if op == "status":
            self.set_status(can_locate=location.device_locate_available())
            conn.sendall(encode({"ok": True, **self.snapshot()}))
            return
        if op == "start":
            conn.sendall(encode({"ok": True, **self.start_watch()}))
            return
        if op == "stop":
            conn.sendall(encode({"ok": True, **self.stop_watch()}))
            return
        if op == "poll":
            conn.sendall(encode({"ok": True, **self.refresh_traffic(force=True)}))
            return
        if op == "locate":
            conn.sendall(encode({"ok": True, **self.locate()}))
            return
        if op == "location":
            if message.get("clear"):
                conn.sendall(encode({"ok": True, **self.clear_location()}))
                return
            if message.get("lat") is not None and message.get("lon") is not None:
                conn.sendall(
                    encode(
                        {
                            "ok": True,
                            **self.set_location(
                                {
                                    "lat": message.get("lat"),
                                    "lon": message.get("lon"),
                                    "source": "manual",
                                    "label": format_coords(float(message["lat"]), float(message["lon"])),
                                },
                                "manual",
                            ),
                        }
                    )
                )
                return
            conn.sendall(encode({"ok": True, **self.apply_query(str(message.get("query") or ""))}))
            return
        if op == "rings":
            conn.sendall(encode({"ok": True, **self.set_rings(message.get("rings"))}))
            return
        if op == "notify":
            conn.sendall(encode({"ok": True, **self.set_notify(bool(message.get("enabled", True)))}))
            return
        if op == "ping":
            conn.sendall(encode({"ok": True, "features": ["location", "rings", "notify"]}))
            return
        if op == "quit":
            conn.sendall(encode({"ok": True}))
            threading.Thread(target=self.shutdown, daemon=True).start()
            return
        conn.sendall(encode({"ok": False, "error": f"unknown op {op}"}))

    def serve_client(self, conn: socket.socket) -> None:
        subscribed = False
        buf = b""
        try:
            if not peer_is_self(conn):
                return
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf = append_ipc(buf, chunk)
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    if not raw.strip():
                        continue
                    message = json.loads(raw.decode("utf-8"))
                    if str(message.get("op") or "") == "subscribe":
                        subscribed = True
                    self.handle(message, conn)
                    if not subscribed:
                        return
        except (OSError, json.JSONDecodeError, ProtocolError, UnicodeDecodeError):
            pass
        finally:
            with self.lock:
                self.subscribers = [s for s in self.subscribers if s is not conn]
            try:
                conn.close()
            except OSError:
                pass

    def poll_loop(self) -> None:
        while not self.stop.wait(self.poll_seconds):
            if self.status.get("watching") and self.status.get("location"):
                try:
                    self.refresh_traffic()
                except Exception as exc:
                    self.set_status(error=str(exc))

    def shutdown(self) -> None:
        self.stop.set()
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        try:
            unlink_socket(socket_path())
        except (OSError, PathError):
            pass
        os._exit(0)

    def serve(self) -> None:
        sock_file = socket_path()
        server = bind_private_unix_socket(sock_file)
        server.listen(16)
        server.setblocking(False)
        self.sock = server
        pid_path().write_text(str(os.getpid()), encoding="utf-8")
        self.write_status()
        threading.Thread(target=self.poll_loop, daemon=True).start()

        def on_signal(*_args: object) -> None:
            self.shutdown()

        signal.signal(signal.SIGTERM, on_signal)
        signal.signal(signal.SIGINT, on_signal)

        while not self.stop.is_set():
            readable, _, _ = select.select([server], [], [], 1.0)
            if not readable:
                continue
            try:
                conn, _ = server.accept()
            except OSError:
                continue
            if not peer_is_self(conn):
                try:
                    conn.close()
                except OSError:
                    pass
                continue
            threading.Thread(target=self.serve_client, args=(conn,), daemon=True).start()


def run_daemon() -> None:
    OverheadDaemon().serve()

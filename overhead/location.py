from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any, Callable

from .geo import parse_location_text, valid_coords

USER_AGENT = "omarchy-overhead/0.1 (personal ADS-B watcher; https://github.com/mohuddle/omarchy-overhead)"
HTTP_TIMEOUT = 10


class LocationError(RuntimeError):
    pass


def _explain(exc: BaseException) -> str:
    text = str(exc)
    if "ServiceUnknown" in text or "not activatable" in text.lower():
        return "GeoClue is not installed (omarchy pkg add geoclue)"
    if "Location services disabled" in text or "NotAllowed" in text:
        return "Hyprland has no location portal; GeoClue is the backend"
    return text


def _http_json(url: str, timeout: int = HTTP_TIMEOUT) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def geocode_place(query: str) -> dict[str, Any]:
    query = str(query or "").strip()
    if not query or query.startswith("-"):
        raise LocationError("enter coordinates or a place name")
    parsed = parse_location_text(query)
    if parsed:
        lat, lon = parsed
        return {"lat": lat, "lon": lon, "source": "manual", "label": f"{lat:.4f}, {lon:.4f}", "accuracy_m": None}
    q = urllib.parse.urlencode({"format": "jsonv2", "limit": "1", "q": query.strip()})
    url = f"https://nominatim.openstreetmap.org/search?{q}"
    rows = _http_json(url)
    if not isinstance(rows, list) or not rows:
        raise LocationError(f"no match for {query!r}")
    row = rows[0]
    lat, lon = float(row["lat"]), float(row["lon"])
    if not valid_coords(lat, lon):
        raise LocationError("geocoder returned unusable coordinates")
    return {
        "lat": lat,
        "lon": lon,
        "source": "manual",
        "label": str(row.get("display_name") or query.strip()),
        "accuracy_m": None,
    }


def locate_geoclue(timeout: int = 6) -> dict[str, Any]:
    try:
        import dbus
        from dbus.mainloop.glib import DBusGMainLoop
        from gi.repository import GLib
    except ImportError as exc:
        raise LocationError("GeoClue bindings are not available") from exc

    DBusGMainLoop(set_as_default=True)
    try:
        bus = dbus.SystemBus()
        manager = dbus.Interface(
            bus.get_object("org.freedesktop.GeoClue2", "/org/freedesktop/GeoClue2/Manager"),
            "org.freedesktop.GeoClue2.Manager",
        )
        client_path = manager.GetClient()
        client_obj = bus.get_object("org.freedesktop.GeoClue2", client_path)
        props = dbus.Interface(client_obj, "org.freedesktop.DBus.Properties")
        client = dbus.Interface(client_obj, "org.freedesktop.GeoClue2.Client")
        props.Set("org.freedesktop.GeoClue2.Client", "DesktopId", "omarchy-overhead")
        props.Set("org.freedesktop.GeoClue2.Client", "RequestedAccuracyLevel", dbus.UInt32(4))
    except Exception as exc:
        raise LocationError(_explain(exc)) from exc

    result: dict[str, Any] = {}
    loop = GLib.MainLoop()

    def on_updated(_old: object, new_path: object) -> None:
        try:
            loc_props = dbus.Interface(
                bus.get_object("org.freedesktop.GeoClue2", str(new_path)),
                "org.freedesktop.DBus.Properties",
            )
            lat = float(loc_props.Get("org.freedesktop.GeoClue2.Location", "Latitude"))
            lon = float(loc_props.Get("org.freedesktop.GeoClue2.Location", "Longitude"))
            acc = float(loc_props.Get("org.freedesktop.GeoClue2.Location", "Accuracy"))
        except Exception as exc:
            result["error"] = str(exc)
            loop.quit()
            return
        if valid_coords(lat, lon):
            result.update({"lat": lat, "lon": lon, "accuracy_m": acc, "source": "geoclue", "label": "device location"})
        else:
            result["error"] = "GeoClue returned unusable coordinates"
        loop.quit()

    def on_timeout() -> bool:
        if "lat" not in result:
            result["error"] = "GeoClue timed out"
        loop.quit()
        return False

    client.connect_to_signal("LocationUpdated", on_updated)
    GLib.timeout_add_seconds(timeout, on_timeout)
    try:
        client.Start()
        loop.run()
    finally:
        try:
            client.Stop()
        except Exception:
            pass
    if "lat" not in result:
        raise LocationError(str(result.get("error") or "GeoClue did not return a location"))
    return {
        "lat": result["lat"],
        "lon": result["lon"],
        "source": "geoclue",
        "label": "device location",
        "accuracy_m": result.get("accuracy_m"),
    }


def locate_portal(timeout: int = 8) -> dict[str, Any]:
    try:
        import dbus
        from dbus.mainloop.glib import DBusGMainLoop
        from gi.repository import GLib
    except ImportError as exc:
        raise LocationError("desktop portal bindings are not available") from exc

    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    portal = bus.get_object("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop")
    loc = dbus.Interface(portal, "org.freedesktop.portal.Location")
    token = f"overhead{os.getpid()}"
    sender = bus.get_unique_name()[1:].replace(".", "_")
    session_path = f"/org/freedesktop/portal/desktop/session/{sender}/{token}"
    result: dict[str, Any] = {}
    loop = GLib.MainLoop()

    def finish_error(message: str) -> None:
        if "lat" not in result:
            result["error"] = message
        loop.quit()

    def on_location(_session: object, location: Any) -> None:
        try:
            payload = dict(location)
            lat = float(payload["Latitude"])
            lon = float(payload["Longitude"])
            acc = float(payload.get("Accuracy") or 0)
        except Exception as exc:
            finish_error(str(exc))
            return
        if not valid_coords(lat, lon):
            finish_error("portal returned unusable coordinates")
            return
        result.update({"lat": lat, "lon": lon, "accuracy_m": acc, "source": "portal", "label": "device location"})
        loop.quit()

    def on_create(response: int, _results: Any) -> None:
        if response != 0:
            finish_error("location permission denied")
            return
        try:
            loc.Start(dbus.ObjectPath(session_path), "", {"handle_token": token + "s"})
        except Exception as exc:
            finish_error(str(exc))

    def on_timeout() -> bool:
        finish_error("location request timed out")
        return False

    bus.add_signal_receiver(
        on_location,
        signal_name="LocationUpdated",
        dbus_interface="org.freedesktop.portal.Location",
    )
    try:
        handle = loc.CreateSession({"session_handle_token": token})
        request = dbus.Interface(
            bus.get_object("org.freedesktop.portal.Desktop", str(handle)),
            "org.freedesktop.portal.Request",
        )
        request.connect_to_signal("Response", on_create)
    except Exception as exc:
        raise LocationError(_explain(exc)) from exc
    GLib.timeout_add_seconds(timeout, on_timeout)
    loop.run()
    if "lat" not in result:
        raise LocationError(str(result.get("error") or "desktop location portal failed"))
    return {
        "lat": result["lat"],
        "lon": result["lon"],
        "source": "portal",
        "label": "device location",
        "accuracy_m": result.get("accuracy_m"),
    }


def locate_auto() -> dict[str, Any]:
    errors: list[str] = []
    steps: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("portal", locate_portal),
        ("geoclue", locate_geoclue),
    ]
    for name, fn in steps:
        try:
            return fn()
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    raise LocationError(
        "Device location needs GeoClue ("
        + "; ".join(errors)
        + "). Install it with: omarchy pkg add geoclue — or type coordinates / a place name."
    )

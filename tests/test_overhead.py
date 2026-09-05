from __future__ import annotations

import json
import math
import os
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overhead.ads import normalize_exchange, normalize_opensky
from overhead.httpjson import MAX_HTTP_BYTES, HttpError, read_json
from overhead.location import LocationError, US_ZIP_RE, device_locate_available, geocode_place
from overhead.alerts import alertable, body_for, coalesce, new_alerts, title_for, urgency_for
from overhead.notify import PLUGIN_ID, notification_argv
from overhead.paths import PathError, ensure_private_dir, runtime_dir
from overhead.protocol import MAX_IPC_FRAME, ProtocolError, append_ipc
from overhead.geo import (
    format_miles,
    haversine_miles,
    innermost_ring,
    parse_location_text,
    rings_inside,
    valid_coords,
)


class GeoTests(unittest.TestCase):
    def test_nyc_philadelphia(self) -> None:
        miles = haversine_miles(40.7128, -74.0060, 39.9526, -75.1652)
        self.assertTrue(79.0 < miles < 83.0)

    def test_parse_location(self) -> None:
        self.assertEqual(parse_location_text("34.05, -118.24"), (34.05, -118.24))
        self.assertEqual(parse_location_text("34.05 N 118.24 W"), (34.05, -118.24))
        self.assertEqual(parse_location_text("https://maps.google.com/@34.05,-118.24,14z"), (34.05, -118.24))
        self.assertIsNone(parse_location_text("Santa Monica"))
        self.assertIsNone(parse_location_text("91, 0"))
        self.assertFalse(valid_coords(0.0, 0.0))
        with self.assertRaises(LocationError):
            geocode_place("--help")
        self.assertTrue(US_ZIP_RE.match("72714"))
        self.assertTrue(US_ZIP_RE.match("72714-1234"))
        self.assertFalse(US_ZIP_RE.match("Santa Monica"))
        self.assertIsInstance(device_locate_available(), bool)

    def test_rings(self) -> None:
        self.assertEqual(rings_inside(0.4, [1, 5, 10]), [1, 5, 10])
        self.assertEqual(rings_inside(3.2, [1, 5, 10]), [5, 10])
        self.assertEqual(rings_inside(12, [1, 5, 10]), [])
        self.assertEqual(innermost_ring(3.2, [1, 5, 10]), 5)
        self.assertEqual(format_miles(0.8), "0.8 mi")
        self.assertEqual(format_miles(12.4), "12 mi")


class AdsTests(unittest.TestCase):
    def test_exchange_payload(self) -> None:
        item = {
            "hex": "A5D28C",
            "flight": "UAL2373 ",
            "r": "N47412",
            "t": "B39M",
            "desc": "BOEING 737 MAX 9",
            "lat": 34.02,
            "lon": -118.49,
            "alt_baro": 4200,
            "gs": 288.1,
            "track": 268.2,
            "seen_pos": 1.2,
        }
        plane = normalize_exchange(item, (34.0195, -118.4912), [1, 5, 10])
        assert plane is not None
        self.assertEqual(plane["hex"], "a5d28c")
        self.assertEqual(plane["callsign"], "UAL2373")
        self.assertEqual(plane["type"], "B39M")
        self.assertEqual(plane["ring"], 1)
        self.assertLess(plane["miles"], 1.0)
        self.assertFalse(plane["ground"])

    def test_ground_and_opensky(self) -> None:
        ground = normalize_exchange(
            {"hex": "abc123", "lat": 34.02, "lon": -118.49, "alt_baro": "ground", "flight": "N1"},
            (34.0195, -118.4912),
            [1, 5, 10],
        )
        assert ground is not None
        self.assertTrue(ground["ground"])
        row = ["a5d28c", "UAL2373 ", "United States", 0, 0, -118.49, 34.02, 1280.16, False, 148.0, 270.0]
        plane = normalize_opensky(row, (34.0195, -118.4912), [1, 5, 10])
        assert plane is not None
        self.assertEqual(plane["callsign"], "UAL2373")
        self.assertTrue(math.isclose(plane["alt_ft"] or 0, 4200, abs_tol=5))


class AlertTests(unittest.TestCase):
    def test_enter_inner_ring_only(self) -> None:
        plane = {"hex": "aa", "callsign": "UAL1", "type": "B738", "miles": 0.8, "alt_ft": 3000, "ground": False}
        events, state = new_alerts({}, [plane], [1, 5, 10])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["ring"], 1)
        self.assertEqual(title_for(events[0]), "Plane overhead")
        self.assertEqual(urgency_for(events[0]), "critical")
        more, state = new_alerts(state, [plane], [1, 5, 10])
        self.assertEqual(more, [])
        far = {**plane, "miles": 8.0}
        left, state = new_alerts(state, [far], [1, 5, 10])
        self.assertEqual(left, [])
        gone, state = new_alerts(state, [], [1, 5, 10])
        self.assertEqual(gone, [])
        self.assertEqual(state, {})
        reenter, _ = new_alerts(state, [far], [1, 5, 10])
        self.assertEqual(reenter[0]["ring"], 10)
        self.assertIn("8.0 mi", body_for(reenter[0]))

    def test_coalesce_swarm(self) -> None:
        events = [
            {"hex": "a", "callsign": "A", "miles": 4.0, "ring": 5, "type": "C172"},
            {"hex": "b", "callsign": "B", "miles": 2.0, "ring": 5, "type": "C172"},
            {"hex": "c", "callsign": "C", "miles": 3.0, "ring": 5, "type": "C172"},
        ]
        batched = coalesce(events)
        self.assertEqual(len(batched), 1)
        self.assertEqual(batched[0]["callsign"], "B")
        self.assertEqual(batched[0]["extra"], 2)
        self.assertIn("3 aircraft", title_for(batched[0]))
        pair = coalesce(events[:2])
        self.assertEqual(len(pair), 1)
        self.assertEqual(pair[0]["extra"], 1)

    def test_alertable_skips_low_and_ground(self) -> None:
        self.assertFalse(alertable({"ground": True, "alt_ft": 8000}))
        self.assertFalse(alertable({"ground": False, "alt_ft": 200}))
        self.assertTrue(alertable({"ground": False, "alt_ft": 1200}))


class NotifyTests(unittest.TestCase):
    def test_exec_follows_title_and_body(self) -> None:
        argv = notification_argv("Plane overhead", "UAL1 is 0.8 mi away.", "critical")
        self.assertEqual(argv[argv.index("-u") + 1], "critical")
        title_at = argv.index("Plane overhead")
        body_at = argv.index("UAL1 is 0.8 mi away.")
        exec_at = argv.index("--exec")
        self.assertLess(title_at, body_at)
        self.assertLess(body_at, exec_at)
        self.assertEqual(argv[exec_at + 1 : exec_at + 5], ["omarchy-shell", "shell", "summon", PLUGIN_ID])


class PathSecurityTests(unittest.TestCase):
    def test_creates_private_runtime_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "run"
            base.mkdir()
            os.chmod(base, 0o700)
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(base)}):
                dest = runtime_dir()
            self.assertEqual(dest, base / "omarchy-overhead")
            st = os.lstat(dest)
            self.assertTrue(stat.S_ISDIR(st.st_mode))
            self.assertFalse(stat.S_ISLNK(st.st_mode))
            self.assertEqual(st.st_uid, os.getuid())
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o700)

    def test_rejects_symlink_runtime_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real"
            real.mkdir()
            os.chmod(real, 0o700)
            link = Path(tmp) / "link"
            link.symlink_to(real)
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(link)}):
                with self.assertRaises(PathError):
                    runtime_dir()

    def test_rejects_permissive_runtime_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "open"
            base.mkdir()
            os.chmod(base, 0o777)
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(base)}):
                with self.assertRaises(PathError):
                    runtime_dir()

    def test_fallback_rejects_symlink_and_tightens_owned_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            link = root / "tmp-link"
            link.symlink_to(root)
            with patch("overhead.paths._tmp_root", return_value=link):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("XDG_RUNTIME_DIR", None)
                    with self.assertRaises(PathError):
                        runtime_dir()
            owned = root / f"omarchy-overhead-{os.getuid()}"
            owned.mkdir()
            os.chmod(owned, 0o755)
            with patch("overhead.paths._tmp_root", return_value=root):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("XDG_RUNTIME_DIR", None)
                    dest = runtime_dir()
            self.assertEqual(dest, owned)
            self.assertEqual(stat.S_IMODE(os.lstat(owned).st_mode), 0o700)

    def test_ensure_private_dir_rejects_parent_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real"
            real.mkdir()
            link = Path(tmp) / "link"
            link.symlink_to(real)
            with self.assertRaises(PathError):
                ensure_private_dir(link / "child")


class IpcAndHttpLimitTests(unittest.TestCase):
    def test_append_ipc_caps_frame(self) -> None:
        buf = append_ipc(b"abc", b"def")
        self.assertEqual(buf, b"abcdef")
        with self.assertRaises(ProtocolError):
            append_ipc(b"x" * MAX_IPC_FRAME, b"y")

    def test_http_json_respects_content_length_and_body_cap(self) -> None:
        class FakeResp:
            def __init__(self, body: bytes, length: str | None) -> None:
                self.headers = {} if length is None else {"Content-Length": length}
                self._body = body

            def read(self, n: int = -1) -> bytes:
                if not self._body:
                    return b""
                chunk, self._body = self._body[:n], self._body[n:]
                return chunk

            def __enter__(self) -> FakeResp:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        payload = json.dumps({"ok": True}).encode("utf-8")
        with patch("urllib.request.urlopen", return_value=FakeResp(payload, str(len(payload)))):
            self.assertEqual(read_json("http://example.test", timeout=1, user_agent="t"), {"ok": True})
        with patch("urllib.request.urlopen", return_value=FakeResp(b"{}", str(MAX_HTTP_BYTES + 1))):
            with self.assertRaises(HttpError):
                read_json("http://example.test", timeout=1, user_agent="t")
        with patch(
            "urllib.request.urlopen",
            return_value=FakeResp(b"x" * (MAX_HTTP_BYTES + 1), None),
        ):
            with self.assertRaises(HttpError):
                read_json("http://example.test", timeout=1, user_agent="t")


class DaemonSocketTests(unittest.TestCase):
    def test_socket_is_private_and_rejects_oversize_frame(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / "run"
            runtime.mkdir()
            os.chmod(runtime, 0o700)
            state = Path(tmp) / "state"
            state.mkdir()
            env = os.environ.copy()
            env["XDG_RUNTIME_DIR"] = str(runtime)
            env["XDG_STATE_HOME"] = str(state)
            env["HOME"] = tmp
            env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
            proc = subprocess.Popen(
                [sys.executable, "-m", "overhead", "daemon"],
                cwd=str(ROOT),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            sock_file = runtime / "omarchy-overhead" / "omarchy-overhead.sock"
            try:
                deadline = time.time() + 5
                while time.time() < deadline and not sock_file.exists():
                    time.sleep(0.05)
                self.assertTrue(sock_file.exists(), "daemon did not create the control socket")
                st = os.lstat(sock_file)
                self.assertTrue(stat.S_ISSOCK(st.st_mode))
                self.assertEqual(st.st_uid, os.getuid())
                self.assertEqual(stat.S_IMODE(st.st_mode) & 0o077, 0)

                ping = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                ping.settimeout(2)
                ping.connect(str(sock_file))
                ping.sendall(b'{"op":"ping"}\n')
                reply = ping.recv(256)
                ping.close()
                self.assertIn(b'"ok": true', reply)

                huge = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                huge.settimeout(2)
                huge.connect(str(sock_file))
                huge.sendall(b"x" * (MAX_IPC_FRAME + 8) + b"\n")
                data = huge.recv(64)
                huge.close()
                self.assertEqual(data, b"")
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()

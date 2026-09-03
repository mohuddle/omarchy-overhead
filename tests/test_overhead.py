from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overhead.ads import normalize_exchange, normalize_opensky
from overhead.location import LocationError, US_ZIP_RE, device_locate_available, geocode_place
from overhead.alerts import alertable, body_for, coalesce, new_alerts, title_for, urgency_for
from overhead.notify import PLUGIN_ID, notification_argv
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


if __name__ == "__main__":
    unittest.main()

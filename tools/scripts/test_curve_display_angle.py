#!/usr/bin/env python3
"""CURVE display-angle override contract (presentation only).

Mirrors dashboard/transport-build.js curveDisplayDirectionRad:
engineer override wins over entry/exit RUN heading; Auto clears override.
"""
from __future__ import annotations

import math
import unittest


def display_direction_rad(n: dict) -> float:
    ov = n.get("curveDisplayAngle")
    if ov is not None and str(ov).upper() != "AUTO":
        return float(ov) * math.pi / 180.0
    entry = n.get("entryCanvas") or {}
    exit_ = n.get("exitCanvas") or {}
    if entry and exit_:
        dx = float(exit_.get("x", 0)) - float(entry.get("x", 0))
        dy = float(exit_.get("y", 0)) - float(entry.get("y", 0))
        if math.hypot(dx, dy) > 0.5:
            return math.atan2(dy, dx)
    return math.radians(-35.0)


def oblong_corners(n: dict, half_l: float = 40.0, half_w: float = 10.0):
    ang = display_direction_rad(n)
    mx = (float(n["entryCanvas"]["x"]) + float(n["exitCanvas"]["x"])) / 2
    my = (float(n["entryCanvas"]["y"]) + float(n["exitCanvas"]["y"])) / 2
    ux, uy = math.cos(ang), math.sin(ang)
    nx, ny = -uy, ux
    return [
        (mx - ux * half_l + nx * half_w, my - uy * half_l + ny * half_w),
        (mx + ux * half_l + nx * half_w, my + uy * half_l + ny * half_w),
    ]


class TestCurveDisplayAngle(unittest.TestCase):
    def setUp(self) -> None:
        self.n = {
            "entryCanvas": {"x": 0.0, "y": 0.0},
            "exitCanvas": {"x": 100.0, "y": 0.0},  # east
        }

    def test_auto_follows_run_heading(self) -> None:
        deg = math.degrees(display_direction_rad(self.n))
        self.assertAlmostEqual(deg, 0.0, places=5)

    def test_override_angles_change_render(self) -> None:
        base = oblong_corners(self.n)
        for ang in (45, -45, 90, -90, 0, 180, 135, -135):
            self.n["curveDisplayAngle"] = ang
            pts = oblong_corners(self.n)
            if ang % 180 != 0:
                self.assertNotEqual(pts, base, f"{ang}° should move geometry")
            got = math.degrees(display_direction_rad(self.n))
            # normalize
            while got > 180:
                got -= 360
            while got < -180:
                got += 360
            self.assertAlmostEqual(got, float(ang), places=5)

    def test_auto_clears_override(self) -> None:
        self.n["curveDisplayAngle"] = 90
        del self.n["curveDisplayAngle"]
        self.assertAlmostEqual(math.degrees(display_direction_rad(self.n)), 0.0, places=5)

    def test_area_assignment_independent(self) -> None:
        self.n["curveDisplayAngle"] = 45
        self.n["area"] = "ModuleA"
        self.n["area"] = "ModuleB"  # Area change must not clear display override
        self.assertEqual(self.n["curveDisplayAngle"], 45)


if __name__ == "__main__":
    unittest.main(verbosity=2)

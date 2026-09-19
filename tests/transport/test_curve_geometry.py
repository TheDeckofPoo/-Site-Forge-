#!/usr/bin/env python3
"""Physical CURVE centerline solver — anchors immutable, no inflation X-cross."""
from __future__ import annotations
# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys
_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO
REPO_ROOT = _SF_REPO
# --- end bootstrap ---

import math
import unittest

from fortna_curve_geometry import (
    build_physical_curve_display_path,
    consecutive_curves_form_x,
    curve_from_chord_and_sweep,
    curve_from_tangents,
    path_self_crosses,
    project_shared_topology_joints,
)


class TestCurveAnchorsImmutable(unittest.TestCase):
    def test_chord_sweep_preserves_endpoints(self) -> None:
        entry = (100.0, 200.0)
        exit_pt = (180.0, 280.0)
        solved = curve_from_chord_and_sweep(entry, exit_pt, -90)
        self.assertIsNotNone(solved)
        assert solved is not None
        self.assertAlmostEqual(solved["entry"]["x"], entry[0], places=6)
        self.assertAlmostEqual(solved["entry"]["y"], entry[1], places=6)
        self.assertAlmostEqual(solved["exit"]["x"], exit_pt[0], places=6)
        self.assertAlmostEqual(solved["exit"]["y"], exit_pt[1], places=6)
        # Tiny chord still does not grow anchors
        tiny = curve_from_chord_and_sweep((0.0, 0.0), (10.0, 0.0), 90)
        self.assertIsNotNone(tiny)
        assert tiny is not None
        self.assertAlmostEqual(tiny["entry"]["x"], 0.0, places=6)
        self.assertAlmostEqual(tiny["exit"]["x"], 10.0, places=6)
        self.assertLess(tiny["radius"], 20.0)  # no minR inflation

    def test_build_path_anchors_unchanged(self) -> None:
        n = {
            "entryCanvas": {"x": 50.0, "y": 50.0},
            "exitCanvas": {"x": 50.0, "y": 150.0},
            "kind": "conv_right",
            "sweepDeg": -90,
        }
        path = build_physical_curve_display_path(n)
        self.assertIsNotNone(path)
        assert path is not None
        self.assertEqual(path[0]["cmd"], "move")
        self.assertAlmostEqual(path[0]["x"], 50.0, places=6)
        self.assertAlmostEqual(path[0]["y"], 50.0, places=6)
        arc = path[1]
        self.assertEqual(arc["cmd"], "arc")
        self.assertAlmostEqual(arc["x"], 50.0, places=6)
        self.assertAlmostEqual(arc["y"], 150.0, places=6)


class TestNoSelfCross(unittest.TestCase):
    def test_quarter_turn_no_self_cross(self) -> None:
        solved = curve_from_chord_and_sweep((0.0, 0.0), (100.0, 100.0), -90)
        from fortna_curve_geometry import solved_to_path

        path = solved_to_path(solved)
        self.assertFalse(path_self_crosses(path))

    def test_tangent_solve_no_self_cross(self) -> None:
        # 90° CW: entry east, exit south
        entry = (0.0, 0.0)
        exit_pt = (100.0, 100.0)
        te = (1.0, 0.0)
        tx = (0.0, 1.0)
        solved = curve_from_tangents(entry, exit_pt, te, tx)
        # May or may not solve depending on geometry; if it does, no self-cross
        if solved:
            from fortna_curve_geometry import solved_to_path

            self.assertFalse(path_self_crosses(solved_to_path(solved)))


class TestConsecutiveNoInflationX(unittest.TestCase):
    def test_joined_curves_do_not_form_x(self) -> None:
        # A exits into B entry (shared joint) — classic inflation X victim
        a = {
            "id": "a",
            "conveyorTag": "P100",
            "downstream": "P102",
            "entryCanvas": {"x": 0.0, "y": 0.0},
            "exitCanvas": {"x": 40.0, "y": 40.0},
            "kind": "conv_right",
            "sweepDeg": -90,
        }
        b = {
            "id": "b",
            "conveyorTag": "P102",
            "entryCanvas": {"x": 40.0, "y": 40.0},
            "exitCanvas": {"x": 80.0, "y": 0.0},
            "kind": "conv_left",
            "sweepDeg": 90,
        }
        self.assertFalse(consecutive_curves_form_x(a, b))
        # Paths keep shared joint
        pa = build_physical_curve_display_path(a)
        pb = build_physical_curve_display_path(b)
        assert pa and pb
        self.assertAlmostEqual(pa[-1]["x"], pb[0]["x"], places=5)
        self.assertAlmostEqual(pa[-1]["y"], pb[0]["y"], places=5)

    def test_topology_joint_projection(self) -> None:
        nodes = [
            {
                "id": "a",
                "conveyorTag": "P100",
                "downstream": "P102",
                "exitCanvas": {"x": 10.0, "y": 10.0},
                "entryCanvas": {"x": 0.0, "y": 0.0},
            },
            {
                "id": "b",
                "conveyorTag": "P102",
                "entryCanvas": {"x": 14.0, "y": 12.0},
                "exitCanvas": {"x": 50.0, "y": 12.0},
            },
        ]
        ov = project_shared_topology_joints(nodes)
        self.assertIn("a", ov)
        self.assertIn("b", ov)
        self.assertAlmostEqual(ov["a"]["exit"]["x"], ov["b"]["entry"]["x"], places=6)


class TestNinetyRadius(unittest.TestCase):
    def test_radius_is_chord_over_sqrt2(self) -> None:
        entry = (0.0, 0.0)
        exit_pt = (100.0, 0.0)
        # For 90°, chord = r*√2 ⇒ r = chord/√2
        solved = curve_from_chord_and_sweep(entry, exit_pt, 90)
        assert solved is not None
        self.assertAlmostEqual(solved["radius"], 100.0 / math.sqrt(2), places=5)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""ORI-078 — Transport Apply must not silently drop canvas nodes (P128 / P1A).

Also covers short-tag acceptance (P1 / P1A) for conveyor identity.
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_transport_graph import (  # noqa: E402
    _is_conveyor_tag,
    apply_graph_to_workbook,
)


class TestShortConveyorTags(unittest.TestCase):
    def test_single_digit_and_lettered_accepted(self) -> None:
        self.assertTrue(_is_conveyor_tag("P1"))
        self.assertTrue(_is_conveyor_tag("P1A"))
        self.assertTrue(_is_conveyor_tag("P128"))
        self.assertTrue(_is_conveyor_tag("P128A"))
        self.assertFalse(_is_conveyor_tag("M128"))
        self.assertFalse(_is_conveyor_tag("P128_AUX"))


class TestApplyDoesNotDropCanvasNodes(unittest.TestCase):
    def test_p128_and_p1a_create_workbook_rows(self) -> None:
        graph = {
            "version": 1,
            "applyMode": "canonical",
            "areas": [
                {
                    "id": "pick",
                    "name": "PICK",
                    "nodes": [
                        {
                            "id": "n128",
                            "kind": "conv_straight",
                            "conveyorTag": "P128",
                            "safetyZone": "PICK_ESZ",
                        },
                        {
                            "id": "n1a",
                            "kind": "conv_right",
                            "conveyorTag": "P1A",
                            "safetyZone": "PICK_ESZ",
                        },
                        {
                            "id": "n1001",
                            "kind": "conv_straight",
                            "conveyorTag": "P1001",
                            "safetyZone": "PICK_ESZ",
                        },
                    ],
                    "wires": [],
                }
            ],
        }
        wb = {
            "machine": "MSCRENOPICK",
            "conveyors": [
                {
                    "conveyor": "P1001",
                    "main_area": "MSCRENOPICK_Area",
                    "source": "run",
                    "include": True,
                }
            ],
            "areas": [],
            "options": {},
            "merges_2to1": [],
        }
        out = apply_graph_to_workbook(graph, copy.deepcopy(wb))
        self.assertTrue(out.get("ok"), out)
        by = {
            str(r.get("conveyor") or "").upper(): r
            for r in (out["workbook"].get("conveyors") or [])
        }
        self.assertIn("P128", by)
        self.assertIn("P1A", by)
        self.assertEqual(by["P128"].get("main_area"), "PICK")
        self.assertEqual(by["P1A"].get("main_area"), "PICK")
        created = {str(t).upper() for t in (out.get("conveyors_created") or [])}
        self.assertTrue({"P128", "P1A"} <= created, created)
        self.assertEqual(by["P1001"].get("main_area"), "PICK")


class TestEngineerZoneConveyorProvenanceLabel(unittest.TestCase):
    """Safety zone detail must not overstate AUTO — RUN PROVEN for engineer zones."""

    def test_safety_build_js_stamps_engineer_assigned(self) -> None:
        src = (
            _SF_REPO / "dashboard" / "safety-build.js"
        ).read_text(encoding="utf-8")
        self.assertIn("ORI-078", src)
        self.assertIn(
            "conveyorsOrigin: (z.conveyors || []).length ? 'ENGINEER_ASSIGNED'",
            src,
        )


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""ORI-032 — explicit Area delete persists; no resurrection; no dangling areaRef."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_transport_graph import (  # noqa: E402
    _rebuild_workbook_areas,
    apply_graph_to_workbook,
)


class TestExplicitAreaDeletePersistence(unittest.TestCase):
    def test_tombstone_prevents_workbook_resurrection(self) -> None:
        wb = {
            "conveyors": [
                {
                    "conveyor": "P100",
                    "main_area": "Busy_Area",
                    "include": True,
                    "safety_zone": "Busy_ESZone1",
                }
            ],
            "areas": [
                {"name": "Busy_Area", "safety_zone": "Busy_ESZone1", "conveyor_count": 1},
                {
                    "name": "Empty_Eng_Area",
                    "safety_zone": "Empty_ESZone1",
                    "conveyor_count": 0,
                    "provenance": "ENGINEER_CREATED",
                    "engineerCreated": True,
                },
            ],
            "options": {"areas": ["Busy_Area", "Empty_Eng_Area"], "safety_zones": []},
            "safety_build": {
                "zones": [
                    {
                        "name": "Empty_ESZone1",
                        "areaRef": "Empty_Eng_Area",
                        "area": "Empty_Eng_Area",
                        "members": [],
                        "provenance": "ENGINEER_CREATED",
                    }
                ]
            },
        }
        # Simulate Apply after explicit delete: graph omits the Area + tombstones it
        graph = {
            "areas": [
                {
                    "id": "a1",
                    "name": "Busy_Area",
                    "isDefault": False,
                    "nodes": [{"kind": "conveyor", "conveyorTag": "P100"}],
                    "wires": [],
                }
            ],
            "deletedAreas": ["Empty_Eng_Area"],
            "safetyBuild": {
                "source": "transport_engineer",
                "zones": [
                    {
                        "source_id": "szone_empty",
                        "name": "Empty_ESZone1",
                        "engineering_name": "Empty_ESZone1",
                        "areaRef": "",
                        "area": "",
                        "members": [],
                        "engineerEdited": True,
                        "createdBy": "engineer",
                        "provenance": "ENGINEER_CREATED",
                    }
                ],
            },
            "merges": [],
        }
        result = apply_graph_to_workbook(graph, wb)
        self.assertTrue(result.get("ok"))
        names = {a["name"] for a in (result["workbook"].get("areas") or [])}
        self.assertIn("Busy_Area", names)
        self.assertNotIn("Empty_Eng_Area", names)
        zones = (result["workbook"].get("safety_build") or {}).get("zones") or []
        empty_z = next(
            (z for z in zones if "Empty" in str(z.get("name") or "")),
            None,
        )
        self.assertIsNotNone(empty_z)
        self.assertEqual(str(empty_z.get("areaRef") or ""), "")
        self.assertEqual(str(empty_z.get("area") or ""), "")
        opts = (result["workbook"].get("options") or {}).get("areas") or []
        self.assertNotIn("Empty_Eng_Area", opts)

    def test_rebuild_honors_deleted_areas(self) -> None:
        wb = {
            "conveyors": [],
            "areas": [
                {
                    "name": "Gone_Area",
                    "provenance": "ENGINEER_CREATED",
                    "engineerCreated": True,
                    "conveyor_count": 0,
                }
            ],
            "options": {"areas": ["Gone_Area"]},
            "safety_build": {
                "zones": [{"name": "Z1", "areaRef": "Gone_Area", "area": "Gone_Area"}]
            },
        }
        _rebuild_workbook_areas(wb, deleted_areas=["Gone_Area"])
        self.assertEqual(wb["areas"], [])
        z = wb["safety_build"]["zones"][0]
        self.assertEqual(z.get("areaRef"), "")
        self.assertEqual(z.get("area"), "")

    def test_js_tombstone_contract(self) -> None:
        src = (ROOT / "dashboard" / "transport-build.js").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("deletedAreas", src)
        self.assertIn("tombstone", src.lower())
        sb = (ROOT / "dashboard" / "safety-build.js").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("sfClearSafetyAreaRefs", sb)


if __name__ == "__main__":
    unittest.main(verbosity=2)

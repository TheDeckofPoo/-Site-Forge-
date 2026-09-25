#!/usr/bin/env python3
"""ORI-035/036/037/032 — active-machine scope, MCR AUX, logical MCR, empty Area."""
from __future__ import annotations

import re
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_safety_model import _classify_device, build_safety_model  # noqa: E402
from fortna_transport_graph import _rebuild_workbook_areas, apply_graph_to_workbook  # noqa: E402


MAIN_JS = ROOT / "desktop" / "main.js"
SAFETY_JS = ROOT / "dashboard" / "safety-build.js"


class TestOri035NoOrnccp2Fallback(unittest.TestCase):
    def test_main_js_has_no_ornccp2_default(self) -> None:
        src = MAIN_JS.read_text(encoding="utf-8", errors="replace")
        self.assertNotIn("data?.machine || 'ORNCCP2'", src)
        self.assertNotIn('data?.machine || "ORNCCP2"', src)
        self.assertIn("ACTIVE_MACHINE_REQUIRED", src)

    def test_safety_build_passes_machine(self) -> None:
        src = SAFETY_JS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("buildSafetyModel({ machine: activeMachine })", src)
        self.assertNotIn("buildSafetyModel({})", src)

    def test_python_cli_requires_machine(self) -> None:
        src = (ROOT / "tools" / "scripts" / "fortna_safety_model.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertNotIn('default="ORNCCP2"', src)
        self.assertIn("required=True", src)
        self.assertIn("ACTIVE_MACHINE_REQUIRED", src)


class TestOri036McrAuxPlainForm(unittest.TestCase):
    def test_js_helper_matches_plain_aux(self) -> None:
        src = SAFETY_JS.read_text(encoding="utf-8", errors="replace")
        # Extract isMcrAuxFeedback body and evaluate key patterns via Node-less regex mirror
        self.assertIn(r"/^\d+MCR\d*_?AUX$/i", src)
        # Prove plain 1MCR1_AUX matches the grammar we ship
        self.assertTrue(re.match(r"^\d+MCR\d*_?AUX$", "1MCR1_AUX", re.I))
        self.assertTrue(re.match(r"^\d+MCR\d*_?AUX$", "1MCR1AUX", re.I))
        self.assertTrue(re.match(r"^T_\d*MCR\d*_?AUX$", "T_1MCR1_AUX", re.I))
        self.assertTrue(re.match(r"^CP\d+_MCR\d*_?AUX$", "CP1_MCR1_AUX", re.I))


class TestOri037LogicalMcrRejected(unittest.TestCase):
    def test_mem_fire_drop_mcr_not_device(self) -> None:
        self.assertEqual(_classify_device("MEM_FIRE_DROP_MCR"), "")
        self.assertEqual(_classify_device("FIRE_DROP_MCR"), "")
        self.assertEqual(_classify_device("SOME_MCR_FLAG"), "")

    def test_legitimate_mcr_still_classifies(self) -> None:
        self.assertEqual(_classify_device("1MCR1"), "MCR")
        self.assertEqual(_classify_device("T_1MCR1"), "MCR")
        self.assertEqual(_classify_device("1MCR1_AUX"), "MCR")
        self.assertEqual(_classify_device("CP1_MCR1_AUX"), "MCR")
        self.assertEqual(_classify_device("MCR1"), "MCR")

    def test_js_classify_rejects_logical(self) -> None:
        src = SAFETY_JS.read_text(encoding="utf-8", errors="replace")
        # Loose substring pattern must be gone
        self.assertNotIn("/(?:^|_)MCR\\d*/.test(u)", src)
        self.assertIn("ORI-037", src)


class TestOri032EmptyEngineerAreaSurvives(unittest.TestCase):
    def test_rebuild_preserves_empty_engineer_area(self) -> None:
        wb = {
            "conveyors": [
                {"conveyor": "P100", "main_area": "Busy_Area", "include": True, "safety_zone": "Busy_ESZone1"},
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
        }
        _rebuild_workbook_areas(wb)
        names = {a["name"] for a in wb["areas"]}
        self.assertIn("Busy_Area", names)
        self.assertIn("Empty_Eng_Area", names)
        empty = next(a for a in wb["areas"] if a["name"] == "Empty_Eng_Area")
        self.assertEqual(empty.get("conveyor_count"), 0)

    def test_apply_graph_keeps_empty_area_and_zone_ref(self) -> None:
        wb = {"conveyors": [], "areas": [], "options": {}, "merges_2to1": []}
        graph = {
            "areas": [
                {
                    "id": "a1",
                    "name": "Staging_Area",
                    "isDefault": False,
                    "nodes": [],
                    "wires": [],
                    "defaultSafetyZone": "Staging_ESZone1",
                }
            ],
            "safetyZones": [
                {
                    "source_id": "szone_staging",
                    "name": "Staging_ESZone1",
                    "engineering_name": "Staging_ESZone1",
                    "areaRef": "Staging_Area",
                    "members": [],
                    "engineerEdited": True,
                    "createdBy": "engineer",
                    "provenance": "ENGINEER_CREATED",
                }
            ],
            # apply_graph_to_workbook reads safetyBuild.zones for membership seeds
            "safetyBuild": {
                "source": "transport_engineer",
                "zones": [
                    {
                        "source_id": "szone_staging",
                        "name": "Staging_ESZone1",
                        "engineering_name": "Staging_ESZone1",
                        "areaRef": "Staging_Area",
                        "area": "Staging_Area",
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
        self.assertIn("Staging_Area", names)
        zones = (result["workbook"].get("safety_build") or {}).get("zones") or []
        self.assertTrue(zones)
        z = next(
            (x for x in zones if "Staging" in str(x.get("name") or x.get("engineering_name") or "")),
            zones[0],
        )
        area_ref = str(z.get("areaRef") or z.get("area") or "")
        self.assertEqual(area_ref, "Staging_Area")
        # No dangling: areaRef resolves to an existing workbook area
        self.assertIn(area_ref, names)


class TestMachineIsolationSynthetic(unittest.TestCase):
    """Two synthetic machines must not leak inventory into each other."""

    def test_classify_isolation_concept(self) -> None:
        from fortna_safety_inventory_scope import (
            LOCAL_PHYSICAL,
            UNRELATED_FOREIGN,
            classify_safety_device_scope,
            partition_safety_inventory,
        )

        devices = [
            {"name": "1ES1", "machine": "MACHINE_A", "physicalEndpoint": "1.1", "kind": "ESTOP"},
            {"name": "1ESLS1", "machine": "MACHINE_A", "physicalEndpoint": "1.2", "kind": "ESLS"},
            {"name": "1ESR1", "machine": "MACHINE_A", "physicalEndpoint": "1.3", "kind": "ESR"},
            {"name": "1MCR1", "machine": "MACHINE_A", "physicalEndpoint": "1.4", "kind": "MCR"},
            {"name": "7ES1", "machine": "MACHINE_B", "physicalEndpoint": "7.1", "kind": "ESTOP"},
            {"name": "7ESLS1", "machine": "MACHINE_B", "physicalEndpoint": "7.2", "kind": "ESLS"},
            {"name": "7ESR1", "machine": "MACHINE_B", "physicalEndpoint": "7.3", "kind": "ESR"},
            {"name": "7MCR1", "machine": "MACHINE_B", "physicalEndpoint": "7.4", "kind": "MCR"},
        ]
        part_a = partition_safety_inventory(devices, active_machine="MACHINE_A")
        names_a = {d["name"] for d in part_a["assignable"]}
        self.assertEqual(names_a, {"1ES1", "1ESLS1", "1ESR1", "1MCR1"})
        self.assertTrue(all(not n.startswith("7") for n in names_a))
        self.assertEqual(part_a["counts"][UNRELATED_FOREIGN], 4)

        part_b = partition_safety_inventory(devices, active_machine="MACHINE_B")
        names_b = {d["name"] for d in part_b["assignable"]}
        self.assertEqual(names_b, {"7ES1", "7ESLS1", "7ESR1", "7MCR1"})
        self.assertTrue(all(not n.startswith("1") for n in names_b))

        # A -> B switch: inventory becomes B only
        self.assertEqual(names_b & names_a, set())
        # B -> A switch: back to A only
        part_a2 = partition_safety_inventory(devices, active_machine="MACHINE_A")
        self.assertEqual({d["name"] for d in part_a2["assignable"]}, names_a)

        self.assertEqual(
            classify_safety_device_scope(
                {"name": "1ES1", "machine": "MACHINE_A"},
                active_machine="MACHINE_B",
            ),
            UNRELATED_FOREIGN,
        )
        self.assertEqual(
            classify_safety_device_scope(
                {"name": "1ES1", "machine": "MACHINE_A"},
                active_machine="MACHINE_A",
            ),
            LOCAL_PHYSICAL,
        )

    def test_missing_machine_handler_fails_visible(self) -> None:
        src = MAIN_JS.read_text(encoding="utf-8", errors="replace")
        # Production must refuse empty machine — no silent inventory
        self.assertIn("ACTIVE_MACHINE_REQUIRED", src)
        self.assertNotIn("|| 'ORNCCP2'", src)
        self.assertNotIn('|| "ORNCCP2"', src)
        # Per-machine cache path prevents A/B overwrite
        self.assertIn("safety_model_${safeMachine}.json", src)


class TestOri032ExplicitAreaDeleteClearsRef(unittest.TestCase):
    def test_js_delete_area_clears_dangling_arearef(self) -> None:
        src = (ROOT / "dashboard" / "transport-build.js").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("ORI-032", src)
        self.assertIn("clearedRefs", src)
        self.assertIn("never leave SafetyZone.areaRef pointing", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)

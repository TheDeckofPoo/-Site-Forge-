#!/usr/bin/env python3
"""Day-1 critical closeout #2 — ORI-072 crash + ORI-045 durable engineer identity.

Classifications: UNIT | INTEGRATION | BUILD_PATH_E2E | REAL_TAR_DERIVED | NODE
"""
from __future__ import annotations

import copy
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_safety_assignment_gate import (  # noqa: E402
    _is_default_zone,
    _is_engineer_zone,
    explicit_engineer_assigned_members,
    validate_engineer_assigned_safety_members,
)
from fortna_transport_graph import apply_graph_to_workbook  # noqa: E402

AUTOGEN = ROOT / "tools" / "scripts" / "fortna_autogen.py"
JS = ROOT / "dashboard" / "safety-build.js"
ULTA = ROOT / "tools" / "diagnostics" / "_real_runs" / "ULTAPICK" / "RUN"
TOPB = ROOT / "workspace" / "_topb_et_run" / "RUN"


class TestOri072ReportLifetime(unittest.TestCase):
    """BUILD_PATH_E2E — PD-0002 Default reviews must not crash on unbound report."""

    def test_pd0002_does_not_write_report_before_construction(self) -> None:
        src = AUTOGEN.read_text(encoding="utf-8", errors="replace")
        # Must collect into local list before report exists
        self.assertIn("_pd0002_default_mcr_reviews", src)
        self.assertIn('report["pd0002_default_mcr_reviews"]', src)
        # Must NOT call report.setdefault before report = {
        pre, _, post = src.partition("\n    report = {")
        self.assertIn("_pd0002_default_mcr_reviews.append", pre)
        self.assertNotIn("report.setdefault(\"pd0002_default_mcr_reviews\"", pre)
        self.assertIn('report["pd0002_default_mcr_reviews"]', post)

    def test_default_only_mcr_not_engineer_intent(self) -> None:
        intent = explicit_engineer_assigned_members(
            [
                {
                    "name": "Default Safety",
                    "members": ["T_1MCR1", "T_23MCR1", "T_2MCR1"],
                    "isDefault": True,
                    "defaultSafety": True,
                },
                {
                    "name": "Pack_ESZ",
                    "members": ["ESLS610L"],
                    "zoneOrigin": "ENGINEER",
                    "engineerEdited": True,
                    "membersOrigin": "ENGINEER_ASSIGNED",
                    "source_id": "szone_1",
                },
            ]
        )
        devices = [i["device"] for i in intent]
        self.assertEqual(devices, ["ESLS610L"])
        self.assertNotIn("T_1MCR1", devices)

    def test_explicit_mcr_missing_writer_still_blocks(self) -> None:
        """Negative control — engineer-assigned MCR without writer still fails."""
        from fortna_safety_model import build_safety_model

        if not TOPB.is_dir():
            self.skipTest("TOPB RUN missing")
        model = build_safety_model(run_dir=TOPB, machine="TOPB-ET")
        devs = list(model.get("safetyDevices") or model.get("devices") or [])
        gate = validate_engineer_assigned_safety_members(
            engineer_zones=[
                {
                    "name": "Z",
                    "members": ["6MCR1"],
                    "zoneOrigin": "ENGINEER",
                    "engineerEdited": True,
                    "membersOrigin": "ENGINEER_ASSIGNED",
                    "source_id": "szone_neg",
                }
            ],
            safety_devices=devs,
            written_tags=set(),  # no writers
        )
        self.assertTrue(gate["blocked"])
        self.assertEqual(gate["violations"][0]["reason"], "NO_IO_MAP_WRITER")

    @unittest.skipUnless(ULTA.is_dir(), "ULTAPICK RUN missing")
    def test_ultapick_build_l5x_no_crash_default_mcr(self) -> None:
        """REAL_TAR_DERIVED / BUILD_PATH_E2E — exercise real build_l5x path."""
        from fortna_autogen import AutogenInput, build_l5x
        from fortna_safety_model import build_safety_model

        lib = ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X"
        if not lib.is_file():
            self.skipTest("library missing")

        model = build_safety_model(run_dir=ULTA, machine="ULTAPICK")
        devs = list(model.get("safetyDevices") or model.get("devices") or [])
        # Minimal input: engineer assigns ESLS610L only; Default MCRs stay unassigned
        inp = AutogenInput(
            machine="ULTAPICK",
            project_name="ULTAPICK",
            run_dir=str(ULTA),
            areas=["Main_Area"],
            conveyors=[],
            include_io_map=True,
            safety_build={
                "zones": [
                    {
                        "name": "Pick_ESZ",
                        "source_id": "szone_pick1",
                        "zoneOrigin": "ENGINEER",
                        "engineerEdited": True,
                        "createdBy": "engineer",
                        "membersOrigin": "ENGINEER_ASSIGNED",
                        "members": ["ESLS610L"],
                        "areaRef": "",
                        "areaUnlinked": True,
                    }
                ],
                "unassignedDevices": ["T_1MCR1", "T_2MCR1", "T_3MCR1", "T_4MCR1", "T_23MCR1"],
            },
            safety_zone_members=[
                {
                    "name": "Pick_ESZ",
                    "source_id": "szone_pick1",
                    "zoneOrigin": "ENGINEER",
                    "engineerEdited": True,
                    "createdBy": "engineer",
                    "membersOrigin": "ENGINEER_ASSIGNED",
                    "members": ["ESLS610L"],
                    "areaRef": "",
                    "areaUnlinked": True,
                }
            ],
        )
        try:
            l5x, report = build_l5x(inp, lib)
        except UnboundLocalError as e:
            self.fail(f"ORI-072 crash still present: {e}")
        self.assertIsInstance(report, dict)
        detail = str(report.get("error") or "") + str(report.get("build_failed") or "")
        self.assertNotIn("UnboundLocalError", detail)
        self.assertTrue(isinstance(l5x, str) and len(l5x) > 100)
        # Default-only MCR reviews are OK; must not be engineer-intent hard fails for T_1MCR1 alone
        blockers = " ".join(str(x) for x in (report.get("studio_blockers") or []))
        # If PD-0002 fires, it must not be solely for Default inventory without engineer MCR intent
        if "PD-0002" in blockers and "T_1MCR1" in blockers:
            self.assertIn("engineer-assigned", blockers.lower())
        # Reviews list may record Default MCRs
        _ = report.get("pd0002_default_mcr_reviews") or []


class TestOri045DurableEngineerIdentity(unittest.TestCase):
    """INTEGRATION — Area delete → Transport Apply → persist → reload."""

    def test_name_containing_default_not_discarded(self) -> None:
        z = {
            "name": "Default Packaging EStops",
            "engineering_name": "Default Packaging EStops",
            "source_id": "szone_pack1",
            "zoneOrigin": "ENGINEER",
            "engineerEdited": True,
            "createdBy": "engineer",
            "members": ["1ES", "2ES"],
            "membersOrigin": "ENGINEER_ASSIGNED",
        }
        self.assertFalse(_is_default_zone(z))
        self.assertTrue(_is_engineer_zone(z))
        intent = explicit_engineer_assigned_members([z])
        self.assertEqual([i["device"] for i in intent], ["1ES", "2ES"])

    def test_unassigned_substring_ordinary_name(self) -> None:
        z = {
            "name": "Unassigned Spares Review Zone",
            "source_id": "szone_u1",
            "zoneOrigin": "ENGINEER",
            "engineerEdited": True,
            "createdBy": "engineer",
            "members": ["3ES"],
        }
        self.assertFalse(_is_default_zone(z))
        self.assertTrue(_is_engineer_zone(z))

    def test_lifecycle_transport_apply_preserves_zone(self) -> None:
        wb = {
            "areas": [{"name": "Test1_Area"}],
            "conveyors": [],
            "safety_build": {
                "appliedAt": "t",
                "source": "safety_build",
                "zones": [
                    {
                        "source_id": "szone_orl1",
                        "name": "Warden_ESZ",
                        "engineering_name": "Warden_ESZ",
                        "zoneOrigin": "ENGINEER",
                        "areaRef": "",
                        "areaUnlinked": True,
                        "members": ["1ES", "2ES", "3ES", "4ES"],
                        "membersOrigin": "ENGINEER_ASSIGNED",
                        "engineerEdited": True,
                        "createdBy": "engineer",
                        "provenance": "ENGINEER_CREATED",
                    }
                ],
            },
            "options": {"areas": ["Test1_Area"]},
            "merges_2to1": [],
        }
        graph = {
            "areas": [{"name": "Default Area", "nodes": [], "wires": []}],
            "deletedAreas": ["Test1_Area"],
            "safetyBuild": {"source": "transport_engineer", "zones": []},
        }
        result = apply_graph_to_workbook(graph, copy.deepcopy(wb))
        zones = (result["workbook"].get("safety_build") or {}).get("zones") or []
        self.assertEqual(len(zones), 1)
        z = zones[0]
        self.assertEqual(z.get("zoneOrigin"), "ENGINEER")
        self.assertTrue(z.get("areaUnlinked"))
        self.assertEqual(len(z.get("members") or []), 4)
        self.assertEqual(z.get("areaRef") or "", "")

        # Recreate Area — must not auto-relink
        graph2 = {
            "areas": [{"name": "Test1_Area", "nodes": [], "wires": []}],
            "deletedAreas": [],
            "safetyBuild": {
                "source": "transport_engineer",
                "zones": [
                    {
                        "name": "Warden_ESZ",
                        "engineering_name": "Warden_ESZ",
                        "source_id": "szone_orl1",
                        "area": "Test1_Area",
                        "areaRef": "Test1_Area",
                        "members": [],
                    }
                ],
            },
        }
        result2 = apply_graph_to_workbook(graph2, copy.deepcopy(result["workbook"]))
        zones2 = (result2["workbook"].get("safety_build") or {}).get("zones") or []
        self.assertEqual(len(zones2), 1)
        z2 = zones2[0]
        self.assertTrue(z2.get("areaUnlinked"))
        self.assertEqual(z2.get("areaRef") or "", "")
        self.assertEqual(len(z2.get("members") or []), 4)
        self.assertEqual(z2.get("zoneOrigin"), "ENGINEER")

    def test_js_canonical_counts_and_zone_origin(self) -> None:
        src = JS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("function isEngineerSafetyZone", src)
        self.assertIn("function canonicalEngineerZones", src)
        self.assertIn("function recomputeModelCounts", src)
        self.assertIn("zoneOrigin: 'ENGINEER'", src)
        self.assertIn("recomputeModelCounts(state.model)", src)
        # Tiles use canonical collection
        self.assertIn("const engZones = canonicalEngineerZones(state.model)", src)
        self.assertIn("set('sb-count-zones', engZoneN)", src)


class TestPreservePasses(unittest.TestCase):
    @unittest.skipUnless(ULTA.is_dir(), "ULTAPICK missing")
    def test_ultapick_panel_local(self) -> None:
        from fortna_physical_word_resolver import PhysicalWordResolver

        r = PhysicalWordResolver(ULTA, "ULTAPICK")
        self.assertIn("CP23", (r.resolve(2705, 12) or {}).get("channel") or "")
        self.assertIn("CP2", (r.resolve(210, 2) or {}).get("channel") or "")

    @unittest.skipUnless(TOPB.is_dir(), "TOPB missing")
    def test_topb_aux_writers(self) -> None:
        from fortna_es_compiler import build_device_evidence_index, safety_operand_has_writer
        from fortna_safety_model import build_safety_model

        m = build_safety_model(run_dir=TOPB, machine="TOPB-ET")
        ev = build_device_evidence_index(m.get("safetyDevices") or m.get("devices") or [])
        self.assertTrue(
            safety_operand_has_writer(
                "T_6MCR1", written_tags={"T_6MCR1_AUX"}, device_evidence=ev
            )
        )


if __name__ == "__main__":
    unittest.main()

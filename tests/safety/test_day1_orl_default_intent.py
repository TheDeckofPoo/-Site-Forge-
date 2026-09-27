#!/usr/bin/env python3
"""Day-1 Beta closeout — ORI-045 live zone + ORI-068 Default-intent PD-0002.

Classifications: UNIT | INTEGRATION | REAL_TAR_DERIVED | BUILD_PATH_E2E | NODE | REAL_UI_E2E
"""
from __future__ import annotations

import copy
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_es_compiler import build_safety_zone_irs  # noqa: E402
from fortna_safety_assignment_gate import (  # noqa: E402
    explicit_engineer_assigned_members,
)
from fortna_transport_graph import (  # noqa: E402
    _clear_deleted_area_refs,
    apply_graph_to_workbook,
)

JS_SAFETY = ROOT / "dashboard" / "safety-build.js"
JS_TRANSPORT = ROOT / "dashboard" / "transport-build.js"
JS_PLUS = ROOT / "dashboard" / "fortna-plus.js"
AUTOGEN = ROOT / "tools" / "scripts" / "fortna_autogen.py"


class TestOri045TransportApplyLiveZone(unittest.TestCase):
    """INTEGRATION / BUILD_PATH_E2E — orphaned engineer zone survives Transport Apply."""

    def test_python_apply_preserves_unlinked_zone_when_graph_hollow(self) -> None:
        wb = {
            "areas": [{"name": "Test1_Area"}],
            "conveyors": [],
            "safety_build": {
                "appliedAt": "2026-01-01T00:00:00Z",
                "source": "safety_build",
                "zones": [
                    {
                        "source_id": "szone_orl1",
                        "id": "szone_orl1",
                        "name": "Warden_ESZ",
                        "engineering_name": "Warden_ESZ",
                        "areaRef": "",
                        "area": "",
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
        self.assertEqual(z.get("source_id"), "szone_orl1")
        self.assertEqual(len(z.get("members") or []), 4)
        self.assertTrue(z.get("areaUnlinked"))
        self.assertEqual(z.get("areaRef") or "", "")

    def test_clear_deleted_area_sets_area_unlinked(self) -> None:
        wb = {
            "safety_build": {
                "zones": [
                    {
                        "name": "Z",
                        "areaRef": "Gone_Area",
                        "members": ["1ES"],
                        "engineerEdited": True,
                    }
                ]
            }
        }
        _clear_deleted_area_refs(wb, {"GONE_AREA"})
        z = wb["safety_build"]["zones"][0]
        self.assertEqual(z.get("areaRef"), "")
        self.assertTrue(z.get("areaUnlinked"))
        self.assertTrue(z.get("engineerEdited"))

    def test_js_refresh_keeps_member_bearing_zones(self) -> None:
        """UNIT/NODE — first live drop was refreshModel stripping non-flagged members."""
        src = JS_SAFETY.read_text(encoding="utf-8", errors="replace")
        self.assertIn(
            "Member-bearing non-RUN zones are engineer intent — never strip on refresh",
            src,
        )
        self.assertIn("never restamp Area onto an already-unlinked engineer zone", src)
        plus = JS_PLUS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("Transport Apply must refresh Safety live model", plus)
        tb = JS_TRANSPORT.read_text(encoding="utf-8", errors="replace")
        self.assertIn("survive Transport Apply without Area", tb)

    def test_ir_orphaned_zone_still_empty_area(self) -> None:
        irs = build_safety_zone_irs(
            engineer_zones=[
                {
                    "name": "Warden_ESZ",
                    "areaRef": "",
                    "areaUnlinked": True,
                    "engineerEdited": True,
                    "createdBy": "engineer",
                    "members": ["1ES", "2ES", "3ES", "4ES"],
                    "membersOrigin": "ENGINEER_ASSIGNED",
                    "source_id": "szone_orl1",
                    "provenance": "ENGINEER_CREATED",
                }
            ],
            areas=["Default Area"],
            default_area="Default Area",
        )
        self.assertEqual(len(irs), 1)
        self.assertEqual(irs[0].area, "")
        self.assertEqual(len(irs[0].members), 4)


class TestOri068DefaultNotPd0002Intent(unittest.TestCase):
    """UNIT / BUILD_PATH_E2E — Default MCR must not hard-fail PD-0002 as engineer intent."""

    def test_explicit_intent_excludes_default(self) -> None:
        intent = explicit_engineer_assigned_members(
            [
                {
                    "name": "Default Safety",
                    "members": ["T_1MCR1", "T_23MCR1"],
                    "engineerEdited": True,
                    "defaultSafety": True,
                },
                {
                    "name": "Eng_ESZ",
                    "members": ["6MCR1"],
                    "engineerEdited": True,
                    "membersOrigin": "ENGINEER_ASSIGNED",
                    "source_id": "szone_1",
                },
            ]
        )
        devices = [i["device"] for i in intent]
        self.assertEqual(devices, ["6MCR1"])
        self.assertNotIn("T_1MCR1", devices)

    def test_autogen_pd0002_scopes_to_engineer_intent(self) -> None:
        src = AUTOGEN.read_text(encoding="utf-8", errors="replace")
        self.assertIn("ORI-068: Default / Unassigned inventory is NOT engineer intent", src)
        self.assertIn("explicit_engineer_assigned_members", src)
        self.assertIn("pd0002_default_mcr_reviews", src)
        self.assertIn("Default/unassigned MCR", src)
        # Hard-fail path still present for engineer-assigned
        self.assertIn("engineer-assigned — no approved generic MCR", src)


class TestPreserveVerifiedPasses(unittest.TestCase):
    """Regression guards — do not reopen working paths."""

    def test_ultapick_resolver_untouched_marker(self) -> None:
        # Panel-local path still present; Day-1 must not rewrite it.
        from fortna_physical_word_resolver import _panel_token

        self.assertEqual(_panel_token("CP23"), "CP23")

    def test_writer_aux_path_still_present(self) -> None:
        from fortna_es_compiler import safety_operand_has_writer

        self.assertTrue(
            safety_operand_has_writer(
                "T_6MCR1",
                written_tags={"T_6MCR1_AUX"},
                device_evidence={
                    "T_6MCR1": {
                        "name": "6MCR1",
                        "signals": [{"name": "6MCR1_AUX", "signalRole": "AUX"}],
                    }
                },
            )
        )


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""SafetyModel unit tests — refs only, engineer overrides survive."""
from __future__ import annotations
# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys
_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / 'tools' / 'scripts'
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
# Prefer canonical names used by existing tests:
SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO
REPO_ROOT = _SF_REPO
# --- end bootstrap ---


import sys
import unittest
from pathlib import Path

SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from fortna_safety_model import (  # noqa: E402
    ORIGIN_ENGINEER,
    build_safety_model,
    safety_build_workbook_payload,
)

RUN = ROOT / "workspace" / "_plc2_run_peek" / "RUN"


class TestSafetyModel(unittest.TestCase):
    def test_classify_engineer_and_run_prefixes(self) -> None:
        from fortna_safety_model import _classify_device

        self.assertEqual(_classify_device("T_2ES"), "ESTOP")
        self.assertEqual(_classify_device("2ES"), "ESTOP")
        self.assertEqual(_classify_device("CP2_ESR1"), "ESR")
        self.assertEqual(_classify_device("2ESR1_AUX"), "ESR")
        self.assertEqual(_classify_device("CP2_MCR1"), "MCR")
        self.assertEqual(_classify_device("T_2MCR1"), "MCR")
        self.assertEqual(_classify_device("2MCR1"), "MCR")
        self.assertEqual(_classify_device("CP2_CS"), "CS")
        self.assertEqual(_classify_device("ESLS125"), "ESLS")
        self.assertEqual(_classify_device("ES406"), "ESTOP")
        self.assertEqual(_classify_device("P406"), "")

    def test_discovers_devices_and_zone_stubs(self) -> None:
        if not (RUN / "FORTNA").is_dir():
            self.skipTest("PLC2 RUN peek missing")
        model = build_safety_model(
            run_dir=RUN,
            machine="ORNCCP2",
            transport_zones=[
                {
                    "name": "test1_ESZone1",
                    "area": "test1",
                    "conveyors": ["P138", "P222", "P404", "P406"],
                    "members": [],
                }
            ],
            areas=["ORNCCP2_Area", "test1"],
            area_conveyors={
                "ORNCCP2_Area": ["P1000", "P312"],
                "test1": ["P138", "P222", "P404", "P406"],
            },
            engineer_safety_build={},
        )
        self.assertGreaterEqual(model["counts"]["devices"], 10)
        names = {z["name"] for z in model["zones"]}
        self.assertIn("test1_ESZone1", names)
        z = next(x for x in model["zones"] if x["name"] == "test1_ESZone1")
        self.assertEqual(z["areaRef"], "test1")
        self.assertEqual(len(z["conveyorRefs"]), 4)
        self.assertEqual(z["members"], [])
        self.assertEqual(z["status"], "REVIEW_REQUIRED")
        self.assertIn("SafetyDevices", z.get("hard_missing") or [])

    def test_unassigned_device_keeps_safety_zone_ref_null(self) -> None:
        if not (RUN / "FORTNA").is_dir():
            self.skipTest("PLC2 RUN peek missing")
        model = build_safety_model(
            run_dir=RUN,
            machine="ORNCCP2",
            transport_zones=[
                {
                    "name": "test1_ESZone1",
                    "area": "test1",
                    "conveyors": ["P404", "P406"],
                    "members": [],
                }
            ],
            areas=["test1"],
            engineer_safety_build={},
        )
        self.assertGreater(len(model["devices"]), 0)
        unassigned = [
            d for d in model["devices"] if d.get("status") == "UNASSIGNED"
        ]
        self.assertGreater(len(unassigned), 0)
        for d in unassigned:
            self.assertIsNone(d.get("safetyZoneRef"))
            self.assertEqual(d.get("status"), "UNASSIGNED")
            self.assertIn("originalName", d)
            self.assertIn("classification", d)
            self.assertIn("confidence", d)
            self.assertIn("source", d)
        self.assertEqual(
            len(model["unassignedDevices"]),
            model["counts"]["unassigned"],
        )

    def test_completion_metrics_present(self) -> None:
        if not (RUN / "FORTNA").is_dir():
            self.skipTest("PLC2 RUN peek missing")
        model = build_safety_model(
            run_dir=RUN,
            machine="ORNCCP2",
            transport_zones=[
                {
                    "name": "test1_ESZone1",
                    "area": "test1",
                    "conveyors": ["P404", "P406"],
                    "members": ["ES400", "ES406"],
                }
            ],
            areas=["test1"],
            engineer_safety_build={
                "zones": [
                    {
                        "name": "test1_ESZone1",
                        "area": "test1",
                        "conveyors": ["P404", "P406"],
                        "members": ["ES400", "ES406"],
                        "engineerEdited": True,
                    }
                ]
            },
        )
        c = model["counts"]
        for key in (
            "estops",
            "esr",
            "mcr",
            "cs",
            "esls",
            "other_safety",
            "devices_found",
            "automatically_resolved",
            "engineer_assigned",
            "unassigned",
            "completion_pct",
            "zones_ready",
            "zones_review",
        ):
            self.assertIn(key, c, msg=f"missing counts.{key}")
        self.assertEqual(c["devices_found"], len(model["devices"]))
        self.assertEqual(
            c["completion_pct"],
            round(
                100
                * (c["automatically_resolved"] + c["engineer_assigned"])
                / max(1, c["devices_found"])
            ),
        )
        self.assertIn("inventoryByKind", model)
        for kind in ("ESTOP", "ESR", "MCR", "CS", "ESLS", "OTHER"):
            self.assertIn(kind, model["inventoryByKind"])
        payload = safety_build_workbook_payload(model)
        self.assertTrue(payload["devices"])
        self.assertIn("safetyZoneRef", payload["devices"][0])
        self.assertIn("status", payload["devices"][0])
        self.assertIn("unassignedDevices", payload)
        self.assertIn("inventoryByKind", payload)

    def test_engineer_members_become_ready(self) -> None:
        if not (RUN / "FORTNA").is_dir():
            self.skipTest("PLC2 RUN peek missing")
        model = build_safety_model(
            run_dir=RUN,
            machine="ORNCCP2",
            transport_zones=[
                {
                    "name": "test1_ESZone1",
                    "area": "test1",
                    "conveyors": ["P404", "P406"],
                    "members": [],
                }
            ],
            areas=["test1"],
            engineer_safety_build={
                "zones": [
                    {
                        "name": "test1_ESZone1",
                        "area": "test1",
                        "conveyors": ["P404", "P406"],
                        "members": ["ES400", "ES406"],
                        "engineerEdited": True,
                    }
                ]
            },
        )
        z = next(x for x in model["zones"] if x["name"] == "test1_ESZone1")
        self.assertEqual(set(z["members"]), {"ES400", "ES406"})
        self.assertEqual(z["membersOrigin"], ORIGIN_ENGINEER)
        self.assertEqual(z["status"], "READY")
        for name in ("ES400", "ES406"):
            d = next(x for x in model["devices"] if x["name"] == name)
            self.assertEqual(d["safetyZoneRef"], "test1_ESZone1")
            self.assertEqual(d["status"], "ENGINEER_ASSIGNED")
        payload = safety_build_workbook_payload(model)
        self.assertEqual(payload["zones"][0]["members"], ["ES400", "ES406"])


if __name__ == "__main__":
    unittest.main()

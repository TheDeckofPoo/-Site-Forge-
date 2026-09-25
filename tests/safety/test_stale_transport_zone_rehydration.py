#!/usr/bin/env python3
"""Stale Transport Safety-zone rehydration — Area→ESZone1 must not become RUN.

Resurrection source (ORNCCP2_ESZone1 after restart):
  workbook conveyor.safety_zone / Transport seed
    → fortna_safety_model promoted every non-engineer Transport seed to RUN_DISCOVERED
    → ingestRunDiscoveredZones → AS.runSafetyZones → Safety UI as RUN / REVIEW / 0 members

Tests A–E from the addendum.
"""
from __future__ import annotations
# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys
_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
# --- end bootstrap ---

import unittest

from fortna_safety_model import (
    PROVENANCE_AUTO_DEFAULT,
    PROVENANCE_ENGINEER_CREATED,
    PROVENANCE_RUN_DISCOVERED,
    _is_area_derived_default_shell,
    _seed_has_genuine_run_evidence,
    build_safety_model,
    classify_zone_provenance,
    reconcile_safety_zones,
    safety_build_workbook_payload,
)


class TestAreaDerivedHelpers(unittest.TestCase):
    def test_ornccp2_area_to_eszone1_is_area_derived(self) -> None:
        self.assertTrue(
            _is_area_derived_default_shell("ORNCCP2_ESZone1", "ORNCCP2_Area", [])
        )

    def test_trash_under_module_is_not_area_derived(self) -> None:
        self.assertFalse(
            _is_area_derived_default_shell("Trash_ESZone1", "ModuleB_Area", [])
        )

    def test_transport_seed_alone_is_not_genuine_run(self) -> None:
        self.assertFalse(
            _seed_has_genuine_run_evidence(
                {
                    "name": "ORNCCP2_ESZone1",
                    "members": [],
                    "runDiscovered": True,
                    "evidence": [{"kind": "transport_zone_seed"}],
                }
            )
        )

    def test_proven_members_are_genuine_run(self) -> None:
        self.assertTrue(
            _seed_has_genuine_run_evidence(
                {
                    "name": "ModuleB_ESZone1",
                    "members": ["ES422"],
                    "membersOrigin": "AUTO_RUN_PROVEN",
                    "membership_confidence": "CONFIRMED",
                    "evidence": [{"kind": "estop_table"}],
                }
            )
        )


class TestA_EngineerDurability(unittest.TestCase):
    """Same project: engineer Trash_ESZone1 + members survive Apply/reopen."""

    def test_engineer_zone_survives_reopen(self) -> None:
        model = build_safety_model(
            run_dir=None,
            machine="ORNCCP2",
            transport_zones=[],
            areas=["ModuleB_Area"],
            area_conveyors={"ModuleB_Area": ["P312"]},
            engineer_safety_build={
                "zones": [
                    {
                        "source_id": "szone_trash",
                        "engineering_name": "Trash_ESZone1",
                        "areaRef": "ModuleB_Area",
                        "members": ["ES406", "2MCR1_AUX"],
                        "membersOrigin": "ENGINEER_ASSIGNED",
                        "engineerEdited": True,
                        "createdBy": "engineer",
                        "provenance": PROVENANCE_ENGINEER_CREATED,
                    }
                ]
            },
        )
        payload = safety_build_workbook_payload(model)
        trash = next(z for z in payload["zones"] if z["engineering_name"] == "Trash_ESZone1")
        self.assertEqual(set(trash["members"]), {"ES406", "2MCR1_AUX"})
        self.assertEqual(trash["provenance"], PROVENANCE_ENGINEER_CREATED)

        reopened = build_safety_model(
            run_dir=None,
            machine="ORNCCP2",
            transport_zones=[],
            areas=["ModuleB_Area"],
            engineer_safety_build=payload,
        )
        by = {z.get("engineering_name") or z.get("name"): z for z in reopened["zones"]}
        self.assertIn("Trash_ESZone1", by)
        self.assertEqual(set(by["Trash_ESZone1"].get("members") or []), {"ES406", "2MCR1_AUX"})


class TestB_AutoDefaultNotRun(unittest.TestCase):
    """ORNCCP2_Area present, no proven/engineer zone → no operational RUN row."""

    def test_area_derived_transport_seed_not_run(self) -> None:
        model = build_safety_model(
            run_dir=None,
            machine="ORNCCP2",
            transport_zones=[
                {
                    "name": "ORNCCP2_ESZone1",
                    "source_id": "ORNCCP2_ESZone1",
                    "area": "ORNCCP2_Area",
                    "conveyors": ["P100"],
                    "members": [],
                }
            ],
            areas=["ORNCCP2_Area"],
            area_conveyors={"ORNCCP2_Area": ["P100"]},
            engineer_safety_build={"zones": []},
        )
        operational = [
            z
            for z in model["zones"]
            if str(z.get("name") or z.get("engineering_name") or "")
            not in {"Default Safety", "Unassigned Safety"}
            and not z.get("isDefault")
        ]
        names = {
            str(z.get("source_id") or z.get("name") or "")
            for z in operational
        }
        self.assertNotIn("ORNCCP2_ESZone1", names)
        # Must not appear in persist payload either
        payload = safety_build_workbook_payload(model)
        payload_names = {z.get("source_id") for z in payload["zones"]}
        self.assertNotIn("ORNCCP2_ESZone1", payload_names)

    def test_classify_demotes_false_run_stamp(self) -> None:
        prov = classify_zone_provenance(
            {
                "source_id": "ORNCCP2_ESZone1",
                "name": "ORNCCP2_ESZone1",
                "areaRef": "ORNCCP2_Area",
                "members": [],
                "runDiscovered": True,
                "provenance": PROVENANCE_RUN_DISCOVERED,
            },
            run_zone_ids=set(),
            conveyor_zone_refs={"ORNCCP2_ESZone1"},
            current_areas={"ORNCCP2_Area"},
        )
        self.assertEqual(prov, PROVENANCE_AUTO_DEFAULT)


class TestC_ProjectSwitch(unittest.TestCase):
    """Prior-project ORNCCP2 shells must not survive into a new project payload."""

    def test_reconcile_drops_foreign_area_shell(self) -> None:
        recon = reconcile_safety_zones(
            [
                {
                    "source_id": "ORNCCP2_ESZone1",
                    "name": "ORNCCP2_ESZone1",
                    "areaRef": "ORNCCP2_Area",
                    "members": [],
                    "runDiscovered": True,
                    "provenance": PROVENANCE_RUN_DISCOVERED,
                },
                {
                    "source_id": "szone_ac3",
                    "engineering_name": "ORINDYAC3_Staging",
                    "areaRef": "ORINDYAC3_Area",
                    "members": ["ES100"],
                    "engineerEdited": True,
                    "createdBy": "engineer",
                    "provenance": PROVENANCE_ENGINEER_CREATED,
                },
            ],
            run_zone_ids=set(),
            conveyor_zone_refs=set(),
            current_areas={"ORINDYAC3_Area"},  # new project areas only
        )
        after = {z.get("source_id") for z in recon["zones"]}
        self.assertNotIn("ORNCCP2_ESZone1", after)
        self.assertIn("szone_ac3", after)


class TestD_LegitimateCurrentRun(unittest.TestCase):
    """Genuine RUN evidence may still appear as RUN_DISCOVERED."""

    def test_proven_membership_stays_run(self) -> None:
        model = build_safety_model(
            run_dir=None,
            machine="ORNCCP2",
            transport_zones=[
                {
                    "name": "ModuleB_ESZone1",
                    "source_id": "ModuleB_ESZone1",
                    "area": "ModuleB_Area",
                    "conveyors": ["P312"],
                    "members": ["ES422"],
                    "membersOrigin": "AUTO_RUN_PROVEN",
                    "membership_confidence": "CONFIRMED",
                    "runDiscovered": True,
                    "provenance": PROVENANCE_RUN_DISCOVERED,
                    "evidence": [{"kind": "estop_table", "table": "EStop.asc"}],
                }
            ],
            areas=["ModuleB_Area"],
            area_conveyors={"ModuleB_Area": ["P312"]},
            engineer_safety_build={"zones": []},
        )
        by = {z.get("source_id") or z.get("name"): z for z in model["zones"]}
        self.assertIn("ModuleB_ESZone1", by)
        z = by["ModuleB_ESZone1"]
        self.assertTrue(z.get("runDiscovered"))
        self.assertEqual(
            z.get("provenance") or z.get("origin"),
            PROVENANCE_RUN_DISCOVERED,
        )
        self.assertIn("ES422", z.get("members") or [])


class TestE_ProvenanceBadge(unittest.TestCase):
    """RUN badge only with genuine RUN evidence — not Transport alone."""

    def test_transport_seed_evidence_is_not_run_badge(self) -> None:
        model = build_safety_model(
            run_dir=None,
            machine="ORNCCP2",
            transport_zones=[
                {
                    "name": "ORNCCP2_ESZone1",
                    "area": "ORNCCP2_Area",
                    "conveyors": ["P100"],
                    "members": [],
                    "evidence": [{"kind": "transport_zone_seed"}],
                }
            ],
            areas=["ORNCCP2_Area"],
            engineer_safety_build={"zones": []},
        )
        for z in model["zones"]:
            if "ORNCCP2_ESZone1" in str(z.get("source_id") or z.get("name") or ""):
                self.fail("Area-derived shell must not be an operational zone row")
            if z.get("runDiscovered") and not _seed_has_genuine_run_evidence(z):
                if z.get("isDefault") or z.get("name") in {"Default Safety"}:
                    continue
                self.fail(f"false RUN badge on {z.get('name')}: {z.get('provenance')}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

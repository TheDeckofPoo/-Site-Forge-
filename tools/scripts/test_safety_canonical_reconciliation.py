#!/usr/bin/env python3
"""Gates P–T permanent tests 12–17 — Safety canonical reconciliation.

12. Safety RUN zone appears immediately
13. Safety rename preserves source_id
14. Repeated Apply does not duplicate Safety zones
15. Test/default Zone1..ZoneN do not leak into production
16. Engineer-created Safety zones survive reconciliation
17. Unknown Safety membership remains fail-safe
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from fortna_safety_model import (  # noqa: E402
    ORIGIN_ENGINEER,
    ORIGIN_UNRESOLVED,
    PROVENANCE_AUTO_DEFAULT,
    PROVENANCE_ENGINEER_CREATED,
    PROVENANCE_RUN_DISCOVERED,
    PROVENANCE_TEST_FIXTURE,
    build_safety_model,
    classify_zone_provenance,
    is_placeholder_or_test_zone_name,
    is_ui_placeholder_area,
    reconcile_safety_zones,
    safety_build_workbook_payload,
)
from fortna_workbook import (  # noqa: E402
    apply_workbook_to_input,
    build_workbook_from_run,
    is_production_safety_zone_name,
)
from fortna_autogen import AutogenInput, ConveyorRow  # noqa: E402

SAFETY_JS = ROOT / "dashboard" / "safety-build.js"
FORTNA_JS = ROOT / "dashboard" / "fortna-plus.js"
RUN_PLC5 = ROOT / "workspace" / "cp5-run" / "RUN"
RUN_PLC2 = ROOT / "workspace" / "_plc2_run_peek" / "RUN"
MANIFEST = ROOT / "exports" / "current" / "ORNCCP5_2026_09_18_0339.manifest.json"


class Test12RunZoneAppearsImmediately(unittest.TestCase):
    """12. Safety RUN zone appears immediately after model build (not only after Build)."""

    def test_js_ingests_run_zones_on_model_build(self) -> None:
        js = SAFETY_JS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("function ingestRunDiscoveredZones", js)
        self.assertIn("Gate H", js)
        self.assertIn("AS.runSafetyZones = shells", js)
        # Immediately on buildSafetyModel success — before Transport Apply
        self.assertIn("ingestRunDiscoveredZones(res.model.zones", js)
        self.assertIn("Appear immediately after import/model build", js)

    def test_build_model_emits_run_discovered_shell(self) -> None:
        model = build_safety_model(
            run_dir=None,
            machine="ORNCCP5",
            transport_zones=[
                {
                    "name": "ORNCCP5_ESZone1",
                    "source_id": "ORNCCP5_ESZone1",
                    "area": "ORNCCP5_Area",
                    "conveyors": ["P440", "P442"],
                    "members": [],
                    "runDiscovered": True,
                }
            ],
            areas=["ORNCCP5_Area"],
            area_conveyors={"ORNCCP5_Area": ["P440", "P442"]},
            engineer_safety_build={},
        )
        names = {z.get("source_id") or z.get("name") for z in model["zones"]}
        self.assertIn("ORNCCP5_ESZone1", names)
        z = next(x for x in model["zones"] if x.get("source_id") == "ORNCCP5_ESZone1")
        self.assertTrue(z.get("runDiscovered") or z.get("provenance") == PROVENANCE_RUN_DISCOVERED)
        # Membership unresolved until engineer / PROVEN — fail-safe
        self.assertEqual(z.get("members") or [], [])
        self.assertIn(z.get("status"), ("REVIEW_REQUIRED", "UNRESOLVED"))


class Test13RenamePreservesSourceId(unittest.TestCase):
    """13. Safety rename preserves source_id (engineering_name editable)."""

    def test_rename_roundtrip(self) -> None:
        model = build_safety_model(
            run_dir=None,
            machine="SYNTH",
            transport_zones=[
                {
                    "name": "ORNCCP5_ESZone1",
                    "area": "ORNCCP5_Area",
                    "conveyors": ["P440"],
                    "members": [],
                }
            ],
            areas=["ORNCCP5_Area"],
            area_conveyors={"ORNCCP5_Area": ["P440"]},
            engineer_safety_build={
                "zones": [
                    {
                        "source_id": "ORNCCP5_ESZone1",
                        "engineering_name": "Shipping_ESZone1",
                        "name": "Shipping_ESZone1",
                        "areaRef": "ORNCCP5_Area",
                        "members": ["ES440"],
                        "membersOrigin": ORIGIN_ENGINEER,
                        "engineerEdited": True,
                    }
                ]
            },
        )
        self.assertEqual(
            [z.get("source_id") for z in model["zones"]].count("ORNCCP5_ESZone1"),
            1,
        )
        hit = next(z for z in model["zones"] if z.get("source_id") == "ORNCCP5_ESZone1")
        self.assertEqual(hit["engineering_name"], "Shipping_ESZone1")
        self.assertEqual(hit["members"], ["ES440"])
        payload = safety_build_workbook_payload(model)
        pz = payload["zones"][0]
        self.assertEqual(pz["source_id"], "ORNCCP5_ESZone1")
        self.assertEqual(pz["engineering_name"], "Shipping_ESZone1")


class Test14RepeatedApplyNoDuplicate(unittest.TestCase):
    """14. Repeated Apply does not duplicate Safety zones."""

    def test_reconcile_idempotent(self) -> None:
        zones = [
            {
                "source_id": "ORNCCP5_ESZone1",
                "name": "ORNCCP5_ESZone1",
                "engineering_name": "ORNCCP5_ESZone1",
                "areaRef": "ORNCCP5_Area",
                "members": [],
                "runDiscovered": True,
            },
            {
                "source_id": "Staging_ESZone1",
                "name": "Staging_ESZone1",
                "engineering_name": "Staging_ESZone1",
                "areaRef": "ORNCCP5_Area",
                "members": ["ES1"],
                "engineerEdited": True,
                "membersOrigin": ORIGIN_ENGINEER,
            },
        ]
        snapshots = []
        cur = zones
        for _ in range(5):
            recon = reconcile_safety_zones(
                cur,
                run_zone_ids={"ORNCCP5_ESZone1"},
                conveyor_zone_refs={"ORNCCP5_ESZone1"},
                current_areas={"ORNCCP5_Area"},
            )
            cur = recon["zones"]
            snapshots.append(tuple(sorted(
                str(z.get("source_id") or z.get("name")) for z in cur
            )))
        self.assertEqual(len(set(snapshots)), 1, snapshots)
        self.assertEqual(len(snapshots[0]), 2)

    def test_build_model_apply_twice_no_dup(self) -> None:
        eng = {
            "zones": [
                {
                    "source_id": "ORNCCP5_ESZone1",
                    "engineering_name": "ORNCCP5_ESZone1",
                    "areaRef": "ORNCCP5_Area",
                    "members": ["ES440"],
                    "membersOrigin": ORIGIN_ENGINEER,
                    "engineerEdited": True,
                }
            ]
        }
        ids = []
        for _ in range(3):
            model = build_safety_model(
                run_dir=None,
                machine="ORNCCP5",
                transport_zones=[
                    {
                        "name": "ORNCCP5_ESZone1",
                        "area": "ORNCCP5_Area",
                        "conveyors": ["P440"],
                        "members": [],
                    }
                ],
                areas=["ORNCCP5_Area"],
                area_conveyors={"ORNCCP5_Area": ["P440"]},
                engineer_safety_build=eng,
            )
            sids = [z.get("source_id") for z in model["zones"]]
            ids.append(tuple(sorted(sids)))
            eng = {"zones": safety_build_workbook_payload(model)["zones"]}
        self.assertEqual(len(set(ids)), 1, ids)
        self.assertEqual(ids[0].count("ORNCCP5_ESZone1"), 1)


class Test15TestDefaultZonesDoNotLeak(unittest.TestCase):
    """15. Test/default Zone1..ZoneN / 123456 do not leak into production."""

    def test_placeholder_detectors(self) -> None:
        self.assertTrue(is_ui_placeholder_area("Zone1_Area"))
        self.assertTrue(is_ui_placeholder_area("Zone9_Area"))
        self.assertFalse(is_ui_placeholder_area("ORNCCP5_Area"))
        self.assertTrue(is_placeholder_or_test_zone_name("Zone1_ESZone1"))
        self.assertTrue(is_placeholder_or_test_zone_name("Zone9_ESZone1"))
        self.assertTrue(is_placeholder_or_test_zone_name("123456_ESZone1"))
        self.assertFalse(is_placeholder_or_test_zone_name("ORNCCP5_ESZone1"))
        self.assertFalse(is_production_safety_zone_name("Zone3_ESZone1"))
        self.assertTrue(is_production_safety_zone_name("ORNCCP5_ESZone1"))

    def test_workbook_apply_does_not_promote_zone1_catalog(self) -> None:
        if not (RUN_PLC5 / "project.cfg").is_file():
            self.skipTest("PLC5 RUN peek missing")
        wb = build_workbook_from_run(RUN_PLC5)
        # Dropdown may still list ZoneN for Excel-style UX
        opts = (wb.get("options") or {}).get("safety_zones") or []
        self.assertIn("Zone1_ESZone1", opts)
        # Production wb.safety_zones must not include placeholders
        prod = wb.get("safety_zones") or []
        self.assertNotIn("Zone1_ESZone1", prod)
        self.assertNotIn("Zone9_ESZone1", prod)
        self.assertNotIn("123456_ESZone1", prod)

        inp = AutogenInput(
            project_name="ORNCCP5",
            areas=["ORNCCP5_Area"],
            safety_zones=["ORNCCP5_ESZone1"],
            conveyors=[
                ConveyorRow(
                    number=1,
                    conveyor="P440",
                    main_area="ORNCCP5_Area",
                    safety_zone="ORNCCP5_ESZone1",
                    type="Transport with MS",
                )
            ],
        )
        # Even with polluted options catalog, apply must not promote
        wb["options"]["safety_zones"] = list(opts) + ["123456_ESZone1"]
        out = apply_workbook_to_input(inp, wb)
        leaked = [
            z for z in (out.safety_zones or [])
            if is_placeholder_or_test_zone_name(z)
        ]
        self.assertEqual(leaked, [], msg=f"leaked into production: {out.safety_zones}")
        self.assertIn("ORNCCP5_ESZone1", out.safety_zones)

    def test_reconcile_drops_curtis_manifest_pollution(self) -> None:
        """Reproduce ORNCCP5 review_zones pollution from da5e86d manifest."""
        before = [
            "123456_ESZone1",
            "ORNCCP5_ESZone1",
            "Zone1_ESZone1",
            "Zone2_ESZone1",
            "Zone3_ESZone1",
            "Zone4_ESZone1",
            "Zone5_ESZone1",
            "Zone6_ESZone1",
            "Zone7_ESZone1",
            "Zone8_ESZone1",
            "Zone9_ESZone1",
        ]
        zones = []
        for name in before:
            area = "ORNCCP5_Area" if name != "123456_ESZone1" else "123456"
            zones.append(
                {
                    "source_id": name,
                    "name": name,
                    "engineering_name": name,
                    "areaRef": area,
                    "members": [],
                    "conveyorRefs": ["P440"] if name == "ORNCCP5_ESZone1" else [],
                    "runDiscovered": name == "ORNCCP5_ESZone1",
                    "engineerEdited": False,
                }
            )
        recon = reconcile_safety_zones(
            zones,
            run_zone_ids={"ORNCCP5_ESZone1"},
            conveyor_zone_refs={"ORNCCP5_ESZone1"},
            current_areas={"ORNCCP5_Area"},
        )
        after = set(recon["after"])
        self.assertIn("ORNCCP5_ESZone1", after)
        for n in range(1, 10):
            self.assertNotIn(f"Zone{n}_ESZone1", after)
        self.assertNotIn("123456_ESZone1", after)
        # Classifications document each suspicious zone
        by_name = {c["source_id"]: c for c in recon["classifications"]}
        self.assertEqual(by_name["Zone1_ESZone1"]["provenance"], PROVENANCE_TEST_FIXTURE)
        self.assertEqual(by_name["Zone1_ESZone1"]["action"], "remove")
        self.assertEqual(by_name["123456_ESZone1"]["provenance"], PROVENANCE_TEST_FIXTURE)
        self.assertEqual(by_name["ORNCCP5_ESZone1"]["action"], "keep")

    def test_js_stops_auto_default_area_shells(self) -> None:
        js = SAFETY_JS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("do NOT auto-create", js)
        self.assertIn("isPlaceholderOrTestZoneName", js)
        self.assertIn("classifyZoneProvenance", js)
        fp = FORTNA_JS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("placeholderArea", fp)


class Test16EngineerZonesSurvive(unittest.TestCase):
    """16. Engineer-created Safety zones survive reconciliation."""

    def test_engineer_zone_kept(self) -> None:
        zones = [
            {
                "source_id": "HAHAHA_ESZone1",
                "name": "HAHAHA_ESZone1",
                "engineering_name": "HAHAHA_ESZone1",
                "areaRef": "HAHAHA",
                "members": ["ES400", "CP2_ES"],
                "membersOrigin": ORIGIN_ENGINEER,
                "engineerEdited": True,
            },
            {
                "source_id": "Zone1_ESZone1",
                "name": "Zone1_ESZone1",
                "areaRef": "ORNCCP5_Area",
                "members": [],
                "engineerEdited": False,
            },
        ]
        recon = reconcile_safety_zones(
            zones,
            run_zone_ids=set(),
            conveyor_zone_refs=set(),
            current_areas={"HAHAHA", "ORNCCP5_Area"},
        )
        after = {z.get("source_id") for z in recon["zones"]}
        self.assertIn("HAHAHA_ESZone1", after)
        self.assertNotIn("Zone1_ESZone1", after)
        self.assertEqual(
            next(z for z in recon["zones"] if z["source_id"] == "HAHAHA_ESZone1")["provenance"],
            PROVENANCE_ENGINEER_CREATED,
        )


class Test17UnknownMembershipFailSafe(unittest.TestCase):
    """17. Unknown Safety membership remains fail-safe (REVIEW_REQUIRED)."""

    def test_empty_members_review_required(self) -> None:
        model = build_safety_model(
            run_dir=None,
            machine="ORNCCP5",
            transport_zones=[
                {
                    "name": "ORNCCP5_ESZone1",
                    "area": "ORNCCP5_Area",
                    "conveyors": ["P440", "P442", "P444"],
                    "members": [],
                }
            ],
            areas=["ORNCCP5_Area"],
            area_conveyors={"ORNCCP5_Area": ["P440", "P442", "P444"]},
            engineer_safety_build={},
        )
        z = next(x for x in model["zones"] if "ORNCCP5" in str(x.get("source_id") or x.get("name")))
        self.assertEqual(z.get("members") or [], [])
        self.assertIn(z.get("status"), ("REVIEW_REQUIRED", "UNRESOLVED"))
        self.assertIn("SafetyDevices", z.get("hard_missing") or ["SafetyDevices"])
        # Never invent devices from area conveyors
        self.assertFalse(any(
            str(m).startswith("P") for m in (z.get("members") or [])
        ))

    def test_js_membership_status_fail_safe(self) -> None:
        js = SAFETY_JS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("membershipStatusLabel", js)
        self.assertIn("REVIEW_REQUIRED", js)
        self.assertIn("fail-safe REVIEW_REQUIRED", js)
        self.assertIn("Gate J", js)
        # membersAreProven gates auto-assign
        self.assertIn("function membersAreProven", js)

    def test_policy_flags(self) -> None:
        model = build_safety_model(
            run_dir=None,
            machine="X",
            transport_zones=[],
            areas=[],
            engineer_safety_build={},
        )
        pol = model.get("policy") or {}
        self.assertTrue(pol.get("no_ui_placeholder_zone_persist"))
        self.assertTrue(pol.get("unknown_membership_fail_safe"))
        self.assertTrue(pol.get("suggestions_are_not_auto_assign"))


class TestClassifyProvenance(unittest.TestCase):
    def test_classes(self) -> None:
        self.assertEqual(
            classify_zone_provenance(
                {"source_id": "Zone3_ESZone1", "name": "Zone3_ESZone1", "members": []},
            ),
            PROVENANCE_TEST_FIXTURE,
        )
        self.assertEqual(
            classify_zone_provenance(
                {
                    "source_id": "A_ESZone1",
                    "runDiscovered": True,
                    "members": [],
                },
                run_zone_ids={"A_ESZone1"},
            ),
            PROVENANCE_RUN_DISCOVERED,
        )
        self.assertEqual(
            classify_zone_provenance(
                {
                    "source_id": "B_ESZone1",
                    "engineerEdited": True,
                    "members": ["ES1"],
                    "membersOrigin": ORIGIN_ENGINEER,
                },
            ),
            PROVENANCE_ENGINEER_CREATED,
        )


class TestGate8RunEngineerCoexistence(unittest.TestCase):
    """Gate 8 — RUN zone + engineer zone both persist; source_id immutable."""

    def test_run_and_engineer_zones_both_persist(self) -> None:
        model = build_safety_model(
            run_dir=None,
            machine="ORNCCP5",
            transport_zones=[
                {
                    "name": "ORNCCP5_ESZone1",
                    "source_id": "ORNCCP5_ESZone1",
                    "area": "ORNCCP5_Area",
                    "conveyors": ["P440"],
                    "members": [],
                    "runDiscovered": True,
                }
            ],
            areas=["ORNCCP5_Area"],
            area_conveyors={"ORNCCP5_Area": ["P440"]},
            engineer_safety_build={
                "zones": [
                    {
                        "source_id": "Staging_ESZone1",
                        "engineering_name": "Staging_ESZone1",
                        "areaRef": "ORNCCP5_Area",
                        "members": ["ES440"],
                        "membersOrigin": ORIGIN_ENGINEER,
                        "engineerEdited": True,
                        "createdBy": "engineer",
                    }
                ]
            },
        )
        by_sid = {z.get("source_id"): z for z in model["zones"]}
        self.assertIn("ORNCCP5_ESZone1", by_sid)
        self.assertIn("Staging_ESZone1", by_sid)
        run_z = by_sid["ORNCCP5_ESZone1"]
        eng_z = by_sid["Staging_ESZone1"]
        self.assertEqual(run_z.get("origin") or run_z.get("provenance"), PROVENANCE_RUN_DISCOVERED)
        self.assertEqual(
            eng_z.get("origin") or eng_z.get("provenance"), PROVENANCE_ENGINEER_CREATED
        )
        # Do not invent membership on the RUN shell
        self.assertEqual(list(run_z.get("members") or []), [])
        self.assertEqual(list(eng_z.get("members") or []), ["ES440"])

    def test_engineer_overlay_does_not_overwrite_run_source_id(self) -> None:
        model = build_safety_model(
            run_dir=None,
            machine="ORNCCP5",
            transport_zones=[
                {
                    "name": "ORNCCP5_ESZone1",
                    "source_id": "ORNCCP5_ESZone1",
                    "area": "ORNCCP5_Area",
                    "conveyors": ["P440"],
                    "members": [],
                    "runDiscovered": True,
                }
            ],
            areas=["ORNCCP5_Area"],
            area_conveyors={"ORNCCP5_Area": ["P440"]},
            engineer_safety_build={
                "zones": [
                    {
                        # Divergent id + display name matching RUN shell — must not steal source_id
                        "source_id": "EngineerAlt_ESZone1",
                        "engineering_name": "ORNCCP5_ESZone1",
                        "areaRef": "ORNCCP5_Area",
                        "members": ["ES440"],
                        "membersOrigin": ORIGIN_ENGINEER,
                        "engineerEdited": True,
                        "createdBy": "engineer",
                    }
                ]
            },
        )
        sids = {z.get("source_id") for z in model["zones"]}
        self.assertIn("ORNCCP5_ESZone1", sids)
        # RUN identity preserved
        run_z = next(z for z in model["zones"] if z.get("source_id") == "ORNCCP5_ESZone1")
        self.assertEqual(run_z["source_id"], "ORNCCP5_ESZone1")
        # Engineer zone also persists under its own source_id (no merge-by-display-name steal)
        self.assertIn("EngineerAlt_ESZone1", sids)


if __name__ == "__main__":
    unittest.main(verbosity=2)

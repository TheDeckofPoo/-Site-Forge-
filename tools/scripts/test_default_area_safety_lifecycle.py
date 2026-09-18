#!/usr/bin/env python3
"""Gates 2 / 3 / 7 / 8 — Default Area + Default/Unassigned Safety lifecycle.

Conservation:
  discovered == default + sum(engineer) + proven_exclusions  (no dupes)

Transport: N equipment → Area_TEST with X moved → delete → back to Default.
Safety: M devices → ES_TEST with Y assigned → delete → back to Default.
Apply idempotence: no [object Object]_ESZone1; Default bucket not emitted as ES zone.
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

from fortna_default_ownership import (  # noqa: E402
    DEFAULT_AREA_NAME,
    DEFAULT_SAFETY_NAME,
    UNASSIGNED_SAFETY_NAME,
    assign_safety_members,
    delete_safety_zone_return_to_default,
    make_default_area,
    make_default_safety_zone,
    return_transport_to_default,
    safety_ownership_counts,
    safety_zone_is_default,
    transport_ownership_counts,
)
from fortna_area_ops import create_area, delete_area, move_equipment  # noqa: E402
from fortna_site_model import SiteModel, ensure_default_area, make_object  # noqa: E402
from fortna_safety_model import (  # noqa: E402
    build_safety_model,
    safety_build_workbook_payload,
)

TRANSPORT_JS = ROOT / "dashboard" / "transport-build.js"
TRANSPORT_PASS2 = ROOT / "dashboard" / "transport-build-pass2.js"
SAFETY_JS = ROOT / "dashboard" / "safety-build.js"
INDEX_HTML = ROOT / "dashboard" / "index.html"


def _synth_transport(n: int = 40) -> list[dict]:
    nodes = []
    for i in range(1, n + 1):
        nodes.append(
            {
                "id": f"n{i}",
                "kind": "conv_straight",
                "conveyorTag": f"P{9000 + i}",
                "label": f"P{9000 + i}",
                "plcOwned": True,
                "displayContext": False,
                "scopeClass": "LOCAL",
                "provenance": {"geometry": "PROVEN_RUN", "area": "SITE_FORGE_DEFAULT"},
            }
        )
    return [make_default_area(nodes=nodes)]


def _synth_safety_devices(m: int = 127) -> list[dict]:
    out = []
    for i in range(1, m + 1):
        out.append(
            {
                "name": f"ES{400 + i}",
                "kind": "ESTOP",
                "status": "UNASSIGNED",
                "origin": "UNRESOLVED",
            }
        )
    return out


class TestGate2DefaultArea(unittest.TestCase):
    def test_autobuild_lands_in_default(self) -> None:
        areas = _synth_transport(40)
        c = transport_ownership_counts(areas, discovered=40)
        self.assertTrue(c["ok"], c)
        self.assertEqual(c["default"], 40)
        self.assertEqual(c["engineer_total"], 0)
        self.assertEqual(areas[0]["name"], DEFAULT_AREA_NAME)
        self.assertTrue(areas[0]["isDefault"])

    def test_move_to_engineer_area_conserves(self) -> None:
        areas = _synth_transport(40)
        # Simulate engineer Area_A with 20 moved
        area_a = {
            "id": "area_a",
            "name": "Area_A",
            "isDefault": False,
            "nodes": [],
            "wires": [],
        }
        moving = areas[0]["nodes"][:20]
        areas[0]["nodes"] = areas[0]["nodes"][20:]
        area_a["nodes"] = moving
        areas.append(area_a)
        c = transport_ownership_counts(areas, discovered=40)
        self.assertTrue(c["ok"], c)
        self.assertEqual(c["default"], 20)
        self.assertEqual(c["engineer"].get("Area_A"), 20)
        self.assertEqual(c["default"] + c["engineer_total"], 40)

    def test_delete_engineer_returns_to_default(self) -> None:
        areas = _synth_transport(40)
        area_a = {
            "id": "area_a",
            "name": "Area_TEST",
            "isDefault": False,
            "nodes": areas[0]["nodes"][:15],
            "wires": [],
        }
        areas[0]["nodes"] = areas[0]["nodes"][15:]
        areas.append(area_a)
        areas = return_transport_to_default(areas, "area_a")
        c = transport_ownership_counts(areas, discovered=40)
        self.assertTrue(c["ok"], c)
        self.assertEqual(c["default"], 40)
        self.assertEqual(c["engineer_total"], 0)
        self.assertFalse(any(a.get("name") == "Area_TEST" for a in areas))

    def test_cannot_delete_default_area(self) -> None:
        areas = _synth_transport(5)
        with self.assertRaises(ValueError):
            return_transport_to_default(areas, areas[0]["id"])

    def test_site_model_delete_returns_to_default(self) -> None:
        m = SiteModel(machine_scope="SYNTH", run_dir="synthetic")
        for i in range(1, 11):
            m.equipment.append(
                make_object(
                    "equipment",
                    f"P{i}",
                    inclusion="INCLUDED",
                ).to_dict()
            )
        ensure_default_area(m)
        create_area(m, "Area_TEST")
        move_equipment(m, ["P1", "P2", "P3"], "Area_TEST", move_attached=False)
        self.assertEqual(
            sum(1 for e in m.equipment if e.get("area_id") == "Area_TEST"),
            3,
        )
        delete_area(m, "Area_TEST", return_to_default=True)
        self.assertFalse(any(a.get("raw_name") == "Area_TEST" for a in m.areas))
        # All equipment still owned; none lost
        self.assertEqual(len(m.equipment), 10)
        self.assertTrue(all(e.get("area_id") for e in m.equipment))

    def test_js_contracts_default_area(self) -> None:
        js = TRANSPORT_JS.read_text(encoding="utf-8", errors="replace")
        p2 = TRANSPORT_PASS2.read_text(encoding="utf-8", errors="replace")
        self.assertIn("DEFAULT_AREA_NAME", js)
        self.assertIn("Default Area", js)
        self.assertIn("ensureDefaultArea", js)
        self.assertIn("returnAreaMembersToDefault", js)
        self.assertIn("transportOwnershipCounts", js)
        self.assertIn("SITE_FORGE_DEFAULT", p2)
        self.assertIn("Returned to Default Area", p2)


class TestGate3DefaultSafety(unittest.TestCase):
    def test_unassigned_bucket_and_conservation(self) -> None:
        devices = _synth_safety_devices(127)
        zones = [make_default_safety_zone(unassigned_members=[d["name"] for d in devices])]
        c = safety_ownership_counts(devices, zones, discovered=127)
        self.assertTrue(c["ok"], c)
        self.assertEqual(c["default"], 127)
        self.assertEqual(c["engineer_total"], 0)

        zones = assign_safety_members(zones, [d["name"] for d in devices[:14]], "Zone2")
        # Drop virtual default before recount (operational only)
        zones = [z for z in zones if not safety_zone_is_default(z)]
        c2 = safety_ownership_counts(devices, zones, discovered=127)
        self.assertTrue(c2["ok"], c2)
        self.assertEqual(c2["default"], 113)
        self.assertEqual(c2["engineer"].get("Zone2"), 14)
        self.assertEqual(c2["default"] + c2["engineer_total"], 127)

    def test_delete_zone_returns_all_to_default(self) -> None:
        devices = _synth_safety_devices(127)
        zones: list[dict] = []
        zones = assign_safety_members(zones, [d["name"] for d in devices[:14]], "ES_TEST")
        zones = delete_safety_zone_return_to_default(zones, "ES_TEST")
        c = safety_ownership_counts(devices, zones, discovered=127)
        self.assertTrue(c["ok"], c)
        self.assertEqual(c["default"], 127)
        self.assertEqual(c["engineer_total"], 0)

    def test_default_bucket_not_emitted_as_es_zone(self) -> None:
        model = build_safety_model(
            run_dir=None,
            machine="SYNTH",
            transport_zones=[],
            areas=["Area_A"],
            area_conveyors={},
            engineer_safety_build={
                "zones": [
                    {
                        "source_id": "ES_TEST",
                        "engineering_name": "ES_TEST",
                        "name": "ES_TEST",
                        "members": ["ES401", "ES402"],
                        "membersOrigin": "ENGINEER_ASSIGNED",
                        "engineerEdited": True,
                        "createdBy": "engineer",
                    }
                ]
            },
            devices=_synth_safety_devices(20),
        )
        # Default Safety present in model for UI
        self.assertTrue(any(safety_zone_is_default(z) for z in model["zones"]))
        self.assertIn(DEFAULT_SAFETY_NAME, {z.get("source_id") for z in model["zones"]})
        # Workbook payload excludes Default bucket (not operational)
        payload = safety_build_workbook_payload(model)
        names = {z.get("source_id") or z.get("name") for z in payload["zones"]}
        self.assertNotIn(DEFAULT_SAFETY_NAME, names)
        self.assertNotIn(UNASSIGNED_SAFETY_NAME, names)
        self.assertIn("ES_TEST", names)
        # Conservation
        self.assertTrue(model["counts"].get("conservation_ok"))
        self.assertEqual(
            model["counts"]["default_safety"] + model["counts"]["assigned"],
            model["counts"]["devices_found"],
        )
        # Fail-safe policy
        self.assertTrue(model["policy"].get("unassigned_is_review_required"))
        self.assertTrue(model["policy"].get("default_safety_not_operational"))

    def test_apply_idempotent_no_object_object(self) -> None:
        model = build_safety_model(
            run_dir=None,
            machine="SYNTH",
            transport_zones=[],
            areas=["Trans_Test_Area"],
            engineer_safety_build={
                "zones": [
                    {
                        "source_id": "ES_TEST",
                        "name": "ES_TEST",
                        "members": ["ES401"],
                        "engineerEdited": True,
                        "createdBy": "engineer",
                    }
                ]
            },
            devices=_synth_safety_devices(10),
        )
        p1 = safety_build_workbook_payload(model)
        p2 = safety_build_workbook_payload(
            build_safety_model(
                run_dir=None,
                machine="SYNTH",
                transport_zones=[],
                areas=["Trans_Test_Area"],
                engineer_safety_build=p1,
                devices=_synth_safety_devices(10),
            )
        )
        ids1 = sorted(z.get("source_id") for z in p1["zones"])
        ids2 = sorted(z.get("source_id") for z in p2["zones"])
        self.assertEqual(ids1, ids2)
        blob = json.dumps(p2)
        self.assertNotRegex(blob, r"\[object\s+Object\]")
        self.assertNotIn("[object Object]_ESZone1", blob)

    def test_js_contracts_default_safety(self) -> None:
        js = SAFETY_JS.read_text(encoding="utf-8", errors="replace")
        html = INDEX_HTML.read_text(encoding="utf-8", errors="replace")
        self.assertIn("DEFAULT_SAFETY_NAME", js)
        self.assertIn("UNASSIGNED_SAFETY_NAME", js)
        self.assertIn("makeDefaultSafetyZone", js)
        self.assertIn("isDefaultSafetyZone", js)
        self.assertIn("NOT an E-stop zone", js)
        self.assertIn("Default / Unassigned", html)
        self.assertIn("sb-count-assigned", html)
        self.assertIn("Site devices", html)


class TestGate8Lifecycle(unittest.TestCase):
    """N transport + M safety → create → move → verify → delete → Default."""

    def test_combined_lifecycle(self) -> None:
        n, m = 40, 127
        x, y = 20, 14

        # --- Transport ---
        areas = _synth_transport(n)
        c0 = transport_ownership_counts(areas, discovered=n)
        self.assertEqual(c0["default"], n)

        area_test = {
            "id": "area_test",
            "name": "Area_TEST",
            "isDefault": False,
            "nodes": areas[0]["nodes"][:x],
            "wires": [],
        }
        areas[0]["nodes"] = areas[0]["nodes"][x:]
        areas.append(area_test)
        c1 = transport_ownership_counts(areas, discovered=n)
        self.assertEqual(c1["default"], n - x)
        self.assertEqual(c1["engineer"].get("Area_TEST"), x)
        self.assertTrue(c1["ok"])

        # Simulate Apply/reopen: serialize + reload areas
        raw = json.loads(json.dumps(areas))
        c1b = transport_ownership_counts(raw, discovered=n)
        self.assertEqual(c1b, c1)

        areas = return_transport_to_default(areas, "area_test")
        c2 = transport_ownership_counts(areas, discovered=n)
        self.assertEqual(c2["default"], n)
        self.assertEqual(c2["engineer_total"], 0)
        self.assertTrue(c2["ok"])

        # --- Safety ---
        devices = _synth_safety_devices(m)
        zones: list[dict] = []
        zones = assign_safety_members(
            zones, [d["name"] for d in devices[:y]], "ES_TEST"
        )
        c_s1 = safety_ownership_counts(devices, zones, discovered=m)
        self.assertEqual(c_s1["default"], m - y)
        self.assertEqual(c_s1["engineer"].get("ES_TEST"), y)
        self.assertTrue(c_s1["ok"])

        # Apply path: workbook payload excludes Default; reopen rebuilds conservation
        model = {
            "zones": [
                make_default_safety_zone(
                    unassigned_members=[d["name"] for d in devices[y:]]
                )
            ]
            + zones,
            "devices": devices,
            "unassignedDevices": [d["name"] for d in devices[y:]],
            "counts": {},
        }
        payload = safety_build_workbook_payload(model)
        self.assertTrue(all(not safety_zone_is_default(z) for z in payload["zones"]))
        self.assertEqual(len(payload["zones"]), 1)
        self.assertEqual(payload["zones"][0]["source_id"], "ES_TEST")

        # Second Apply (idempotent)
        payload2 = safety_build_workbook_payload(
            {
                "zones": payload["zones"]
                + [
                    make_default_safety_zone(
                        unassigned_members=payload.get("unassignedDevices") or []
                    )
                ],
                "devices": devices,
                "unassignedDevices": [d["name"] for d in devices[y:]],
            }
        )
        self.assertEqual(
            [z["source_id"] for z in payload["zones"]],
            [z["source_id"] for z in payload2["zones"]],
        )
        self.assertFalse(re.search(r"\[object\s+Object\]", json.dumps(payload2)))

        zones = delete_safety_zone_return_to_default(zones, "ES_TEST")
        c_s2 = safety_ownership_counts(devices, zones, discovered=m)
        self.assertEqual(c_s2["default"], m)
        self.assertEqual(c_s2["engineer_total"], 0)
        self.assertTrue(c_s2["ok"])


if __name__ == "__main__":
    unittest.main()

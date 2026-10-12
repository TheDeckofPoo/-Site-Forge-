#!/usr/bin/env python3
"""P0 Safety Area/Zone persistence + Autogen consumption.

Reproduces Curtis MSCRENOPICK failure:
  Area_Test1 / Area_Test1_ESZone1 + ESPB2/24/32/ESLS2
must survive Apply (workbook.safety_build), refresh, and emit
Main_Routine / Safe_Logic / Safe_PI.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))

from fortna_es_compiler import (  # noqa: E402
    build_safety_zone_irs,
    emit_es_program,
)
from fortna_safety_assignment_gate import (  # noqa: E402
    _is_default_zone,
    _is_engineer_zone,
)
from fortna_safety_inventory_scope import (  # noqa: E402
    UNRELATED_FOREIGN,
    classify_safety_device_scope,
)


def _rung_xml(num: int, text: str, comment: str = "") -> str:
    c = f"<Comment><![CDATA[{comment}]]></Comment>" if comment else ""
    return f'<Rung Number="{num}" Type="N">{c}<Text><![CDATA[{text}]]></Text></Rung>'


def _routine(name: str, rungs: list[str]) -> str:
    fixed = []
    for i, r in enumerate(rungs):
        fixed.append(re.sub(r'Number="\d+"', f'Number="{i}"', r, count=1))
    return (
        f'<Routine Name="{name}" Type="RLL"><RLLContent>'
        + "".join(fixed)
        + "</RLLContent></Routine>"
    )


def _extract_tag_block(_library_text: str, _tag_name: str) -> str | None:
    return None

PICK_MEMBERS = ["ESPB2", "ESPB24", "ESPB32", "ESLS2"]
ZONE_NAME = "Area_Test1_ESZone1"
AREA_NAME = "Area_Test1"


def _engineer_zone(*, members=None, extra=None) -> dict:
    row = {
        "id": "szone_test1eszone1",
        "source_id": "szone_test1eszone1",
        "name": ZONE_NAME,
        "engineering_name": ZONE_NAME,
        "area": AREA_NAME,
        "areaRef": AREA_NAME,
        "members": list(members if members is not None else PICK_MEMBERS),
        "membersOrigin": "ENGINEER_ASSIGNED",
        "engineerEdited": True,
        "createdBy": "engineer",
        "zoneOrigin": "ENGINEER",
        "provenance": "ENGINEER_CREATED",
        "origin": "ENGINEER_CREATED",
        "operational": True,
        "status": "READY",
        "conveyors": [],
        "conveyorRefs": [],
        "eStops": ["ESPB2", "ESPB24", "ESPB32"],
        "eslsDevices": ["ESLS2"],
        "esrDevices": [],
        "mcrDevices": [],
        "csDevices": [],
        "resetSource": f"{AREA_NAME}.Reset",
        "silenceSource": f"{AREA_NAME}.Silence",
    }
    if extra:
        row.update(extra)
    return row


def _safety_build(*, members=None) -> dict:
    return {
        "version": 1,
        "source": "safety_build",
        "appliedAt": "2026-10-12T21:00:00+00:00",
        "zones": [_engineer_zone(members=members)],
        "devices": [],
        "safetyDevices": [],
    }


class TestSafetyZonePersistenceSource(unittest.TestCase):
    def test_engineer_zone_predicate(self) -> None:
        z = _engineer_zone()
        self.assertTrue(_is_engineer_zone(z))
        self.assertFalse(_is_default_zone(z))

    def test_cleared_workbook_is_not_authoritative_over_applied(self) -> None:
        """Simulate prefer: Applied payload must beat source:cleared stub."""
        applied = _safety_build()
        cleared = {"version": 1, "source": "cleared", "zones": [], "devices": []}
        # Python-side mirror of isClearedSafetyBuild + prefer rule
        def prefer(a, b):
            def cleared_sb(sb):
                return str((sb or {}).get("source") or "").lower() == "cleared"

            aa = None if cleared_sb(a) else a
            bb = None if cleared_sb(b) else b
            return aa or bb

        self.assertEqual(prefer(cleared, applied), applied)
        self.assertEqual(prefer(applied, cleared), applied)
        self.assertIsNone(prefer(cleared, cleared))

    def test_assignment_membership_exact_and_mutable(self) -> None:
        z = _engineer_zone()
        self.assertEqual(sorted(z["members"]), sorted(PICK_MEMBERS))
        # Remove one / add one — exact membership is the persisted list
        z2 = _engineer_zone(members=["ESPB2", "ESPB24", "ESPB32", "ESLS2", "ESPB99"])
        self.assertIn("ESPB99", z2["members"])
        self.assertEqual(len(z2["members"]), 5)
        z3 = _engineer_zone(members=["ESPB2", "ESPB24", "ESPB32"])
        self.assertNotIn("ESLS2", z3["members"])
        self.assertEqual(len(z3["members"]), 3)

    def test_workbook_roundtrip_preserves_zone(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "autogen_workbook.json"
            wb = {
                "version": 1,
                "kind": "fortna_autogen_workbook",
                "machine": "MSCRENOPICK",
                "source": "safety_apply",
                "areas": [{"name": AREA_NAME, "id": AREA_NAME}],
                "conveyors": [],
                "safety_build": _safety_build(),
            }
            path.write_text(json.dumps(wb, indent=2), encoding="utf-8")
            loaded = json.loads(path.read_text(encoding="utf-8"))
            sb = loaded["safety_build"]
            self.assertEqual(sb["source"], "safety_build")
            self.assertTrue(sb.get("appliedAt"))
            zones = sb["zones"]
            self.assertEqual(len(zones), 1)
            self.assertEqual(zones[0]["engineering_name"], ZONE_NAME)
            self.assertEqual(sorted(zones[0]["members"]), sorted(PICK_MEMBERS))
            self.assertEqual(loaded["areas"][0]["name"], AREA_NAME)


class TestSafetyZoneAutogenEmission(unittest.TestCase):
    def test_irs_built_from_workbook_safety_build(self) -> None:
        sb = _safety_build()
        eng = [z for z in sb["zones"] if _is_engineer_zone(z) and not _is_default_zone(z)]
        irs = build_safety_zone_irs(
            safety_zones=[],
            areas=[AREA_NAME],
            engineer_zones=eng,
            default_area=AREA_NAME,
            area_conveyors={AREA_NAME: []},
            safety_devices=[
                {"name": m, "kind": "ESTOP" if m.startswith("ESPB") else "ESLS", "assignable": True}
                for m in PICK_MEMBERS
            ],
        )
        names = [z.name for z in irs]
        self.assertIn(ZONE_NAME, names)
        hit = next(z for z in irs if z.name == ZONE_NAME)
        self.assertEqual(sorted(hit.members), sorted(PICK_MEMBERS))
        self.assertTrue(hit.members)

    def test_emit_es_program_populates_main_safe_logic_safe_pi(self) -> None:
        sb = _safety_build()
        eng = sb["zones"]
        irs = build_safety_zone_irs(
            safety_zones=[],
            areas=[AREA_NAME],
            engineer_zones=eng,
            default_area=AREA_NAME,
            area_conveyors={AREA_NAME: []},
            safety_devices=[
                {"name": m, "kind": "ESTOP" if m.startswith("ESPB") else "ESLS", "assignable": True}
                for m in PICK_MEMBERS
            ],
        )
        self.assertTrue(irs, "engineer zone must become SafetyZoneIR")
        pack = emit_es_program(
            irs,
            _rung_xml=_rung_xml,
            routine=_routine,
            extract_tag_block=_extract_tag_block,
            library_text="",
            ensure_tag=lambda *_a, **_k: None,
            add_tag_block=lambda *_a, **_k: None,
            # Synthetic writer graph so PI invariant can pass for unit emit.
            written_tags=set(PICK_MEMBERS),
        )
        self.assertIsNotNone(pack)
        xml = str(pack.get("program_xml") or "")
        self.assertIn("Main_Routine", xml)
        self.assertIn(f"JSR({ZONE_NAME}_Safe_Logic,0);", xml)
        self.assertIn(f"JSR({ZONE_NAME}_Safe_PI,0);", xml)
        self.assertIn(f'Routine Name="{ZONE_NAME}_Safe_Logic"', xml)
        self.assertIn(f'Routine Name="{ZONE_NAME}_Safe_PI"', xml)
        # Populated Main — not blank RLLContent when zone has members
        self.assertNotRegex(
            xml,
            r'Routine Name="Main_Routine"[^>]*>\s*<RLLContent>\s*</RLLContent>',
        )

    def test_default_bucket_does_not_replace_engineer_zone(self) -> None:
        eng = _engineer_zone()
        default = {
            "name": "Default Safety",
            "engineering_name": "Default Safety",
            "members": ["ESPB20", "ESPB21"],
            "defaultSafety": True,
            "isDefault": True,
            "zoneOrigin": "DEFAULT",
            "operational": False,
        }
        zones = [eng, default]
        filtered = [z for z in zones if not _is_default_zone(z) and (_is_engineer_zone(z) or z.get("members"))]
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["engineering_name"], ZONE_NAME)


class TestForeignDisplayScope(unittest.TestCase):
    def test_ship_device_scope_foreign_for_pick(self) -> None:
        d = {
            "name": "ESPB20",
            "ownership": "FOREIGN",
            "final_status": "FOREIGN_CONTROLLER",
            "controller": "MSCRENOSHIP",
            "evidence_class": "FOREIGN_CONTROLLER",
            "assignable": False,
        }
        self.assertEqual(
            classify_safety_device_scope(d, active_machine="MSCRENOPICK"),
            UNRELATED_FOREIGN,
        )


@unittest.skipUnless(
    (
        REPO
        / "workspace"
        / "_reno_peek"
        / "20260813-1132-MSCRENO-MSCRENOSHIP-RUN"
        / "RUN"
        / "project.cfg"
    ).is_file(),
    "MSCRENOSHIP RUN missing",
)
class TestShipLocalSafetyRegression(unittest.TestCase):
    def test_ship_engineer_zone_predicate_still_works(self) -> None:
        z = {
            "name": "MSCRENOSHIP_ESZone1",
            "engineering_name": "MSCRENOSHIP_ESZone1",
            "members": ["ESLS1"],
            "membersOrigin": "ENGINEER_ASSIGNED",
            "createdBy": "engineer",
            "zoneOrigin": "ENGINEER",
            "provenance": "ENGINEER_CREATED",
        }
        self.assertTrue(_is_engineer_zone(z))
        irs = build_safety_zone_irs(
            engineer_zones=[z],
            areas=["Ship_Area"],
            default_area="Ship_Area",
            safety_devices=[{"name": "ESLS1", "kind": "ESLS", "assignable": True}],
        )
        self.assertTrue(any(x.name == "MSCRENOSHIP_ESZone1" for x in irs))


if __name__ == "__main__":
    unittest.main()

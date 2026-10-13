#!/usr/bin/env python3
"""P0: engineer-created local Areas/Zones must not be FOREIGN_SITE residue.

Authority = EXPECTED_ARTIFACT_MANIFEST / resolved model — never display-name prefix.
Foreign-site residue detection remains active for real other-controller tokens.
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from fortna_l5x_acceptance_auditor import (  # noqa: E402
    FOREIGN_SITE_TOKENS,
    STATE_AUDIT_FAIL,
    STATE_AUDIT_PASS,
    audit_l5x,
    build_expected_artifact_manifest,
    _foreign_site_forbid_for_build,
    _expected_local_artifact_names,
)

# Local matrix — must NOT be flagged when present in expected manifest
LOCAL_MATRIX = [
    ("Area_Test1", "Area_Test1_ESZone1"),
    ("MSCRENOPICK_AreaTest1", "MSCRENOPICK_AreaTest1_ESZone1"),
    ("Area_1", "Zone_1"),
    ("North Sort", "North_Sort_ESZone1"),
]
MEMBERS = ["ESPB2", "ESPB24", "ESPB32", "ESLS2"]


class _Inp:
    def __init__(self, area: str, zone: str):
        self.machine = "MSCRENOPICK"
        self.project_name = "MSCRENOPICK"
        self.areas = ["MSCRENOPICK_Area", area]
        self.include_io_map = True
        self.conveyors = [object()] * 29
        self.safety_zone_members = [
            {
                "name": zone,
                "engineering_name": zone,
                "area": area,
                "areaRef": area,
                "members": list(MEMBERS),
                "membersOrigin": "ENGINEER_ASSIGNED",
                "engineerEdited": True,
                "provenance": "ENGINEER_CREATED",
                "source_id": "szone_test_local",
                "status": "READY",
                "operational": True,
            }
        ]


def _mini_l5x(*, zone: str, area_sym: str, extra_tags: str = "") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<RSLogix5000Content SchemaRevision="1.0">
  <Controller Name="MSCRENOPICK">
    <Tags>
      <Tag Name="{area_sym}" TagType="Base" DataType="Area_UDT"></Tag>
      <Tag Name="{zone}" TagType="Base" DataType="Safe_UDT"></Tag>
      {extra_tags}
    </Tags>
    <Programs>
      <Program Name="ES" TestEdits="false" MainRoutineName="Main_Routine" Disabled="false">
        <Tags/>
        <Routines>
          <Routine Name="Main_Routine" Type="RLL">
            <RLLContent>
              <Rung Number="0" Type="N">
                <Text><![CDATA[JSR({zone}_Safe_Logic,0);]]></Text>
              </Rung>
              <Rung Number="1" Type="N">
                <Text><![CDATA[JSR({zone}_Safe_PI,0);]]></Text>
              </Rung>
            </RLLContent>
          </Routine>
          <Routine Name="{zone}_Safe_Logic" Type="RLL">
            <RLLContent>
              <Rung Number="0" Type="N">
                <Text><![CDATA[ES_SIL1_Cat1(ESPB2_AOI,ESPB2,{area_sym},{zone}.PI.Reset,{zone}.PI.Silence);]]></Text>
              </Rung>
            </RLLContent>
          </Routine>
          <Routine Name="{zone}_Safe_PI" Type="RLL">
            <RLLContent>
              <Rung Number="0" Type="N">
                <Text><![CDATA[XIC({area_sym}.Reset)OTE({zone}.PI.Reset);]]></Text>
              </Rung>
            </RLLContent>
          </Routine>
        </Routines>
      </Program>
      <Program Name="IO_MAP" TestEdits="false" MainRoutineName="MainRoutine" Disabled="false">
        <Tags/><Routines>
          <Routine Name="MainRoutine" Type="RLL">
            <RLLContent>
              <Rung Number="0" Type="N"><Text><![CDATA[NOP();]]></Text></Rung>
            </RLLContent>
          </Routine>
        </Routines>
      </Program>
      <Program Name="MSCRENOPICK_Area_Fast" TestEdits="false" MainRoutineName="MainRoutine" Disabled="false">
        <Tags/><Routines>
          <Routine Name="MainRoutine" Type="RLL">
            <RLLContent>
              <Rung Number="0" Type="N"><Text><![CDATA[XIC(AlwaysOn)OTE(Fast_Run);]]></Text></Rung>
            </RLLContent>
          </Routine>
        </Routines>
      </Program>
    </Programs>
  </Controller>
</RSLogix5000Content>
"""


class TestNoHardCodedLocalZoneInForeignTokens(unittest.TestCase):
    def test_area_test1_not_in_static_foreign_tokens(self) -> None:
        toks = {t.upper() for t in FOREIGN_SITE_TOKENS}
        self.assertNotIn("AREA_TEST1_ESZONE1", toks)
        self.assertNotIn("AREA_TEST1", toks)
        # Real foreign controllers remain listed
        self.assertIn("MSCRENOSHIP", toks)
        self.assertIn("MSCRENOPACK", toks)


class TestExpectedLocalExemptFromForbid(unittest.TestCase):
    def test_local_matrix_absent_from_foreign_forbid(self) -> None:
        for area, zone in LOCAL_MATRIX:
            with self.subTest(area=area, zone=zone):
                man = build_expected_artifact_manifest(
                    _Inp(area, zone),
                    report={"conveyor_count": 29, "include_io_map": True},
                )
                forbid = {t.upper() for t in (man.get("foreign_site_forbid") or [])}
                self.assertNotIn(zone.upper(), forbid, man.get("foreign_site_forbid"))
                # Display area must not be treated as foreign either
                from fortna_area_symbol import area_plc_symbol

                sym = area_plc_symbol(area)
                self.assertNotIn(area.upper(), forbid)
                self.assertNotIn(sym.upper(), forbid)
                # Expected zone must appear in safety.zones
                znames = [z["name"] for z in (man.get("safety") or {}).get("zones") or []]
                self.assertIn(zone, znames)
                # Real foreign still forbidden
                self.assertIn("MSCRENOSHIP", forbid)
                self.assertIn("MSCRENOPACK", forbid)

    def test_ship_token_forbidden_on_pick_build(self) -> None:
        local = _expected_local_artifact_names(
            areas=["MSCRENOPICK_Area", "Area_Test1"],
            zones=[{"name": "Area_Test1_ESZone1", "area": "Area_Test1"}],
            machine="MSCRENOPICK",
        )
        forbid = _foreign_site_forbid_for_build(
            machine="MSCRENOPICK", local_names=local
        )
        fu = {t.upper() for t in forbid}
        self.assertIn("MSCRENOSHIP", fu)
        self.assertIn("MSCRENOSHIP_ESZONE1", fu)
        self.assertNotIn("AREA_TEST1_ESZONE1", fu)
        self.assertNotIn("MSCRENOPICK", fu)
        self.assertNotIn("MSCRENOPICK_ESZONE1", fu)


class TestAuditorLocalMatrixPass(unittest.TestCase):
    def test_local_zones_audit_pass(self) -> None:
        from fortna_area_symbol import area_plc_symbol

        for area, zone in LOCAL_MATRIX:
            with self.subTest(area=area, zone=zone):
                man = build_expected_artifact_manifest(
                    _Inp(area, zone),
                    report={"conveyor_count": 29, "include_io_map": True},
                )
                # Soften transport requirements for the mini fixture
                man["transportation"] = {
                    "required": False,
                    "min_conveyors": 0,
                    "programs": [],
                    "core_routines_populated": False,
                }
                sym = area_plc_symbol(area)
                xml = _mini_l5x(zone=zone, area_sym=sym)
                with tempfile.TemporaryDirectory() as td:
                    p = Path(td) / f"{zone}.L5X"
                    p.write_text(xml, encoding="utf-8")
                    r = audit_l5x(p, man)
                foreign_fails = [
                    f
                    for f in (r.get("failures") or [])
                    if f.get("code") == "RESIDUE_FOREIGN_SITE"
                ]
                self.assertEqual(
                    foreign_fails,
                    [],
                    f"{zone} flagged FOREIGN: {foreign_fails} forbid={man.get('foreign_site_forbid')}",
                )


class TestAuditorForeignStillRejected(unittest.TestCase):
    def test_mscrenoship_residue_on_pick_build_fails(self) -> None:
        from fortna_area_symbol import area_plc_symbol

        area, zone = "Area_Test1", "Area_Test1_ESZone1"
        man = build_expected_artifact_manifest(
            _Inp(area, zone),
            report={"conveyor_count": 29, "include_io_map": True},
        )
        man["transportation"] = {
            "required": False,
            "min_conveyors": 0,
            "programs": [],
            "core_routines_populated": False,
        }
        sym = area_plc_symbol(area)
        # Inject proven MSCRENOSHIP residue into an otherwise-local L5X
        xml = _mini_l5x(
            zone=zone,
            area_sym=sym,
            extra_tags='<Tag Name="MSCRENOSHIP_ESZone1" TagType="Base" DataType="BOOL"></Tag>',
        )
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "foreign.L5X"
            p.write_text(xml, encoding="utf-8")
            r = audit_l5x(p, man)
        self.assertEqual(r["status"], STATE_AUDIT_FAIL, r)
        sigs = " | ".join(r.get("signatures") or [])
        self.assertTrue(
            any(s.startswith("RESIDUE:FOREIGN_SITE") for s in (r.get("signatures") or [])),
            sigs,
        )
        # Must cite a SHIP token, not the local Area_Test1 zone
        self.assertTrue(
            any("MSCRENOSHIP" in s for s in (r.get("signatures") or [])),
            sigs,
        )
        self.assertFalse(
            any("Area_Test1_ESZone1" in s for s in (r.get("signatures") or [])),
            sigs,
        )


if __name__ == "__main__":
    unittest.main()

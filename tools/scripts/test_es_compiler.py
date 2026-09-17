#!/usr/bin/env python3
"""Regression: reusable ES program emitter (PLC4/PLC5 structure)."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_es_compiler import (  # noqa: E402
    ES_PI20_CAPACITY,
    SafetyZoneIR,
    build_safety_zone_irs,
    emit_es_program,
    safety_readiness,
)


def _rung_xml(num: int, text: str, comment: str = "") -> str:
    c = f"<Comment><![CDATA[{comment}]]></Comment>" if comment else ""
    return f'<Rung Number="{num}" Type="N">{c}<Text><![CDATA[{text}]]></Text></Rung>'


def routine(name: str, rungs: list[str]) -> str:
    fixed = []
    for i, r in enumerate(rungs):
        fixed.append(re.sub(r'Number="\d+"', f'Number="{i}"', r, count=1))
    return (
        f'<Routine Name="{name}" Type="RLL"><RLLContent>'
        + "".join(fixed)
        + "</RLLContent></Routine>"
    )


def extract_tag_block(library_text: str, tag_name: str) -> str | None:
    # Minimal stubs so emit does not require full library for unit test
    stubs = {
        "Main_Area_Safe": '<Tag Name="Main_Area_Safe" TagType="Base" DataType="ES_Zone_UDT" />',
        "Main_Area_Safe_ES_PI": '<Tag Name="Main_Area_Safe_ES_PI" TagType="Base" DataType="ES_PI20" />',
        "NO_ES": '<Tag Name="NO_ES" TagType="Base" DataType="ES_UDT" />',
        "NO_ESNull": '<Tag Name="NO_ESNull" TagType="Base" DataType="ES_UDT" />',
        "ES1000_AOI": '<Tag Name="ES1000_AOI" TagType="Base" DataType="ES_SIL1_Cat1" />',
    }
    return stubs.get(tag_name)


class TestEsCompiler(unittest.TestCase):
    def test_named_zone_stub_without_inventing_devices(self) -> None:
        """Named Safety Zone stubs are OK for readiness reporting — devices stay empty."""
        zones = build_safety_zone_irs(
            safety_zones=["Shipping_Area_ESZone1"],
            areas=["Shipping_Area"],
            engineer_zones=[],
            estop_model={"zones": []},
            area_conveyors={"Shipping_Area": ["P100", "P101"]},
        )
        self.assertEqual(len(zones), 1)
        self.assertEqual(zones[0].name, "Shipping_Area_ESZone1")
        self.assertEqual(zones[0].area, "Shipping_Area")
        self.assertEqual(zones[0].conveyors, ["P100", "P101"])
        self.assertEqual(zones[0].members, [])  # never invent devices
        self.assertEqual(zones[0].device_membership_status, "UNRESOLVED")
        print("  [PASS] named zone stub reports conveyors; does not invent devices")

    def test_transport_zone_without_devices_is_review_required(self) -> None:
        eng = [
            {
                "name": "test1",
                "area": "ORNCCP2_Area",
                "conveyors": ["P1006", "P1007"],
                "members": [],
            }
        ]
        irs = build_safety_zone_irs(engineer_zones=eng, default_area="ORNCCP2_Area")
        self.assertEqual(len(irs), 1)
        self.assertEqual(irs[0].conveyors, ["P1006", "P1007"])
        self.assertEqual(irs[0].device_membership_status, "UNRESOLVED")
        ready = safety_readiness(irs, library_has_aois=True)
        self.assertEqual(ready["status"], "REVIEW_REQUIRED")
        self.assertIn("UNRESOLVED", ready["detail"])
        self.assertIn("Safety Zone:", ready["detail"])
        self.assertTrue(ready.get("zones"))
        gap = str(ready["zones"][0].get("gap") or "")
        self.assertTrue(
            "SafetyDevices" in gap or "safety-device" in gap.lower() or "UNRESOLVED" in gap,
            gap,
        )
        fields = ready["zones"][0].get("fields") or {}
        self.assertEqual(fields.get("SafetyDevices"), "UNRESOLVED")
        pack = emit_es_program(
            irs,
            _rung_xml=_rung_xml,
            routine=routine,
            extract_tag_block=extract_tag_block,
            library_text="",
        )
        # Fail-safe shell: Program ES + Main_Routine NOP — no fabricated membership
        self.assertIsNotNone(pack)
        self.assertTrue(pack.get("shell"))
        self.assertEqual(pack.get("status"), "REVIEW_REQUIRED")
        self.assertEqual(pack.get("emitted_zones"), [])
        self.assertIn("test1", pack.get("omitted_zones") or [])
        xml = pack.get("program_xml") or ""
        self.assertIn('Name="ES"', xml)
        self.assertIn("Main_Routine", xml)
        self.assertNotIn('Routine Name="test1_Safe_Logic"', xml)
        self.assertNotIn("ES_SIL1_Cat1(", xml)
        self.assertNotIn("JSR(", xml)
        print("  [PASS] Transport zone with conveyors but no devices → ES shell REVIEW REQUIRED")

    def test_emit_main_jsr_and_sil1(self) -> None:
        eng = [
            {
                "name": "Shipping_ESZone1",
                "area": "Shipping_Area",
                "conveyors": ["P100", "P102"],
                "members": ["CP2_MCR1", "CP2_ESR1", "ES201", "ES202", "ES203"],
            }
        ]
        irs = build_safety_zone_irs(engineer_zones=eng, default_area="Shipping_Area")
        self.assertEqual(len(irs), 1)
        ready = safety_readiness(irs, library_has_aois=True)
        self.assertEqual(ready["status"], "READY")
        pack = emit_es_program(
            irs,
            _rung_xml=_rung_xml,
            routine=routine,
            extract_tag_block=extract_tag_block,
            library_text="",
        )
        self.assertIsNotNone(pack)
        xml = pack["program_xml"]
        self.assertIn('Program Name="ES"', xml)
        self.assertIn("JSR(Shipping_ESZone1_Safe_Logic,0);", xml)
        self.assertIn("JSR(Shipping_ESZone1_Safe_PI,0);", xml)
        self.assertIn(
            "ES_SIL1_Cat1(ES201_AOI,ES201,Shipping_Area,Shipping_ESZone1.PI.Reset,Shipping_ESZone1.PI.Silence);",
            xml,
        )
        self.assertIn("ES_PI20(Shipping_ESZone1_ES_PI,Shipping_ESZone1,", xml)
        self.assertIn("NO_ESLS", xml)
        self.assertIn("XIC(Shipping_Area.Reset)OTE(Shipping_ESZone1.PI.Reset);", xml)
        self.assertIn("XIC(Shipping_ESZone1_ES_PI.O_Tripped)OTE(Shipping_ESZone1.PI.Tripped);", xml)
        print("  [PASS] Main_Routine JSRs + SIL1 + PI20 + mappings")

    def test_multi_aggregator_when_over_20(self) -> None:
        members = [f"ES{i:03d}" for i in range(1, 25)]  # 24 devices
        ir = SafetyZoneIR(name="Big_ESZone1", area="Big_Area", members=members)
        ir.ensure_aggregators()
        self.assertEqual(len(ir.aggregator_groups), 2)
        self.assertEqual(ir.aggregator_groups[0].tag, "Big_ESZone1_ES_PI")
        self.assertEqual(ir.aggregator_groups[1].tag, "Big_ESZone1_ES_PI2")
        self.assertEqual(len(ir.aggregator_groups[0].members), ES_PI20_CAPACITY)
        self.assertEqual(len(ir.aggregator_groups[1].members), 4)
        pack = emit_es_program(
            [ir],
            _rung_xml=_rung_xml,
            routine=routine,
            extract_tag_block=extract_tag_block,
            library_text="",
        )
        xml = pack["program_xml"]
        self.assertIn("ES_PI20(Big_ESZone1_ES_PI,Big_ESZone1,", xml)
        self.assertIn("ES_PI20(Big_ESZone1_ES_PI2,Big_ESZone1,", xml)
        print("  [PASS] multi ES_PI20 aggregator groups for >20 members")


def main() -> int:
    print("=== test_es_compiler ===")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestEsCompiler)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("ALL PASS" if result.wasSuccessful() else "FAIL")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

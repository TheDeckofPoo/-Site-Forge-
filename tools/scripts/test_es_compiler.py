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
        "NO_ESLS": '<Tag Name="NO_ESLS" TagType="Base" DataType="ES_UDT" />',
        "ES1000_AOI": '<Tag Name="ES1000_AOI" TagType="Base" DataType="ES_SIL1_Cat1" />',
    }
    return stubs.get(tag_name)


class TestEsCompiler(unittest.TestCase):
    def test_no_area_name_inference(self) -> None:
        zones = build_safety_zone_irs(
            safety_zones=["Shipping_Area_ESZone1"],
            areas=["Shipping_Area"],
            engineer_zones=[],
            estop_model={"zones": []},
        )
        self.assertEqual(zones, [])
        print("  [PASS] does not invent zones from Area names alone")

    def test_emit_main_jsr_and_sil1(self) -> None:
        eng = [
            {
                "name": "Shipping_ESZone1",
                "area": "Shipping_Area",
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

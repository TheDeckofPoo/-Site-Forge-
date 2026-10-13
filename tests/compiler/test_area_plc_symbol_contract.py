#!/usr/bin/env python3
"""P0 Area→PLC symbol contract: display_name ≠ plc_symbol.

Matrix A–D: engineer display Area names must not require a pre-existing
Fortna controller Area tag of the same literal name. Site Forge creates
Area_UDT tags via Main_Area clone using the plc_symbol layer.
"""
from __future__ import annotations

from pathlib import Path as _SFPath
import sys as _SFSys

_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))

import re
import unittest
from pathlib import Path

from fortna_area_symbol import (
    area_canonical_id,
    area_display_name,
    area_plc_symbol,
    collect_area_plc_symbols,
    normalize_area_row,
)
from fortna_es_compiler import (
    SafetyZoneIR,
    build_safety_zone_irs,
    emit_es_program,
)

SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO


def _rung_xml(n: int, logic: str, comment: str = "") -> str:
    c = f'<Comment><![CDATA[{comment}]]></Comment>' if comment else ""
    return f'<Rung Number="{n}" Type="N">{c}<Text><![CDATA[{logic}]]></Text></Rung>'


def routine(name: str, rungs: list[str]) -> str:
    return (
        f'<Routine Name="{name}" Type="RLL">'
        f"<RLLContent>{''.join(rungs)}</RLLContent></Routine>"
    )


def extract_tag_block(library_text: str, name: str) -> str | None:
    m = re.search(
        rf'<Tag\b[^>]*\bName="{re.escape(name)}"[^>]*>.*?</Tag>',
        library_text or "",
        re.DOTALL,
    )
    return m.group(0) if m else None


INLINE_LIBRARY = """<?xml version="1.0" encoding="UTF-8"?>
<RSLogix5000Content SchemaRevision="1.0">
  <Controller>
    <Tags>
      <Tag Name="Main_Area" TagType="Base" DataType="Area_UDT" Constant="false"
           ExternalAccess="Read/Write">
        <Data Format="Decorated"><Structure DataType="Area_UDT"/></Data>
      </Tag>
      <Tag Name="Main_Area_Safe" TagType="Base" DataType="Safe_UDT" Constant="false"
           ExternalAccess="Read/Write">
        <Data Format="Decorated"><Structure DataType="Safe_UDT"/></Data>
      </Tag>
      <Tag Name="Main_Area_Safe_ES_PI" TagType="Base" DataType="ES_PI_UDT" Constant="false"
           ExternalAccess="Read/Write">
        <Data Format="Decorated"><Structure DataType="ES_PI_UDT"/></Data>
      </Tag>
      <Tag Name="NO_ES" TagType="Base" DataType="ES_UDT" Constant="false"
           ExternalAccess="Read/Write">
        <Data Format="Decorated"><Structure DataType="ES_UDT"/></Data>
      </Tag>
      <Tag Name="ES1000_AOI" TagType="Base" DataType="ES_SIL1_Cat1" Constant="false"
           ExternalAccess="Read/Write">
        <Data Format="Decorated"><Structure DataType="ES_SIL1_Cat1"/></Data>
      </Tag>
    </Tags>
  </Controller>
</RSLogix5000Content>
"""

# Matrix A–D from mission brief
MATRIX = [
    # (display_area, zone_name, expected_plc_symbol)
    ("Area_Test1", "Area_Test1_ESZone1", "Area_Test1"),
    ("MSCRENOPICK_AreaTest1", "MSCRENOPICK_AreaTest1_ESZone1", "MSCRENOPICK_AreaTest1"),
    ("Area_1", "Zone_1", "Area_1"),
    ("North Sort", "North_Sort_ESZone1", "North_Sort"),  # spaces → underscore
]


class TestAreaPlcSymbolContract(unittest.TestCase):
    def test_symbol_sanitization_rules(self) -> None:
        self.assertEqual(area_plc_symbol("Area_Test1"), "Area_Test1")
        self.assertEqual(area_plc_symbol("North Sort"), "North_Sort")
        self.assertEqual(area_plc_symbol("Area 1"), "Area_1")
        self.assertEqual(area_plc_symbol("1Sort"), "Area_1Sort")  # digit-leading
        # Never invent controller prefix
        self.assertEqual(area_plc_symbol("Area_Test1"), "Area_Test1")
        self.assertNotIn("MSCRENOPICK", area_plc_symbol("Area_Test1"))

    def test_normalize_preserves_identity_on_display_change(self) -> None:
        row = normalize_area_row(
            {"name": "Area_Test1", "id": "area_stable_xyz", "canonical_area_id": "area_stable_xyz"}
        )
        self.assertEqual(row["display_name"], "Area_Test1")
        self.assertEqual(row["plc_symbol"], "Area_Test1")
        self.assertEqual(row["canonical_area_id"], "area_stable_xyz")
        # Rename display — identity stays, symbol recomputes
        renamed = normalize_area_row(
            {
                "name": "North Sort",
                "display_name": "North Sort",
                "id": "area_stable_xyz",
                "canonical_area_id": "area_stable_xyz",
                "plc_symbol": "Area_Test1",  # stale prior symbol
            }
        )
        self.assertEqual(renamed["canonical_area_id"], "area_stable_xyz")
        self.assertEqual(renamed["plc_symbol"], "North_Sort")
        self.assertEqual(renamed["display_name"], "North Sort")

    def test_collect_includes_zero_conveyor_safety_areas(self) -> None:
        syms = collect_area_plc_symbols(
            areas=[{"name": "MSCRENOPICK_Area"}],
            safety_zones=[
                {
                    "name": "Area_Test1_ESZone1",
                    "area": "Area_Test1",
                    "areaRef": "Area_Test1",
                    "members": ["ESPB2", "ESPB24", "ESPB32", "ESLS2"],
                    "conveyors": [],
                    "engineerEdited": True,
                }
            ],
        )
        self.assertIn("Area_Test1", syms)
        self.assertIn("MSCRENOPICK_Area", syms)

    def test_matrix_a_through_d_emit(self) -> None:
        members = ["ESPB2", "ESPB24", "ESPB32", "ESLS2"]
        for display, zone, expect_sym in MATRIX:
            with self.subTest(display=display, zone=zone):
                eng = [
                    {
                        "name": zone,
                        "engineering_name": zone,
                        "area": display,
                        "areaRef": display,
                        "members": members,
                        "conveyors": [],
                        "engineerEdited": True,
                        "membersOrigin": "ENGINEER_ASSIGNED",
                    }
                ]
                irs = build_safety_zone_irs(
                    engineer_zones=eng,
                    areas=[display],
                    default_area=display,
                )
                self.assertEqual(len(irs), 1, f"IR missing for {display}")
                ir = irs[0]
                self.assertEqual(ir.area, display)  # display preserved
                self.assertEqual(ir.area_plc_symbol, expect_sym)
                self.assertTrue(ir.area_canonical_id)
                self.assertEqual(len(ir.members), 4)
                self.assertEqual(ir.reset_source, f"{expect_sym}.Reset")
                self.assertEqual(ir.silence_source, f"{expect_sym}.Silence")

                pack = emit_es_program(
                    irs,
                    _rung_xml=_rung_xml,
                    routine=routine,
                    extract_tag_block=extract_tag_block,
                    library_text=INLINE_LIBRARY,
                )
                self.assertIsNotNone(pack)
                self.assertFalse(pack.get("shell"), f"shell emit for {display}")
                xml = pack["program_xml"]
                # No PD-0034: every ES_SIL1 uses plc_symbol, never raw spaced display
                self.assertIn(f"ES_SIL1_Cat1(", xml)
                self.assertIn(f",{expect_sym},", xml)
                if display != expect_sym:
                    # Spaced display must NOT appear as InOut operand
                    self.assertNotIn(f",{display},", xml)
                self.assertIn(f"XIC({expect_sym}.Reset)", xml)
                self.assertIn(f"XIC({expect_sym}.Silence)", xml)
                self.assertIn(f"JSR({zone}_Safe_Logic,0);", xml)
                self.assertIn(f"JSR({zone}_Safe_PI,0);", xml)
                self.assertIn(f"{zone}_Safe_Logic", xml)
                self.assertIn(f"{zone}_Safe_PI", xml)
                # Membership conserved — no invented devices
                for m in ("ESPB2", "ESPB24", "ESPB32", "ESLS2"):
                    self.assertIn(m, xml)
                self.assertEqual(len(pack["emitted_zones"]), 1)
                self.assertEqual(pack["zones"][0]["area_plc_symbol"], expect_sym)

    def test_lazy_backfill_on_legacy_ir(self) -> None:
        """Older callers that omit area_plc_symbol still emit legal tags."""
        ir = SafetyZoneIR(
            name="Legacy_ESZone1",
            area="Area Test Legacy",
            members=["ESPB2"],
        )
        pack = emit_es_program(
            [ir],
            _rung_xml=_rung_xml,
            routine=routine,
            extract_tag_block=extract_tag_block,
            library_text=INLINE_LIBRARY,
        )
        xml = pack["program_xml"]
        self.assertIn(",Area_Test_Legacy,", xml)
        self.assertNotIn(",Area Test Legacy,", xml)
        self.assertEqual(ir.area_plc_symbol, "Area_Test_Legacy")


if __name__ == "__main__":
    unittest.main()

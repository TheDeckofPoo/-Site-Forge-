#!/usr/bin/env python3
"""Regression: datatype-aware L5X structured tag serialization vs THIS L5X datatypes."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from fortna_l5x_structured_data import (  # noqa: E402
    emit_comm_udt_tag,
    emit_merge_2to1_tag,
    emit_merge_time_tag,
    parse_datatypes,
    validate_decorated_structure,
    validate_tag_matches_datatype,
)


class TestL5xStructuredData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib = ROOT / "tools/libraries/OReilly_Library_v3.L5X"
        assert lib.is_file(), f"missing library {lib}"
        cls.lib_text = lib.read_text(encoding="utf-8", errors="replace")
        cls.defs = parse_datatypes(cls.lib_text)
        # Prefer datatype defs from latest generated L5X when present
        cands = sorted(
            (ROOT / "exports/current").glob("ORNCCP2*.L5X"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if cands:
            cls.l5x_defs = parse_datatypes(
                cands[0].read_text(encoding="utf-8", errors="replace")
            )
        else:
            cls.l5x_defs = cls.defs

    def test_parse_merge_time_and_comm(self):
        self.assertIn("Merge_Time", self.defs)
        self.assertIn("Comm_UDT", self.defs)
        self.assertIn("String_20", self.defs)

    def test_merge_time_matches_datatype_members(self):
        xml = emit_merge_time_tag("P404_MergeTime", self.l5x_defs)
        self.assertIn("StructureMember", xml)
        self.assertIn('Format="L5K"', xml)
        self.assertNotRegex(xml, r'<Structure DataType="Merge_Time"\s*/>')
        # L5K: ONE outer structure array matching Studio gold / PLC5 P444_MergeTime
        m = re.search(r'Format="L5K"\s*>\s*<!\[CDATA\[(.*?)\]\]>', xml, re.S)
        self.assertIsNotNone(m)
        l5k = (m.group(1) or "").strip()
        self.assertEqual(l5k.count("["), l5k.count("]"))
        self.assertTrue(l5k.startswith("[[0,"), l5k)
        self.assertFalse(l5k.startswith("[[[0,"), "extra L5K wrap rejected by Studio")
        issues = validate_tag_matches_datatype(xml, self.l5x_defs, dt_name="Merge_Time")
        self.assertEqual(issues, [], issues)

    def test_comm_udt_no_bare_empty_string_l5k(self):
        xml = emit_comm_udt_tag("CP2RIO0_Comm", self.l5x_defs)
        self.assertIn('Format="L5K"', xml)
        self.assertNotIn("[0,'']", xml)
        self.assertIn("$00", xml)  # padded empty strings
        self.assertNotIn('DataType="SINT" Dimensions="', xml)
        self.assertNotIn("<![CDATA['']]>", xml)  # bare empty CDATA only
        self.assertIn("<![CDATA[]]>", xml)
        m = re.search(r'Format="L5K"\s*>\s*<!\[CDATA\[(.*?)\]\]>', xml, re.S)
        self.assertIsNotNone(m)
        l5k = (m.group(1) or "").strip()
        self.assertTrue(l5k.startswith("[[0,0,0]"), l5k)
        self.assertFalse(l5k.startswith("[[[0,0,0]"), "extra L5K wrap rejected by Studio")
        issues = validate_decorated_structure(xml, "Comm_UDT")
        self.assertEqual(issues, [])
        issues2 = validate_tag_matches_datatype(xml, self.l5x_defs, dt_name="Comm_UDT")
        self.assertEqual(issues2, [], issues2)

    def test_emitter_matches_library_gold_l5k_shape(self):
        """Compare emitter L5K nesting to library/PLC5 gold (not failing export)."""
        lib_comm = re.search(
            r'<Tag Name="CP2N6_RIO"[^>]*>.*?</Tag>', self.lib_text, re.S
        )
        self.assertIsNotNone(lib_comm)
        gold_l5k = re.search(
            r'Format="L5K"\s*>\s*<!\[CDATA\[(.*?)\]\]>', lib_comm.group(0), re.S
        )
        self.assertIsNotNone(gold_l5k)
        gold = gold_l5k.group(1).strip()
        # Gold starts with [[TIMER... not [[[
        self.assertTrue(gold.startswith("[[0,0,0]"), gold[:80])
        emitted = emit_comm_udt_tag("X", self.defs)
        em = re.search(r'Format="L5K"\s*>\s*<!\[CDATA\[(.*?)\]\]>', emitted, re.S)
        self.assertTrue(em.group(1).strip().startswith("[[0,0,0]"))

    def test_merge_2to1_not_empty_shell(self):
        xml = emit_merge_2to1_tag("P406_Merge")
        self.assertIn("EnableIn", xml)
        self.assertIn('Format="L5K"', xml)
        self.assertNotRegex(xml, r'<Structure DataType="Merge_2to1"\s*/>')

    def test_validate_catches_empty_shell(self):
        bad = '<Structure DataType="Merge_Time"/>'
        issues = validate_decorated_structure(bad, "Merge_Time")
        self.assertTrue(issues)


if __name__ == "__main__":
    unittest.main()

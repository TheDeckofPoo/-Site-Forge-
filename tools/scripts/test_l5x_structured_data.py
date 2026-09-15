#!/usr/bin/env python3
"""Regression: datatype-aware L5X structured tag serialization."""
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
)


class TestL5xStructuredData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lib = ROOT / "tools/libraries/OReilly_Library_v3.L5X"
        assert lib.is_file(), f"missing library {lib}"
        cls.lib_text = lib.read_text(encoding="utf-8", errors="replace")
        cls.defs = parse_datatypes(cls.lib_text)

    def test_parse_merge_time_and_comm(self):
        self.assertIn("Merge_Time", self.defs)
        self.assertIn("Comm_UDT", self.defs)
        self.assertIn("String_20", self.defs)
        mt = self.defs["Merge_Time"]
        names = [m.name for m in mt.members]
        self.assertIn("HMI", names)

    def test_merge_time_not_empty_shell(self):
        xml = emit_merge_time_tag("P404_MergeTime", self.defs)
        self.assertIn("StructureMember", xml)
        self.assertIn("DataValueMember", xml)
        self.assertIn('DataType="Merge_Time_HMI"', xml)
        self.assertNotRegex(xml, r'<Structure DataType="Merge_Time"\s*/>')
        self.assertIn('Format="L5K"', xml)
        issues = validate_decorated_structure(xml, "Merge_Time")
        self.assertEqual(issues, [])

    def test_merge_2to1_not_empty_shell(self):
        xml = emit_merge_2to1_tag("P406_Merge")
        self.assertIn("EnableIn", xml)
        self.assertIn('Format="L5K"', xml)
        self.assertNotRegex(xml, r'<Structure DataType="Merge_2to1"\s*/>')
        self.assertTrue(
            ("StructureMember" in xml) or ("DataValueMember" in xml),
            "Merge_2to1 must emit StructureMember or DataValueMember",
        )

    def test_comm_udt_string_cdata_not_sint_dims(self):
        xml = emit_comm_udt_tag("CP2RIO0_Comm", self.defs)
        self.assertIn('Format="L5K"', xml)
        self.assertIn("MACId", xml)
        self.assertIn("IP_Address", xml)
        self.assertIn("String_20", xml)
        self.assertNotIn('DataType="SINT" Dimensions="20"', xml)
        self.assertNotIn('DataType="SINT" Dimensions="15"', xml)
        self.assertIn("CDATA", xml)
        issues = validate_decorated_structure(xml, "Comm_UDT")
        self.assertEqual(issues, [])

    def test_validate_catches_empty_shell(self):
        bad = '<Structure DataType="Merge_Time"/>'
        issues = validate_decorated_structure(bad, "Merge_Time")
        self.assertTrue(issues)


if __name__ == "__main__":
    unittest.main()

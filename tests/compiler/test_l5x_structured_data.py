#!/usr/bin/env python3
"""Regression: datatype-aware L5X structured tag serialization vs THIS L5X datatypes."""
from __future__ import annotations
# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys
_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / 'tools' / 'scripts'
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
# Prefer canonical names used by existing tests:
SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO
REPO_ROOT = _SF_REPO
# --- end bootstrap ---


import re
import sys
import unittest
from pathlib import Path

SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from fortna_l5x_structured_data import (  # noqa: E402
    DEFAULT_REWRITE_STRUCTURED_TYPES,
    emit_comm_udt_tag,
    emit_decorated_structure,
    emit_merge_2to1_tag,
    emit_merge_time_tag,
    extract_decorated_values,
    parse_datatypes,
    rewrite_l5x_structured_decorated,
    rewrite_tag_decorated_from_datatype,
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
        # Studio export oracle: DATA DataType = parent StringFamily name (not SINT).
        self.assertIn('Name="DATA" DataType="String_20"', xml)
        self.assertIn('Name="DATA" DataType="String_15"', xml)
        self.assertNotIn('Name="DATA" DataType="SINT"', xml)
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

    def test_track_divert_udt_member_order_matches_datatype(self):
        self.assertIn("Track_Divert_UDT", self.defs)
        deco = emit_decorated_structure("Track_Divert_UDT", self.defs, strict=True)
        self.assertTrue(deco)
        self.assertIn('<ArrayMember Name="Run"', deco)
        self.assertIn('<ArrayMember Name="Search_Timing_History"', deco)
        tag = (
            f'<Tag Name="P506_Divert1" TagType="Base" DataType="Track_Divert_UDT" '
            f'Constant="false" ExternalAccess="Read/Write">'
            f'<Data Format="Decorated">{deco}</Data></Tag>'
        )
        issues = validate_tag_matches_datatype(
            tag, self.defs, dt_name="Track_Divert_UDT", require_l5k=False
        )
        self.assertEqual(issues, [], issues)
        from fortna_l5x_structured_data import _top_level_decorated_members

        expected = [
            m.name
            for m in self.defs["Track_Divert_UDT"].members
            if not (m.hidden and m.name.startswith("ZZZZ"))
        ]
        self.assertEqual(
            expected[:6], ["CFG", "PI", "O", "HMI", "Limit_Timer", "DCPE_Stats"]
        )
        inner = re.search(
            r'<Structure DataType="Track_Divert_UDT">(.*)</Structure>', deco, re.S
        ).group(1)
        got = [n for n, _t in _top_level_decorated_members(inner)]
        self.assertEqual(got, expected, got)
    def test_area_udt_member_order_matches_datatype(self):
        self.assertIn("Area_UDT", self.defs)
        deco = emit_decorated_structure("Area_UDT", self.defs, strict=True)
        self.assertIn('Name="EngMgmt"', deco)  # Area_PI first BIT in library
        tag = (
            f'<Tag Name="ShippingSorter_Area" TagType="Base" DataType="Area_UDT" '
            f'Constant="false" ExternalAccess="Read/Write">'
            f'<Data Format="Decorated">{deco}</Data></Tag>'
        )
        issues = validate_tag_matches_datatype(
            tag, self.defs, dt_name="Area_UDT", require_l5k=False
        )
        self.assertEqual(issues, [], issues)
        expected = [
            m.name
            for m in self.defs["Area_UDT"].members
            if not (m.hidden and m.name.startswith("ZZZZ"))
        ]
        self.assertEqual(expected[0], "HMI")
        self.assertEqual(expected[1], "PI")

    def test_rewrite_preserves_divert_values_and_fills_missing_members(self):
        """Pack Decorated missing newer Divert_HMI bits → rewrite from library datatype."""
        stale = (
            '<Tag Name="P506_Divert1" TagType="Base" DataType="Track_Divert_UDT" '
            'Constant="false" ExternalAccess="Read/Write">'
            '<Data Format="L5K"><![CDATA[[[0]]]]></Data>'
            '<Data Format="Decorated"><Structure DataType="Track_Divert_UDT">'
            '<StructureMember Name="CFG" DataType="Divert_CFG">'
            '<StructureMember Name="Name" DataType="Location_String">'
            '<DataValueMember Name="LEN" DataType="DINT" Radix="Decimal" Value="12"/>'
            '<DataValueMember Name="DATA" DataType="Location_String" Radix="ASCII">'
            "<![CDATA['P504_Divert1']]></DataValueMember></StructureMember>"
            '<DataValueMember Name="Lane_Number" DataType="INT" Radix="Decimal" Value="1"/>'
            "</StructureMember>"
            '<StructureMember Name="PI" DataType="Divert_PI">'
            '<DataValueMember Name="Full" DataType="BOOL" Value="0"/>'
            '<DataValueMember Name="RIO_Fault" DataType="BOOL" Value="0"/>'
            "</StructureMember>"
            "</Structure></Data></Tag>"
        )
        out = rewrite_tag_decorated_from_datatype(
            stale, self.defs, dt_name="Track_Divert_UDT", strip_l5k=True
        )
        self.assertNotIn('Format="L5K"', out)
        self.assertIn("P504_Divert1", out)
        self.assertIn('Name="Lane_Number"', out)
        self.assertIn('Value="1"', out)
        # Library Divert_HMI has DivertCommission — must appear after rewrite
        self.assertIn('Name="DivertCommission"', out)
        issues = validate_tag_matches_datatype(
            out, self.defs, dt_name="Track_Divert_UDT", require_l5k=False
        )
        self.assertEqual(issues, [], issues)
        vals = extract_decorated_values(
            re.search(r'<Data Format="Decorated">(.*)</Data>', out, re.S).group(1)
        )
        self.assertEqual(vals.get("CFG", {}).get("Lane_Number"), 1)
        # Nested Location_String DATA uses parent StringFamily name (Studio export).
        self.assertRegex(
            out,
            r'<DataValueMember Name="DATA" DataType="Location_String" Radix="ASCII">',
        )
        self.assertNotRegex(
            out, r'<DataValueMember Name="DATA" DataType="SINT"'
        )

    def _assert_nested_string_data_is_parent(self, xml: str, parent: str) -> None:
        """Decorated DATA DataType attribute equals parent StringFamily name."""
        matches = re.findall(
            r'<StructureMember\s+Name="[^"]+"\s+DataType="'
            + re.escape(parent)
            + r'"[^>]*>(.*?)</StructureMember>',
            xml,
            re.S,
        )
        if not matches:
            # Root StringFamily emit (no StructureMember wrapper)
            matches = [xml]
        found = False
        for inner in matches:
            data_m = re.search(
                r'<DataValueMember Name="DATA" DataType="([^"]+)"', inner
            )
            if not data_m:
                continue
            found = True
            self.assertEqual(
                data_m.group(1),
                parent,
                f"DATA DataType must be parent {parent}, got {data_m.group(1)}",
            )
            self.assertNotIn('DataType="SINT"', data_m.group(0))
        self.assertTrue(found, f"expected DATA member for {parent}")

    def test_nested_custom_string_type_data_is_parent_name(self):
        """UDT with nested custom STRING type → DATA DataType = parent name."""
        fixture = """
        <DataType Name="String_20" Family="StringFamily" Class="User">
          <Members>
            <Member Name="LEN" DataType="DINT" Dimension="0" Radix="Decimal"/>
            <Member Name="DATA" DataType="SINT" Dimension="20" Radix="ASCII"/>
          </Members>
        </DataType>
        <DataType Name="Holder_UDT" Family="NoFamily" Class="User">
          <Members>
            <Member Name="Label" DataType="String_20" Dimension="0"/>
          </Members>
        </DataType>
        """
        defs = parse_datatypes(fixture)
        deco = emit_decorated_structure("Holder_UDT", defs, strict=True)
        self.assertIn('StructureMember Name="Label" DataType="String_20"', deco)
        self._assert_nested_string_data_is_parent(deco, "String_20")
        self.assertIn('Name="LEN" DataType="DINT"', deco)

    def test_multiple_nested_string_types_data_is_parent_name(self):
        """Multiple nested STRING types → each DATA uses its parent type name."""
        fixture = """
        <DataType Name="String_20" Family="StringFamily" Class="User">
          <Members>
            <Member Name="LEN" DataType="DINT" Dimension="0"/>
            <Member Name="DATA" DataType="SINT" Dimension="20" Radix="ASCII"/>
          </Members>
        </DataType>
        <DataType Name="String_15" Family="StringFamily" Class="User">
          <Members>
            <Member Name="LEN" DataType="DINT" Dimension="0"/>
            <Member Name="DATA" DataType="SINT" Dimension="15" Radix="ASCII"/>
          </Members>
        </DataType>
        <DataType Name="Dual_String_UDT" Family="NoFamily" Class="User">
          <Members>
            <Member Name="MACId" DataType="String_20" Dimension="0"/>
            <Member Name="IP_Address" DataType="String_15" Dimension="0"/>
          </Members>
        </DataType>
        """
        defs = parse_datatypes(fixture)
        deco = emit_decorated_structure("Dual_String_UDT", defs, strict=True)
        self.assertIn('Name="DATA" DataType="String_20"', deco)
        self.assertIn('Name="DATA" DataType="String_15"', deco)
        self.assertNotRegex(
            deco, r'<DataValueMember Name="DATA" DataType="SINT"'
        )

    def test_scanner_style_barcode_string_data_is_parent_name(self):
        """Scanner-style UDT (Barcode_String) → DATA DataType = Barcode_String."""
        fixture = """
        <DataType Name="Barcode_String" Family="StringFamily" Class="User">
          <Members>
            <Member Name="LEN" DataType="DINT" Dimension="0"/>
            <Member Name="DATA" DataType="SINT" Dimension="82" Radix="ASCII"/>
          </Members>
        </DataType>
        <DataType Name="Scanner_Style_UDT" Family="NoFamily" Class="User">
          <Members>
            <Member Name="RawData" DataType="Barcode_String" Dimension="0"/>
            <Member Name="Barcode" DataType="Barcode_String" Dimension="0"/>
            <Member Name="Barcode_Last" DataType="Barcode_String" Dimension="0"/>
          </Members>
        </DataType>
        """
        defs = parse_datatypes(fixture)
        deco = emit_decorated_structure(
            "Scanner_Style_UDT",
            defs,
            values={"Barcode": "ABC123"},
            strict=True,
        )
        self.assertEqual(deco.count('Name="DATA" DataType="Barcode_String"'), 3)
        self.assertNotIn('Name="DATA" DataType="SINT"', deco)
        self.assertIn("<![CDATA['ABC123']]>", deco)
        self.assertIn('Name="LEN" DataType="DINT" Radix="Decimal" Value="6"', deco)

    def test_comm_udt_style_string_data_is_parent_name(self):
        """Comm_UDT-style nested String_20/String_15 → DATA uses parent names."""
        deco = emit_decorated_structure("Comm_UDT", self.defs, strict=True)
        self.assertIn('Name="DATA" DataType="String_20"', deco)
        self.assertIn('Name="DATA" DataType="String_15"', deco)
        self.assertNotIn('Name="DATA" DataType="SINT"', deco)
        issues = validate_decorated_structure(deco, "Comm_UDT")
        self.assertEqual(issues, [], issues)

    def test_nonzero_initialized_string_data_is_parent_name(self):
        """Nonzero initialized string keeps payload; DATA DataType = parent name."""
        fixture = """
        <DataType Name="String_20" Family="StringFamily" Class="User">
          <Members>
            <Member Name="LEN" DataType="DINT" Dimension="0"/>
            <Member Name="DATA" DataType="SINT" Dimension="20" Radix="ASCII"/>
          </Members>
        </DataType>
        <DataType Name="Named_UDT" Family="NoFamily" Class="User">
          <Members>
            <Member Name="Name" DataType="String_20" Dimension="0"/>
          </Members>
        </DataType>
        """
        defs = parse_datatypes(fixture)
        deco = emit_decorated_structure(
            "Named_UDT", defs, values={"Name": "P504_SCN"}, strict=True
        )
        self.assertIn('Name="DATA" DataType="String_20"', deco)
        self.assertIn('Value="8"', deco)
        self.assertIn("<![CDATA['P504_SCN']]>", deco)

    def test_empty_initialized_string_data_is_parent_name(self):
        """Empty initialized string uses bare CDATA; DATA DataType = parent name."""
        fixture = """
        <DataType Name="String_15" Family="StringFamily" Class="User">
          <Members>
            <Member Name="LEN" DataType="DINT" Dimension="0"/>
            <Member Name="DATA" DataType="SINT" Dimension="15" Radix="ASCII"/>
          </Members>
        </DataType>
        <DataType Name="Empty_String_UDT" Family="NoFamily" Class="User">
          <Members>
            <Member Name="IP" DataType="String_15" Dimension="0"/>
          </Members>
        </DataType>
        """
        defs = parse_datatypes(fixture)
        deco = emit_decorated_structure("Empty_String_UDT", defs, strict=True)
        self.assertIn('Name="DATA" DataType="String_15"', deco)
        self.assertIn('Value="0"', deco)
        self.assertIn("<![CDATA[]]>", deco)
        self.assertNotIn("<![CDATA['']]>", deco)

    def test_decorated_data_datatype_attr_equals_parent_not_sint(self):
        """Decorated DATA DataType attribute equals parent StringFamily name."""
        for dt_name in (
            "String_20",
            "String_15",
            "Barcode_String",
            "Location_String",
        ):
            with self.subTest(dt=dt_name):
                self.assertIn(dt_name, self.defs)
                deco = emit_decorated_structure(dt_name, self.defs, strict=True)
                self.assertIn(f'DataType="{dt_name}" Radix="ASCII"', deco)
                self.assertNotIn('DataType="SINT"', deco)

    def test_sanitize_rewrite_regenerates_comm_and_barcode_scanner(self):
        """rewrite path regenerates Comm_UDT / Barcode_Scanner_UDT Decorated from datatype."""
        self.assertIn("Comm_UDT", DEFAULT_REWRITE_STRUCTURED_TYPES)
        self.assertIn("Barcode_Scanner_UDT", DEFAULT_REWRITE_STRUCTURED_TYPES)
        stale = (
            '<Controller>'
            '<DataTypes>'
            + re.search(
                r'<DataType Name="String_20".*?</DataType>', self.lib_text, re.S
            ).group(0)
            + re.search(
                r'<DataType Name="String_15".*?</DataType>', self.lib_text, re.S
            ).group(0)
            + re.search(
                r'<DataType Name="Barcode_String".*?</DataType>', self.lib_text, re.S
            ).group(0)
            + re.search(
                r'<DataType Name="Comm_Flt".*?</DataType>', self.lib_text, re.S
            ).group(0)
            + re.search(
                r'<DataType Name="Comm_UDT".*?</DataType>', self.lib_text, re.S
            ).group(0)
            + re.search(
                r'<DataType Name="Scanner_Flt".*?</DataType>', self.lib_text, re.S
            ).group(0)
            + re.search(
                r'<DataType Name="Barcode_Scanner_UDT".*?</DataType>',
                self.lib_text,
                re.S,
            ).group(0)
            + "</DataTypes>"
            '<Tags>'
            '<Tag Name="T_Comm" TagType="Base" DataType="Comm_UDT" '
            'Constant="false" ExternalAccess="Read/Write">'
            '<Data Format="L5K"><![CDATA[[[0,0,0],[0],0,0.00000000e+000,'
            "[0,'$00$00$00$00$00$00$00$00$00$00$00$00$00$00$00$00$00$00$00$00'],"
            "[0,'$00$00$00$00$00$00$00$00$00$00$00$00$00$00$00']]]]></Data>"
            '<Data Format="Decorated"><Structure DataType="Comm_UDT">'
            '<StructureMember Name="MACId" DataType="String_20">'
            '<DataValueMember Name="LEN" DataType="DINT" Radix="Decimal" Value="0"/>'
            '<DataValueMember Name="DATA" DataType="SINT" Dimensions="20" Radix="ASCII">'
            "<![CDATA[]]></DataValueMember></StructureMember>"
            "</Structure></Data></Tag>"
            '<Tag Name="T_Scan" TagType="Base" DataType="Barcode_Scanner_UDT" '
            'Constant="false" ExternalAccess="Read/Write">'
            '<Data Format="Decorated"><Structure DataType="Barcode_Scanner_UDT">'
            '<StructureMember Name="RawData" DataType="Barcode_String">'
            '<DataValueMember Name="LEN" DataType="DINT" Radix="Decimal" Value="0"/>'
            '<DataValueMember Name="DATA" DataType="SINT" Dimensions="82" Radix="ASCII">'
            "<![CDATA[]]></DataValueMember></StructureMember>"
            "</Structure></Data></Tag>"
            "</Tags></Controller>"
        )
        out = rewrite_l5x_structured_decorated(stale, strip_l5k=True)
        # Comm keeps L5K; nested Decorated DATA rewritten to parent StringFamily names.
        # DataTypeDef Member DATA remains SINT[N] — only Decorated DataValueMember changes.
        self.assertIn('DataType="Comm_UDT"', out)
        self.assertIn('Format="L5K"', out)
        self.assertIn('DataValueMember Name="DATA" DataType="String_20"', out)
        self.assertIn('DataValueMember Name="DATA" DataType="String_15"', out)
        self.assertNotIn('DataValueMember Name="DATA" DataType="SINT"', out)
        self.assertIn('DataValueMember Name="DATA" DataType="Barcode_String"', out)
        # Full member expansion from datatype (not stale partial shell).
        self.assertIn('Name="CommLoss_Tmr"', out)
        self.assertIn('Name="RelativeOffsetHistory"', out)


if __name__ == "__main__":
    unittest.main()

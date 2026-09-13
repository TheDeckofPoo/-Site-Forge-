#!/usr/bin/env python3
"""Part B: Sawtooth enable gates must emit from workbook sawtooth_build.

Gold Sawtooth_Merge XICs Enable_Merge2_Trk / Enable_Merge1_Reserv / Use_GapStore_Belts
but the pack never defines those tags. Studio build must emit them when the pack is
included and sawtooth_build is configured.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

AUTOGEN_SRC = (SCRIPTS / "fortna_autogen.py").read_text(encoding="utf-8")


class TestSawtoothEnableTagsSource(unittest.TestCase):
    """Unit/source checks — emit path exists without requiring a full CP4 build."""

    def test_builder_and_wire_in_autogen_source(self):
        self.assertIn("def build_sawtooth_enable_tag_blocks", AUTOGEN_SRC)
        self.assertIn("Enable_Merge2_Trk", AUTOGEN_SRC)
        self.assertIn("Enable_Merge1_Reserv", AUTOGEN_SRC)
        self.assertIn("Use_GapStore_Belts", AUTOGEN_SRC)
        self.assertIn("ENGINEER_CONFIGURED workbook enable_track", AUTOGEN_SRC)
        # Emit gated on pack + configured workbook
        self.assertIn('Sawtooth_Merge" in gold_program_names', AUTOGEN_SRC)
        self.assertIn("sawtooth_build_is_configured(saw_cfg_live)", AUTOGEN_SRC)
        # Assertion fail-closed on missing enable tag
        self.assertIn('Tag Name="Enable_Merge2_Trk"', AUTOGEN_SRC)
        self.assertIn("Enable_Merge2_Trk tag missing from L5X", AUTOGEN_SRC)
        # Param/semantics deepen deferred intentionally
        self.assertIn("TODO(Part B deepen)", AUTOGEN_SRC)
        self.assertIn("parameterize_sawtooth_pack", AUTOGEN_SRC)
        # DataTypes inject preserved
        self.assertIn("SAWTOOTH_MERGE_DATATYPES", AUTOGEN_SRC)
        self.assertIn("Sawtooth_Merge_DataTypes.L5X", AUTOGEN_SRC)

    def test_build_sawtooth_enable_tag_blocks_defaults(self):
        from fortna_autogen import build_sawtooth_enable_tag_blocks

        blocks = build_sawtooth_enable_tag_blocks(
            {"collector_conveyor": "P414", "enable_track": True, "enable_reserve": True}
        )
        blob = "".join(blocks)
        self.assertEqual(len(blocks), 3)
        self.assertIn('Tag Name="Enable_Merge2_Trk"', blob)
        self.assertIn('Tag Name="Enable_Merge1_Reserv"', blob)
        self.assertIn('Tag Name="Use_GapStore_Belts"', blob)
        # Defaults: track/reserve on, gapstore off
        self.assertRegex(blob, re.compile(r'Tag Name="Enable_Merge2_Trk"[^>]*>.*?Value="1"', re.S))
        self.assertRegex(blob, re.compile(r'Tag Name="Enable_Merge1_Reserv"[^>]*>.*?Value="1"', re.S))
        self.assertRegex(blob, re.compile(r'Tag Name="Use_GapStore_Belts"[^>]*>.*?Value="0"', re.S))
        self.assertIn("ENGINEER_CONFIGURED", blob)
        for block in blocks:
            m = re.search(r"<Description><!\[CDATA\[(.*?)\]\]></Description>", block)
            self.assertIsNotNone(m)
            self.assertLessEqual(len(m.group(1)), 128)

    def test_build_sawtooth_enable_tag_blocks_explicit_off_and_gapstore(self):
        from fortna_autogen import build_sawtooth_enable_tag_blocks

        blocks = build_sawtooth_enable_tag_blocks(
            {
                "collector_conveyor": "P414",
                "enable_track": False,
                "enable_reserve": False,
                "use_gapstore": True,
            }
        )
        blob = "".join(blocks)
        self.assertRegex(blob, re.compile(r'Tag Name="Enable_Merge2_Trk"[^>]*>.*?Value="0"', re.S))
        self.assertRegex(blob, re.compile(r'Tag Name="Enable_Merge1_Reserv"[^>]*>.*?Value="0"', re.S))
        self.assertRegex(blob, re.compile(r'Tag Name="Use_GapStore_Belts"[^>]*>.*?Value="1"', re.S))

    def test_assertion_fails_without_enable_tag(self):
        from fortna_autogen import AutogenInput, _generation_assertion_failures

        inp = AutogenInput(
            project_name="ORNCCP4",
            include_programs=["Sawtooth_Merge"],
            sawtooth_build={"collector_conveyor": "P414", "enable_track": True},
            include_io_map=False,
        )
        report = {
            "programs": ["Sawtooth_Merge"],
            "gold_programs": ["Sawtooth_Merge"],
            "io_map_mapped": 0,
            "pe_logic_rungs": 0,
            "conveyor_count": 0,
        }
        fails = _generation_assertion_failures(
            inp,
            report,
            mappable_io_count=0,
            l5x_text='<Program Name="Sawtooth_Merge"/>',  # no Enable tag
        )
        self.assertTrue(
            any("Enable_Merge2_Trk tag missing" in f for f in fails),
            fails,
        )

    def test_assertion_ok_when_enable_tag_present(self):
        from fortna_autogen import AutogenInput, _generation_assertion_failures

        inp = AutogenInput(
            project_name="ORNCCP4",
            include_programs=["Sawtooth_Merge"],
            sawtooth_build={"collector_conveyor": "P414"},
            include_io_map=False,
        )
        report = {
            "programs": ["Sawtooth_Merge"],
            "gold_programs": ["Sawtooth_Merge"],
            "io_map_mapped": 0,
            "pe_logic_rungs": 0,
            "conveyor_count": 0,
        }
        l5x = (
            '<Tags><Tag Name="Enable_Merge2_Trk" TagType="Base" DataType="BOOL">'
            '<Data Format="Decorated"><DataValue DataType="BOOL" Value="1"/></Data>'
            "</Tag></Tags>"
        )
        fails = _generation_assertion_failures(
            inp, report, mappable_io_count=0, l5x_text=l5x
        )
        self.assertFalse(
            any("Enable_Merge2_Trk" in f for f in fails),
            fails,
        )


class TestSawtoothEnableTagsOptionalSmoke(unittest.TestCase):
    """Optional CP4 workbook smoke — skipped when fixtures unavailable."""

    def test_cp4_workbook_emit_if_available(self):
        from fortna_autogen import (
            AutogenInput,
            DEFAULT_LIBRARY,
            build_l5x,
            build_sawtooth_enable_tag_blocks,
            sawtooth_build_is_configured,
        )

        wb_path = ROOT / "exports/plc2-validation/_sawtooth_apply_wb.json"
        lib = Path(DEFAULT_LIBRARY)
        if not lib.is_file():
            lib = ROOT / "tools/libraries/OReilly_Library_v3.L5X"
        pack = ROOT / "tools/libraries/programs/Sawtooth_Merge_Program.L5X"
        if not wb_path.is_file() or not lib.is_file() or not pack.is_file():
            self.skipTest("CP4 workbook / library / Sawtooth pack not available")

        wb = json.loads(wb_path.read_text(encoding="utf-8"))
        saw = dict(wb.get("sawtooth_build") or {})
        self.assertTrue(sawtooth_build_is_configured(saw))

        blocks = build_sawtooth_enable_tag_blocks(saw)
        self.assertTrue(any('Name="Enable_Merge2_Trk"' in b for b in blocks))

        inp = AutogenInput(
            project_name=str(wb.get("project_name") or "ORNCCP4"),
            machine=str(wb.get("machine") or "ORNCCP4"),
            conveyors=[],
            include_programs=["Sawtooth_Merge"],
            sawtooth_build=saw,
            include_io_map=False,
        )
        l5x, report = build_l5x(inp, lib)
        self.assertIn('Tag Name="Enable_Merge2_Trk"', l5x)
        self.assertIn('Tag Name="Enable_Merge1_Reserv"', l5x)
        self.assertIn('Tag Name="Use_GapStore_Belts"', l5x)
        self.assertRegex(l5x, re.compile(r'Tag Name="Enable_Merge2_Trk"[^>]*>.*?Value="1"', re.S))
        en = (report or {}).get("sawtooth_enable_tags") or {}
        self.assertTrue(en.get("emitted"), en)
        asserts = (report or {}).get("generation_assertions") or {}
        self.assertFalse(
            any("Enable_Merge2_Trk" in f for f in (asserts.get("failures") or [])),
            asserts,
        )


if __name__ == "__main__":
    unittest.main()

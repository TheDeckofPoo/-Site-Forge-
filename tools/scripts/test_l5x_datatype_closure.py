#!/usr/bin/env python3
"""Regression: DataType closure + Sawtooth ST_* types + Git provenance rule."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTOGEN = (ROOT / "tools/scripts/fortna_autogen.py").read_text(encoding="utf-8")
ST_TYPES = ROOT / "tools/libraries/programs/Sawtooth_Merge_DataTypes.L5X"


class TestL5xDatatypeClosure(unittest.TestCase):
    def test_sawtooth_datatypes_fragment_exists(self):
        self.assertTrue(ST_TYPES.is_file(), "Sawtooth_Merge_DataTypes.L5X required")
        text = ST_TYPES.read_text(encoding="utf-8", errors="replace")
        for name in (
            "ST_CollStatus",
            "ST_SlugBuildCtrl",
            "SawMergeHMI_UDT",
            "ST_UnlCnvCtrl",
        ):
            self.assertIn(f'DataType Name="{name}"', text)

    def test_autogen_loads_sawtooth_datatypes(self):
        self.assertIn("SAWTOOTH_MERGE_DATATYPES", AUTOGEN)
        self.assertIn("Sawtooth_Merge_DataTypes.L5X", AUTOGEN)
        self.assertIn("_close_datatype_member_deps", AUTOGEN)
        self.assertIn("FBD_TIMER", AUTOGEN)

    def test_integrity_checks_unresolved_tag_datatypes(self):
        self.assertIn("unresolved_tag_datatypes", AUTOGEN)
        self.assertIn("unresolved_datatype_members", AUTOGEN)
        self.assertIn(
            "Studio will open controller name but discard Tags/Programs", AUTOGEN
        )

    def test_git_provenance_mismatch_is_failure(self):
        self.assertIn("does not match build", AUTOGEN)
        self.assertIn("git_in_l5x", AUTOGEN)

    def test_controller_description_max_128(self):
        """Studio aborts L5X import if Controller Description > 128 chars."""
        self.assertIn("Studio max 128", AUTOGEN)
        self.assertIn("controller_description_len", AUTOGEN)
        # Prov desc must be built short — not the old 6-field pipe join
        self.assertNotIn('prov_desc = " | ".join(prov_lines[:6])', AUTOGEN)

    def test_latest_fixed_l5x_if_present(self):
        cur = ROOT / "exports/current"
        cands = sorted(cur.glob("ORNCCP4_*.L5X"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not cands:
            self.skipTest("no ORNCCP4 L5X in exports/current")
        text = cands[0].read_text(encoding="utf-8", errors="replace")
        # Prefer builds that include Sawtooth
        if "Sawtooth_Merge" not in text:
            self.skipTest("latest ORNCCP4 L5X has no Sawtooth_Merge")
        self.assertRegex(text, r'<DataType Name="ST_CollStatus"')
        self.assertRegex(text, r'<DataType Name="ST_SlugBuildCtrl"')
        self.assertNotRegex(text, r'<DataType Name="Divert_CFG"')
        # No unresolved tag types among Sawtooth ST_
        dt = set(re.findall(r'<DataType Name="([^"]+)"', text))
        aoi = set(
            re.findall(
                r'(?:EncodedData EncodedType="AddOnInstructionDefinition"|AddOnInstructionDefinition)'
                r'[^>]*Name="([^"]+)"',
                text,
            )
        )
        tag_types = set(
            re.findall(r'<Tag Name="[^"]+" TagType="Base" DataType="([^"]+)"', text)
        )
        missing = [
            t
            for t in tag_types
            if t.startswith("ST_") and t not in dt and t not in aoi
        ]
        self.assertEqual(missing, [], f"missing ST_ DataTypes for tags: {missing}")


if __name__ == "__main__":
    unittest.main()

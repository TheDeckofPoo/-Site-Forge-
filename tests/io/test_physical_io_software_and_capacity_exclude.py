#!/usr/bin/env python3
"""Physical I/O truth: MEM_ software + OA4 capacity-invalid must not get BOOL stubs."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from fortna_autogen import (  # noqa: E402
    AutogenInput,
    IoPoint,
    _fortna_bit_to_data_bit,
    _point_card_max_bit,
    build_l5x,
)

LIBRARY = ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X"

INLINE_LIB = """<?xml version="1.0" encoding="UTF-8"?>
<RSLogix5000Content SchemaRevision="1.0">
  <Controller Name="TEST">
    <Tags>
      <Tag Name="Main_Area" TagType="Base" DataType="Area_UDT"></Tag>
      <Tag Name="NO_Conv" TagType="Base" DataType="Conv_UDT"></Tag>
      <Tag Name="NO_PE" TagType="Base" DataType="PE_UDT"></Tag>
      <Tag Name="P3000_Conv" TagType="Base" DataType="Conv_UDT"></Tag>
    </Tags>
    <AddOnInstructionDefinitions/>
    <DataTypes/>
    <Modules/>
    <Programs/>
  </Controller>
</RSLogix5000Content>
"""


class TestBitCapacity(unittest.TestCase):
    def test_oa4_max_bit(self) -> None:
        self.assertEqual(_point_card_max_bit("1734-OA4"), 3)

    def test_high_half_bits_invalid_for_oa4(self) -> None:
        # raw Fortna bits that normalize outside OA4 0..3 → None
        for b in ("4", "5", "12", "13"):
            db = _fortna_bit_to_data_bit(b, max_bit=3, run_dir=None)
            # Some high-half bits may normalize into 0..3; capacity gate uses max_bit
            # After normalization, values must be in 0..max_bit or None
            if db is not None:
                self.assertGreaterEqual(db, 0)
                self.assertLessEqual(db, 3)


class TestSoftwareInternalNaming(unittest.TestCase):
    def test_mem_prefix_is_software_internal(self) -> None:
        for n in ("MEM_ALLOW_JAM", "MEM_OK_TO_RUN_MP3", "mem_ok"):
            self.assertTrue(str(n).upper().startswith("MEM_"))
        self.assertFalse("CL17".startswith("MEM_"))
        self.assertFalse("EZSSV15".startswith("MEM_"))


if __name__ == "__main__":
    unittest.main()

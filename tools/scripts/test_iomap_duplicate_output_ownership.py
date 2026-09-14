#!/usr/bin/env python3
"""Regression: one physical OUTPUT bit = one logical owner.

Reproduces the PLC2 INT229 vs M402 collision on CP2RIO0:O.Data[6].6 and
asserts:
  - INT### want_dir is I (interlock sense)
  - configio_physical for bank 207 is I.Data[7], bank 206 is O.Data[6]
  - studio preflight still ERROR-blocks duplicate OTE targets
  - autogen _io_point_want_dir + physical resolve do not cross-map 207→206
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_autogen import _io_point_want_dir  # noqa: E402
from fortna_physical_word_resolver import build_physical_word_map, resolve_word_bit  # noqa: E402
from fortna_studio_preflight import _check_iomap_duplicate_otes  # noqa: E402

RUN = ROOT / "workspace" / "active" / "RUN"
TARGET = "CP2RIO0:O.Data[6].6"


class TestIoMapDuplicateOutputOwnership(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not RUN.exists():
            raise unittest.SkipTest(f"PLC2 RUN missing: {RUN}")
        cls.pm = build_physical_word_map(RUN, "ORNCCP2")

    def test_int229_want_dir_is_input(self) -> None:
        self.assertEqual(_io_point_want_dir("INT229", "motor", "O"), "I")
        self.assertEqual(_io_point_want_dir("M402", "motor", "O"), "O")
        self.assertEqual(_io_point_want_dir("M402_AUX", "motor", "O"), "I")
        print("  [PASS] INT229 want_dir=I; M402 want_dir=O; AUX=I")

    def test_physical_banks_do_not_collide(self) -> None:
        m402 = resolve_word_bit(self.pm, 206, 6)
        int229 = resolve_word_bit(self.pm, 207, 6)
        self.assertIsNotNone(m402)
        self.assertIsNotNone(int229)
        self.assertEqual(m402.get("channel"), TARGET)
        self.assertEqual(m402.get("direction"), "O")
        self.assertEqual(int229.get("channel"), "CP2RIO0:I.Data[7].6")
        self.assertEqual(int229.get("direction"), "I")
        self.assertNotEqual(m402.get("channel"), int229.get("channel"))
        print("  [PASS] M402→O.Data[6].6 ; INT229→I.Data[7].6 (no collision)")

    def test_preflight_still_blocks_duplicate_ote(self) -> None:
        # Minimal IO_MAP with two writers of the same OUTPUT bit — must ERROR.
        l5x = f"""<?xml version="1.0"?>
<RSLogix5000Content>
  <Controller>
    <Programs>
      <Program Name="IO_MAP">
        <Routines>
          <Routine Name="CP_O" Type="RLL">
            <RLLContent>
              <Rung Number="1" Type="N">
                <Comment><![CDATA[INT229 · Bank207.6 · via bad resolve]]></Comment>
                <Text><![CDATA[XIC(INT229)OTE({TARGET});]]></Text>
              </Rung>
              <Rung Number="2" Type="N">
                <Comment><![CDATA[M402 · Bank206.6 · 1794-OA8I]]></Comment>
                <Text><![CDATA[XIC(P402_Conv.O.Run)OTE({TARGET});]]></Text>
              </Rung>
            </RLLContent>
          </Routine>
        </Routines>
      </Program>
    </Programs>
  </Controller>
</RSLogix5000Content>
"""
        findings: list[dict] = []

        def add(sev, kind, message, **extra):
            findings.append({"severity": sev, "kind": kind, "message": message, **extra})

        _check_iomap_duplicate_otes(l5x, add)
        dups = [f for f in findings if f.get("kind") == "iomap_duplicate_ote"]
        self.assertTrue(dups, f"expected duplicate OTE blocker, got {findings}")
        self.assertTrue(any(TARGET in (f.get("message") or "") for f in dups))
        # Writers should be named in the message
        msg = dups[0]["message"]
        self.assertIn("INT229", msg)
        self.assertIn("P402_Conv.O.Run", msg)
        print(f"  [PASS] preflight blocks duplicate OTE: {msg[:160]}")

    def test_valid_owner_is_m402_not_int229(self) -> None:
        """Document proven owners from RUN evidence (not a guess)."""
        m402 = resolve_word_bit(self.pm, 206, 6)
        int229 = resolve_word_bit(self.pm, 207, 6)
        self.assertEqual(m402.get("channel"), TARGET)
        self.assertNotEqual(int229.get("channel"), TARGET)
        # Conveyor.asc evidence: M402 START MOTOR at 206/6
        from fortna_asc import read_asc

        _hdr, rows = read_asc(RUN / "FORTNA" / "Conveyor.asc")
        m402_rows = [
            r
            for r in rows
            if str(r.get("IO_Name") or "") == "M402"
            and str(r.get("IO_Address_Word") or "").strip() == "206"
            and str(r.get("IO_Address_Bit") or "").strip() == "6"
        ]
        int_rows = [
            r
            for r in rows
            if str(r.get("IO_Name") or "") == "INT229"
            and str(r.get("IO_Address_Word") or "").strip() == "207"
            and str(r.get("IO_Address_Bit") or "").strip() == "6"
        ]
        self.assertTrue(m402_rows, "M402 @ 206.6 missing from Conveyor.asc")
        self.assertTrue(int_rows, "INT229 @ 207.6 missing from Conveyor.asc")
        print("  [PASS] valid OUTPUT owner = M402/P402_Conv.O.Run; INT229 is INPUT bank 207")


def main() -> int:
    print("=== test_iomap_duplicate_output_ownership ===")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestIoMapDuplicateOutputOwnership)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("ALL PASS" if result.wasSuccessful() else "FAIL")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

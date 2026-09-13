#!/usr/bin/env python3
"""Regression: VFD###_FLT → P###_VFD.Flt.Overload (IO_MAP operand base exists)."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))


class TestVfdFltMember(unittest.TestCase):
    def test_suffix_mapping_in_source(self):
        text = (ROOT / "tools" / "scripts" / "fortna_autogen.py").read_text(encoding="utf-8")
        self.assertIn('return f"{base}.Flt.Overload"', text)
        self.assertIn('"FLT"', text)

    def test_library_has_overload_member(self):
        lib = (ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X").read_text(
            encoding="utf-8", errors="ignore"
        )
        self.assertIn('Name="Motor_Starter_Flt"', lib)
        self.assertIn('Name="Overload"', lib)

    def test_run_points_exist_cp4(self):
        from fortna_asc import read_asc

        run = ROOT / "workspace" / "cp4-run" / "RUN" / "FORTNA" / "Conveyor.asc"
        if not run.is_file():
            self.skipTest("CP4 RUN missing")
        _h, rows = read_asc(run)
        names = {(r.get("IO_Name") or "").strip().upper() for r in rows}
        for n in ("VFD216_FLT", "VFD219_FLT", "VFD410_FLT", "VFD422_FLT", "VFD834_FLT"):
            self.assertIn(n, names, n)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Regression: VFD###_FLT → P###_VFD.Flt.PS_Flt (library Motor_Starter_UDT.Flt)."""
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


import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))


class TestVfdFltMember(unittest.TestCase):
    def test_suffix_mapping_in_source(self):
        text = (ROOT / "tools" / "scripts" / "fortna_autogen.py").read_text(encoding="utf-8")
        self.assertIn('return f"{base}.Flt.PS_Flt"', text)
        self.assertIn('"FLT"', text)

    def test_library_ps_fault_member(self):
        lib = (ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X").read_text(
            encoding="utf-8", errors="ignore"
        )
        self.assertIn('Name="PS_Fault"', lib)
        self.assertIn('Name="PS_Flt"', lib)
        # Motor_Starter_UDT.Flt must be PS_Fault (not Motor_Starter_Flt)
        self.assertRegex(
            lib,
            r'<DataType Name="Motor_Starter_UDT"[\s\S]*?<Member Name="Flt" DataType="PS_Fault"',
        )

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

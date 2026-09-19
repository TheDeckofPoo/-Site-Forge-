#!/usr/bin/env python3
"""Export cleanup + L5X integrity guard regressions for exports/current."""
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
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))


class TestExportCurrentSingleL5x(unittest.TestCase):
    def test_autogen_source_no_longer_writes_latest_l5x(self):
        text = (ROOT / "tools" / "scripts" / "fortna_autogen.py").read_text(encoding="utf-8")
        # Must not write physical {controller}_LATEST.L5X anymore
        self.assertNotIn('latest_path.write_text(l5x', text)
        self.assertNotIn('latest_name = f"{file_stem}_LATEST.L5X"', text)
        self.assertIn("cleanup_exports_current_for_controller", text)
        self.assertIn("validate_l5x_output_integrity", text)

    def test_integrity_failure_message_strings_exist(self):
        text = (ROOT / "tools" / "scripts" / "fortna_autogen.py").read_text(encoding="utf-8")
        self.assertIn(
            "BUILD FAILED — Transportation model contained",
            text,
        )
        self.assertIn(
            "but final L5X contains 0 transport devices.",
            text,
        )
        self.assertIn(
            "BUILD FAILED — Hardware model contained",
            text,
        )
        self.assertIn(
            "but final L5X contains 0/incorrect modules.",
            text,
        )

    def test_cleanup_helper_removes_clutter_keeps_new(self):
        from fortna_autogen import cleanup_exports_current_for_controller

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "ORNCCP4_2026_09_13_1511.L5X").write_text("old1", encoding="utf-8")
            (d / "ORNCCP4_2026_09_13_1516.L5X").write_text("old2", encoding="utf-8")
            (d / "ORNCCP4_LATEST.L5X").write_text("latest", encoding="utf-8")
            (d / "ORNCCP4_2026_09_13_1511.manifest.json").write_text("{}", encoding="utf-8")
            (d / "ORNCCP4_2026_09_13_1517.L5X").write_text("new", encoding="utf-8")
            (d / "ORNCCP4_2026_09_13_1517.manifest.json").write_text("{}", encoding="utf-8")
            (d / "build_manifest.json").write_text("{}", encoding="utf-8")
            (d / "LATEST.json").write_text("{}", encoding="utf-8")
            (d / "ORNCCP2_2026_09_13_1151.L5X").write_text("other", encoding="utf-8")

            removed = cleanup_exports_current_for_controller(
                d,
                "ORNCCP4",
                keep_l5x_name="ORNCCP4_2026_09_13_1517.L5X",
                keep_manifest_name="ORNCCP4_2026_09_13_1517.manifest.json",
            )
            self.assertTrue(removed)
            names = {p.name for p in d.iterdir()}
            self.assertIn("ORNCCP4_2026_09_13_1517.L5X", names)
            self.assertIn("ORNCCP4_2026_09_13_1517.manifest.json", names)
            self.assertIn("build_manifest.json", names)
            self.assertIn("LATEST.json", names)
            self.assertIn("ORNCCP2_2026_09_13_1151.L5X", names)
            self.assertNotIn("ORNCCP4_LATEST.L5X", names)
            self.assertNotIn("ORNCCP4_2026_09_13_1511.L5X", names)
            self.assertNotIn("ORNCCP4_2026_09_13_1516.L5X", names)
            self.assertNotIn("ORNCCP4_2026_09_13_1511.manifest.json", names)

    def test_readme_mentions_timestamped_not_latest_l5x(self):
        text = (ROOT / "tools" / "scripts" / "fortna_autogen.py").read_text(encoding="utf-8")
        self.assertIn("single timestamped L5X named in", text)
        self.assertIn("physical _LATEST.L5X is not written", text)


if __name__ == "__main__":
    unittest.main()

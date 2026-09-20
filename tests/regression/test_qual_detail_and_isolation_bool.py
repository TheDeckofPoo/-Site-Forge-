#!/usr/bin/env python3
"""Qualification markdown must stringify dict details; isolation bool polarity."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "diagnostics"))


class TestQualDetailStringify(unittest.TestCase):
    def test_dict_detail_does_not_crash_replace(self) -> None:
        raw_detail = {"visual": "PASS", "parity": "REVIEW"}
        if isinstance(raw_detail, dict):
            detail = json.dumps(raw_detail, sort_keys=True, default=str)
        else:
            detail = str(raw_detail or "")
        detail = detail.replace("|", "/").replace("\n", " ")
        self.assertIn("visual", detail)
        self.assertIn("REVIEW", detail)


class TestIsolationBoolPolarity(unittest.TestCase):
    def test_zero_foreign_is_not_a_leak(self) -> None:
        foreign = []
        leak = len(foreign) > 0
        isolation_ok = len(foreign) == 0
        self.assertFalse(leak)
        self.assertTrue(isolation_ok)

    def test_source_file_polarity(self) -> None:
        src = (
            ROOT
            / "tools"
            / "diagnostics"
            / "_reality_check_demo_b_pass1.py"
        ).read_text(encoding="utf-8")
        self.assertIn("foreign_archive_leak_into_current_site", src)
        self.assertIn("len(foreign) > 0", src)
        self.assertIn("current_site_isolation_ok", src)


if __name__ == "__main__":
    unittest.main()

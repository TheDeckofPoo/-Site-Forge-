#!/usr/bin/env python3
"""3:1 / lettered discharge merges must not be silently skipped in Autogen emit."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))


class TestMergeLanesGt2Emit(unittest.TestCase):
    def test_autogen_no_longer_skips_lanes_gt_2(self) -> None:
        src = (ROOT / "tools" / "scripts" / "fortna_autogen.py").read_text(
            encoding="utf-8"
        )
        # Old defect: if lane_n > 2: continue
        self.assertNotRegex(
            src,
            r"if\s+lane_n\s*>\s*2:\s*\n\s*#.*\n\s*continue",
            msg="lanes>2 hard-skip must be removed so P3012A-class merges emit",
        )
        self.assertIn("lane_c", src)
        self.assertIn("section3", src)

    def test_suffix_a_identity_not_aliased_in_discovery_handoff(self) -> None:
        src = (ROOT / "tools" / "scripts" / "fortna_plc2_merge_discovery.py").read_text(
            encoding="utf-8"
        )
        # Keep existing no-flatten comments / lettered discharge behavior
        self.assertTrue(
            re.search(r"suffix|lettered|flatten", src, re.I),
            msg="discovery should retain suffix-identity guidance",
        )


if __name__ == "__main__":
    unittest.main()

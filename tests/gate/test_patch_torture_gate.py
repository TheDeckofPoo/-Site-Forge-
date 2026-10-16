#!/usr/bin/env python3
"""PATCH torture gate — Overnight Phase 2 lanes runnable without Electron.

Lanes covered here (plus reused modules invoked by tools/scripts/patch_gate.py):
  P6 residue scan smoke (configured sorter pack)
  P7 static L5X quality smoke (convergence_final)
  P8 discovery timing smoke (SHIP / PICK)

P1 → tests/gate/test_p1_site_switch_identity.py
P3 → tests/discovery/test_incomplete_run_fail_closed.py
P4 → tests/io/test_deterministic_io_no_ai.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "diagnostics"))

from patch_torture_helpers import (  # noqa: E402
    discovery_timing,
    residue_scan_configured_sorter,
    resolve_convergence_l5x,
    run_path,
    scan_l5x_static_quality,
    P8_FAIL_SECS,
)


class TestP6ResidueScanSmoke(unittest.TestCase):
    def test_configured_sorter_pack_no_foreign_descriptions(self) -> None:
        result = residue_scan_configured_sorter()
        if result.get("skipped"):
            self.skipTest(result.get("reason") or "skipped")
        self.assertEqual(result.get("mode"), "configured_pack", result)
        self.assertEqual(
            result.get("foreign_desc_count"),
            0,
            result.get("foreign_desc_hits"),
        )
        self.assertGreaterEqual(
            int(result.get("foreign_description_scrubbed") or 0),
            1,
            "expected neutralize path to scrub at least one donor Divert description",
        )
        self.assertTrue(result.get("ok"), result)


class TestP7StaticL5xQualitySmoke(unittest.TestCase):
    def test_convergence_final_l5x_static_quality(self) -> None:
        l5x = resolve_convergence_l5x()
        if l5x is None:
            self.skipTest("convergence_final MSCRENOSHIP.L5X missing")
        q = scan_l5x_static_quality(l5x)
        self.assertTrue(q["has_rslogix"], q)
        self.assertTrue(q["has_controller"], q)
        self.assertIn("MSCRENOSHIP", str(q.get("controller_name") or "").upper(), q)
        self.assertGreater(int(q["bytes"]), 100_000, q)
        self.assertGreater(int(q["program_count"]), 5, q)
        self.assertTrue(q["has_io_map"], q)
        self.assertEqual(
            int(q["blank_operand_count"]),
            0,
            q.get("blank_operand_sample"),
        )
        # Description residue on frozen Safe Partial is advisory for P7;
        # hard fail stays on blank operands / identity / structure.
        self.assertIsInstance(q.get("foreign_desc_count"), int)


class TestP8DiscoveryTimingSmoke(unittest.TestCase):
    @unittest.skipUnless(run_path("MSCRENOSHIP") is not None, "MSCRENOSHIP RUN missing")
    def test_ship_discovery_timing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = discovery_timing("MSCRENOSHIP", Path(td))
        self.assertFalse(result.get("skipped"), result)
        self.assertTrue(result.get("ok"), result)
        self.assertFalse(result.get("incomplete_run"), result)
        self.assertGreater(int(result.get("equipment") or 0), 0, result)
        self.assertLessEqual(float(result["seconds"]), P8_FAIL_SECS, result)

    @unittest.skipUnless(run_path("MSCRENOPICK") is not None, "MSCRENOPICK RUN missing")
    def test_pick_discovery_timing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = discovery_timing("MSCRENOPICK", Path(td))
        self.assertFalse(result.get("skipped"), result)
        self.assertTrue(result.get("ok"), result)
        self.assertFalse(result.get("incomplete_run"), result)
        self.assertGreater(int(result.get("equipment") or 0), 0, result)
        self.assertLessEqual(float(result["seconds"]), P8_FAIL_SECS, result)


if __name__ == "__main__":
    unittest.main(verbosity=2)

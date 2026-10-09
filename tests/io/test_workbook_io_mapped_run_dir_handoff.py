#!/usr/bin/env python3
"""Regression: workbook IO mapped must use RUN-proven bit radix.

After 9646977, _fortna_bit_to_data_bit requires run_dir for radix proof.
Calling it without run_dir returns None for PLC-5 octal bits and collapses
workbook stats.io_mapped to 0/N even when Configio word_map proves mappings.
Generate still mapped ~115/118 — this is a UI/workbook handoff defect only.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))

from fortna_autogen import _fortna_bit_to_data_bit  # noqa: E402
from fortna_workbook import build_workbook_from_run  # noqa: E402

MSC_PICK_RUN = (
    REPO
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
    / "RUN"
)


@unittest.skipUnless((MSC_PICK_RUN / "project.cfg").is_file(), "MSCRENOPICK RUN missing")
class TestWorkbookIoMappedRunDirHandoff(unittest.TestCase):
    def test_bit_without_run_dir_collapses_octal(self) -> None:
        # Reproduce the defect signature: valid Fortna bits → None without RUN.
        for bit in ("6", "14", "10", "17", "0"):
            self.assertIsNone(
                _fortna_bit_to_data_bit(bit),
                f"bit {bit!r} must fail closed without run_dir",
            )

    def test_bit_with_run_dir_resolves(self) -> None:
        # Same bits resolve when RUN radix proof is supplied.
        resolved = {
            bit: _fortna_bit_to_data_bit(bit, run_dir=MSC_PICK_RUN)
            for bit in ("6", "14", "10", "17", "0")
        }
        self.assertTrue(
            all(v is not None for v in resolved.values()),
            f"expected all bits resolved with run_dir, got {resolved}",
        )
        self.assertEqual(resolved["0"], 0)
        self.assertEqual(resolved["17"], 15)  # PLC-5 octal 17 → decimal 15

    def test_workbook_io_mapped_nonzero_when_word_map_proves(self) -> None:
        wb = build_workbook_from_run(MSC_PICK_RUN)
        stats = wb.get("stats") or {}
        io_points = int(stats.get("io_point_count") or 0)
        io_mapped = int(stats.get("io_mapped") or 0)
        self.assertGreater(io_points, 0, "expected MSCRENOPICK IO points from RUN")
        self.assertGreater(
            io_mapped,
            0,
            "workbook io_mapped must not be 0 when RUN+word_map prove mappings "
            f"(got {io_mapped}/{io_points})",
        )
        # Honesty bound: mapped cannot exceed point count.
        self.assertLessEqual(io_mapped, io_points)
        # Spot-check at least one concrete mapped module_ref survived.
        mapped_rows = [r for r in (wb.get("io_points") or []) if r.get("mapped")]
        self.assertTrue(mapped_rows, "expected at least one mapped IO row")
        self.assertTrue(
            any(str(r.get("module_ref") or "").strip() for r in mapped_rows),
            "mapped rows must carry a module_ref",
        )


if __name__ == "__main__":
    unittest.main()

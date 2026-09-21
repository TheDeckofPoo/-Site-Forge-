#!/usr/bin/env python3
"""IO_MAP CP_I/CP_O rungs sort by adapter natural order, slot, channel/bit."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_autogen import _rio_numeric_key, io_map_rung_sort_key  # noqa: E402


class TestIoMapNumericOrder(unittest.TestCase):
    def test_adapter_natural_order(self) -> None:
        names = ["AENTR_14", "AENTR_2", "AENTR_10", "AENTR_1", "AENTR_3"]
        ordered = sorted(names, key=_rio_numeric_key)
        self.assertEqual(
            ordered, ["AENTR_1", "AENTR_2", "AENTR_3", "AENTR_10", "AENTR_14"]
        )

    def test_rung_sort_slot_then_bit(self) -> None:
        rows = [
            {"rio": "AENTR_2", "slot": 5, "data_bit": 3, "tname": "B"},
            {"rio": "AENTR_1", "slot": 7, "data_bit": 1, "tname": "A"},
            {"rio": "AENTR_2", "slot": 5, "data_bit": 1, "tname": "C"},
            {"rio": "AENTR_1", "slot": 6, "data_bit": 0, "tname": "D"},
            {"rio": "AENTR_2", "slot": 4, "data_bit": 0, "tname": "E"},
        ]
        ordered = sorted(rows, key=io_map_rung_sort_key)
        self.assertEqual(
            [(r["rio"], r["slot"], r["data_bit"]) for r in ordered],
            [
                ("AENTR_1", 6, 0),
                ("AENTR_1", 7, 1),
                ("AENTR_2", 4, 0),
                ("AENTR_2", 5, 1),
                ("AENTR_2", 5, 3),
            ],
        )

    def test_stable_tiebreak_by_tname(self) -> None:
        rows = [
            {"rio": "AENTR_1", "slot": 1, "data_bit": 0, "tname": "Z_TAG"},
            {"rio": "AENTR_1", "slot": 1, "data_bit": 0, "tname": "A_TAG"},
        ]
        ordered = sorted(rows, key=io_map_rung_sort_key)
        self.assertEqual([r["tname"] for r in ordered], ["A_TAG", "Z_TAG"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

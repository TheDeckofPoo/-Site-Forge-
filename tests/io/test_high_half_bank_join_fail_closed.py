#!/usr/bin/env python3
"""High-half Configio bank join miss must not silently inherit Low module."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_physical_word_resolver import (  # noqa: E402
    PhysicalWordResolver,
    build_physical_word_map,
)

SHIP = ROOT / "workspace" / "_reno_peek" / "20260813-1132-MSCRENO-MSCRENOSHIP-RUN" / "RUN"


@unittest.skipUnless((SHIP / "project.cfg").is_file(), "MSCRENOSHIP RUN missing")
class TestHighHalfBankJoinFailClosed(unittest.TestCase):
    """POINT word 1111: High bank=OutputAddress must not collapse onto Low IB8."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pm = build_physical_word_map(SHIP, "MSCRENOSHIP")
        cls.resolver = PhysicalWordResolver(SHIP, "MSCRENOSHIP")

    def test_word_1111_low_resolves_high_unresolved(self) -> None:
        low = self.resolver.resolve(1111, 0)
        self.assertIsNotNone(low)
        self.assertEqual(low.get("channel"), "AENTR_2:I.Data[5].0")
        self.assertEqual(str(low.get("bit_half") or "").lower(), "low")
        # High octal labels / logical 8-15 must NOT inherit Low IB8
        for bit in (8, 9, 10, 11, "10", "11", "12"):
            hit = self.resolver.resolve(1111, bit)
            self.assertFalse(
                hit and hit.get("channel"),
                f"high bit {bit} must not collapse onto Low: {hit}",
            )

    def test_word_1111_review_required_recorded(self) -> None:
        misses = [
            u
            for u in (self.pm.get("unresolved") or [])
            if str(u.get("octal_word")) == "1111"
            and str(u.get("reason") or "").startswith("high_half")
        ]
        self.assertTrue(misses, self.pm.get("unresolved"))
        self.assertEqual(misses[0].get("classification"), "REVIEW_REQUIRED")
        self.assertEqual(int(misses[0].get("high_bank")), 4)

    def test_word_1137_ia4_high_half_not_collapsed(self) -> None:
        low = self.resolver.resolve(1137, 1)
        self.assertIsNotNone(low)
        self.assertEqual(low.get("channel"), "AENTR_4:I.Data[13].1")
        high = self.resolver.resolve(1137, "11")
        self.assertFalse(
            high and high.get("channel"),
            f"IA4 high-half must not fan onto Low bits: {high}",
        )

    def test_no_low_high_same_module_bit_collision_on_1111(self) -> None:
        by = self.pm.get("by_word_bit") or {}
        low_chs = {
            (by[k].get("channel"), by[k].get("bit"))
            for k in by
            if k.startswith("1111:") and str(by[k].get("bit_half") or "").lower() == "low"
        }
        high_chs = {
            (by[k].get("channel"), by[k].get("bit"))
            for k in by
            if k.startswith("1111:") and str(by[k].get("bit_half") or "").lower() == "high"
        }
        self.assertTrue(low_chs)
        self.assertFalse(high_chs, high_chs)
        # No High entries sharing Low module bits
        self.assertFalse(low_chs & high_chs)


if __name__ == "__main__":
    unittest.main(verbosity=2)

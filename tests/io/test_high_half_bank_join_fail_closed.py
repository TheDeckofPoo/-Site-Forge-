#!/usr/bin/env python3
"""High-half Configio bank join: mixed POINT words must bind High to OB/OA.

Previously fail-closed (unresolved) to avoid collapsing High onto Low IB8.
Overnight gospel: when Configio High bank + In_Out mask + synthesized
OutputBank prove an opposite-direction module, resolve it — do not leave
SSVD/M27/VFD high-half outputs missing or bound to Low inputs.
"""
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
class TestHighHalfBankJoinMixedPoint(unittest.TestCase):
    """POINT word 1111: Low=IB8, High=OB8E (OutputBank == adapter OutputAddress)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pm = build_physical_word_map(SHIP, "MSCRENOSHIP")
        cls.resolver = PhysicalWordResolver(SHIP, "MSCRENOSHIP")

    def test_word_1111_low_stays_ib8(self) -> None:
        low = self.resolver.resolve(1111, 0)
        self.assertIsNotNone(low)
        self.assertEqual(low.get("channel"), "AENTR_2:I.Data[5].0")
        self.assertEqual(str(low.get("bit_half") or "").lower(), "low")
        self.assertIn("IB8", str(low.get("type") or "").upper())

    def test_word_1111_high_binds_ob8e_not_ib8(self) -> None:
        # Fortna octal bit labels 10-17 → high half channels 0-7 on OB8E slot 6
        # (SHIP OCTAL_MODE=1 — bare decimal 8 is not a valid Fortna octal label)
        for bit, ch in (
            ("10", "AENTR_2:O.Data[6].0"),
            ("11", "AENTR_2:O.Data[6].1"),
            ("12", "AENTR_2:O.Data[6].2"),
            ("17", "AENTR_2:O.Data[6].7"),
        ):
            hit = self.resolver.resolve(1111, bit)
            self.assertTrue(hit and hit.get("channel"), f"high bit {bit} unresolved: {hit}")
            self.assertEqual(
                hit.get("channel"),
                ch,
                f"high bit {bit} wrong channel: {hit}",
            )
            self.assertNotIn(
                ":I.Data[5]",
                str(hit.get("channel") or ""),
                f"high bit {bit} collapsed onto Low IB8: {hit}",
            )
            self.assertIn("OB8E", str(hit.get("type") or "").upper())

    def test_word_1137_high_binds_oa4(self) -> None:
        low = self.resolver.resolve(1137, 1)
        self.assertIsNotNone(low)
        self.assertEqual(low.get("channel"), "AENTR_4:I.Data[13].1")
        # Octal bit 10 → high half channel 0 on OA4 slot 14 (M27 motor starter)
        high = self.resolver.resolve(1137, "10")
        self.assertTrue(high and high.get("channel"), high)
        self.assertEqual(high.get("channel"), "AENTR_4:O.Data[14].0")
        self.assertIn("OA4", str(high.get("type") or "").upper())

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
        self.assertTrue(high_chs, "high half must now fan out to OB8E")
        self.assertFalse(low_chs & high_chs)


if __name__ == "__main__":
    unittest.main(verbosity=2)

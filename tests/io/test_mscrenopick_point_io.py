#!/usr/bin/env python3
"""MSCRENOPICK POINT I/O — Configio bank + synthesized AENTR banks → owners."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

_SF_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SF_REPO / "tools" / "scripts"))

RUN = (
    _SF_REPO
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
    / "RUN"
)


@unittest.skipUnless((RUN / "project.cfg").is_file(), "MSCRENOPICK RUN missing")
class TestMscrenoPickPointIo(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from fortna_physical_word_resolver import build_physical_word_map, resolve_word_bit
        from fortna_hardware_io_model import build_hardware_io_model

        cls.pm = build_physical_word_map(RUN, "MSCRENOPICK")
        cls.hm = build_hardware_io_model(RUN, "MSCRENOPICK")

    def test_word_1005_low_aentr3_slot1(self) -> None:
        from fortna_physical_word_resolver import resolve_word_bit

        hit = resolve_word_bit(self.pm, 1005, 0)
        self.assertIsNotNone(hit)
        self.assertEqual(str(hit.get("rio_name") or "").upper(), "AENTR3")
        self.assertEqual(int(hit.get("eip_slot") or -1), 1)
        self.assertEqual(int(hit.get("bit") if hit.get("bit") is not None else -1), 0)

    def test_word_1143_low_aentr2_slot3(self) -> None:
        from fortna_physical_word_resolver import resolve_word_bit

        hit = resolve_word_bit(self.pm, 1143, 0)
        self.assertIsNotNone(hit)
        self.assertEqual(str(hit.get("rio_name") or "").upper(), "AENTR2")
        self.assertEqual(int(hit.get("eip_slot") or -1), 3)

    def test_owners_assigned_not_all_unresolved(self) -> None:
        stats = (self.hm.get("stats") or {}).get("owner_states") or {}
        self.assertGreaterEqual(int(stats.get("ASSIGNED") or 0), 4)
        # Must not leave every provable channel unresolved
        self.assertLess(int(stats.get("UNRESOLVED_OWNER") or 0), 50)

    def test_m1_aux_family_assigned(self) -> None:
        found = set()
        for ad in self.hm.get("adapters") or []:
            for mod in ad.get("modules") or []:
                for ch in mod.get("channels") or []:
                    own = str(
                        ch.get("owner")
                        or ch.get("engineering_owner")
                        or ch.get("owner_name")
                        or ""
                    ).upper()
                    if own in {"M1_AUX", "M2_AUX", "M3_AUX", "M4_AUX", "ESPB32", "EZPWS33", "EZPWS34"}:
                        found.add(own)
                        self.assertNotIn("UNRESOLVED", str(ch.get("owner_state") or "").upper())
        self.assertTrue({"M1_AUX", "M2_AUX"} & found)
        self.assertIn("ESPB32", found)


if __name__ == "__main__":
    unittest.main(verbosity=2)

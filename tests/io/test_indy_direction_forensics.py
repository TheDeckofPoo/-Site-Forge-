#!/usr/bin/env python3
"""Indy direction forensics + In_Out helper smoke tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_configio_direction import resolve_configio_direction  # noqa: E402

ORINDY = ROOT / "workspace" / "_virgin_orindy" / "RUN"


class TestConfigioDirection(unittest.TestCase):
    def test_oa8i_agrees_output(self) -> None:
        r = resolve_configio_direction(catalog="1794-OA8I", in_out="0000000011111111")
        self.assertEqual(r["direction"], "O")
        self.assertEqual(r["status"], "AGREE")

    def test_ia16_agrees_input(self) -> None:
        r = resolve_configio_direction(catalog="1794-IA16", in_out="0000000000000000")
        self.assertEqual(r["direction"], "I")
        self.assertEqual(r["status"], "AGREE")

    def test_conflict_when_disagree(self) -> None:
        r = resolve_configio_direction(catalog="1794-OA8I", in_out="0000000000000000")
        self.assertEqual(r["status"], "DIRECTION_CONFLICT")


@unittest.skipUnless((ORINDY / "project.cfg").is_file(), "ORINDY missing")
class TestFivePointBankCollision(unittest.TestCase):
    def test_words_out_oa_but_by_word_bit_ia(self) -> None:
        from fortna_physical_word_resolver import build_physical_word_map

        pm = build_physical_word_map(ORINDY, "ORINDYAC6")
        w616 = (pm.get("words") or {}).get("616") or {}
        bwb = (pm.get("by_word_bit") or {}).get("616:4") or {}
        self.assertEqual(w616.get("direction"), "O")
        self.assertIn("OA8", str(w616.get("type") or "").upper())
        # Production emit bug: undirected bank match selects IA16 for bit fan-out
        self.assertEqual(bwb.get("direction"), "I")
        self.assertIn("IA16", str(bwb.get("type") or "").upper())


if __name__ == "__main__":
    unittest.main(verbosity=2)

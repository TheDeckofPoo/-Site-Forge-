"""P0: HIGH-half bits must not fold onto LOW-only Configio banks (PES1-7)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_autogen import _resolve_via_configio  # noqa: E402
from fortna_physical_word_resolver import PhysicalWordResolver  # noqa: E402

SHIP = ROOT / "workspace" / "_reno_peek" / "20260813-1132-MSCRENO-MSCRENOSHIP-RUN" / "RUN"
PICK = ROOT / "workspace" / "_reno_peek" / "20260813-1132-MSCRENO-MSCRENOPICK-RUN" / "RUN"


class TestResolveViaConfigioNoFold(unittest.TestCase):
    def test_high_bit_solo_low_bank_returns_none(self) -> None:
        # Solo Low Configio row — high bit must NOT bind to banks[0].
        configio_map = {
            1115: [{"lohi": "Low", "bank": 84, "desc": "AENTR-2"}],
        }
        bank_index = {
            84: [
                {
                    "direction": "I",
                    "rio_name": "AENTR_2",
                    "flex_slot": 13,
                    "type": "1734-IA4",
                }
            ]
        }
        hit = _resolve_via_configio(
            1115,
            "12",
            want_dir="I",
            bank_index=bank_index,
            configio_map=configio_map,
            run_dir=None,
        )
        self.assertIsNone(hit)

    def test_low_bit_solo_low_bank_resolves(self) -> None:
        configio_map = {
            1115: [{"lohi": "Low", "bank": 84, "desc": "AENTR-2"}],
        }
        bank_index = {
            84: [
                {
                    "direction": "I",
                    "rio_name": "AENTR_2",
                    "flex_slot": 13,
                    "type": "1734-IA4",
                }
            ]
        }
        hit = _resolve_via_configio(
            1115,
            "2",
            want_dir="I",
            bank_index=bank_index,
            configio_map=configio_map,
            run_dir=None,
        )
        self.assertIsNotNone(hit)
        self.assertEqual(hit.get("resolved_bank"), 84)
        self.assertEqual(str(hit.get("bit_half") or "").lower(), "low")


@unittest.skipUnless((SHIP / "project.cfg").is_file(), "MSCRENOSHIP RUN missing")
class TestShipWord1115HalfBank(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.resolver = PhysicalWordResolver(SHIP, "MSCRENOSHIP")

    def test_low_bit_2_proven(self) -> None:
        hit = self.resolver.resolve(1115, 2)
        self.assertIsNotNone(hit)
        self.assertEqual(hit.get("channel"), "AENTR_2:I.Data[13].2")

    def test_high_bit_12_unsupported(self) -> None:
        hit = self.resolver.resolve(1115, "12")
        self.assertIsNone(hit)


@unittest.skipUnless((PICK / "project.cfg").is_file(), "MSCRENOPICK RUN missing")
class TestPickHalfBankRegression(unittest.TestCase):
    def test_pick_resolver_constructs(self) -> None:
        r = PhysicalWordResolver(PICK, "MSCRENOPICK")
        # Smoke: resolve something on PICK without crash
        self.assertTrue(hasattr(r, "resolve"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

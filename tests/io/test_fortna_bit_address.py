#!/usr/bin/env python3
"""Fortna bit-encoding semantics + by_word_bit key integrity."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_bit_address import (  # noqa: E402
    ENCODING_DECIMAL_INDEX,
    ENCODING_FORTNA_OCTAL_LABEL,
    parse_fortna_bit_address,
)
from fortna_physical_word_resolver import (  # noqa: E402
    PhysicalWordResolver,
    build_physical_word_map,
    parse_fortna_octal_bit,
)

PICK = (
    ROOT
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
    / "RUN"
)
ORINDY = ROOT / "workspace" / "_virgin_orindy" / "RUN"


class TestFortnaBitAddressSemantics(unittest.TestCase):
    def test_low_0_7(self) -> None:
        for i in range(8):
            a = parse_fortna_bit_address(str(i))
            self.assertEqual(a.logical_bit, i)
            self.assertEqual(a.half, "Low")
            self.assertEqual(a.module_bit, i)
            self.assertEqual(a.encoding, ENCODING_FORTNA_OCTAL_LABEL)
            self.assertEqual(a.raw_text, str(i))

    def test_high_octal_labels_10_17(self) -> None:
        # "10" is Fortna octal label for logical 8 — NOT decimal ten
        expected = {
            "10": (8, 0),
            "11": (9, 1),
            "12": (10, 2),
            "13": (11, 3),
            "14": (12, 4),
            "15": (13, 5),
            "16": (14, 6),
            "17": (15, 7),
        }
        for raw, (logical, mod) in expected.items():
            a = parse_fortna_bit_address(raw)
            self.assertEqual(a.raw_text, raw)
            self.assertEqual(a.encoding, ENCODING_FORTNA_OCTAL_LABEL, raw)
            self.assertEqual(a.logical_bit, logical, raw)
            self.assertEqual(a.half, "High", raw)
            self.assertEqual(a.module_bit, mod, raw)

    def test_eight_nine_decimal_high(self) -> None:
        for raw, logical, mod in (("8", 8, 0), ("9", 9, 1)):
            a = parse_fortna_bit_address(raw)
            self.assertEqual(a.encoding, ENCODING_DECIMAL_INDEX)
            self.assertEqual(a.logical_bit, logical)
            self.assertEqual(a.half, "High")
            self.assertEqual(a.module_bit, mod)

    def test_legacy_parse_fortna_octal_bit_compatible(self) -> None:
        p = parse_fortna_octal_bit("10")
        self.assertIsNotNone(p)
        self.assertEqual(p["raw"], 8)
        self.assertEqual(p["half"], "High")
        self.assertEqual(p["module_bit"], 0)
        self.assertEqual(p["raw_text"], "10")


@unittest.skipUnless((PICK / "project.cfg").is_file(), "MSCRENOPICK missing")
class TestByWordBitNoOverwrite(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pm = build_physical_word_map(PICK, "MSCRENOPICK")
        cls.r = PhysicalWordResolver(PICK, "MSCRENOPICK")

    def test_no_duplicate_channel_for_conflicting_keys(self) -> None:
        bwb = self.pm.get("by_word_bit") or {}
        by_ch = {}
        for k, v in bwb.items():
            ch = v.get("channel")
            if not ch:
                continue
            by_ch.setdefault(ch, []).append(k)
        # Same channel may appear once; conflicting overwrite would leave wrong owners
        # For word 1011 High OA4: logical 8-11 must map to Data[10].0-3 uniquely
        for bit, expect_mod in ((8, 0), (9, 1), (10, 2), (11, 3)):
            hit = bwb.get(f"1011:{bit}")
            self.assertIsNotNone(hit, bit)
            self.assertEqual(hit["bit"], expect_mod)
            self.assertEqual(hit["channel"], f"AENTR3:O.Data[10].{expect_mod}")

    def test_label_aliases_separate(self) -> None:
        labels = self.pm.get("by_word_bit_labels") or {}
        self.assertEqual(labels.get("1011:10"), "1011:8")
        self.assertEqual(labels.get("1011:11"), "1011:9")
        self.assertEqual(labels.get("1011:12"), "1011:10")
        self.assertEqual(labels.get("1011:13"), "1011:11")
        # Label keys must NOT pollute logical map as wrong channels
        # (old bug: 1011:10 meant module 2 after overwrite)

    def test_reno_1011_proven_and_unresolved(self) -> None:
        for b in ("0", "1", "2", "3"):
            h = self.r.resolve(1011, b)
            self.assertIsNotNone(h, b)
            self.assertTrue(str(h["channel"]).startswith("AENTR3:O.Data[9]."))
        for b in ("10", "11", "12", "13"):
            h = self.r.resolve(1011, b)
            self.assertIsNotNone(h, b)
            self.assertTrue(str(h["channel"]).startswith("AENTR3:O.Data[10]."), b)
        # bits 4/5 remain unresolved — no remap
        self.assertIsNone(self.r.resolve(1011, "4"))
        self.assertIsNone(self.r.resolve(1011, "5"))

    def test_label_10_equals_logical_8_not_module_2(self) -> None:
        h10 = self.r.resolve(1011, "10")
        h8 = self.r.resolve(1011, "8")
        self.assertEqual(h10["channel"], h8["channel"])
        self.assertEqual(h10["bit"], 0)


@unittest.skipUnless((ORINDY / "project.cfg").is_file(), "ORINDYAC6 missing")
class TestFlex16ChannelBits(unittest.TestCase):
    def test_flex_high_labels_resolve(self) -> None:
        r = PhysicalWordResolver(ORINDY, "ORINDYAC6")
        pm = build_physical_word_map(ORINDY, "ORINDYAC6")
        # Find any 16-pt word
        words = set()
        for key, rec in (pm.get("by_word_bit") or {}).items():
            if "IA16" in str(rec.get("type") or "") or "OA16" in str(rec.get("type") or ""):
                words.add(int(key.split(":")[0]))
        if not words:
            self.skipTest("no 16-pt FLEX words in map")
        w = sorted(words)[0]
        # Labels must parse/resolve without raising; High "10"→logical 8
        for b in ("0", "7", "10", "17"):
            _ = r.resolve(w, b)
        h10 = r.resolve(w, "10")
        h8 = r.resolve(w, "8")
        if h10 and h8:
            self.assertEqual(h10.get("channel"), h8.get("channel"))


class TestBaselineCountsUnchanged(unittest.TestCase):
    def test_counts(self) -> None:
        from fortna_ai_io_evidence import build_raw_claims

        cases = [
            (ORINDY, "ORINDYAC6", 371),
            (PICK, "MSCRENOPICK", 117),
            (ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN", "MSCATL_CP3", 256),
            (ROOT / "workspace" / "_ordencp3_peek" / "ORDENCP3" / "RUN", "ORDENCP3", 0),
        ]
        for run, mach, expect in cases:
            if not (run / "project.cfg").is_file():
                continue
            self.assertEqual(len(build_raw_claims(run, mach)), expect, mach)


if __name__ == "__main__":
    unittest.main(verbosity=2)

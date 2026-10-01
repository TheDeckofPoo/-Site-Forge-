#!/usr/bin/env python3
"""Canonical Fortna bit normalization — source-aware radix + consumer coherence."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_bit_address import (  # noqa: E402
    CONF_PROVEN,
    CONF_REVIEW_REQUIRED,
    ENCODING_DECIMAL_INDEX,
    ENCODING_FORTNA_OCTAL_LABEL,
    RADIX_DECIMAL,
    RADIX_OCTAL,
    clear_radix_cache,
    normalize_fortna_word_bit,
    normalize_lookup_word_bit,
    parse_fortna_bit_address,
    resolve_bit_radix,
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


class TestOctalFieldLabels(unittest.TestCase):
    """1. OCTAL field: 00-07, 10-17 → canonical 0-15."""

    def setUp(self) -> None:
        clear_radix_cache()

    def test_octal_low_and_high_labels(self) -> None:
        expected = {
            "00": (0, "LOW", 0),
            "0": (0, "LOW", 0),
            "01": (1, "LOW", 1),
            "02": (2, "LOW", 2),
            "03": (3, "LOW", 3),
            "04": (4, "LOW", 4),
            "05": (5, "LOW", 5),
            "06": (6, "LOW", 6),
            "07": (7, "LOW", 7),
            "10": (8, "HIGH", 0),
            "11": (9, "HIGH", 1),
            "12": (10, "HIGH", 2),
            "13": (11, "HIGH", 3),
            "14": (12, "HIGH", 4),
            "15": (13, "HIGH", 5),
            "16": (14, "HIGH", 6),
            "17": (15, "HIGH", 7),
        }
        for raw, (canon, byte, mod) in expected.items():
            wb = normalize_fortna_word_bit(
                1142,
                raw,
                field_name="IO_Address_Bit",
                source_table="Conveyor",
                radix=RADIX_OCTAL,
            )
            self.assertTrue(wb.valid, raw)
            self.assertEqual(wb.raw_bit, raw)
            self.assertEqual(wb.bit_radix, RADIX_OCTAL)
            self.assertEqual(wb.canonical_bit_index_0_15, canon, raw)
            self.assertEqual(wb.byte_index_within_word, byte, raw)
            self.assertEqual(wb.bit_index_within_byte, mod, raw)
            self.assertEqual(wb.encoding, ENCODING_FORTNA_OCTAL_LABEL, raw)


class TestInvalidOctal(unittest.TestCase):
    """2. Invalid OCTAL: 08, 09 (and bare 8/9)."""

    def test_08_09_rejected(self) -> None:
        for raw in ("08", "09", "8", "9"):
            wb = normalize_fortna_word_bit(
                1000,
                raw,
                field_name="IO_Address_Bit",
                radix=RADIX_OCTAL,
            )
            self.assertFalse(wb.valid, raw)
            self.assertIsNone(wb.canonical_bit_index_0_15, raw)
            self.assertEqual(wb.confidence, CONF_REVIEW_REQUIRED, raw)
            self.assertIn("invalid_octal_bit_label", wb.notes, raw)
            # Raw preserved
            self.assertEqual(wb.raw_bit, raw)


class TestDecimalSourceContext(unittest.TestCase):
    """3. DECIMAL source context remains decimal."""

    def test_decimal_13_stays_13(self) -> None:
        wb = normalize_fortna_word_bit(
            1142,
            "13",
            field_name="DECIMAL_BIT",
            source_table="DECIMAL_FIXTURE",
            radix=RADIX_DECIMAL,
        )
        self.assertTrue(wb.valid)
        self.assertEqual(wb.bit_radix, RADIX_DECIMAL)
        self.assertEqual(wb.canonical_bit_index_0_15, 13)
        self.assertEqual(wb.byte_index_within_word, "HIGH")
        self.assertEqual(wb.bit_index_within_byte, 5)
        self.assertEqual(wb.encoding, ENCODING_DECIMAL_INDEX)


class TestSameRawDifferentRadix(unittest.TestCase):
    """4. Same raw text differs only when schema proves different radix."""

    def test_raw_13_octal_vs_decimal(self) -> None:
        octal = normalize_fortna_word_bit(
            1142, "13", field_name="IO_Address_Bit", radix=RADIX_OCTAL
        )
        decimal = normalize_fortna_word_bit(
            1142, "13", field_name="DECIMAL_BIT", radix=RADIX_DECIMAL
        )
        self.assertEqual(octal.canonical_bit_index_0_15, 11)
        self.assertEqual(decimal.canonical_bit_index_0_15, 13)
        self.assertEqual(octal.raw_bit, decimal.raw_bit)


class TestOpaqueNamesIgnored(unittest.TestCase):
    """8. Opaque device/tag names do not affect bit normalization."""

    def test_device_name_ignored(self) -> None:
        a = normalize_fortna_word_bit(
            1142, "13", radix=RADIX_OCTAL, device_name="ESLS2"
        )
        b = normalize_fortna_word_bit(
            1142, "13", radix=RADIX_OCTAL, device_name="TOTALLY_DIFFERENT"
        )
        self.assertEqual(a.canonical_bit_index_0_15, b.canonical_bit_index_0_15)
        self.assertEqual(a.canonical_bit_index_0_15, 11)


class TestRadixEvidenceFromRun(unittest.TestCase):
    @unittest.skipUnless((PICK / "project.cfg").is_file(), "MSCRENOPICK missing")
    def test_pick_run_proves_octal(self) -> None:
        clear_radix_cache()
        ev = resolve_bit_radix(
            PICK, source_table="Conveyor", field_name="IO_Address_Bit"
        )
        self.assertEqual(ev.bit_radix, RADIX_OCTAL)
        self.assertEqual(ev.confidence, CONF_PROVEN)
        self.assertEqual(ev.octal_mode, 1)
        self.assertEqual(ev.mnu_dtype, "12")


class TestLegacyCompat(unittest.TestCase):
    def test_parse_fortna_bit_address_octal_labels(self) -> None:
        a = parse_fortna_bit_address("13")
        self.assertEqual(a.logical_bit, 11)
        self.assertEqual(a.half, "High")
        self.assertEqual(a.module_bit, 3)
        self.assertEqual(a.raw_text, "13")
        self.assertEqual(a.encoding, ENCODING_FORTNA_OCTAL_LABEL)

    def test_legacy_parse_fortna_octal_bit_compatible(self) -> None:
        p = parse_fortna_octal_bit("10", radix=RADIX_OCTAL)
        self.assertIsNotNone(p)
        self.assertEqual(p["raw"], 8)
        self.assertEqual(p["half"], "High")
        self.assertEqual(p["module_bit"], 0)
        self.assertEqual(p["raw_text"], "10")
        self.assertEqual(p["canonical_bit_index_0_15"], 8)


@unittest.skipUnless((PICK / "project.cfg").is_file(), "MSCRENOPICK missing")
class TestByWordBitNoOverwrite(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pm = build_physical_word_map(PICK, "MSCRENOPICK")
        cls.r = PhysicalWordResolver(PICK, "MSCRENOPICK")

    def test_no_duplicate_channel_for_conflicting_keys(self) -> None:
        bwb = self.pm.get("by_word_bit") or {}
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

    def test_reno_1011_proven_and_unresolved(self) -> None:
        for b in ("0", "1", "2", "3"):
            h = self.r.resolve(1011, b)
            self.assertIsNotNone(h, b)
            self.assertTrue(str(h["channel"]).startswith("AENTR3:O.Data[9]."))
        for b in ("10", "11", "12", "13"):
            h = self.r.resolve(1011, b)
            self.assertIsNotNone(h, b)
            self.assertTrue(str(h["channel"]).startswith("AENTR3:O.Data[10]."), b)
        self.assertIsNone(self.r.resolve(1011, "4"))
        self.assertIsNone(self.r.resolve(1011, "5"))

    def test_label_10_equals_logical_8_not_module_2(self) -> None:
        h10 = self.r.resolve(1011, "10")
        # Under OCTAL radix bare "8" is an invalid label; logical key 1011:8 is
        # the canonical map entry that label "10" must resolve to.
        logical = (self.pm.get("by_word_bit") or {}).get("1011:8")
        self.assertIsNotNone(h10)
        self.assertIsNotNone(logical)
        self.assertEqual(h10["channel"], logical["channel"])
        self.assertEqual(h10["bit"], 0)
        self.assertEqual(h10.get("canonical_bit_index_0_15"), 8)


@unittest.skipUnless((PICK / "project.cfg").is_file(), "MSCRENOPICK missing")
class TestSafetyHardwareCanonicalBitCoherence(unittest.TestCase):
    """5. Safety lookup and hardware lookup return the same canonical bit."""

    @classmethod
    def setUpClass(cls) -> None:
        clear_radix_cache()
        cls.r = PhysicalWordResolver(PICK, "MSCRENOPICK")
        from fortna_safety_endpoint_integrity import build_hardware_endpoint_maps

        cls.maps = build_hardware_endpoint_maps(PICK, "MSCRENOPICK")
        cls.wb = cls.maps["word_bit_to_endpoint"]

    def test_esls2_raw_13_shared_canonical(self) -> None:
        from fortna_safety_endpoint_integrity import _resolve_one_endpoint
        from fortna_safety_model import _canonical_word_bit_endpoint

        key, wb = normalize_lookup_word_bit(
            1142, "13", run_dir=PICK, field_name="IO_Address_Bit", source_table="Conveyor"
        )
        self.assertEqual(wb.canonical_bit_index_0_15, 11)
        self.assertEqual(key, "1142.11")
        phys = self.r.resolve(1142, "13")
        self.assertIsNotNone(phys)
        self.assertEqual(phys["channel"], "AENTR2:I.Data[2].3")
        self.assertEqual(self.wb.get("1142.11"), "AENTR2:I.Data[2].3")
        stamped = _canonical_word_bit_endpoint("1142", "13", run_dir=PICK)
        self.assertEqual(stamped, "1142.11")
        resolved, _from = _resolve_one_endpoint(stamped, self.wb)
        self.assertEqual(resolved.upper(), "AENTR2:I.DATA[2].3")
        resolved_raw, _ = _resolve_one_endpoint("1142.13", self.wb)
        self.assertEqual(resolved_raw.upper(), "AENTR2:I.DATA[2].3")

    def test_espb2_raw_14_shared_canonical(self) -> None:
        from fortna_safety_endpoint_integrity import _resolve_one_endpoint
        from fortna_safety_model import _canonical_word_bit_endpoint

        key, wb = normalize_lookup_word_bit(
            1006, "14", run_dir=PICK, field_name="IO_Address_Bit", source_table="Conveyor"
        )
        self.assertEqual(wb.canonical_bit_index_0_15, 12)
        self.assertEqual(key, "1006.12")
        phys = self.r.resolve(1006, "14")
        self.assertIsNotNone(phys)
        self.assertEqual(phys["channel"], "AENTR3:I.Data[4].4")
        self.assertEqual(self.wb.get("1006.12"), "AENTR3:I.Data[4].4")
        stamped = _canonical_word_bit_endpoint("1006", "14", run_dir=PICK)
        self.assertEqual(stamped, "1006.12")
        resolved, _ = _resolve_one_endpoint(stamped, self.wb)
        self.assertEqual(resolved.upper(), "AENTR3:I.DATA[4].4")


@unittest.skipUnless((PICK / "project.cfg").is_file(), "MSCRENOPICK missing")
class TestHighByteProvenance(unittest.TestCase):
    """6. High-byte provenance refers to correct bank/module/slot."""

    def test_high_half_provenance_not_low(self) -> None:
        r = PhysicalWordResolver(PICK, "MSCRENOPICK")
        low = r.resolve(1142, "0")
        high = r.resolve(1142, "13")
        self.assertIsNotNone(low)
        self.assertIsNotNone(high)
        self.assertEqual(low["eip_slot"], 1)
        self.assertEqual(high["eip_slot"], 2)
        self.assertEqual(int(low["half_bank"]), 68)
        self.assertEqual(int(high["half_bank"]), 69)
        lp = low.get("provenance") or {}
        hp = high.get("provenance") or {}
        self.assertEqual(lp.get("eipcfg_slot"), 1)
        self.assertEqual(hp.get("eipcfg_slot"), 2)
        self.assertEqual(int(lp.get("eipmodules_bank")), 68)
        self.assertEqual(int(hp.get("eipmodules_bank")), 69)
        self.assertEqual(hp.get("half"), "High")
        self.assertEqual(lp.get("half"), "Low")


@unittest.skipUnless((PICK / "project.cfg").is_file(), "MSCRENOPICK missing")
class TestWord1142Consistency(unittest.TestCase):
    def test_raw_labels_00_03_and_10_13(self) -> None:
        r = PhysicalWordResolver(PICK, "MSCRENOPICK")
        # Low
        for raw, ch in (("0", 0), ("1", 1), ("2", 2), ("3", 3)):
            h = r.resolve(1142, raw)
            self.assertEqual(h["channel"], f"AENTR2:I.Data[1].{ch}", raw)
            self.assertEqual(h["eip_slot"], 1)
        # High octal labels
        for raw, ch in (("10", 0), ("11", 1), ("12", 2), ("13", 3)):
            h = r.resolve(1142, raw)
            self.assertEqual(h["channel"], f"AENTR2:I.Data[2].{ch}", raw)
            self.assertEqual(h["eip_slot"], 2)


class TestCrossPanelNameIpConflict(unittest.TestCase):
    """7. Same adapter name with conflicting IP cannot become PROVEN."""

    def test_name_match_with_ip_mismatch_not_panels_equivalent(self) -> None:
        from fortna_panel_identity import panels_equivalent

        # Sanitized: identical adapter name tokens with distinct controller IPs
        # must never be treated as the same physical panel authority.
        model = {
            "aliases": [
                {
                    "panel_token": "EP2",
                    "adapter_name": "AENTR3",
                    "target_ip": "192.168.1.53",
                    "confidence": "PROVEN",
                },
                {
                    "panel_token": "EP_PACK",
                    "adapter_name": "AENTR3",
                    "target_ip": "192.168.1.54",
                    "confidence": "PROVEN",
                },
            ]
        }
        # Same adapter name alone does not make panels equivalent across IPs
        self.assertFalse(
            panels_equivalent("EP2", "EP_PACK", alias_model=model)
        )
        self.assertNotEqual(
            model["aliases"][0]["target_ip"], model["aliases"][1]["target_ip"]
        )


@unittest.skipUnless((ORINDY / "project.cfg").is_file(), "ORINDYAC6 missing")
class TestFlex16ChannelBits(unittest.TestCase):
    def test_flex_high_labels_resolve(self) -> None:
        r = PhysicalWordResolver(ORINDY, "ORINDYAC6")
        pm = build_physical_word_map(ORINDY, "ORINDYAC6")
        words = set()
        for key, rec in (pm.get("by_word_bit") or {}).items():
            if "IA16" in str(rec.get("type") or "") or "OA16" in str(rec.get("type") or ""):
                words.add(int(key.split(":")[0]))
        if not words:
            self.skipTest("no 16-pt FLEX words in map")
        w = sorted(words)[0]
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

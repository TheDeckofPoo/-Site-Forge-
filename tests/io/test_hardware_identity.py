#!/usr/bin/env python3
"""Canonical HardwareIdentity + FLEX 16-ch half domain invariants."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_hardware_identity import (  # noqa: E402
    build_hardware_identity_model,
    classify_host_xml_value,
    inventory_hardware_files,
)
from fortna_physical_word_resolver import build_physical_word_map  # noqa: E402

ORINDY = ROOT / "workspace" / "_virgin_orindy" / "RUN"
PICK = (
    ROOT
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
    / "RUN"
)


@unittest.skipUnless((ORINDY / "project.cfg").is_file(), "ORINDY missing")
class TestHardwareIdentityOrindy(unittest.TestCase):
    def test_inventory_finds_eipcfg(self) -> None:
        inv = inventory_hardware_files(ORINDY, "ORINDYAC6")
        roles = {i.get("authority_role") for i in inv if i.get("authority_candidate")}
        self.assertIn("eipcfg_xml", roles)
        self.assertIn("eipmodules", roles)
        self.assertFalse(any(str(i["path"]).upper().endswith(".L5X") for i in inv))

    def test_model_builds_adapters(self) -> None:
        hw = build_hardware_identity_model(ORINDY, "ORINDYAC6")
        self.assertGreaterEqual(hw["stats"]["adapter_count"], 1)
        self.assertGreaterEqual(hw["stats"]["module_count"], 1)
        # Names are aliases on canonical ids
        ads = hw["adapters"]
        self.assertTrue(any(a.get("ip_address") for a in ads))
        self.assertTrue(any(a.get("catalog_number") for a in ads))

    def test_host_xml_classification(self) -> None:
        inv = inventory_hardware_files(ORINDY, "ORINDYAC6")
        v = classify_host_xml_value(inv)
        self.assertIn(v["classification"], {"HIGH_VALUE", "PARTIAL_VALUE", "REDUNDANT", "ABSENT"})
        self.assertFalse(v.get("new_unused_authority"))


@unittest.skipUnless((ORINDY / "project.cfg").is_file(), "ORINDY missing")
class TestFlex16HalfDomain(unittest.TestCase):
    def test_no_logical_bits_above_15(self) -> None:
        pm = build_physical_word_map(ORINDY, "ORINDYAC6")
        bad = []
        for k in pm.get("by_word_bit") or {}:
            if ":" not in k:
                continue
            bit = int(k.split(":")[1])
            if bit > 15:
                bad.append(k)
        self.assertEqual(bad, [], bad[:10])

    def test_word_600_no_ge16_alias(self) -> None:
        pm = build_physical_word_map(ORINDY, "ORINDYAC6")
        keys = sorted(k for k in (pm.get("by_word_bit") or {}) if k.startswith("600:"))
        self.assertTrue(keys)
        self.assertFalse(any(int(k.split(":")[1]) > 15 for k in keys), keys)
        # 600:8 and 600:16 must not both exist
        self.assertNotIn("600:16", keys)


@unittest.skipUnless((PICK / "project.cfg").is_file(), "PICK missing")
class TestPointIdentityReno(unittest.TestCase):
    def test_aentr_aliases_not_split(self) -> None:
        hw = build_hardware_identity_model(PICK, "MSCRENOPICK")
        # AENTR3 should be one adapter with catalog 1734-AENT
        aentr3 = [
            a
            for a in hw["adapters"]
            if any("AENTR3" in str(x).upper() for x in (a.get("aliases") or []))
        ]
        self.assertEqual(len(aentr3), 1, aentr3)
        self.assertIn("1734", str(aentr3[0].get("adapter_family") or aentr3[0].get("catalog_number")))


class TestBaselineRawCounts(unittest.TestCase):
    def test_raw_physical_unchanged(self) -> None:
        from fortna_ai_io_evidence import build_raw_claims

        cases = [
            (ORINDY, "ORINDYAC6", 371),
            (PICK, "MSCRENOPICK", 117),
            (ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN", "MSCATL_CP3", 256),
            (ROOT / "workspace" / "_ordencp3_peek" / "ORDENCP3" / "RUN", "ORDENCP3", 0),
        ]
        for run, mach, n in cases:
            if (run / "project.cfg").is_file():
                self.assertEqual(len(build_raw_claims(run, mach)), n, mach)


if __name__ == "__main__":
    unittest.main(verbosity=2)

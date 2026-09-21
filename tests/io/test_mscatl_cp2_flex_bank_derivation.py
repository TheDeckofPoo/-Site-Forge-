#!/usr/bin/env python3
"""MSCATL_CP2 zero-bank EIPModules → derived Flex layout banks.

Raw InputBank/OutputBank stay 0. Effective banks come from
adapter InputAddress/OutputAddress + InputSize/OutputSize slot order.
"""
from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_ai_io_evidence import build_evidence_bundle  # noqa: E402
from fortna_hardware_io_model import build_hardware_io_model  # noqa: E402
from fortna_physical_word_resolver import PhysicalWordResolver  # noqa: E402

CP2 = _SF_REPO / "workspace" / "_mscatl_peek" / "MSCATL_CP2" / "RUN"
CP3 = _SF_REPO / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN"


@unittest.skipUnless((CP2 / "FORTNA").is_dir(), "MSCATL_CP2 RUN peek missing")
class TestMscatlCp2FlexBankDerivation(unittest.TestCase):
    def test_raw_banks_remain_zero_effective_populated(self) -> None:
        from fortna_physical_word_resolver import parse_eipcfg

        # Derivation stamps live on parse_eipcfg topology (physical_map adapters
        # are a slim autogen projection without bank fields).
        topo = parse_eipcfg(CP2, "MSCATL_CP2")
        ads = topo.get("adapters") or []
        flex = [
            a
            for a in ads
            if any("1794" in str(m.get("type") or "") for m in (a.get("modules") or []))
        ]
        self.assertGreaterEqual(len(flex), 3)
        derived = 0
        for ad in flex:
            for m in ad.get("modules") or []:
                if "AENT" in (m.get("type") or "").upper():
                    continue
                if (m.get("connection") or "").upper() == "HEADNODE":
                    continue
                self.assertEqual(int(m.get("input_bank") or 0), 0)
                self.assertEqual(int(m.get("output_bank") or 0), 0)
                if m.get("bank_derivation"):
                    derived += 1
                    self.assertTrue(
                        m.get("effective_input_bank") is not None
                        or m.get("effective_output_bank") is not None
                    )
        self.assertGreater(derived, 0)
        # Resolver must bind discrete Flex words using derived banks
        pwr = PhysicalWordResolver(CP2, "MSCATL_CP2")
        hit = pwr.resolve(600, 0)
        self.assertIsNotNone(hit)
        self.assertIn("T_1794_AENT_1", str((hit or {}).get("channel") or ""))

    def test_claims_assigned_and_occupancy_nonzero(self) -> None:
        ev = build_evidence_bundle(CP2, "MSCATL_CP2", project="MSCATL_CP2")
        raw = ev.get("raw_claims") or []
        self.assertGreater(len(raw), 0)
        disp = Counter(c.get("deterministic_disposition") for c in raw)
        self.assertGreater(int(disp.get("ASSIGNED") or 0), 0)
        # PowerFlex words may remain unresolved — honest REVIEW, not silent zero
        self.assertGreater(int(disp.get("physical_resolution_failure") or 0), 0)

        hw = build_hardware_io_model(CP2, "MSCATL_CP2")
        ch_n = 0
        for ad in hw.get("adapters") or []:
            for mod in ad.get("modules") or []:
                ch_n += len(mod.get("channels") or [])
        self.assertGreater(ch_n, 0, "Flex modules must expose channels after derivation")

    def test_cp3_still_fully_assigned(self) -> None:
        if not (CP3 / "FORTNA").is_dir():
            self.skipTest("MSCATL_CP3 peek missing")
        ev = build_evidence_bundle(CP3, "MSCATL_CP3", project="MSCATL_CP3")
        raw = ev.get("raw_claims") or []
        disp = Counter(c.get("deterministic_disposition") for c in raw)
        self.assertEqual(int(disp.get("ASSIGNED") or 0), len(raw))
        self.assertEqual(int(disp.get("physical_resolution_failure") or 0), 0)


if __name__ == "__main__":
    unittest.main()

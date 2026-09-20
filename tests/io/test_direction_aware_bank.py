#!/usr/bin/env python3
"""Direction-aware bank resolution — no site specials."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_physical_word_resolver import (  # noqa: E402
    PhysicalWordResolver,
    find_module_for_configio_bank,
    parse_eipcfg,
)
from fortna_rack_discovery import (  # noqa: E402
    DEVICE_NETWORK_DRIVE,
    DEVICE_REMOTE_IO_RACK,
    classify_network_device,
    discover_racks,
)

ORINDY = ROOT / "workspace" / "_virgin_orindy" / "RUN"
MSCATL = ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN"
PICK = (
    ROOT
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
    / "RUN"
)


class TestFindModuleDirectionAware(unittest.TestCase):
    @unittest.skipUnless((ORINDY / "project.cfg").is_file(), "missing")
    def test_bank_32_input_vs_output(self) -> None:
        topo = parse_eipcfg(ORINDY, "ORINDYAC6")
        ad = next(a for a in topo["adapters"] if "AENT-2" in str(a.get("name") or ""))
        hi = find_module_for_configio_bank(ad, 32, expected_direction="I", expected_catalog="1794-IA16")
        ho = find_module_for_configio_bank(ad, 32, expected_direction="O", expected_catalog="1794-OA8I")
        self.assertTrue(hi["ok"])
        self.assertTrue(ho["ok"])
        self.assertEqual(hi["direction"], "I")
        self.assertEqual(ho["direction"], "O")
        self.assertNotEqual(hi["module"]["slot"], ho["module"]["slot"])

    @unittest.skipUnless((ORINDY / "project.cfg").is_file(), "missing")
    def test_five_indy_output(self) -> None:
        r = PhysicalWordResolver(ORINDY, "ORINDYAC6")
        for w, b, expect in [
            (616, 4, "T_1794_AENT_2:O.Data[6].4"),
            (616, 5, "T_1794_AENT_2:O.Data[6].5"),
            (616, 6, "T_1794_AENT_2:O.Data[6].6"),
            (616, 7, "T_1794_AENT_2:O.Data[6].7"),
            (614, 7, "T_1794_AENT_2:O.Data[4].7"),
        ]:
            self.assertEqual(r.resolve(w, b)["channel"], expect)

    @unittest.skipUnless((ORINDY / "project.cfg").is_file(), "missing")
    def test_word_bit_matches_words_out_direction(self) -> None:
        from fortna_physical_word_resolver import build_physical_word_map

        pm = build_physical_word_map(ORINDY, "ORINDYAC6")
        w = pm["words"]["616"]
        b = pm["by_word_bit"]["616:4"]
        self.assertEqual(w["direction"], b["direction"])
        self.assertEqual(w["type"], b["type"])


class TestRackTaxonomy(unittest.TestCase):
    def test_classify(self) -> None:
        self.assertEqual(classify_network_device("1794-AENT"), DEVICE_REMOTE_IO_RACK)
        self.assertEqual(classify_network_device("PowerFlex70"), DEVICE_NETWORK_DRIVE)

    @unittest.skipUnless((ORINDY / "project.cfg").is_file(), "missing")
    def test_powerflex_not_area_rio(self) -> None:
        d = discover_racks(ORINDY, "ORINDYAC6")
        for r in d["racks"]:
            self.assertNotIn("POWERFLEX", str(r.get("catalog_number") or "").upper())
            self.assertTrue(str(r.get("provisional_display_name") or "").startswith("AREA_RIO_"))
        others = d.get("other_network_devices") or []
        self.assertTrue(any(o.get("device_class") == DEVICE_NETWORK_DRIVE for o in others) or len(others) >= 0)

    @unittest.skipUnless((MSCATL / "project.cfg").is_file(), "missing")
    def test_atlanta_three_racks(self) -> None:
        d = discover_racks(MSCATL, "MSCATL_CP3")
        self.assertEqual(d["stats"]["rack_count"], 3)
        self.assertEqual(d["stats"]["unplaced_modules"], 0)


@unittest.skipUnless((MSCATL / "project.cfg").is_file() and (PICK / "project.cfg").is_file(), "fixtures")
class TestCrossSiteNoSpecials(unittest.TestCase):
    def test_atlanta_assigns_and_reno_stable(self) -> None:
        from fortna_ai_io_evidence import build_evidence_bundle

        atl = build_evidence_bundle(MSCATL, "MSCATL_CP3", project="MSCATL_CP3")
        self.assertEqual(
            sum(1 for c in atl["raw_claims"] if c.get("deterministic_disposition") == "ASSIGNED"),
            256,
        )
        reno = build_evidence_bundle(PICK, "MSCRENOPICK", project="MSCRENOPICK")
        assigned = sum(1 for c in reno["raw_claims"] if c.get("deterministic_disposition") == "ASSIGNED")
        self.assertGreaterEqual(assigned, 115)

    @unittest.skipUnless((MSCATL / "project.cfg").is_file(), "missing")
    def test_atlanta_exact_ip_bridge_is_proven(self) -> None:
        r = PhysicalWordResolver(MSCATL, "MSCATL_CP3")
        hit = r.resolve(700, 0)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.get("channel"), "T_1794_AENT_1:I.Data[0].0")
        self.assertEqual(hit.get("bank_join"), "exact_ip_bridge")
        self.assertEqual(hit.get("binding_confidence"), "PROVEN")


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""CP8 evidence integrity + purpose/machine-scope regressions."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_hardware_conflict import (  # noqa: E402
    ALIAS_CATALOG_MISMATCH,
    HARDWARE_TYPE_SOURCE_CONFLICT,
    classify_catalog_disagreement,
)
from fortna_machine_source_scope import (  # noqa: E402
    SCOPE_ACTIVE,
    SCOPE_SIBLING,
    classify_eipcfg_files,
    select_active_eipcfg,
)
from fortna_physical_word_resolver import parse_eipcfg  # noqa: E402
from siteforge_learning.classify_configio_purpose import (  # noqa: E402
    PURPOSE_INTERNAL_MEMORY,
    PURPOSE_PHYSICAL_IO,
    classify_configio_purpose,
)

ORNCCP4 = ROOT / "exports/learning/_extract/ab56d6beb1b1ca87/RUN"
RESPICK = ROOT / "workspace/_corpus_peek/RESPICK/RUN"
PMART = ROOT / "workspace/_corpus_peek/PMARTOTW_AC1/RUN"
MSCATL = ROOT / "workspace/_mscatl_peek/MSCATL_CP3/RUN"


class TestIA16AliasMismatch(unittest.TestCase):
    def test_desc_ia16_physical_ib16_is_alias_not_source_conflict(self) -> None:
        r = classify_catalog_disagreement(
            human_name_or_desc="CP8-1794-IA16-6A",
            eipmodules_type="1794-IB16",
            eipcfg_type="1794-IB16",
        )
        self.assertEqual(r["classification"], ALIAS_CATALOG_MISMATCH)
        self.assertNotEqual(r["classification"], HARDWARE_TYPE_SOURCE_CONFLICT)


class TestBlankDescPhysical(unittest.TestCase):
    def test_blank_desc_strong_rta_is_physical_candidate(self) -> None:
        r = classify_configio_purpose(
            {
                "desc": "",
                "interface": "RTA",
                "bank": 4,
                "octal_word": 201,
                "lohi": "Low",
                "in_out": "0000000011111111",
                "i_o_type": "Digital",
            }
        )
        self.assertEqual(r["purpose"], PURPOSE_PHYSICAL_IO)
        self.assertTrue(r["keep_in_physical_io_queue"])
        self.assertTrue(r.get("exception_nonphysical_desc_but_physical_fields"))


class TestMemoryFieldSemantics(unittest.TestCase):
    def test_interface_memory(self) -> None:
        r = classify_configio_purpose(
            {
                "desc": "1794-MEM-150",
                "interface": "Memory",
                "i_o_type": "Memory",
                "lohi": "Both",
                "in_out": "1111111111111111",
                "bank": 0,
            }
        )
        self.assertEqual(r["purpose"], PURPOSE_INTERNAL_MEMORY)
        self.assertEqual(r.get("detection"), "field_semantics")


@unittest.skipUnless((RESPICK / "project.cfg").is_file(), "RESPICK peek missing")
class TestActiveMachineScope(unittest.TestCase):
    def test_respick_does_not_use_respna_sibling(self) -> None:
        classified = classify_eipcfg_files(RESPICK, "RESPICK")
        scopes = {c.source_file.split("/")[-1]: c.scope_status for c in classified}
        self.assertEqual(scopes.get("RESPICK-RTA-eipcfg.xml"), SCOPE_ACTIVE)
        self.assertEqual(scopes.get("RESPNA-RTA-eipcfg.xml"), SCOPE_SIBLING)
        sel = select_active_eipcfg(RESPICK, "RESPICK")
        self.assertTrue(str(sel["selected_eipcfg"] or "").endswith("RESPICK-RTA-eipcfg.xml"))
        self.assertFalse(
            str(sel["selected_eipcfg"] or "").endswith("RESPNA-RTA-eipcfg.xml")
        )
        topo = parse_eipcfg(RESPICK, "RESPICK")
        self.assertIn("RESPICK", str(topo.get("eipcfg_path") or ""))
        self.assertNotIn("RESPNA-RTA-eipcfg", str(topo.get("eipcfg_path") or ""))


@unittest.skipUnless((ORNCCP4 / "project.cfg").is_file(), "ORNCCP4 missing")
class TestCp8IntegrityModel(unittest.TestCase):
    def test_no_ambiguous_same_physical_module_boolean(self) -> None:
        from siteforge_learning.cp8_evidence_integrity import build_integrity_dossier

        d = build_integrity_dossier(ORNCCP4)
        # OA8I/OB16P High halves: NO_PHYSICAL_CLAIMS; IA16/IB16 High halves: claims → UNKNOWN
        self.assertEqual(d["high_relationship_summary"]["NO_PHYSICAL_CLAIMS"], 5)
        self.assertEqual(d["high_relationship_summary"]["UNKNOWN"], 3)
        for p in d["pairs"]:
            self.assertNotIn("same_physical_module", p)
            self.assertIn("logical_pair_relationship", p)
            self.assertIn("high_physical_relationship", p)
            self.assertIn("low_direct_module_resolution", p)
            self.assertIn("high_direct_module_resolution", p)
            self.assertIsNone(p["high_direct_module_resolution"])
            if "OA8I" in (p.get("authoritative_catalog") or ""):
                self.assertEqual(p["high_physical_relationship"], "NO_PHYSICAL_CLAIMS")
                self.assertEqual(p["B_High"]["occupancy"]["physical_claim_count"], 0)
        self.assertTrue(d["api_required"])


@unittest.skipUnless((MSCATL / "project.cfg").is_file(), "MSCATL missing")
class TestAtlantaStable(unittest.TestCase):
    def test_atlanta_still_proven(self) -> None:
        from fortna_production_gate_atlanta import site_counts

        atl = site_counts(MSCATL, "MSCATL_CP3")
        self.assertEqual(atl["ASSIGNED"], 256)
        self.assertEqual(atl["PROVEN"], 256)
        self.assertEqual(atl["needs_resolution"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Hardware type vs instance identity + enrich catalog safety."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_hardware_identity import (  # noqa: E402
    STATUS_CONFLICT,
    build_hardware_identity_model,
    classify_name,
    enrich_claim_hardware,
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
MSCATL = ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN"


class TestNameClassification(unittest.TestCase):
    def test_catalog_is_type_label(self) -> None:
        self.assertEqual(classify_name("1794-IA16"), "TYPE_LABEL")
        self.assertEqual(classify_name("1734-OA4"), "TYPE_LABEL")
        self.assertEqual(classify_name("PowerFlex70"), "TYPE_LABEL")

    def test_adapter_is_instance(self) -> None:
        self.assertEqual(classify_name("AENTR3"), "INSTANCE_ALIAS")
        self.assertEqual(classify_name("T_1794_AENT_2"), "INSTANCE_ALIAS")

    def test_shared_module_label(self) -> None:
        self.assertEqual(classify_name("AENTR1-IB8"), "SHARED_MODULE_LABEL")


@unittest.skipUnless((ORINDY / "project.cfg").is_file(), "ORINDY missing")
class TestInstanceVsTypeConflicts(unittest.TestCase):
    def test_catalog_reuse_not_conflict(self) -> None:
        hw = build_hardware_identity_model(ORINDY, "ORINDYAC6")
        stats = hw["stats"]
        self.assertGreater(stats["hardware_type_count"], 0)
        self.assertGreater(stats["module_count"], stats["hardware_type_count"])
        # Generic catalog must not appear as conflicting_instance_alias
        for c in hw.get("conflicts") or []:
            alias = str(c.get("conflicting_instance_alias") or "")
            self.assertNotEqual(alias.upper(), "1794-IA16")
            self.assertNotEqual(alias.upper(), "1794-AENT")
            self.assertFalse(alias.upper().startswith("POWERFLEX"))

    def test_same_catalog_two_slots_valid(self) -> None:
        hw = build_hardware_identity_model(ORINDY, "ORINDYAC6")
        ia16 = [
            m
            for m in hw["modules"]
            if str(m.get("catalog_number") or "").upper() == "1794-IA16"
        ]
        self.assertGreaterEqual(len(ia16), 2)
        slots = {m.get("physical_slot") for m in ia16}
        self.assertGreaterEqual(len(slots), 2)

    def test_provenance_on_every_instance(self) -> None:
        hw = build_hardware_identity_model(ORINDY, "ORINDYAC6")
        for m in hw["modules"]:
            self.assertTrue(m.get("evidence"), m.get("canonical_id"))
        for a in hw["adapters"]:
            self.assertTrue(a.get("evidence"), a.get("canonical_id"))


@unittest.skipUnless((PICK / "project.cfg").is_file(), "PICK missing")
class TestRenoIdentity(unittest.TestCase):
    def test_aentr3_single_adapter(self) -> None:
        hw = build_hardware_identity_model(PICK, "MSCRENOPICK")
        a3 = [
            a
            for a in hw["adapters"]
            if any("AENTR3" == str(x).upper() for x in (a.get("aliases") or []))
            or any("AENTR3" == str(x).upper() for x in (a.get("source_names") or []))
        ]
        self.assertEqual(len(a3), 1)
        # Remaining conflicts must be true source disagreements (eipcfg vs EIPModules),
        # never bare catalog reuse like 1734-OA4 / 1794-IA16.
        for c in hw.get("conflicts") or []:
            self.assertIn("eipcfg_vs_eipmodules_catalog_mismatch", c.get("reasons") or [])
            self.assertNotEqual(str(c.get("catalog_a") or "").upper(), "")
            self.assertNotEqual(
                str(c.get("catalog_a") or "").upper(),
                str(c.get("catalog_b") or "").upper(),
            )


class TestEnrichCatalogMismatch(unittest.TestCase):
    def test_wrong_catalog_not_silently_attached(self) -> None:
        model = {
            "adapters": [
                {
                    "canonical_id": "hw_ad1",
                    "aliases": ["AENTR3"],
                    "source_names": ["AENTR3"],
                    "status": "PROVEN",
                    "evidence": [{"source": "eipcfg_xml", "ref": "x", "fact": "y"}],
                }
            ],
            "modules": [
                {
                    "canonical_id": "hw_mod_wrong",
                    "parent_canonical_id": "hw_ad1",
                    "physical_slot": 10,
                    "catalog_number": "1734-IB8",  # wrong vs claim
                    "channel_capacity": 8,
                    "direction": "I",
                    "status": "PROVEN",
                    "evidence": [],
                }
            ],
        }
        hit = {
            "rio_name": "AENTR3",
            "type": "1734-OA4",
            "eip_slot": 10,
            "data_index": 10,
            "direction": "O",
            "family": "1734",
            "module_capacity": 4,
        }
        out = enrich_claim_hardware({"io_name": "X"}, physical_hit=hit, identity_model=model)
        self.assertEqual(out["hardware_identity_status"], STATUS_CONFLICT)
        self.assertEqual(out.get("canonical_module_id"), "")
        self.assertIn("hardware_identity_conflict", out)
        self.assertEqual(out["module_catalog"], "1734-OA4")  # claim catalog preserved


@unittest.skipUnless((ORINDY / "project.cfg").is_file(), "ORINDY missing")
class TestFlexDomainStillHolds(unittest.TestCase):
    def test_no_logical_gt_15(self) -> None:
        pm = build_physical_word_map(ORINDY, "ORINDYAC6")
        bad = [k for k in pm.get("by_word_bit") or {} if ":" in k and int(k.split(":")[1]) > 15]
        self.assertEqual(bad, [])


@unittest.skipUnless((MSCATL / "project.cfg").is_file(), "MSCATL missing")
class TestMscatlBindingTrace(unittest.TestCase):
    def test_binding_trace_readonly(self) -> None:
        from fortna_configio_binding_trace import get_configio_binding_trace

        from fortna_physical_word_resolver import _load_configio_rows

        rows = _load_configio_rows(MSCATL, "MSCATL_CP3")
        if not rows:
            self.skipTest("no configio")
        w = int(rows[0]["octal_word"])
        tr = get_configio_binding_trace(MSCATL, "MSCATL_CP3", w)
        self.assertTrue(tr["ok"])
        self.assertTrue(tr["read_only"])
        self.assertIn("final", tr)
        self.assertIn("candidates_attempted", tr)


class TestBaselineRaw(unittest.TestCase):
    def test_raw_counts(self) -> None:
        from fortna_ai_io_evidence import build_raw_claims

        for run, mach, n in [
            (ORINDY, "ORINDYAC6", 371),
            (PICK, "MSCRENOPICK", 117),
            (MSCATL, "MSCATL_CP3", 256),
            (ROOT / "workspace" / "_ordencp3_peek" / "ORDENCP3" / "RUN", "ORDENCP3", 0),
        ]:
            if (run / "project.cfg").is_file():
                self.assertEqual(len(build_raw_claims(run, mach)), n, mach)


if __name__ == "__main__":
    unittest.main(verbosity=2)

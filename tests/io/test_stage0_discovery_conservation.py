#!/usr/bin/env python3
"""Stage-0 evidence-entry conservation + exact Desc bridge + LOST gate.

Locks:
  - raw>0 + assigned=0 (or <10%) with hardware/Configio → DISCOVERY_FAILURE / not PASS
  - LOST CLAIMS gate still blocks generation
  - configio_desc_exact_eipcfg_module: unique match resolves; ambiguous/zero does not
  - Atlanta MSCATL_CP3 still ASSIGNED>0 (no regression)
"""
from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from fortna_ai_io_validate import (  # noqa: E402
    build_stage0_metrics,
    compute_claim_conservation,
    enrich_conservation_with_readiness,
    is_stage0_discovery_failure,
)
from fortna_autogen import _generation_assertion_failures  # noqa: E402
from fortna_physical_word_resolver import (  # noqa: E402
    _find_unique_exact_eipcfg_module,
    build_physical_word_map,
)

MSCATL_CP3 = ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN"
MSCATL_CP2 = ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP2" / "RUN"


class TestStage0BlocksWhenRawWithoutAssigned(unittest.TestCase):
    def test_raw_gt0_assigned_0_is_discovery_failure(self) -> None:
        self.assertTrue(
            is_stage0_discovery_failure(
                raw_physical_claims=605,
                assigned=0,
                hardware_modules=20,
                configio_words=50,
            )
        )
        cons = enrich_conservation_with_readiness(
            {
                "ok": True,
                "conservation": "PASS",
                "raw_physical_claims": 605,
                "accounted_claims": 605,
                "lost_claims": 0,
                "duplicate_accounting": 0,
                "counts": {
                    "ASSIGNED": 0,
                    "UNRESOLVED_OWNER": 0,
                    "OWNER_CONFLICT": 0,
                    "physical_resolution_failure": 605,
                    "ai_derived": 0,
                    "ai_review_required": 0,
                },
            },
            configio_words=50,
            hardware_modules=20,
        )
        self.assertFalse(cons["ok"])
        self.assertEqual(cons["conservation"], "FAIL")
        self.assertEqual(cons["discovery_status"], "DISCOVERY_FAILURE")
        self.assertEqual(cons["build_status"], "BUILD_BLOCKED")
        self.assertEqual(cons["evidence_status"], "DISCOVERY_FAILURE")
        self.assertEqual(cons["resolution_status"], "DISCOVERY_FAILURE")
        self.assertTrue(cons.get("accounting_ok"))

    def test_handful_assigned_still_discovery_failure(self) -> None:
        """Exact Desc bridge may assign ~3 rows / <10% — still insufficient."""
        self.assertTrue(
            is_stage0_discovery_failure(
                raw_physical_claims=605,
                assigned=28,
                hardware_modules=20,
                configio_words=50,
            )
        )

    def test_healthy_assigned_floor_not_discovery_failure(self) -> None:
        self.assertFalse(
            is_stage0_discovery_failure(
                raw_physical_claims=256,
                assigned=256,
                hardware_modules=20,
                configio_words=29,
            )
        )
        self.assertFalse(
            is_stage0_discovery_failure(
                raw_physical_claims=371,
                assigned=245,
                hardware_modules=30,
                configio_words=40,
            )
        )

    def test_stage0_metrics_block_build(self) -> None:
        s0 = build_stage0_metrics(
            raw_physical_candidates=605,
            claims_created=605,
            claims_excluded=100,
            claims_resolved=0,
            claims_unresolved=605,
            exclusion_reasons={"spare_io_name": 10},
            hardware_modules=20,
            configio_words=50,
        )
        self.assertEqual(s0["discovery_status"], "DISCOVERY_FAILURE")
        self.assertEqual(s0["build_status"], "BUILD_BLOCKED")
        self.assertFalse(s0["ok"])
        self.assertEqual(s0["RAW_PHYSICAL_CANDIDATES"], 605)
        self.assertEqual(s0["CLAIMS_CREATED"], 605)
        self.assertEqual(s0["CLAIMS_RESOLVED"], 0)

    def test_autogen_blocks_on_discovery_failure(self) -> None:
        inp = SimpleNamespace(
            include_io_map=True,
            pe_devices=[],
            conveyors=[],
            include_programs=[],
            sawtooth_build={},
        )
        report = {
            "io_map_mapped": 0,
            "io_map_lost_claims_count": 0,
            "io_map_source": "run_tar_gz_banks_eip",
            "pe_logic_rungs": 0,
            "conveyor_count": 0,
            "discovery_status": "DISCOVERY_FAILURE",
            "raw_physical_claims": 605,
            "claims_resolved": 0,
            "hardware_modules": 20,
            "stage0": {
                "RAW_PHYSICAL_CANDIDATES": 605,
                "CLAIMS_CREATED": 605,
                "CLAIMS_RESOLVED": 0,
                "discovery_status": "DISCOVERY_FAILURE",
                "hardware_modules": 20,
            },
        }
        failures = _generation_assertion_failures(inp, report, mappable_io_count=100)
        self.assertTrue(
            any("DISCOVERY_FAILURE" in f or "BUILD BLOCKED" in f for f in failures),
            failures,
        )


class TestLostGateStillWorks(unittest.TestCase):
    def test_lost_claims_still_block(self) -> None:
        inp = SimpleNamespace(
            include_io_map=True,
            pe_devices=[],
            conveyors=[],
            include_programs=[],
            sawtooth_build={},
        )
        report = {
            "io_map_mapped": 67,
            "io_map_lost_claims_count": 189,
            "io_map_lost_claims_sample": [{"tname": "SOME_INPUT"}],
            "io_map_source": "run_tar_gz_banks_eip",
            "pe_logic_rungs": 0,
            "conveyor_count": 0,
            "discovery_status": "OK",
            "raw_physical_claims": 256,
            "claims_resolved": 256,
            "hardware_modules": 20,
        }
        failures = _generation_assertion_failures(inp, report, mappable_io_count=256)
        self.assertTrue(any("LOST CLAIMS=189" in f for f in failures), failures)

    def test_lost_accounting_still_fails_conservation(self) -> None:
        evidence = {
            "raw_claims": [
                {"claim_id": "", "deterministic_disposition": "ASSIGNED"}
            ]
        }
        cons = compute_claim_conservation(evidence)
        self.assertGreater(cons["lost_claims"], 0)
        self.assertEqual(cons["conservation"], "FAIL")
        self.assertFalse(cons["ok"])


class TestConfigioDescExactEipcfgModule(unittest.TestCase):
    def _adapters(self):
        return [
            {
                "name": "1794-AENT-1",
                "rio_name": "T_1794_AENT_1",
                "panel": "",
                "adapter_index": 0,
                "modules": [
                    {
                        "name": "1794-AENT-1",
                        "type": "1794-AENT",
                        "slot": 0,
                        "connection": "HEADNODE",
                        "direction": "",
                        "input_bank": None,
                        "output_bank": None,
                        "data_index": 0,
                    },
                    {
                        "name": "1794-IA16-5",
                        "type": "1794-IA16",
                        "slot": 4,
                        "connection": "BRIDGED",
                        "direction": "I",
                        "input_bank": 0,
                        "output_bank": 0,
                        "data_index": 3,
                    },
                    {
                        "name": "1794-OA8I-8",
                        "type": "1794-OA8I",
                        "slot": 7,
                        "connection": "BRIDGED",
                        "direction": "O",
                        "input_bank": 0,
                        "output_bank": 0,
                        "data_index": 6,
                    },
                ],
            }
        ]

    def test_unique_exact_match_resolves(self) -> None:
        hit = _find_unique_exact_eipcfg_module(
            self._adapters(), "1794-IA16-5", expected_direction="I"
        )
        self.assertIsNotNone(hit)
        self.assertEqual(hit.get("name"), "1794-IA16-5")
        self.assertEqual(hit.get("direction"), "I")

    def test_zero_match_unresolved(self) -> None:
        hit = _find_unique_exact_eipcfg_module(
            self._adapters(), "1794-IA16-99", expected_direction="I"
        )
        self.assertIsNone(hit)

    def test_ambiguous_match_unresolved(self) -> None:
        ads = self._adapters()
        ads.append(
            {
                "name": "1794-AENT-2",
                "rio_name": "T_1794_AENT_2",
                "panel": "",
                "adapter_index": 1,
                "modules": [
                    {
                        "name": "1794-IA16-5",
                        "type": "1794-IA16",
                        "slot": 1,
                        "connection": "BRIDGED",
                        "direction": "I",
                        "input_bank": 0,
                        "output_bank": 0,
                        "data_index": 0,
                    }
                ],
            }
        )
        hit = _find_unique_exact_eipcfg_module(
            ads, "1794-IA16-5", expected_direction="I"
        )
        self.assertIsNone(hit)

    def test_direction_incompatible_rejected(self) -> None:
        hit = _find_unique_exact_eipcfg_module(
            self._adapters(), "1794-IA16-5", expected_direction="O"
        )
        self.assertIsNone(hit)

    def test_aent_head_skipped(self) -> None:
        hit = _find_unique_exact_eipcfg_module(
            self._adapters(), "1794-AENT-1", expected_direction=""
        )
        self.assertIsNone(hit)


@unittest.skipUnless((MSCATL_CP3 / "project.cfg").is_file(), "MSCATL_CP3 RUN missing")
class TestAtlantaCp3AssignedFloor(unittest.TestCase):
    def test_cp3_assigned_gt_zero(self) -> None:
        from fortna_ai_io_evidence import build_evidence_bundle

        ev = build_evidence_bundle(MSCATL_CP3, "MSCATL_CP3", project="MSCATL_CP3")
        assigned = int(
            (ev.get("conservation_counts") or {}).get("deterministic_assigned") or 0
        )
        self.assertGreater(assigned, 0)
        self.assertEqual(assigned, 256)
        self.assertEqual(ev.get("evidence_status"), "READY")
        self.assertNotEqual(ev.get("discovery_status"), "DISCOVERY_FAILURE")
        self.assertTrue((ev.get("conservation") or {}).get("ok"))

    def test_cp3_physical_map_still_catalog_prefix(self) -> None:
        pm = build_physical_word_map(MSCATL_CP3, "MSCATL_CP3")
        hows = {
            (v.get("assign_how") or "")
            for v in (pm.get("words") or {}).values()
        }
        self.assertIn("configio_catalog_prefix_bank", hows)
        self.assertGreater(int((pm.get("stats") or {}).get("word_count") or 0), 0)


@unittest.skipUnless((MSCATL_CP2 / "project.cfg").is_file(), "MSCATL_CP2 RUN missing")
class TestMscatlCp2Stage0AfterFlexDerivation(unittest.TestCase):
    def test_cp2_no_longer_vacuous_zero_assigned(self) -> None:
        """Zero-bank EIPModules + proven Flex layout derivation → ASSIGNED > 0.

        Raw IB/OB stay 0; effective_* banks drive Configio joins.
        Remaining PowerFlex words may stay unresolved (honest REVIEW).
        Vacuous PASS (claims>0, assigned=0, lost=0) must not recur.
        """
        from fortna_ai_io_evidence import build_evidence_bundle
        from fortna_hardware_io_model import build_hardware_io_model

        ev = build_evidence_bundle(MSCATL_CP2, "MSCATL_CP2", project="MSCATL_CP2")
        stage0 = ev.get("stage0") or {}
        created = int(stage0.get("CLAIMS_CREATED") or len(ev.get("raw_claims") or []))
        assigned = int(
            (ev.get("conservation_counts") or {}).get("deterministic_assigned")
            or stage0.get("CLAIMS_RESOLVED")
            or 0
        )
        self.assertGreater(created, 0)
        self.assertGreater(assigned, 0)
        self.assertNotEqual(ev.get("discovery_status"), "DISCOVERY_FAILURE")
        model = build_hardware_io_model(MSCATL_CP2, "MSCATL_CP2")
        self.assertNotEqual(model.get("claim_discovery_status"), "FAILED")
        ch_n = sum(
            len(m.get("channels") or [])
            for a in (model.get("adapters") or [])
            for m in (a.get("modules") or [])
        )
        self.assertGreater(ch_n, 0)
        pm = build_physical_word_map(MSCATL_CP2, "MSCATL_CP2")
        hows = Counter(
            (v.get("assign_how") or "") for v in (pm.get("words") or {}).values()
        )
        self.assertTrue(
            "configio_bank_match_derived_from_eipmodule_layout" in hows
            or "configio_catalog_prefix_bank" in hows
            or "configio_bank_match" in hows,
            f"expected derived/catalog bank assign_how, got {hows}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

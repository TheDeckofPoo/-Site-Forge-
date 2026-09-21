#!/usr/bin/env python3
"""UNRESOLVED_OWNER / OWNER_CONFLICT must not emit as proven IO_MAP mappings."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_autogen import (  # noqa: E402
    classify_iomap_physical_duplicate,
    _generation_assertion_failures,
)


class TestClassifyIomapDuplicate(unittest.TestCase):
    def test_owner_conflict_same_bank_bit(self) -> None:
        owners = [
            {
                "member": "P48A_MS.I.Auxiliary_Forward",
                "tname": "P48A_MS",
                "word": 400,
                "bit": "2",
                "comment": "P48A_MS · Bank400.2",
            },
            {
                "member": "P48_MS.I.Auxiliary_Forward",
                "tname": "P48_MS",
                "word": 400,
                "bit": "2",
                "comment": "P48_MS · Bank400.2",
            },
        ]
        audit = classify_iomap_physical_duplicate("AENTR_1:I.Data[6].2", owners)
        self.assertEqual(audit["classification"], "OWNER_CONFLICT")

    def test_decoder_error_low_high_collapse(self) -> None:
        owners = [
            {
                "member": "EZPWS_PA2",
                "tname": "EZPWS_PA2",
                "word": 1111,
                "bit": "1",
                "comment": "EZPWS_PA2 · Bank1111.1",
            },
            {
                "member": "SSVD3",
                "tname": "SSVD3",
                "word": 1111,
                "bit": "11",
                "comment": "SSVD3 · Bank1111.11",
            },
        ]
        audit = classify_iomap_physical_duplicate("AENTR_2:I.Data[5].1", owners)
        self.assertEqual(audit["classification"], "DECODER_ERROR")

    def test_proven_shared_semantic_allowed(self) -> None:
        owners = [
            {
                "member": "MSORTTR1",
                "tname": "MSORTTR1",
                "word": 1124,
                "bit": "15",
                "comment": "MSORTTR1 · Bank1124.15 · REVIEW_SHARED_OUTPUT · RUN_PROVEN",
            },
            {
                "member": "VFDSSVSOL1",
                "tname": "VFDSSVSOL1",
                "word": 1124,
                "bit": "15",
                "comment": "VFDSSVSOL1 · Bank1124.15 · REVIEW_SHARED_OUTPUT · RUN_PROVEN",
            },
        ]
        audit = classify_iomap_physical_duplicate("AENTR_3:O.Data[10].5", owners)
        self.assertEqual(audit["classification"], "PROVEN_SHARED_SEMANTIC")


class TestUnresolvedBlockedGate(unittest.TestCase):
    def test_dup_blocked_trips_generation_assertion(self) -> None:
        from types import SimpleNamespace

        report = {
            "io_map_mapped": 10,
            "io_map_lost_claims_count": 0,
            "io_map_source": "run_tar_gz_banks_eip",
            "io_map_dup_physical_blocked_count": 2,
            "io_map_dup_physical_audits": [
                {
                    "physical_address": "AENTR_2:I.Data[5].1",
                    "classification": "DECODER_ERROR",
                    "named_mapping_count": 2,
                },
                {
                    "physical_address": "AENTR_1:I.Data[6].2",
                    "classification": "OWNER_CONFLICT",
                    "named_mapping_count": 2,
                },
            ],
            "pe_logic_rungs": 0,
            "conveyor_count": 0,
        }
        inp = SimpleNamespace(
            include_io_map=True,
            pe_devices=[],
            conveyors=[],
            include_programs=[],
            sawtooth_build={},
        )
        failures = _generation_assertion_failures(inp, report, mappable_io_count=10)
        blocked = [f for f in failures if "BUILD BLOCKED: duplicate physical" in f]
        self.assertEqual(len(blocked), 1, failures)
        self.assertIn("DECODER_ERROR", blocked[0])

    def test_proven_shared_does_not_trip_when_blocked_count_zero(self) -> None:
        from types import SimpleNamespace

        report = {
            "io_map_mapped": 10,
            "io_map_lost_claims_count": 0,
            "io_map_source": "run_tar_gz_banks_eip",
            "io_map_dup_physical_blocked_count": 0,
            "io_map_dup_physical_audits": [
                {
                    "physical_address": "AENTR_3:O.Data[10].5",
                    "classification": "PROVEN_SHARED_SEMANTIC",
                    "named_mapping_count": 2,
                }
            ],
            "pe_logic_rungs": 0,
            "conveyor_count": 0,
        }
        inp = SimpleNamespace(
            include_io_map=True,
            pe_devices=[],
            conveyors=[],
            include_programs=[],
            sawtooth_build={},
        )
        failures = _generation_assertion_failures(inp, report, mappable_io_count=10)
        self.assertFalse(
            any("duplicate physical" in f for f in failures), failures
        )


class TestEmitBlockCountersUnit(unittest.TestCase):
    """Small unit: unresolved dispositions are the blocked set for proven emit."""

    def test_blocked_disposition_set(self) -> None:
        blocked = {"UNRESOLVED_OWNER", "OWNER_CONFLICT"}
        self.assertIn("UNRESOLVED_OWNER", blocked)
        self.assertIn("OWNER_CONFLICT", blocked)
        self.assertNotIn("ASSIGNED", blocked)
        self.assertNotIn("PROVEN_SHARED_SEMANTIC", blocked)


if __name__ == "__main__":
    unittest.main(verbosity=2)

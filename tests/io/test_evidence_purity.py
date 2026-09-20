#!/usr/bin/env python3
"""Evidence-purity: decoder output cannot independently prove decoder rules."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_evidence_purity import (  # noqa: E402
    CURRENT_DECODER_OUTPUT,
    INDEPENDENT_DERIVATION,
    RAW_RUN_EVIDENCE,
    cannot_prove_with_decoder_output,
    classify_tool_evidence,
)


class TestEvidencePurity(unittest.TestCase):
    def test_physical_trace_is_decoder_output(self) -> None:
        m = classify_tool_evidence("get_physical_word_resolution_trace")
        self.assertEqual(m["evidence_class"], CURRENT_DECODER_OUTPUT)
        self.assertFalse(m["independent_of_candidate_logic"])
        self.assertFalse(m["usable_for_rule_proof"])

    def test_configio_word_is_raw(self) -> None:
        m = classify_tool_evidence("get_configio_word")
        self.assertEqual(m["evidence_class"], RAW_RUN_EVIDENCE)
        self.assertTrue(m["usable_for_rule_proof"])

    def test_eip_bank_map_independent(self) -> None:
        m = classify_tool_evidence("get_eip_bank_map")
        self.assertEqual(m["evidence_class"], INDEPENDENT_DERIVATION)

    def test_decoder_assigned_cannot_prove_when_raw_unknown(self) -> None:
        self.assertTrue(
            cannot_prove_with_decoder_output(
                raw_status="UNKNOWN", decoder_status="ASSIGNED"
            )
        )
        self.assertFalse(
            cannot_prove_with_decoder_output(
                raw_status="RAW_MATCH", decoder_status="ASSIGNED"
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

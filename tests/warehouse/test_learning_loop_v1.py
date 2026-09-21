#!/usr/bin/env python3
"""Learning Loop V1 — eligibility gate + schema smoke."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from siteforge_warehouse.learning_loop import ai_investigation_eligible  # noqa: E402


class TestAiEligibility(unittest.TestCase):
    def test_blocks_when_deterministic_explains(self) -> None:
        r = ai_investigation_eligible(
            signature_id="fs_x",
            machines_observed=["MSCATL_CP1"],
            unresolved_count=500,
            deterministic_explains=True,
        )
        self.assertFalse(r["eligible"])
        self.assertIn("deterministic_evidence_explains", r["block_reasons"])

    def test_allows_multi_controller(self) -> None:
        r = ai_investigation_eligible(
            signature_id="fs_y",
            machines_observed=["A", "B"],
            unresolved_count=10,
        )
        self.assertTrue(r["eligible"])
        self.assertIn("multi_controller_recurrence", r["allow_reasons"])

    def test_allows_meaningful_impact(self) -> None:
        r = ai_investigation_eligible(
            signature_id="fs_z",
            machines_observed=["ONLY"],
            unresolved_count=80,
        )
        self.assertTrue(r["eligible"])
        self.assertIn("meaningful_single_controller_impact", r["allow_reasons"])


class TestModelsImport(unittest.TestCase):
    def test_learning_loop_models_importable(self) -> None:
        from siteforge_warehouse.models import (
            AiInvestigation,
            FailureEvent,
            FieldTest,
            ShadowEvaluation,
            StructuralSignature,
        )

        self.assertEqual(FieldTest.__tablename__, "field_tests")
        self.assertEqual(FailureEvent.__tablename__, "failure_events")
        self.assertEqual(StructuralSignature.__tablename__, "structural_signatures")
        self.assertEqual(AiInvestigation.__tablename__, "ai_investigations")
        self.assertEqual(ShadowEvaluation.__tablename__, "shadow_evaluations")


if __name__ == "__main__":
    unittest.main()

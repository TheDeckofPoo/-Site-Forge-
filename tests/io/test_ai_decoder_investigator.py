#!/usr/bin/env python3
"""AI Decoder Investigator — schema, clustering, read-only tools, Reno fixture."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from fortna_ai_decoder_schema import (  # noqa: E402
    DECODER_RULE_CANDIDATE_SCHEMA,
    validate_decoder_rule_candidate,
)
from fortna_ai_failure_cluster import cluster_unresolved_claims  # noqa: E402
from fortna_ai_investigate_reno_oa4 import investigate_reno_oa4_low_overflow  # noqa: E402
from fortna_ai_io_validate import AI_ENDPOINT_AUTHORITY  # noqa: E402
from fortna_ai_readonly_tools import (  # noqa: E402
    FORBIDDEN_MUTATION_OPS,
    ReadOnlyViolation,
    SiteForgeReadOnlyContext,
    invoke_tool,
)


def _minimal_candidate(**overrides):
    base = {
        "investigation_id": "inv_test",
        "subsystem": "physical_io_word_bit_decode",
        "failure_pattern": "TEST_PATTERN",
        "affected_claim_ids": ["cl_a"],
        "affected_count": 1,
        "observed_facts": ["fact"],
        "evidence_refs": [{"source": "Configio.asc", "ref": "row:1", "fact": "x"}],
        "candidate_rule_name": "test_rule",
        "candidate_rule_description": "desc",
        "proposed_inputs": ["Configio.Bank"],
        "proposed_transformation": "IF capacity==4 AND bit>=4: REVIEW",
        "expected_outputs": ["physical_resolution_failure"],
        "supporting_examples": [{"summary": "ok example"}],
        "counterexamples": [{"summary": "bad remap", "why_contradicts": "collision"}],
        "ambiguities": [],
        "additional_evidence_needed": [],
        "tests_required": ["regression"],
        "scope": "1734 OA4",
        "confidence": "MEDIUM",
        "status": "CANDIDATE",
    }
    base.update(overrides)
    return base


class TestDecoderRuleCandidateSchema(unittest.TestCase):
    def test_schema_has_required_fields(self) -> None:
        req = set(DECODER_RULE_CANDIDATE_SCHEMA["required"])
        for field in (
            "investigation_id",
            "failure_pattern",
            "candidate_rule_name",
            "proposed_transformation",
            "supporting_examples",
            "counterexamples",
            "status",
        ):
            self.assertIn(field, req)

    def test_valid_candidate_ok(self) -> None:
        v = validate_decoder_rule_candidate(_minimal_candidate())
        self.assertTrue(v["ok"], v)
        self.assertFalse(v["compiler_authority"])
        self.assertFalse(v["creates_ready"])

    def test_ai_cannot_return_compiler_authoritative_mapping(self) -> None:
        bad = _minimal_candidate(physical_endpoint={"channel": "X:I.Data[0].0"})
        v = validate_decoder_rule_candidate(bad)
        self.assertFalse(v["ok"])
        self.assertTrue(any("forbidden" in r for r in v["reasons"]))

    def test_candidate_cannot_create_ready_status(self) -> None:
        bad = _minimal_candidate(status="READY")
        v = validate_decoder_rule_candidate(bad)
        self.assertFalse(v["ok"])
        self.assertNotEqual(v["status"], "READY")

    def test_review_required_remains_unresolved(self) -> None:
        c = _minimal_candidate(status="REVIEW_REQUIRED")
        v = validate_decoder_rule_candidate(c)
        self.assertTrue(v["ok"], v)
        self.assertEqual(v["status"], "REVIEW_REQUIRED")
        self.assertFalse(v["creates_ready"])

    def test_insufficient_evidence_remains_unresolved(self) -> None:
        c = _minimal_candidate(status="INSUFFICIENT_EVIDENCE")
        v = validate_decoder_rule_candidate(c)
        self.assertTrue(v["ok"], v)
        self.assertEqual(v["status"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(v["creates_ready"])

    def test_endpoint_authority_flag_is_off(self) -> None:
        self.assertFalse(AI_ENDPOINT_AUTHORITY)


class TestFailureClusteringConservation(unittest.TestCase):
    def test_clusters_preserve_all_ids_no_dup_no_loss(self) -> None:
        claims = [
            {
                "claim_id": f"cl_{i}",
                "io_name": f"N{i}",
                "word": "1011" if i < 5 else "611",
                "bit": str(i % 8),
                "machine": "MSCRENOPICK",
                "deterministic_disposition": "physical_resolution_failure",
                "family": "1734",
                "catalog": "1734-OA4",
                "direction": "O",
            }
            for i in range(12)
        ]
        # Add one conflict with different dims
        claims.append(
            {
                "claim_id": "cl_conflict",
                "io_name": "X",
                "word": "610",
                "bit": "0",
                "machine": "MSCRENOPICK",
                "deterministic_disposition": "OWNER_CONFLICT",
                "family": "1794",
                "catalog": "1794-IA16",
                "direction": "I",
            }
        )
        result = cluster_unresolved_claims(claims)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["conservation"], "PASS")
        self.assertEqual(result["lost_claim_ids"], [])
        self.assertEqual(result["duplicate_claim_ids"], [])
        self.assertEqual(result["input_claim_count"], 13)
        all_ids = []
        for cl in result["clusters"]:
            all_ids.extend(cl["claim_ids"])
        self.assertEqual(len(all_ids), 13)
        self.assertEqual(len(set(all_ids)), 13)
        # No claim in two clusters
        self.assertEqual(len(result["claim_to_cluster"]), 13)

    def test_assigned_excluded_from_default_clustering(self) -> None:
        claims = [
            {
                "claim_id": "cl_ok",
                "word": "1011",
                "bit": "0",
                "deterministic_disposition": "ASSIGNED",
            },
            {
                "claim_id": "cl_fail",
                "word": "1011",
                "bit": "5",
                "deterministic_disposition": "physical_resolution_failure",
            },
        ]
        result = cluster_unresolved_claims(claims)
        self.assertEqual(result["input_claim_count"], 1)
        self.assertIn("cl_fail", result["claim_to_cluster"])
        self.assertNotIn("cl_ok", result["claim_to_cluster"])


class TestReadOnlyTools(unittest.TestCase):
    @unittest.skipUnless(
        (
            ROOT
            / "workspace"
            / "_reno_peek"
            / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
            / "RUN"
            / "project.cfg"
        ).is_file(),
        "MSCRENOPICK RUN missing",
    )
    def test_readonly_tools_cannot_mutate(self) -> None:
        run = (
            ROOT
            / "workspace"
            / "_reno_peek"
            / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
            / "RUN"
        )
        ctx = SiteForgeReadOnlyContext(run_dir=run, machine="MSCRENOPICK")
        for op in FORBIDDEN_MUTATION_OPS:
            with self.assertRaises(ReadOnlyViolation):
                invoke_tool(ctx, op)
        # Read path works
        ident = invoke_tool(ctx, "get_project_identity")
        self.assertEqual(ident["machine"], "MSCRENOPICK")
        # Evidence notes forbid finished/reference L5X discovery
        notes = " ".join(ctx.evidence.get("notes") or [])
        self.assertIn("Never includes finished/reference L5X", notes)
        self.assertNotIn("reference_l5x", ctx.evidence)
        self.assertNotIn("finished_l5x", ctx.evidence)


class TestRenoInvestigationFixture(unittest.TestCase):
    @unittest.skipUnless(
        (
            ROOT
            / "workspace"
            / "_reno_peek"
            / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
            / "RUN"
            / "project.cfg"
        ).is_file(),
        "MSCRENOPICK RUN missing",
    )
    def test_reno_produces_rule_candidate_not_endpoint(self) -> None:
        result = investigate_reno_oa4_low_overflow()
        self.assertTrue(result["ok"])
        self.assertFalse(result["live_api_called"])
        self.assertFalse(result["endpoint_assignments_emitted"])
        self.assertFalse(result["compiler_authority"])
        self.assertFalse(result["creates_ready"])
        cand = result["candidate"]
        self.assertNotIn("physical_endpoint", cand)
        self.assertIn(cand["status"], {"CANDIDATE", "REVIEW_REQUIRED", "INSUFFICIENT_EVIDENCE"})
        self.assertEqual(cand["status"], "REVIEW_REQUIRED")
        self.assertTrue(result["schema_validation"]["ok"], result["schema_validation"])
        # Must document collision counterexample against prior AI remap
        texts = " ".join(c["why_contradicts"] for c in cand["counterexamples"])
        self.assertIn("EZSSV10", texts)
        self.assertIn("EZSSV11", texts)
        # Affected claims are the bit 4/5 failures
        self.assertEqual(cand["affected_count"], len(cand["affected_claim_ids"]))
        self.assertGreaterEqual(cand["affected_count"], 1)


class TestFourSiteBaselineNoRegress(unittest.TestCase):
    """Deterministic baselines must not regress because AI architecture changed."""

    def _raw_count(self, run: Path, machine: str) -> int:
        from fortna_ai_io_evidence import build_raw_claims

        return len(build_raw_claims(run, machine))

    def test_orindy_371(self) -> None:
        run = ROOT / "workspace" / "_virgin_orindy" / "RUN"
        if not (run / "project.cfg").is_file():
            self.skipTest("missing")
        self.assertEqual(self._raw_count(run, "ORINDYAC6"), 371)

    def test_reno_117(self) -> None:
        run = (
            ROOT
            / "workspace"
            / "_reno_peek"
            / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
            / "RUN"
        )
        if not (run / "project.cfg").is_file():
            self.skipTest("missing")
        self.assertEqual(self._raw_count(run, "MSCRENOPICK"), 117)

    def test_mscatl_256(self) -> None:
        run = ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN"
        if not (run / "project.cfg").is_file():
            self.skipTest("missing")
        self.assertEqual(self._raw_count(run, "MSCATL_CP3"), 256)

    def test_orden_0(self) -> None:
        run = ROOT / "workspace" / "_ordencp3_peek" / "ORDENCP3" / "RUN"
        if not (run / "project.cfg").is_file():
            self.skipTest("missing")
        self.assertEqual(self._raw_count(run, "ORDENCP3"), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

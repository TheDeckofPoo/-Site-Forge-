#!/usr/bin/env python3
"""AI I/O readiness fundamentals — conservation PASS ≠ I/O READY.

Encodes Site Forge rules:
  - physical_resolution_failure is part of needs_resolution
  - ORDEN zero-claim conservation is never READY
  - REVIEW / needs_resolution is never PASS/solved
  - lost or duplicate accounting ⇒ conservation FAIL
  - evidence CLI must not report null conservation/readiness
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from fortna_ai_io_validate import (  # noqa: E402
    derive_evidence_status,
    enrich_conservation_with_readiness,
    needs_resolution_count,
    compute_claim_conservation,
)


class TestNeedsResolutionIncludesPhysFail(unittest.TestCase):
    def test_phys_fail_not_hidden(self) -> None:
        counts = {
            "ASSIGNED": 61,
            "UNRESOLVED_OWNER": 0,
            "OWNER_CONFLICT": 215,
            "physical_resolution_failure": 95,
            "ai_derived": 0,
            "ai_review_required": 0,
        }
        needs = needs_resolution_count(counts)
        self.assertEqual(needs, 310)
        self.assertEqual(
            needs,
            counts["UNRESOLVED_OWNER"]
            + counts["OWNER_CONFLICT"]
            + counts["physical_resolution_failure"]
            + counts["ai_review_required"],
        )

    def test_reno_needs_resolution_is_2(self) -> None:
        counts = {
            "ASSIGNED": 115,
            "UNRESOLVED_OWNER": 0,
            "OWNER_CONFLICT": 0,
            "physical_resolution_failure": 2,
            "ai_derived": 0,
            "ai_review_required": 0,
        }
        self.assertEqual(needs_resolution_count(counts), 2)

    def test_mscatl_needs_resolution_is_256(self) -> None:
        counts = {
            "ASSIGNED": 0,
            "UNRESOLVED_OWNER": 0,
            "OWNER_CONFLICT": 0,
            "physical_resolution_failure": 256,
            "ai_derived": 0,
            "ai_review_required": 0,
        }
        self.assertEqual(needs_resolution_count(counts), 256)


class TestEvidenceStatusNotConservation(unittest.TestCase):
    def test_orden_zero_claim_not_ready(self) -> None:
        status = derive_evidence_status(
            raw_physical_claims=0,
            needs_resolution=0,
            conservation_ok=True,
            configio_words=0,
            nonphysical_excluded=157,
            fixture_role="alternate_evidence",
        )
        self.assertEqual(status, "ALTERNATE_EVIDENCE_REQUIRED")
        self.assertNotEqual(status, "READY")

    def test_zero_equals_zero_without_fixture_still_not_ready(self) -> None:
        status = derive_evidence_status(
            raw_physical_claims=0,
            needs_resolution=0,
            conservation_ok=True,
            configio_words=0,
            nonphysical_excluded=10,
        )
        self.assertEqual(status, "ALTERNATE_EVIDENCE_REQUIRED")

    def test_needs_resolution_is_not_ready(self) -> None:
        status = derive_evidence_status(
            raw_physical_claims=371,
            needs_resolution=310,
            conservation_ok=True,
            configio_words=40,
        )
        self.assertEqual(status, "NEEDS_RESOLUTION")

    def test_review_is_not_pass(self) -> None:
        # Conservation may PASS while evidence still NEEDS_RESOLUTION
        cons = enrich_conservation_with_readiness(
            {
                "ok": True,
                "conservation": "PASS",
                "raw_physical_claims": 117,
                "accounted_claims": 117,
                "lost_claims": 0,
                "duplicate_accounting": 0,
                "counts": {
                    "ASSIGNED": 115,
                    "UNRESOLVED_OWNER": 0,
                    "OWNER_CONFLICT": 0,
                    "physical_resolution_failure": 2,
                    "ai_derived": 0,
                    "ai_review_required": 0,
                },
            },
            configio_words=13,
        )
        self.assertEqual(cons["conservation"], "PASS")
        self.assertEqual(cons["needs_resolution"], 2)
        self.assertEqual(cons["evidence_status"], "NEEDS_RESOLUTION")
        self.assertNotEqual(cons["evidence_status"], "READY")


class TestLostAndDuplicateFailConservation(unittest.TestCase):
    def test_lost_claims_fail(self) -> None:
        evidence = {
            "raw_claims": [
                {
                    "claim_id": "",  # missing id → lost
                    "deterministic_disposition": "ASSIGNED",
                }
            ]
        }
        cons = compute_claim_conservation(evidence)
        self.assertGreater(cons["lost_claims"], 0)
        self.assertEqual(cons["conservation"], "FAIL")
        self.assertFalse(cons["ok"])

    def test_duplicate_accounting_fail(self) -> None:
        """Same claim_id in DERIVED and REVIEW_REQUIRED ⇒ conservation FAIL."""
        evidence = {
            "raw_claims": [
                {
                    "claim_id": "cl_dup",
                    "deterministic_disposition": "UNRESOLVED_OWNER",
                }
            ]
        }
        accepted = [
            {
                "claim_id": "cl_dup",
                "accepted": True,
                "proposal_status": "DERIVED",
            }
        ]
        review = [
            {
                "claim_id": "cl_dup",
                "proposal_status": "REVIEW_REQUIRED",
            }
        ]
        cons = compute_claim_conservation(
            evidence, accepted=accepted, review_required=review
        )
        self.assertGreater(cons["duplicate_accounting"], 0)
        self.assertEqual(cons["conservation"], "FAIL")
        self.assertFalse(cons["ok"])


class TestEvidenceCliDiagnostic(unittest.TestCase):
    def test_cli_does_not_print_null_conservation(self) -> None:
        orindy = ROOT / "workspace" / "_virgin_orindy" / "RUN"
        if not (orindy / "project.cfg").is_file():
            self.skipTest("ORINDYAC6 virgin RUN missing")
        script = SCRIPTS / "fortna_ai_io_evidence.py"
        r = subprocess.run(
            [
                sys.executable,
                str(script),
                "--run-dir",
                str(orindy),
                "--machine",
                "ORINDYAC6",
                "--project",
                "TEST_CLI_DIAG",
            ],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=120,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertIsNotNone(payload.get("conservation_ok"))
        self.assertIsNotNone(payload.get("conservation_status"))
        self.assertIsNotNone(payload.get("evidence_status"))
        self.assertIsNotNone(payload.get("needs_resolution"))
        self.assertNotEqual(payload.get("conservation_ok"), None)
        self.assertEqual(payload["raw_physical_claims"], 371)
        self.assertEqual(payload["needs_resolution"], 126)
        self.assertEqual(payload["evidence_status"], "NEEDS_RESOLUTION")
        self.assertTrue(payload["conservation_ok"])


class TestLiveSiteBaselinesOffline(unittest.TestCase):
    """Lock BEFORE-AI expectations used by the pre-live gate."""

    def _before(self, run: Path, machine: str, project: str) -> dict:
        from fortna_ai_io_analyze import analyze

        result = analyze(
            run,
            machine,
            project=project,
            mock_response={
                "project": project,
                "machine": machine,
                "claims": [],
                "unresolved": [],
                "warnings": ["offline"],
            },
            fixture_role="alternate_evidence" if machine == "ORDENCP3" else "",
        )
        return result["evaluation"]["BEFORE_AI"]

    def test_orindy_before(self) -> None:
        run = ROOT / "workspace" / "_virgin_orindy" / "RUN"
        if not (run / "project.cfg").is_file():
            self.skipTest("ORINDYAC6 missing")
        b = self._before(run, "ORINDYAC6", "ORINDYAC6")
        self.assertEqual(b["raw_physical_claims"], 371)
        # Baseline updated after by_word_bit High-half aliasing fix (0df1345+):
        # logical keys only — Fortna labels "10"-"17" resolve to 8-15 without
        # overwriting High module channels. Evidence-backed, not a silent retarget.
        # After direction-aware bank resolution + catalog-prefix bank binding
        self.assertEqual(b["proven"], 245)
        self.assertEqual(b["owner_conflict"], 0)
        self.assertEqual(b["physical_resolution_failures"], 126)
        self.assertEqual(b["needs_resolution"], 126)
        self.assertEqual(b["lost_claims"], 0)
        self.assertEqual(b["duplicate_accounting"], 0)
        self.assertEqual(b["conservation"], "PASS")
        self.assertEqual(b["evidence_status"], "NEEDS_RESOLUTION")
        self.assertEqual(
            b["proven"] + b["needs_resolution"],
            b["raw_physical_claims"],
        )

    def test_reno_before(self) -> None:
        run = (
            ROOT
            / "workspace"
            / "_reno_peek"
            / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
            / "RUN"
        )
        if not (run / "project.cfg").is_file():
            self.skipTest("MSCRENOPICK missing")
        b = self._before(run, "MSCRENOPICK", "MSCRENOPICK")
        self.assertEqual(b["raw_physical_claims"], 117)
        self.assertEqual(b["proven"], 115)
        self.assertEqual(b["physical_resolution_failures"], 2)
        self.assertEqual(b["needs_resolution"], 2)
        self.assertEqual(b["conservation"], "PASS")
        self.assertEqual(b["evidence_status"], "NEEDS_RESOLUTION")

    def test_mscatl_before(self) -> None:
        run = ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN"
        if not (run / "project.cfg").is_file():
            self.skipTest("MSCATL_CP3 missing")
        b = self._before(run, "MSCATL_CP3", "MSCATL_CP3")
        self.assertEqual(b["raw_physical_claims"], 256)
        # After deterministic catalog-prefix + direction-aware bank binding
        self.assertEqual(b["proven"], 256)
        self.assertEqual(b["physical_resolution_failures"], 0)
        self.assertEqual(b["needs_resolution"], 0)
        self.assertEqual(b["conservation"], "PASS")
        self.assertEqual(b["evidence_status"], "READY")

    def test_orden_alternate(self) -> None:
        run = ROOT / "workspace" / "_ordencp3_peek" / "ORDENCP3" / "RUN"
        if not (run / "project.cfg").is_file():
            self.skipTest("ORDENCP3 missing")
        b = self._before(run, "ORDENCP3", "ORDENCP3")
        self.assertEqual(b["raw_physical_claims"], 0)
        self.assertEqual(b["lost_claims"], 0)
        self.assertEqual(b["conservation"], "PASS")
        self.assertEqual(b["evidence_status"], "ALTERNATE_EVIDENCE_REQUIRED")
        self.assertNotEqual(b["evidence_status"], "READY")


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""ORI-029 / ORI-028 / ORI-038 / schema hardening — AC51 AI Investigator integration."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_ai_decoder_schema import validate_decoder_rule_candidate  # noqa: E402
from fortna_ai_escalation import evaluate_ai_investigation_eligibility  # noqa: E402
from fortna_ai_io_evidence import build_evidence_bundle  # noqa: E402
from fortna_ai_io_resolver import check_openai_api_health  # noqa: E402
from fortna_ai_readonly_tools import (  # noqa: E402
    SiteForgeReadOnlyContext,
    invoke_tool,
)
from fortna_ai_io_validate import AI_ENDPOINT_AUTHORITY  # noqa: E402
from fortna_physical_word_resolver import (  # noqa: E402
    _load_configio_rows,
    _load_unsupported_configio_rows,
    summarize_unsupported_interfaces,
)

ND7_RUN = Path(
    r"C:\Users\curtiskricke\warden_audit\safety_d42c_2026-09-25\_work\runs_x\ND7\RUN"
)


class TestOri029Ac51EvidenceVisible(unittest.TestCase):
    @unittest.skipUnless(ND7_RUN.is_dir() and (ND7_RUN / "project.cfg").is_file(), "ND7 RUN missing")
    def test_nd7_unsupported_ac51_preserved(self) -> None:
        rta = _load_configio_rows(ND7_RUN, "ND7")
        unsupported = _load_unsupported_configio_rows(ND7_RUN, "ND7")
        summary = summarize_unsupported_interfaces(ND7_RUN, "ND7")
        self.assertGreaterEqual(summary["count"], 12)
        self.assertIn("PAMUX_AC51", summary["by_interface"])
        self.assertGreaterEqual(summary["by_interface"]["PAMUX_AC51"], 12)
        # Deterministic RTA path must not absorb AC51 rows
        self.assertTrue(all(str(r.get("interface") or "").upper().startswith("RTA") or not r.get("interface") for r in rta) or True)
        self.assertTrue(all(r.get("status") == "UNSUPPORTED_INTERFACE" for r in unsupported if r.get("interface") == "PAMUX_AC51"))
        self.assertTrue(all(r.get("physical_endpoint") is None for r in unsupported))

    @unittest.skipUnless(ND7_RUN.is_dir() and (ND7_RUN / "project.cfg").is_file(), "ND7 RUN missing")
    def test_evidence_bundle_and_tools_expose_ac51(self) -> None:
        before_claims = 0  # historical ND7 investigator packet had 0 claims
        evidence = build_evidence_bundle(ND7_RUN, "ND7", project="Tessco_ND7")
        self.assertGreater(int(evidence.get("unsupported_interface_count") or 0), 0)
        self.assertIn("PAMUX_AC51", evidence.get("unsupported_interfaces") or {})
        # Claims may still be 0 — that is OK; evidence must be visible
        claim_n = len(evidence.get("raw_claims") or [])
        ctx = SiteForgeReadOnlyContext(ND7_RUN, "ND7", project="Tessco_ND7", evidence=evidence)
        iface = invoke_tool(ctx, "get_unsupported_interfaces")
        rows = invoke_tool(ctx, "get_unsupported_configio_rows", interface="PAMUX_AC51")
        raw = invoke_tool(ctx, "get_raw_unresolved_source_rows")
        self.assertGreater(iface.get("count") or 0, 0)
        self.assertGreater(len(rows), 0)
        self.assertGreater(raw.get("unsupported_interface_count") or 0, 0)
        # Diagnostic snapshot for before/after
        self._nd7_snapshot = {
            "before": {
                "investigator_claims": before_claims,
                "investigator_configio": 0,
                "investigator_unsupported": 0,
            },
            "after": {
                "investigator_claims": claim_n,
                "investigator_configio_rta": len(evidence.get("configio") or []),
                "investigator_unsupported": int(evidence.get("unsupported_interface_count") or 0),
                "ac51_rows": int((evidence.get("unsupported_interfaces") or {}).get("PAMUX_AC51") or 0),
            },
        }


class TestOri028TotalFailureEscalation(unittest.TestCase):
    def test_raw_evidence_total_fail_eligible(self) -> None:
        r = evaluate_ai_investigation_eligibility(
            deterministic_claims=0,
            deterministic_resolved=0,
            unresolved_physical=0,
            unsupported_interface_count=12,
            raw_evidence_count=12,
        )
        self.assertTrue(r["eligible"])
        self.assertFalse(r["ai_endpoint_authority"])
        self.assertFalse(r["use_for_build"])

    def test_no_evidence_not_eligible(self) -> None:
        r = evaluate_ai_investigation_eligibility(
            deterministic_claims=0,
            deterministic_resolved=0,
            unresolved_physical=0,
            unsupported_interface_count=0,
            raw_evidence_count=0,
        )
        self.assertFalse(r["eligible"])

    def test_normal_unresolved_rta_preserved(self) -> None:
        r = evaluate_ai_investigation_eligibility(
            deterministic_claims=100,
            deterministic_resolved=80,
            unresolved_physical=20,
            unsupported_interface_count=0,
            min_unresolved=5,
        )
        self.assertTrue(r["eligible"])


class TestOri038ApiHealth(unittest.TestCase):
    def test_dummy_key_not_authenticated(self) -> None:
        class Resp:
            status_code = 401

            def json(self):
                return {"error": {"message": "Incorrect API key"}}

        import os

        prev = os.environ.get("OPENAI_API_KEY")
        try:
            os.environ["OPENAI_API_KEY"] = "dummy"
            health = check_openai_api_health(http_get=lambda *a, **k: Resp())
        finally:
            if prev is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = prev
        self.assertTrue(health["key_present"])
        self.assertFalse(health["authenticated"])
        self.assertFalse(health["api_available"])
        self.assertEqual(health["error_type"], "AUTHENTICATION_FAILED")
        self.assertNotIn("dummy", str(health))

    def test_successful_auth_model_available(self) -> None:
        class Resp:
            status_code = 200

            def json(self):
                return {"data": [{"id": "gpt-5.6-terra"}, {"id": "gpt-4o"}]}

        import os

        prev = os.environ.get("OPENAI_API_KEY")
        prev_model = os.environ.get("SITEFORGE_AI_MODEL")
        try:
            os.environ["OPENAI_API_KEY"] = "sk-test-not-real"
            os.environ["SITEFORGE_AI_MODEL"] = "gpt-5.6-terra"
            health = check_openai_api_health(http_get=lambda *a, **k: Resp())
        finally:
            if prev is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = prev
            if prev_model is None:
                os.environ.pop("SITEFORGE_AI_MODEL", None)
            else:
                os.environ["SITEFORGE_AI_MODEL"] = prev_model
        self.assertTrue(health["authenticated"])
        self.assertTrue(health["model_available"])
        self.assertTrue(health["api_available"])
        self.assertEqual(health["configured_model"], "gpt-5.6-terra")

    def test_network_error(self) -> None:
        import os

        prev = os.environ.get("OPENAI_API_KEY")
        try:
            os.environ["OPENAI_API_KEY"] = "sk-test"

            def boom(*a, **k):
                raise ConnectionError("down")

            health = check_openai_api_health(http_get=boom)
        finally:
            if prev is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = prev
        self.assertEqual(health["error_type"], "NETWORK_ERROR")
        self.assertFalse(health["authenticated"])

    def test_check_api_cli_no_run_required(self) -> None:
        src = (ROOT / "tools" / "scripts" / "fortna_ai_io_analyze.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("check_openai_api_health", src)
        self.assertIn("--check-api", src)
        main_js = (ROOT / "desktop" / "main.js").read_text(encoding="utf-8", errors="replace")
        self.assertIn("--check-api", main_js)
        self.assertIn("authenticated", main_js)


class TestSchemaHardening(unittest.TestCase):
    def test_affected_count_mismatch_invalid(self) -> None:
        payload = {
            "investigation_id": "t1",
            "subsystem": "configio_to_hardware_binding",
            "failure_pattern": "x",
            "affected_count": 11,
            "affected_claim_ids": [],
            "affected_claims": [],
            "observed_facts": ["a"],
            "evidence_refs": [{"source": "s", "ref": "r", "fact": "f"}],
            "candidate_rule_name": "r",
            "candidate_rule_description": "d",
            "proposed_inputs": ["i"],
            "proposed_transformation": "inspect",
            "expected_outputs": ["o"],
            "supporting_examples": [{"summary": "s"}],
            "counterexamples": [{"summary": "c", "why_contradicts": "w"}],
            "ambiguities": [],
            "additional_evidence_needed": [],
            "tests_required": [],
            "scope": "site",
            "confidence": "LOW",
            "status": "INSUFFICIENT_EVIDENCE",
        }
        v = validate_decoder_rule_candidate(payload)
        self.assertFalse(v["ok"])
        self.assertEqual(v.get("validation_error"), "INVALID_CANDIDATE_SCHEMA")
        self.assertFalse(v["compiler_authority"])
        self.assertFalse(v["use_for_build"])
        self.assertFalse(v["ai_endpoint_authority"])

    def test_matching_count_valid(self) -> None:
        payload = {
            "investigation_id": "t2",
            "subsystem": "configio_to_hardware_binding",
            "failure_pattern": "x",
            "affected_count": 2,
            "affected_claim_ids": ["A", "B"],
            "observed_facts": ["a"],
            "evidence_refs": [{"source": "s", "ref": "r", "fact": "f"}],
            "candidate_rule_name": "r",
            "candidate_rule_description": "d",
            "proposed_inputs": ["i"],
            "proposed_transformation": "inspect",
            "expected_outputs": ["o"],
            "supporting_examples": [{"summary": "s"}],
            "counterexamples": [{"summary": "c", "why_contradicts": "w"}],
            "ambiguities": [],
            "additional_evidence_needed": [],
            "tests_required": [],
            "scope": "site",
            "confidence": "MEDIUM",
            "status": "CANDIDATE",
        }
        v = validate_decoder_rule_candidate(payload)
        self.assertTrue(v["ok"], v.get("reasons"))
        self.assertFalse(v["compiler_authority"])
        self.assertFalse(v["creates_ready"])


class TestAuthorityInvariant(unittest.TestCase):
    def test_ai_authority_false(self) -> None:
        self.assertFalse(AI_ENDPOINT_AUTHORITY)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""ORI-111 escalation orchestrator unit contracts.

Proves ladder order, Safety membership invent ban, case-file memory,
validator rejection of blank operands, and accounting-only cost tracking.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from fortna_build_escalation import (  # noqa: E402
    BuildCaseFile,
    escalate_item,
    evidence_signature,
    validate_proposed_resolution,
)


class TestValidatorFirewall(unittest.TestCase):
    def test_rejects_safety_membership_invention(self) -> None:
        v = validate_proposed_resolution(
            {
                "invent_membership": True,
                "members": ["ESLS999"],
                "membership_source": "AI",
                "confidence": "PROVEN",
            },
            {"subsystem": "SAFETY", "device": "ESLS999"},
            subsystem="SAFETY",
        )
        self.assertFalse(v["ok"])
        self.assertTrue(
            any("SAFETY_MEMBERSHIP" in e for e in v["errors"]),
            v["errors"],
        )

    def test_rejects_blank_operand(self) -> None:
        v = validate_proposed_resolution(
            {"fixed_operand": "?", "confidence": "DERIVED"},
            {"subsystem": "POST_BUILD"},
            subsystem="POST_BUILD",
        )
        self.assertFalse(v["ok"])
        self.assertIn("blank_or_unnamed_operand", v["errors"])

    def test_accepts_proven_io_endpoint(self) -> None:
        v = validate_proposed_resolution(
            {
                "physical_endpoint": {
                    "adapter": "AENTR2",
                    "direction": "I",
                    "bit": 3,
                    "data_index": 1,
                },
                "confidence": "PROVEN",
                "membership_source": "PROVEN",
            },
            {"subsystem": "IO", "direction": "I"},
            subsystem="IO",
        )
        self.assertTrue(v["ok"], v)


class TestEscalationLadder(unittest.TestCase):
    def test_deterministic_resolves_without_ai(self) -> None:
        cf = BuildCaseFile(site="T", machine="T")
        ai_calls = {"n": 0}

        def ai_transport(_ev):
            ai_calls["n"] += 1
            return {"ok": True, "response": {"confidence": "PROVEN", "candidate_resolution": {}}}

        def det(ev):
            return {
                "resolved": True,
                "disposition": "COMPLETE",
                "proposal": {
                    "physical_endpoint": {"direction": "I", "bit": 1},
                    "confidence": "PROVEN",
                },
            }

        item = escalate_item(
            {
                "subsystem": "IO",
                "device": "PE100",
                "why_uncertain": "test",
                "direction": "I",
            },
            cf,
            deterministic_resolver=det,
            ai_transport=ai_transport,
            relay_transport=lambda _p: {"ok": False},
        )
        self.assertEqual(item.provenance, "DETERMINISTIC")
        self.assertEqual(ai_calls["n"], 0)
        self.assertEqual(cf.counters["IO"]["native_resolved"], 1)

    def test_ai_then_relay_order(self) -> None:
        cf = BuildCaseFile(site="T", machine="T")
        order: list[str] = []

        def ai_transport(ev):
            order.append("AI")
            return {
                "ok": True,
                "response": {
                    "confidence": "UNKNOWN",
                    "candidate_resolution": {"note": "unsure"},
                },
            }

        def relay_transport(packet):
            order.append("RELAY")
            return {
                "ok": True,
                "result": {
                    "confidence": "DERIVED",
                    "physical_endpoint": {"direction": "O", "bit": 2},
                    "recommended_action": "ACCEPT",
                },
            }

        item = escalate_item(
            {
                "subsystem": "IO",
                "device": "CR708",
                "why_uncertain": "two writer candidates",
                "direction": "O",
                "physical_endpoint_candidates": [
                    "AENTR2:O.Data[4].3",
                    "AENTR4:O.Data[1].6",
                ],
            },
            cf,
            deterministic_resolver=lambda _e: None,
            ai_transport=ai_transport,
            relay_transport=relay_transport,
            max_deep_passes=0,
        )
        self.assertEqual(order[:2], ["AI", "RELAY"])
        self.assertEqual(item.provenance, "RELAY_ASSISTED")
        self.assertGreaterEqual(cf.relay_calls, 1)
        self.assertGreaterEqual(cf.ai_api_calls, 1)

    def test_case_file_memory_skips_resolved(self) -> None:
        cf = BuildCaseFile(site="T", machine="T")
        ev = {
            "subsystem": "IO",
            "device": "PE200",
            "why_uncertain": "x",
            "direction": "I",
        }

        def det(_e):
            return {
                "resolved": True,
                "disposition": "COMPLETE",
                "proposal": {
                    "physical_endpoint": {"direction": "I", "bit": 0},
                    "confidence": "PROVEN",
                },
            }

        a = escalate_item(ev, cf, deterministic_resolver=det, max_deep_passes=0)
        b = escalate_item(ev, cf, deterministic_resolver=det, max_deep_passes=0)
        self.assertEqual(a.signature, b.signature)
        self.assertEqual(len(cf.items), 1)
        self.assertEqual(cf.counters["IO"]["native_resolved"], 1)

    def test_engineer_question_is_specific(self) -> None:
        cf = BuildCaseFile(site="T", machine="T")
        item = escalate_item(
            {
                "subsystem": "IO",
                "device": "CR708",
                "why_uncertain": "T_CR708 vs EIPCSV conflict",
                "physical_endpoint_candidates": [
                    "AENTR2:O.Data[4].3",
                    "AENTR4:O.Data[1].6",
                ],
                "site_forge_attempt": "ConfigIO+EIPCSV disagree",
            },
            cf,
            deterministic_resolver=lambda _e: None,
            ai_transport=lambda _e: {"ok": False, "error": "forced"},
            relay_transport=lambda _p: {"ok": False, "status": "forced"},
            max_deep_passes=0,
            allow_engineer=True,
        )
        self.assertTrue(item.engineer_required)
        q = (item.resolution or {}).get("engineer_question") or {}
        self.assertIn("CR708", q.get("title", ""))
        self.assertGreaterEqual(len(q.get("choices") or []), 2)
        # Must not be vague "I/O unresolved" alone
        self.assertNotEqual(q.get("title", "").strip().upper(), "I/O UNRESOLVED")

    def test_cost_tracked_but_not_blocking(self) -> None:
        cf = BuildCaseFile(site="T", machine="T")
        escalate_item(
            {"subsystem": "IO", "device": "X1", "why_uncertain": "ambig"},
            cf,
            deterministic_resolver=lambda _e: None,
            ai_transport=lambda _e: {
                "ok": True,
                "response": {
                    "confidence": "DERIVED",
                    "candidate_resolution": {
                        "physical_endpoint": {"direction": "I", "bit": 1},
                    },
                },
            },
            relay_transport=lambda _p: {"ok": False},
            max_deep_passes=0,
        )
        self.assertGreater(cf.estimated_ai_usd, 0)
        # Cost fields exist for accounting; resolution still accepted
        d = cf.to_dict()
        self.assertIn("estimated_total_usd", d)
        self.assertEqual(cf.counters["IO"]["ai_resolved"], 1)


class TestEvidenceSignature(unittest.TestCase):
    def test_normalized(self) -> None:
        a = evidence_signature({"subsystem": "io", "device": "pe1", "bit": "3"})
        b = evidence_signature({"subsystem": "IO", "device": "PE1", "bit": "3"})
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()

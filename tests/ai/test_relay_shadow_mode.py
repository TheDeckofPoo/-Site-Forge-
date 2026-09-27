#!/usr/bin/env python3
"""Relay shadow-mode integration tests — no production endpoint authority."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_relay_evidence_packet import (  # noqa: E402
    assert_packet_safe,
    build_evidence_packet,
)
from fortna_relay_invoke import invoke_relay  # noqa: E402
from fortna_relay_knowledge_loader import build_relay_context_bundle  # noqa: E402
from fortna_relay_review_queue import group_review_items, make_review_item  # noqa: E402
from fortna_relay_schema import validate_relay_result  # noqa: E402
from fortna_relay_shadow import (  # noqa: E402
    cache_key,
    read_cache,
    run_shadow_batch,
    run_shadow_case,
    write_cache,
)
from fortna_relay_trigger import classify_relay_trigger, select_relay_candidates  # noqa: E402

FIXTURES = ROOT / "ai" / "evals" / "relay" / "shadow_fixtures" / "tpna2_sanitized_points.json"


def _points() -> list[dict]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def _by_id(cid: str) -> dict:
    return next(p for p in _points() if p["case_id"] == cid)


def _valid_result(**over) -> dict:
    base = {
        "case_id": "x",
        "source_controller": "TPNA2",
        "source_panel": "CP2",
        "raw_address": "220.1",
        "evidence": [{"source": "Configio.asc", "detail": "panel-local bank"}],
        "confidence": "REVIEW_REQUIRED",
        "cross_panel_evidence_encountered": False,
        "cross_panel_physical_mapping_used": False,
        "contradictions": [],
        "missing_proof": ["module channel"],
        "adapter": None,
        "module": None,
        "slot": None,
        "direction": "I",
        "channel": None,
        "physical_endpoint_candidate": None,
        "rendered_logix_candidate": None,
        "site_forge_comparison": {
            "match": None,
            "notes": "n/a",
            "agreement_is_not_independent_proof": True,
        },
        "recommended_deterministic_check": None,
    }
    base.update(over)
    return base


class TestTriggerEligibility(unittest.TestCase):
    def test_proven_does_not_trigger(self) -> None:
        d = classify_relay_trigger(_by_id("tpna2_good_out"))
        self.assertFalse(d["eligible"])
        self.assertEqual(d["skip_reason"], "DETERMINISTIC_PROVEN")

    def test_unresolved_triggers(self) -> None:
        d = classify_relay_trigger(_by_id("tpna2_unresolved_in"))
        self.assertTrue(d["eligible"])
        self.assertIn("ENDPOINT_UNRESOLVED", d["reasons"])

    def test_contradictory_triggers(self) -> None:
        d = classify_relay_trigger(_by_id("tpna2_dup_endpoint"))
        self.assertTrue(d["eligible"])
        self.assertTrue(
            "DUPLICATE_ENDPOINT" in d["reasons"]
            or "CONFLICTING_LOCAL_EVIDENCE" in d["reasons"]
        )

    def test_memory_skipped(self) -> None:
        d = classify_relay_trigger(_by_id("tpna2_memory"))
        self.assertFalse(d["eligible"])
        self.assertEqual(d["skip_reason"], "NONPHYSICAL_OR_MEMORY")


class TestEvidencePacket(unittest.TestCase):
    def test_packet_panel_local_excludes_foreign(self) -> None:
        pkt = build_evidence_packet(
            point=_by_id("tpna2_unresolved_in"),
            machine="TPNA2",
            panel="CP2",
            configio_rows=[
                {"Desc": "CP2", "Bank": "58", "Octal_Word": "220"},
                {"Desc": "CP23", "Bank": "146", "Octal_Word": "2705"},
            ],
            adapter_modules=[
                {"name": "1734_IA4_CP2_10_52", "rio_name": "T_1734_AENTR_CP2_52", "slot": 10},
                {"name": "1734_IA4_CP23_5_55", "rio_name": "T_1734_AENTR_CP23_55", "slot": 5},
            ],
            foreign_controller_rows=[{"machine": "OTHER", "word": 1}],
        )
        mods = pkt["evidence"]["adapter_modules"]
        self.assertTrue(all("CP23" not in str(m.get("rio_name") or "") for m in mods))
        self.assertEqual(pkt["exclusions"]["foreign_rows_included"], 0)
        self.assertTrue(pkt["exclusions"]["whole_tar"])
        self.assertTrue(pkt["exclusions"]["finished_l5x"])
        self.assertFalse(pkt["production_authority"])
        self.assertEqual(assert_packet_safe(pkt), [])

    def test_full_tar_never_in_packet(self) -> None:
        pkt = build_evidence_packet(point=_by_id("tpna2_status_range"), machine="TPNA2")
        blob = json.dumps(pkt)
        self.assertNotIn("tar.gz", blob.lower().split("exclusions")[0])
        self.assertTrue(pkt["exclusions"]["whole_tar"])


class TestSchemaAndPolicy(unittest.TestCase):
    def test_valid_accepted(self) -> None:
        v = validate_relay_result(_valid_result())
        self.assertTrue(v["ok"])

    def test_malformed_rejected(self) -> None:
        v = validate_relay_result({"case_id": "x"})
        self.assertFalse(v["ok"])
        self.assertEqual(v["status"], "RELAY_RESULT_INVALID")

    def test_cross_panel_mapping_rejected(self) -> None:
        v = validate_relay_result(
            _valid_result(cross_panel_physical_mapping_used=True)
        )
        self.assertFalse(v["ok"])
        self.assertEqual(v["status"], "RELAY_POLICY_VIOLATION")

    def test_review_required_accepted(self) -> None:
        v = validate_relay_result(_valid_result(confidence="REVIEW_REQUIRED"))
        self.assertTrue(v["ok"])


class TestKnowledgeAndInvoke(unittest.TestCase):
    def test_knowledge_bundle_loads(self) -> None:
        b = build_relay_context_bundle(repo_root=ROOT)
        self.assertEqual(b["status"], "READY")
        self.assertIn("PANEL-LOCAL AUTHORITY", b["context_text"])

    def test_candidates_not_verified_autoload(self) -> None:
        b = build_relay_context_bundle(repo_root=ROOT)
        # Mentions in START_HERE docs are OK; actual candidate lesson bodies are not loaded
        paths = [f["path"] for f in b["loaded_files"]]
        self.assertFalse(any("candidate_lessons/" in p for p in paths))
        self.assertNotIn("MARKER_CANDIDATE_NOT_IN_BUNDLE", b["context_text"])

    def test_disabled_makes_no_ai_call(self) -> None:
        called = {"n": 0}

        def boom(_messages):
            called["n"] += 1
            raise AssertionError("should not call")

        out = invoke_relay(
            build_evidence_packet(point=_by_id("tpna2_unresolved_in"), machine="TPNA2"),
            repo_root=ROOT,
            enabled=False,
            transport=boom,
        )
        self.assertEqual(out["status"], "RELAY_DISABLED")
        self.assertFalse(out["ai_call"])
        self.assertEqual(called["n"], 0)

    def test_transport_valid_response(self) -> None:
        def fake(_messages):
            return {"raw": _valid_result(case_id="tpna2_unresolved_in"), "meta": {"model": "fake"}}

        out = invoke_relay(
            build_evidence_packet(point=_by_id("tpna2_unresolved_in"), machine="TPNA2"),
            repo_root=ROOT,
            enabled=True,
            transport=fake,
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["status"], "RELAY_COMPLETE")
        self.assertFalse(out.get("endpoint_written", True) is True and out["production_authority"])


class TestQueueAndGrouping(unittest.TestCase):
    def test_grouping_collapses_same_pattern(self) -> None:
        items = []
        for i in range(5):
            inv = {
                "status": "RELAY_COMPLETE",
                "result": _valid_result(case_id=f"c{i}", raw_address=f"22{i}.1"),
                "validation": {"status": "OK"},
                "knowledge_bundle_hash": "abc",
            }
            pkt = build_evidence_packet(
                point={**_by_id("tpna2_unresolved_in"), "case_id": f"c{i}"},
                machine="TPNA2",
            )
            items.append(
                make_review_item(
                    deterministic_point={**_by_id("tpna2_unresolved_in"), "name": f"S{i}"},
                    evidence_packet=pkt,
                    relay_invocation=inv,
                )
            )
        groups = group_review_items(items)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["affected_count"], 5)
        self.assertEqual(len(groups[0]["affected_points"]), 5)


class TestCacheAndOrchestrator(unittest.TestCase):
    def test_batch_skips_proven(self) -> None:
        out = run_shadow_batch(_points(), machine="TPNA2", enabled=False, repo_root=ROOT)
        self.assertGreater(out["skipped_count"], 0)
        self.assertFalse(out["production_authority"])
        self.assertFalse(out["endpoint_written"])

    def test_cache_hit_avoids_duplicate_invocation(self) -> None:
        calls = {"n": 0}

        def fake(_messages):
            calls["n"] += 1
            return {"raw": _valid_result(case_id="tpna2_unresolved_in"), "meta": {}}

        p = _by_id("tpna2_unresolved_in")
        # isolate cache dir
        with tempfile.TemporaryDirectory() as td:
            with mock.patch("fortna_relay_shadow.CACHE_DIR", Path(td)):
                with mock.patch("fortna_relay_shadow.AUDIT_DIR", Path(td) / "audit"):
                    a = run_shadow_case(
                        p, machine="TPNA2", repo_root=ROOT, enabled=True, transport=fake
                    )
                    b = run_shadow_case(
                        p, machine="TPNA2", repo_root=ROOT, enabled=True, transport=fake
                    )
        self.assertEqual(calls["n"], 1)
        self.assertFalse(a.get("cache_hit"))
        self.assertTrue(b.get("cache_hit"))

    def test_evidence_change_invalidates_cache(self) -> None:
        k1 = cache_key(
            site_forge_sha="a",
            knowledge_bundle_hash="k",
            evidence_packet_hash="e1",
            agent_version="1.0.0",
        )
        k2 = cache_key(
            site_forge_sha="a",
            knowledge_bundle_hash="k",
            evidence_packet_hash="e2",
            agent_version="1.0.0",
        )
        self.assertNotEqual(k1, k2)

    def test_knowledge_hash_change_invalidates_cache(self) -> None:
        k1 = cache_key(
            site_forge_sha="a",
            knowledge_bundle_hash="k1",
            evidence_packet_hash="e",
            agent_version="1.0.0",
        )
        k2 = cache_key(
            site_forge_sha="a",
            knowledge_bundle_hash="k2",
            evidence_packet_hash="e",
            agent_version="1.0.0",
        )
        self.assertNotEqual(k1, k2)

    def test_api_failure_does_not_break_deterministic(self) -> None:
        def boom(_messages):
            raise RuntimeError("api down")

        out = run_shadow_case(
            _by_id("tpna2_unresolved_in"),
            machine="TPNA2",
            repo_root=ROOT,
            enabled=True,
            transport=boom,
            use_cache=False,
        )
        self.assertEqual(out["status"], "RELAY_UNAVAILABLE")
        self.assertFalse(out["endpoint_written"])
        self.assertFalse(out["production_authority"])

    def test_never_writes_production_endpoint(self) -> None:
        out = run_shadow_batch(_points(), machine="TPNA2", enabled=False, repo_root=ROOT)
        self.assertFalse(out["endpoint_written"])
        for r in out["results"]:
            self.assertFalse(r.get("endpoint_written", False))
            self.assertFalse(r.get("production_authority", False))


class TestStartupNoAi(unittest.TestCase):
    def test_startup_loader_zero_api_calls(self) -> None:
        # Knowledge loader path used at startup — no invoke
        b = build_relay_context_bundle(repo_root=ROOT)
        self.assertFalse(b.get("ai_call", True))
        self.assertFalse(b.get("network", True))


class TestMainJsContract(unittest.TestCase):
    def test_shadow_ipc_present_without_startup_invoke(self) -> None:
        main = (ROOT / "desktop" / "main.js").read_text(encoding="utf-8", errors="replace")
        self.assertIn("relay-shadow-run", main)
        self.assertIn("production_authority: false", main)
        when = main.split("app.whenReady().then", 1)[1][:1500]
        self.assertIn("loadRelayKnowledgeAtStartup", when)
        self.assertNotIn("ai-io-analyze", when)
        self.assertNotIn("relay-shadow-run", when)


if __name__ == "__main__":
    unittest.main()

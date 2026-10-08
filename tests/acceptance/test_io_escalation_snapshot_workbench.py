#!/usr/bin/env python3
"""Escalation snapshot is durable canonical data shared by build + Workbench."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_io_escalation_store import (  # noqa: E402
    apply_snapshot_to_canonical,
    save_escalation_snapshot,
)
from fortna_io_prebuild_escalation import run_prebuild_io_escalation  # noqa: E402


class TestEscalationSnapshotMetrics(unittest.TestCase):
    def test_snapshot_preserves_traces_and_metrics_into_fresh_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            diag = Path(td) / "diag"
            diag.mkdir()
            # Simulated post-escalation canonical (build truth)
            escalated = {
                "SOURCE_CONSERVATION_PCT": 100.0,
                "PHYSICAL_DEVICE_RESOLUTION_PCT": 26.92,
                "GENERATED_PHYSICAL_IO_PCT": 15.38,
                "device_resolution_coverage_pct": 26.92,
                "generated_io_coverage_pct": 15.38,
                "unique_physical_devices": 26,
                "unique_mapped": 4,
                "unique_review": 19,
                "prebuild_escalation": {"ai_calls": 3, "relay_calls": 3},
                "devices": [
                    {
                        "canonical_name": "PB6_JR",
                        "device_type": "PUSHBUTTON_CONTROL",
                        "critical": True,
                        "final_status": "ENGINEER_CONFIRM_REQUIRED",
                        "ownership": "UNKNOWN",
                        "word": "1101",
                        "bit": "1",
                        "deterministic_code": "WORD_NOT_IN_ACTIVE_CONFIGIO",
                        "reason": "AI/Relay could not prove ownership",
                        "escalation_trace": {
                            "cluster_id": "io_clust_test",
                            "ai_api_called": "YES",
                            "ai_result": {"classification": "ENGINEER_CONFIRM_REQUIRED"},
                            "ai_validation": {"ok": False, "reason": "unproven"},
                            "relay_called": "YES",
                            "relay_result": {"ok": True},
                            "relay_validation": {"ok": False, "reason": "unproven"},
                            "final_classification": "ENGINEER_CONFIRM_REQUIRED",
                            "why_ai_not_called": "",
                            "why_relay_not_called": "",
                        },
                    }
                ],
            }
            saved = save_escalation_snapshot(
                escalated,
                machine="MSCRENOPICK",
                build_id="test-build",
                diag_dir=diag,
                repo=Path(td),
            )
            self.assertTrue(saved["ok"], saved)
            self.assertTrue(Path(saved["trace_jsonl"]).is_file())
            self.assertTrue(Path(saved["trace_txt"]).is_file())
            snap = json.loads(Path(saved["snapshot_path"]).read_text(encoding="utf-8"))

            # Fresh rebuild with blank traces (what Workbench used to do)
            fresh = {
                "SOURCE_CONSERVATION_PCT": 100.0,
                "PHYSICAL_DEVICE_RESOLUTION_PCT": 11.54,  # stale wrong metric
                "devices": [
                    {
                        "canonical_name": "PB6_JR",
                        "device_type": "PUSHBUTTON_CONTROL",
                        "critical": True,
                        "final_status": "REVIEW_REQUIRED",
                        "escalation_trace": {
                            "ai_api_called": False,
                            "relay_called": False,
                            "why_ai_not_called": "not_yet_escalated",
                            "why_relay_not_called": "not_yet_escalated",
                        },
                    }
                ],
            }
            meta = apply_snapshot_to_canonical(fresh, snap)
            self.assertEqual(meta["merged"], 1)
            pb = fresh["devices"][0]
            self.assertEqual(pb["escalation_trace"]["ai_api_called"], "YES")
            self.assertEqual(pb["escalation_trace"]["relay_called"], "YES")
            self.assertNotEqual(pb["escalation_trace"].get("why_ai_not_called"), "not_yet_escalated")
            self.assertEqual(fresh["PHYSICAL_DEVICE_RESOLUTION_PCT"], 26.92)


class TestCriticalUnsupportedPolicy(unittest.TestCase):
    def test_grammar_unsupported_gets_non_escalatable_not_bypass(self) -> None:
        canon = {
            "active_configio_words": ["1000", "1001"],
            "devices": [
                {
                    "canonical_name": "ESPB_PA3",
                    "device_type": "ESPB",
                    "critical": True,
                    "final_status": "UNSUPPORTED",
                    "ownership": "UNKNOWN",
                    "word": "1113",
                    "deterministic_code": "WORD_NOT_IN_ACTIVE_CONFIGIO",
                    "reason": "safety_like_name_without_supported_device_grammar",
                    "escalation_trace": {
                        "ai_api_called": False,
                        "why_ai_not_called": "not_yet_escalated",
                    },
                },
                {
                    "canonical_name": "ESSTOP1",
                    "device_type": "SAFETY",
                    "critical": True,
                    "final_status": "UNSUPPORTED",
                    "ownership": "UNKNOWN",
                    "word": "",
                    "deterministic_code": "OWNERSHIP_UNRESOLVED",
                    "reason": "safety_like_name_without_supported_device_grammar",
                    "escalation_trace": {
                        "ai_api_called": False,
                        "why_ai_not_called": "not_yet_escalated",
                    },
                },
            ],
        }
        # Force health down so we don't make live AI calls in unit test
        health = {
            "ai_api": {"available": False},
            "relay": {"available": False},
            "escalation_service_unavailable": True,
        }
        stats = run_prebuild_io_escalation(
            canon,
            machine="MSCRENOPICK",
            health=health,
        )
        self.assertEqual(stats.get("critical_items_bypassing_escalation"), 0, stats)
        for d in canon["devices"]:
            trace = d.get("escalation_trace") or {}
            self.assertTrue(
                trace.get("non_escalatable_reason"),
                f"{d['canonical_name']} missing NON_ESCALATABLE: {trace}",
            )
            self.assertEqual(trace.get("why_ai_not_called"), "NON_ESCALATABLE_POLICY")


if __name__ == "__main__":
    unittest.main()

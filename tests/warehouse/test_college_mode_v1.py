#!/usr/bin/env python3
"""College Mode V1 — dataset roles, holdout firewall, health snapshot shape."""
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from siteforge_warehouse.holdout import (  # noqa: E402
    HOLDOUT_FIREWALL_DOC,
    assert_no_holdout_in_learning_query,
    is_learning_eligible_role,
    learning_eligible_archive_filter,
    learning_eligible_archive_filter_sql,
)
from siteforge_warehouse.warehouse_health import (  # noqa: E402
    assign_dataset_role,
    warehouse_health_snapshot,
)


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


class TestAssignDatasetRole(unittest.TestCase):
    def test_deterministic(self) -> None:
        sha = _sha("college-mode-archive-a")
        a = assign_dataset_role(sha)
        b = assign_dataset_role(sha)
        self.assertEqual(a, b)
        self.assertIn(a, {"LEARNING", "VALIDATION", "HOLDOUT"})

    def test_override_wins(self) -> None:
        sha = _sha("override-me")
        self.assertEqual(assign_dataset_role(sha, override="HOLDOUT"), "HOLDOUT")
        self.assertEqual(assign_dataset_role(sha, override="validation"), "VALIDATION")

    def test_bucket_split_covers_all_roles(self) -> None:
        """Across many SHAs we should observe all three roles."""
        seen: set[str] = set()
        for i in range(500):
            seen.add(assign_dataset_role(_sha(f"split-{i}")))
            if seen == {"LEARNING", "VALIDATION", "HOLDOUT"}:
                break
        self.assertEqual(seen, {"LEARNING", "VALIDATION", "HOLDOUT"})

    def test_idempotent_same_sha(self) -> None:
        sha = _sha("idempotent-role")
        roles = {assign_dataset_role(sha) for _ in range(20)}
        self.assertEqual(len(roles), 1)


class TestHoldoutFirewall(unittest.TestCase):
    def test_sql_excludes_holdout(self) -> None:
        sql = learning_eligible_archive_filter_sql("dataset_role")
        self.assertIn("LEARNING", sql)
        self.assertIn("VALIDATION", sql)
        self.assertNotIn("HOLDOUT", sql)

    def test_python_filter_excludes_holdout(self) -> None:
        rows = [
            {"archive_sha256": "a", "dataset_role": "LEARNING"},
            {"archive_sha256": "b", "dataset_role": "HOLDOUT"},
            {"archive_sha256": "c", "dataset_role": "VALIDATION"},
            {"archive_sha256": "d", "dataset_role": "UNASSIGNED"},
        ]
        kept = learning_eligible_archive_filter(rows)
        self.assertEqual([r["archive_sha256"] for r in kept], ["a", "c"])
        assert_no_holdout_in_learning_query(kept)

    def test_assert_raises_on_holdout_leak(self) -> None:
        with self.assertRaises(AssertionError) as ctx:
            assert_no_holdout_in_learning_query(
                [{"archive_sha256": "x", "dataset_role": "HOLDOUT"}]
            )
        self.assertIn("HOLDOUT", str(ctx.exception))
        self.assertIn("rule discovery", HOLDOUT_FIREWALL_DOC)

    def test_eligibility_helpers(self) -> None:
        self.assertTrue(is_learning_eligible_role("LEARNING"))
        self.assertTrue(is_learning_eligible_role("VALIDATION"))
        self.assertFalse(is_learning_eligible_role("HOLDOUT"))
        self.assertFalse(is_learning_eligible_role("UNASSIGNED"))
        self.assertFalse(is_learning_eligible_role(None))


class TestWarehouseHealthSnapshot(unittest.TestCase):
    def test_snapshot_structure_live_or_mock(self) -> None:
        from siteforge_warehouse.config import is_postgres_configured

        if is_postgres_configured():
            snap = warehouse_health_snapshot()
            if snap.get("connection") == "CONNECTED":
                self.assertIn("counts", snap)
                self.assertIn("dataset_roles", snap)
                self.assertIn("archives_complete", snap)
                self.assertIn("database_size", snap)
                self.assertIn("current_site_leakage_checks", snap)
                return

        # Offline / disconnected: mock engine path shape via direct stub
        fake = {
            "generated_at": "t",
            "extractor_version": "warehouse_hw_io_v1.0.0",
            "postgres_configured": True,
            "connection": "CONNECTED",
            "counts": {"corpus.archives": 0},
            "archives_complete": 0,
            "archives_failed": 0,
            "controllers": 0,
            "projects": 0,
            "dataset_roles": {"UNASSIGNED": 0},
            "database_size": "0 bytes",
            "current_site_leakage_checks": {
                "pg_supplies_live_safety_devices": False,
            },
        }
        with mock.patch(
            "siteforge_warehouse.warehouse_health.warehouse_health_snapshot",
            return_value=fake,
        ):
            from siteforge_warehouse.warehouse_health import warehouse_health_snapshot as whs

            snap = whs()
        self.assertEqual(snap["connection"], "CONNECTED")
        self.assertIn("dataset_roles", snap)
        self.assertIn("counts", snap)


class TestCollegeScorecardOffline(unittest.TestCase):
    def test_scorecard_from_synthetic_coverage(self) -> None:
        from siteforge_warehouse.college_reports import compute_college_scorecard

        cov = {
            "generated_at": "t",
            "connection": "CONNECTED",
            "archives_complete": 71,
            "controllers": 62,
            "projects": 10,
            "dataset_roles": {
                "LEARNING": 55,
                "VALIDATION": 6,
                "HOLDOUT": 10,
                "UNASSIGNED": 0,
            },
            "counts": {
                "learning.rule_candidates": 6,
                "learning.field_tests": 3,
                "learning.unknown_clusters": 8,
                "learning.shadow_evaluations": 1,
            },
            "learning_eligible": {"archives": 61},
            "rule_candidates": {"total": 6, "by_status": {}},
            "unknown_clusters": {"total": 8},
        }
        card = compute_college_scorecard(
            cov,
            snapshot={"ai_total_recorded_cost_usd": 0.0, **cov},
        )
        self.assertIn(card["stage"], {"FRESHMAN", "SOPHOMORE", "JUNIOR", "SENIOR", "GRADUATE"})
        self.assertGreaterEqual(card["score"], 0)
        self.assertLessEqual(card["score"], 100)


if __name__ == "__main__":
    unittest.main()

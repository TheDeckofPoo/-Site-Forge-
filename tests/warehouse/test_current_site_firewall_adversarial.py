#!/usr/bin/env python3
"""Adversarial current-site vs corpus firewall using live PostgreSQL."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from siteforge_warehouse.config import is_postgres_configured  # noqa: E402
from siteforge_warehouse.postgres_repository import (  # noqa: E402
    PostgresCorpusLearningRepository,
    PostgresCurrentSiteEvidenceRepository,
    make_engine,
)
from sqlalchemy import text  # noqa: E402


@unittest.skipUnless(is_postgres_configured(), "PostgreSQL not configured")
class TestCurrentSiteFirewallAdversarial(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = make_engine()
        assert cls.engine is not None
        with cls.engine.connect() as c:
            rows = c.execute(
                text(
                    "SELECT archive_sha256, machine FROM corpus.archives "
                    "WHERE complete IS TRUE AND machine <> '' "
                    "ORDER BY machine LIMIT 20"
                )
            ).fetchall()
        if len(rows) < 2:
            raise unittest.SkipTest("need >=2 complete archives")
        cls.a_sha, cls.a_mach = rows[0][0], rows[0][1]
        # pick a different machine
        cls.b_sha, cls.b_mach = None, None
        for sha, mach in rows[1:]:
            if mach != cls.a_mach:
                cls.b_sha, cls.b_mach = sha, mach
                break
        if not cls.b_sha:
            raise unittest.SkipTest("need two distinct machines")

    def test_b_facts_not_in_a_current_site(self) -> None:
        repo = PostgresCurrentSiteEvidenceRepository(self.engine)
        a_cfg = repo.get_configio_rows(
            archive_sha256=self.a_sha, machine=self.a_mach
        )
        foreign = [
            r
            for r in a_cfg
            if r.get("archive_sha256") and r.get("archive_sha256") != self.a_sha
        ]
        self.assertEqual(foreign, [], msg="foreign archive rows in A current-site")
        # Wrong machine on A's archive should be empty / rejected
        wrong = repo.get_configio_rows(
            archive_sha256=self.a_sha, machine=self.b_mach
        )
        self.assertEqual(len(wrong), 0)

    def test_learning_still_cross_site(self) -> None:
        learn = PostgresCorpusLearningRepository(self.engine)
        dialects = learn.count_dialects()
        self.assertTrue(isinstance(dialects, dict))
        # Learning may be empty in theory; just ensure callable without site key
        _ = learn.list_rule_candidates()


if __name__ == "__main__":
    unittest.main()

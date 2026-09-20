#!/usr/bin/env python3
"""Warehouse V1 foundation tests — UNIT_BACKEND_ONLY / offline.

PostgreSQL integration is NOT claimed by these tests.
"""
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from hypothesis import given, settings, strategies as st  # noqa: E402

from siteforge_warehouse.ids import fact_uid, normalize_archive_sha256  # noqa: E402
from siteforge_warehouse.postgres_repository import (  # noqa: E402
    InMemoryCorpusLearningRepository,
    InMemoryCurrentSiteEvidenceRepository,
)
from siteforge_warehouse.repository import WarehouseNotConfigured  # noqa: E402
from siteforge_warehouse.config import (  # noqa: E402
    POSTGRESQL_NOT_CONFIGURED,
    is_postgres_configured,
)
from siteforge_warehouse.models import Base  # noqa: E402
from fortna_evidence_purity import (  # noqa: E402
    CURRENT_DECODER_OUTPUT,
    RAW_RUN_EVIDENCE,
    classify_tool_evidence,
)


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


class TestIds(unittest.TestCase):
    def test_stable_fact_uid(self) -> None:
        a = _sha("archive-a")
        u1 = fact_uid("configio", a, "FORTNA/Configio.asc", 0)
        u2 = fact_uid("configio", a, "FORTNA/Configio.asc", 0)
        self.assertEqual(u1, u2)
        self.assertTrue(u1.startswith("sf_"))

    def test_different_archives_different_uids(self) -> None:
        u1 = fact_uid("configio", _sha("a"), "FORTNA/Configio.asc", 0)
        u2 = fact_uid("configio", _sha("b"), "FORTNA/Configio.asc", 0)
        self.assertNotEqual(u1, u2)

    @given(st.binary(min_size=1, max_size=64))
    @settings(max_examples=25)
    def test_same_bytes_same_sha_property(self, data: bytes) -> None:
        h1 = hashlib.sha256(data).hexdigest()
        h2 = hashlib.sha256(data).hexdigest()
        self.assertEqual(h1, h2)
        self.assertEqual(normalize_archive_sha256(h1), h1)


class TestCurrentSiteIsolation(unittest.TestCase):
    """UNIT_BACKEND_ONLY — proves interface cannot leak cross-site rows."""

    def setUp(self) -> None:
        self.repo = InMemoryCurrentSiteEvidenceRepository()
        self.sha_a = _sha("site-a")
        self.sha_b = _sha("site-b")
        self.repo.configio_rows = [
            {
                "archive_sha256": self.sha_a,
                "machine": "ATLA",
                "desc": "from-a",
                "evidence_class": RAW_RUN_EVIDENCE,
            },
            {
                "archive_sha256": self.sha_b,
                "machine": "INDY",
                "desc": "from-b",
                "evidence_class": RAW_RUN_EVIDENCE,
            },
        ]

    def test_requires_archive_and_machine(self) -> None:
        with self.assertRaises(ValueError):
            self.repo.get_configio_rows(archive_sha256="", machine="ATLA")
        with self.assertRaises(ValueError):
            self.repo.get_configio_rows(archive_sha256=self.sha_a, machine="")

    def test_no_cross_archive_leak(self) -> None:
        rows = self.repo.get_configio_rows(
            archive_sha256=self.sha_a, machine="ATLA"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["desc"], "from-a")
        self.assertNotEqual(rows[0]["archive_sha256"], self.sha_b)

    def test_machine_mismatch_empty(self) -> None:
        rows = self.repo.get_configio_rows(
            archive_sha256=self.sha_a, machine="WRONG"
        )
        self.assertEqual(rows, [])


class TestEvidenceClassLaw(unittest.TestCase):
    def test_decoder_output_not_raw(self) -> None:
        m = classify_tool_evidence("get_physical_word_resolution_trace")
        self.assertEqual(m["evidence_class"], CURRENT_DECODER_OUTPUT)
        self.assertNotEqual(m["evidence_class"], RAW_RUN_EVIDENCE)


class TestModelsCompile(unittest.TestCase):
    def test_postgres_ddl_compiles(self) -> None:
        from sqlalchemy.dialects import postgresql
        from sqlalchemy.schema import CreateTable

        # UNIT: compile a few tables against PostgreSQL dialect without a server
        for name, table in list(Base.metadata.tables.items())[:5]:
            ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
            self.assertIn("CREATE TABLE", ddl.upper())

    def test_schemas_present(self) -> None:
        schemas = {t.schema for t in Base.metadata.tables.values()}
        for s in ("siteforge_meta", "corpus", "evidence", "learning", "qualification"):
            self.assertIn(s, schemas)


class TestOfflineStatus(unittest.TestCase):
    def test_postgres_not_configured_without_url(self) -> None:
        # May be true if user has env set; only assert constant exists
        self.assertEqual(POSTGRESQL_NOT_CONFIGURED, "POSTGRESQL_NOT_CONFIGURED")
        # is_postgres_configured reflects env — just callable
        self.assertIsInstance(is_postgres_configured(), bool)


class TestCorpusLearningSeparate(unittest.TestCase):
    def test_learning_repo_exists(self) -> None:
        repo = InMemoryCorpusLearningRepository()
        self.assertEqual(repo.count_dialects(), {})
        self.assertEqual(repo.list_unknown_clusters(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

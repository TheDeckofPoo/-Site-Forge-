#!/usr/bin/env python3
"""LIVE PostgreSQL integration gate tests.

Skip entirely when SITEFORGE_DATABASE_URL / local_database_url.txt is absent.
"""
from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from siteforge_warehouse.config import is_postgres_configured  # noqa: E402
from siteforge_warehouse.extract import build_bundle_from_run_dir  # noqa: E402
from siteforge_warehouse.ids import fact_uid  # noqa: E402
from siteforge_warehouse.postgres_repository import (  # noqa: E402
    PostgresCorpusLearningRepository,
    PostgresCurrentSiteEvidenceRepository,
    make_engine,
)
from siteforge_warehouse.writer import PostgresWarehouseWriter  # noqa: E402
from siteforge_warehouse import EXTRACTOR_VERSION, seed_cp8_candidate_status  # noqa: E402
from sqlalchemy import text  # noqa: E402


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


@unittest.skipUnless(is_postgres_configured(), "PostgreSQL not configured")
class TestLivePostgresGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = make_engine()
        assert cls.engine is not None
        cls.writer = PostgresWarehouseWriter(cls.engine)
        cls.writer.ensure_extractor_version()
        # Minimal synthetic RUN fixture
        cls.fix = Path(tempfile.mkdtemp(prefix="sf_wh_fix_"))
        run = cls.fix / "RUN"
        (run / "FORTNA").mkdir(parents=True)
        (run / "PROJECT").mkdir(parents=True)
        (run / "project.cfg").write_text(
            "MACHINENAME=ATLA\nPROJECTNAME=TESTSITE\n", encoding="utf-8"
        )
        # Minimal Configio ASC (tilde format used by fortna_asc)
        cfg = run / "FORTNA" / "Configio.asc"
        # Write a tiny valid-ish ASC if possible; otherwise empty extract is ok
        cfg.write_text(
            "Octal_Word~Bank~LoHi~Desc~In_Out~Interface~I_O_Type\n"
            "700~4~Low~1794-IA16-5~0000000011111111~RTA~Digital\n"
            "700~5~High~1794-IA16-6~1111111100000000~RTA~Digital\n",
            encoding="utf-8",
        )
        cls.fixture_sha = _sha("warehouse-live-fixture-v1")
        cls.bundle = build_bundle_from_run_dir(
            run,
            archive_sha256=cls.fixture_sha,
            filename="fixture-ATLA.tar.gz",
            discovered_path=str(run),
        )
        # Force machine/project if extract missed cfg parse
        if not cls.bundle.machine:
            cls.bundle.machine = "ATLA"
            cls.bundle.project = "TESTSITE"
            cls.bundle.archive.machine = "ATLA"
            cls.bundle.archive.project = "TESTSITE"

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.fix, ignore_errors=True)

    def test_01_ingest_fixture(self) -> None:
        r = self.writer.ingest_bundle(self.bundle, force=True)
        self.assertIn(r["status"], {"INGESTED", "REEXTRACTED"})
        repo = PostgresCurrentSiteEvidenceRepository(self.engine)
        rows = repo.get_configio_rows(
            archive_sha256=self.fixture_sha, machine="ATLA"
        )
        self.assertGreaterEqual(len(rows), 1)

    def test_02_idempotent_unchanged(self) -> None:
        r = self.writer.ingest_bundle(self.bundle, force=False)
        self.assertEqual(r["status"], "UNCHANGED")

    def test_03_force_reingest(self) -> None:
        before = self.bundle.configio_rows[0]["fact_uid"]
        r = self.writer.ingest_bundle(self.bundle, force=True)
        self.assertEqual(r["status"], "REEXTRACTED")
        # Same bundle bytes => same fact_uid identity (stable across reingest)
        self.assertEqual(self.bundle.configio_rows[0]["fact_uid"], before)
        repo = PostgresCurrentSiteEvidenceRepository(self.engine)
        rows = repo.get_configio_rows(
            archive_sha256=self.fixture_sha, machine="ATLA"
        )
        uids = {row["fact_uid"] for row in rows}
        self.assertIn(before, uids)

    def test_04_rollback_no_partial_complete(self) -> None:
        from siteforge_warehouse.staging import ArchiveEvidenceBundle, ArchiveMeta

        bad_sha = _sha("warehouse-live-fail-inject")
        cfg_rows = []
        for row in self.bundle.configio_rows:
            r = dict(row)
            r["archive_sha256"] = bad_sha
            r["fact_uid"] = fact_uid(
                "configio",
                bad_sha,
                r.get("source_path") or "FORTNA/Configio.asc",
                r.get("source_row_index") or 0,
            )
            cfg_rows.append(r)
        b2 = ArchiveEvidenceBundle(
            archive=ArchiveMeta(
                archive_sha256=bad_sha,
                filename="fail.tgz",
                archive_class="RUN",
                discovered_path=self.bundle.archive.discovered_path,
                project="TESTSITE",
                site="TESTSITE",
                machine="ATLA",
            ),
            project="TESTSITE",
            machine="ATLA",
            source_files=[],
            configio_rows=cfg_rows,
            extractor_version=EXTRACTOR_VERSION,
        )
        r = self.writer.ingest_bundle(b2, force=True, fail_after="after_configio")
        self.assertEqual(r["status"], "FAILED")
        with self.engine.connect() as conn:
            complete = conn.execute(
                text(
                    "SELECT complete, sync_status FROM corpus.archives WHERE archive_sha256=:s"
                ),
                {"s": bad_sha},
            ).first()
            self.assertIsNotNone(complete)
            self.assertFalse(bool(complete[0]))
            self.assertEqual(complete[1], "FAILED")
            n = conn.execute(
                text(
                    "SELECT COUNT(*) FROM evidence.configio_rows WHERE archive_sha256=:s"
                ),
                {"s": bad_sha},
            ).scalar()
            self.assertEqual(int(n or 0), 0)

    def test_05_current_site_isolation(self) -> None:
        sha_a = self.fixture_sha
        sha_b = _sha("warehouse-live-indy")
        # ingest B lightly
        from siteforge_warehouse.staging import ArchiveEvidenceBundle, ArchiveMeta

        b = ArchiveEvidenceBundle(
            archive=ArchiveMeta(
                archive_sha256=sha_b,
                filename="indy.tgz",
                archive_class="RUN",
                project="INDYSITE",
                machine="INDY",
            ),
            project="INDYSITE",
            machine="INDY",
            source_files=[],
            configio_rows=[
                {
                    "fact_uid": fact_uid("configio", sha_b, "FORTNA/Configio.asc", 0),
                    "archive_sha256": sha_b,
                    "project": "INDYSITE",
                    "machine": "INDY",
                    "source_path": "FORTNA/Configio.asc",
                    "source_row_index": 0,
                    "machine_scope": "ACTIVE_MACHINE_SOURCE",
                    "evidence_class": "RAW_RUN_EVIDENCE",
                    "extractor_version": EXTRACTOR_VERSION,
                    "octal_word": "100",
                    "bank": "1",
                    "lohi": "Low",
                    "in_out": "",
                    "desc": "from-indy",
                    "interface": "RTA",
                    "i_o_type": "Digital",
                    "status": "",
                    "process": "",
                    "purpose": "PHYSICAL_IO_CANDIDATE",
                    "purpose_meta": {},
                    "dialect_form": "UNKNOWN",
                    "dialect_meta": {},
                    "raw_fields": {},
                }
            ],
            extractor_version=EXTRACTOR_VERSION,
        )
        self.writer.ingest_bundle(b, force=True)
        repo = PostgresCurrentSiteEvidenceRepository(self.engine)
        a_rows = repo.get_configio_rows(archive_sha256=sha_a, machine="ATLA")
        for row in a_rows:
            self.assertNotEqual(row.get("archive_sha256"), sha_b)
            self.assertNotEqual(row.get("machine"), "INDY")
        with self.assertRaises(ValueError):
            repo.get_configio_rows(archive_sha256=sha_a, machine="")
        with self.assertRaises(ValueError):
            repo.get_configio_rows(archive_sha256="", machine="ATLA")

    def test_06_corpus_learning_and_rule_seed(self) -> None:
        self.writer.seed_rule_candidate(
            {
                **seed_cp8_candidate_status(),
                "rule_id": "exact_adapter_ip_bridge",
                "title": "Exact EIPAdapters TargetIP bridge",
                "status": "PRODUCTION_RULE",
                "summary": "EIPModules.Adapter==EIPAdapters.Name then TargetIP==eipcfg.targetip",
                "implementation_commit": "68a4fed",
                "honesty_notes": ["METHOD not site answer"],
            }
        )
        self.writer.seed_rule_candidate(seed_cp8_candidate_status())
        learn = PostgresCorpusLearningRepository(self.engine)
        rules = learn.list_rule_candidates()
        ids = {r.get("rule_id") for r in rules}
        self.assertIn("exact_adapter_ip_bridge", ids)
        dialects = learn.count_dialects()
        self.assertIsInstance(dialects, dict)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Freeze Reality Check V1 baseline — no decoder changes."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from siteforge_warehouse import EXTRACTOR_VERSION  # noqa: E402
from siteforge_warehouse.config import is_postgres_configured  # noqa: E402
from siteforge_warehouse.postgres_repository import (  # noqa: E402
    PostgresCorpusLearningRepository,
    make_engine,
)
from sqlalchemy import text  # noqa: E402


def git_sha() -> str:
    return (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
        .decode()
        .strip()
    )


def main() -> int:
    out_root = ROOT / "exports" / "demo" / "siteforge-reality-check-v1"
    out_root.mkdir(parents=True, exist_ok=True)

    sha = git_sha()
    payload: dict = {
        "kind": "siteforge_reality_check_v1_baseline",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": sha,
        "expected_baseline_sha": "25b0752d5c364e04b7cd3ee2b0e34a96524a6d24",
        "sha_matches_task_baseline": sha.startswith("25b0752"),
        "extractor_version": EXTRACTOR_VERSION,
        "postgres_configured": is_postgres_configured(),
        "measurement_policy": {
            "do_not_change_production_decoding": True,
            "instrumentation_allowed": True,
            "do_not_fix_while_measuring": True,
        },
        "production_rules": [],
        "candidate_rules": [],
        "db": {},
    }

    if is_postgres_configured():
        eng = make_engine()
        assert eng is not None
        with eng.connect() as c:
            payload["db"] = {
                "alembic_revision": c.execute(
                    text("SELECT version_num FROM siteforge_meta.alembic_version")
                ).scalar(),
                "postgresql_version": c.execute(text("SHOW server_version")).scalar(),
                "archive_count": int(
                    c.execute(text("SELECT COUNT(*) FROM corpus.archives")).scalar()
                    or 0
                ),
                "archives_complete": int(
                    c.execute(
                        text(
                            "SELECT COUNT(*) FROM corpus.archives WHERE complete IS TRUE"
                        )
                    ).scalar()
                    or 0
                ),
                "controller_count": int(
                    c.execute(text("SELECT COUNT(*) FROM corpus.controllers")).scalar()
                    or 0
                ),
            }
        learn = PostgresCorpusLearningRepository(eng)
        for r in learn.list_rule_candidates():
            entry = {
                "rule_id": r.get("rule_id") or r.get("rule_key"),
                "status": r.get("status"),
                "title": r.get("title"),
            }
            if str(entry["status"] or "").upper() == "PRODUCTION_RULE":
                payload["production_rules"].append(entry)
            else:
                payload["candidate_rules"].append(entry)

    path = out_root / "baseline_manifest.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(path), "git_sha": sha}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

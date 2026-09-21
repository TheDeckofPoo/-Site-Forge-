#!/usr/bin/env python3
"""PostgreSQL warehouse health + College Mode scorecard (no secrets)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

from . import EXTRACTOR_VERSION
from .config import get_database_url, is_postgres_configured, resolve_corpus_roots
from .postgres_repository import make_engine

REPO = Path(__file__).resolve().parents[2]

DATASET_ROLES = ("LEARNING", "VALIDATION", "HOLDOUT")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def warehouse_health_snapshot() -> dict[str, Any]:
    out: dict[str, Any] = {
        "generated_at": _utcnow(),
        "extractor_version": EXTRACTOR_VERSION,
        "postgres_configured": is_postgres_configured(),
        "connection": "DISCONNECTED",
        "corpus_roots": [str(p) for p in resolve_corpus_roots()],
    }
    if not is_postgres_configured():
        out["error"] = "POSTGRESQL_NOT_CONFIGURED"
        return out
    eng = make_engine()
    if eng is None:
        out["error"] = "engine_null"
        return out
    with eng.connect() as c:
        out["connection"] = "CONNECTED"
        out["server_version"] = c.execute(text("SHOW server_version")).scalar()
        out["database_name"] = c.execute(text("SELECT current_database()")).scalar()
        out["database_size"] = c.execute(
            text("SELECT pg_size_pretty(pg_database_size(current_database()))")
        ).scalar()
        out["database_size_bytes"] = int(
            c.execute(text("SELECT pg_database_size(current_database())")).scalar() or 0
        )
        try:
            out["alembic_revision"] = c.execute(
                text("SELECT version_num FROM siteforge_meta.alembic_version")
            ).scalar()
        except Exception:
            c.rollback()
            out["alembic_revision"] = None

        counts: dict[str, Any] = {}
        for schema, table in [
            ("corpus", "archives"),
            ("corpus", "controllers"),
            ("corpus", "projects"),
            ("corpus", "source_files"),
            ("evidence", "configio_rows"),
            ("evidence", "io_claims"),
            ("evidence", "eipmodules"),
            ("evidence", "eipcfg_modules"),
            ("evidence", "adapter_bridges"),
            ("learning", "field_tests"),
            ("learning", "failure_events"),
            ("learning", "structural_signatures"),
            ("learning", "unknown_clusters"),
            ("learning", "rule_candidates"),
            ("learning", "shadow_evaluations"),
            ("learning", "ai_investigations"),
            ("learning", "investigation_sessions"),
        ]:
            try:
                counts[f"{schema}.{table}"] = int(
                    c.execute(text(f'SELECT COUNT(*) FROM "{schema}"."{table}"')).scalar()
                    or 0
                )
            except Exception:
                c.rollback()
                counts[f"{schema}.{table}"] = None
        out["counts"] = counts

        out["archives_complete"] = int(
            c.execute(
                text("SELECT COUNT(*) FROM corpus.archives WHERE complete IS TRUE")
            ).scalar()
            or 0
        )
        out["archives_failed"] = int(
            c.execute(
                text(
                    "SELECT COUNT(*) FROM corpus.archives WHERE sync_status = 'FAILED'"
                )
            ).scalar()
            or 0
        )
        out["controllers"] = int(
            c.execute(
                text("SELECT COUNT(DISTINCT machine) FROM corpus.archives WHERE machine <> ''")
            ).scalar()
            or 0
        )
        out["projects"] = int(
            c.execute(
                text("SELECT COUNT(DISTINCT project) FROM corpus.archives WHERE project <> ''")
            ).scalar()
            or 0
        )

        # Largest tables
        try:
            largest = c.execute(
                text(
                    """
                    SELECT n.nspname AS schema,
                           c.relname AS table,
                           c.reltuples::bigint AS est_rows,
                           pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
                           pg_total_relation_size(c.oid) AS total_bytes,
                           pg_size_pretty(pg_relation_size(c.oid)) AS data_size,
                           pg_size_pretty(pg_indexes_size(c.oid)) AS index_size
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relkind = 'r'
                      AND n.nspname IN ('corpus','evidence','learning','qualification','siteforge_meta')
                    ORDER BY pg_total_relation_size(c.oid) DESC
                    LIMIT 25
                    """
                )
            ).mappings().all()
            out["largest_tables"] = [dict(r) for r in largest]
        except Exception as exc:
            c.rollback()
            out["largest_tables_error"] = str(exc)

        # Dataset roles if column exists
        try:
            roles = c.execute(
                text(
                    """
                    SELECT COALESCE(dataset_role, 'UNASSIGNED') AS role, COUNT(*) AS n
                    FROM corpus.archives
                    GROUP BY 1 ORDER BY 2 DESC
                    """
                )
            ).mappings().all()
            out["dataset_roles"] = {r["role"]: int(r["n"]) for r in roles}
        except Exception:
            c.rollback()
            out["dataset_roles"] = {"UNASSIGNED": out.get("archives_complete")}

        # Recent
        try:
            out["last_archive_ingested"] = c.execute(
                text(
                    "SELECT filename, machine, project, ingested_at "
                    "FROM corpus.archives WHERE complete IS TRUE "
                    "ORDER BY ingested_at DESC NULLS LAST LIMIT 1"
                )
            ).mappings().first()
            if out["last_archive_ingested"]:
                out["last_archive_ingested"] = dict(out["last_archive_ingested"])
        except Exception:
            c.rollback()
            out["last_archive_ingested"] = None

        try:
            out["last_field_test"] = c.execute(
                text(
                    "SELECT field_test_id, machine, git_sha, timestamp, build_status "
                    "FROM learning.field_tests ORDER BY timestamp DESC NULLS LAST LIMIT 1"
                )
            ).mappings().first()
            if out["last_field_test"]:
                out["last_field_test"] = dict(out["last_field_test"])
        except Exception:
            c.rollback()
            out["last_field_test"] = None

        try:
            ai_cost = c.execute(
                text(
                    "SELECT COALESCE(SUM(estimated_cost_usd),0) FROM learning.ai_investigations"
                )
            ).scalar()
            out["ai_total_recorded_cost_usd"] = float(ai_cost or 0)
        except Exception:
            c.rollback()
            out["ai_total_recorded_cost_usd"] = 0.0

        # Current-site leakage check: no live hydrate from PG (contract)
        out["current_site_leakage_checks"] = {
            "pg_supplies_live_safety_devices": False,
            "pg_supplies_live_io_assignments": False,
            "pg_supplies_live_transport": False,
            "note": "Live site state must come from active archive+machine only",
        }
    return out


def assign_dataset_role(archive_sha: str, *, override: str | None = None) -> str:
    """Deterministic LEARNING/VALIDATION/HOLDOUT from SHA (~82/8/10 split).

    Override (HOLDOUT/LEARNING/VALIDATION) wins for explicit virgin reservations.
    """
    if override and override.upper() in DATASET_ROLES:
        return override.upper()
    digest = (archive_sha or "").strip().lower()
    if len(digest) < 2:
        return "LEARNING"
    # Use last byte for stable bucket 0-255
    try:
        bucket = int(digest[-2:], 16)
    except ValueError:
        bucket = 0
    # ~15% holdout (0-37), ~8% validation (38-57), rest learning
    if bucket < 38:
        return "HOLDOUT"
    if bucket < 58:
        return "VALIDATION"
    return "LEARNING"


def write_health_reports(snapshot: dict[str, Any] | None = None) -> dict[str, Path]:
    snap = snapshot or warehouse_health_snapshot()
    research = REPO / "exports" / "research"
    research.mkdir(parents=True, exist_ok=True)
    jp = research / "postgresql_warehouse_health.json"
    mp = research / "POSTGRESQL_WAREHOUSE_HEALTH.md"
    jp.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
    lines = [
        "# PostgreSQL Warehouse Health",
        "",
        f"Generated: {snap.get('generated_at')}",
        "",
        f"- Connection: **{snap.get('connection')}**",
        f"- Server: {snap.get('server_version')}",
        f"- Database: `{snap.get('database_name')}`",
        f"- Size: **{snap.get('database_size')}**",
        f"- Alembic: `{snap.get('alembic_revision')}`",
        f"- Archives complete: {snap.get('archives_complete')} (failed {snap.get('archives_failed')})",
        f"- Controllers: {snap.get('controllers')} · Projects: {snap.get('projects')}",
        f"- AI recorded cost: ${snap.get('ai_total_recorded_cost_usd', 0):.2f}",
        "",
        "## Counts",
        "",
    ]
    for k, v in (snap.get("counts") or {}).items():
        lines.append(f"- `{k}`: {v}")
    lines += ["", "## Largest tables", "", "| schema | table | est_rows | total | data | index |", "| --- | --- | ---: | --- | --- | --- |"]
    for t in snap.get("largest_tables") or []:
        lines.append(
            f"| {t.get('schema')} | {t.get('table')} | {t.get('est_rows')} | "
            f"{t.get('total_size')} | {t.get('data_size')} | {t.get('index_size')} |"
        )
    lines += ["", "## Dataset roles", ""]
    for k, v in (snap.get("dataset_roles") or {}).items():
        lines.append(f"- {k}: {v}")
    mp.write_text("\n".join(lines), encoding="utf-8")
    return {"json": jp, "md": mp}

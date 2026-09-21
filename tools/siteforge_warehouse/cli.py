"""CLI: python -m tools.siteforge_warehouse.cli"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import EXTRACTOR_VERSION, seed_cp8_candidate_status
from .config import (
    POSTGRESQL_NOT_CONFIGURED,
    get_database_url,
    is_postgres_configured,
    resolve_corpus_roots,
)
from .parquet_export import export_staging_to_parquet
from .sync import dry_run_sync


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True, default=str))


def _url_hint(url: str) -> str:
    """Strip password from URL for display."""
    try:
        if "://" not in url:
            return "set"
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            creds, hostpart = rest.rsplit("@", 1)
            user = creds.split(":", 1)[0]
            return f"{scheme}://{user}:***@{hostpart}"
        return f"{scheme}://{rest}"
    except Exception:
        return "set"


def cmd_status(_: argparse.Namespace) -> int:
    url = get_database_url()
    roots = resolve_corpus_roots()
    payload: dict[str, Any] = {
        "extractor_version": EXTRACTOR_VERSION,
        "postgres_configured": is_postgres_configured(),
        "database_url_set": bool(url),
        "database_status": "configured" if url else POSTGRESQL_NOT_CONFIGURED,
        "database_url_hint": _url_hint(url) if url else None,
        "corpus_roots": [str(p) for p in roots],
        "cp8_seed": seed_cp8_candidate_status(),
    }
    if is_postgres_configured():
        try:
            from sqlalchemy import text

            from .postgres_repository import (
                PostgresCorpusLearningRepository,
                make_engine,
            )

            eng = make_engine()
            assert eng is not None
            with eng.connect() as conn:
                ver = conn.execute(text("SHOW server_version")).scalar()
                payload["postgresql_version"] = ver
                # Alembic version table lives in siteforge_meta (see alembic/env.py).
                # Must rollback on miss so later counts are not aborted.
                try:
                    rev = conn.execute(
                        text(
                            "SELECT version_num FROM siteforge_meta.alembic_version"
                        )
                    ).scalar()
                    payload["alembic_revision"] = rev
                except Exception:
                    conn.rollback()
                    payload["alembic_revision"] = None
                counts = {}
                for schema, table in [
                    ("corpus", "archives"),
                    ("corpus", "projects"),
                    ("corpus", "controllers"),
                    ("corpus", "source_files"),
                    ("evidence", "configio_rows"),
                    ("evidence", "io_claims"),
                    ("evidence", "eipmodules"),
                    ("evidence", "eipcfg_modules"),
                    ("evidence", "eipmodule_types"),
                    ("evidence", "adapter_bridges"),
                    ("evidence", "conflicts"),
                    ("evidence", "machine_source_scopes"),
                    ("learning", "dialect_observations"),
                    ("learning", "rule_candidates"),
                    ("learning", "unknown_clusters"),
                    ("learning", "rule_coverage"),
                    ("qualification", "qualification_runs"),
                ]:
                    try:
                        n = conn.execute(
                            text(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
                        ).scalar()
                        counts[f"{schema}.{table}"] = int(n or 0)
                    except Exception:
                        conn.rollback()
                        counts[f"{schema}.{table}"] = None
                payload["counts"] = counts
                try:
                    complete = conn.execute(
                        text(
                            "SELECT COUNT(*) FROM corpus.archives WHERE complete IS TRUE"
                        )
                    ).scalar()
                    failed = conn.execute(
                        text(
                            "SELECT COUNT(*) FROM corpus.archives "
                            "WHERE sync_status = 'FAILED'"
                        )
                    ).scalar()
                    payload["archives_complete"] = int(complete or 0)
                    payload["archives_failed"] = int(failed or 0)
                except Exception:
                    conn.rollback()
                try:
                    size = conn.execute(
                        text(
                            "SELECT pg_size_pretty("
                            "pg_database_size(current_database()))"
                        )
                    ).scalar()
                    payload["database_size"] = size
                except Exception:
                    conn.rollback()
                try:
                    last_sync = conn.execute(
                        text(
                            "SELECT MAX(ingested_at) FROM corpus.archives "
                            "WHERE complete IS TRUE"
                        )
                    ).scalar()
                    payload["last_sync_time"] = last_sync
                except Exception:
                    conn.rollback()
                    payload["last_sync_time"] = None
            learn = PostgresCorpusLearningRepository(eng)
            payload["dialect_counts"] = learn.count_dialects()
            payload["hardware_catalog_counts_sample"] = dict(
                list(learn.hardware_catalog_counts().items())[:20]
            )
            payload["rule_candidates"] = [
                {k: r.get(k) for k in ("rule_id", "status", "title")}
                for r in learn.list_rule_candidates()
            ]
        except Exception as exc:
            payload["live_status_error"] = str(exc)
    _print_json(payload)
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    roots = [Path(r) for r in (args.roots or [])] or None
    dry = bool(args.dry_run)

    if not is_postgres_configured():
        if not dry:
            print(
                f"NOTE: {POSTGRESQL_NOT_CONFIGURED} — running dry-run only.",
                file=sys.stderr,
            )
        dry = True

    if dry:
        known = None
        if is_postgres_configured():
            try:
                from .writer import PostgresWarehouseWriter

                known = PostgresWarehouseWriter().known_complete_shas()
            except Exception:
                known = None
        summary = dry_run_sync(
            roots,
            known_complete_shas=known,
            force=bool(args.force),
            build_bundles=True,
        )
        out = {k: v for k, v in summary.items() if k != "bundles"}
        out["dry_run"] = True
        _print_json(out)
        return 0 if not summary.get("staging_errors") else 1

    # LIVE ingest
    from .writer import live_sync

    summary = live_sync(roots, force=bool(args.force), dry_run=False)
    # Drop per-archive noise if huge — keep status_counts + sample failures
    out = {
        "dry_run": False,
        "extractor_version": summary.get("extractor_version"),
        "discovered_count": summary.get("discovered_count"),
        "status_counts": summary.get("status_counts"),
        "staging_counts": summary.get("staging_counts"),
        "sync_run_id": summary.get("sync_run_id"),
        "failed": [
            r
            for r in (summary.get("results") or [])
            if r.get("status") == "FAILED"
        ][:50],
        "ingested_sample": [
            r
            for r in (summary.get("results") or [])
            if r.get("status") in {"INGESTED", "REEXTRACTED", "UNCHANGED"}
        ][:20],
    }
    _print_json(out)
    fails = (summary.get("status_counts") or {}).get("FAILED", 0)
    return 0 if fails == 0 else 1


def cmd_export_parquet(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    if is_postgres_configured() and not args.staging_only:
        # Live export from PG
        from sqlalchemy import text

        import pandas as pd

        from .postgres_repository import make_engine

        eng = make_engine()
        assert eng is not None
        out_dir.mkdir(parents=True, exist_ok=True)
        tables = {
            "archives": 'SELECT * FROM corpus.archives',
            "controllers": 'SELECT * FROM corpus.controllers',
            "configio": 'SELECT * FROM evidence.configio_rows',
            "eipmodules": 'SELECT * FROM evidence.eipmodules',
            "io_claims": 'SELECT * FROM evidence.io_claims',
            "dialect_observations": 'SELECT * FROM learning.dialect_observations',
            "rule_coverage": 'SELECT * FROM learning.rule_coverage',
            "unknown_clusters": 'SELECT * FROM learning.unknown_clusters',
        }
        written = []
        with eng.connect() as conn:
            for name, sql in tables.items():
                try:
                    df = pd.read_sql(text(sql), conn)
                    # Empty JSON/struct columns break pyarrow; stringify object cols
                    for col in df.columns:
                        if df[col].dtype == object:
                            df[col] = df[col].apply(
                                lambda v: None
                                if v is None
                                else (
                                    v
                                    if isinstance(v, (str, int, float, bool))
                                    else str(v)
                                )
                            )
                    path = out_dir / f"{name}.parquet"
                    df.to_parquet(path, index=False)
                    written.append({"table": name, "rows": len(df), "path": str(path)})
                except Exception as exc:
                    written.append({"table": name, "error": str(exc)})
        _print_json({"source": "postgresql", "exports": written})
        return 0

    roots = [Path(r) for r in (args.roots or [])]
    summary = dry_run_sync(roots or None, build_bundles=True)
    result = export_staging_to_parquet(summary, out_dir)
    out = {
        "export": result,
        "plan_status_counts": summary.get("status_counts"),
        "staging_counts": summary.get("staging_counts"),
        "staging_errors": summary.get("staging_errors"),
        "postgres": "staging_export",
    }
    _print_json(out)
    return 0 if not summary.get("staging_errors") else 1


def cmd_health(_: argparse.Namespace) -> int:
    """Warehouse health snapshot + research report write (incl. college coverage).

    Prints a GUI-safe payload (no passwords / DB URL credentials / secrets).
    """
    from .college_reports import write_college_reports
    from .warehouse_health import warehouse_health_snapshot, write_health_reports

    snap = warehouse_health_snapshot()
    health_paths = write_health_reports(snap)
    college = write_college_reports(snapshot=snap)
    # Engineer-facing fields only — never include connection strings or secrets.
    safe_snap = {
        "generated_at": snap.get("generated_at"),
        "connection": snap.get("connection"),
        "server_version": snap.get("server_version"),
        "database_name": snap.get("database_name"),
        "database_size": snap.get("database_size"),
        "database_size_bytes": snap.get("database_size_bytes"),
        "alembic_revision": snap.get("alembic_revision"),
        "archives_complete": snap.get("archives_complete"),
        "archives_failed": snap.get("archives_failed"),
        "controllers": snap.get("controllers"),
        "projects": snap.get("projects"),
        "dataset_roles": snap.get("dataset_roles"),
        "counts": snap.get("counts"),
        "largest_tables": snap.get("largest_tables"),
        "last_archive_ingested": snap.get("last_archive_ingested"),
        "last_field_test": snap.get("last_field_test"),
        "ai_total_recorded_cost_usd": snap.get("ai_total_recorded_cost_usd"),
        "current_site_leakage_checks": snap.get("current_site_leakage_checks"),
        "corpus_roots": snap.get("corpus_roots"),
        "extractor_version": snap.get("extractor_version"),
        "postgres_configured": snap.get("postgres_configured"),
    }
    out = {
        "snapshot": safe_snap,
        "health_reports": {k: str(v) for k, v in health_paths.items()},
        "college_reports": {
            k: str(v) for k, v in (college.get("paths") or {}).items()
        },
        "college_stage": (college.get("college") or {}).get("stage"),
        "college_score": (college.get("college") or {}).get("score"),
        "college_gates": (college.get("college") or {}).get("gates"),
    }
    if snap.get("error"):
        out["error"] = snap["error"]
        _print_json(out)
        return 2
    _print_json(out)
    return 0


def cmd_assign_roles(args: argparse.Namespace) -> int:
    """Assign LEARNING/VALIDATION/HOLDOUT roles (default: UNASSIGNED only)."""
    from .college_reports import apply_dataset_roles

    fill_only = not bool(args.reassign_all)
    result = apply_dataset_roles(fill_unassigned_only=fill_only)
    _print_json(result)
    if result.get("error"):
        return 2
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    if not is_postgres_configured():
        _print_json({"error": POSTGRESQL_NOT_CONFIGURED})
        return 2
    from sqlalchemy import text

    from .postgres_repository import (
        PostgresCorpusLearningRepository,
        PostgresCurrentSiteEvidenceRepository,
        make_engine,
    )

    eng = make_engine()
    assert eng is not None
    kind = args.kind
    key = args.key
    out: dict[str, Any] = {"kind": kind, "key": key}

    if kind == "archive":
        sha = key.strip().lower()
        with eng.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM corpus.archives WHERE archive_sha256 = :s"),
                {"s": sha},
            ).mappings().first()
            out["archive"] = dict(row) if row else None
            if row:
                counts = {}
                for table in (
                    "configio_rows",
                    "eipmodules",
                    "io_claims",
                    "source_files",
                    "conflicts",
                    "machine_source_scopes",
                ):
                    schema = "corpus" if table == "source_files" else "evidence"
                    n = conn.execute(
                        text(
                            f'SELECT COUNT(*) FROM "{schema}"."{table}" WHERE archive_sha256 = :s'
                        ),
                        {"s": sha},
                    ).scalar()
                    counts[table] = int(n or 0)
                out["counts"] = counts
                scopes = conn.execute(
                    text(
                        "SELECT machine_scope, COUNT(*) FROM evidence.machine_source_scopes "
                        "WHERE archive_sha256 = :s GROUP BY machine_scope"
                    ),
                    {"s": sha},
                ).all()
                out["scope_counts"] = {r[0]: int(r[1]) for r in scopes}
    elif kind == "machine":
        mach = key.strip()
        repo = PostgresCurrentSiteEvidenceRepository(eng)
        # Need archive — list archives for machine
        with eng.connect() as conn:
            arches = conn.execute(
                text(
                    "SELECT archive_sha256, project, complete, sync_status "
                    "FROM corpus.archives WHERE machine = :m"
                ),
                {"m": mach},
            ).mappings().all()
            out["archives"] = [dict(a) for a in arches]
            if arches:
                sha = arches[0]["archive_sha256"]
                out["sample_configio"] = len(
                    repo.get_configio_rows(archive_sha256=sha, machine=mach)
                )
    elif kind == "rule":
        learn = PostgresCorpusLearningRepository(eng)
        rules = [r for r in learn.list_rule_candidates() if r.get("rule_id") == key]
        out["rules"] = rules
    else:
        out["error"] = "unknown inspect kind"
        _print_json(out)
        return 2
    _print_json(out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m tools.siteforge_warehouse.cli",
        description="Site Forge PostgreSQL warehouse CLI",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="Discover + sync (live when DB configured)")
    p_sync.add_argument("--roots", nargs="*", default=[])
    p_sync.add_argument("--dry-run", action="store_true")
    p_sync.add_argument("--force", action="store_true")
    p_sync.set_defaults(func=cmd_sync)

    p_status = sub.add_parser("status", help="Show warehouse status")
    p_status.set_defaults(func=cmd_status)

    p_health = sub.add_parser(
        "health",
        help="Warehouse health snapshot + write exports/research reports",
    )
    p_health.set_defaults(func=cmd_health)

    p_roles = sub.add_parser(
        "assign-roles",
        help="Assign dataset_role (default: fill UNASSIGNED only)",
    )
    p_roles.add_argument(
        "--reassign-all",
        action="store_true",
        help="Recompute roles for all archives (ignores prior non-UNASSIGNED)",
    )
    p_roles.set_defaults(func=cmd_assign_roles)

    p_exp = sub.add_parser("export-parquet", help="Export Parquet snapshots")
    p_exp.add_argument("--out", default="exports/learning/parquet")
    p_exp.add_argument("--roots", nargs="*", default=[])
    p_exp.add_argument(
        "--staging-only",
        action="store_true",
        help="Force staging dry-run export even if PostgreSQL configured",
    )
    p_exp.set_defaults(func=cmd_export_parquet)

    p_ins = sub.add_parser("inspect", help="Read-only engineering inspection")
    p_ins.add_argument("kind", choices=["archive", "machine", "rule"])
    p_ins.add_argument("key")
    p_ins.set_defaults(func=cmd_inspect)

    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

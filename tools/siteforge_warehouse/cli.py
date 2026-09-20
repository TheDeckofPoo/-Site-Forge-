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


def cmd_status(_: argparse.Namespace) -> int:
    url = get_database_url()
    roots = resolve_corpus_roots()
    payload = {
        "extractor_version": EXTRACTOR_VERSION,
        "postgres_configured": is_postgres_configured(),
        "database_url_set": bool(url),
        "database_status": "configured" if url else POSTGRESQL_NOT_CONFIGURED,
        # Never echo credentials — only scheme/host hint
        "database_url_hint": _url_hint(url) if url else None,
        "corpus_roots": [str(p) for p in roots],
        "cp8_seed": seed_cp8_candidate_status(),
    }
    _print_json(payload)
    return 0


def _url_hint(url: str) -> str:
    """Strip password from URL for display."""
    try:
        # postgresql+psycopg://user:pass@host:port/db
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


def cmd_sync(args: argparse.Namespace) -> int:
    roots = [Path(r) for r in (args.roots or [])]
    dry = bool(args.dry_run) or not is_postgres_configured()
    if not is_postgres_configured() and not args.dry_run:
        print(
            f"NOTE: {POSTGRESQL_NOT_CONFIGURED} — running dry-run only.",
            file=sys.stderr,
        )
        dry = True

    known: list[str] = []
    if is_postgres_configured() and not dry:
        # Live ingest path reserved for post-gate; still plan + dry staging for safety
        print(
            "PostgreSQL is configured but live ingest is gated; "
            "use --dry-run for staging or complete POSTGRESQL_INTEGRATION_GATE.",
            file=sys.stderr,
        )
        dry = True

    summary = dry_run_sync(
        roots or None,
        force=bool(args.force),
        build_bundles=True,
    )
    # Drop heavy bundles from stdout JSON
    out = {k: v for k, v in summary.items() if k != "bundles"}
    out["dry_run"] = dry
    _print_json(out)
    return 0 if not summary.get("staging_errors") else 1


def cmd_export_parquet(args: argparse.Namespace) -> int:
    roots = [Path(r) for r in (args.roots or [])]
    out_dir = Path(args.out)
    summary = dry_run_sync(roots or None, build_bundles=True)
    result = export_staging_to_parquet(summary, out_dir)
    out = {
        "export": result,
        "plan_status_counts": summary.get("status_counts"),
        "staging_counts": summary.get("staging_counts"),
        "staging_errors": summary.get("staging_errors"),
        "postgres": "not_required_for_dry_run_export",
    }
    _print_json(out)
    return 0 if not summary.get("staging_errors") else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m tools.siteforge_warehouse.cli",
        description="Site Forge PostgreSQL warehouse foundation CLI",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="Discover + plan sync (dry-run without DB)")
    p_sync.add_argument(
        "--roots",
        nargs="*",
        default=[],
        help="Corpus roots (also SITEFORGE_CORPUS_ROOTS / local_corpus_roots.txt)",
    )
    p_sync.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan + stage without writing to PostgreSQL",
    )
    p_sync.add_argument(
        "--force",
        action="store_true",
        help="Force re-extract even if archive SHA is known complete",
    )
    p_sync.set_defaults(func=cmd_sync)

    p_status = sub.add_parser("status", help="Show warehouse configuration status")
    p_status.set_defaults(func=cmd_status)

    p_exp = sub.add_parser(
        "export-parquet",
        help="Export dry-run staging to Parquet (no DB required)",
    )
    p_exp.add_argument(
        "--out",
        default="exports/learning/parquet",
        help="Output directory (default: exports/learning/parquet)",
    )
    p_exp.add_argument("--roots", nargs="*", default=[])
    p_exp.set_defaults(func=cmd_export_parquet)

    return ap


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

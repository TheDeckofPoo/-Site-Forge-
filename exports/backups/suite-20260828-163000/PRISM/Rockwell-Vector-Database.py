#!/usr/bin/env python3
"""
Rockwell Vector Database — entry point.

Usage:
  python Rockwell-Vector-Database.py index [--reset]
  python Rockwell-Vector-Database.py search "photoeye jam logic"
  python Rockwell-Vector-Database.py stats
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "rockwell-vector-db"))

from rockwell_vectordb import RockwellVectorDB  # noqa: E402


def cmd_index(args: argparse.Namespace) -> int:
    db = RockwellVectorDB(ROOT)
    result = db.index(reset=args.reset)
    print(json.dumps(result, indent=2))
    return 0


def write_output(payload, out_path: str | None) -> None:
    text = json.dumps(payload, indent=2) if isinstance(payload, (dict, list)) else str(payload)
    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
        print(f"Wrote: {out_path}")
    else:
        print(text)


def cmd_search(args: argparse.Namespace) -> int:
    db = RockwellVectorDB(ROOT)
    hits = db.search(args.query, n_results=args.limit, system=args.system or None)
    if not hits:
        print("No results. Run: python Rockwell-Vector-Database.py index")
        return 1
    if args.json:
        write_output(hits, args.out)
        return 0
    for i, hit in enumerate(hits, 1):
        meta = hit.get("metadata") or {}
        print(f"\n--- Result {i} (score {hit.get('score')}) ---")
        print(f"source: {meta.get('source')} | system: {meta.get('system')} | path: {meta.get('path')}")
        if meta.get("routine"):
            print(f"routine: {meta.get('routine')}")
        print(hit.get("text", "")[:1200])
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    db = RockwellVectorDB(ROOT)
    notes = ""
    if args.notes_file:
        notes = Path(args.notes_file).read_text(encoding="utf-8")
    elif args.notes:
        notes = args.notes
    bundle = db.build_ai_context(
        args.query,
        n_results=args.limit,
        system=args.system or None,
        new_site_notes=notes,
    )
    if not bundle["references"]:
        print("No results. Run: python Rockwell-Vector-Database.py index")
        return 1
    if args.json:
        write_output(bundle, args.out)
        return 0
    if args.prompt_only:
        text = bundle["prompt"]
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"Wrote prompt: {args.out}")
        else:
            print(text)
        return 0
    write_output(bundle, args.out)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    db = RockwellVectorDB(ROOT)
    print(json.dumps(db.stats(), indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Rockwell Vector Database")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="Build or refresh the vector index")
    p_index.add_argument("--reset", action="store_true", help="Drop and rebuild the collection")
    p_index.set_defaults(func=cmd_index)

    p_search = sub.add_parser("search", help="Semantic search across indexed project knowledge")
    p_search.add_argument("query", help="Natural language or tag/routine query")
    p_search.add_argument("--limit", type=int, default=8)
    p_search.add_argument("--system", default="", help="Filter to one system e.g. MGE9_MCP05")
    p_search.add_argument("--json", action="store_true", help="Emit JSON results (for scripts / AI)")
    p_search.add_argument("--out", default="", help="Write output to file")
    p_search.set_defaults(func=cmd_search)

    p_context = sub.add_parser(
        "context",
        help="Build AI-ready reference bundle from search + new-site notes",
    )
    p_context.add_argument("query", help="What you want to build, e.g. photoeye jam logic for BYP01")
    p_context.add_argument("--limit", type=int, default=8)
    p_context.add_argument("--system", default="")
    p_context.add_argument("--notes", default="", help="Inline new-site I/O or layout notes")
    p_context.add_argument("--notes-file", default="", help="Text file with new prints / I/O list")
    p_context.add_argument("--out", default="", help="Write JSON or prompt to file")
    p_context.add_argument("--prompt-only", action="store_true", help="Output plain-text prompt only")
    p_context.add_argument("--json", action="store_true", help="Emit JSON (for PRISM dashboard)")
    p_context.set_defaults(func=cmd_context)

    p_stats = sub.add_parser("stats", help="Show collection stats")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
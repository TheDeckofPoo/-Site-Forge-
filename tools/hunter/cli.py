"""Hunter CLI.

  python -m tools.hunter.cli --input <pdf-or-dir> --out <dir> [--project X] [--controller Y]

--controller is a metadata hint only; it never forces devices into a controller.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from . import HUNTER_VERSION


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.hunter.cli",
        description="HUNTER: read-only PDF engineering-print evidence extractor (evidence, not authority).",
    )
    p.add_argument("--input", required=True, help="a PDF file or a directory of PDFs (recursive)")
    p.add_argument("--out", required=True, help="output directory")
    p.add_argument("--project", default=None, help="project metadata label")
    p.add_argument("--controller", default=None, help="controller scope HINT (metadata only)")
    p.add_argument("--generated-at", default=None, help=argparse.SUPPRESS)
    p.add_argument("--version", action="version", version=f"hunter {HUNTER_VERSION}")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    from .pipeline import run_hunter

    try:
        res = run_hunter(args.input, args.out, project=args.project, controller=args.controller,
                         generated_at=args.generated_at)
    except FileNotFoundError as exc:
        print(f"hunter: {exc}", file=sys.stderr)
        return 2
    s = res["summary"]
    print(f"HUNTER {HUNTER_VERSION}: {s['document_count']} document(s), {s['page_count']} page(s), "
          f"{s['evidence_count']} evidence record(s), {s['unknown_token_count']} unknown token(s), "
          f"{s['review_queue_count']} review item(s)")
    for name, path in res["paths"].items():
        print(f"  {name}: {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

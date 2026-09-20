#!/usr/bin/env python3
"""Rebuild physical-I/O dialect / unknown / investigation queues after purpose cleanup.

Separates PRIMARY_RANDOM_CORPUS vs COMBINED_DEVELOPMENT_CORPUS.
Never mutates source archives. No live API.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tarfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tools"))

from fortna_asc import read_asc  # noqa: E402
from fortna_learning_signatures import build_failure_signature  # noqa: E402

from siteforge_learning.classify_configio_dialect import (  # noqa: E402
    classify_configio_dialect,
)
from siteforge_learning.classify_configio_purpose import (  # noqa: E402
    PURPOSE_PHYSICAL_IO,
    classify_configio_purpose,
)
from siteforge_learning.cluster_unknowns import cluster_unknown_dialects  # noqa: E402
from siteforge_learning.corpus_models import FORM_UNKNOWN, DialectHit  # noqa: E402


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_roots(cli_roots: list[str]) -> list[Path]:
    roots: list[Path] = []
    for r in cli_roots:
        p = Path(r)
        if p.is_dir():
            roots.append(p.resolve())
    env = (os.environ.get("SITEFORGE_CORPUS_ROOTS") or "").strip()
    if env:
        for part in env.split(os.pathsep):
            p = Path(part.strip())
            if p.is_dir():
                roots.append(p.resolve())
    local = ROOT / "config" / "local_corpus_roots.txt"
    if local.is_file():
        for line in local.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                p = Path(line)
                if p.is_dir():
                    roots.append(p.resolve())
    uniq = {str(p): p for p in roots}
    return [uniq[k] for k in sorted(uniq)]


def _iter_configio_from_tar(tar_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with tarfile.open(tar_path, "r:*") as tf:
            members = [
                m
                for m in tf.getmembers()
                if m.isfile()
                and "Configio.asc" in Path(m.name).name
                and not Path(m.name).name.endswith(".bak")
            ]
            # Prefer machine-scoped overlay if present
            members = sorted(members, key=lambda m: (0 if "." in Path(m.name).name[12:] else 1, m.name))
            if not members:
                return []
            # Use first matching Configio (machine overlay sorts first when named Configio.asc.MACHINE)
            m = members[0]
            f = tf.extractfile(m)
            if not f:
                return []
            # write temp for read_asc
            import tempfile

            with tempfile.NamedTemporaryFile(delete=False, suffix=".asc") as tmp:
                tmp.write(f.read())
                tmp_path = Path(tmp.name)
            try:
                _, raw = read_asc(tmp_path)
            finally:
                tmp_path.unlink(missing_ok=True)
            for r in raw:
                rows.append(
                    {
                        "desc": (r.get("Desc") or "").strip(),
                        "bank": r.get("Bank"),
                        "octal_word": r.get("Octal_Word") or r.get("OctalWord"),
                        "lohi": (r.get("LoHi") or "").strip(),
                        "in_out": (r.get("In_Out") or "").strip(),
                        "interface": (r.get("Interface") or "").strip(),
                        "i_o_type": (r.get("I_O_Type") or r.get("IO_Type") or "").strip(),
                        "process": (r.get("Process") or "").strip(),
                        "status": (r.get("Status") or "").strip(),
                        "source_archive": tar_path.name,
                    }
                )
    except Exception:
        return []
    return rows


def _iter_configio_from_run(run: Path) -> list[dict[str, Any]]:
    proj = run / "PROJECT" if (run / "PROJECT").is_dir() else run
    paths = sorted(proj.glob("**/Configio.asc*")) if proj.is_dir() else []
    # Also FORTNA/
    paths += sorted(run.glob("**/Configio.asc*"))
    seen = set()
    uniq = []
    for p in paths:
        rp = str(p.resolve())
        if rp in seen:
            continue
        seen.add(rp)
        uniq.append(p)
    if not uniq:
        return []
    # Prefer machine overlay
    uniq.sort(key=lambda p: (0 if p.name.count(".") >= 2 else 1, p.name))
    try:
        _, raw = read_asc(uniq[0])
    except Exception:
        return []
    rows = []
    for r in raw:
        rows.append(
            {
                "desc": (r.get("Desc") or "").strip(),
                "bank": r.get("Bank"),
                "octal_word": r.get("Octal_Word") or r.get("OctalWord"),
                "lohi": (r.get("LoHi") or "").strip(),
                "in_out": (r.get("In_Out") or "").strip(),
                "interface": (r.get("Interface") or "").strip(),
                "i_o_type": (r.get("I_O_Type") or r.get("IO_Type") or "").strip(),
                "process": (r.get("Process") or "").strip(),
                "status": (r.get("Status") or "").strip(),
                "source_archive": str(run),
            }
        )
    return rows


def analyze_roots(roots: list[Path], label: str) -> dict[str, Any]:
    archives = []
    for root in roots:
        archives.extend(sorted(root.rglob("*.tar.gz")))
    run_dirs = []
    for root in roots:
        for cfg in sorted(root.rglob("project.cfg")):
            run_dirs.append(cfg.parent)

    purpose_counts: Counter = Counter()
    dialect_physical: Counter = Counter()
    dialect_all: Counter = Counter()
    exceptions = []
    physical_unknown_hits: list[DialectHit] = []
    total_rows = 0
    physical_rows = 0
    projects = set()
    controllers = set()

    for tar in archives:
        # filename meta
        name = tar.name
        parts = name.replace(".tar.gz", "").split("-")
        if len(parts) >= 4:
            projects.add(parts[2] if parts[0].isdigit() else parts[0])
            controllers.add(parts[-2] if parts[-1].upper().startswith("RUN") else parts[-1])
        rows = _iter_configio_from_tar(tar)
        for row in rows:
            total_rows += 1
            pur = classify_configio_purpose(row)
            purpose_counts[pur["purpose"]] += 1
            hit = classify_configio_dialect(row.get("desc") or "")
            dialect_all[hit.configio_form] += 1
            if pur.get("exception_nonphysical_desc_but_physical_fields"):
                exceptions.append({**row, "purpose": pur})
            if pur.get("keep_in_physical_io_queue"):
                physical_rows += 1
                dialect_physical[hit.configio_form] += 1
                if hit.configio_form == FORM_UNKNOWN:
                    physical_unknown_hits.append(hit)

    for run in run_dirs:
        rows = _iter_configio_from_run(run)
        for row in rows:
            total_rows += 1
            pur = classify_configio_purpose(row)
            purpose_counts[pur["purpose"]] += 1
            hit = classify_configio_dialect(row.get("desc") or "")
            dialect_all[hit.configio_form] += 1
            if pur.get("exception_nonphysical_desc_but_physical_fields"):
                exceptions.append({**row, "purpose": pur})
            if pur.get("keep_in_physical_io_queue"):
                physical_rows += 1
                dialect_physical[hit.configio_form] += 1
                if hit.configio_form == FORM_UNKNOWN:
                    physical_unknown_hits.append(hit)

    clusters = cluster_unknown_dialects(physical_unknown_hits)
    cluster_dicts = [c.to_dict() if hasattr(c, "to_dict") else dict(c) for c in clusters]
    cluster_dicts.sort(
        key=lambda c: -(c.get("count") or c.get("affected_claim_count") or 0)
    )

    queue = []
    for i, c in enumerate(cluster_dicts[:25]):
        queue.append(
            {
                "rank": i + 1,
                "cluster_id": c.get("signature_id") or c.get("cluster_id"),
                "structural_form": (c.get("fields") or {}).get("configio_form")
                or c.get("configio_form")
                or FORM_UNKNOWN,
                "affected_physical_rows": c.get("count") or 0,
                "example_raw": (c.get("example_raw") or [])[:5],
                "payoff_note": "physical-I/O only — internal memory excluded",
            }
        )

    return {
        "label": label,
        "generated_at": _ts(),
        "archive_count": len(archives),
        "extracted_run_count": len(run_dirs),
        "project_count": len(projects),
        "controller_count": len(controllers),
        "projects": sorted(projects),
        "controllers": sorted(controllers),
        "TOTAL_CONFIGIO_ROWS": total_rows,
        "purpose_counts": dict(sorted(purpose_counts.items())),
        "PHYSICAL_IO_CANDIDATE_ROWS": physical_rows,
        "dialect_counts_ALL_ROWS": dict(sorted(dialect_all.items())),
        "dialect_counts_PHYSICAL_ONLY": dict(sorted(dialect_physical.items())),
        "physical_unknown_row_count": dialect_physical.get(FORM_UNKNOWN, 0),
        "physical_unknown_cluster_count": len(cluster_dicts),
        "physical_unknown_clusters": cluster_dicts[:20],
        "investigation_queue": queue,
        "exceptions_nonphysical_desc_but_physical_fields": exceptions[:50],
        "exception_count": len(exceptions),
        "archive_names": [a.name for a in archives],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--primary-root", default="", help="Primary random corpus root")
    ap.add_argument("--combined-roots", nargs="*", default=[])
    ap.add_argument("--out", default=str(ROOT / "exports/learning"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    primary_roots = _load_roots([args.primary_root] if args.primary_root else [])
    # If no primary explicit, use local_corpus_roots first entry only
    if not primary_roots:
        primary_roots = _load_roots([])[:1]

    combined = _load_roots(args.combined_roots or [])
    if not combined:
        combined = _load_roots(
            [
                str(ROOT / "workspace/inbox"),
                str(ROOT / "workspace/_mscatl_peek"),
                str(ROOT / "workspace/_virgin_orindy"),
                str(ROOT / "workspace/_reno_peek"),
                str(ROOT / "workspace/_ordencp3_peek"),
            ]
        )
        combined = list({str(p): p for p in (primary_roots + combined)}.values())

    before = {
        "note": "Pre-cleanup UNKNOWN counted all Desc forms including memory/blank",
        "unknown_rows_all_desc": None,  # filled from last overnight if present
    }
    prev = out / "corpus_summary.json"
    if prev.is_file():
        try:
            old = json.loads(prev.read_text(encoding="utf-8"))
            before["unknown_rows_all_desc"] = (old.get("dialect_form_counts") or {}).get(
                "UNKNOWN"
            )
            before["unknown_clusters"] = old.get("unknown_cluster_count")
            before["total_rows"] = old.get("configio_rows_classified")
        except Exception:
            pass

    primary = analyze_roots(primary_roots, "PRIMARY_RANDOM_CORPUS") if primary_roots else {}
    combined_rep = analyze_roots(combined, "COMBINED_DEVELOPMENT_CORPUS")

    report = {
        "kind": "physical_io_queue_rebuild",
        "generated_at": _ts(),
        "before_cleanup": before,
        "PRIMARY_RANDOM_CORPUS": primary,
        "COMBINED_DEVELOPMENT_CORPUS": combined_rep,
        "live_api_called": False,
    }
    (out / "physical_io_queue_rebuild.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    (out / "investigation_queue.json").write_text(
        json.dumps({"queue": combined_rep.get("investigation_queue") or []}, indent=2),
        encoding="utf-8",
    )
    lines = [
        "PHYSICAL I/O QUEUE REBUILD",
        f"generated: {_ts()}",
        "",
        "BEFORE (all Desc UNKNOWN including memory/blank):",
        f"  total_rows≈{before.get('total_rows')}",
        f"  unknown_rows≈{before.get('unknown_rows_all_desc')}",
        f"  unknown_clusters≈{before.get('unknown_clusters')}",
        "",
        "PRIMARY_RANDOM_CORPUS:",
        f"  archives={primary.get('archive_count')} projects={primary.get('project_count')} controllers={primary.get('controller_count')}",
        f"  TOTAL_CONFIGIO={primary.get('TOTAL_CONFIGIO_ROWS')}",
        f"  purpose={primary.get('purpose_counts')}",
        f"  PHYSICAL_IO_CANDIDATE={primary.get('PHYSICAL_IO_CANDIDATE_ROWS')}",
        f"  physical dialects={primary.get('dialect_counts_PHYSICAL_ONLY')}",
        f"  physical UNKNOWN rows={primary.get('physical_unknown_row_count')} clusters={primary.get('physical_unknown_cluster_count')}",
        "",
        "COMBINED_DEVELOPMENT_CORPUS:",
        f"  archives={combined_rep.get('archive_count')} projects={combined_rep.get('project_count')} controllers={combined_rep.get('controller_count')}",
        f"  TOTAL_CONFIGIO={combined_rep.get('TOTAL_CONFIGIO_ROWS')}",
        f"  purpose={combined_rep.get('purpose_counts')}",
        f"  PHYSICAL_IO_CANDIDATE={combined_rep.get('PHYSICAL_IO_CANDIDATE_ROWS')}",
        f"  physical dialects={combined_rep.get('dialect_counts_PHYSICAL_ONLY')}",
        f"  physical UNKNOWN rows={combined_rep.get('physical_unknown_row_count')} clusters={combined_rep.get('physical_unknown_cluster_count')}",
        "",
        "TOP PHYSICAL INVESTIGATION QUEUE:",
    ]
    for q in (combined_rep.get("investigation_queue") or [])[:10]:
        lines.append(
            f"  {q['rank']}. {q.get('cluster_id')} form={q.get('structural_form')} rows={q.get('affected_physical_rows')} ex={q.get('example_raw')}"
        )
    lines.append(f"\nexceptions (nonphysical Desc but physical fields): {combined_rep.get('exception_count')}")
    (out / "physical_io_queue_rebuild.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "primary_physical_unknown": primary.get("physical_unknown_row_count"),
        "combined_physical_unknown": combined_rep.get("physical_unknown_row_count"),
        "combined_purpose": combined_rep.get("purpose_counts"),
        "combined_physical_dialects": combined_rep.get("dialect_counts_PHYSICAL_ONLY"),
        "queue_top": (combined_rep.get("investigation_queue") or [])[:5],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

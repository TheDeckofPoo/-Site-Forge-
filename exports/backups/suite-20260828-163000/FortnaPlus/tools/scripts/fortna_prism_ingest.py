#!/usr/bin/env python3
"""
Stage FortnaPlus intake into PRISM (Rockwell knowledge-corpus) and re-index.

Dedupes by RUN content fingerprint so the same site is not re-loaded unless
Conveyor.asc / project.cfg / EIP files change.

Usage:
  py fortna_prism_ingest.py after-import --archive path.tar.gz --run-dir ...
  py fortna_prism_ingest.py after-export --export-dir ... --kind autogen|ignition|plc
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_source_id import (  # noqa: E402
    archive_export_name,
    export_label_from_meta,
    load_active_meta,
    run_content_fingerprint,
    safe_fs_name,
)

# Standalone PRISM project (split from Rockwell_GitHub)
DEFAULT_PRISM_ROOT = Path(r"C:\dev\worktree\PRISM")
INGEST_MARKER = ".fortna_ingest.json"


def _prism_root() -> Path:
    # Prefer env override
    import os

    raw = (os.environ.get("FORTNA_PRISM_ROOT") or "").strip()
    if raw and Path(raw).is_dir():
        return Path(raw)
    if DEFAULT_PRISM_ROOT.is_dir():
        return DEFAULT_PRISM_ROOT
    # Sibling of FortnaPlus (new layout)
    sib = REPO_ROOT.parent / "PRISM"
    if sib.is_dir():
        return sib
    # Legacy: PRISM lived inside Rockwell_GitHub
    legacy = REPO_ROOT.parent / "Rockwell_GitHub"
    if (legacy / "rockwell-vector-db").is_dir() or (legacy / "knowledge-corpus").is_dir():
        return legacy
    return DEFAULT_PRISM_ROOT


def _site_dir(prism_root: Path, site: str) -> Path:
    return prism_root / "knowledge-corpus" / safe_fs_name(site)


def _load_marker(site_dir: Path) -> dict:
    p = site_dir / INGEST_MARKER
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_marker(site_dir: Path, data: dict) -> None:
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / INGEST_MARKER).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _copy_tree_files(src: Path, dst: Path, patterns: list[str] | None = None) -> int:
    """Copy files from src into dst; optional suffix filters e.g. ['.pdf', '.csv']."""
    if not src.is_dir():
        return 0
    n = 0
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.rglob("*"):
        if not f.is_file():
            continue
        if patterns and f.suffix.lower() not in patterns:
            continue
        rel = f.relative_to(src)
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(f, out)
            n += 1
        except OSError:
            continue
    return n


def stage_run_to_corpus(
    *,
    run_dir: Path,
    site: str,
    archive_path: str = "",
    fingerprint: str = "",
) -> dict:
    """
    Materialize a PRISM site folder from a Fortna RUN extract.

    Layout (matches PRISM expectations):
      knowledge-corpus/{site}/
        manifest.json
        io/          — small summaries from RUN
        programs/    — empty unless L5X exports linked later
        prints/      — optional PDFs from FortnaPlus workspace/prints
        layouts/     — optional
        generated/   — FortnaPlus autogen/ignition exports
        run_snapshot/— key RUN files for search context
    """
    prism = _prism_root()
    site_dir = _site_dir(prism, site)
    for sub in ("io", "programs", "prints", "layouts", "generated", "hmi", "run_snapshot"):
        (site_dir / sub).mkdir(parents=True, exist_ok=True)

    run_dir = Path(run_dir)
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"

    # Snapshot key RUN artifacts (text/searchable)
    snap = site_dir / "run_snapshot"
    copied = 0
    for rel in (
        "project.cfg",
        "FORTNA/Conveyor.asc",
        "PROJECT/EIPCSV.csv",
        "PROJECT/EIPModules.csv",
        "PROJECT/EIPAdapters.csv",
    ):
        src = run_dir / rel
        if src.is_file():
            dest = snap / Path(rel).name
            try:
                shutil.copy2(src, dest)
                copied += 1
            except OSError:
                pass

    # IO summary JSON for vector extractors
    io_summary = {
        "site": site,
        "archive": archive_path,
        "fingerprint": fingerprint,
        "run_dir": str(run_dir),
        "staged_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files_snapshotted": copied,
    }
    try:
        # Best-effort device list via existing banks helper
        sys.path.insert(0, str(SCRIPT_DIR))
        from fortna_io_extract import extract_io_points, read_project_meta

        meta = read_project_meta(run_dir)
        points = extract_io_points(run_dir)
        preview = [
            {
                "tag": p.get("fortna_name") or p.get("tag"),
                "type": p.get("device_class") or p.get("device_type"),
                "address": p.get("fortna_address"),
                "description": (p.get("description") or "")[:80],
            }
            for p in points[:200]
        ]
        summary_path = site_dir / "io" / "summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "preview": preview,
                    "point_count": len(points),
                    "machine": meta.get("machine_name") or site,
                    "project": meta.get("project_name") or site,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        io_summary["io_points"] = len(points)
        io_summary["machine"] = meta.get("machine_name")
    except Exception as exc:
        io_summary["io_error"] = str(exc)

    # Optional: copy prints assigned under FortnaPlus workspace/prints (small set)
    prints_root = REPO_ROOT / "workspace" / "prints"
    print_n = 0
    if prints_root.is_dir():
        print_n = _copy_tree_files(
            prints_root, site_dir / "prints", patterns=[".pdf", ".png", ".dxf", ".dwg"]
        )
    io_summary["prints_copied"] = print_n

    manifest = {
        "primary": site,
        "quality_tier": "fortna_plus_intake",
        "mechanism": "fortna_plus_run_tar_gz",
        "conveyance_tags": [],
        "sources": {
            "archive": archive_path,
            "run": str(run_dir),
            "fingerprint": fingerprint,
        },
        "fortna_plus": True,
        "staged_utc": io_summary["staged_utc"],
    }
    (site_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (site_dir / "io" / "ingest_meta.json").write_text(
        json.dumps(io_summary, indent=2), encoding="utf-8"
    )

    return {
        "site": site,
        "site_dir": str(site_dir),
        "prism_root": str(prism),
        "snapshot_files": copied,
        "prints_copied": print_n,
        "io_points": io_summary.get("io_points"),
    }


def stage_export_artifacts(export_dir: Path, site: str, kind: str) -> int:
    """Copy L5X / ignition / plc export files into corpus generated/."""
    export_dir = Path(export_dir)
    if not export_dir.is_dir():
        return 0
    site_dir = _site_dir(_prism_root(), site)
    dest = site_dir / "generated" / safe_fs_name(kind or "export")
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in export_dir.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() not in {
            ".l5x", ".csv", ".json", ".md", ".svg", ".html", ".txt"
        }:
            continue
        # skip huge zip/node noise
        if f.stat().st_size > 80_000_000:
            continue
        rel = f.relative_to(export_dir)
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(f, out)
            n += 1
        except OSError:
            continue
    return n


def run_prism_index(*, reset: bool = False) -> dict:
    prism = _prism_root()
    entry = prism / "Rockwell-Vector-Database.py"
    if not entry.is_file():
        return {"ok": False, "error": f"PRISM entry not found: {entry}"}
    cmd = [sys.executable, str(entry), "index"]
    if reset:
        cmd.append("--reset")
    try:
        r = subprocess.run(
            cmd,
            cwd=str(prism),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        payload = {}
        if out:
            try:
                # last JSON object in stdout
                start = out.rfind("{")
                if start >= 0:
                    payload = json.loads(out[start:])
            except json.JSONDecodeError:
                payload = {"raw": out[-500:]}
        return {
            "ok": r.returncode == 0,
            "returncode": r.returncode,
            "index": payload,
            "stderr_tail": err[-400:] if err else "",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def after_import(
    *,
    archive: Path | str,
    run_dir: Path | str,
    force: bool = False,
) -> dict:
    archive = Path(archive)
    run_dir = Path(run_dir)
    site = safe_fs_name(archive_export_name(archive) or export_label_from_meta())
    fp = run_content_fingerprint(run_dir)
    site_dir = _site_dir(_prism_root(), site)
    prev = _load_marker(site_dir)

    if (
        not force
        and prev.get("fingerprint") == fp
        and prev.get("archive_name") == archive.name
        and (site_dir / "manifest.json").is_file()
    ):
        return {
            "ok": True,
            "skipped": True,
            "reason": "same_site_fingerprint",
            "site": site,
            "fingerprint": fp,
            "message": f"PRISM already has {site} (unchanged RUN) — skip re-index",
        }

    staged = stage_run_to_corpus(
        run_dir=run_dir,
        site=site,
        archive_path=str(archive),
        fingerprint=fp,
    )
    indexed = run_prism_index(reset=False)
    marker = {
        "site": site,
        "fingerprint": fp,
        "archive_name": archive.name,
        "archive_path": str(archive),
        "run_dir": str(run_dir),
        "last_ingest_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "indexed": indexed,
        "staged": staged,
    }
    _write_marker(site_dir, marker)
    return {
        "ok": bool(indexed.get("ok", True)),
        "skipped": False,
        "site": site,
        "fingerprint": fp,
        "staged": staged,
        "index": indexed,
        "message": (
            f"PRISM staged + indexed site {site}"
            if indexed.get("ok")
            else f"PRISM staged {site} but index failed: {indexed.get('error') or indexed.get('stderr_tail')}"
        ),
    }


def stage_twin(
    *,
    site: str,
    gaps: dict | None = None,
    peers: list | None = None,
    transport_graph: dict | None = None,
    reindex: bool = False,
) -> dict:
    """Write PRISM site-twin pack: twin/gaps.json, peers.json, optional transport graph."""
    site = safe_fs_name(site or export_label_from_meta())
    site_dir = _site_dir(_prism_root(), site)
    twin_dir = site_dir / "twin"
    gen_transport = site_dir / "generated" / "transport"
    twin_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    if gaps is not None:
        path = twin_dir / "gaps.json"
        path.write_text(json.dumps(gaps, indent=2), encoding="utf-8")
        written.append(str(path))
        # Also keep a searchable copy under generated/
        gen_transport.mkdir(parents=True, exist_ok=True)
        (gen_transport / "twin_gaps.json").write_text(
            json.dumps(gaps, indent=2), encoding="utf-8"
        )
        written.append(str(gen_transport / "twin_gaps.json"))

    if peers is not None:
        path = twin_dir / "peers.json"
        payload = {
            "site": site,
            "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "peers": peers,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written.append(str(path))

    if transport_graph is not None:
        gen_transport.mkdir(parents=True, exist_ok=True)
        path = gen_transport / "graph.json"
        path.write_text(json.dumps(transport_graph, indent=2), encoding="utf-8")
        written.append(str(path))
        (twin_dir / "transport_graph.json").write_text(
            json.dumps(transport_graph, indent=2), encoding="utf-8"
        )
        written.append(str(twin_dir / "transport_graph.json"))

    # Light manifest peer pointer (merge, don't wipe existing)
    manifest_path = site_dir / "manifest.json"
    manifest: dict = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
    manifest["site"] = site
    manifest["twin_updated_utc"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    if peers is not None:
        manifest["peers"] = peers
    if gaps is not None:
        manifest["twin_gap_count"] = gaps.get("gap_count")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    written.append(str(manifest_path))

    indexed = run_prism_index(reset=False) if reindex else {"ok": True, "skipped": True}
    return {
        "ok": True,
        "site": site,
        "written": written,
        "index": indexed,
        "message": f"PRISM twin updated for {site} ({len(written)} files)",
    }


def after_export(
    *,
    export_dir: Path | str,
    kind: str = "autogen",
    site: str = "",
) -> dict:
    export_dir = Path(export_dir)
    site = safe_fs_name(site or export_label_from_meta())
    n = stage_export_artifacts(export_dir, site, kind)
    if n == 0:
        return {
            "ok": True,
            "skipped": True,
            "site": site,
            "files": 0,
            "message": "No export artifacts to stage",
        }
    indexed = run_prism_index(reset=False)
    return {
        "ok": bool(indexed.get("ok", True)),
        "skipped": False,
        "site": site,
        "files": n,
        "index": indexed,
        "message": f"PRISM updated generated/{kind} for {site} ({n} files)",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Site Forge → PRISM ingest")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("after-import", help="Stage RUN + index (dedupe by fingerprint)")
    p1.add_argument("--archive", required=True)
    p1.add_argument("--run-dir", required=True)
    p1.add_argument("--force", action="store_true")

    p2 = sub.add_parser("after-export", help="Stage export artifacts + re-index")
    p2.add_argument("--export-dir", required=True)
    p2.add_argument("--kind", default="autogen")
    p2.add_argument("--site", default="")

    p3 = sub.add_parser("stats", help="Show PRISM root + last marker for active site")

    p4 = sub.add_parser(
        "stage-twin",
        help="Write twin/gaps.json + optional Transport graph snapshot (Phase 0)",
    )
    p4.add_argument("--site", default="")
    p4.add_argument("--gaps", type=Path, help="Path to twin_gaps.json")
    p4.add_argument("--graph", type=Path, help="Path to Transport Build graph JSON")
    p4.add_argument("--reindex", action="store_true")

    args = ap.parse_args()

    if args.cmd == "after-import":
        result = after_import(
            archive=args.archive, run_dir=args.run_dir, force=args.force
        )
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    if args.cmd == "after-export":
        result = after_export(
            export_dir=args.export_dir, kind=args.kind, site=args.site
        )
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    if args.cmd == "stage-twin":
        gaps = None
        graph = None
        if args.gaps and Path(args.gaps).is_file():
            gaps = json.loads(Path(args.gaps).read_text(encoding="utf-8"))
        if args.graph and Path(args.graph).is_file():
            graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
        result = stage_twin(
            site=args.site or "",
            gaps=gaps,
            transport_graph=graph,
            reindex=bool(args.reindex),
        )
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    if args.cmd == "stats":
        meta = load_active_meta()
        site = export_label_from_meta(meta)
        site_dir = _site_dir(_prism_root(), site)
        print(
            json.dumps(
                {
                    "prism_root": str(_prism_root()),
                    "active_site": site,
                    "site_dir": str(site_dir),
                    "marker": _load_marker(site_dir),
                },
                indent=2,
            )
        )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

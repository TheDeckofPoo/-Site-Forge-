#!/usr/bin/env python3
"""Locate FISHER_CC9 RUN path from selection + corpus roots / extracts. No decode."""
from __future__ import annotations

import json
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEL = ROOT / "exports" / "demo" / "siteforge-reality-check-v1" / "hard_site_selection.json"


def main() -> int:
    sel = json.loads(SEL.read_text(encoding="utf-8"))
    chosen = sel["selected"]
    sha = chosen["archive_sha256"]
    machine = chosen["machine"]
    filename = chosen["filename"]

    candidates: list[Path] = []
    # corpus roots
    roots_file = ROOT / "config" / "local_corpus_roots.txt"
    roots: list[Path] = []
    if roots_file.is_file():
        for line in roots_file.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines():
            line = line.strip().strip("\ufeff")
            if line and not line.startswith("#"):
                roots.append(Path(line))
    roots.append(Path(r"C:\Users\curtiskricke\Desktop\All Tar.gz"))
    roots.append(ROOT / "workspace" / "corpus_inbox")
    roots.append(ROOT / "workspace" / "inbox")

    for root in roots:
        if not root.is_dir():
            continue
        direct = root / filename
        if direct.is_file():
            candidates.append(direct)
        for p in root.rglob(f"*{machine}*"):
            if p.is_file() and p.suffixes[-2:] == [".tar", ".gz"] or p.name.endswith(
                ".tar.gz"
            ):
                candidates.append(p)
            if p.is_dir() and (p / "project.cfg").is_file():
                candidates.append(p)
            if p.is_dir() and (p / "RUN" / "project.cfg").is_file():
                candidates.append(p / "RUN")

    # warehouse extract short sha
    short = sha[:16]
    extract = ROOT / "exports" / "learning" / "_extract" / short / "RUN"
    if (extract / "project.cfg").is_file():
        candidates.append(extract)

    # discovered_path from PG
    try:
        import sys

        sys.path.insert(0, str(ROOT / "tools"))
        from sqlalchemy import text
        from siteforge_warehouse.postgres_repository import make_engine

        eng = make_engine()
        with eng.connect() as c:
            row = c.execute(
                text(
                    "SELECT discovered_path, filename FROM corpus.archives "
                    "WHERE archive_sha256=:s"
                ),
                {"s": sha},
            ).mappings().first()
        if row and row["discovered_path"]:
            candidates.append(Path(row["discovered_path"]))
    except Exception as ex:
        print("pg_lookup_error", ex)

    uniq: list[str] = []
    for p in candidates:
        s = str(p)
        if s not in uniq:
            uniq.append(s)

    # Prefer existing RUN dirs, else tar.gz
    run_dir = None
    tar_path = None
    for s in uniq:
        p = Path(s)
        if p.is_dir() and (p / "project.cfg").is_file():
            run_dir = p
            break
    if not run_dir:
        for s in uniq:
            p = Path(s)
            if p.is_file() and p.name.endswith(".tar.gz"):
                tar_path = p
                break

    out = {
        "machine": machine,
        "archive_sha256": sha,
        "filename": filename,
        "candidates": uniq[:30],
        "run_dir": str(run_dir) if run_dir else None,
        "tar_path": str(tar_path) if tar_path else None,
    }

    # If only tar, selectively extract (Windows: skip ABS_CARD_INFO / bad members)
    if not run_dir and tar_path and tar_path.is_file():
        import re

        dest = (
            ROOT
            / "exports"
            / "demo"
            / "siteforge-reality-check-v1"
            / "HARD_BLIND"
            / "_run_extract"
            / machine
        )
        if dest.exists():
            if (dest / "RUN" / "project.cfg").is_file():
                run_dir = dest / "RUN"
            elif (dest / "project.cfg").is_file():
                run_dir = dest
        if not run_dir:
            dest.mkdir(parents=True, exist_ok=True)
            skip_re = re.compile(r"(ABS_CARD_INFO|KTX_)", re.I)
            keep_hint = re.compile(
                r"(project\.cfg$|/FORTNA/|/PROJECT/|Configio|Conveyor|EIP|"
                r"eipcfg|IOCard|EStop|Merge|Mtrchain|Machine\.asc|"
                r"identity\.cfg|info\.cfg)",
                re.I,
            )
            extracted = 0
            skipped = 0
            with tarfile.open(tar_path, "r:gz") as tf:
                for m in tf.getmembers():
                    name = m.name.replace("\\", "/")
                    if not m.isfile():
                        continue
                    if skip_re.search(name):
                        skipped += 1
                        continue
                    if not keep_hint.search(name):
                        skipped += 1
                        continue
                    try:
                        dest_file = dest / name
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        tf.extract(m, dest)
                        extracted += 1
                    except (OSError, tarfile.TarError):
                        skipped += 1
                        continue
            out["extract_stats"] = {"extracted": extracted, "skipped": skipped}
            if (dest / "RUN" / "project.cfg").is_file():
                run_dir = dest / "RUN"
            elif (dest / "project.cfg").is_file():
                run_dir = dest
            else:
                for cfg in dest.rglob("project.cfg"):
                    run_dir = cfg.parent
                    break
        out["run_dir"] = str(run_dir) if run_dir else None
        out["extracted_to"] = str(dest)

    path = (
        ROOT
        / "exports"
        / "demo"
        / "siteforge-reality-check-v1"
        / "HARD_BLIND"
        / "run_locate.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0 if out.get("run_dir") else 2


if __name__ == "__main__":
    raise SystemExit(main())

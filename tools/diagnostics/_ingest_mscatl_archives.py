#!/usr/bin/env python3
"""Ingest all available MSCATL RUN archives into PostgreSQL warehouse."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "scripts"))

from siteforge_warehouse.extract import build_bundle_from_run_dir  # noqa: E402
from siteforge_warehouse.ids import normalize_archive_sha256  # noqa: E402
from siteforge_warehouse.writer import PostgresWarehouseWriter  # noqa: E402

INBOX = REPO / "workspace" / "inbox"
PEEK = REPO / "workspace" / "_mscatl_peek"

CONTROLLERS = ("MSCATL_CP1", "MSCATL_CP2", "MSCATL_CP3", "MSCATL_CP4")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_peek(machine: str) -> Path | None:
    run = PEEK / machine / "RUN"
    if (run / "FORTNA").is_dir():
        return run
    tar = INBOX / f"20260813-1428-MSCATL-{machine}-RUN.tar.gz"
    if not tar.is_file():
        return None
    dest = PEEK / machine
    dest.mkdir(parents=True, exist_ok=True)
    import tarfile

    with tarfile.open(tar, "r:gz") as tf:
        # Python 3.14 may fail on some long/special paths; extract members best-effort.
        for m in tf.getmembers():
            try:
                tf.extract(m, dest, filter="data")
            except Exception:
                continue
    if (dest / "RUN" / "FORTNA").is_dir():
        return dest / "RUN"
    # sometimes extracted as flat RUN
    if (dest / "FORTNA").is_dir():
        return dest
    return run if run.is_dir() else None


def main() -> int:
    writer = PostgresWarehouseWriter()
    writer.ensure_extractor_version()
    results = {}
    for machine in CONTROLLERS:
        tar = INBOX / f"20260813-1428-MSCATL-{machine}-RUN.tar.gz"
        if not tar.is_file():
            results[machine] = {"status": "MISSING_TAR"}
            continue
        run = ensure_peek(machine)
        if run is None or not run.is_dir():
            results[machine] = {"status": "MISSING_RUN"}
            continue
        sha = normalize_archive_sha256(sha256_file(tar))
        bundle = build_bundle_from_run_dir(
            run,
            archive_sha256=sha,
            filename=tar.name,
            discovered_path=str(tar.resolve()),
        )
        bundle.machine = machine
        bundle.project = bundle.project or "MSCATL"
        if bundle.archive:
            bundle.archive.machine = machine
            bundle.archive.project = "MSCATL"
            bundle.archive.site = "MSCATL"
            bundle.archive.filename = tar.name
            bundle.archive.discovered_path = str(tar.resolve())
            bundle.archive.size_bytes = tar.stat().st_size
            bundle.archive.archive_class = "RUN"
        r = writer.ingest_bundle(bundle, force=True)
        counts = bundle.staging_counts()
        results[machine] = {
            "status": r.get("status"),
            "archive_sha256": sha,
            "run_dir": str(run),
            "counts": counts,
        }
        print(machine, r.get("status"), "claims", counts.get("io_claims"), "configio", counts.get("configio_rows"))
    out = REPO / "exports" / "diagnostics" / "mscatl_warehouse_ingest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

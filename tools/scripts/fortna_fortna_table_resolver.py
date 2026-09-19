#!/usr/bin/env python3
"""Canonical FortnaPlus active-table resolver (native ASC shadow).

SOURCE_PROVEN open order (amenu.c get_one_amenu):
  Table.rom.<MACHINE> → Table.rom → Table.asc.<MACHINE> → Table.asc

This module resolves the active ASC view for a machine:
  if Table.asc.<MACHINE> exists (non-empty) → overlay only
  else → Table.asc

Callers should prefer resolve_active_asc / iter_active_tables over ad-hoc
globbing of *.asc* or reading base Table.asc alone.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

from fortna_asc import SCAN_FOLDERS, SKIP_FILE_PREFIXES, read_asc
from fortna_site_model import (
    DEFAULT_MERGE_MODE,
    MODE_NATIVE_SHADOW,
    merge_table_rows,
    resolve_table_paths,
)

ROOT = Path(__file__).resolve().parents[2]


def _fingerprint_path(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _fingerprint_rows(headers: list[str], rows: list[dict[str, Any]]) -> str:
    payload = {
        "headers": headers,
        "rows": [dict(r) if isinstance(r, dict) else r for r in rows],
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def normalize_table_stem(table_stem: str) -> str:
    stem = str(table_stem or "").strip()
    if stem.lower().endswith(".asc"):
        stem = stem[: -len(".asc")]
    return stem


def resolve_active_asc(
    fortna_dir: Path | str,
    table_stem: str,
    machine: str,
    *,
    mode: str = DEFAULT_MERGE_MODE,
) -> dict[str, Any]:
    """Resolve the active ASC table for ``machine``.

    Returns:
      path, kind, rows, headers, fingerprint, plus merge metadata.
    """
    fortna_dir = Path(fortna_dir)
    stem = normalize_table_stem(table_stem)
    basename = f"{stem}.asc"
    machine = str(machine or "").strip()

    paths = resolve_table_paths(fortna_dir, basename, machine)
    merged = merge_table_rows(fortna_dir, basename, machine, mode=mode)

    overlay = paths.get("overlay")
    base = paths.get("base")
    if overlay is not None:
        active_path: Path | None = overlay
        kind = "MACHINE_SPECIFIC_ASC"
    elif base is not None:
        active_path = base
        kind = "GENERIC_ASC"
    else:
        active_path = None
        kind = "MISSING"

    # Active row payloads (plain field dicts)
    plain_rows = [dict(item.get("row") or {}) for item in merged.get("rows") or []]
    headers = list(merged.get("headers") or [])
    file_fp = _fingerprint_path(active_path)
    rows_fp = _fingerprint_rows(headers, plain_rows)

    return {
        "table": stem,
        "basename": basename,
        "machine": machine,
        "mode": merged.get("mode") or mode,
        "path": str(active_path) if active_path else None,
        "path_name": active_path.name if active_path else None,
        "kind": kind,
        "headers": headers,
        "rows": plain_rows,
        "merged_rows": merged.get("rows") or [],
        "fingerprint": {
            "file_sha256": file_fp,
            "rows_sha256": rows_fp,
            "combined": hashlib.sha256(
                f"{file_fp or ''}:{rows_fp}".encode("utf-8")
            ).hexdigest(),
        },
        "resolution": merged.get("resolution"),
        "paths": merged.get("paths") or {},
        "counts": merged.get("counts") or {},
        "historical_rows": merged.get("historical_rows") or [],
    }


def discover_table_stems(run_dir: Path | str, *, machine: str = "") -> list[str]:
    """Discover unique table stems under FORTNA/PROJECT, including overlays."""
    run_dir = Path(run_dir)
    machine = str(machine or "").strip()
    stems: set[str] = set()
    suffix = f".asc.{machine}" if machine else None

    for folder in SCAN_FOLDERS:
        base = run_dir / folder
        if not base.is_dir():
            continue
        for path in sorted(base.iterdir()):
            if not path.is_file():
                continue
            name = path.name
            lower = name.lower()
            if any(lower.startswith(p) for p in SKIP_FILE_PREFIXES):
                continue
            if lower.endswith(".bak"):
                continue
            if suffix and name.endswith(suffix):
                stems.add(name[: -len(suffix)])
                continue
            if lower.endswith(".asc") and name.count(".") == 1:
                stems.add(path.stem)
                continue
            # Generic .asc.<OTHER_MACHINE> ignored unless machine filter empty
            if machine:
                continue
            if ".asc." in lower:
                # stem is everything before .asc.<controller>
                idx = name.lower().find(".asc.")
                if idx > 0:
                    stems.add(name[:idx])
    return sorted(stems)


def iter_active_tables(
    run_dir: Path | str,
    machine: str,
    *,
    mode: str = MODE_NATIVE_SHADOW,
    folders: tuple[str, ...] = SCAN_FOLDERS,
) -> Iterator[dict[str, Any]]:
    """Yield active table resolutions for ``machine`` across RUN folders.

    Includes tables that only exist as ``Table.asc.<MACHINE>`` overlays.
    """
    run_dir = Path(run_dir)
    machine = str(machine or "").strip()
    seen: set[tuple[str, str]] = set()
    stems = discover_table_stems(run_dir, machine=machine)

    for folder in folders:
        fortna = run_dir / folder
        if not fortna.is_dir():
            continue
        for stem in stems:
            base = fortna / f"{stem}.asc"
            overlay = fortna / f"{stem}.asc.{machine}" if machine else None
            if not (base.is_file() or (overlay is not None and overlay.is_file())):
                continue
            key = (folder, stem)
            if key in seen:
                continue
            seen.add(key)
            resolved = resolve_active_asc(fortna, stem, machine, mode=mode)
            resolved["folder"] = folder
            resolved["run_dir"] = str(run_dir)
            if resolved["kind"] == "MISSING":
                continue
            yield resolved


def bypass_loaders_report() -> dict[str, Any]:
    """Static inventory of scripts that still read ASC outside this resolver.

    Kept as a callable so docs/exports can embed a fresh grep-backed list.
    """
    scripts = ROOT / "tools" / "scripts"
    patterns = (
        "read_asc(",
        "merge_table_rows(",
        "iter_asc_tables(",
        "resolve_physical_table_file(",
        "resolve_asc_path(",
        "glob(\"*.asc",
        "glob('*.asc",
        ".asc\")",
    )
    hits: dict[str, list[str]] = {}
    for path in sorted(scripts.glob("*.py")):
        if path.name in {
            "fortna_fortna_table_resolver.py",
            "fortna_site_model.py",
            "fortna_asc.py",
        }:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        matched = [p for p in patterns if p in text]
        # Prefer files that look like direct ASC consumers bypassing resolver
        if any(
            p in matched
            for p in (
                "read_asc(",
                "glob(\"*.asc",
                "glob('*.asc",
                "iter_asc_tables(",
                "resolve_physical_table_file(",
                "resolve_asc_path(",
            )
        ):
            hits[str(path.relative_to(ROOT)).replace("\\", "/")] = matched
    return {
        "kind": "FortnaTableResolverBypassReport",
        "version": 1,
        "canonical_api": [
            "fortna_fortna_table_resolver.resolve_active_asc",
            "fortna_fortna_table_resolver.iter_active_tables",
            "fortna_site_model.merge_table_rows(mode='native_shadow')",
        ],
        "bypass_paths": hits,
        "notes": (
            "These paths still open ASC files directly or via legacy helpers. "
            "migrate_callers should prefer resolve_active_asc for machine-scoped views."
        ),
    }


__all__ = [
    "bypass_loaders_report",
    "discover_table_stems",
    "iter_active_tables",
    "normalize_table_stem",
    "resolve_active_asc",
]

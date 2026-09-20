"""Export staged warehouse evidence to Parquet (offline / dry-run friendly)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .staging import ArchiveEvidenceBundle

_TABLE_ATTRS = (
    "source_files",
    "configio_rows",
    "eipmodules",
    "eipadapters",
    "eipmodule_types",
    "eipcfg_adapters",
    "eipcfg_modules",
    "io_claims",
    "purpose_annotations",
    "dialect_annotations",
    "scopes",
    "conflicts",
    "adapter_bridges",
)


def _as_bundles(
    bundles_or_summary: Sequence[ArchiveEvidenceBundle]
    | Mapping[str, Any]
    | Iterable[ArchiveEvidenceBundle],
) -> list[ArchiveEvidenceBundle]:
    if isinstance(bundles_or_summary, Mapping):
        raw = bundles_or_summary.get("bundles") or []
        return list(raw)
    return list(bundles_or_summary)


def _rows_for_table(
    bundles: list[ArchiveEvidenceBundle], attr: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for b in bundles:
        for row in getattr(b, attr, []) or []:
            rows.append(dict(row))
    return rows


def _flatten_row(row: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (dict, list)):
            flat[k] = json.dumps(v, sort_keys=True, default=str)
        else:
            flat[k] = v
    return flat


def export_staging_to_parquet(
    bundles_or_summary: Sequence[ArchiveEvidenceBundle]
    | Mapping[str, Any]
    | Iterable[ArchiveEvidenceBundle],
    out_dir: Path | str,
) -> dict[str, Any]:
    """Write one parquet file per evidence collection under out_dir.

    Works from dry-run staging when no database is configured.
    """
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pandas is required for parquet export") from exc

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bundles = _as_bundles(bundles_or_summary)
    written: dict[str, str] = {}
    counts: dict[str, int] = {}

    archive_rows = []
    for b in bundles:
        meta = b.archive.to_dict() if hasattr(b.archive, "to_dict") else dict(b.archive)
        meta["extractor_version"] = b.extractor_version
        archive_rows.append(_flatten_row(meta))
    if archive_rows:
        path = out / "archives.parquet"
        pd.DataFrame(archive_rows).to_parquet(path, index=False)
        written["archives"] = str(path)
        counts["archives"] = len(archive_rows)

    for attr in _TABLE_ATTRS:
        rows = [_flatten_row(r) for r in _rows_for_table(bundles, attr)]
        counts[attr] = len(rows)
        if not rows:
            continue
        path = out / f"{attr}.parquet"
        pd.DataFrame(rows).to_parquet(path, index=False)
        written[attr] = str(path)

    keep = out / ".gitkeep"
    if not keep.exists():
        keep.write_text("", encoding="utf-8")

    return {
        "out_dir": str(out),
        "bundle_count": len(bundles),
        "written": written,
        "counts": counts,
    }

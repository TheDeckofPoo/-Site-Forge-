#!/usr/bin/env python3
"""Deterministic Rockwell catalog-signature detector (1794- / 1734- Stage 1).

SIGNATURE DETECTED ≠ CATALOG IDENTITY PROVEN.
Known catalogs require corroboration from EIPModuleType / eipcfg / EIPModules /
supported registry.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from fortna_asc import read_asc

_CATALOG_RE = re.compile(
    r"(?P<matched>(?P<family>1794|1734)-(?P<body>[A-Za-z0-9]+))",
    re.IGNORECASE,
)
_TRAILING_RE = re.compile(r"^(?P<trail>(?:[-_]?\d+)+)")

KNOWN_CATALOG = "KNOWN_CATALOG"
CATALOG_SIGNATURE_ONLY = "CATALOG_SIGNATURE_ONLY"
UNKNOWN_CATALOG = "UNKNOWN_CATALOG"


def family_label(prefix: str) -> str:
    p = (prefix or "").upper()
    if p == "1794":
        return "1794_FLEX"
    if p == "1734":
        return "1734_POINT"
    return "UNKNOWN"


@dataclass(frozen=True)
class RockwellCatalogEvidence:
    raw_text: str
    matched_text: str
    family_prefix: str
    catalog_number: str
    hardware_family: str
    trailing_text: str
    catalog_status: str = CATALOG_SIGNATURE_ONLY
    source_file: str = ""
    source_table: str = ""
    source_row: int | None = None
    confidence: str = "MEDIUM"
    corroboration: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["corroboration"] = list(self.corroboration)
        return d


_KNOWN_CACHE: dict[str, set[str]] = {}


def load_known_catalogs(run_dir: Path | None = None) -> set[str]:
    """Load known catalogs from EIPModuleType (+ optional run_dir overlay)."""
    global _KNOWN_CACHE
    key = str(run_dir.resolve()) if run_dir else "__builtin__"
    if key in _KNOWN_CACHE:
        return _KNOWN_CACHE[key]

    known: set[str] = set()
    # Built-in Stage-1 seeds (always available)
    seeds = [
        "1794-AENT", "1794-AENTR", "1794-IA16", "1794-IB16", "1794-OA8", "1794-OA8I",
        "1794-OB16", "1794-OB16P", "1794-OW8", "1794-OW16",
        "1734-AENT", "1734-AENTR", "1734-IA4", "1734-OA4", "1734-IB8", "1734-OB8",
        "1734-IV8", "1734-OV8", "1734-OW4",
    ]
    known.update(s.upper() for s in seeds)

    candidates: list[Path] = []
    if run_dir:
        run_dir = Path(run_dir)
        candidates.extend(
            [
                run_dir / "PROJECT" / "EIPModuleType.asc",
                run_dir / "PROJECT" / f"EIPModuleType.asc.{run_dir.name}",
            ]
        )
        # machine overlays
        for p in (run_dir / "PROJECT").glob("EIPModuleType.asc*"):
            candidates.append(p)
    for path in candidates:
        if not path.is_file() or path.stat().st_size <= 0:
            continue
        try:
            _, rows = read_asc(path)
        except Exception:
            continue
        for r in rows:
            name = str(r.get("Name") or r.get("Type") or "").strip().upper()
            if re.match(r"^(1794|1734)-[A-Z0-9]+", name):
                # Strip revision suffixes like /B
                name = name.split("/")[0]
                known.add(name)
    _KNOWN_CACHE[key] = known
    return known


def detect_rockwell_catalogs(
    text: Any,
    *,
    source_file: str = "",
    source_table: str = "",
    source_row: int | None = None,
    known_catalogs: set[str] | None = None,
    run_dir: Path | None = None,
) -> list[RockwellCatalogEvidence]:
    raw = "" if text is None else str(text)
    if not raw.strip():
        return []
    known = known_catalogs if known_catalogs is not None else load_known_catalogs(run_dir)
    out: list[RockwellCatalogEvidence] = []
    for m in _CATALOG_RE.finditer(raw):
        matched = m.group("matched")
        fam = m.group("family").upper()
        body = m.group("body").upper()
        catalog = f"{fam}-{body}"
        rest = raw[m.end() :]
        trail_m = _TRAILING_RE.match(rest)
        trailing = trail_m.group("trail") if trail_m else ""
        if catalog in known:
            status = KNOWN_CATALOG
            conf = "HIGH"
            corr = ("known_catalog_registry",)
        elif fam in {"1794", "1734"}:
            status = CATALOG_SIGNATURE_ONLY
            conf = "MEDIUM"
            corr = ("family_prefix_regex_only",)
        else:
            status = UNKNOWN_CATALOG
            conf = "LOW"
            corr = ()
        out.append(
            RockwellCatalogEvidence(
                raw_text=raw,
                matched_text=matched,
                family_prefix=fam,
                catalog_number=catalog,
                hardware_family=family_label(fam),
                trailing_text=trailing,
                catalog_status=status,
                source_file=source_file,
                source_table=source_table,
                source_row=source_row,
                confidence=conf,
                corroboration=corr,
            )
        )
    return out


def first_catalog(text: Any, **kwargs: Any) -> RockwellCatalogEvidence | None:
    hits = detect_rockwell_catalogs(text, **kwargs)
    return hits[0] if hits else None


def scan_fields(
    rows: Iterable[dict[str, Any]],
    fields: list[str],
    *,
    source_file: str = "",
    source_table: str = "",
    row_key: str = "row",
    run_dir: Path | None = None,
) -> list[dict[str, Any]]:
    known = load_known_catalogs(run_dir)
    found: list[dict[str, Any]] = []
    for r in rows:
        try:
            row_i = int(r.get(row_key)) if r.get(row_key) is not None else None
        except (TypeError, ValueError):
            row_i = None
        for f in fields:
            val = r.get(f)
            if val is None:
                for k, v in r.items():
                    if k.lower() == f.lower():
                        val = v
                        break
            if val is None:
                continue
            for ev in detect_rockwell_catalogs(
                val,
                source_file=source_file,
                source_table=source_table or f,
                source_row=row_i,
                known_catalogs=known,
            ):
                d = ev.to_dict()
                d["field"] = f
                found.append(d)
    return found

#!/usr/bin/env python3
"""Deterministic Rockwell catalog-signature detector (1794- / 1734- Stage 1).

Finds WHAT TYPE a string mentions. Does NOT assign physical instance/slot.
Trailing suffixes like -5 are preserved as trailing_text, never auto-slot.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable

# Catalog body: letters+digits after family prefix (not fixed width)
_CATALOG_RE = re.compile(
    r"(?P<matched>(?P<family>1794|1734)-(?P<body>[A-Za-z0-9]+))",
    re.IGNORECASE,
)
_TRAILING_RE = re.compile(r"^(?P<trail>(?:[-_]?\d+)+)")


@dataclass(frozen=True)
class RockwellCatalogEvidence:
    raw_text: str
    matched_text: str
    family_prefix: str
    catalog_number: str
    hardware_family: str
    trailing_text: str
    source_file: str = ""
    source_table: str = ""
    source_row: int | None = None
    confidence: str = "HIGH"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def family_label(prefix: str) -> str:
    p = (prefix or "").upper()
    if p == "1794":
        return "1794_FLEX"
    if p == "1734":
        return "1734_POINT"
    return "UNKNOWN"


def detect_rockwell_catalogs(
    text: Any,
    *,
    source_file: str = "",
    source_table: str = "",
    source_row: int | None = None,
) -> list[RockwellCatalogEvidence]:
    """Extract all 1794-/1734- catalog signatures from arbitrary text."""
    raw = "" if text is None else str(text)
    if not raw.strip():
        return []
    out: list[RockwellCatalogEvidence] = []
    for m in _CATALOG_RE.finditer(raw):
        matched = m.group("matched")
        fam = m.group("family").upper()
        catalog = f"{fam}-{m.group('body').upper()}"
        # Normalize common catalog casing: keep Rockwell-ish form
        catalog = catalog[0:5] + catalog[5:]  # already upper body
        rest = raw[m.end() :]
        trail_m = _TRAILING_RE.match(rest)
        trailing = trail_m.group("trail") if trail_m else ""
        out.append(
            RockwellCatalogEvidence(
                raw_text=raw,
                matched_text=matched,
                family_prefix=fam,
                catalog_number=catalog,
                hardware_family=family_label(fam),
                trailing_text=trailing,
                source_file=source_file,
                source_table=source_table,
                source_row=source_row,
                confidence="HIGH",
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
) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for r in rows:
        try:
            row_i = int(r.get(row_key)) if r.get(row_key) is not None else None
        except (TypeError, ValueError):
            row_i = None
        for f in fields:
            if f not in r and f.lower() not in {k.lower() for k in r}:
                # try case-insensitive
                val = None
                for k, v in r.items():
                    if k.lower() == f.lower():
                        val = v
                        break
            else:
                val = r.get(f)
            if val is None:
                continue
            for ev in detect_rockwell_catalogs(
                val,
                source_file=source_file,
                source_table=source_table or f,
                source_row=row_i,
            ):
                d = ev.to_dict()
                d["field"] = f
                found.append(d)
    return found

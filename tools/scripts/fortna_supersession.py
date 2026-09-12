#!/usr/bin/env python3
"""Supersession evaluator for SiteModel equipment/devices.

Detect SUPERSEDED_CANDIDATE using:
  - controller overlay replacement
  - duplicate I/O
  - identical physical identity
  - explicit disabled record
  - replacement relationship
  - same logical device with newer variant

Never delete automatically. Never use "appears later in file" as sole evidence.
Engineer must confirm.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from fortna_site_model import (
    EXCLUDED,
    HISTORICAL_OR_STALE,
    INACTIVE_CONFIRMED,
    SCOPE_HISTORICAL,
    SCOPE_OVERLAY,
    _clean,
    normalize_name,
)


def _io_key(obj: dict[str, Any]) -> str | None:
    word = _clean(obj.get("io_address_word") or obj.get("IO_Address_Word") or "")
    bit = _clean(obj.get("io_address_bit") or obj.get("IO_Address_Bit") or "")
    if not word:
        return None
    return f"{word}:{bit or '0'}"


def _physical_identity(obj: dict[str, Any]) -> str | None:
    x = obj.get("x")
    y = obj.get("y")
    length = obj.get("length")
    angle = obj.get("angle")
    if x is None or y is None:
        return None
    try:
        return f"{float(x):.1f}|{float(y):.1f}|{float(length or 0):.1f}|{float(angle or 0):.1f}"
    except (TypeError, ValueError):
        return None


def evaluate_supersession(site: dict[str, Any]) -> list[dict[str, Any]]:
    """Return superseded candidates; attach to site['superseded_candidates']."""
    candidates: list[dict[str, Any]] = []
    buckets = ("equipment", "motors", "vfds", "photoeyes", "encoders")

    # Index by IO and physical identity
    by_io: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    by_phys: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    by_base: dict[str, list[tuple[str, dict]]] = defaultdict(list)

    for bucket in buckets:
        for obj in site.get(bucket) or []:
            nn = normalize_name(obj.get("normalized_name") or "")
            if not nn:
                continue
            io = _io_key(obj)
            if io:
                by_io[io].append((bucket, obj))
            phys = _physical_identity(obj)
            if phys:
                by_phys[phys].append((bucket, obj))
            # Strip trailing letter variants P116A / P116
            base = re_base(nn)
            by_base[base].append((bucket, obj))

            reasons: list[str] = []
            if obj.get("source_scope") == SCOPE_HISTORICAL:
                reasons.append("historical_scope")
            if obj.get("active_state") in {INACTIVE_CONFIRMED, HISTORICAL_OR_STALE}:
                reasons.append("inactive_or_stale_state")
            enabled = str(obj.get("enabled") or obj.get("Enabled") or "").upper()
            if enabled in {"N", "NO", "FALSE", "0", "OFF", "DISABLED"}:
                reasons.append("explicit_disabled")
            if reasons:
                candidates.append(
                    _candidate(obj, bucket, reasons, confidence="MEDIUM")
                )

    # Duplicate I/O across active objects
    for io, items in by_io.items():
        if len(items) < 2:
            continue
        overlays = [o for _, o in items if o.get("source_scope") == SCOPE_OVERLAY]
        bases = [o for _, o in items if o.get("source_scope") != SCOPE_OVERLAY]
        if overlays and bases:
            for o in bases:
                candidates.append(
                    _candidate(
                        o,
                        "equipment",
                        ["duplicate_io", "controller_overlay_replacement"],
                        confidence="HIGH",
                        replaces_with=overlays[0].get("normalized_name"),
                        io_key=io,
                    )
                )
        elif len(items) > 1:
            # Same IO claimed by multiple — mark non-INCLUDED or lower confidence as candidates
            included = [o for _, o in items if o.get("inclusion") != EXCLUDED]
            if len(included) > 1:
                for o in included[1:]:
                    candidates.append(
                        _candidate(
                            o,
                            "equipment",
                            ["duplicate_io"],
                            confidence="MEDIUM",
                            io_key=io,
                        )
                    )

    # Identical physical identity + different names
    for phys, items in by_phys.items():
        names = {normalize_name(o.get("normalized_name") or "") for _, o in items}
        if len(names) < 2:
            continue
        for _, o in items:
            if o.get("source_scope") == SCOPE_HISTORICAL or o.get("active_state") in {
                INACTIVE_CONFIRMED,
                HISTORICAL_OR_STALE,
            }:
                candidates.append(
                    _candidate(
                        o,
                        "equipment",
                        ["identical_physical_identity"],
                        confidence="MEDIUM",
                        physical_key=phys,
                    )
                )

    # Same logical device newer variant (P116 vs P116A) — supporting only with other signals
    for base, items in by_base.items():
        if len(items) < 2:
            continue
        variants = sorted(
            items,
            key=lambda t: (
                0 if t[1].get("source_scope") == SCOPE_OVERLAY else 1,
                t[1].get("normalized_name") or "",
            ),
        )
        newer = variants[0][1]
        for _, older in variants[1:]:
            extra_signals = []
            if older.get("source_scope") == SCOPE_HISTORICAL:
                extra_signals.append("historical_scope")
            if older.get("active_state") in {INACTIVE_CONFIRMED, HISTORICAL_OR_STALE}:
                extra_signals.append("inactive_or_stale_state")
            if _io_key(older) and _io_key(older) == _io_key(newer):
                extra_signals.append("duplicate_io")
            if not extra_signals:
                # Never use name variant alone
                continue
            candidates.append(
                _candidate(
                    older,
                    "equipment",
                    ["newer_variant"] + extra_signals,
                    confidence="MEDIUM",
                    replaces_with=newer.get("normalized_name"),
                    logical_base=base,
                )
            )

    # Replacement relationships
    for r in site.get("relationships") or []:
        if str(r.get("kind") or "") not in {"replacement", "supersedes", "replaces"}:
            continue
        frm = normalize_name(r.get("from") or r.get("source") or "")
        to = normalize_name(r.get("to") or r.get("target") or "")
        for bucket in buckets:
            for obj in site.get(bucket) or []:
                if normalize_name(obj.get("normalized_name") or "") == frm:
                    candidates.append(
                        _candidate(
                            obj,
                            bucket,
                            ["replacement_relationship"],
                            confidence="HIGH",
                            replaces_with=to,
                        )
                    )

    # Deduplicate by canonical_id
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for c in candidates:
        cid = c.get("canonical_id") or ""
        if cid in seen:
            # merge reasons
            for u in unique:
                if u.get("canonical_id") == cid:
                    u["reasons"] = sorted(set(u.get("reasons") or []) | set(c.get("reasons") or []))
                    break
            continue
        seen.add(cid)
        unique.append(c)

    # Never auto-exclude; mark state only
    for c in unique:
        c["state"] = "SUPERSEDED_CANDIDATE"
        c["auto_deleted"] = False
        c["engineer_confirmed"] = False

    site["superseded_candidates"] = unique
    return unique


def re_base(nn: str) -> str:
    """Logical base without trailing single-letter variant (P116A -> P116)."""
    m = re.match(r"^((?:P|M|PE|EZPE|VFD|ENC)\d{2,4})[A-Z]?$", nn, re.I)
    if m:
        return m.group(1).upper()
    return nn


def _candidate(
    obj: dict[str, Any],
    bucket: str,
    reasons: list[str],
    *,
    confidence: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "canonical_id": obj.get("canonical_id"),
        "normalized_name": obj.get("normalized_name"),
        "bucket": bucket,
        "reasons": list(reasons),
        "confidence": confidence,
        "provenance": obj.get("provenance"),
        "evidence": obj.get("evidence") or [],
        "engineer_override": obj.get("engineer_override"),
        **extra,
    }

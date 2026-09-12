#!/usr/bin/env python3
"""Canonical RUN SiteModel objects + table precedence merge.

SOURCE OF TRUTH: RUN + engineer overrides only. Never reads finished PLC.
See docs/RUN_DISCOVERY_MODEL.md and docs/RUN_TABLE_PRECEDENCE.md.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fortna_asc import NAME_COLUMNS, read_asc

PROV_RUN_EXPLICIT = "RUN_EXPLICIT"
PROV_RUN_DERIVED = "RUN_DERIVED"
PROV_RUN_DERIVED_HIGH = "RUN_DERIVED_HIGH_CONFIDENCE"
PROV_ENGINEER = "ENGINEER_CONFIGURED"
PROV_ENGINEER_REQUIRED = "ENGINEER_CONFIGURED_REQUIRED"
PROV_UNKNOWN = "UNKNOWN"

ACTIVE_CONFIRMED = "ACTIVE_CONFIRMED"
ACTIVE_LIKELY = "ACTIVE_LIKELY"
INACTIVE_CONFIRMED = "INACTIVE_CONFIRMED"
HISTORICAL_OR_STALE = "HISTORICAL_OR_STALE"
CANDIDATE = "CANDIDATE"
UNKNOWN = "UNKNOWN"

INCLUDED = "INCLUDED"
AVAILABLE = "AVAILABLE"
EXCLUDED = "EXCLUDED"

GEN_READY = "READY"
GEN_CFG = "CONFIGURATION_REQUIRED"
GEN_NOT_SUPPORTED = "NOT_SUPPORTED"
GEN_EXCLUDED = "EXCLUDED"

SCOPE_OVERLAY = "controller_overlay"
SCOPE_BASE_FALLBACK = "base_fallback"
SCOPE_BASE_ONLY = "base_only"
SCOPE_HISTORICAL = "historical"
SCOPE_ENGINEER = "engineer"

BLANK = {"", "N/A", "INVALID", "NONE", "~", "N/A~", "n/a"}
DEFAULT_AREA_ID = "Area_1"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(v: Any) -> str:
    s = str(v or "").strip().strip('"')
    if s.upper() in BLANK or s.startswith("==="):
        return ""
    return s


def normalize_name(name: str) -> str:
    return _clean(name).upper()


def canonical_id(kind: str, name: str) -> str:
    return f"{kind}:{normalize_name(name) or 'UNNAMED'}"


# ---------------------------------------------------------------------------
# Table precedence
# ---------------------------------------------------------------------------


def resolve_table_paths(fortna: Path, basename: str, machine: str) -> dict[str, Any]:
    """Locate base + controller overlay for Table.asc vs Table.asc.<CONTROLLER>."""
    if not basename.endswith(".asc"):
        basename = f"{basename}.asc"
    base = fortna / basename
    overlay = fortna / f"{basename}.{machine}"
    historical = sorted(
        p
        for p in fortna.glob(f"old.{basename}*")
        if p.is_file() and not p.name.lower().endswith(".bak")
    )
    return {
        "basename": basename,
        "machine": machine,
        "base": base if base.is_file() and base.stat().st_size > 0 else None,
        "overlay": overlay if overlay.is_file() and overlay.stat().st_size > 0 else None,
        "historical": historical,
    }


def row_identity_key(row: dict[str, str], headers: list[str] | None = None) -> str | None:
    for col in NAME_COLUMNS:
        val = _clean(row.get(col))
        if val:
            return normalize_name(val)
    # Common sorter header
    for col in ("Sorter Name", "Encoder Name", "Sensor_Name", "Desc", "EventName"):
        val = _clean(row.get(col))
        if val:
            return normalize_name(val)
    if headers:
        val = _clean(row.get(headers[0]))
        if val:
            return normalize_name(val)
    return None


def _merge_fields(winner: dict[str, str], loser: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Fill empty winner fields from loser; return merged row + filled field names."""
    out = dict(winner)
    filled: list[str] = []
    for k, v in loser.items():
        wv = _clean(out.get(k))
        lv = _clean(v)
        if not wv and lv:
            out[k] = v
            filled.append(k)
    return out, filled


def merge_table_rows(
    fortna: Path,
    basename: str,
    machine: str,
) -> dict[str, Any]:
    """Merge base + overlay per docs/RUN_TABLE_PRECEDENCE.md.

    Overlay wins identity collisions; base supplies absent rows; empty overlay
    fields may be filled from base (RUN_DERIVED_HIGH_CONFIDENCE).
    """
    paths = resolve_table_paths(fortna, basename, machine)
    basename = paths["basename"]
    base_path: Path | None = paths["base"]
    overlay_path: Path | None = paths["overlay"]

    base_headers: list[str] = []
    overlay_headers: list[str] = []
    base_rows: list[dict[str, str]] = []
    overlay_rows: list[dict[str, str]] = []
    if base_path is not None:
        base_headers, base_rows = read_asc(base_path)
    if overlay_path is not None:
        overlay_headers, overlay_rows = read_asc(overlay_path)

    headers = overlay_headers or base_headers
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _emit(
        row: dict[str, str],
        *,
        scope: str,
        source_path: Path,
        source_row: int,
        evidence: list[dict[str, Any]] | None = None,
        provenance: str = PROV_RUN_EXPLICIT,
        key: str | None = None,
    ) -> None:
        ident = key or row_identity_key(row, headers)
        if ident:
            if ident in seen:
                return
            seen.add(ident)
        merged.append(
            {
                "row": row,
                "identity": ident,
                "source_table": basename,
                "source_scope": scope,
                "source_row": source_row,
                "source_path": source_path.name,
                "provenance": provenance,
                "evidence": evidence or [],
            }
        )

    if overlay_path is not None and base_path is not None:
        base_by_key: dict[str, tuple[int, dict[str, str]]] = {}
        for i, r in enumerate(base_rows, start=1):
            k = row_identity_key(r, base_headers)
            if k and k not in base_by_key:
                base_by_key[k] = (i, r)

        for i, r in enumerate(overlay_rows, start=1):
            k = row_identity_key(r, overlay_headers)
            evidence: list[dict[str, Any]] = [
                {"kind": "source", "scope": SCOPE_OVERLAY, "path": overlay_path.name, "row": i}
            ]
            prov = PROV_RUN_EXPLICIT
            row = dict(r)
            if k and k in base_by_key:
                bi, br = base_by_key[k]
                row, filled = _merge_fields(r, br)
                if filled:
                    prov = PROV_RUN_DERIVED_HIGH
                    evidence.append(
                        {
                            "kind": "field_fill_from_base",
                            "fields": filled,
                            "base_path": base_path.name,
                            "base_row": bi,
                        }
                    )
                evidence.append(
                    {"kind": "supersedes_base", "base_path": base_path.name, "base_row": bi}
                )
            _emit(
                row,
                scope=SCOPE_OVERLAY,
                source_path=overlay_path,
                source_row=i,
                evidence=evidence,
                provenance=prov,
                key=k,
            )

        for i, r in enumerate(base_rows, start=1):
            k = row_identity_key(r, base_headers)
            if k and k in seen:
                continue
            if not k:
                # Anonymous placeholders from base are not imported when overlay exists
                continue
            _emit(
                r,
                scope=SCOPE_BASE_FALLBACK,
                source_path=base_path,
                source_row=i,
                evidence=[
                    {
                        "kind": "source",
                        "scope": SCOPE_BASE_FALLBACK,
                        "path": base_path.name,
                        "row": i,
                        "note": "identity absent from controller overlay",
                    }
                ],
                key=k,
            )
        resolution = "merged_overlay_over_base"
    elif overlay_path is not None:
        for i, r in enumerate(overlay_rows, start=1):
            _emit(r, scope=SCOPE_OVERLAY, source_path=overlay_path, source_row=i)
        resolution = "overlay_only"
    elif base_path is not None:
        for i, r in enumerate(base_rows, start=1):
            _emit(r, scope=SCOPE_BASE_ONLY, source_path=base_path, source_row=i)
        resolution = "base_only"
    else:
        resolution = "missing"

    historical_rows: list[dict[str, Any]] = []
    for hp in paths["historical"]:
        try:
            hh, hr = read_asc(hp)
        except Exception as exc:  # noqa: BLE001
            historical_rows.append({"path": hp.name, "error": str(exc)})
            continue
        for i, r in enumerate(hr, start=1):
            k = row_identity_key(r, hh)
            if not k:
                continue
            historical_rows.append(
                {
                    "row": r,
                    "identity": k,
                    "source_table": basename,
                    "source_scope": SCOPE_HISTORICAL,
                    "source_row": i,
                    "source_path": hp.name,
                    "provenance": PROV_RUN_EXPLICIT,
                    "active_state_hint": HISTORICAL_OR_STALE,
                }
            )

    return {
        "basename": basename,
        "machine": machine,
        "resolution": resolution,
        "headers": headers,
        "paths": {
            "base": base_path.name if base_path else None,
            "overlay": overlay_path.name if overlay_path else None,
            "historical": [p.name for p in paths["historical"]],
        },
        "rows": merged,
        "historical_rows": historical_rows,
        "counts": {
            "merged": len(merged),
            "overlay_input": len(overlay_rows),
            "base_input": len(base_rows),
            "historical": len(historical_rows),
        },
    }


# ---------------------------------------------------------------------------
# Canonical object
# ---------------------------------------------------------------------------


@dataclass
class CanonicalObject:
    canonical_id: str
    kind: str
    source_table: str
    source_row: Any
    source_scope: str
    raw_name: str
    normalized_name: str
    active_state: str = UNKNOWN
    inclusion: str = AVAILABLE
    confidence: str = "UNKNOWN"
    provenance: str = PROV_UNKNOWN
    evidence: list[dict[str, Any]] = field(default_factory=list)
    engineer_override: dict[str, Any] | None = None
    generation_state: str = GEN_CFG
    area_id: str | None = None
    es_zone_id: str | None = None
    attrs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        attrs = d.pop("attrs", {}) or {}
        d.update(attrs)
        return d


def make_object(
    kind: str,
    raw_name: str,
    *,
    source_table: str = "",
    source_row: Any = None,
    source_scope: str = SCOPE_BASE_ONLY,
    active_state: str = UNKNOWN,
    inclusion: str = AVAILABLE,
    confidence: str = "UNKNOWN",
    provenance: str = PROV_UNKNOWN,
    evidence: list[dict[str, Any]] | None = None,
    generation_state: str = GEN_CFG,
    area_id: str | None = None,
    es_zone_id: str | None = None,
    engineer_override: dict[str, Any] | None = None,
    **attrs: Any,
) -> CanonicalObject:
    nn = normalize_name(raw_name)
    return CanonicalObject(
        canonical_id=canonical_id(kind, nn or raw_name or kind),
        kind=kind,
        source_table=source_table,
        source_row=source_row,
        source_scope=source_scope,
        raw_name=_clean(raw_name) or raw_name,
        normalized_name=nn,
        active_state=active_state,
        inclusion=inclusion,
        confidence=confidence,
        provenance=provenance,
        evidence=list(evidence or []),
        engineer_override=engineer_override,
        generation_state=generation_state,
        area_id=area_id,
        es_zone_id=es_zone_id,
        attrs=attrs,
    )


# Zone-membership / PE fields accepted by apply_engineer_overrides.
ZONE_MEMBERSHIP_FIELDS = (
    "area_id",
    "es_zone_id",
    "jam_zone_id",
    "startstop_zone_id",
    "full_group_id",
    "sorter_zone_id",
    "engineering_area_id",
)
OVERRIDE_SCALAR_FIELDS = (
    "inclusion",
    "active_state",
    "generation_state",
    "pe_roles",
) + ZONE_MEMBERSHIP_FIELDS

# Attr keys that indicate I/O / geometry / activity changes in change_report.
_IO_ATTR_KEYS = (
    "io_address_word",
    "IO_Address_Word",
    "io_points",
    "io_module",
    "io_slot",
    "linked_conveyor",
    "motor_io",
    "vfd_io",
)
_GEOMETRY_ATTR_KEYS = (
    "x",
    "y",
    "angle",
    "length",
    "width",
    "entry_anchor",
    "exit_anchor",
    "has_geometry",
    "placed",
)
_ACTIVITY_ATTR_KEYS = ("active_state", "inclusion", "generation_state", "confidence")


def make_relationship(
    *,
    source: Any,
    target: Any,
    kind: str,
    provenance: str,
    confidence: str,
    evidence: list[dict[str, Any]] | None = None,
    engineer_override: dict[str, Any] | None = None,
    source_table: str = "",
) -> dict[str, Any]:
    """Build a SiteModel relationship edge (source/target + from/to compat)."""
    evid = list(evidence or [])
    return {
        "source": source,
        "target": target,
        # Backward-compatible aliases used by discovery / classifiers.
        "from": source,
        "to": target,
        "kind": kind,
        "provenance": provenance,
        "confidence": confidence,
        "evidence": evid,
        "engineer_override": engineer_override,
        "source_table": source_table or "",
    }


@dataclass
class SiteModel:
    machine_scope: str
    run_dir: str
    generated_at: str = field(default_factory=_ts)
    source_of_truth: str = (
        "RUN + engineer overrides only — finished PLC not read; sorter/WCS generation not faked"
    )
    # V2 schema marker — older consumers ignore unknown keys via to_dict extras.
    schema_version: str = "2.0"
    controllers: list[dict[str, Any]] = field(default_factory=list)
    areas: list[dict[str, Any]] = field(default_factory=list)
    equipment: list[dict[str, Any]] = field(default_factory=list)
    transport: dict[str, Any] = field(default_factory=dict)
    motors: list[dict[str, Any]] = field(default_factory=list)
    vfds: list[dict[str, Any]] = field(default_factory=list)
    # Alias / sync bucket for VFD-class drives (see to_dict sync).
    drives: list[dict[str, Any]] = field(default_factory=list)
    photoeyes: list[dict[str, Any]] = field(default_factory=list)
    encoders: list[dict[str, Any]] = field(default_factory=list)
    estop_zones: list[dict[str, Any]] = field(default_factory=list)
    sawtooth_merges: list[dict[str, Any]] = field(default_factory=list)
    sorters: list[dict[str, Any]] = field(default_factory=list)
    tracking_systems: list[dict[str, Any]] = field(default_factory=list)
    # Alias / sync bucket for tracking_systems (see to_dict sync).
    tracking: list[dict[str, Any]] = field(default_factory=list)
    wcs_interfaces: list[dict[str, Any]] = field(default_factory=list)
    # V2 discovery buckets (empty until harvest fills them).
    io_points: list[dict[str, Any]] = field(default_factory=list)
    motor_chains: list[dict[str, Any]] = field(default_factory=list)
    transport_paths: list[dict[str, Any]] = field(default_factory=list)
    merges: list[dict[str, Any]] = field(default_factory=list)
    scanners: list[dict[str, Any]] = field(default_factory=list)
    communications: list[dict[str, Any]] = field(default_factory=list)
    decision_traces: list[dict[str, Any]] = field(default_factory=list)
    inclusion_reasons: dict[str, Any] = field(default_factory=dict)
    superseded_candidates: list[dict[str, Any]] = field(default_factory=list)
    # Optional operational groups. Discovery may fill; do NOT convert one zone
    # type into another. Expected shape keys (each a list unless noted):
    #   engineering_areas[]  # mirror of areas as an operational group type
    #   estop_zones[]
    #   startstop_zones[]
    #   jam_zones[]
    #   full_groups[]
    #   sorter_zones[]
    # Plus optional doc_refs / metadata. Empty by default for older consumers.
    operational_groups: dict[str, Any] = field(default_factory=dict)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    unresolved: list[dict[str, Any]] = field(default_factory=list)
    table_resolutions: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def sync_aliases(self) -> None:
        """Keep drives↔vfds and tracking↔tracking_systems aligned when one side is empty."""
        if not self.drives and self.vfds:
            self.drives = list(self.vfds)
        elif not self.vfds and self.drives:
            self.vfds = list(self.drives)
        if not self.tracking and self.tracking_systems:
            self.tracking = list(self.tracking_systems)
        elif not self.tracking_systems and self.tracking:
            self.tracking_systems = list(self.tracking)

    def counts(self) -> dict[str, int]:
        self.sync_aliases()
        og = self.operational_groups or {}
        return {
            "controllers": len(self.controllers),
            "areas": len(self.areas),
            "equipment": len(self.equipment),
            "equipment_included": sum(1 for e in self.equipment if e.get("inclusion") == INCLUDED),
            "motors": len(self.motors),
            "vfds": len(self.vfds),
            "drives": len(self.drives),
            "photoeyes": len(self.photoeyes),
            "encoders": len(self.encoders),
            "estop_zones": len(self.estop_zones),
            "sawtooth_merges": len(self.sawtooth_merges),
            "sawtooth_lanes": sum(len(m.get("lanes") or []) for m in self.sawtooth_merges),
            "sorters": len(self.sorters),
            "tracking_systems": len(self.tracking_systems),
            "tracking": len(self.tracking),
            "wcs_interfaces": len(self.wcs_interfaces),
            "io_points": len(self.io_points),
            "motor_chains": len(self.motor_chains),
            "transport_paths": len(self.transport_paths),
            "merges": len(self.merges),
            "scanners": len(self.scanners),
            "communications": len(self.communications),
            "decision_traces": len(self.decision_traces),
            "superseded_candidates": len(self.superseded_candidates),
            "inclusion_reasons": len(self.inclusion_reasons or {}),
            "startstop_zones": len(og.get("startstop_zones") or []),
            "jam_zones": len(og.get("jam_zones") or []),
            "engineering_areas": len(og.get("engineering_areas") or []),
            "full_groups": len(og.get("full_groups") or []),
            "sorter_zones": len(og.get("sorter_zones") or []),
            "og_estop_zones": len(og.get("estop_zones") or []),
            "relationships": len(self.relationships),
            "unresolved": len(self.unresolved),
            "transport_nodes": len((self.transport or {}).get("nodes") or []),
            "transport_edges": len((self.transport or {}).get("edges") or []),
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize model; keep V1 keys and add V2 buckets (backward compatible)."""
        self.sync_aliases()
        d = asdict(self)
        d["counts"] = self.counts()
        return d


def ensure_default_area(model: SiteModel) -> SiteModel:
    """If no reliable RUN area, create Area_1 (ENGINEER_CONFIGURED_REQUIRED)."""
    reliable = [
        a
        for a in model.areas
        if a.get("provenance") in {PROV_RUN_EXPLICIT, PROV_ENGINEER}
        and a.get("normalized_name")
        and a.get("normalized_name") != DEFAULT_AREA_ID.upper()
    ]
    if reliable:
        return model

    area = make_object(
        "area",
        DEFAULT_AREA_ID,
        source_table="",
        source_row=None,
        source_scope=SCOPE_ENGINEER,
        active_state=ACTIVE_LIKELY,
        inclusion=INCLUDED,
        confidence="LOW",
        provenance=PROV_ENGINEER_REQUIRED,
        evidence=[
            {
                "kind": "default_area",
                "note": "No reliable Area table/rows from RUN; Area_1 is engineer-configured required placeholder",
            }
        ],
        generation_state=GEN_CFG,
        run_derived=False,
        default_area=True,
    ).to_dict()
    model.areas = [area]
    for eq in model.equipment:
        if eq.get("inclusion") == INCLUDED and not eq.get("area_id"):
            eq["area_id"] = DEFAULT_AREA_ID
    model.notes.append(
        "Area_1 assigned as ENGINEER_CONFIGURED_REQUIRED default — not claimed as RUN-derived"
    )
    return model


def apply_engineer_overrides(
    model: SiteModel,
    overrides: list[dict[str, Any]] | None,
) -> SiteModel:
    """Re-apply engineer overrides by canonical_id or normalized_name.

    Supports pe_roles and zone membership fields (area_id, es_zone_id,
    jam_zone_id, startstop_zone_id, full_group_id, sorter_zone_id,
    engineering_area_id). Nested ``zone_membership`` dicts are flattened.
    """
    if not overrides:
        return model
    index: dict[str, dict[str, Any]] = {}
    buckets = [
        model.equipment,
        model.motors,
        model.vfds,
        model.drives,
        model.photoeyes,
        model.encoders,
        model.sawtooth_merges,
        model.sorters,
        model.areas,
        model.io_points,
        model.scanners,
        model.merges,
    ]
    for bucket in buckets:
        for obj in bucket:
            index[obj.get("canonical_id", "")] = obj
            nn = obj.get("normalized_name") or ""
            if nn:
                index.setdefault(f"name:{nn}", obj)

    for ov in overrides:
        key = ov.get("canonical_id") or (
            f"name:{normalize_name(ov.get('normalized_name') or ov.get('name') or '')}"
        )
        target = index.get(key) or index.get(ov.get("canonical_id", ""))
        if not target:
            model.unresolved.append(
                {
                    "kind": "override_orphan",
                    "override": ov,
                    "provenance": PROV_ENGINEER,
                }
            )
            continue
        target["engineer_override"] = ov
        applied: list[str] = []
        for field_name in OVERRIDE_SCALAR_FIELDS:
            if field_name in ov and ov[field_name] is not None:
                target[field_name] = ov[field_name]
                applied.append(field_name)
        zm = ov.get("zone_membership")
        if isinstance(zm, dict):
            for field_name in ZONE_MEMBERSHIP_FIELDS:
                if field_name in zm and zm[field_name] is not None:
                    target[field_name] = zm[field_name]
                    applied.append(field_name)
        target.setdefault("evidence", []).append(
            {
                "kind": "engineer_override",
                "fields": sorted(set(list(ov.keys()) + applied)),
            }
        )
        if target.get("provenance") not in {PROV_ENGINEER}:
            target["provenance"] = PROV_ENGINEER
    return model


def _rel_key(rel: dict[str, Any]) -> str:
    src = rel.get("source") if rel.get("source") is not None else rel.get("from")
    tgt = rel.get("target") if rel.get("target") is not None else rel.get("to")
    return f"{src}|{tgt}|{rel.get('kind') or ''}"


def _attr_changed(prev: dict[str, Any], cur: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    changed: list[str] = []
    for k in keys:
        if prev.get(k) != cur.get(k):
            # Only report when at least one side had a value (avoid noise on missing keys).
            if prev.get(k) is not None or cur.get(k) is not None:
                changed.append(k)
    return changed


def change_report(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    """Diff previous site_model.json vs current.

    Emits legacy added/removed/changed_inclusion plus V2 event buckets:
    NEW, REMOVED_FROM_RUN, CHANGED_IO, CHANGED_RELATIONSHIP, CHANGED_ACTIVITY,
    CHANGED_GEOMETRY when detectable from object attrs.
    """
    empty_events: dict[str, list] = {
        "NEW": [],
        "REMOVED_FROM_RUN": [],
        "CHANGED_IO": [],
        "CHANGED_RELATIONSHIP": [],
        "CHANGED_ACTIVITY": [],
        "CHANGED_GEOMETRY": [],
    }
    if not previous:
        return {
            "generated_at": _ts(),
            "baseline": None,
            "status": "NO_PREVIOUS",
            "added": [],
            "removed": [],
            "changed_inclusion": [],
            "new": [],
            "removed_from_run": [],
            "changed_io": [],
            "changed_relationship": [],
            "changed_activity": [],
            "changed_geometry": [],
            "events": empty_events,
            "count_delta": {},
        }

    def _ids(model: dict, key: str) -> dict[str, dict]:
        return {
            (o.get("canonical_id") or o.get("normalized_name") or ""): o
            for o in (model.get(key) or [])
            if (o.get("canonical_id") or o.get("normalized_name"))
        }

    keys = (
        "equipment",
        "sawtooth_merges",
        "sorters",
        "vfds",
        "drives",
        "encoders",
        "areas",
        "motors",
        "photoeyes",
        "io_points",
        "scanners",
        "merges",
        "motor_chains",
    )
    added: list[dict[str, str]] = []
    removed: list[dict[str, str]] = []
    changed: list[dict[str, Any]] = []
    new_events: list[dict[str, Any]] = []
    removed_events: list[dict[str, Any]] = []
    changed_io: list[dict[str, Any]] = []
    changed_activity: list[dict[str, Any]] = []
    changed_geometry: list[dict[str, Any]] = []

    for key in keys:
        prev_ids = _ids(previous, key)
        cur_ids = _ids(current, key)
        for cid in sorted(set(cur_ids) - set(prev_ids)):
            entry = {"bucket": key, "canonical_id": cid}
            added.append(entry)
            new_events.append({**entry, "type": "NEW"})
        for cid in sorted(set(prev_ids) - set(cur_ids)):
            entry = {"bucket": key, "canonical_id": cid}
            removed.append(entry)
            removed_events.append({**entry, "type": "REMOVED_FROM_RUN"})
        for cid in sorted(set(prev_ids) & set(cur_ids)):
            po, co = prev_ids[cid], cur_ids[cid]
            pi, ci = po.get("inclusion"), co.get("inclusion")
            if pi != ci:
                changed.append(
                    {
                        "bucket": key,
                        "canonical_id": cid,
                        "from": pi,
                        "to": ci,
                    }
                )
            act_fields = _attr_changed(po, co, _ACTIVITY_ATTR_KEYS)
            if act_fields:
                changed_activity.append(
                    {
                        "type": "CHANGED_ACTIVITY",
                        "bucket": key,
                        "canonical_id": cid,
                        "fields": act_fields,
                    }
                )
            io_fields = _attr_changed(po, co, _IO_ATTR_KEYS)
            if io_fields:
                changed_io.append(
                    {
                        "type": "CHANGED_IO",
                        "bucket": key,
                        "canonical_id": cid,
                        "fields": io_fields,
                    }
                )
            geo_fields = _attr_changed(po, co, _GEOMETRY_ATTR_KEYS)
            if geo_fields:
                changed_geometry.append(
                    {
                        "type": "CHANGED_GEOMETRY",
                        "bucket": key,
                        "canonical_id": cid,
                        "fields": geo_fields,
                    }
                )

    prev_rels = {_rel_key(r): r for r in (previous.get("relationships") or [])}
    cur_rels = {_rel_key(r): r for r in (current.get("relationships") or [])}
    changed_relationship: list[dict[str, Any]] = []
    for rk in sorted(set(cur_rels) - set(prev_rels)):
        changed_relationship.append(
            {"type": "CHANGED_RELATIONSHIP", "action": "added", "key": rk, "relationship": cur_rels[rk]}
        )
    for rk in sorted(set(prev_rels) - set(cur_rels)):
        changed_relationship.append(
            {
                "type": "CHANGED_RELATIONSHIP",
                "action": "removed",
                "key": rk,
                "relationship": prev_rels[rk],
            }
        )
    for rk in sorted(set(prev_rels) & set(cur_rels)):
        pr, cr = prev_rels[rk], cur_rels[rk]
        if (
            pr.get("provenance") != cr.get("provenance")
            or pr.get("confidence") != cr.get("confidence")
            or pr.get("engineer_override") != cr.get("engineer_override")
        ):
            changed_relationship.append(
                {
                    "type": "CHANGED_RELATIONSHIP",
                    "action": "modified",
                    "key": rk,
                    "from": pr,
                    "to": cr,
                }
            )

    prev_counts = previous.get("counts") or {}
    cur_counts = current.get("counts") or {}
    delta = {
        k: int(cur_counts.get(k, 0)) - int(prev_counts.get(k, 0))
        for k in sorted(set(prev_counts) | set(cur_counts))
    }
    events = {
        "NEW": new_events,
        "REMOVED_FROM_RUN": removed_events,
        "CHANGED_IO": changed_io,
        "CHANGED_RELATIONSHIP": changed_relationship,
        "CHANGED_ACTIVITY": changed_activity,
        "CHANGED_GEOMETRY": changed_geometry,
    }
    return {
        "generated_at": _ts(),
        "baseline": previous.get("generated_at"),
        "status": "COMPARED",
        "added": added,
        "removed": removed,
        "changed_inclusion": changed,
        "new": new_events,
        "removed_from_run": removed_events,
        "changed_io": changed_io,
        "changed_relationship": changed_relationship,
        "changed_activity": changed_activity,
        "changed_geometry": changed_geometry,
        "events": events,
        "count_delta": delta,
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def p_tag_ok(name: str) -> bool:
    return bool(re.match(r"^P\d{2,4}[A-Za-z0-9_]*$", (name or "").strip(), re.I))


def extract_p_from_name(name: str) -> str:
    m = re.search(r"(P\d{2,4}[A-Za-z]?)", name or "", re.I)
    return m.group(1).upper() if m else ""

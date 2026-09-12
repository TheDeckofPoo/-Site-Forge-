#!/usr/bin/env python3
"""Activity + inclusion classifier for RUN SiteModel objects.

Evidence-driven. Row order is supporting only. Explicit RUN relationships beat numbering.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from fortna_site_model import (
    ACTIVE_CONFIRMED,
    ACTIVE_LIKELY,
    AVAILABLE,
    CANDIDATE,
    EXCLUDED,
    GEN_CFG,
    GEN_EXCLUDED,
    GEN_NOT_SUPPORTED,
    GEN_READY,
    HISTORICAL_OR_STALE,
    INACTIVE_CONFIRMED,
    INCLUDED,
    PROV_ENGINEER,
    SCOPE_HISTORICAL,
    SCOPE_OVERLAY,
    UNKNOWN,
    _clean,
    normalize_name,
)

YES = {"Y", "YES", "TRUE", "1", "ON", "ENABLE", "ENABLED"}
NO = {"N", "NO", "FALSE", "0", "OFF", "DISABLE", "DISABLED"}


def _evidence_kinds(obj: dict[str, Any]) -> set[str]:
    return {str(e.get("kind") or e.get("type") or "") for e in (obj.get("evidence") or [])}


def _has_kind(obj: dict[str, Any], *kinds: str) -> bool:
    have = _evidence_kinds(obj)
    return any(k in have for k in kinds)


def classify_object(
    obj: dict[str, Any],
    *,
    machine: str,
    related_links: set[str] | None = None,
    superseded: bool = False,
    in_machine_scope: bool | None = None,
) -> dict[str, Any]:
    """Mutate/return obj with active_state, inclusion, confidence, generation_state."""
    out = obj
    nn = normalize_name(out.get("normalized_name") or out.get("raw_name") or "")
    related_links = related_links or set()
    evidence = list(out.get("evidence") or [])
    scope = out.get("source_scope") or ""

    # Engineer override short-circuit
    ov = out.get("engineer_override")
    if isinstance(ov, dict) and (
        ov.get("inclusion") or ov.get("active_state") or ov.get("generation_state")
    ):
        if ov.get("active_state"):
            out["active_state"] = ov["active_state"]
        if ov.get("inclusion"):
            out["inclusion"] = ov["inclusion"]
        if ov.get("generation_state"):
            out["generation_state"] = ov["generation_state"]
        out["confidence"] = ov.get("confidence") or "HIGH"
        out["provenance"] = PROV_ENGINEER
        evidence.append({"kind": "engineer_override_applied"})
        out["evidence"] = evidence
        return out

    if scope == SCOPE_HISTORICAL or superseded or out.get("active_state_hint") == HISTORICAL_OR_STALE:
        out["active_state"] = HISTORICAL_OR_STALE
        out["inclusion"] = EXCLUDED
        out["confidence"] = "HIGH" if superseded or scope == SCOPE_HISTORICAL else "MEDIUM"
        out["generation_state"] = GEN_EXCLUDED
        evidence.append({"kind": "historical_or_superseded", "superseded": superseded})
        out["evidence"] = evidence
        return out

    enable_val = _clean(
        out.get("enable")
        or out.get("EnableBit")
        or out.get("AllowedToRun")
        or out.get("WCSEnable")
        or (out.get("attrs") or {}).get("enable")
    )
    offline = _clean(out.get("Offline") or out.get("offline") or "")
    disable_io = _clean(out.get("Disable I/O") or out.get("disable_io") or out.get("DisableIO") or "")

    strong_link = nn in related_links or _has_kind(
        out,
        "controller_io",
        "pe_assignment",
        "motor_link",
        "vfd_link",
        "mtrchain",
        "saw_lane",
        "saw_merge",
        "path_link",
        "jam_link",
        "merge_link",
        "encoder_link",
        "ownership",
        "explicit_machine_name",
    )
    overlay_presence = scope == SCOPE_OVERLAY or _has_kind(out, "controller_overlay", "source")
    io_assigned = _has_kind(out, "controller_io", "io_assignment") or bool(
        _clean(out.get("io_address_word") or out.get("IO_Address_Word") or "")
    )

    # Explicit inactive signals
    if offline.upper() in YES or enable_val.upper() in NO:
        out["active_state"] = INACTIVE_CONFIRMED
        out["inclusion"] = EXCLUDED
        out["confidence"] = "HIGH"
        out["generation_state"] = GEN_EXCLUDED
        evidence.append(
            {
                "kind": "explicit_inactive",
                "offline": offline,
                "enable": enable_val,
            }
        )
        out["evidence"] = evidence
        return out

    if strong_link and (io_assigned or overlay_presence or enable_val.upper() in YES):
        state = ACTIVE_CONFIRMED
        conf = "HIGH"
        evidence.append({"kind": "activity_strong_link"})
    elif strong_link or (overlay_presence and io_assigned):
        state = ACTIVE_LIKELY
        conf = "MEDIUM"
        evidence.append({"kind": "activity_likely"})
    elif _has_kind(out, "geometry_candidate", "numbering_hint"):
        state = CANDIDATE
        conf = "LOW"
        evidence.append({"kind": "activity_candidate_only"})
    else:
        state = out.get("active_state") or UNKNOWN
        conf = out.get("confidence") or "UNKNOWN"
        if state == UNKNOWN:
            evidence.append({"kind": "activity_unknown"})

    out["active_state"] = state
    out["confidence"] = conf

    # Inclusion relative to machine scope
    scoped = in_machine_scope
    if scoped is None:
        row_mach = _clean(out.get("machine_name") or out.get("Machine_Name") or "")
        if row_mach:
            scoped = row_mach.upper() == machine.upper()
        else:
            scoped = strong_link or overlay_presence

    if state in {INACTIVE_CONFIRMED, HISTORICAL_OR_STALE}:
        out["inclusion"] = EXCLUDED
        out["generation_state"] = GEN_EXCLUDED
    elif state in {ACTIVE_CONFIRMED, ACTIVE_LIKELY} and scoped:
        out["inclusion"] = INCLUDED
        # generation_state: leave NOT_SUPPORTED if already set for sorter/wcs
        if out.get("generation_state") not in {GEN_NOT_SUPPORTED, GEN_EXCLUDED}:
            if out.get("kind") in {"sorter", "tracking", "wcs"}:
                out["generation_state"] = GEN_NOT_SUPPORTED
            elif out.get("area_id") or out.get("kind") in {"sawtooth_merge", "sawtooth_lane", "equipment"}:
                out["generation_state"] = out.get("generation_state") or GEN_CFG
            else:
                out["generation_state"] = out.get("generation_state") or GEN_CFG
    elif state == CANDIDATE:
        out["inclusion"] = AVAILABLE
        out["generation_state"] = out.get("generation_state") or GEN_CFG
    else:
        out["inclusion"] = AVAILABLE if scoped is False else (out.get("inclusion") or AVAILABLE)
        if out["inclusion"] == EXCLUDED:
            out["generation_state"] = GEN_EXCLUDED

    # Hard rule: inactive/historical never INCLUDED
    if out["active_state"] in {INACTIVE_CONFIRMED, HISTORICAL_OR_STALE}:
        out["inclusion"] = EXCLUDED

    out["evidence"] = evidence
    return out


def classify_site_model(model: dict[str, Any], machine: str) -> dict[str, Any]:
    """Classify all buckets; return activity_classification summary."""
    related: set[str] = set()
    for rel in model.get("relationships") or []:
        for side in ("from", "to", "source", "target"):
            v = normalize_name(str(rel.get(side) or ""))
            if v:
                related.add(v)
        for v in rel.get("nodes") or []:
            related.add(normalize_name(str(v)))

    # Collect saw/vfd/motor linked names
    for merge in model.get("sawtooth_merges") or []:
        related.add(normalize_name(merge.get("normalized_name") or merge.get("raw_name") or ""))
        for lane in merge.get("lanes") or []:
            if isinstance(lane, dict):
                related.add(normalize_name(lane.get("name") or lane.get("normalized_name") or ""))
                for k in ("conveyor", "photoeye", "drive", "vfd"):
                    related.add(normalize_name(str(lane.get(k) or "")))
            else:
                related.add(normalize_name(str(lane)))

    buckets = [
        "equipment",
        "motors",
        "vfds",
        "photoeyes",
        "encoders",
        "estop_zones",
        "sawtooth_merges",
        "sorters",
        "tracking_systems",
        "wcs_interfaces",
        "areas",
        "controllers",
    ]
    by_state: dict[str, list[str]] = defaultdict(list)
    by_inclusion: dict[str, list[str]] = defaultdict(list)

    superseded_names = {
        normalize_name(x.get("identity") or x.get("normalized_name") or "")
        for x in (model.get("_historical_superseded") or [])
    }

    for key in buckets:
        items = model.get(key) or []
        for obj in items:
            if not isinstance(obj, dict):
                continue
            nn = normalize_name(obj.get("normalized_name") or obj.get("raw_name") or "")
            classify_object(
                obj,
                machine=machine,
                related_links=related,
                superseded=nn in superseded_names,
            )
            cid = obj.get("canonical_id") or nn
            by_state[obj.get("active_state") or UNKNOWN].append(cid)
            by_inclusion[obj.get("inclusion") or AVAILABLE].append(cid)

    return {
        "machine": machine,
        "buckets": {
            "by_active_state": {k: sorted(v) for k, v in sorted(by_state.items())},
            "by_inclusion": {k: sorted(v) for k, v in sorted(by_inclusion.items())},
        },
        "counts": {
            "by_active_state": {k: len(v) for k, v in sorted(by_state.items())},
            "by_inclusion": {k: len(v) for k, v in sorted(by_inclusion.items())},
        },
        "rules": [
            "Explicit RUN relationships beat numbering",
            "Row order is supporting evidence only",
            "INACTIVE_CONFIRMED / HISTORICAL_OR_STALE never INCLUDED",
            "Engineer override wins when present",
        ],
    }

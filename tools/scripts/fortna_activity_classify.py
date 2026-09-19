#!/usr/bin/env python3
"""Activity + inclusion classifier for RUN SiteModel objects.

Evidence-driven. Row order is supporting only. Explicit RUN relationships beat numbering.

Cross-table participation scoring (docs = semantics, RUN = facts):
  - FPC-Motor-Startup-Chains: Mtrchain membership / Motor_Chained* / Motor_Aux Latch
  - FPC-Fulls-Jams-Fulljams: Jamcheck / Fullline / Fulljam sensor↔conveyor↔response links
  - FPC-StartStopZones: StartStopZones ↔ Jamzones (Latch Bit → Mtrchain Motor_Aux)
  - SawLane / SawMerge / HSSaw*: merge/lane participation
  - Sorter static config tables vs runtime track slots
  - Configio / FORTNADT / IOCard: I/O assignment ownership

Never deletes stale rows — only sets INCLUDED / AVAILABLE / EXCLUDED.
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
    HISTORICAL_OR_STALE,
    INACTIVE_CONFIRMED,
    INCLUDED,
    PROV_ENGINEER,
    PROV_ENGINEER_REQUIRED,
    SCOPE_HISTORICAL,
    SCOPE_MACHINE_OVERLAY,
    SCOPE_OVERLAY,
    UNKNOWN,
    _clean,
    normalize_name,
)

YES = {"Y", "YES", "TRUE", "1", "ON", "ENABLE", "ENABLED"}
NO = {"N", "NO", "FALSE", "0", "OFF", "DISABLE", "DISABLED"}

# Placeholder / ambiguous raw values. MUST NOT alone deactivate, exclude,
# mark stale, or block generation. Preserve under provenance / Source Evidence.
AMBIGUOUS_FIELD_VALUES = {
    "",
    "N/A",
    "NA",
    "N\\A",
    "NONE",
    "NULL",
    "~",
    "N/A~",
    "INVALID",
    "UNKNOWN",
    "?",
    "-",
    "--",
}


def _raw_str(v: Any) -> str:
    return str(v if v is not None else "").strip().strip('"')


def _is_ambiguous_field_value(v: Any) -> bool:
    """True when a field value is a placeholder with no automatic activity weight."""
    s = _raw_str(v)
    return s.upper() in {x.upper() for x in AMBIGUOUS_FIELD_VALUES} or s.startswith("===")

# ---------------------------------------------------------------------------
# Cross-table evidence weights
# Docs: FPC-Motor-Startup-Chains, FPC-Fulls-Jams-Fulljams, FPC-StartStopZones.
# Higher weight = stronger proof the object participates in live control.
# ---------------------------------------------------------------------------
EVIDENCE_WEIGHTS: dict[str, int] = {
    # Motor startup chains (FPC-Motor-Startup-Chains)
    "mtrchain": 3,
    "mtrchain_aux": 2,
    "mtrchain_stop_zone": 2,
    # Jam / full / fulljam (FPC-Fulls-Jams-Fulljams + FPC-StartStopZones)
    "jam_link": 3,
    "jamzone_link": 3,
    "jamcheck_link": 3,
    "full_link": 2,
    "fullline_link": 2,
    "fulljam_link": 2,
    "startstop_link": 2,
    # Path / geometry participation
    "path_link": 2,
    "convpath_link": 2,
    # Sawtooth / HS sawtooth
    "saw_lane": 3,
    "saw_merge": 3,
    "hssaw_link": 3,
    "hssaw_lane": 3,
    "hssaw_merge": 3,
    # Sorter — static config vs runtime slots (FPC-Sorter-Control-Module)
    "sorter_table": 2,
    "sorter_static": 2,
    "sorter_runtime": 1,
    "sorter_research_integrate": 1,
    # I/O assignment (View I/O / Configio / FORTNADT / IOCard)
    "controller_io": 3,
    "io_assignment": 3,
    "configio_link": 2,
    "fortnadt_link": 1,
    "iocard_link": 2,
    "pe_assignment": 2,
    "motor_link": 2,
    "vfd_link": 2,
    "encoder_link": 2,
    "ownership": 2,
    "explicit_machine_name": 2,
    "controller_overlay": 1,
    "merge_link": 2,
    # Weak / supporting
    "geometry_candidate": 1,
    "numbering_hint": 0,
    "source": 0,
}

STRONG_KINDS = {
    k
    for k, w in EVIDENCE_WEIGHTS.items()
    if w >= 3
} | {
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
    "jamzone_link",
    "jamcheck_link",
    "full_link",
    "fulljam_link",
    "hssaw_link",
    "io_assignment",
}

# Score thresholds after summing weights (plus bonuses below).
SCORE_ACTIVE_CONFIRMED = 5
SCORE_ACTIVE_LIKELY = 3
SCORE_CANDIDATE = 1


def _evidence_kinds(obj: dict[str, Any]) -> set[str]:
    return {str(e.get("kind") or e.get("type") or "") for e in (obj.get("evidence") or [])}


def _has_kind(obj: dict[str, Any], *kinds: str) -> bool:
    have = _evidence_kinds(obj)
    return any(k in have for k in kinds)


def score_cross_table_evidence(
    obj: dict[str, Any],
    *,
    related_links: set[str] | None = None,
) -> dict[str, Any]:
    """Score an object from cross-table evidence kinds.

    Returns {score, matched_kinds, related_hit, breakdown}.
    Documented against FPC-Fulls-Jams-Fulljams, FPC-Motor-Startup-Chains,
    FPC-StartStopZones — RUN facts only; docs supply meaning of the links.
    """
    related_links = related_links or set()
    nn = normalize_name(obj.get("normalized_name") or obj.get("raw_name") or "")
    kinds = _evidence_kinds(obj)
    breakdown: dict[str, int] = {}
    score = 0
    for kind in kinds:
        w = EVIDENCE_WEIGHTS.get(kind, 0)
        if w:
            breakdown[kind] = breakdown.get(kind, 0) + w
            score += w
    related_hit = bool(nn) and nn in related_links
    if related_hit and "related_graph" not in breakdown:
        # Participation in harvested relationship graph (any cross-table edge).
        breakdown["related_graph"] = 2
        score += 2
    return {
        "score": score,
        "matched_kinds": sorted(k for k in kinds if EVIDENCE_WEIGHTS.get(k, 0) > 0),
        "related_hit": related_hit,
        "breakdown": breakdown,
    }


def classify_object(
    obj: dict[str, Any],
    *,
    machine: str,
    related_links: set[str] | None = None,
    superseded: bool = False,
    in_machine_scope: bool | None = None,
) -> dict[str, Any]:
    """Mutate/return obj with active_state, inclusion, confidence, generation_state.

    Every decision records:
      evidence_for[], evidence_against[], source_tables[], confidence,
      engineer_override, generation_reason

    N/A / blank / NONE alone MUST NOT deactivate, exclude, mark stale, or
    block generation. Such values are preserved as contextual Source Evidence.
    """
    out = obj
    nn = normalize_name(out.get("normalized_name") or out.get("raw_name") or "")
    related_links = related_links or set()
    evidence = list(out.get("evidence") or [])
    scope = out.get("source_scope") or ""
    evidence_for: list[str] = []
    evidence_against: list[str] = []
    source_tables: list[str] = []
    if out.get("source_table"):
        source_tables.append(str(out.get("source_table")))

    def _finish(
        *,
        generation_reason: str,
        engineer_override: bool = False,
    ) -> dict[str, Any]:
        out["evidence"] = evidence
        out["evidence_for"] = evidence_for
        out["evidence_against"] = evidence_against
        out["source_tables"] = sorted({s for s in source_tables if s})
        out["generation_reason"] = generation_reason
        out["engineer_override_applied"] = engineer_override
        # Preserve ambiguous raw ownership values for UI Source Evidence display.
        raw_mach = _raw_str(out.get("machine_name") or out.get("Machine_Name") or "")
        if _is_ambiguous_field_value(raw_mach) and raw_mach:
            out.setdefault("source_evidence_notes", []).append(
                {
                    "field": "Machine_Name",
                    "raw_value": raw_mach,
                    "interpretation": "ambiguous_ownership_evidence",
                    "automatic_activity_weight": 0,
                    "note": "N/A/blank alone does not deactivate or exclude",
                }
            )
        return out

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
        evidence_for.append("engineer_override")
        return _finish(generation_reason="ENGINEER_OVERRIDE", engineer_override=True)

    if scope == SCOPE_HISTORICAL or superseded or out.get("active_state_hint") == HISTORICAL_OR_STALE:
        out["active_state"] = HISTORICAL_OR_STALE
        out["inclusion"] = EXCLUDED
        out["confidence"] = "HIGH" if superseded or scope == SCOPE_HISTORICAL else "MEDIUM"
        out["generation_state"] = GEN_EXCLUDED
        evidence.append({"kind": "historical_or_superseded", "superseded": superseded})
        if scope == SCOPE_HISTORICAL:
            evidence_against.append("historical_asc_scope")
        if superseded:
            evidence_against.append("superseded_candidate_confirmed_or_hint")
        out["activity_score"] = 0
        return _finish(
            generation_reason="HISTORICAL_OR_SUPERSEDED",
        )

    # Documented enable/disable controls only — never N/A/blank alone.
    enable_raw = (
        out.get("enable")
        or out.get("EnableBit")
        or out.get("AllowedToRun")
        or out.get("WCSEnable")
        or (out.get("attrs") or {}).get("enable")
    )
    offline_raw = out.get("Offline") or out.get("offline") or ""
    disable_io_raw = (
        out.get("Disable I/O") or out.get("disable_io") or out.get("DisableIO") or ""
    )
    enable_val = _clean(enable_raw)
    offline = _clean(offline_raw)
    disable_io = _clean(disable_io_raw)

    # Record ambiguous placeholder fields as contextual evidence only.
    for field, raw in (
        ("Machine_Name", out.get("machine_name") or out.get("Machine_Name")),
        ("enable", enable_raw),
        ("Offline", offline_raw),
        ("Disable I/O", disable_io_raw),
    ):
        if raw is not None and _is_ambiguous_field_value(raw) and _raw_str(raw):
            evidence.append(
                {
                    "kind": "ambiguous_field_value",
                    "field": field,
                    "raw_value": _raw_str(raw),
                    "automatic_activity_weight": 0,
                }
            )

    scored = score_cross_table_evidence(out, related_links=related_links)
    score = int(scored["score"])
    out["activity_score"] = score
    out["activity_score_breakdown"] = scored["breakdown"]
    for kind in scored["matched_kinds"]:
        evidence_for.append(f"cross_table:{kind}")
        # Infer source tables from evidence detail when present
        for e in evidence:
            if e.get("kind") == kind and e.get("table"):
                source_tables.append(str(e.get("table")))

    strong_link = (
        nn in related_links
        or _has_kind(out, *sorted(STRONG_KINDS))
        or score >= SCORE_ACTIVE_LIKELY
    )
    overlay_presence = (
        scope in (SCOPE_OVERLAY, SCOPE_MACHINE_OVERLAY)
        or _has_kind(out, "controller_overlay", "machine_overlay", "source")
    )
    io_assigned = _has_kind(
        out, "controller_io", "io_assignment", "configio_link", "iocard_link"
    ) or bool(_clean(out.get("io_address_word") or out.get("IO_Address_Word") or ""))

    if io_assigned:
        evidence_for.append("valid_current_io")
    if overlay_presence:
        evidence_for.append("controller_overlay_or_scope")
    if strong_link:
        evidence_for.append("strong_cross_table_or_relationship_link")
    if nn in related_links:
        evidence_for.append("relationship_graph_member")

    # Explicit inactive signals — documented enable/offline only.
    # N/A / blank enable is NOT inactive.
    explicit_inactive = False
    if offline and offline.upper() in YES:
        explicit_inactive = True
        evidence_against.append("offline=YES")
    if enable_val and enable_val.upper() in NO:
        explicit_inactive = True
        evidence_against.append(f"enable={enable_val}")
    # Disable I/O alone is NOT automatic deactivation (optional force path).
    if disable_io and not _is_ambiguous_field_value(disable_io):
        evidence.append(
            {
                "kind": "disable_io_present",
                "value": disable_io,
                "automatic_activity_weight": 0,
                "note": "Disable I/O is optional force path — not sole inactivity proof",
            }
        )

    if explicit_inactive:
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
        return _finish(generation_reason="EXPLICIT_INACTIVE_DOCUMENTED_FIELD")

    # Score-first activity decision (cross-table participation).
    if score >= SCORE_ACTIVE_CONFIRMED and (
        io_assigned or overlay_presence or (enable_val and enable_val.upper() in YES) or score >= 7
    ):
        state = ACTIVE_CONFIRMED
        conf = "HIGH"
        evidence.append(
            {
                "kind": "activity_strong_link",
                "score": score,
                "matched": scored["matched_kinds"],
            }
        )
    elif strong_link and (
        io_assigned or overlay_presence or (enable_val and enable_val.upper() in YES)
    ):
        state = ACTIVE_CONFIRMED
        conf = "HIGH"
        evidence.append({"kind": "activity_strong_link", "score": score})
    elif score >= SCORE_ACTIVE_LIKELY or strong_link or (overlay_presence and io_assigned):
        state = ACTIVE_LIKELY
        conf = "MEDIUM"
        evidence.append(
            {
                "kind": "activity_likely",
                "score": score,
                "matched": scored["matched_kinds"],
            }
        )
    elif score >= SCORE_CANDIDATE or _has_kind(out, "geometry_candidate", "numbering_hint"):
        state = CANDIDATE
        conf = "LOW"
        evidence.append({"kind": "activity_candidate_only", "score": score})
        if _has_kind(out, "geometry_candidate") and score < SCORE_ACTIVE_LIKELY:
            evidence_against.append("geometry_only_insufficient_for_include")
    else:
        state = out.get("active_state") or UNKNOWN
        conf = out.get("confidence") or "UNKNOWN"
        if state == UNKNOWN:
            evidence.append({"kind": "activity_unknown", "score": score})
            evidence_against.append("insufficient_positive_cross_table_evidence")

    out["active_state"] = state
    out["confidence"] = conf

    # Inclusion relative to machine scope.
    # Ambiguous Machine_Name (N/A/blank) is NOT "wrong owner" — treat as unknown ownership.
    scoped = in_machine_scope
    raw_mach = _raw_str(out.get("machine_name") or out.get("Machine_Name") or "")
    if scoped is None:
        if _is_ambiguous_field_value(raw_mach):
            # Ambiguous ownership — fall back to positive evidence, never force EXCLUDED.
            scoped = strong_link or overlay_presence or score >= SCORE_ACTIVE_LIKELY or io_assigned
            evidence.append(
                {
                    "kind": "ambiguous_ownership",
                    "field": "Machine_Name",
                    "raw_value": raw_mach or "(blank)",
                    "interpretation": "ambiguous_ownership_evidence",
                    "automatic_activity_weight": 0,
                }
            )
        else:
            row_mach = _clean(raw_mach)
            if row_mach:
                scoped = row_mach.upper() == machine.upper()
                if scoped:
                    evidence_for.append(f"machine_ownership={row_mach}")
                else:
                    evidence_against.append(f"machine_ownership_other={row_mach}")
            else:
                scoped = strong_link or overlay_presence or score >= SCORE_ACTIVE_LIKELY

    # Default Area_1 / engineer-required placeholders stay INCLUDED for the workspace.
    if out.get("default_area") or out.get("provenance") == PROV_ENGINEER_REQUIRED:
        scoped = True
        evidence_for.append("engineer_required_or_default_area")
        if state in {UNKNOWN, CANDIDATE}:
            state = ACTIVE_LIKELY
            out["active_state"] = state
            conf = out.get("confidence") or "LOW"
            out["confidence"] = conf

    generation_reason = "CLASSIFIED"
    if state in {INACTIVE_CONFIRMED, HISTORICAL_OR_STALE}:
        out["inclusion"] = EXCLUDED
        out["generation_state"] = GEN_EXCLUDED
        generation_reason = "INACTIVE_OR_HISTORICAL"
    elif state in {ACTIVE_CONFIRMED, ACTIVE_LIKELY} and scoped:
        out["inclusion"] = INCLUDED
        generation_reason = "ACTIVE_IN_SCOPE"
        if out.get("generation_state") not in {GEN_NOT_SUPPORTED, GEN_EXCLUDED}:
            if out.get("kind") in {"sorter", "tracking", "wcs"}:
                out["generation_state"] = GEN_NOT_SUPPORTED
                generation_reason = "ACTIVE_BUT_GENERATION_NOT_SUPPORTED"
            elif out.get("area_id") or out.get("kind") in {
                "sawtooth_merge",
                "sawtooth_lane",
                "equipment",
            }:
                out["generation_state"] = out.get("generation_state") or GEN_CFG
            else:
                out["generation_state"] = out.get("generation_state") or GEN_CFG
    elif state == CANDIDATE:
        out["inclusion"] = AVAILABLE
        out["generation_state"] = out.get("generation_state") or GEN_CFG
        generation_reason = "CANDIDATE_NEEDS_REVIEW"
    else:
        # Unknown / out-of-scope: AVAILABLE for review — never silent EXCLUDE from N/A.
        if scoped is False and state not in {ACTIVE_CONFIRMED, ACTIVE_LIKELY}:
            out["inclusion"] = AVAILABLE
            generation_reason = "OUT_OF_SCOPE_OR_INSUFFICIENT_EVIDENCE"
            evidence_against.append("not_in_machine_scope_or_insufficient_evidence")
        else:
            out["inclusion"] = out.get("inclusion") or AVAILABLE
            generation_reason = "AVAILABLE_DEFAULT"
        if out["inclusion"] == EXCLUDED:
            out["generation_state"] = GEN_EXCLUDED
        else:
            out["generation_state"] = out.get("generation_state") or GEN_CFG

    # Hard rule: inactive/historical never INCLUDED; never delete stale rows
    if out["active_state"] in {INACTIVE_CONFIRMED, HISTORICAL_OR_STALE}:
        out["inclusion"] = EXCLUDED
        generation_reason = "INACTIVE_OR_HISTORICAL"

    return _finish(generation_reason=generation_reason)

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

    # Operational groups (StartStopZones / Jamzones) when present
    for key in ("startstop_zones", "jam_zones", "operational_groups"):
        blob = model.get(key)
        if isinstance(blob, dict):
            for sub in blob.values() if not isinstance(blob.get("items"), list) else {"_": blob.get("items")}:
                items = sub if isinstance(sub, list) else []
                for obj in items:
                    if isinstance(obj, dict):
                        related.add(normalize_name(obj.get("normalized_name") or obj.get("raw_name") or ""))
        elif isinstance(blob, list):
            for obj in blob:
                if isinstance(obj, dict):
                    related.add(normalize_name(obj.get("normalized_name") or obj.get("raw_name") or ""))

    og = model.get("operational_groups") or {}
    if isinstance(og, dict):
        for sub_key in ("startstop_zones", "jam_zones"):
            for obj in og.get(sub_key) or []:
                if isinstance(obj, dict):
                    related.add(normalize_name(obj.get("normalized_name") or obj.get("raw_name") or ""))
                    for ref in obj.get("linked_names") or []:
                        related.add(normalize_name(str(ref)))

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
    score_samples: list[dict[str, Any]] = []

    superseded_names = {
        normalize_name(x.get("identity") or x.get("normalized_name") or "")
        for x in (model.get("_historical_superseded") or [])
    }
    # Also honor SUPERSEDED_CANDIDATE list when engineer-confirmed or HIGH confidence
    # with definitive reasons — candidates alone do not auto-exclude.
    for cand in model.get("superseded_candidates") or []:
        if not isinstance(cand, dict):
            continue
        if cand.get("engineer_confirmed") or (
            cand.get("confidence") == "HIGH"
            and "replacement_relationship" in (cand.get("reasons") or [])
        ):
            nn = normalize_name(cand.get("normalized_name") or cand.get("identity") or "")
            if nn:
                superseded_names.add(nn)

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
            if obj.get("activity_score"):
                score_samples.append(
                    {
                        "canonical_id": cid,
                        "score": obj.get("activity_score"),
                        "inclusion": obj.get("inclusion"),
                        "active_state": obj.get("active_state"),
                    }
                )

    score_samples.sort(key=lambda x: (-int(x.get("score") or 0), str(x.get("canonical_id"))))
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
        "scoring": {
            "weights": dict(EVIDENCE_WEIGHTS),
            "thresholds": {
                "ACTIVE_CONFIRMED": SCORE_ACTIVE_CONFIRMED,
                "ACTIVE_LIKELY": SCORE_ACTIVE_LIKELY,
                "CANDIDATE": SCORE_CANDIDATE,
            },
            "doc_refs": [
                "FPC-Fulls-Jams-Fulljams",
                "FPC-Motor-Startup-Chains",
                "FPC-StartStopZones",
            ],
            "top_scores": score_samples[:25],
        },
        "rules": [
            "Explicit RUN relationships beat numbering",
            "Row order is supporting evidence only",
            "INACTIVE_CONFIRMED / HISTORICAL_OR_STALE never INCLUDED",
            "Engineer override wins when present",
            "Cross-table participation (Mtrchain/Jam*/Full*/Saw*/Sorter/Configio) raises activity_score",
            "Stale rows are never deleted — only INCLUDED/AVAILABLE/EXCLUDED",
            "N/A / blank / NONE alone MUST NOT deactivate, exclude, mark stale, or block generation",
            "Machine_Name=N/A is ambiguous ownership evidence, not device inactive",
            "Disable I/O alone is not automatic deactivation",
            "Every decision records evidence_for / evidence_against / generation_reason",
        ],
        "policy": {
            "single_field_na_deactivation": False,
            "ambiguous_field_values": sorted(AMBIGUOUS_FIELD_VALUES),
        },
    }

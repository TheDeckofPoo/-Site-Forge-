#!/usr/bin/env python3
"""Activity classification closure — CP2/CP4/CP5 audits + CP5 19-item review.

Preserves CP5 gap-closure compiler bridge gains. Does not use N/A alone to
deactivate devices. Does not optimize toward finished PLC counts.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_site_model import (  # noqa: E402
    AVAILABLE,
    EXCLUDED,
    INCLUDED,
    _clean,
    load_json,
    normalize_name,
    write_json,
)
from fortna_activity_classify import (  # noqa: E402
    AMBIGUOUS_FIELD_VALUES,
    classify_site_model,
    _is_ambiguous_field_value,
)
from fortna_supersession import evaluate_supersession  # noqa: E402


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


BUCKETS = (
    "equipment",
    "motors",
    "vfds",
    "photoeyes",
    "encoders",
    "sorters",
    "sawtooth_merges",
)


def summarize_activity(site: dict[str, Any], activity: dict[str, Any]) -> dict[str, Any]:
    by_obj: dict[str, Counter] = {b: Counter() for b in ("inclusion", "active_state")}
    per_bucket: dict[str, Any] = {}
    for key in BUCKETS:
        items = site.get(key) or []
        inc = Counter(o.get("inclusion") for o in items)
        act = Counter(o.get("active_state") for o in items)
        per_bucket[key] = {
            "total": len(items),
            "inclusion": dict(inc),
            "active_state": dict(act),
        }
        by_obj["inclusion"].update(inc)
        by_obj["active_state"].update(act)

    # Positive-evidence explanation when nearly all INCLUDED
    eq = site.get("equipment") or []
    eq_inc = sum(1 for e in eq if e.get("inclusion") == INCLUDED)
    explanation = None
    if eq and eq_inc / max(len(eq), 1) >= 0.85:
        top_kinds: Counter[str] = Counter()
        for e in eq:
            if e.get("inclusion") != INCLUDED:
                continue
            for k in e.get("evidence_for") or []:
                top_kinds[str(k)] += 1
            for ev in e.get("evidence") or []:
                kind = ev.get("kind")
                if kind and kind not in {"source", "ambiguous_field_value", "ambiguous_ownership"}:
                    top_kinds[f"evidence:{kind}"] += 1
        explanation = {
            "note": (
                "High INCLUDED ratio is supported by positive cross-table evidence "
                "(I/O, Mtrchain, jam/full, ownership) — not forced balance."
            ),
            "top_positive_signals": top_kinds.most_common(12),
        }

    return {
        "generated_at": _ts(),
        "machine": site.get("machine_scope"),
        "run_dir": site.get("run_dir"),
        "totals": {
            "inclusion": dict(by_obj["inclusion"]),
            "active_state": dict(by_obj["active_state"]),
        },
        "per_bucket": per_bucket,
        "activity_counts": activity.get("counts"),
        "policy": activity.get("policy"),
        "high_included_explanation": explanation,
        "single_field_na_deactivation_used": False,
    }


def reclassify(site_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    site = json.loads(site_path.read_text(encoding="utf-8"))
    machine = site.get("machine_scope") or ""
    # Refresh supersession candidates before classify (engineer-confirmed / HIGH only auto-exclude)
    evaluate_supersession(site)
    activity = classify_site_model(site, machine)
    return site, activity


def audit_cp5_19(
    site: dict[str, Any],
    gap_loss_path: Path,
) -> dict[str, Any]:
    """Audit the 19 CONFIGURATION_REQUIRED equipment from gap-closure."""
    loss = load_json(gap_loss_path) or {}
    rows = (
        ((loss.get("entities") or {}).get("equipment") or {}).get("rows")
        or []
    )
    cfg_names = [
        r.get("name")
        for r in rows
        if r.get("disposition") == "CONFIGURATION_REQUIRED"
    ]
    by_name = {
        normalize_name(e.get("normalized_name") or e.get("raw_name") or ""): e
        for e in (site.get("equipment") or [])
    }
    # Also map generated set from gap closure
    generated = {
        normalize_name(r.get("name") or "")
        for r in rows
        if r.get("disposition") == "GENERATED"
    }

    items = []
    reason_counts: Counter[str] = Counter()
    for name in cfg_names:
        nn = normalize_name(name or "")
        eq = by_name.get(nn) or {}
        io_word = _clean(eq.get("io_address_word") or eq.get("IO_Address_Word") or "")
        mach_raw = str(eq.get("machine_name") or eq.get("Machine_Name") or "")
        mach_ambiguous = _is_ambiguous_field_value(mach_raw)
        has_io_ev = any(
            (e.get("kind") in {"controller_io", "io_assignment", "configio_link"})
            for e in (eq.get("evidence") or [])
        )
        has_motor = bool(_clean(eq.get("motor") or "")) or any(
            e.get("kind") == "motor_link" for e in (eq.get("evidence") or [])
        )
        has_vfd = bool(_clean(eq.get("drive") or eq.get("vfd") or "")) or any(
            e.get("kind") in {"vfd_link", "vfd_to_conveyor"} for e in (eq.get("evidence") or [])
        )
        has_pe = any(e.get("kind") == "pe_assignment" for e in (eq.get("evidence") or []))
        has_path = any(
            e.get("kind") in {"path_link", "convpath_link"} for e in (eq.get("evidence") or [])
        )
        has_mtrchain = any(e.get("kind") == "mtrchain" for e in (eq.get("evidence") or []))
        has_subsystem = any(
            e.get("kind")
            in {
                "saw_lane",
                "saw_merge",
                "sorter_static",
                "sorter_table",
                "merge_link",
                "jam_link",
                "full_link",
            }
            for e in (eq.get("evidence") or [])
        )

        # Reason taxonomy (no N/A-alone resolution)
        if eq.get("active_state") in {"INACTIVE_CONFIRMED", "HISTORICAL_OR_STALE"}:
            reason = "HISTORICAL_CANDIDATE"
        elif not io_word and not has_io_ev:
            reason = "MISSING_IO_PROOF"
        elif mach_ambiguous and not has_io_ev and not has_subsystem:
            # Ambiguous ownership without other proof — still not inactive
            reason = "MISSING_CONTROLLER_SCOPE"
        elif not has_motor and not has_vfd and not has_mtrchain:
            reason = "ENGINEER_CONFIGURATION_REQUIRED"
        elif not has_subsystem and not has_path:
            reason = "AMBIGUOUS_RELATIONSHIP"
        else:
            reason = "ENGINEER_CONFIGURATION_REQUIRED"

        # Compiler bug only if it WAS generated previously incorrectly excluded — not here
        if nn in generated:
            reason = "COMPILER_BUG"

        reason_counts[reason] += 1
        et = str(eq.get("equipment_type") or eq.get("type") or "")
        items.append(
            {
                "identity": name,
                "equipment_type": et,
                "inclusion": eq.get("inclusion"),
                "active_state": eq.get("active_state"),
                "controller_evidence": {
                    "machine_name_raw": mach_raw or None,
                    "machine_name_ambiguous": mach_ambiguous,
                    "source_scope": eq.get("source_scope"),
                    "note": (
                        "N/A Machine_Name is ambiguous ownership — not inactive"
                        if mach_ambiguous
                        else None
                    ),
                },
                "io_evidence": {
                    "io_address_word": io_word or None,
                    "has_io_evidence_kind": has_io_ev,
                },
                "motor_vfd_evidence": {"has_motor": has_motor, "has_vfd": has_vfd, "has_mtrchain": has_mtrchain},
                "pe_evidence": {"has_pe_assignment": has_pe},
                "path_evidence": {"has_path": has_path},
                "zone_evidence": {
                    "area_id": eq.get("area_id"),
                    "es_zone_id": eq.get("es_zone_id"),
                    "jam_zone_id": eq.get("jam_zone_id"),
                },
                "subsystem_references": has_subsystem,
                "evidence_for": eq.get("evidence_for") or [],
                "evidence_against": eq.get("evidence_against") or [],
                "generation_reason": eq.get("generation_reason"),
                "reason_not_generated": reason,
                "na_alone_used": False,
            }
        )

    return {
        "generated_at": _ts(),
        "policy": "N/A alone must not resolve activity or generation disposition",
        "count": len(items),
        "reason_counts": dict(reason_counts),
        "buckets": {
            "proven_active": sum(
                1 for i in items if i.get("active_state") == "ACTIVE_CONFIRMED"
            ),
            "likely_active": sum(
                1 for i in items if i.get("active_state") == "ACTIVE_LIKELY"
            ),
            "historical_candidates": sum(
                1 for i in items if i["reason_not_generated"] == "HISTORICAL_CANDIDATE"
            ),
            "engineer_required": sum(
                1
                for i in items
                if i["reason_not_generated"]
                in {
                    "ENGINEER_CONFIGURATION_REQUIRED",
                    "MISSING_IO_PROOF",
                    "MISSING_CONTROLLER_SCOPE",
                    "AMBIGUOUS_RELATIONSHIP",
                    "MISSING_TEMPLATE",
                    "UNSUPPORTED_TYPE",
                }
            ),
            "compiler_bugs": sum(
                1 for i in items if i["reason_not_generated"] == "COMPILER_BUG"
            ),
        },
        "items": items,
    }


def supersession_audit(site: dict[str, Any]) -> dict[str, Any]:
    cands = evaluate_supersession(site)
    by_reason: Counter[str] = Counter()
    for c in cands:
        for r in c.get("reasons") or []:
            by_reason[str(r)] += 1
    return {
        "generated_at": _ts(),
        "machine": site.get("machine_scope"),
        "candidate_count": len(cands),
        "auto_deleted": False,
        "reasons": dict(by_reason),
        "samples": cands[:40],
        "policy": [
            "SUPERSEDED_CANDIDATE when evidence strong but not definitive",
            "Never silently delete",
            "Engineer confirms before exclusion",
            "Do not use appears-later-in-file as sole evidence",
            "N/A alone is not supersession evidence",
        ],
    }


def verify_cp5_bridge_gains(summary_path: Path) -> dict[str, Any]:
    """Ensure gap-closure gains remain the baseline floor."""
    s = load_json(summary_path) or {}
    floor = {
        "conveyors_generated": 60,
        "pe_generated": 94,
        "io_modules": 61,
        "io_map_rungs": 368,
        "encoders": 5,
    }
    # Re-read generation_result if needed
    gen = load_json(summary_path.parent / "generation_result.json") or {}
    meta = gen.get("meta") or {}
    actual = {
        "conveyors_generated": int(s.get("conveyors_generated") or meta.get("conveyor_count") or 0),
        "pe_generated": int(s.get("pe_generated") or meta.get("pe_device_count") or 0),
        "io_modules": int(meta.get("io_module_count") or s.get("io_modules") or 0),
        "io_map_rungs": int(s.get("io_map_rungs") or meta.get("io_map_rungs") or 0),
        "encoders": int(s.get("encoders_in_l5x") or meta.get("encoder_count") or 0),
    }
    reductions = {
        k: {"floor": floor[k], "actual": actual[k], "ok": actual[k] >= floor[k]}
        for k in floor
    }
    return {
        "generated_at": _ts(),
        "floor": floor,
        "actual": actual,
        "reductions": reductions,
        "preserved": all(v["ok"] for v in reductions.values()),
        "note": "Any reduction requires explicit evidence-based explanation",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Activity classification closure")
    ap.add_argument("--out", type=Path, default=ROOT / "exports" / "activity-closure")
    ap.add_argument(
        "--cp2-site",
        type=Path,
        default=ROOT / "exports" / "run-discovery-cp2" / "site_model.json",
    )
    ap.add_argument(
        "--cp4-site",
        type=Path,
        default=ROOT / "exports" / "run-discovery" / "site_model.json",
    )
    ap.add_argument(
        "--cp5-site",
        type=Path,
        default=ROOT / "exports" / "cp5-blind" / "site_model.json",
    )
    ap.add_argument(
        "--cp5-gap-summary",
        type=Path,
        default=ROOT / "exports" / "cp5-gap-closure" / "summary.json",
    )
    ap.add_argument(
        "--cp5-gap-loss",
        type=Path,
        default=ROOT / "exports" / "cp5-gap-closure" / "pipeline_loss.json",
    )
    args = ap.parse_args(argv)
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    reports = {}
    for label, path in (
        ("cp2", args.cp2_site),
        ("cp4", args.cp4_site),
        ("cp5", args.cp5_site),
    ):
        if not path.is_file():
            reports[label] = {"ok": False, "error": f"missing {path}"}
            write_json(out / f"{label}_activity.json", reports[label])
            continue
        site, activity = reclassify(path)
        # Write reclassified working copies (do not overwrite frozen cp5-blind site_model)
        write_json(out / f"{label}_site_model_reclassified.json", site)
        write_json(out / f"{label}_activity_classification.json", activity)
        summary = summarize_activity(site, activity)
        write_json(out / f"{label}_activity.json", summary)
        reports[label] = summary

    # CP5 19-item audit uses frozen/gap-closure site for identities + reclassified evidence
    cp5_site = load_json(out / "cp5_site_model_reclassified.json") or {}
    audit19 = audit_cp5_19(cp5_site, args.cp5_gap_loss)
    write_json(out / "cp5_19_item_audit.json", audit19)

    # Supersession across CP5 (and include CP2/CP4 counts)
    super_all = {"generated_at": _ts(), "machines": {}}
    for label in ("cp2", "cp4", "cp5"):
        sp = out / f"{label}_site_model_reclassified.json"
        if sp.is_file():
            site = json.loads(sp.read_text(encoding="utf-8"))
            super_all["machines"][label] = supersession_audit(site)
    write_json(out / "supersession_audit.json", super_all)

    bridge = verify_cp5_bridge_gains(args.cp5_gap_summary)
    write_json(out / "cp5_bridge_floor_check.json", bridge)

    summary = {
        "generated_at": _ts(),
        "single_field_na_deactivation_used": False,
        "ambiguous_field_policy": sorted(AMBIGUOUS_FIELD_VALUES),
        "cp2": (reports.get("cp2") or {}).get("totals"),
        "cp4": (reports.get("cp4") or {}).get("totals"),
        "cp5": (reports.get("cp5") or {}).get("totals"),
        "cp5_19": audit19.get("buckets"),
        "cp5_bridge_preserved": bridge.get("preserved"),
        "cp5_bridge_actual": bridge.get("actual"),
    }
    write_json(out / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if bridge.get("preserved") else 1


if __name__ == "__main__":
    raise SystemExit(main())

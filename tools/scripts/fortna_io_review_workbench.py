#!/usr/bin/env python3
"""Engineering Review Workbench — actionable REVIEW_REQUIRED I/O surface.

PRIMARY consumer: Site Forge Desktop Hardware I/O tab (IPC).
Engineer opens a review item, inspects evidence + AI/Relay/KB traces, then:
  CONFIRM_LOCAL | CONFIRM_FOREIGN | MARK_INTERNAL | MARK_SPARE
  | CHANGE_DEVICE_TYPE | ASSIGN_ENDPOINT | CONFIRM_SAFETY | LEAVE_REVIEW

Decisions persist as ENGINEER_CONFIRMED (or sibling terminal statuses) and
survive Apply / restart / build via workspace/engineer_io_confirmations.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_io_engineer_confirm import (  # noqa: E402
    CONFIRM_FOREIGN,
    CONFIRM_LOCAL,
    CONFIRM_SAFETY,
    CHANGE_DEVICE_TYPE,
    ASSIGN_ENDPOINT,
    LEAVE_REVIEW,
    MARK_INTERNAL,
    MARK_SPARE,
    apply_confirmations_to_devices,
    confirm_physical_device,
    default_store_path,
    load_confirmations,
)
from fortna_run_io_source_ledger import (  # noqa: E402
    STATUS_ENGINEER_REQUIRED,
    STATUS_REVIEW,
    build_canonical_device_ledger,
    build_source_evidence_ledger,
    recompute_physical_io_metrics,
)


REVIEW_STATUSES = frozenset({STATUS_REVIEW, STATUS_ENGINEER_REQUIRED})

ACTIONS = (
    CONFIRM_LOCAL,
    CONFIRM_FOREIGN,
    MARK_INTERNAL,
    MARK_SPARE,
    CHANGE_DEVICE_TYPE,
    ASSIGN_ENDPOINT,
    CONFIRM_SAFETY,
    LEAVE_REVIEW,
)


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _find_run_dir(explicit: Path | str | None = None) -> Path | None:
    if explicit:
        p = Path(explicit)
        if (p / "project.cfg").is_file():
            return p
        if (p / "RUN" / "project.cfg").is_file():
            return p / "RUN"
    active = REPO_ROOT / "workspace" / "active"
    if active.is_dir():
        for cfg in active.rglob("project.cfg"):
            return cfg.parent
    return None


def _find_map_csv() -> Path | None:
    builds = REPO_ROOT / "workspace" / ".internal" / "builds"
    if not builds.is_dir():
        return None
    for p in sorted(builds.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        cand = p / "physical_io_map.csv"
        if cand.is_file():
            return cand
    return None


def _kb_matches(name: str) -> list[dict[str, Any]]:
    try:
        from fortna_io_knowledge_base import match_knowledge

        return list(match_knowledge(name) or [])[:8]
    except Exception:
        return []


def _review_item(device: dict[str, Any]) -> dict[str, Any]:
    trace = dict(device.get("escalation_trace") or {})
    name = _norm(device.get("canonical_name"))
    locked = bool(device.get("locked") or device.get("hard_invalid"))
    return {
        "canonical_name": name,
        "suggested_device_type": device.get("device_type") or device.get("equipment_class"),
        "equipment_class": device.get("equipment_class"),
        "evidence_class": device.get("evidence_class"),
        "fortna_plus_hint": device.get("fortna_plus_hint"),
        "source_evidence": device.get("source_evidence") or [],
        "source_evidence_count": device.get("source_evidence_count"),
        "physical_endpoint": device.get("physical_endpoint") or "",
        "controller_ownership": device.get("ownership"),
        "controller": device.get("controller") or "",
        "source_machine": device.get("source_machine") or "",
        "word": device.get("word"),
        "bit": device.get("bit"),
        "module": device.get("module"),
        "slot": device.get("slot"),
        "deterministic_result": trace.get("deterministic_result")
        or trace.get("deterministic_attempt")
        or {
            "code": device.get("deterministic_code"),
            "reason": device.get("reason"),
            "ownership": device.get("ownership"),
            "word_in_active_configio": device.get("word_in_active_configio"),
        },
        "ai_api_result": {
            "called": trace.get("ai_api_called"),
            "result": trace.get("ai_result"),
            "validation": trace.get("ai_validation"),
            "why_not_called": trace.get("why_ai_not_called"),
        },
        "relay_result": {
            "called": trace.get("relay_called"),
            "result": trace.get("relay_result"),
            "validation": trace.get("relay_validation"),
            "why_not_called": trace.get("why_relay_not_called"),
        },
        "non_escalatable_reason": trace.get("non_escalatable_reason"),
        "knowledge_base_matches": trace.get("knowledge_base_evidence")
        or _kb_matches(name),
        "confidence": device.get("confidence"),
        "reason_unresolved": device.get("reason"),
        "final_status": device.get("final_status"),
        "critical": bool(device.get("critical")),
        "assignable": bool(device.get("assignable")),
        "cluster_id": trace.get("cluster_id"),
        "engineer_confirmation": device.get("engineer_confirmation"),
        "locked": locked,
        "editable": not locked,
        "actions_allowed": list(ACTIONS) if not locked else [LEAVE_REVIEW],
        "safety_actions_allowed": bool(
            _norm(device.get("device_type")).upper()
            in {"ESPB", "ESLS", "ESR", "MCR", "SAFETY", "ESTOP"}
            or "SAFETY" in _norm(device.get("equipment_class")).upper()
        ),
    }


def build_workbench(
    *,
    machine: str,
    run_dir: Path | str | None = None,
    physical_io_map_csv: Path | str | None = None,
    confirmations_path: Path | str | None = None,
    include_escalation: bool = False,
) -> dict[str, Any]:
    run_p = _find_run_dir(run_dir)
    if not run_p:
        return {"ok": False, "error": "no active RUN"}
    mach = _norm(machine) or "UNKNOWN"
    map_csv = Path(physical_io_map_csv) if physical_io_map_csv else _find_map_csv()
    store_path = Path(confirmations_path) if confirmations_path else default_store_path(REPO_ROOT)

    evidence = build_source_evidence_ledger(run_p, mach)
    canon = build_canonical_device_ledger(
        evidence,
        machine=mach,
        run_dir=run_p,
        physical_io_map_csv=map_csv,
        confirmations_path=store_path,
        apply_engineer_confirmations=True,
    )

    # Prefer durable live-build escalation snapshot (single source of truth).
    # Do NOT rebuild blank not_yet_escalated traces when a matching snapshot exists.
    snapshot_meta = {"loaded": False}
    try:
        from fortna_io_escalation_store import (
            apply_snapshot_to_canonical,
            load_escalation_snapshot,
        )

        snap = load_escalation_snapshot(machine=mach, run_dir=run_p, repo=REPO_ROOT)
        if snap:
            snapshot_meta = apply_snapshot_to_canonical(canon, snap)
            snapshot_meta["loaded"] = True
            snapshot_meta["path"] = snap.get("_loaded_from")
    except Exception as ex:  # noqa: BLE001
        snapshot_meta = {"loaded": False, "error": str(ex)[:200]}

    if include_escalation and not snapshot_meta.get("loaded"):
        try:
            from fortna_io_prebuild_escalation import (
                probe_escalation_services,
                run_prebuild_io_escalation,
            )

            health = probe_escalation_services()
            esc = run_prebuild_io_escalation(
                canon, machine=mach, run_dir=run_p, health=health
            )
            canon["prebuild_escalation"] = esc
        except Exception as ex:  # noqa: BLE001
            canon["prebuild_escalation_error"] = str(ex)[:300]

    # When snapshot supplied metrics, keep them; otherwise recompute from devices.
    if not snapshot_meta.get("loaded"):
        recompute_physical_io_metrics(canon)
    else:
        # Still refresh counts that depend on engineer confirmations just applied
        try:
            recompute_physical_io_metrics(canon)
            # Re-assert snapshot metrics as build truth for the three coverage %
            sm = snapshot_meta.get("metrics") or {}
            for k in (
                "SOURCE_CONSERVATION_PCT",
                "PHYSICAL_DEVICE_RESOLUTION_PCT",
                "GENERATED_PHYSICAL_IO_PCT",
                "device_resolution_coverage_pct",
                "generated_io_coverage_pct",
            ):
                if sm.get(k) is not None:
                    canon[k] = sm[k]
        except Exception:
            pass

    devices = list(canon.get("devices") or [])
    review_devices = [
        d
        for d in devices
        if _norm(d.get("final_status")).split(":")[0] in REVIEW_STATUSES
        or (
            # Surface critical UNSUPPORTED Safety/PB with escalation evidence
            d.get("critical")
            and _norm(d.get("final_status")).split(":")[0] == "UNSUPPORTED"
        )
    ]
    # Also surface engineer-confirmed recently for audit trail
    confirmed = [
        d
        for d in devices
        if d.get("engineer_confirmation")
        and _norm(d.get("final_status")).split(":")[0]
        not in REVIEW_STATUSES
    ]

    items = [_review_item(d) for d in review_devices]
    items.sort(key=lambda x: (0 if x.get("critical") else 1, x.get("canonical_name") or ""))

    return {
        "ok": True,
        "ori": "ENGINEERING_REVIEW_WORKBENCH",
        "machine": mach,
        "run_dir": str(run_p),
        "confirmations_path": str(store_path),
        "escalation_snapshot": snapshot_meta,
        "metrics_source": (
            "live_build_escalation_snapshot"
            if snapshot_meta.get("loaded")
            else "rebuilt_ledger"
        ),
        "review_count": len(items),
        "critical_review_count": sum(1 for i in items if i.get("critical")),
        "items": items,
        "recently_confirmed": [
            {
                "canonical_name": d.get("canonical_name"),
                "final_status": d.get("final_status"),
                "engineer_confirmation": d.get("engineer_confirmation"),
            }
            for d in confirmed[:40]
        ],
        "metrics": {
            "SOURCE_CONSERVATION_PCT": canon.get("SOURCE_CONSERVATION_PCT"),
            "PHYSICAL_DEVICE_RESOLUTION_PCT": canon.get("PHYSICAL_DEVICE_RESOLUTION_PCT"),
            "GENERATED_PHYSICAL_IO_PCT": canon.get("GENERATED_PHYSICAL_IO_PCT"),
            "unique_physical_devices": canon.get("unique_physical_devices"),
            "mapped_physical_devices": canon.get("unique_mapped"),
            "proven_physical_spares": canon.get("proven_physical_spares"),
            "foreign_devices": canon.get("unique_foreign"),
            "review_physical_devices": canon.get("unique_review"),
            "unsupported_physical_devices": canon.get("unique_unsupported"),
            "internal_logical_excluded": canon.get("unique_internal_logical"),
            "unproven_channel_occupancy": canon.get("unproven_channel_occupancy"),
            "critical_unresolved_count": canon.get("critical_unresolved_count"),
        },
        "actions": list(ACTIONS),
        "pushbuttons": [
            _review_item(d)
            for d in devices
            if d.get("device_type") == "PUSHBUTTON_CONTROL"
            and _norm(d.get("final_status")).split(":")[0] in REVIEW_STATUSES
        ],
        "safety": [
            _review_item(d)
            for d in devices
            if d.get("device_type") in {"ESPB", "ESLS", "ESR", "MCR", "SAFETY", "ESTOP"}
            and _norm(d.get("final_status")).split(":")[0] in REVIEW_STATUSES
        ],
        "prebuild_escalation": canon.get("prebuild_escalation"),
    }


def get_item(
    canonical_name: str,
    *,
    machine: str,
    run_dir: Path | str | None = None,
) -> dict[str, Any]:
    wb = build_workbench(machine=machine, run_dir=run_dir, include_escalation=False)
    if not wb.get("ok"):
        return wb
    key = _norm(canonical_name).upper()
    for item in wb.get("items") or []:
        if _norm(item.get("canonical_name")).upper() == key:
            return {"ok": True, "item": item, "metrics": wb.get("metrics")}
    # Also search recently confirmed / all devices via rebuild
    run_p = _find_run_dir(run_dir)
    if run_p:
        evidence = build_source_evidence_ledger(run_p, machine)
        canon = build_canonical_device_ledger(
            evidence, machine=machine, run_dir=run_p, apply_engineer_confirmations=True
        )
        for d in canon.get("devices") or []:
            if _norm(d.get("canonical_name")).upper() == key:
                return {"ok": True, "item": _review_item(d), "metrics": wb.get("metrics")}
    return {"ok": False, "error": f"device not found: {canonical_name}"}


def apply_review_decision(
    *,
    canonical_device: str,
    classification: str,
    machine: str = "",
    controller: str = "",
    physical_endpoint: str = "",
    device_type: str = "",
    safety_classification: str = "",
    safety_zone: str = "",
    reason: str = "",
    confirmed_by: str = "engineer",
    conflict_acknowledged: bool = False,
    store_path: Path | str | None = None,
) -> dict[str, Any]:
    cls = _norm(classification).upper().replace(" ", "_")
    # Convenience aliases from UI
    aliases = {
        "CONFIRM_LOCAL_PHYSICAL": CONFIRM_LOCAL,
        "CONFIRM_PHYSICAL": CONFIRM_LOCAL,
        "CONFIRM_FOREIGN_CONTROLLER": CONFIRM_FOREIGN,
        "MARK_INTERNAL_LOGICAL": MARK_INTERNAL,
        "MARK_PROVEN_SPARE": MARK_SPARE,
        "CONFIRM_SAFETY_DEVICE": CONFIRM_SAFETY,
    }
    cls = aliases.get(cls, cls)

    target = _norm(controller) or _norm(machine)
    result = confirm_physical_device(
        canonical_device=canonical_device,
        classification=cls,
        controller=target,
        physical_endpoint=physical_endpoint,
        device_type=device_type,
        safety_classification=safety_classification,
        safety_zone=safety_zone,
        reason=reason or f"workbench:{cls}",
        confirmed_by=confirmed_by,
        conflict_acknowledged=conflict_acknowledged,
        store_path=store_path or default_store_path(REPO_ROOT),
    )
    if not result.get("ok"):
        return result

    # Refresh workbench slice for the device
    refreshed = None
    if machine:
        try:
            refreshed = get_item(canonical_device, machine=machine)
        except Exception:
            refreshed = None
    return {
        "ok": True,
        "status": result.get("status"),
        "confirmation": result.get("confirmation"),
        "path": result.get("path"),
        "knowledge_learn": result.get("knowledge_learn"),
        "refreshed_item": (refreshed or {}).get("item") if refreshed else None,
        "message": f"{canonical_device} → {result.get('status')}",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Engineering Review Workbench CLI")
    ap.add_argument("--machine", default="")
    ap.add_argument("--run-dir", default="")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--get", default="", help="canonical device name")
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--device", default="")
    ap.add_argument("--classification", default="")
    ap.add_argument("--controller", default="")
    ap.add_argument("--endpoint", default="")
    ap.add_argument("--device-type", default="")
    ap.add_argument("--safety-classification", default="")
    ap.add_argument("--safety-zone", default="")
    ap.add_argument("--reason", default="")
    ap.add_argument("--conflict-ack", action="store_true")
    ap.add_argument("--include-escalation", action="store_true")
    args = ap.parse_args()

    machine = args.machine
    if not machine:
        # Infer from active meta if present
        meta = REPO_ROOT / "workspace" / "active" / "meta.json"
        if meta.is_file():
            try:
                machine = json.loads(meta.read_text(encoding="utf-8")).get("machine") or ""
            except Exception:
                machine = ""
    machine = machine or "MSCRENOPICK"

    if args.confirm:
        out = apply_review_decision(
            canonical_device=args.device,
            classification=args.classification,
            machine=machine,
            controller=args.controller or machine,
            physical_endpoint=args.endpoint,
            device_type=args.device_type,
            safety_classification=args.safety_classification,
            safety_zone=args.safety_zone,
            reason=args.reason,
            conflict_acknowledged=args.conflict_ack,
        )
    elif args.get:
        out = get_item(args.get, machine=machine, run_dir=args.run_dir or None)
    else:
        out = build_workbench(
            machine=machine,
            run_dir=args.run_dir or None,
            include_escalation=args.include_escalation,
        )

    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

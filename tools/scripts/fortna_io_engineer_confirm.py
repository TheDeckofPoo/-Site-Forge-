#!/usr/bin/env python3
"""Durable engineer confirmation for physical I/O ownership/classification.

CONFIRM PHYSICAL DEVICE — not a blind ignore-validation switch.

Choices:
  CONFIRM:<controller>  → ENGINEER_CONFIRMED LOCAL on that controller
  CONFIRM_FOREIGN       → FOREIGN_CONTROLLER
  MARK_SPARE            → SPARE_UNUSED
  MARK_INTERNAL         → INTERNAL_LOGICAL (excluded from physical denominator)
  CONFIRM_SAFETY        → ENGINEER_CONFIRMED with optional safety fields
  CHANGE_DEVICE_TYPE    → ENGINEER_CONFIRMED + updated device_type
  ASSIGN_ENDPOINT       → ENGINEER_CONFIRMED LOCAL with physical_endpoint
  LEAVE_REVIEW          → remains ENGINEER_CONFIRM_REQUIRED / REVIEW_REQUIRED

Hard conflicts (duplicate endpoint, proven foreign ownership) require
conflict_acknowledged=True.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONFIRM_LOCAL = "CONFIRM_LOCAL"
CONFIRM_FOREIGN = "CONFIRM_FOREIGN"
MARK_SPARE = "MARK_SPARE"
MARK_INTERNAL = "MARK_INTERNAL"
CONFIRM_SAFETY = "CONFIRM_SAFETY"
CHANGE_DEVICE_TYPE = "CHANGE_DEVICE_TYPE"
ASSIGN_ENDPOINT = "ASSIGN_ENDPOINT"
LEAVE_REVIEW = "LEAVE_REVIEW"

STATUS_ENGINEER_CONFIRMED = "ENGINEER_CONFIRMED"
STATUS_FOREIGN = "FOREIGN_CONTROLLER"
STATUS_SPARE = "SPARE_UNUSED"
STATUS_INTERNAL_LOGICAL = "INTERNAL_LOGICAL"
STATUS_ENGINEER_REQUIRED = "ENGINEER_CONFIRM_REQUIRED"

_DEFAULT_NAME = "engineer_io_confirmations.json"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s: Any) -> str:
    return str(s or "").strip()


def default_store_path(repo_or_workspace: Path | str | None = None) -> Path:
    if repo_or_workspace:
        root = Path(repo_or_workspace)
        if (root / "workspace").is_dir():
            return root / "workspace" / _DEFAULT_NAME
        if root.name == "workspace" or root.is_dir():
            return root / _DEFAULT_NAME if root.name == "workspace" else root / "workspace" / _DEFAULT_NAME
    # Prefer CWD workspace
    cwd = Path.cwd()
    if (cwd / "workspace").is_dir():
        return cwd / "workspace" / _DEFAULT_NAME
    return cwd / _DEFAULT_NAME


def load_confirmations(path: Path | str | None = None) -> dict[str, Any]:
    p = Path(path) if path else default_store_path()
    if not p.is_file():
        return {"version": 1, "confirmations": {}, "path": str(p)}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "confirmations": {}, "path": str(p), "load_error": True}
    if not isinstance(data, dict):
        return {"version": 1, "confirmations": {}, "path": str(p)}
    data.setdefault("version", 1)
    data.setdefault("confirmations", {})
    data["path"] = str(p)
    return data


def save_confirmations(store: dict[str, Any], path: Path | str | None = None) -> Path:
    p = Path(path) if path else Path(store.get("path") or default_store_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "version": int(store.get("version") or 1),
        "updated_at": _ts(),
        "confirmations": store.get("confirmations") or {},
    }
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    store["path"] = str(p)
    return p


def lookup_confirmation(
    store: dict[str, Any], canonical_name: str
) -> dict[str, Any] | None:
    key = _norm(canonical_name).upper()
    confs = store.get("confirmations") or {}
    row = confs.get(key)
    return dict(row) if isinstance(row, dict) else None


def confirm_physical_device(
    *,
    canonical_device: str,
    classification: str,
    controller: str = "",
    physical_endpoint: str = "",
    reason: str = "",
    confirmed_by: str = "engineer",
    conflict_acknowledged: bool = False,
    proven_foreign: bool = False,
    duplicate_endpoint_owner: str = "",
    prior_status: str = "",
    evidence_snapshot: dict[str, Any] | None = None,
    store_path: Path | str | None = None,
    device_type: str = "",
    safety_classification: str = "",
    safety_zone: str = "",
) -> dict[str, Any]:
    """Record a controlled engineer confirmation.

    Returns {ok, status, confirmation, error?}.
    """
    name = _norm(canonical_device)
    if not name:
        return {"ok": False, "error": "canonical_device required"}

    cls = _norm(classification).upper().replace(" ", "_")
    # Accept CONFIRM:MSCRENOPICK / CONFIRM_MSCRENOPICK / CONFIRM_LOCAL
    target_controller = _norm(controller)
    if cls.startswith("CONFIRM:") or cls.startswith("CONFIRM_"):
        rest = cls.split(":", 1)[-1] if ":" in cls else cls[len("CONFIRM_") :]
        if rest in {
            "FOREIGN",
            "SAFETY",
            "LOCAL",
            "PHYSICAL_DEVICE",
            "",
        }:
            if rest == "FOREIGN":
                cls = CONFIRM_FOREIGN
            elif rest == "SAFETY":
                cls = CONFIRM_SAFETY
            else:
                cls = CONFIRM_LOCAL
        elif rest and rest not in {
            "LOCAL",
            "FOREIGN",
            "PHYSICAL_DEVICE",
            "SAFETY",
        }:
            # CONFIRM:<controller>
            target_controller = target_controller or rest
            cls = CONFIRM_LOCAL
    if cls in {"CONFIRM", "CONFIRM_PHYSICAL_DEVICE", "CONFIRM_PHYSICAL"}:
        cls = CONFIRM_LOCAL

    if proven_foreign and cls in {
        CONFIRM_LOCAL,
        CONFIRM_SAFETY,
        ASSIGN_ENDPOINT,
        CHANGE_DEVICE_TYPE,
    } and not conflict_acknowledged:
        return {
            "ok": False,
            "error": "proven_foreign_requires_conflict_acknowledged",
            "code": "CONFLICT_FOREIGN",
        }
    if duplicate_endpoint_owner and cls in {
        CONFIRM_LOCAL,
        CONFIRM_SAFETY,
        ASSIGN_ENDPOINT,
        CHANGE_DEVICE_TYPE,
    } and not conflict_acknowledged:
        return {
            "ok": False,
            "error": f"duplicate_endpoint_owned_by:{duplicate_endpoint_owner}",
            "code": "CONFLICT_ENDPOINT",
        }

    needs_controller = cls in {
        CONFIRM_LOCAL,
        CONFIRM_SAFETY,
        ASSIGN_ENDPOINT,
        CHANGE_DEVICE_TYPE,
    }
    if needs_controller and not target_controller:
        return {"ok": False, "error": f"controller required for {cls}"}

    if cls == ASSIGN_ENDPOINT and not _norm(physical_endpoint):
        return {"ok": False, "error": "physical_endpoint required for ASSIGN_ENDPOINT"}

    if cls == CHANGE_DEVICE_TYPE and not _norm(device_type):
        return {"ok": False, "error": "device_type required for CHANGE_DEVICE_TYPE"}

    dt = _norm(device_type)
    safety_cls = _norm(safety_classification)
    safety_zn = _norm(safety_zone)

    if cls == CONFIRM_LOCAL:
        final_status = STATUS_ENGINEER_CONFIRMED
        ownership = "LOCAL"
    elif cls == CONFIRM_FOREIGN:
        final_status = STATUS_FOREIGN
        ownership = "FOREIGN"
    elif cls == MARK_SPARE:
        final_status = STATUS_SPARE
        ownership = "LOCAL"
    elif cls == MARK_INTERNAL:
        final_status = STATUS_INTERNAL_LOGICAL
        ownership = "INTERNAL"
        dt = dt or "INTERNAL_LOGICAL"
    elif cls == CONFIRM_SAFETY:
        final_status = STATUS_ENGINEER_CONFIRMED
        ownership = "LOCAL"
        dt = dt or "SAFETY"
    elif cls == CHANGE_DEVICE_TYPE:
        final_status = STATUS_ENGINEER_CONFIRMED
        ownership = "LOCAL"
    elif cls == ASSIGN_ENDPOINT:
        final_status = STATUS_ENGINEER_CONFIRMED
        ownership = "LOCAL"
    elif cls == LEAVE_REVIEW:
        final_status = STATUS_ENGINEER_REQUIRED
        ownership = "UNKNOWN"
    else:
        return {"ok": False, "error": f"unknown classification:{classification}"}

    store = load_confirmations(store_path)
    confs = dict(store.get("confirmations") or {})
    row = {
        "canonical_device": name,
        "classification": cls,
        "controller": target_controller,
        "physical_endpoint": _norm(physical_endpoint),
        "ownership": ownership,
        "final_status": final_status,
        "reason": _norm(reason) or "engineer confirmation",
        "confirmed_by": _norm(confirmed_by) or "engineer",
        "confirmed_at": _ts(),
        "conflict_acknowledged": bool(conflict_acknowledged),
        "prior_status": _norm(prior_status),
        "evidence_snapshot": evidence_snapshot or {},
        "assignable": final_status == STATUS_ENGINEER_CONFIRMED,
        "device_type": dt,
        "safety_classification": safety_cls,
        "safety_zone": safety_zn,
        "evidence_class": (
            "INTERNAL_LOGICAL" if final_status == STATUS_INTERNAL_LOGICAL else ""
        ),
    }
    confs[name.upper()] = row
    store["confirmations"] = confs
    path = save_confirmations(store, store_path)

    # Best-effort knowledge capture — omit gracefully if module absent.
    learn_result = None
    try:
        from fortna_io_knowledge_base import learn_from_engineer_confirmation  # type: ignore

        learn_result = learn_from_engineer_confirmation(row)
    except Exception:
        learn_result = None

    out = {
        "ok": True,
        "status": final_status,
        "confirmation": row,
        "path": str(path),
    }
    if learn_result is not None:
        out["knowledge_learn"] = learn_result
    return out


def apply_confirmations_to_devices(
    devices: list[dict[str, Any]],
    store: dict[str, Any] | None = None,
    store_path: Path | str | None = None,
) -> dict[str, Any]:
    """Apply durable confirmations onto canonical device rows in-place."""
    st = store if store is not None else load_confirmations(store_path)
    applied = 0
    for d in devices:
        name = _norm(d.get("canonical_name") or d.get("canonical_device") or d.get("name"))
        conf = lookup_confirmation(st, name)
        if not conf:
            continue
        d["engineer_confirmation"] = conf
        d["final_status"] = conf.get("final_status") or d.get("final_status")
        d["ownership"] = conf.get("ownership") or d.get("ownership")
        if conf.get("physical_endpoint"):
            d["physical_endpoint"] = conf["physical_endpoint"]
        if conf.get("controller"):
            d["controller"] = conf["controller"]
        if conf.get("device_type"):
            d["device_type"] = conf["device_type"]
        if conf.get("evidence_class"):
            d["evidence_class"] = conf["evidence_class"]
        if conf.get("safety_classification"):
            d["safety_classification"] = conf["safety_classification"]
        if conf.get("safety_zone"):
            d["safety_zone"] = conf["safety_zone"]
        d["assignable"] = bool(conf.get("assignable"))
        d["confidence"] = "ENGINEER_CONFIRMED"
        d["reason"] = conf.get("reason") or d.get("reason")
        # Stamp engineer decision onto any prior escalation trace.
        trace = d.get("escalation_trace")
        if isinstance(trace, dict):
            trace["engineer_decision"] = {
                "classification": conf.get("classification"),
                "final_status": conf.get("final_status"),
                "confirmed_by": conf.get("confirmed_by"),
                "confirmed_at": conf.get("confirmed_at"),
                "reason": conf.get("reason"),
            }
        applied += 1
    return {
        "applied": applied,
        "store_path": st.get("path"),
        "total_confirmations": len(st.get("confirmations") or {}),
    }

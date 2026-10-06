#!/usr/bin/env python3
"""Durable engineer confirmation for physical I/O ownership/classification.

CONFIRM PHYSICAL DEVICE — not a blind ignore-validation switch.

Choices:
  CONFIRM:<controller>  → ENGINEER_CONFIRMED LOCAL on that controller
  CONFIRM_FOREIGN       → FOREIGN_CONTROLLER
  MARK_SPARE            → SPARE_UNUSED
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
LEAVE_REVIEW = "LEAVE_REVIEW"

STATUS_ENGINEER_CONFIRMED = "ENGINEER_CONFIRMED"
STATUS_FOREIGN = "FOREIGN_CONTROLLER"
STATUS_SPARE = "SPARE_UNUSED"
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
        if rest and rest not in {"LOCAL", "FOREIGN", "PHYSICAL_DEVICE"}:
            target_controller = target_controller or rest
            cls = CONFIRM_LOCAL
        elif rest == "FOREIGN":
            cls = CONFIRM_FOREIGN
        elif rest in {"LOCAL", "PHYSICAL_DEVICE", ""}:
            cls = CONFIRM_LOCAL
    if cls in {"CONFIRM", "CONFIRM_PHYSICAL_DEVICE", "CONFIRM_PHYSICAL"}:
        cls = CONFIRM_LOCAL

    if proven_foreign and cls == CONFIRM_LOCAL and not conflict_acknowledged:
        return {
            "ok": False,
            "error": "proven_foreign_requires_conflict_acknowledged",
            "code": "CONFLICT_FOREIGN",
        }
    if duplicate_endpoint_owner and cls == CONFIRM_LOCAL and not conflict_acknowledged:
        return {
            "ok": False,
            "error": f"duplicate_endpoint_owned_by:{duplicate_endpoint_owner}",
            "code": "CONFLICT_ENDPOINT",
        }
    if cls == CONFIRM_LOCAL and not target_controller:
        return {"ok": False, "error": "controller required for CONFIRM_LOCAL"}

    if cls == CONFIRM_LOCAL:
        final_status = STATUS_ENGINEER_CONFIRMED
        ownership = "LOCAL"
    elif cls == CONFIRM_FOREIGN:
        final_status = STATUS_FOREIGN
        ownership = "FOREIGN"
    elif cls == MARK_SPARE:
        final_status = STATUS_SPARE
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
    }
    confs[name.upper()] = row
    store["confirmations"] = confs
    path = save_confirmations(store, store_path)
    return {"ok": True, "status": final_status, "confirmation": row, "path": str(path)}


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
        d["assignable"] = bool(conf.get("assignable"))
        d["confidence"] = "ENGINEER_CONFIRMED"
        d["reason"] = conf.get("reason") or d.get("reason")
        applied += 1
    return {"applied": applied, "store_path": st.get("path"), "total_confirmations": len(st.get("confirmations") or {})}

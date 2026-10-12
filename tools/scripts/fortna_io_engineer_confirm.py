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
APPLY_DECISION = "APPLY_DECISION"

# Actions that compose with a prior durable confirmation instead of wiping fields.
_COMPOSING_ACTIONS = frozenset(
    {
        CONFIRM_LOCAL,
        CONFIRM_SAFETY,
        CHANGE_DEVICE_TYPE,
        ASSIGN_ENDPOINT,
        APPLY_DECISION,
    }
)

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
    ownership_choice: str = "",
) -> dict[str, Any]:
    """Record a controlled engineer confirmation.

    Successive composing actions (CONFIRM_LOCAL → CONFIRM_SAFETY, etc.) merge
    with the prior durable row so endpoint / type / Safety role are preserved.

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

    dt = _norm(device_type)
    safety_cls = _norm(safety_classification)
    safety_zn = _norm(safety_zone)
    endpoint_in = _norm(physical_endpoint)
    own_choice = _norm(ownership_choice).upper().replace(" ", "_")

    # Coherent single-submit decision → concrete classification.
    if cls == APPLY_DECISION:
        if own_choice in {"FOREIGN", "FOREIGN_CONTROLLER"}:
            cls = CONFIRM_FOREIGN
        elif own_choice in {"INTERNAL", "INTERNAL_LOGICAL"}:
            cls = MARK_INTERNAL
        elif own_choice in {"SPARE", "SPARE_UNUSED"}:
            cls = MARK_SPARE
        elif own_choice in {"LEAVE", "LEAVE_REVIEW", "REVIEW"}:
            cls = LEAVE_REVIEW
        elif (
            own_choice in {"SAFETY", "LOCAL_SAFETY"}
            or safety_cls
            or dt.upper()
            in {"ESPB", "ESLS", "ESR", "MCR", "SAFETY", "ESTOP"}
        ):
            cls = CONFIRM_SAFETY
        else:
            cls = CONFIRM_LOCAL

    if proven_foreign and cls in {
        CONFIRM_LOCAL,
        CONFIRM_SAFETY,
        ASSIGN_ENDPOINT,
        CHANGE_DEVICE_TYPE,
        APPLY_DECISION,
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
        APPLY_DECISION,
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

    if cls == ASSIGN_ENDPOINT and not endpoint_in:
        return {"ok": False, "error": "physical_endpoint required for ASSIGN_ENDPOINT"}

    if cls == CHANGE_DEVICE_TYPE and not dt:
        return {"ok": False, "error": "device_type required for CHANGE_DEVICE_TYPE"}

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
    elif cls == CONFIRM_SAFETY:
        final_status = STATUS_ENGINEER_CONFIRMED
        ownership = "LOCAL"
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
    prior = confs.get(name.upper()) if isinstance(confs.get(name.upper()), dict) else {}

    # Compose, do not silently erase earlier valid properties on successive actions.
    # CONFIRM_LOCAL then CONFIRM_SAFETY must keep endpoint / ownership / type.
    if cls in _COMPOSING_ACTIONS and prior:
        if not endpoint_in:
            endpoint_in = _norm(prior.get("physical_endpoint"))
        if not dt:
            dt = _norm(prior.get("device_type"))
        if not safety_cls:
            safety_cls = _norm(prior.get("safety_classification"))
        if not safety_zn:
            safety_zn = _norm(prior.get("safety_zone"))
        if not target_controller:
            target_controller = _norm(prior.get("controller"))
        # Keep SAFETY device_type once established when a later LOCAL confirm omits it.
        if cls == CONFIRM_LOCAL and _norm(prior.get("device_type")).upper() in {
            "ESPB",
            "ESLS",
            "ESR",
            "MCR",
            "SAFETY",
            "ESTOP",
        }:
            dt = dt or _norm(prior.get("device_type"))
            safety_cls = safety_cls or _norm(prior.get("safety_classification"))

    # Defaults only after compose so prior ESPB/ESLS is not wiped by "SAFETY".
    if cls == MARK_INTERNAL:
        dt = dt or "INTERNAL_LOGICAL"
    elif cls == CONFIRM_SAFETY:
        dt = dt or "SAFETY"

    history = list(prior.get("classification_history") or []) if prior else []
    if prior.get("classification"):
        history.append(
            {
                "classification": prior.get("classification"),
                "final_status": prior.get("final_status"),
                "confirmed_at": prior.get("confirmed_at"),
                "physical_endpoint": prior.get("physical_endpoint"),
                "device_type": prior.get("device_type"),
                "safety_classification": prior.get("safety_classification"),
                "safety_zone": prior.get("safety_zone"),
                "reason": prior.get("reason"),
            }
        )

    row = {
        "canonical_device": name,
        "classification": cls,
        "controller": target_controller,
        "physical_endpoint": endpoint_in,
        "ownership": ownership,
        "final_status": final_status,
        "reason": _norm(reason) or "engineer confirmation",
        "confirmed_by": _norm(confirmed_by) or "engineer",
        "confirmed_at": _ts(),
        "conflict_acknowledged": bool(conflict_acknowledged),
        "prior_status": _norm(prior_status) or _norm(prior.get("final_status")),
        "evidence_snapshot": evidence_snapshot or prior.get("evidence_snapshot") or {},
        "assignable": final_status == STATUS_ENGINEER_CONFIRMED,
        "device_type": dt,
        "safety_classification": safety_cls,
        "safety_zone": safety_zn,
        "evidence_class": (
            "INTERNAL_LOGICAL" if final_status == STATUS_INTERNAL_LOGICAL else ""
        ),
        "classification_history": history[-12:],
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


_SAFETY_DEVICE_TYPES = frozenset(
    {"ESPB", "ESLS", "ESR", "MCR", "SAFETY", "ESTOP", "CS"}
)


def _is_safety_confirmation(conf: dict[str, Any]) -> bool:
    dt = _norm(conf.get("device_type") or conf.get("safety_classification")).upper()
    if dt in _SAFETY_DEVICE_TYPES:
        return True
    name = _norm(conf.get("canonical_device")).upper()
    return bool(
        name.startswith("ESPB")
        or name.startswith("ESLS")
        or name.startswith("ESR")
        or name.startswith("MCR")
        or name.startswith("ESSTOP")
        or name.startswith("ES_")
    )


def apply_confirmations_to_safety_devices(
    devices: list[dict[str, Any]],
    store: dict[str, Any] | None = None,
    store_path: Path | str | None = None,
    *,
    inject_missing: bool = True,
    active_machine: str = "",
) -> dict[str, Any]:
    """Stamp engineer I/O confirmations onto Safety inventory rows.

    ENGINEER_CONFIRMED LOCAL + Safety + endpoint → assignable LOCAL_PHYSICAL.
    FOREIGN / INTERNAL / GUI_ONLY remain non-assignable with visible reason.
    When inject_missing=True, confirmed Safety devices absent from discovery are
    appended so Safety Build can consume them after refresh (no re-import).
    """
    st = store if store is not None else load_confirmations(store_path)
    confs = st.get("confirmations") or {}
    by_name: dict[str, dict[str, Any]] = {}
    for d in devices:
        key = _norm(
            d.get("name") or d.get("canonicalTag") or d.get("canonical_name") or d.get("id")
        ).upper()
        if key:
            by_name[key] = d

    applied = 0
    injected = 0
    mach = _norm(active_machine)

    for key, conf in confs.items():
        if not isinstance(conf, dict):
            continue
        name = _norm(conf.get("canonical_device") or key)
        name_u = name.upper()
        fs = _norm(conf.get("final_status")).upper()
        ownership = _norm(conf.get("ownership")).upper()
        endpoint = _norm(conf.get("physical_endpoint"))
        reason = _norm(conf.get("reason")) or fs
        ctrl = _norm(conf.get("controller")) or mach
        dt = _norm(conf.get("device_type") or conf.get("safety_classification")) or "SAFETY"

        row = by_name.get(name_u)
        if row is None:
            if not inject_missing or not _is_safety_confirmation(conf):
                continue
            if fs not in {STATUS_ENGINEER_CONFIRMED, STATUS_FOREIGN, STATUS_INTERNAL_LOGICAL}:
                continue
            row = {
                "id": name,
                "name": name,
                "canonicalTag": name,
                "kind": dt.upper() if dt.upper() in _SAFETY_DEVICE_TYPES else "OTHER",
                "stem": name,
                "signals": [],
                "signalNames": [],
                "status": "UNASSIGNED",
                "origin": "ENGINEER_CONFIRMATION",
                "sources": ["engineer_io_confirmations"],
            }
            devices.append(row)
            by_name[name_u] = row
            injected += 1

        row["engineer_confirmation"] = conf
        if endpoint:
            row["physicalEndpoint"] = endpoint
            row["physical_endpoint"] = endpoint
        if ctrl:
            row["machine"] = ctrl
            row["controller"] = ctrl
        if dt:
            row["device_type"] = dt
            if not row.get("kind") or str(row.get("kind")).upper() in {"", "OTHER"}:
                row["kind"] = dt.upper() if dt.upper() in _SAFETY_DEVICE_TYPES else row.get("kind")
        if conf.get("safety_classification"):
            row["safety_classification"] = conf.get("safety_classification")
        if conf.get("safety_zone"):
            row["safety_zone"] = conf.get("safety_zone")

        if fs == STATUS_FOREIGN or ownership == "FOREIGN":
            row["assignable"] = False
            row["inventory_scope"] = "UNRELATED_FOREIGN"
            row["machine_ownership"] = "FOREIGN"
            row["status"] = "REVIEW_REQUIRED"
            row["review_reason"] = (
                f"FOREIGN_CONTROLLER — {ctrl}" if ctrl else "FOREIGN_CONTROLLER"
            )
            row["non_assignable_reason"] = (
                f"FOREIGN_CONTROLLER — {ctrl or 'peer'} · Not assignable to "
                f"{mach or 'local'} Safety zone"
            )
        elif fs == STATUS_INTERNAL_LOGICAL or ownership == "INTERNAL":
            row["assignable"] = False
            row["inventory_scope"] = "UNRELATED_FOREIGN"
            row["machine_ownership"] = "INTERNAL"
            row["status"] = "REVIEW_REQUIRED"
            row["review_reason"] = "INTERNAL_LOGICAL"
            row["non_assignable_reason"] = "INTERNAL_LOGICAL · No physical endpoint"
            row["evidence_class"] = "INTERNAL_LOGICAL"
        elif fs == STATUS_ENGINEER_CONFIRMED and ownership == "LOCAL":
            row["inventory_scope"] = "LOCAL_PHYSICAL"
            row["machine_ownership"] = "LOCAL_PHYSICAL"
            row["evidence_class"] = row.get("evidence_class") or "PHYSICAL_FIELD_DEVICE"
            has_ep = bool(endpoint or _norm(row.get("physicalEndpoint")))
            if has_ep and _is_safety_confirmation(conf):
                row["assignable"] = True
                if str(row.get("status") or "").upper() in {
                    "",
                    "REVIEW_REQUIRED",
                    "GROUPED",
                }:
                    row["status"] = "UNASSIGNED"
                row["review_reason"] = None
                row["non_assignable_reason"] = None
            elif not has_ep:
                row["assignable"] = False
                row["review_reason"] = row.get("review_reason") or "NO_PHYSICAL_ENDPOINT"
                row["non_assignable_reason"] = (
                    "ENGINEER_CONFIRMED LOCAL but no physical endpoint yet"
                )
        applied += 1

    return {
        "applied": applied,
        "injected": injected,
        "store_path": st.get("path"),
        "total_confirmations": len(confs),
    }

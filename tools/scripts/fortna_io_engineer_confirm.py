#!/usr/bin/env python3
"""Durable engineer confirmation for physical I/O ownership/classification.

CONFIRM PHYSICAL DEVICE — not a blind ignore-validation switch.

Identity / scope (P0):
  An engineer confirmation NEVER applies merely because the device name matches.
  Durable key: site | controller | canonical device name
  Plus an evidence fingerprint (RUN hash, word/bit, Configio, endpoint, class).

Load rule:
  Apply only when site, controller, and canonical device match AND the evidence
  fingerprint is still compatible with current discovery.

  Cross-controller confirmations MUST NOT APPLY (peer history only).
  Legacy name-only / unscoped records MUST NOT AUTO-APPLY
  (STALE_LEGACY_CONFIRMATION / REVIEW_REQUIRED).

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

import hashlib
import json
import shutil
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
STATUS_STALE_LEGACY = "STALE_LEGACY_CONFIRMATION"
STATUS_STALE_EVIDENCE = "STALE_EVIDENCE"
STATUS_REVIEW_REQUIRED = "REVIEW_REQUIRED"

STORE_VERSION = 2

_DEFAULT_NAME = "engineer_io_confirmations.json"
_LEGACY_BACKUP_NAME = "engineer_io_confirmations.legacy_v1_backup.json"

# Explicit exclusion: legacy / unrevalidated confirmations must never contribute
# to physical-resolution metrics, Safety assignability, or generated I/O.
_METRICS_EXCLUSION_FLAGS = {
    "metrics_eligible": False,
    "counts_toward_physical_resolution": False,
    "counts_toward_safety_assignability": False,
    "counts_toward_generated_io": False,
    "requires_scoped_revalidation": True,
}

# Known role suffixes used only for NEW-write site derivation from controller.
# Never used to invent scope for legacy unscoped records.
_ROLE_SUFFIXES = (
    "PICK",
    "SHIP",
    "PACK",
    "SORT",
    "INDUCT",
    "LOOP",
    "RECV",
    "RECEIVE",
    "SHIPPING",
    "PACKING",
    "PICKING",
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _norm_u(s: Any) -> str:
    return _norm(s).upper()


def derive_site_from_controller(controller: str, site: str = "") -> str:
    """Derive site for NEW writes only. Never invent scope for legacy rows.

    MSCRENOPICK / MSCRENOSHIP / MSCRENOPACK → MSCRENO
    Controllers without a known role suffix keep the controller as site.
    Explicit site argument always wins.
    """
    explicit = _norm_u(site)
    if explicit:
        return explicit
    ctrl = _norm_u(controller)
    if not ctrl:
        return ""
    for suf in _ROLE_SUFFIXES:
        if ctrl.endswith(suf) and len(ctrl) > len(suf):
            return ctrl[: -len(suf)]
    return ctrl


def make_scope_key(
    site: str,
    controller: str,
    canonical_device: str,
) -> str:
    """Durable confirmation identity: site|controller|canonical."""
    return "|".join(
        [
            _norm_u(site) or _norm_u(derive_site_from_controller(controller)),
            _norm_u(controller),
            _norm_u(canonical_device),
        ]
    )


def parse_scope_key(key: str) -> dict[str, str]:
    parts = str(key or "").split("|")
    if len(parts) == 3 and all(parts):
        return {
            "site": parts[0].upper(),
            "controller": parts[1].upper(),
            "canonical_device": parts[2].upper(),
            "scoped": True,
        }
    return {
        "site": "",
        "controller": "",
        "canonical_device": _norm_u(key),
        "scoped": False,
    }


def is_scoped_key(key: str) -> bool:
    return bool(parse_scope_key(key).get("scoped"))


def build_evidence_fingerprint(
    *,
    run_hash: str = "",
    raw_word: Any = "",
    raw_bit: Any = "",
    parsed_bit: Any = "",
    configio_evidence: str = "",
    endpoint: str = "",
    module: str = "",
    evidence_class: str = "",
    ownership: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persistable evidence fingerprint for stale detection."""
    fp: dict[str, Any] = {
        "run_hash": _norm(run_hash),
        "raw_word": _norm(raw_word),
        "raw_bit": _norm(raw_bit),
        "parsed_bit": _norm(parsed_bit),
        "configio_evidence": _norm(configio_evidence),
        "endpoint": _norm(endpoint),
        "module": _norm(module),
        "evidence_class": _norm_u(evidence_class),
        "ownership": _norm_u(ownership),
    }
    if extra and isinstance(extra, dict):
        for k, v in extra.items():
            if k not in fp and v not in (None, ""):
                fp[str(k)] = v
    # Compact digest for equality checks when all material fields present.
    material = "|".join(
        [
            fp["run_hash"],
            fp["raw_word"],
            fp["raw_bit"],
            fp["parsed_bit"],
            fp["configio_evidence"],
            fp["endpoint"],
            fp["module"],
            fp["evidence_class"],
            fp["ownership"],
        ]
    )
    fp["digest"] = (
        hashlib.sha1(material.encode("utf-8")).hexdigest()[:16] if material.strip("|") else ""
    )
    return fp


def fingerprint_from_device(device: dict[str, Any] | None) -> dict[str, Any]:
    """Extract a fingerprint from a live device / evidence row."""
    if not isinstance(device, dict):
        return build_evidence_fingerprint()
    snap = device.get("evidence_snapshot") if isinstance(device.get("evidence_snapshot"), dict) else {}
    return build_evidence_fingerprint(
        run_hash=_norm(
            device.get("run_hash")
            or device.get("run_id")
            or snap.get("run_hash")
            or snap.get("run_id")
        ),
        raw_word=device.get("word") or device.get("raw_word") or snap.get("word") or snap.get("raw_word"),
        raw_bit=device.get("bit") or device.get("raw_bit") or snap.get("bit") or snap.get("raw_bit"),
        parsed_bit=device.get("parsed_bit") or snap.get("parsed_bit"),
        configio_evidence=_norm(
            device.get("configio_evidence")
            or device.get("active_configio")
            or snap.get("configio_evidence")
        ),
        endpoint=_norm(
            device.get("physical_endpoint")
            or device.get("physicalEndpoint")
            or snap.get("endpoint")
            or snap.get("physical_endpoint")
        ),
        module=_norm(device.get("module") or snap.get("module")),
        evidence_class=_norm(
            device.get("evidence_class") or snap.get("evidence_class")
        ),
        ownership=_norm(device.get("ownership") or device.get("machine_ownership")),
    )


def fingerprint_compatible(
    stored: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> bool:
    """True when current evidence has not materially diverged from the confirmation.

    Empty stored fingerprint → compatible only when current also has no material
    fields (new confirmation with no evidence yet). If stored has material fields
    and current contradicts them, incompatible → STALE_EVIDENCE.
    """
    if not isinstance(stored, dict):
        stored = {}
    if not isinstance(current, dict):
        current = {}

    # Material fields force stale only when BOTH sides present and disagree.
    # Empty / UNKNOWN / REVIEW current values do not invalidate a stored
    # fingerprint (device rows often omit optional evidence until later stages,
    # and pre-confirmation ownership is frequently UNKNOWN).
    _non_material_current = {
        "",
        "UNKNOWN",
        "REVIEW",
        "REVIEW_REQUIRED",
        "ENGINEER_CONFIRM_REQUIRED",
        "UNRESOLVED",
    }
    checks = (
        "run_hash",
        "raw_word",
        "raw_bit",
        "parsed_bit",
        "configio_evidence",
        "endpoint",
        "module",
        "evidence_class",
        "ownership",
    )
    for field in checks:
        s = _norm_u(stored.get(field))
        c = _norm_u(current.get(field))
        if not s or not c:
            continue
        if c in _non_material_current:
            continue
        if s != c:
            return False
    return True


def default_store_path(repo_or_workspace: Path | str | None = None) -> Path:
    if repo_or_workspace:
        root = Path(repo_or_workspace)
        if (root / "workspace").is_dir():
            return root / "workspace" / _DEFAULT_NAME
        if root.name == "workspace" or root.is_dir():
            return root / _DEFAULT_NAME if root.name == "workspace" else root / "workspace" / _DEFAULT_NAME
    cwd = Path.cwd()
    if (cwd / "workspace").is_dir():
        return cwd / "workspace" / _DEFAULT_NAME
    return cwd / _DEFAULT_NAME


def _legacy_backup_path(store_path: Path) -> Path:
    """Stable alias kept for older callers; prefer timestamped backups."""
    return store_path.with_name(_LEGACY_BACKUP_NAME)


def _timestamped_backup_path(store_path: Path, when: datetime | None = None) -> Path:
    ts = (when or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return store_path.with_name(f"engineer_io_confirmations.backup_{ts}.json")


def write_confirmation_backup(
    store_path: Path,
    *,
    reason: str = "pre_migration",
) -> Path | None:
    """Preserve a timestamped copy of the live store before rewriting.

    Always writes a unique timestamped file. Also refreshes the stable
    ``legacy_v1_backup`` alias when it does not yet exist.
    """
    p = Path(store_path)
    if not p.is_file():
        return None
    stamped = _timestamped_backup_path(p)
    shutil.copy2(p, stamped)
    alias = _legacy_backup_path(p)
    if not alias.is_file():
        shutil.copy2(p, alias)
    meta = {
        "backup_path": str(stamped),
        "alias_path": str(alias) if alias.is_file() else "",
        "reason": reason,
        "backed_up_at": _ts(),
        "source_path": str(p),
        "source_bytes": p.stat().st_size,
    }
    meta_path = stamped.with_suffix(stamped.suffix + ".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return stamped


def _infer_original_final_status(row: dict[str, Any]) -> str:
    """Recover the pre-stale decision status from preserved fields."""
    fs = _norm_u(row.get("original_final_status") or row.get("final_status"))
    if fs and fs not in {STATUS_STALE_LEGACY, STATUS_STALE_EVIDENCE, STATUS_REVIEW_REQUIRED}:
        return fs
    ownership = _norm_u(row.get("ownership"))
    classification = _norm_u(row.get("classification"))
    if ownership == "FOREIGN" or classification == CONFIRM_FOREIGN:
        return STATUS_FOREIGN
    if ownership == "INTERNAL" or classification == MARK_INTERNAL:
        return STATUS_INTERNAL_LOGICAL
    if classification == MARK_SPARE or ownership == "SPARE":
        return STATUS_SPARE
    if classification in {
        CONFIRM_LOCAL,
        CONFIRM_SAFETY,
        ASSIGN_ENDPOINT,
        CHANGE_DEVICE_TYPE,
    } or ownership == "LOCAL":
        return STATUS_ENGINEER_CONFIRMED
    return fs or STATUS_ENGINEER_REQUIRED


def _legacy_decision_snapshot(row: dict[str, Any], key: str) -> dict[str, Any]:
    """Preserve the historical decision fields Curtis required for audit."""
    device = _norm(
        row.get("canonical_device")
        or parse_scope_key(key).get("canonical_device")
        or key.replace("legacy:", "")
    )
    return {
        "canonical_device": device,
        "controller": _norm(row.get("controller")),
        "site": _norm(row.get("site")),
        "classification": _norm(row.get("classification")),
        "decision": _norm(row.get("classification")),
        "original_final_status": _infer_original_final_status(row),
        "ownership": _norm(row.get("ownership")),
        "physical_endpoint": _norm(row.get("physical_endpoint")),
        "endpoint": _norm(row.get("physical_endpoint")),
        "reason": _norm(row.get("reason")),
        "device_type": _norm(row.get("device_type")),
        "safety_classification": _norm(row.get("safety_classification")),
        "safety_zone": _norm(row.get("safety_zone")),
        "confirmed_by": _norm(row.get("confirmed_by")),
        "confirmed_at": _norm(row.get("confirmed_at")),
        "legacy_key": _norm(row.get("legacy_key") or key),
        "evidence_snapshot": row.get("evidence_snapshot")
        if isinstance(row.get("evidence_snapshot"), dict)
        else {},
    }


def confirmation_is_metrics_eligible(conf: dict[str, Any] | None) -> bool:
    """Legacy / stale confirmations never count toward physical/Safety/generated I/O."""
    if not isinstance(conf, dict):
        return False
    if conf.get("metrics_eligible") is False:
        return False
    if conf.get("read_only") is True and _norm_u(conf.get("scope_status")) in {
        STATUS_STALE_LEGACY,
        STATUS_STALE_EVIDENCE,
        "LEGACY_UNSCOPED",
    }:
        return False
    scope = _norm_u(conf.get("scope_status") or conf.get("apply_status"))
    if scope in {STATUS_STALE_LEGACY, STATUS_STALE_EVIDENCE, "LEGACY_UNSCOPED", "PEER_HISTORY"}:
        return False
    if conf.get("requires_scoped_revalidation") is True and scope != "SCOPED":
        return False
    if not _norm(conf.get("scope_key")) and not (
        _norm(conf.get("site")) and _norm(conf.get("controller"))
    ):
        return False
    # Active scoped confirmations may count only after apply sets ENGINEER_CONFIRMED
    # from a non-stale row — callers still gate on final_status.
    return scope in {"", "SCOPED", "APPLICABLE"}


def _row_is_legacy_unscoped(key: str, row: dict[str, Any]) -> bool:
    """True when the record lacks adequate site|controller scope."""
    if not is_scoped_key(key):
        return True
    site = _norm_u(row.get("site"))
    ctrl = _norm_u(row.get("controller"))
    if not site or not ctrl:
        return True
    if _norm_u(row.get("scope_status")) in {
        STATUS_STALE_LEGACY,
        "LEGACY_UNSCOPED",
    }:
        return True
    return False


def _mark_stale_legacy(row: dict[str, Any], key: str) -> dict[str, Any]:
    """Convert a name-only row to STALE_LEGACY without discarding history.

    Preserves device, controller, decision, endpoint, and reason in
    ``legacy_decision_snapshot`` and ``classification_history``.
    """
    snapshot = _legacy_decision_snapshot(row, key)
    out = dict(row)
    history = list(out.get("classification_history") or [])
    history.append(
        {
            "event": "MIGRATED_TO_STALE_LEGACY",
            "migrated_at": _ts(),
            "canonical_device": snapshot["canonical_device"],
            "controller": snapshot["controller"],
            "classification": snapshot["classification"],
            "decision": snapshot["decision"],
            "original_final_status": snapshot["original_final_status"],
            "physical_endpoint": snapshot["physical_endpoint"],
            "endpoint": snapshot["endpoint"],
            "reason": snapshot["reason"],
            "ownership": snapshot["ownership"],
            "device_type": snapshot["device_type"],
            "safety_zone": snapshot["safety_zone"],
            "confirmed_at": snapshot["confirmed_at"],
            "confirmed_by": snapshot["confirmed_by"],
            "legacy_key": snapshot["legacy_key"],
        }
    )
    out["legacy_decision_snapshot"] = snapshot
    out["original_final_status"] = snapshot["original_final_status"]
    out["original_classification"] = snapshot["classification"]
    out["original_ownership"] = snapshot["ownership"]
    out["original_physical_endpoint"] = snapshot["physical_endpoint"]
    out["original_reason"] = snapshot["reason"]
    out["original_controller"] = snapshot["controller"]
    out["original_canonical_device"] = snapshot["canonical_device"]
    out["classification_history"] = history[-20:]
    out["scope_status"] = STATUS_STALE_LEGACY
    out["apply_status"] = STATUS_STALE_LEGACY
    out["final_status"] = STATUS_REVIEW_REQUIRED
    out["assignable"] = False
    out.update(_METRICS_EXCLUSION_FLAGS)
    out["stale_reason"] = (
        "LEGACY_UNSCOPED — name-only confirmation; missing durable "
        "site|controller scope. Must not auto-apply. Must not count toward "
        "physical-resolution metrics, Safety assignability, or generated I/O "
        "until revalidated under scoped identity. Re-confirm under current "
        "controller evidence."
    )
    out["legacy_key"] = snapshot["legacy_key"]
    out["read_only"] = True
    out.setdefault(
        "canonical_device",
        snapshot["canonical_device"] or parse_scope_key(key).get("canonical_device") or key,
    )
    return out


def enrich_legacy_confirmations(store: dict[str, Any]) -> dict[str, Any]:
    """Backfill snapshot / metrics-exclusion fields on already-migrated legacy rows."""
    legacy = dict(store.get("legacy_confirmations") or {})
    changed = 0
    for key, row in list(legacy.items()):
        if not isinstance(row, dict):
            continue
        if row.get("legacy_decision_snapshot") and row.get("metrics_eligible") is False:
            # Still force exclusion flags in case an older enrich missed one.
            before = {k: row.get(k) for k in _METRICS_EXCLUSION_FLAGS}
            row.update(_METRICS_EXCLUSION_FLAGS)
            row["assignable"] = False
            row["read_only"] = True
            if before != {k: row.get(k) for k in _METRICS_EXCLUSION_FLAGS}:
                changed += 1
            legacy[key] = row
            continue
        legacy[key] = _mark_stale_legacy(row, key)
        changed += 1
    store["legacy_confirmations"] = legacy
    if changed:
        mig = dict(store.get("migration") or {})
        mig["legacy_enriched_at"] = _ts()
        mig["legacy_enriched_count"] = changed
        mig["metrics_exclusion"] = (
            "Legacy confirmations never count toward physical-resolution, "
            "Safety assignability, or generated I/O until scoped revalidation."
        )
        store["migration"] = mig
    return store


def migrate_store_to_scoped(store: dict[str, Any]) -> dict[str, Any]:
    """Migrate name-keyed / unscoped rows → legacy_confirmations (STALE).

    Does NOT guess missing site/controller to promote a legacy row into active
    confirmations. Historical rows are preserved read-only with full decision
    snapshots. Legacy rows never count toward physical/Safety/generated metrics.
    """
    version = int(store.get("version") or 1)
    confs_in = dict(store.get("confirmations") or {})
    legacy_in = dict(store.get("legacy_confirmations") or {})
    active: dict[str, Any] = {}
    legacy: dict[str, Any] = dict(legacy_in)
    migrated = 0

    for key, row in confs_in.items():
        if not isinstance(row, dict):
            continue
        if _row_is_legacy_unscoped(key, row):
            # Preserve under original key in legacy bucket; do not invent scope.
            stale = _mark_stale_legacy(row, key)
            legacy_key = f"legacy:{_norm_u(key)}"
            if legacy_key not in legacy:
                legacy[legacy_key] = stale
                migrated += 1
            else:
                # Prefer richer snapshot if an older stale row lacked it.
                existing = legacy[legacy_key]
                if not isinstance(existing, dict) or not existing.get("legacy_decision_snapshot"):
                    legacy[legacy_key] = stale
            continue
        # Already scoped — keep active, ensure site field present.
        parsed = parse_scope_key(key)
        row = dict(row)
        row.setdefault("site", parsed["site"] or derive_site_from_controller(row.get("controller", "")))
        row.setdefault("scope_key", key)
        row.setdefault("scope_status", "SCOPED")
        row.setdefault("metrics_eligible", True)
        row.setdefault("requires_scoped_revalidation", False)
        row.setdefault(
            "evidence_fingerprint",
            row.get("evidence_fingerprint")
            or build_evidence_fingerprint(
                endpoint=_norm(row.get("physical_endpoint")),
                evidence_class=_norm(row.get("evidence_class")),
                ownership=_norm(row.get("ownership")),
            ),
        )
        active[key] = row

    store["version"] = max(version, STORE_VERSION)
    store["confirmations"] = active
    store["legacy_confirmations"] = legacy
    store = enrich_legacy_confirmations(store)
    store["migration"] = {
        "migrated_legacy_count": migrated,
        "active_count": len(active),
        "legacy_count": len(store.get("legacy_confirmations") or {}),
        "migrated_at": _ts(),
        "backup_policy": "timestamped + stable legacy_v1_backup alias; never delete history",
        "metrics_exclusion": (
            "Legacy confirmations never count toward physical-resolution, "
            "Safety assignability, or generated I/O until scoped revalidation."
        ),
        "note": (
            "Legacy name-only confirmations moved to legacy_confirmations as "
            "STALE_LEGACY_CONFIRMATION with full decision snapshots. They never "
            "auto-apply and never count toward metrics until re-confirmed under "
            "site|controller|device scope with current evidence."
        ),
    }
    return store


def load_confirmations(path: Path | str | None = None) -> dict[str, Any]:
    p = Path(path) if path else default_store_path()
    if not p.is_file():
        return {
            "version": STORE_VERSION,
            "confirmations": {},
            "legacy_confirmations": {},
            "path": str(p),
        }
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {
            "version": STORE_VERSION,
            "confirmations": {},
            "legacy_confirmations": {},
            "path": str(p),
            "load_error": True,
        }
    if not isinstance(data, dict):
        return {
            "version": STORE_VERSION,
            "confirmations": {},
            "legacy_confirmations": {},
            "path": str(p),
        }
    data.setdefault("confirmations", {})
    data.setdefault("legacy_confirmations", {})
    data["path"] = str(p)

    # Auto-migrate v1 / name-keyed stores in memory (and persist if dirty).
    needs_migrate = int(data.get("version") or 1) < STORE_VERSION or any(
        not is_scoped_key(k) for k in (data.get("confirmations") or {})
    )
    dirty = False
    if needs_migrate:
        try:
            backup = write_confirmation_backup(p, reason="pre_migration_v1_to_scoped")
            if backup is not None:
                data["legacy_backup_path"] = str(backup)
                data["legacy_backup_alias"] = str(_legacy_backup_path(p))
        except Exception:
            pass
        data = migrate_store_to_scoped(data)
        dirty = True
    else:
        data.setdefault("version", STORE_VERSION)
        before = json.dumps(data.get("legacy_confirmations") or {}, sort_keys=True, default=str)
        data = enrich_legacy_confirmations(data)
        after = json.dumps(data.get("legacy_confirmations") or {}, sort_keys=True, default=str)
        dirty = before != after

    if dirty:
        try:
            save_confirmations(data, p)
        except Exception:
            pass
    return data


def save_confirmations(store: dict[str, Any], path: Path | str | None = None) -> Path:
    p = Path(path) if path else Path(store.get("path") or default_store_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "version": int(store.get("version") or STORE_VERSION),
        "updated_at": _ts(),
        "confirmations": store.get("confirmations") or {},
        "legacy_confirmations": store.get("legacy_confirmations") or {},
    }
    if store.get("migration"):
        out["migration"] = store["migration"]
    if store.get("legacy_backup_path"):
        out["legacy_backup_path"] = store["legacy_backup_path"]
    if store.get("legacy_backup_alias"):
        out["legacy_backup_alias"] = store["legacy_backup_alias"]
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    store["path"] = str(p)
    return p


def lookup_confirmation(
    store: dict[str, Any],
    canonical_name: str,
    *,
    site: str = "",
    controller: str = "",
    current_fingerprint: dict[str, Any] | None = None,
    allow_legacy: bool = False,
) -> dict[str, Any] | None:
    """Return an applicable confirmation for site|controller|device.

    Without site+controller, returns None (name-only lookup is forbidden for apply).
    Cross-controller matches are never returned as applicable.
    Legacy unscoped rows are never returned unless allow_legacy=True (peer/history).
    """
    name = _norm_u(canonical_name)
    if not name:
        return None
    ctrl = _norm_u(controller)
    site_u = _norm_u(site) or (_norm_u(derive_site_from_controller(ctrl)) if ctrl else "")
    confs = store.get("confirmations") or {}

    if not site_u or not ctrl:
        # Name-only apply is forbidden. Optional peer/history via allow_legacy.
        if not allow_legacy:
            return None
        return _peer_or_legacy_history(store, name)

    key = make_scope_key(site_u, ctrl, name)
    row = confs.get(key)
    if isinstance(row, dict):
        if _norm_u(row.get("scope_status")) in {STATUS_STALE_LEGACY, STATUS_STALE_EVIDENCE}:
            return None if not allow_legacy else dict(row)
        if not confirmation_is_metrics_eligible(row) and _norm_u(row.get("scope_status")) != "SCOPED":
            # Unrevalidated / excluded rows never apply.
            return None if not allow_legacy else dict(row)
        stored_fp = row.get("evidence_fingerprint") if isinstance(row.get("evidence_fingerprint"), dict) else {}
        if current_fingerprint is not None and not fingerprint_compatible(stored_fp, current_fingerprint):
            # Material evidence change → treat as stale for apply.
            stale = dict(row)
            stale["scope_status"] = STATUS_STALE_EVIDENCE
            stale["apply_status"] = STATUS_STALE_EVIDENCE
            stale["stale_reason"] = (
                "STALE_EVIDENCE — stored fingerprint incompatible with current "
                "RUN/word/bit/Configio/endpoint/ownership"
            )
            stale["assignable"] = False
            stale.update(_METRICS_EXCLUSION_FLAGS)
            return None if not allow_legacy else stale
        out = dict(row)
        out["scope_key"] = key
        out["apply_status"] = "APPLICABLE"
        return out

    if allow_legacy:
        return _peer_or_legacy_history(store, name, exclude_controller=ctrl)
    return None


def _peer_or_legacy_history(
    store: dict[str, Any],
    canonical_name: str,
    *,
    exclude_controller: str = "",
) -> dict[str, Any] | None:
    """Read-only peer/legacy history for UI — never auto-applied."""
    name = _norm_u(canonical_name)
    excl = _norm_u(exclude_controller)
    peers: list[dict[str, Any]] = []
    for key, row in (store.get("confirmations") or {}).items():
        if not isinstance(row, dict):
            continue
        parsed = parse_scope_key(key)
        if parsed["canonical_device"] != name:
            continue
        if excl and parsed["controller"] == excl:
            continue
        peer = dict(row)
        peer["scope_key"] = key
        peer["read_only"] = True
        peer["peer_history"] = True
        peer["apply_status"] = "PEER_HISTORY"
        peers.append(peer)
    for key, row in (store.get("legacy_confirmations") or {}).items():
        if not isinstance(row, dict):
            continue
        cname = _norm_u(row.get("canonical_device") or parse_scope_key(key).get("canonical_device"))
        if cname != name:
            continue
        peer = dict(row)
        peer["scope_key"] = key
        peer["read_only"] = True
        peer["peer_history"] = True
        peer["apply_status"] = STATUS_STALE_LEGACY
        peers.append(peer)
    if not peers:
        return None
    # Return the most recent peer as representative; attach full list.
    peers.sort(key=lambda r: str(r.get("confirmed_at") or ""), reverse=True)
    top = dict(peers[0])
    top["peer_history_all"] = peers
    return top


def list_peer_history(
    store: dict[str, Any],
    canonical_name: str,
    *,
    exclude_controller: str = "",
) -> list[dict[str, Any]]:
    hist = _peer_or_legacy_history(
        store, canonical_name, exclude_controller=exclude_controller
    )
    if not hist:
        return []
    return list(hist.get("peer_history_all") or [hist])


def confirm_physical_device(
    *,
    canonical_device: str,
    classification: str,
    controller: str = "",
    site: str = "",
    physical_endpoint: str = "",
    reason: str = "",
    confirmed_by: str = "engineer",
    conflict_acknowledged: bool = False,
    proven_foreign: bool = False,
    duplicate_endpoint_owner: str = "",
    prior_status: str = "",
    evidence_snapshot: dict[str, Any] | None = None,
    evidence_fingerprint: dict[str, Any] | None = None,
    store_path: Path | str | None = None,
    device_type: str = "",
    safety_classification: str = "",
    safety_zone: str = "",
    ownership_choice: str = "",
) -> dict[str, Any]:
    """Record a controlled engineer confirmation under site|controller|device.

    Successive composing actions (CONFIRM_LOCAL → CONFIRM_SAFETY, etc.) merge
    with the prior durable row so endpoint / type / Safety role are preserved.

    Returns {ok, status, confirmation, error?}.
    """
    name = _norm(canonical_device)
    if not name:
        return {"ok": False, "error": "canonical_device required"}

    cls = _norm(classification).upper().replace(" ", "_")
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
    site_u = derive_site_from_controller(target_controller, site)

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
        CONFIRM_FOREIGN,
        MARK_SPARE,
        MARK_INTERNAL,
    }
    if needs_controller and not target_controller:
        return {"ok": False, "error": f"controller required for {cls}"}
    if needs_controller and not site_u:
        return {"ok": False, "error": f"site required for {cls} (derive from controller failed)"}

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
    scope_key = make_scope_key(site_u, target_controller, name)
    prior = confs.get(scope_key) if isinstance(confs.get(scope_key), dict) else {}

    # Compose, do not silently erase earlier valid properties on successive actions.
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
        if not site_u:
            site_u = _norm(prior.get("site")) or derive_site_from_controller(target_controller)
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

    if cls == MARK_INTERNAL:
        dt = dt or "INTERNAL_LOGICAL"
    elif cls == CONFIRM_SAFETY:
        dt = dt or "SAFETY"

    # Rebuild scope key after compose may have filled controller/site.
    scope_key = make_scope_key(site_u, target_controller, name)

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
                "scope_key": prior.get("scope_key") or scope_key,
            }
        )

    snap = evidence_snapshot or prior.get("evidence_snapshot") or {}
    fp = evidence_fingerprint
    if not isinstance(fp, dict) or not fp:
        fp = prior.get("evidence_fingerprint") if isinstance(prior.get("evidence_fingerprint"), dict) else None
    if not isinstance(fp, dict) or not fp:
        fp = build_evidence_fingerprint(
            run_hash=_norm(snap.get("run_hash") or snap.get("run_id")),
            raw_word=snap.get("word") or snap.get("raw_word"),
            raw_bit=snap.get("bit") or snap.get("raw_bit"),
            parsed_bit=snap.get("parsed_bit"),
            configio_evidence=_norm(snap.get("configio_evidence") or snap.get("active_configio")),
            endpoint=endpoint_in or _norm(snap.get("endpoint") or snap.get("physical_endpoint")),
            module=_norm(snap.get("module")),
            evidence_class=_norm(snap.get("evidence_class")),
            ownership=ownership,
        )
    else:
        fp = dict(fp)
        if endpoint_in and not fp.get("endpoint"):
            fp["endpoint"] = endpoint_in
        if ownership and not fp.get("ownership"):
            fp["ownership"] = ownership

    row = {
        "canonical_device": name,
        "site": site_u,
        "controller": _norm_u(target_controller),
        "scope_key": scope_key,
        "scope_status": "SCOPED",
        "classification": cls,
        "physical_endpoint": endpoint_in,
        "ownership": ownership,
        "final_status": final_status,
        "reason": _norm(reason) or "engineer confirmation",
        "confirmed_by": _norm(confirmed_by) or "engineer",
        "confirmed_at": _ts(),
        "conflict_acknowledged": bool(conflict_acknowledged),
        "prior_status": _norm(prior_status) or _norm(prior.get("final_status")),
        "evidence_snapshot": snap,
        "evidence_fingerprint": fp,
        "assignable": final_status == STATUS_ENGINEER_CONFIRMED,
        "device_type": dt,
        "safety_classification": safety_cls,
        "safety_zone": safety_zn,
        "evidence_class": (
            "INTERNAL_LOGICAL" if final_status == STATUS_INTERNAL_LOGICAL else _norm(fp.get("evidence_class"))
        ),
        "classification_history": history[-12:],
        "read_only": False,
    }
    confs[scope_key] = row
    store["confirmations"] = confs
    path = save_confirmations(store, store_path)

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
        "scope_key": scope_key,
        "path": str(path),
    }
    if learn_result is not None:
        out["knowledge_learn"] = learn_result
    return out


def apply_confirmations_to_devices(
    devices: list[dict[str, Any]],
    store: dict[str, Any] | None = None,
    store_path: Path | str | None = None,
    *,
    active_machine: str = "",
    site: str = "",
) -> dict[str, Any]:
    """Apply durable confirmations onto canonical device rows in-place.

    Requires active_machine (controller). Name-only matches never apply.
    Cross-controller confirmations never apply. Stale fingerprint → skip apply
    and stamp STALE_EVIDENCE / REVIEW_REQUIRED on the device when a scoped row
    exists but evidence diverged.
    """
    st = store if store is not None else load_confirmations(store_path)
    mach = _norm_u(active_machine)
    site_u = _norm_u(site) or (_norm_u(derive_site_from_controller(mach)) if mach else "")
    applied = 0
    skipped_cross_controller = 0
    skipped_stale = 0
    skipped_no_scope = 0
    peer_history_attached = 0

    if not mach:
        # Without controller scope we refuse to apply anything.
        return {
            "applied": 0,
            "skipped_no_scope": len(devices),
            "skipped_cross_controller": 0,
            "skipped_stale": 0,
            "store_path": st.get("path"),
            "total_confirmations": len(st.get("confirmations") or {}),
            "active_machine": "",
            "site": site_u,
            "error": "active_machine required — name-only apply forbidden",
        }

    for d in devices:
        name = _norm(d.get("canonical_name") or d.get("canonical_device") or d.get("name"))
        if not name:
            continue
        current_fp = fingerprint_from_device(d)
        conf = lookup_confirmation(
            st,
            name,
            site=site_u,
            controller=mach,
            current_fingerprint=current_fp,
        )
        if not conf:
            # Attach peer history read-only when present; never apply.
            peers = list_peer_history(st, name, exclude_controller=mach)
            if peers:
                d["engineer_confirmation_peer_history"] = peers
                peer_history_attached += 1
                # Count cross-controller peers for metrics.
                skipped_cross_controller += sum(
                    1
                    for p in peers
                    if _norm_u(p.get("controller")) and _norm_u(p.get("controller")) != mach
                )
            # Check whether a scoped row exists but was stale.
            key = make_scope_key(site_u, mach, name)
            raw = (st.get("confirmations") or {}).get(key)
            if isinstance(raw, dict):
                stored_fp = raw.get("evidence_fingerprint") if isinstance(raw.get("evidence_fingerprint"), dict) else {}
                if stored_fp and not fingerprint_compatible(stored_fp, current_fp):
                    d["engineer_confirmation_stale"] = {
                        "scope_status": STATUS_STALE_EVIDENCE,
                        "stale_reason": (
                            "STALE_EVIDENCE — confirmation fingerprint incompatible "
                            "with current discovery"
                        ),
                        "scope_key": key,
                        "stored_fingerprint": stored_fp,
                        "current_fingerprint": current_fp,
                    }
                    # Do not keep ENGINEER_CONFIRMED from a stale row.
                    skipped_stale += 1
            continue

        # Hard gate: unrevalidated / legacy-shaped rows never mutate device status
        # or contribute to physical-resolution / assignability.
        if not confirmation_is_metrics_eligible(conf):
            d["engineer_confirmation_peer_history"] = list(
                d.get("engineer_confirmation_peer_history") or []
            ) + [dict(conf, read_only=True, apply_status=STATUS_STALE_LEGACY)]
            skipped_stale += 1
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
        d["engineer_confirmation_metrics_eligible"] = True
        trace = d.get("escalation_trace")
        if isinstance(trace, dict):
            trace["engineer_decision"] = {
                "classification": conf.get("classification"),
                "final_status": conf.get("final_status"),
                "confirmed_by": conf.get("confirmed_by"),
                "confirmed_at": conf.get("confirmed_at"),
                "reason": conf.get("reason"),
                "scope_key": conf.get("scope_key"),
                "metrics_eligible": True,
            }
        applied += 1

    return {
        "applied": applied,
        "skipped_cross_controller": skipped_cross_controller,
        "skipped_stale": skipped_stale,
        "skipped_no_scope": skipped_no_scope,
        "peer_history_attached": peer_history_attached,
        "store_path": st.get("path"),
        "total_confirmations": len(st.get("confirmations") or {}),
        "legacy_confirmations": len(st.get("legacy_confirmations") or {}),
        "active_machine": mach,
        "site": site_u,
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
    site: str = "",
) -> dict[str, Any]:
    """Stamp engineer I/O confirmations onto Safety inventory rows.

    ENGINEER_CONFIRMED LOCAL + Safety + endpoint → assignable LOCAL_PHYSICAL.
    FOREIGN / INTERNAL / GUI_ONLY remain non-assignable with visible reason.

    inject_missing:
      NEVER injects a confirmation into a different controller.
      Same-controller missing Safety rows may be surfaced as REVIEW_REQUIRED
      unless current evidence independently proves them (endpoint present).
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
    skipped_cross_controller = 0
    skipped_legacy = 0
    skipped_stale = 0
    mach = _norm_u(active_machine)
    site_u = _norm_u(site) or (_norm_u(derive_site_from_controller(mach)) if mach else "")

    if not mach:
        return {
            "applied": 0,
            "injected": 0,
            "skipped_cross_controller": 0,
            "skipped_legacy": len(st.get("legacy_confirmations") or {}),
            "store_path": st.get("path"),
            "total_confirmations": len(confs),
            "error": "active_machine required — name-only apply forbidden",
        }

    for key, conf in confs.items():
        if not isinstance(conf, dict):
            continue
        parsed = parse_scope_key(key)
        conf_ctrl = _norm_u(conf.get("controller") or parsed.get("controller"))
        conf_site = _norm_u(conf.get("site") or parsed.get("site"))
        name = _norm(conf.get("canonical_device") or parsed.get("canonical_device") or key)
        name_u = name.upper()

        # Cross-controller: never apply, never inject.
        if conf_ctrl and conf_ctrl != mach:
            skipped_cross_controller += 1
            # Attach peer history on existing local row if present.
            existing = by_name.get(name_u)
            if existing is not None:
                peers = existing.get("engineer_confirmation_peer_history")
                if not isinstance(peers, list):
                    peers = []
                peer = dict(conf)
                peer["read_only"] = True
                peer["peer_history"] = True
                peer["apply_status"] = "PEER_HISTORY"
                peers.append(peer)
                existing["engineer_confirmation_peer_history"] = peers
            continue

        # Site mismatch (same controller name collision across sites) — refuse.
        if conf_site and site_u and conf_site != site_u:
            skipped_cross_controller += 1
            continue

        # Stale / legacy scoped markers — never auto-apply.
        if _norm_u(conf.get("scope_status")) in {STATUS_STALE_LEGACY, STATUS_STALE_EVIDENCE}:
            skipped_stale += 1
            continue
        if not confirmation_is_metrics_eligible(conf):
            skipped_stale += 1
            continue

        fs = _norm(conf.get("final_status")).upper()
        ownership = _norm(conf.get("ownership")).upper()
        endpoint = _norm(conf.get("physical_endpoint"))
        reason = _norm(conf.get("reason")) or fs
        ctrl = conf_ctrl or mach
        dt = _norm(conf.get("device_type") or conf.get("safety_classification")) or "SAFETY"

        row = by_name.get(name_u)
        if row is None:
            if not inject_missing or not _is_safety_confirmation(conf):
                continue
            # Same-controller inject only (already filtered above).
            # Surface as REVIEW_REQUIRED unless endpoint independently present.
            if fs not in {STATUS_ENGINEER_CONFIRMED, STATUS_FOREIGN, STATUS_INTERNAL_LOGICAL}:
                continue
            has_ep = bool(endpoint)
            row = {
                "id": name,
                "name": name,
                "canonicalTag": name,
                "kind": dt.upper() if dt.upper() in _SAFETY_DEVICE_TYPES else "OTHER",
                "stem": name,
                "signals": [],
                "signalNames": [],
                "status": "UNASSIGNED" if (has_ep and fs == STATUS_ENGINEER_CONFIRMED and ownership == "LOCAL") else "REVIEW_REQUIRED",
                "origin": "ENGINEER_CONFIRMATION",
                "sources": ["engineer_io_confirmations"],
                "review_reason": (
                    None
                    if (has_ep and fs == STATUS_ENGINEER_CONFIRMED and ownership == "LOCAL")
                    else "INJECTED_SAME_CONTROLLER_REVIEW_REQUIRED"
                ),
            }
            devices.append(row)
            by_name[name_u] = row
            injected += 1

        # Fingerprint stale check against live row evidence.
        current_fp = fingerprint_from_device(row)
        stored_fp = conf.get("evidence_fingerprint") if isinstance(conf.get("evidence_fingerprint"), dict) else {}
        if stored_fp and current_fp and not fingerprint_compatible(stored_fp, current_fp):
            row["engineer_confirmation_stale"] = {
                "scope_status": STATUS_STALE_EVIDENCE,
                "scope_key": key,
                "stale_reason": "STALE_EVIDENCE — fingerprint incompatible",
            }
            row["assignable"] = False
            skipped_stale += 1
            continue

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
        # Safety assignability / generated I/O only from metrics-eligible scoped rows.
        row["engineer_confirmation_metrics_eligible"] = True
        applied += 1

    # Legacy unscoped rows: never apply / never inject. Count only.
    skipped_legacy = len(st.get("legacy_confirmations") or {})

    return {
        "applied": applied,
        "injected": injected,
        "skipped_cross_controller": skipped_cross_controller,
        "skipped_stale": skipped_stale,
        "skipped_legacy": skipped_legacy,
        "store_path": st.get("path"),
        "total_confirmations": len(confs),
        "active_machine": mach,
        "site": site_u,
    }

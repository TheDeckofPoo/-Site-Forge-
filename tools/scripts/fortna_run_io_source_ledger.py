#!/usr/bin/env python3
"""RUN_IO_SOURCE_LEDGER — upstream physical I/O conservation.

Denominator for I/O completeness is the reconciled upstream RUN source ledger,
never physical_io_map.csv alone.

Pipeline:
  SOURCE → CANONICAL DEVICE → PHYSICAL ENDPOINT → LOGICAL TAG → IO_MAP → L5X

Every source physical candidate terminates in exactly one of:
  MAPPED | SPARE_UNUSED | FOREIGN_CONTROLLER | ALIAS_OF:<parent>
  | REVIEW_REQUIRED | UNSUPPORTED

silently_missing must be 0 or AUDIT_FAIL:
  IO:SOURCE_CONSERVATION_FAILURE:<device>
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATUS_MAPPED = "MAPPED"
STATUS_SPARE = "SPARE_UNUSED"
STATUS_FOREIGN = "FOREIGN_CONTROLLER"
STATUS_ALIAS = "ALIAS_OF"  # stored as ALIAS_OF:<parent>
STATUS_REVIEW = "REVIEW_REQUIRED"
STATUS_UNSUPPORTED = "UNSUPPORTED"
STATUS_SILENT = "SILENTLY_MISSING"
STATUS_ENGINEER_CONFIRMED = "ENGINEER_CONFIRMED"
STATUS_ENGINEER_REQUIRED = "ENGINEER_CONFIRM_REQUIRED"
STATUS_INTERNAL = "INTERNAL_LOGICAL"
STATUS_INTERNAL_LOGICAL = STATUS_INTERNAL  # alias used by escalation / engineer confirm

# Evidence / world classes (physical-world-first separation)
EVIDENCE_PHYSICAL_FIELD = "PHYSICAL_FIELD_DEVICE"
EVIDENCE_PROVEN_SPARE = "PHYSICAL_UNUSED_CHANNEL"
EVIDENCE_INTERNAL = "INTERNAL_LOGICAL"
EVIDENCE_FOREIGN = "FOREIGN_CONTROLLER"
EVIDENCE_REVIEW = "REVIEW_REQUIRED"
EVIDENCE_CHANNEL_OCCUPANCY = "CHANNEL_OCCUPANCY"  # unproven unused channel — not a device

TERMINAL_STATUSES = (
    STATUS_MAPPED,
    STATUS_SPARE,
    STATUS_FOREIGN,
    STATUS_ALIAS,
    STATUS_REVIEW,
    STATUS_UNSUPPORTED,
    STATUS_ENGINEER_CONFIRMED,
    STATUS_ENGINEER_REQUIRED,
    STATUS_INTERNAL,
)

# Resolved for physical-device resolution (REVIEW is NOT resolved).
# SPARE only counts when evidence_class is PHYSICAL_UNUSED_CHANNEL (proven).
RESOLVED_STATUSES = frozenset(
    {
        STATUS_MAPPED,
        STATUS_SPARE,
        STATUS_FOREIGN,
        STATUS_UNSUPPORTED,
        STATUS_ENGINEER_CONFIRMED,
        STATUS_ALIAS,
        STATUS_INTERNAL,
    }
)

CRITICAL_HIGHLIGHTS = frozenset(
    {
        "ESPB",
        "ESLS",
        "ESR",
        "MCR",
        "SAFETY",
        "ESTOP",
        "PUSHBUTTON_CONTROL",
        "PUSHBUTTON",
        "CS",
    }
)

RESOLUTION_THRESHOLD_PCT = 85.0

_PB_RE = re.compile(
    r"(?:PBSTART|PBSTOP|PBRESET|_PLT$|(?:^|[^A-Z0-9])PB\d|(?:^|_)(?:SS|RS)\d)",
    re.I,
)
_SAFETY_RE = re.compile(r"(?:^ESPB|^ESLS|^ESR|^MCR|ESLS|ESPB|_AUX$)", re.I)
_SPARE_TOKENS = frozenset(
    {"", "SPARE", "INVALID", "N/A", "NA", "NONE", "NULL", "—", "-", "(SPARE)"}
)
_MACHINE_WILDCARD = frozenset(
    {"", "N/A", "NA", "NONE", "INVALID", "ALL", "0", "NULL"}
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _is_spare_name(name: str) -> bool:
    return _norm(name).upper() in _SPARE_TOKENS or _norm(name).upper().startswith("SPARE")


def _is_endpoint_shaped_name(name: str) -> bool:
    """True when the 'name' is really a module channel address, not a device tag."""
    u = _norm(name)
    if not u:
        return True
    if u.upper().startswith("CH:"):
        return True
    return bool(re.match(r"^[A-Z][A-Z0-9_]*:\d*:?[IO]\.Data", u, re.I))


def _is_proven_spare_channel(row: dict[str, Any]) -> bool:
    """SPARE only when module/channel exists AND RUN explicitly indicates unused/spare.

    Unoccupied channels whose 'name' is merely an endpoint address are NOT proven spares.
    """
    name = _norm(row.get("source_signal") or row.get("canonical_name") or row.get("name"))
    if _is_spare_name(name):
        return True
    flag = _norm(
        row.get("spare_flag")
        or row.get("unused")
        or row.get("configio_spare")
        or row.get("explicit_spare")
    ).upper()
    if flag in {"Y", "YES", "1", "TRUE", "SPARE", "UNUSED"}:
        return True
    reason = _norm(row.get("reason")).upper()
    if (
        "EXPLICIT SPARE" in reason
        or "PROVEN SPARE" in reason
        or ("ENGINEER" in reason and "SPARE" in reason)
    ):
        return True
    # Endpoint-shaped names without spare token are occupancy only
    if _is_endpoint_shaped_name(name):
        return False
    return False


def _is_pb_or_control(name: str) -> bool:
    return bool(_PB_RE.search(_norm(name)))


def _is_safety_name(name: str) -> bool:
    u = _norm(name).upper()
    if u.endswith("_AUX") and re.search(r"(?:ESR|MCR|ES|ESPB|ESLS)", u):
        return True
    return bool(re.search(r"^ESPB|^ESLS|^ESR\d|^MCR\d|ESLS\d|ESPB\d", u))


def _classify_device_semantics(
    name: str,
    *,
    highlight: str = "",
    source_type: str = "",
) -> dict[str, Any]:
    """Evidence-driven equipment / world-class classification.

    Prefers fortna_io_equipment_classifier when available; falls back to local rules.
    """
    try:
        from fortna_io_equipment_classifier import classify_equipment

        return dict(classify_equipment(name, highlight=highlight, source_type=source_type) or {})
    except Exception:
        pass

    u = _norm(name).upper()
    h = _norm(highlight).upper()
    reasons: list[str] = []
    equipment_class = "UNKNOWN"
    evidence_class = EVIDENCE_REVIEW
    confidence = "UNKNOWN"
    fortna_hint = ""
    needs_review = False

    if _is_spare_name(name) or h == "PHYSICAL_CHANNEL" and _is_endpoint_shaped_name(name):
        if _is_spare_name(name):
            return {
                "equipment_class": "PHYSICAL_CHANNEL",
                "evidence_class": EVIDENCE_PROVEN_SPARE,
                "confidence": "PROVEN",
                "reasons": ["explicit spare/invalid token"],
                "fortna_plus_hint": "",
                "needs_review": False,
            }
        return {
            "equipment_class": "PHYSICAL_CHANNEL",
            "evidence_class": EVIDENCE_CHANNEL_OCCUPANCY,
            "confidence": "DERIVED",
            "reasons": ["unoccupied channel without explicit spare token"],
            "fortna_plus_hint": "",
            "needs_review": False,
        }

    # Internal / logical Fortna evidence — not physical-field denominator
    if re.match(r"^MEM_", u) or (
        (u.endswith("_STATUS") or u.endswith("_ENABLE") or u.endswith("_ENABLED"))
        and not (_is_pb_or_control(name) or _is_safety_name(name) or re.search(r"(?:^|_)PE\d", u))
    ):
        return {
            "equipment_class": "INTERNAL_LOGICAL",
            "evidence_class": EVIDENCE_INTERNAL,
            "confidence": "DERIVED",
            "reasons": ["internal/logical naming pattern"],
            "fortna_plus_hint": "",
            "needs_review": False,
        }

    if re.match(r"^ES_PE_", u) or re.search(r"^ES_PE", u):
        return {
            "equipment_class": "AMBIGUOUS",
            "evidence_class": EVIDENCE_REVIEW,
            "confidence": "REVIEW_REQUIRED",
            "reasons": ["compound ES_PE naming — review required"],
            "fortna_plus_hint": "",
            "needs_review": True,
        }

    if re.search(r"PBSTART", u):
        equipment_class, fortna_hint, reasons = "CONTROL_STATION_START_PB", "CPx_CS.I.Start_PB", ["PBSTART nomenclature"]
    elif re.search(r"PBSTOP", u):
        equipment_class, fortna_hint, reasons = "CONTROL_STATION_STOP_PB", "CPx_CS.I.Stop_PB", ["PBSTOP nomenclature"]
    elif re.search(r"PBRESET", u):
        equipment_class, fortna_hint, reasons = "CONTROL_STATION_RESET_PB", "CPx_CS.I.Reset_PB", ["PBRESET nomenclature"]
    elif re.search(r"(?:_PLT|_PL)$|\.PLT", u):
        equipment_class, fortna_hint, reasons = "CONTROL_STATION_OUTPUT", "CPx_CS.O.PilotLight", ["pilot-light suffix"]
    elif re.search(r"(?:^ESPB|ESPB\d)", u) or h == "ESPB":
        equipment_class, reasons = "SAFETY_ESTOP_PB", ["ESPB nomenclature"]
    elif re.search(r"(?:^ESLS|ESLS\d)", u) or h == "ESLS":
        equipment_class, reasons = "SAFETY_SWITCH", ["ESLS nomenclature"]
    elif re.search(r"(?:^ESR|ESR\d)", u) or h == "ESR":
        equipment_class, reasons = "SAFETY_RELAY", ["ESR nomenclature"]
    elif re.search(r"(?:^MCR|MCR\d)", u) or h == "MCR":
        equipment_class, reasons = "MASTER_CONTROL_RELAY", ["MCR nomenclature"]
    elif re.search(r"(?:^PE\d|(?:^|_)PE\d|_PE$|PHOTOEYE)", u) or h in {"PE", "PHOTOEYE"}:
        equipment_class, fortna_hint, reasons = "PHOTOEYE", "CPx.I.PE", ["photoeye nomenclature"]
    elif re.search(r"\bVFD|VFD\d", u) or h == "VFD":
        equipment_class, fortna_hint, reasons = "DRIVE", "CPx_VFD", ["VFD nomenclature"]
    elif re.search(r"(?:^MTR|MTR\d|STARTER|(?:^|_)MS\d)", u):
        equipment_class, fortna_hint, reasons = "MOTOR_EQUIPMENT", "CPx_MTR", ["motor starter nomenclature"]
    elif _is_pb_or_control(name) or h in {"PUSHBUTTON_CONTROL", "PUSHBUTTON", "CS"}:
        equipment_class, fortna_hint, reasons = "PUSHBUTTON_CONTROL", "CPx_CS", ["control-station PB nomenclature"]
    elif _is_safety_name(name) or h in {"SAFETY", "ESTOP"}:
        equipment_class, reasons = "SAFETY", ["safety nomenclature"]
    elif h and h not in {"IO", "PHYSICAL_CHANNEL"}:
        equipment_class, reasons = h, [f"highlight={h}"]

    if equipment_class in {
        "CONTROL_STATION_START_PB",
        "CONTROL_STATION_STOP_PB",
        "CONTROL_STATION_RESET_PB",
        "CONTROL_STATION_OUTPUT",
        "SAFETY_ESTOP_PB",
        "SAFETY_SWITCH",
        "SAFETY_RELAY",
        "MASTER_CONTROL_RELAY",
        "PHOTOEYE",
        "DRIVE",
        "MOTOR_EQUIPMENT",
        "PUSHBUTTON_CONTROL",
        "SAFETY",
    }:
        evidence_class = EVIDENCE_PHYSICAL_FIELD
        confidence = "DERIVED"
    elif equipment_class == "UNKNOWN":
        # Bare word/bit with no nomenclature → internal/logical, not field hardware
        if not h or h in {"IO", ""}:
            equipment_class = "INTERNAL_LOGICAL"
            evidence_class = EVIDENCE_INTERNAL
            confidence = "DERIVED"
            reasons = ["no field-device nomenclature — treated as internal/logical"]
        else:
            evidence_class = EVIDENCE_REVIEW
            needs_review = True
            confidence = "REVIEW_REQUIRED"

    return {
        "equipment_class": equipment_class,
        "evidence_class": evidence_class,
        "confidence": confidence,
        "reasons": reasons,
        "fortna_plus_hint": fortna_hint,
        "needs_review": needs_review,
    }


def _equipment_to_device_type(equipment_class: str, highlight: str = "", name: str = "") -> str:
    try:
        from fortna_io_equipment_classifier import map_equipment_to_device_type

        mapped = map_equipment_to_device_type(equipment_class)
        if mapped:
            return mapped
    except Exception:
        pass
    ec = _norm(equipment_class).upper()
    mapping = {
        "SAFETY_ESTOP_PB": "ESPB",
        "SAFETY_SWITCH": "ESLS",
        "SAFETY_RELAY": "ESR",
        "MASTER_CONTROL_RELAY": "MCR",
        "CONTROL_STATION_START_PB": "PUSHBUTTON_CONTROL",
        "CONTROL_STATION_STOP_PB": "PUSHBUTTON_CONTROL",
        "CONTROL_STATION_RESET_PB": "PUSHBUTTON_CONTROL",
        "CONTROL_STATION_OUTPUT": "PUSHBUTTON_CONTROL",
        "PUSHBUTTON_CONTROL": "PUSHBUTTON_CONTROL",
        "PHOTOEYE": "PHOTOEYE",
        "DRIVE": "VFD",
        "MOTOR_EQUIPMENT": "MOTOR",
        "PHYSICAL_CHANNEL": "PHYSICAL_CHANNEL",
        "INTERNAL_LOGICAL": "INTERNAL_LOGICAL",
        "SAFETY": "SAFETY",
        "AMBIGUOUS": "IO",
    }
    if ec in mapping:
        return mapping[ec]
    return _device_type_from_highlight(highlight, name)


def _alias_parent(name: str) -> str | None:
    """Return canonical parent if this name is a known alias child form."""
    u = _norm(name)
    if not u:
        return None
    # T_ prefix alias of same stem
    if u.upper().startswith("T_") and len(u) > 2:
        return u[2:]
    # trailing _AUX feedback of command device
    if u.upper().endswith("_AUX") and len(u) > 4:
        return u[:-4]
    return None


def _candidate_id(source_file: str, name: str, word: str = "", bit: str = "") -> str:
    return "|".join(
        [
            _norm(source_file) or "-",
            _norm(name).upper() or "-",
            _norm(word) or "-",
            _norm(bit) or "-",
        ]
    )


def _add_candidate(
    by_id: dict[str, dict[str, Any]],
    *,
    name: str,
    source_file: str,
    source_type: str,
    machine_name: str = "",
    word: str = "",
    bit: str = "",
    direction: str = "",
    module: str = "",
    slot: str = "",
    endpoint: str = "",
    highlight: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    cid = _candidate_id(source_file, name, word, bit)
    if cid in by_id:
        # Merge sources
        prev = by_id[cid]
        srcs = list(prev.get("source_types") or [])
        if source_type and source_type not in srcs:
            srcs.append(source_type)
            prev["source_types"] = srcs
        if endpoint and not prev.get("endpoint"):
            prev["endpoint"] = endpoint
        if highlight and not prev.get("highlight"):
            prev["highlight"] = highlight
        return
    row = {
        "id": cid,
        "source_signal": _norm(name),
        "source_file": _norm(source_file),
        "source_type": _norm(source_type),
        "source_types": [_norm(source_type)] if source_type else [],
        "machine": _norm(machine_name),
        "module": _norm(module),
        "slot": _norm(slot),
        "word": _norm(word),
        "bit": _norm(bit),
        "direction": _norm(direction),
        "endpoint": _norm(endpoint),
        "highlight": _norm(highlight),
        "canonical_device": "",
        "alias_parent": "",
        "final_status": "",
        "generated_tag": "",
        "io_map_writer": "N",
        "reason": "",
    }
    if extra:
        row.update(extra)
    by_id[cid] = row


def _scan_conveyor_all_machines(
    run_dir: Path, machine: str, by_id: dict[str, dict[str, Any]]
) -> None:
    from fortna_asc import read_asc

    conv = run_dir / "FORTNA" / "Conveyor.asc"
    if not conv.is_file():
        return
    _, rows = read_asc(conv)
    mach_u = (machine or "").strip().upper()
    for row in rows:
        name = _norm(row.get("IO_Name"))
        if not name or _is_spare_name(name):
            continue
        word = _norm(row.get("IO_Address_Word"))
        bit = _norm(row.get("IO_Address_Bit"))
        if not word or not bit:
            continue
        rm = _norm(row.get("Machine_Name"))
        rm_u = rm.upper()
        typ = _norm(row.get("Type")).upper()
        highlight = ""
        if _is_pb_or_control(name):
            highlight = "PUSHBUTTON_CONTROL"
        elif _is_safety_name(name):
            if re.search(r"ESPB", name, re.I):
                highlight = "ESPB"
            elif re.search(r"ESLS", name, re.I):
                highlight = "ESLS"
            elif re.search(r"^ESR|ESR", name, re.I):
                highlight = "ESR"
            elif re.search(r"^MCR|MCR", name, re.I):
                highlight = "MCR"
            else:
                highlight = "SAFETY"
        # Conservation denominator focuses on pushbuttons/control-stations and
        # Safety-named devices (plus foreign rows of those kinds). Ordinary
        # PE/motor/conveyor claims are covered via physical_word_map + io_points.
        is_interest = bool(highlight)
        if not is_interest:
            continue
        is_current = (not rm_u or rm_u in _MACHINE_WILDCARD) or rm_u == mach_u
        is_foreign = bool(rm_u) and rm_u not in _MACHINE_WILDCARD and rm_u != mach_u
        _add_candidate(
            by_id,
            name=name,
            source_file="FORTNA/Conveyor.asc",
            source_type="conveyor_named_claim",
            machine_name=rm or ("N/A" if is_current else rm),
            word=word,
            bit=bit,
            direction="",
            highlight=highlight,
            extra={
                "asc_type": typ,
                "ownership_hint": (
                    "FOREIGN"
                    if is_foreign
                    else ("WILDCARD" if (not rm_u or rm_u in _MACHINE_WILDCARD) else "OWN")
                ),
            },
        )


def _scan_estop_table(run_dir: Path, by_id: dict[str, dict[str, Any]]) -> None:
    from fortna_asc import read_asc

    path = run_dir / "FORTNA" / "EStop.asc"
    if not path.is_file():
        return
    _, rows = read_asc(path)
    for row in rows:
        # EStop.asc columns vary: Part / Desc commonly hold the device token
        name = _norm(row.get("Part") or row.get("Part_Conveyor") or row.get("IO_Name"))
        if not name or _is_spare_name(name):
            continue
        if not (_is_safety_name(name) or _is_pb_or_control(name)):
            # Keep safety-like Desc tokens
            desc = _norm(row.get("Desc") or row.get("Description"))
            if not (_is_safety_name(desc) or _is_pb_or_control(desc)):
                continue
            if not name and desc:
                name = desc
        highlight = "ESPB" if re.search(r"ESPB", name, re.I) else (
            "ESLS" if re.search(r"ESLS", name, re.I) else (
                "ESR" if re.search(r"ESR", name, re.I) else (
                    "MCR" if re.search(r"MCR", name, re.I) else "SAFETY"
                )
            )
        )
        _add_candidate(
            by_id,
            name=name,
            source_file="FORTNA/EStop.asc",
            source_type="estop_table",
            machine_name="",
            word=_norm(row.get("IO_Address_Word") or row.get("Word") or ""),
            bit=_norm(row.get("IO_Address_Bit") or row.get("Bit") or ""),
            highlight=highlight,
            extra={"desc": _norm(row.get("Desc") or row.get("Description"))[:120]},
        )


def _scan_physical_word_map(
    run_dir: Path, machine: str, by_id: dict[str, dict[str, Any]]
) -> None:
    try:
        from fortna_physical_word_resolver import build_physical_word_map

        pm = build_physical_word_map(run_dir, machine)
    except Exception as ex:  # noqa: BLE001
        by_id.setdefault(
            "__word_map_error__",
            {
                "id": "__word_map_error__",
                "source_signal": "",
                "source_file": "eipcfg+configio",
                "source_type": "physical_word_map_error",
                "error": str(ex),
                "final_status": STATUS_REVIEW,
                "highlight": "",
            },
        )
        return
    by_wb = pm.get("by_word_bit") or {}
    for wb_key, hit in by_wb.items():
        if not isinstance(hit, dict):
            continue
        channel = _norm(hit.get("channel"))
        rio = _norm(hit.get("rio_name") or hit.get("adapter"))
        direction = _norm(hit.get("direction")).upper()
        bit = hit.get("bit")
        word = None
        if isinstance(wb_key, str) and ":" in wb_key:
            word = wb_key.split(":", 1)[0]
        name = channel or f"CH:{wb_key}"
        _add_candidate(
            by_id,
            name=name,
            source_file="eipcfg+configio",
            source_type="physical_word_map",
            machine_name=machine,
            word=str(word or hit.get("octal_word") or ""),
            bit=str(bit if bit is not None else ""),
            direction=direction,
            module=rio,
            slot=str(hit.get("eip_slot") if hit.get("eip_slot") is not None else hit.get("slot") or ""),
            endpoint=channel,
            highlight="PHYSICAL_CHANNEL",
        )


def _scan_safety_model(
    run_dir: Path, machine: str, by_id: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    meta: dict[str, Any] = {"devices": 0, "signals": 0, "error": None}
    try:
        from fortna_safety_model import build_safety_model

        sm = build_safety_model(run_dir=run_dir, machine=machine, areas=[f"{machine}_Area"])
    except Exception as ex:  # noqa: BLE001
        meta["error"] = str(ex)
        return meta
    eu = sm.get("evidence_union") or {}
    # Prefer evidence_union devices (raw) over assignable-only
    devices = list(eu.get("devices") or sm.get("devices") or [])
    meta["devices"] = len(devices)
    meta["eu_counts"] = eu.get("counts")
    meta["source_counts"] = eu.get("source_counts")
    for d in devices:
        if not isinstance(d, dict):
            continue
        name = _norm(d.get("name") or d.get("id"))
        if not name:
            continue
        kind = _norm(d.get("kind")).upper() or "SAFETY"
        signals = d.get("signals") or d.get("signalNames") or [name]
        if isinstance(signals, list) and signals and isinstance(signals[0], dict):
            sig_names = [_norm(s.get("name")) for s in signals if _norm(s.get("name"))]
        else:
            sig_names = [_norm(s) for s in signals if _norm(s)]
        if not sig_names:
            sig_names = [name]
        meta["signals"] += len(sig_names)
        for sn in sig_names:
            parent = None
            if sn.upper() != name.upper():
                parent = name
            _add_candidate(
                by_id,
                name=sn,
                source_file="safety_model/evidence_union",
                source_type="safety_evidence",
                machine_name=_norm(d.get("machine")),
                word=_norm(d.get("io_word")),
                bit=_norm(d.get("io_bit")),
                endpoint=_norm(d.get("physicalEndpoint")),
                highlight=kind if kind in {"ESPB", "ESLS", "ESR", "MCR", "ESTOP", "CS"} else (
                    "ESPB" if kind == "ESTOP" else "SAFETY"
                ),
                extra={
                    "canonical_hint": name,
                    "alias_hint": parent or "",
                    "safety_status": _norm(d.get("status")),
                    "assignable": d.get("assignable"),
                    "inventory_scope": _norm(d.get("inventory_scope")),
                    "review_reason": _norm(d.get("review_reason")),
                },
            )
    # review_required / unsupported from evidence_union
    for d in list(eu.get("review_required") or []) + list(eu.get("unsupported_interface") or []):
        if not isinstance(d, dict):
            continue
        name = _norm(d.get("name"))
        if not name:
            continue
        _add_candidate(
            by_id,
            name=name,
            source_file="safety_model/evidence_union",
            source_type="safety_review",
            machine_name=_norm(d.get("machine")),
            endpoint=_norm(d.get("physicalEndpoint")),
            highlight="SAFETY",
            extra={
                "disposition": _norm(d.get("disposition") or d.get("inventory_bucket")),
                "reason": _norm(d.get("reason") or d.get("review_reason")),
                "forced_status_hint": (
                    STATUS_UNSUPPORTED
                    if "UNSUPPORTED" in _norm(d.get("disposition") or d.get("inventory_bucket")).upper()
                    else STATUS_REVIEW
                ),
            },
        )
    return meta


def build_run_io_source_ledger(
    run_dir: Path | str,
    machine: str,
) -> dict[str, Any]:
    """Build upstream RUN_IO_SOURCE_LEDGER (pre-reconcile)."""
    run_dir = Path(run_dir)
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"
    by_id: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    try:
        _scan_physical_word_map(run_dir, machine, by_id)
    except Exception as ex:  # noqa: BLE001
        errors.append(f"word_map:{ex}")
    try:
        _scan_conveyor_all_machines(run_dir, machine, by_id)
    except Exception as ex:  # noqa: BLE001
        errors.append(f"conveyor:{ex}")
    try:
        _scan_estop_table(run_dir, by_id)
    except Exception as ex:  # noqa: BLE001
        errors.append(f"estop:{ex}")
    safety_meta: dict[str, Any] = {}
    try:
        safety_meta = _scan_safety_model(run_dir, machine, by_id)
    except Exception as ex:  # noqa: BLE001
        errors.append(f"safety:{ex}")
        safety_meta = {"error": str(ex)}

    # Drop internal error placeholder from candidate set if present
    err_row = by_id.pop("__word_map_error__", None)
    if err_row:
        errors.append(str(err_row.get("error") or "word_map_error"))

    candidates = [v for k, v in by_id.items() if not k.startswith("__")]
    sources_ok = len(candidates) > 0 and not (
        safety_meta.get("error") and "conveyor" in "".join(errors)
    )
    return {
        "ori": "IO_SOURCE_CONSERVATION",
        "machine": machine,
        "run_dir": str(run_dir),
        "built_at": _ts(),
        "source_physical_candidates": len(candidates),
        "candidates": candidates,
        "safety_meta": safety_meta,
        "errors": errors,
        "ledger_complete": bool(sources_ok),
        "coverage_status": "PROVEN" if sources_ok else "NOT_PROVEN",
    }


def _load_physical_io_map(path: Path | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not path or not path.is_file():
        return out
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            name = _norm(row.get("fortna_name") or row.get("name")).upper()
            if not name:
                continue
            out[name] = row
    return out


def _l5x_tag_set(l5x_path: Path | None) -> set[str]:
    if not l5x_path or not Path(l5x_path).is_file():
        return set()
    text = Path(l5x_path).read_text(encoding="utf-8", errors="replace")
    names = set(re.findall(r'TagName="([^"]+)"', text))
    names.update(re.findall(r'Name="([A-Za-z_][A-Za-z0-9_]*)"', text))
    return {n.upper() for n in names}


def _io_map_writers(l5x_path: Path | None) -> set[str]:
    if not l5x_path or not Path(l5x_path).is_file():
        return set()
    text = Path(l5x_path).read_text(encoding="utf-8", errors="replace")
    m = re.search(r'<Program Name="IO_MAP"[^>]*>(.*?)</Program>', text, re.S)
    if not m:
        return set()
    body = m.group(1)
    tags = set()
    for inst in re.findall(r"\b(?:OTE|OTL|OTU|MOV|COP)\s*\(\s*([A-Za-z_][A-Za-z0-9_\.]*)", body, re.I):
        tags.add(inst.split(".")[0].upper())
    for inst in re.findall(r"\b(?:XIC|XIO)\s*\(\s*([A-Za-z_][A-Za-z0-9_\.]*)", body, re.I):
        tags.add(inst.split(".")[0].upper())
    return tags


def reconcile_ledger(
    ledger: dict[str, Any],
    *,
    physical_io_map_csv: Path | str | None = None,
    l5x_path: Path | str | None = None,
    machine: str | None = None,
    canonical_device_names: set[str] | None = None,
) -> dict[str, Any]:
    """Reconcile source candidates against map/L5X; compute conservation metrics.

    If canonical_device_names is provided, any source candidate whose name is
    absent from that set (and not foreign/spare/alias) is SILENTLY_MISSING.
    This enables the critical regression: drop from canonical discovery while
    CSV remains self-consistent → FAIL.
    """
    mach = (machine or ledger.get("machine") or "").strip().upper()
    map_path = Path(physical_io_map_csv) if physical_io_map_csv else None
    l5x = Path(l5x_path) if l5x_path else None
    phys_map = _load_physical_io_map(map_path)
    tags = _l5x_tag_set(l5x)
    writers = _io_map_writers(l5x)

    # Default canonical set = names present in physical_io_map + safety canonical hints
    if canonical_device_names is None:
        canonical_device_names = set(phys_map.keys())
        for c in ledger.get("candidates") or []:
            hint = _norm(c.get("canonical_hint")).upper()
            if hint:
                canonical_device_names.add(hint)

    rows: list[dict[str, Any]] = []
    buckets: Counter[str] = Counter()
    silent_devices: list[str] = []
    endpoints_seen: dict[str, str] = {}

    for c in list(ledger.get("candidates") or []):
        row = dict(c)
        name = _norm(row.get("source_signal"))
        name_u = name.upper()
        rm = _norm(row.get("machine")).upper()
        ownership = _norm(row.get("ownership_hint")).upper()
        forced = _norm(row.get("forced_status_hint")).upper()
        parent = _alias_parent(name) or _norm(row.get("alias_hint")) or None
        endpoint = _norm(row.get("endpoint"))
        status = ""
        reason = ""
        canonical = _norm(row.get("canonical_hint")) or name
        alias_parent = ""

        # 1) Explicit foreign machine
        if ownership == "FOREIGN" or (
            rm and rm not in _MACHINE_WILDCARD and mach and rm != mach
        ):
            status = STATUS_FOREIGN
            reason = f"Machine_Name={rm or row.get('machine')} != {mach}"
        # 2) Spare
        elif _is_spare_name(name):
            status = STATUS_SPARE
            reason = "spare/invalid token"
        # 3) Forced unsupported from safety evidence
        elif forced == STATUS_UNSUPPORTED:
            status = STATUS_UNSUPPORTED
            reason = _norm(row.get("reason")) or "unsupported_interface"
            canonical = name
        # 4) Alias child (only if parent exists among candidates/canonical)
        elif parent:
            parent_u = parent.upper()
            parent_in_canon = parent_u in {x.upper() for x in canonical_device_names} or any(
                _norm(x.get("source_signal")).upper() == parent_u
                for x in (ledger.get("candidates") or [])
            )
            if parent_in_canon and parent_u != name_u:
                status = f"{STATUS_ALIAS}:{parent}"
                alias_parent = parent
                canonical = parent
                reason = "alias/feedback child of canonical parent"
        # 5) Present in physical_io_map
        if not status and name_u in phys_map:
            mrow = phys_map[name_u]
            mapped_y = _norm(mrow.get("mapped")).upper() in {"Y", "YES", "TRUE", "1"}
            canonical = _norm(mrow.get("fortna_name")) or name
            endpoint = endpoint or _norm(mrow.get("module_data_ref"))
            row["word"] = row.get("word") or _norm(mrow.get("fortna_bank"))
            row["bit"] = row.get("bit") or _norm(mrow.get("fortna_bit"))
            row["direction"] = row.get("direction") or _norm(mrow.get("direction"))
            if mapped_y:
                status = STATUS_MAPPED
                reason = "present in physical_io_map mapped=Y"
            else:
                status = STATUS_REVIEW
                reason = _norm(mrow.get("notes")) or "physical_io_map mapped=N"
        # 6) In L5X tags / IO_MAP writers without CSV row
        if not status and name_u in tags:
            status = STATUS_MAPPED
            reason = "present as L5X tag (no CSV row)"
            canonical = name
        # 7) Still in canonical discovery as REVIEW
        if not status and name_u in {x.upper() for x in canonical_device_names}:
            status = STATUS_REVIEW
            reason = "in canonical discovery but not mapped"
        # 8) Wildcard / own claim with word/bit but missing from canonical → SILENT
        if not status:
            # Physical channels are inventory evidence of module bits — never
            # SILENTLY_MISSING (they collapse to SPARE or attach to a named device).
            is_channel = (
                _norm(row.get("source_type")) == "physical_word_map"
                or _norm(row.get("highlight")).upper() == "PHYSICAL_CHANNEL"
                or name_u.startswith("CH:")
                or ":" in name  # AENTR1:I.Data[n].b style channel tokens
            )
            if is_channel and not (_is_pb_or_control(name) or _is_safety_name(name)):
                status = STATUS_SPARE
                reason = "active-controller physical channel (spare/occupancy evidence)"
            else:
                status = STATUS_SILENT
                reason = "present in RUN source evidence; absent from canonical discovery and physical_io_map"
                silent_devices.append(name)

        # Endpoint de-dup note for aliases
        if endpoint and status.startswith(STATUS_ALIAS):
            endpoints_seen.setdefault(endpoint, alias_parent or canonical)
        elif endpoint and status == STATUS_MAPPED:
            endpoints_seen.setdefault(endpoint, canonical)

        gen_tag = ""
        if name_u in tags:
            gen_tag = name
        writer = "Y" if name_u in writers else "N"

        row["canonical_device"] = canonical
        row["alias_parent"] = alias_parent
        row["final_status"] = status
        row["generated_tag"] = gen_tag
        row["io_map_writer"] = writer
        row["reason"] = reason
        row["endpoint"] = endpoint or row.get("endpoint") or ""
        rows.append(row)

        bucket_key = status.split(":", 1)[0] if status.startswith(STATUS_ALIAS) else status
        buckets[bucket_key] += 1

    source_n = len(rows)
    mapped = buckets[STATUS_MAPPED]
    spare = buckets[STATUS_SPARE]
    foreign = buckets[STATUS_FOREIGN]
    alias_child = buckets[STATUS_ALIAS]
    review = buckets[STATUS_REVIEW]
    unsupported = buckets[STATUS_UNSUPPORTED]
    silently_missing = buckets[STATUS_SILENT]
    accounted = mapped + spare + foreign + alias_child + review + unsupported + silently_missing
    conservation_ok = (
        source_n > 0
        and accounted == source_n
        and silently_missing == 0
        and bool(ledger.get("ledger_complete", True))
    )

    # Coverage vs upstream denominator
    classified_non_silent = mapped + spare + foreign + alias_child + review + unsupported
    if not ledger.get("ledger_complete", True) or source_n == 0:
        coverage_status = "NOT_PROVEN"
        coverage_pct = None
    else:
        coverage_status = "PROVEN"
        coverage_pct = round(100.0 * classified_non_silent / max(1, source_n), 2)

    failures = [
        {
            "code": "IO_SOURCE_CONSERVATION_FAILURE",
            "signature": f"IO:SOURCE_CONSERVATION_FAILURE:{d}",
            "device": d,
        }
        for d in silent_devices
    ]

    # Highlight slices
    def _hl(rows_in: list[dict], *keys: str) -> list[dict]:
        want = {k.upper() for k in keys}
        return [
            r
            for r in rows_in
            if _norm(r.get("highlight")).upper() in want
            or (
                "PUSHBUTTON" in want
                and _is_pb_or_control(_norm(r.get("source_signal")))
            )
        ]

    return {
        "ori": "IO_SOURCE_CONSERVATION",
        "machine": mach,
        "reconciled_at": _ts(),
        "ledger_complete": bool(ledger.get("ledger_complete", True)),
        "coverage_status": coverage_status,
        "coverage_pct": coverage_pct,
        "source_physical_candidates": source_n,
        "canonical_physical_devices": len(canonical_device_names or []),
        "mapped": mapped,
        "spare": spare,
        "foreign": foreign,
        "alias_child": alias_child,
        "review": review,
        "unsupported": unsupported,
        "silently_missing": silently_missing,
        "accounted": accounted,
        "conservation_ok": conservation_ok,
        "silently_missing_devices": silent_devices,
        "failures": failures,
        "rows": rows,
        "pushbuttons": _hl(rows, "PUSHBUTTON_CONTROL", "PUSHBUTTON"),
        "safety_rows": _hl(rows, "ESPB", "ESLS", "ESR", "MCR", "SAFETY", "ESTOP"),
        "physical_io_map_csv": str(map_path) if map_path else "",
        "l5x": str(l5x) if l5x else "",
        "safety_meta": ledger.get("safety_meta") or {},
    }


def write_ledger_artifacts(
    reconciled: dict[str, Any],
    out_dir: Path | str,
    *,
    stem: str = "RUN_IO_SOURCE_LEDGER",
) -> dict[str, str]:
    """Write JSON + CSV engineer tables."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / f"{stem}.json"
    csv_path = out / f"{stem}.csv"
    pb_path = out / f"{stem}_PUSHBUTTONS.csv"
    safety_path = out / f"{stem}_SAFETY.csv"

    json_path.write_text(json.dumps(reconciled, indent=2, default=str), encoding="utf-8")

    cols = [
        "source_signal",
        "source_file",
        "source_type",
        "machine",
        "module",
        "slot",
        "word",
        "bit",
        "direction",
        "endpoint",
        "canonical_device",
        "alias_parent",
        "final_status",
        "generated_tag",
        "io_map_writer",
        "highlight",
        "reason",
    ]

    def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in cols})

    _write_csv(csv_path, list(reconciled.get("rows") or []))
    _write_csv(pb_path, list(reconciled.get("pushbuttons") or []))
    _write_csv(safety_path, list(reconciled.get("safety_rows") or []))
    return {
        "json": str(json_path),
        "csv": str(csv_path),
        "pushbuttons_csv": str(pb_path),
        "safety_csv": str(safety_path),
    }


def audit_source_conservation(
    reconciled: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return auditor-style failures when conservation fails."""
    if reconciled.get("conservation_ok"):
        return []
    fails = list(reconciled.get("failures") or [])
    if not fails and int(reconciled.get("silently_missing") or 0) > 0:
        fails = [
            {
                "code": "IO_SOURCE_CONSERVATION_FAILURE",
                "signature": f"IO:SOURCE_CONSERVATION_FAILURE:{d}",
                "device": d,
            }
            for d in (reconciled.get("silently_missing_devices") or ["UNKNOWN"])
        ]
    if not fails and not reconciled.get("ledger_complete"):
        fails = [
            {
                "code": "IO_SOURCE_LEDGER_NOT_PROVEN",
                "signature": "IO:SOURCE_LEDGER_NOT_PROVEN",
                "device": "",
            }
        ]
    if not fails and int(reconciled.get("accounted") or 0) != int(
        reconciled.get("source_physical_candidates") or 0
    ):
        fails = [
            {
                "code": "IO_SOURCE_CONSERVATION_MISCOUNT",
                "signature": "IO:SOURCE_CONSERVATION_MISCOUNT",
                "device": "",
            }
        ]
    return fails

# ---------------------------------------------------------------------------
# SOURCE_EVIDENCE → CANONICAL_PHYSICAL_DEVICE (unique-device layer)
# ---------------------------------------------------------------------------


def build_source_evidence_ledger(
    run_dir: Path | str,
    machine: str,
) -> dict[str, Any]:
    """Alias: upstream source observations (one row per evidence record)."""
    led = build_run_io_source_ledger(run_dir, machine)
    led["ori"] = "SOURCE_EVIDENCE_LEDGER"
    led["source_evidence_rows"] = led.get("source_physical_candidates")
    led["evidence"] = led.get("candidates") or []
    return led


def _endpoint_key(endpoint: str = "", word: str = "", bit: str = "", direction: str = "") -> str:
    ep = _norm(endpoint)
    if ep:
        return ep.upper()
    w, b = _norm(word), _norm(bit)
    if w and b != "":
        return f"WB:{w}.{b}:{_norm(direction).upper() or '?'}"
    return ""


def _device_type_from_highlight(highlight: str, name: str) -> str:
    h = _norm(highlight).upper()
    if h in {"ESPB", "ESLS", "ESR", "MCR", "ESTOP", "SAFETY", "CS"}:
        return h if h != "ESTOP" else "ESPB"
    if h in {"PUSHBUTTON_CONTROL", "PUSHBUTTON"} or _is_pb_or_control(name):
        return "PUSHBUTTON_CONTROL"
    if h == "PHYSICAL_CHANNEL":
        return "PHYSICAL_CHANNEL"
    if _is_safety_name(name):
        if re.search(r"ESPB", name, re.I):
            return "ESPB"
        if re.search(r"ESLS", name, re.I):
            return "ESLS"
        if re.search(r"ESR", name, re.I):
            return "ESR"
        if re.search(r"MCR", name, re.I):
            return "MCR"
        return "SAFETY"
    return h or "IO"


def _is_critical_device(device: dict[str, Any]) -> bool:
    dt = _norm(device.get("device_type") or device.get("highlight")).upper()
    if dt in CRITICAL_HIGHLIGHTS:
        return True
    name = _norm(device.get("canonical_name") or device.get("source_signal"))
    return _is_pb_or_control(name) or _is_safety_name(name)


def resolve_ownership_deterministic(
    *,
    machine: str,
    source_machine: str,
    word: str,
    bit: str,
    direction: str = "",
    run_dir: Path | str | None = None,
    resolver: Any = None,
) -> dict[str, Any]:
    """Deterministic ownership. N/A is uncertainty — never invent LOCAL/FOREIGN."""
    mach = _norm(machine).upper()
    sm = _norm(source_machine).upper()
    out: dict[str, Any] = {
        "ownership": "UNKNOWN",
        "confidence": "UNKNOWN",
        "endpoint": "",
        "module": "",
        "slot": "",
        "reason": "",
        "word_in_active_configio": None,
        "deterministic_code": "",
    }
    if sm and sm not in _MACHINE_WILDCARD and mach and sm != mach:
        out.update(
            {
                "ownership": "FOREIGN",
                "confidence": "PROVEN",
                "reason": f"Machine_Name={sm} != {mach}",
                "deterministic_code": "EXPLICIT_FOREIGN_MACHINE",
            }
        )
        return out
    if sm and sm == mach:
        out["ownership"] = "LOCAL"
        out["confidence"] = "PROVEN"
        out["deterministic_code"] = "EXPLICIT_OWN_MACHINE"
        out["reason"] = f"Machine_Name={sm}"

    # Endpoint via PhysicalWordResolver
    hit = None
    word_in_map = None
    try:
        pwr = resolver
        if pwr is None and run_dir is not None:
            from fortna_physical_word_resolver import PhysicalWordResolver

            pwr = PhysicalWordResolver(Path(run_dir), machine)
        if pwr is not None and _norm(word):
            wm = {}
            try:
                wm = pwr.io_word_map() or {}
            except Exception:
                wm = {}
            word_in_map = _norm(word) in wm or (word.isdigit() and int(word) in wm)
            out["word_in_active_configio"] = bool(word_in_map)
            hit = pwr.resolve(word, bit) if _norm(bit) != "" else None
    except Exception as ex:  # noqa: BLE001
        out["resolver_error"] = str(ex)[:200]

    if hit and isinstance(hit, dict):
        rio = _norm(hit.get("rio_name") or hit.get("adapter"))
        slot = hit.get("eip_slot") if hit.get("eip_slot") is not None else hit.get("flex_slot")
        direction_h = _norm(hit.get("direction") or direction).upper() or "I"
        # Build Logix-ish endpoint when possible
        child = _norm(hit.get("child_name"))
        data_index = hit.get("data_index")
        bit_n = hit.get("bit") if hit.get("bit") is not None else bit
        if child and data_index is not None:
            ep = f"{rio}:{slot}:{direction_h}.Data.{bit_n}" if rio and slot is not None else child
        elif rio and slot is not None:
            ep = f"{rio}:{slot}:{direction_h}.Data.{bit_n}"
        else:
            ep = _norm(hit.get("channel")) or f"{rio}:{bit_n}"
        out["endpoint"] = ep
        out["module"] = rio
        out["slot"] = str(slot if slot is not None else "")
        out["ownership"] = "LOCAL"
        out["confidence"] = "PROVEN"
        out["deterministic_code"] = "ENDPOINT_ON_ACTIVE_CONTROLLER"
        out["reason"] = f"PhysicalWordResolver → {ep} ({hit.get('resolve_how')})"
        out["resolve_hit"] = {k: hit.get(k) for k in (
            "rio_name", "type", "panel", "resolve_how", "flex_slot", "eip_slot", "direction"
        )}
        return out

    if sm in _MACHINE_WILDCARD or not sm:
        if word_in_map is False:
            out["ownership"] = "UNKNOWN"
            out["confidence"] = "DERIVED"
            out["deterministic_code"] = "WORD_NOT_IN_ACTIVE_CONFIGIO"
            out["reason"] = (
                f"Machine_Name=N/A and word {word} absent from active-controller Configio/EIP map"
            )
        elif out.get("ownership") != "LOCAL":
            out["ownership"] = "UNKNOWN"
            out["deterministic_code"] = out.get("deterministic_code") or "OWNERSHIP_UNRESOLVED"
            out["reason"] = out.get("reason") or "Machine_Name=N/A; endpoint unresolved"
    return out


def _is_physical_device_row(d: dict[str, Any]) -> bool:
    """True when the row belongs in the physical-field device denominator."""
    st = _norm(d.get("final_status")).split(":")[0]
    ec = _norm(d.get("evidence_class"))
    dt = _norm(d.get("device_type"))
    own = _norm(d.get("ownership")).upper()
    if st == STATUS_INTERNAL or ec == EVIDENCE_INTERNAL or dt == "INTERNAL_LOGICAL" or own == "INTERNAL":
        return False
    if ec == EVIDENCE_CHANNEL_OCCUPANCY:
        return False
    if st == STATUS_FOREIGN or own == "FOREIGN":
        return False  # foreign tracked separately
    return True


def _is_proven_spare_device(d: dict[str, Any]) -> bool:
    st = _norm(d.get("final_status")).split(":")[0]
    if st != STATUS_SPARE:
        return False
    ec = _norm(d.get("evidence_class"))
    code = _norm(d.get("deterministic_code")).upper()
    if ec == EVIDENCE_PROVEN_SPARE or code in {"PROVEN_SPARE_CHANNEL", "ENGINEER_MARK_SPARE"}:
        return True
    return _is_proven_spare_channel(d)


def recompute_physical_io_metrics(canonical: dict[str, Any]) -> dict[str, Any]:
    """Three separate metrics — SOURCE CONSERVATION / PHYSICAL RESOLUTION / GENERATED I/O.

    Internal Fortna logic is excluded from the physical-device denominator.
    Unproven channel occupancy is excluded. Only proven spares count as SPARE.
    """
    devices = list(canonical.get("devices") or [])
    alias_children = list(canonical.get("alias_children") or [])
    evidence_recon = canonical.get("evidence_reconcile") or {}
    missing_evidence = list(canonical.get("missing_evidence_links") or [])
    unproven_occ = int(canonical.get("unproven_channel_occupancy") or 0)
    source_rows = int(
        canonical.get("source_evidence_rows")
        or evidence_recon.get("source_physical_candidates")
        or len(canonical.get("rows") or [])
        or 0
    )

    foreign_list = [
        d
        for d in devices
        if _norm(d.get("final_status")).split(":")[0] == STATUS_FOREIGN
        or _norm(d.get("ownership")).upper() == "FOREIGN"
        or _norm(d.get("evidence_class")) == EVIDENCE_FOREIGN
    ]
    internal_list = [
        d
        for d in devices
        if _norm(d.get("final_status")).split(":")[0] == STATUS_INTERNAL
        or _norm(d.get("evidence_class")) == EVIDENCE_INTERNAL
        or _norm(d.get("device_type")) == "INTERNAL_LOGICAL"
        or _norm(d.get("ownership")).upper() == "INTERNAL"
    ]
    # Downgrade unproven SPARE masquerading as resolved
    for d in devices:
        st = _norm(d.get("final_status")).split(":")[0]
        if st == STATUS_SPARE and not _is_proven_spare_device(d):
            d["final_status"] = STATUS_REVIEW
            d["evidence_class"] = EVIDENCE_REVIEW
            d["reason"] = (
                (d.get("reason") or "")
                + "; unproven spare demoted — requires explicit unused/spare evidence"
            ).strip("; ")
            d["deterministic_code"] = "UNPROVEN_SPARE_DEMOTED"

    physical_list = [d for d in devices if _is_physical_device_row(d)]
    proven_spares = [d for d in physical_list if _is_proven_spare_device(d)]

    def _st(d: dict[str, Any]) -> str:
        return _norm(d.get("final_status")).split(":")[0]

    mapped = [d for d in physical_list if _st(d) == STATUS_MAPPED]
    review = [
        d
        for d in physical_list
        if _st(d) in {STATUS_REVIEW, STATUS_ENGINEER_REQUIRED}
    ]
    unsupported = [d for d in physical_list if _st(d) == STATUS_UNSUPPORTED]
    eng_confirmed = [d for d in physical_list if _st(d) == STATUS_ENGINEER_CONFIRMED]
    silent = [d for d in devices if _st(d) == STATUS_SILENT]

    # Physical resolution: classified correctly among physical field devices
    # Proven spare + mapped + unsupported + engineer confirmed count as resolved.
    resolved_physical = [
        d
        for d in physical_list
        if _st(d)
        in {STATUS_MAPPED, STATUS_SPARE, STATUS_UNSUPPORTED, STATUS_ENGINEER_CONFIRMED}
        and ( _st(d) != STATUS_SPARE or _is_proven_spare_device(d) )
    ]
    phys_denom = len(physical_list)
    phys_res_pct = round(100.0 * len(resolved_physical) / max(1, phys_denom), 2) if phys_denom else 0.0

    # Generated physical I/O: mapped among named physical field devices (exclude proven-spare channels)
    named_physical = [
        d
        for d in physical_list
        if _norm(d.get("device_type")) != "PHYSICAL_CHANNEL"
        or _st(d) != STATUS_SPARE
    ]
    named_field = [
        d
        for d in physical_list
        if _norm(d.get("device_type")) != "PHYSICAL_CHANNEL"
    ]
    gen_mapped = sum(1 for d in named_field if _st(d) == STATUS_MAPPED)
    gen_pct = round(100.0 * gen_mapped / max(1, len(named_field)), 2) if named_field else 0.0

    # Source conservation: did evidence disappear?
    silent_n = len(silent) + int(evidence_recon.get("silently_missing") or 0) + len(missing_evidence)
    accounted = (
        len(physical_list)
        + len(foreign_list)
        + len(internal_list)
        + len(alias_children)
        + unproven_occ
    )
    # Prefer evidence_recon conservation when available
    if evidence_recon.get("conservation_ok") is True and silent_n == 0:
        source_cons_pct = 100.0
    elif source_rows > 0:
        conserved = max(0, source_rows - silent_n)
        source_cons_pct = round(100.0 * conserved / source_rows, 2)
    else:
        source_cons_pct = 100.0 if silent_n == 0 else 0.0

    critical_unresolved = [
        d
        for d in physical_list
        if d.get("critical")
        and _st(d)
        not in {
            STATUS_MAPPED,
            STATUS_SPARE,
            STATUS_UNSUPPORTED,
            STATUS_ENGINEER_CONFIRMED,
            STATUS_FOREIGN,
            STATUS_INTERNAL,
        }
    ]

    out = {
        "SOURCE_CONSERVATION_PCT": source_cons_pct,
        "PHYSICAL_DEVICE_RESOLUTION_PCT": phys_res_pct,
        "GENERATED_PHYSICAL_IO_PCT": gen_pct,
        "unique_physical_devices": phys_denom,
        "mapped_physical_devices": len(mapped),
        "proven_physical_spares": len(proven_spares),
        "foreign_devices": len(foreign_list),
        "review_physical_devices": len(review),
        "unsupported_physical_devices": len(unsupported),
        "unique_engineer_confirmed": len(eng_confirmed),
        "unique_silently_missing": len(silent),
        "internal_logical_excluded": len(internal_list),
        "unproven_channel_occupancy": unproven_occ,
        "accounted_observations": accounted,
        "critical_unresolved_list": critical_unresolved,
        "unique_foreign_devices_list": foreign_list,
        "unique_local_physical_list": physical_list,
        "named_physical_field_devices": len(named_field),
        "generated_mapped_count": gen_mapped,
    }
    # Mutate canonical in place for escalation / callers that discard the return.
    canonical.update(
        {
            "SOURCE_CONSERVATION_PCT": source_cons_pct,
            "PHYSICAL_DEVICE_RESOLUTION_PCT": phys_res_pct,
            "GENERATED_PHYSICAL_IO_PCT": gen_pct,
            "device_resolution_coverage_pct": phys_res_pct,
            "generated_io_coverage_pct": gen_pct,
            "unique_physical_devices": phys_denom,
            "unique_physical_candidates": phys_denom,
            "unique_local": phys_denom,
            "unique_foreign": len(foreign_list),
            "unique_mapped": len(mapped),
            "unique_review": len(review),
            "unique_unsupported": len(unsupported),
            "unique_spare": len(proven_spares),
            "proven_physical_spares": len(proven_spares),
            "unique_engineer_confirmed": len(eng_confirmed),
            "unique_internal_logical": len(internal_list),
            "critical_unresolved_count": len(critical_unresolved),
            "critical_unresolved": [
                {
                    "canonical_device": d.get("canonical_name"),
                    "status": d.get("final_status"),
                    "reason": d.get("reason"),
                }
                for d in critical_unresolved
            ],
            "engineering_resolution_ok": phys_res_pct >= RESOLUTION_THRESHOLD_PCT
            and len(critical_unresolved) == 0,
            "metrics": {
                "SOURCE_CONSERVATION_PCT": source_cons_pct,
                "PHYSICAL_DEVICE_RESOLUTION_PCT": phys_res_pct,
                "GENERATED_PHYSICAL_IO_PCT": gen_pct,
                "note": "Three separate metrics — do not combine",
            },
        }
    )
    safety = canonical.get("safety")
    if isinstance(safety, dict):
        safety["review"] = sum(
            1
            for d in devices
            if d.get("device_type") in {"ESPB", "ESLS", "ESR", "MCR", "SAFETY", "ESTOP"}
            and _norm(d.get("final_status")).split(":")[0]
            in {STATUS_REVIEW, STATUS_ENGINEER_REQUIRED}
        )
        safety["assignable"] = sum(
            1
            for d in devices
            if d.get("assignable")
            and d.get("device_type") in {"ESPB", "ESLS", "ESR", "MCR", "SAFETY", "ESTOP"}
        )
        canonical["safety"] = safety
    return out


def build_canonical_device_ledger(
    evidence_ledger: dict[str, Any],
    *,
    machine: str | None = None,
    run_dir: Path | str | None = None,
    physical_io_map_csv: Path | str | None = None,
    l5x_path: Path | str | None = None,
    canonical_device_names: set[str] | None = None,
    confirmations_path: Path | str | None = None,
    apply_engineer_confirmations: bool = True,
) -> dict[str, Any]:
    """Collapse source evidence into unique canonical physical devices."""
    mach = (machine or evidence_ledger.get("machine") or "").strip()
    mach_u = mach.upper()
    run_p = Path(run_dir or evidence_ledger.get("run_dir") or "")
    if run_p.is_dir() and (run_p / "RUN" / "project.cfg").is_file():
        run_p = run_p / "RUN"

    # First reconcile evidence rows (conservation layer)
    evidence_recon = reconcile_ledger(
        evidence_ledger,
        physical_io_map_csv=physical_io_map_csv,
        l5x_path=l5x_path,
        machine=mach,
        canonical_device_names=canonical_device_names,
    )
    evidence_rows = list(evidence_recon.get("rows") or [])
    phys_map = _load_physical_io_map(Path(physical_io_map_csv) if physical_io_map_csv else None)

    resolver = None
    active_words: set[str] = set()
    try:
        if run_p.is_dir():
            from fortna_physical_word_resolver import PhysicalWordResolver

            resolver = PhysicalWordResolver(run_p, mach)
            active_words = {str(k) for k in (resolver.io_word_map() or {})}
    except Exception:
        resolver = None

    # Index named evidence (exclude unnamed physical channels from unique device seed)
    by_name: dict[str, list[dict[str, Any]]] = {}
    channel_rows: list[dict[str, Any]] = []
    for r in evidence_rows:
        name = _norm(r.get("source_signal"))
        st = _norm(r.get("final_status"))
        is_channel = (
            _norm(r.get("source_type")) == "physical_word_map"
            or _norm(r.get("highlight")).upper() == "PHYSICAL_CHANNEL"
            or name.upper().startswith("CH:")
        )
        if is_channel and not (_is_pb_or_control(name) or _is_safety_name(name)):
            channel_rows.append(r)
            continue
        key = name.upper()
        by_name.setdefault(key, []).append(r)

    devices: list[dict[str, Any]] = []
    evidence_to_canonical: dict[str, str] = {}
    alias_children: list[dict[str, Any]] = []

    # Pass 1: named devices
    for name_u, rows in sorted(by_name.items()):
        # Alias child?
        sample = rows[0]
        parent = _alias_parent(sample.get("source_signal") or "") or _norm(sample.get("alias_hint"))
        parent_u = parent.upper() if parent else ""
        if parent_u and parent_u in by_name and parent_u != name_u:
            for r in rows:
                evidence_to_canonical[_norm(r.get("id")) or _candidate_id(
                    r.get("source_file"), r.get("source_signal"), r.get("word"), r.get("bit")
                )] = parent_u
            alias_children.append(
                {
                    "canonical_name": _norm(sample.get("source_signal")),
                    "alias_parent": parent,
                    "final_status": f"{STATUS_ALIAS}:{parent}",
                    "source_evidence_count": len(rows),
                    "device_type": _device_type_from_highlight(sample.get("highlight"), sample.get("source_signal")),
                }
            )
            continue

        # Merge fields across evidence
        words = [_norm(r.get("word")) for r in rows if _norm(r.get("word"))]
        bits = [_norm(r.get("bit")) for r in rows if _norm(r.get("bit")) != ""]
        endpoints = [_norm(r.get("endpoint")) for r in rows if _norm(r.get("endpoint"))]
        machines = [_norm(r.get("machine")) for r in rows]
        highlights = [_norm(r.get("highlight")) for r in rows if _norm(r.get("highlight"))]
        directions = [_norm(r.get("direction")) for r in rows if _norm(r.get("direction"))]
        statuses = [_norm(r.get("final_status")) for r in rows]

        word = next((w for w in words if w), "")
        bit = next((b for b in bits if b != ""), "")
        endpoint = next((e for e in endpoints if e), "")
        direction = next((d for d in directions if d), "")
        highlight = next((h for h in highlights if h), "")
        # Prefer explicit foreign machine if any evidence is foreign
        source_machine = ""
        for m in machines:
            mu = m.upper()
            if mu and mu not in _MACHINE_WILDCARD and mu != mach_u:
                source_machine = m
                break
        if not source_machine:
            for m in machines:
                if m.upper() == mach_u:
                    source_machine = m
                    break
        if not source_machine:
            source_machine = next((m for m in machines if m), "N/A")

        own = resolve_ownership_deterministic(
            machine=mach,
            source_machine=source_machine,
            word=word,
            bit=bit,
            direction=direction,
            run_dir=run_p if run_p.is_dir() else None,
            resolver=resolver,
        )
        if own.get("endpoint") and not endpoint:
            endpoint = _norm(own.get("endpoint"))

        semantics = _classify_device_semantics(
            sample.get("source_signal") or "",
            highlight=highlight,
            source_type=_norm(sample.get("source_type")),
        )
        equipment_class = _norm(semantics.get("equipment_class")) or "UNKNOWN"
        evidence_class = _norm(semantics.get("evidence_class")) or EVIDENCE_REVIEW
        device_type = _equipment_to_device_type(
            equipment_class, highlight, sample.get("source_signal") or ""
        )

        # Status from evidence reconcile + ownership + semantics
        status = ""
        reason = ""
        if evidence_class == EVIDENCE_INTERNAL or equipment_class == "INTERNAL_LOGICAL":
            status = STATUS_INTERNAL
            reason = "; ".join(semantics.get("reasons") or []) or "internal/logical Fortna evidence"
            own["ownership"] = "INTERNAL"
            evidence_class = EVIDENCE_INTERNAL
        elif own.get("ownership") == "FOREIGN" or any(s.startswith(STATUS_FOREIGN) or s == STATUS_FOREIGN for s in statuses):
            status = STATUS_FOREIGN
            reason = own.get("reason") or next((r.get("reason") for r in rows if r.get("final_status") == STATUS_FOREIGN), "foreign")
            evidence_class = EVIDENCE_FOREIGN
        elif any(s == STATUS_UNSUPPORTED for s in statuses):
            status = STATUS_UNSUPPORTED
            reason = next((r.get("reason") for r in rows if r.get("final_status") == STATUS_UNSUPPORTED), "unsupported")
        elif any(s == STATUS_MAPPED for s in statuses) or name_u in phys_map and _norm(phys_map[name_u].get("mapped")).upper() in {"Y", "YES", "1", "TRUE"}:
            status = STATUS_MAPPED
            reason = "mapped in physical_io_map / L5X"
            if name_u in phys_map and not endpoint:
                endpoint = _norm(phys_map[name_u].get("module_data_ref"))
            own["ownership"] = own.get("ownership") if own.get("ownership") == "FOREIGN" else "LOCAL"
            if evidence_class not in {EVIDENCE_FOREIGN, EVIDENCE_INTERNAL}:
                evidence_class = EVIDENCE_PHYSICAL_FIELD
        elif any(s == STATUS_SILENT for s in statuses):
            # Explicit discovery-drop regression: only keep SILENT when caller
            # provided a canonical set that excludes this name.
            if canonical_device_names is not None and name_u not in {
                x.upper() for x in canonical_device_names
            }:
                status = STATUS_SILENT
                reason = "silently missing from canonical discovery"
            else:
                status = STATUS_REVIEW
                reason = (
                    "present in RUN evidence; awaiting mapping / ownership resolution"
                )
                evidence_class = EVIDENCE_REVIEW
        elif own.get("ownership") == "LOCAL" and own.get("endpoint"):
            # Endpoint proven local but not yet in map → REVIEW until generated/mapped
            if name_u in phys_map:
                mapped_y = _norm(phys_map[name_u].get("mapped")).upper() in {"Y", "YES", "1", "TRUE"}
                status = STATUS_MAPPED if mapped_y else STATUS_REVIEW
                reason = "local endpoint proven; " + ("mapped" if mapped_y else "awaiting map/generation")
            else:
                status = STATUS_REVIEW
                reason = "local endpoint proven via PhysicalWordResolver; not yet in physical_io_map"
            if evidence_class not in {EVIDENCE_FOREIGN, EVIDENCE_INTERNAL}:
                evidence_class = EVIDENCE_PHYSICAL_FIELD if status == STATUS_MAPPED else (
                    EVIDENCE_PHYSICAL_FIELD if device_type != "INTERNAL_LOGICAL" else EVIDENCE_REVIEW
                )
                if status == STATUS_REVIEW:
                    evidence_class = EVIDENCE_REVIEW if semantics.get("needs_review") else EVIDENCE_PHYSICAL_FIELD
        else:
            status = STATUS_REVIEW
            reason = own.get("reason") or "ownership or mapping unresolved"
            if evidence_class == EVIDENCE_PHYSICAL_FIELD and not semantics.get("needs_review"):
                # Recognizable field device stays physical even while ownership is open
                evidence_class = EVIDENCE_PHYSICAL_FIELD
            else:
                evidence_class = EVIDENCE_REVIEW

        # Recognizable field-device nomenclature must not silently become internal
        if device_type in CRITICAL_HIGHLIGHTS or device_type in {
            "ESPB", "ESLS", "ESR", "MCR", "PUSHBUTTON_CONTROL", "PHOTOEYE", "VFD", "MOTOR", "SAFETY"
        }:
            if evidence_class == EVIDENCE_INTERNAL:
                evidence_class = EVIDENCE_PHYSICAL_FIELD
                if status == STATUS_INTERNAL:
                    status = STATUS_REVIEW
                    reason = "field-device nomenclature overrides internal classification"
                    own["ownership"] = own.get("ownership") if own.get("ownership") not in {"INTERNAL", ""} else "UNKNOWN"

        device = {
            "canonical_name": _norm(sample.get("source_signal")),
            "physical_endpoint": endpoint,
            "direction": direction or _norm(own.get("resolve_hit", {}).get("direction") if isinstance(own.get("resolve_hit"), dict) else "") or "",
            "controller": mach if own.get("ownership") == "LOCAL" else (source_machine if own.get("ownership") == "FOREIGN" else ""),
            "source_machine": source_machine,
            "ownership": own.get("ownership") or "UNKNOWN",
            "device_type": device_type,
            "equipment_class": equipment_class,
            "evidence_class": evidence_class,
            "fortna_plus_hint": _norm(semantics.get("fortna_plus_hint")),
            "classifier_reasons": list(semantics.get("reasons") or []),
            "word": word,
            "bit": bit,
            "module": _norm(own.get("module") or sample.get("module")),
            "slot": _norm(own.get("slot") or sample.get("slot")),
            "source_evidence": [
                {
                    "source_file": r.get("source_file"),
                    "source_type": r.get("source_type"),
                    "machine": r.get("machine"),
                    "word": r.get("word"),
                    "bit": r.get("bit"),
                    "endpoint": r.get("endpoint"),
                    "final_status": r.get("final_status"),
                }
                for r in rows
            ],
            "source_evidence_count": len(rows),
            "aliases": [],
            "confidence": own.get("confidence") or semantics.get("confidence") or "UNKNOWN",
            "final_status": status,
            "reason": reason,
            "deterministic_code": own.get("deterministic_code"),
            "word_in_active_configio": own.get("word_in_active_configio"),
            "assignable": status in {STATUS_MAPPED, STATUS_ENGINEER_CONFIRMED},
            "critical": False,
            "escalation_trace": {
                "deterministic_result": own,
                "ai_api_called": False,
                "ai_result": None,
                "ai_validation": None,
                "relay_called": False,
                "relay_result": None,
                "relay_validation": None,
                "knowledge_base_evidence": [],
                "final_classification": status,
                "engineer_confirmation_required": False,
                "why_ai_not_called": "not_yet_escalated",
                "why_relay_not_called": "not_yet_escalated",
            },
        }
        device["critical"] = _is_critical_device(device)
        devices.append(device)
        for r in rows:
            eid = _norm(r.get("id")) or _candidate_id(
                r.get("source_file"), r.get("source_signal"), r.get("word"), r.get("bit")
            )
            evidence_to_canonical[eid] = name_u

    # Attach alias children onto parents
    by_canon = {d["canonical_name"].upper(): d for d in devices}
    for a in alias_children:
        parent_u = _norm(a.get("alias_parent")).upper()
        if parent_u in by_canon:
            by_canon[parent_u].setdefault("aliases", []).append(a["canonical_name"])

    # Pass 2: physical channels — spare or attach to named endpoint occupant
    named_endpoints = {
        _endpoint_key(d.get("physical_endpoint"), d.get("word"), d.get("bit"), d.get("direction")): d["canonical_name"]
        for d in devices
        if _endpoint_key(d.get("physical_endpoint"), d.get("word"), d.get("bit"), d.get("direction"))
    }
    # Also index by word.bit from named devices
    named_wb = {
        f"{_norm(d.get('word'))}.{_norm(d.get('bit'))}": d["canonical_name"]
        for d in devices
        if _norm(d.get("word")) and _norm(d.get("bit")) != ""
    }
    spare_n = 0
    attached_channels = 0
    unproven_channel_occupancy = 0
    channel_occupancy_rows: list[dict[str, Any]] = []
    for r in channel_rows:
        eid = _norm(r.get("id")) or _candidate_id(
            r.get("source_file"), r.get("source_signal"), r.get("word"), r.get("bit")
        )
        ek = _endpoint_key(r.get("endpoint"), r.get("word"), r.get("bit"), r.get("direction"))
        wb = f"{_norm(r.get('word'))}.{_norm(r.get('bit'))}"
        owner = named_endpoints.get(ek) or named_wb.get(wb)
        if owner:
            evidence_to_canonical[eid] = owner.upper()
            attached_channels += 1
            if owner.upper() in by_canon:
                by_canon[owner.upper()].setdefault("channel_evidence", []).append(
                    {"word": r.get("word"), "bit": r.get("bit"), "endpoint": r.get("endpoint")}
                )
            continue

        # Proven spare ONLY when RUN/config explicitly indicates unused/spare.
        # Unoccupied endpoint-shaped channels are occupancy evidence — not devices,
        # and MUST NOT inflate physical-device resolution percentage.
        if _is_proven_spare_channel(r):
            spare_name = _norm(r.get("source_signal")) or f"SPARE_{_norm(r.get('word'))}_{_norm(r.get('bit'))}"
            if _is_endpoint_shaped_name(spare_name) and not _is_spare_name(spare_name):
                spare_name = f"SPARE_{_norm(r.get('word'))}_{_norm(r.get('bit'))}"
            spare_dev = {
                "canonical_name": spare_name,
                "physical_endpoint": _norm(r.get("endpoint")),
                "direction": _norm(r.get("direction")),
                "controller": mach,
                "source_machine": mach,
                "ownership": "LOCAL",
                "device_type": "PHYSICAL_CHANNEL",
                "equipment_class": "PHYSICAL_CHANNEL",
                "evidence_class": EVIDENCE_PROVEN_SPARE,
                "word": _norm(r.get("word")),
                "bit": _norm(r.get("bit")),
                "module": _norm(r.get("module")),
                "slot": _norm(r.get("slot")),
                "source_evidence": [{"source_file": r.get("source_file"), "source_type": r.get("source_type")}],
                "source_evidence_count": 1,
                "aliases": [],
                "confidence": "PROVEN",
                "final_status": STATUS_SPARE,
                "reason": "proven spare — module/channel exists and RUN explicitly indicates unused/spare",
                "deterministic_code": "PROVEN_SPARE_CHANNEL",
                "assignable": False,
                "critical": False,
                "escalation_trace": {
                    "deterministic_result": {"ownership": "LOCAL", "code": "PROVEN_SPARE_CHANNEL"},
                    "ai_api_called": False,
                    "why_ai_not_called": "proven_spare_not_critical",
                    "relay_called": False,
                    "why_relay_not_called": "proven_spare_not_critical",
                    "knowledge_base_evidence": [],
                    "final_classification": STATUS_SPARE,
                    "engineer_confirmation_required": False,
                },
            }
            devices.append(spare_dev)
            evidence_to_canonical[eid] = spare_name.upper()
            spare_n += 1
            continue

        # Unproven unused channel — conserve evidence, exclude from device denominator
        occ_key = f"OCCUPANCY:{ek or wb or eid}"
        evidence_to_canonical[eid] = occ_key
        unproven_channel_occupancy += 1
        channel_occupancy_rows.append(
            {
                "occupancy_key": occ_key,
                "physical_endpoint": _norm(r.get("endpoint")),
                "word": _norm(r.get("word")),
                "bit": _norm(r.get("bit")),
                "direction": _norm(r.get("direction")),
                "module": _norm(r.get("module")),
                "slot": _norm(r.get("slot")),
                "source_signal": _norm(r.get("source_signal")),
                "evidence_class": EVIDENCE_CHANNEL_OCCUPANCY,
                "reason": "unoccupied channel without explicit spare/unused proof",
            }
        )

    # Engineer confirmations
    eng_stats = {"applied": 0, "total_confirmations": 0}
    if apply_engineer_confirmations:
        try:
            from fortna_io_engineer_confirm import apply_confirmations_to_devices, load_confirmations

            store = load_confirmations(confirmations_path)
            eng_stats = apply_confirmations_to_devices(devices, store=store)
        except Exception as ex:  # noqa: BLE001
            eng_stats["error"] = str(ex)[:200]

    # Evidence conservation: every evidence row must map to a canonical
    missing_evidence = []
    for r in evidence_rows:
        eid = _norm(r.get("id")) or _candidate_id(
            r.get("source_file"), r.get("source_signal"), r.get("word"), r.get("bit")
        )
        if eid not in evidence_to_canonical:
            # Alias rows already mapped via parent name key — try name
            nu = _norm(r.get("source_signal")).upper()
            if nu in by_canon or any(nu == a["canonical_name"].upper() for a in alias_children):
                evidence_to_canonical[eid] = nu
            else:
                missing_evidence.append(_norm(r.get("source_signal")) or eid)

    # Metrics — physical-world-first (internal Fortna logic excluded from physical denom)
    unique_all = devices  # alias children excluded from unique device list
    metrics = recompute_physical_io_metrics(
        {
            "devices": unique_all,
            "alias_children": alias_children,
            "evidence_reconcile": evidence_recon,
            "missing_evidence_links": missing_evidence,
            "unproven_channel_occupancy": unproven_channel_occupancy,
            "source_evidence_rows": len(evidence_rows),
        }
    )
    unique_foreign = metrics["unique_foreign_devices_list"]
    unique_local = metrics["unique_local_physical_list"]
    unique_mapped = metrics["mapped_physical_devices"]
    unique_review = metrics["review_physical_devices"]
    unique_unsupported = metrics["unsupported_physical_devices"]
    unique_spare = metrics["proven_physical_spares"]
    unique_engineer_confirmed = metrics["unique_engineer_confirmed"]
    unique_silent = metrics["unique_silently_missing"]
    unique_aliases = len(alias_children)
    unique_internal = metrics["internal_logical_excluded"]
    local_denom = metrics["unique_physical_devices"]
    resolution_pct = metrics["PHYSICAL_DEVICE_RESOLUTION_PCT"]
    generated_pct = metrics["GENERATED_PHYSICAL_IO_PCT"]
    source_conservation_pct = metrics["SOURCE_CONSERVATION_PCT"]
    critical_unresolved = metrics["critical_unresolved_list"]

    source_conservation_ok = bool(evidence_recon.get("conservation_ok")) and not missing_evidence and unique_silent == 0
    # Do NOT treat inflated spare% as engineering success; require meaningful physical resolution
    engineering_resolution_ok = (
        resolution_pct >= RESOLUTION_THRESHOLD_PCT and len(critical_unresolved) == 0
    )

    # Safety unique slices (physical safety candidates only)
    def _safety_unique(kind: str) -> list[dict[str, Any]]:
        return [
            d
            for d in unique_all
            if d.get("device_type") == kind
            and _norm(d.get("evidence_class")) != EVIDENCE_INTERNAL
            and _norm(d.get("final_status")) != STATUS_INTERNAL
        ]

    safety_summary = {
        "unique_ESPB": len(_safety_unique("ESPB")),
        "unique_ESLS": len(_safety_unique("ESLS")),
        "unique_ESR": len(_safety_unique("ESR")),
        "unique_MCR": len(_safety_unique("MCR")),
        "assignable": sum(
            1
            for d in unique_all
            if d.get("assignable")
            and d.get("device_type") in {"ESPB", "ESLS", "ESR", "MCR", "SAFETY", "ESTOP"}
        ),
        "review": sum(
            1
            for d in unique_all
            if d.get("device_type") in {"ESPB", "ESLS", "ESR", "MCR", "SAFETY", "ESTOP"}
            and _norm(d.get("final_status")).split(":")[0] in {STATUS_REVIEW, STATUS_ENGINEER_REQUIRED}
        ),
        "devices": [
            {
                "canonical_device": d.get("canonical_name"),
                "device_type": d.get("device_type"),
                "equipment_class": d.get("equipment_class"),
                "evidence_class": d.get("evidence_class"),
                "physical_endpoint": d.get("physical_endpoint"),
                "source_evidence_count": d.get("source_evidence_count"),
                "ownership": d.get("ownership"),
                "assignable": d.get("assignable"),
                "final_status": d.get("final_status"),
                "reason": d.get("reason"),
            }
            for d in unique_all
            if d.get("device_type") in {"ESPB", "ESLS", "ESR", "MCR", "SAFETY", "ESTOP"}
        ],
    }

    pb_devices = [d for d in unique_all if d.get("device_type") == "PUSHBUTTON_CONTROL"]

    return {
        "ori": "CANONICAL_PHYSICAL_DEVICE_LEDGER",
        "machine": mach,
        "built_at": _ts(),
        "source_evidence_rows": len(evidence_rows),
        "raw_source_observations": len(evidence_rows),
        "internal_logical_observations_excluded": unique_internal,
        "unique_physical_candidates": local_denom,
        "unique_physical_devices": local_denom,
        "unique_foreign": len(unique_foreign),
        "unique_local": local_denom,
        "unique_aliases": unique_aliases,
        "unique_mapped": unique_mapped,
        "unique_review": unique_review,
        "unique_unsupported": unique_unsupported,
        "unique_spare": unique_spare,
        "proven_physical_spares": unique_spare,
        "unique_engineer_confirmed": unique_engineer_confirmed,
        "unique_silently_missing": unique_silent,
        "unique_internal_logical": unique_internal,
        "attached_physical_channels": attached_channels,
        "unproven_channel_occupancy": unproven_channel_occupancy,
        "channel_occupancy_rows": channel_occupancy_rows[:200],
        "source_conservation_ok": source_conservation_ok,
        "SOURCE_CONSERVATION_PCT": source_conservation_pct,
        "PHYSICAL_DEVICE_RESOLUTION_PCT": resolution_pct,
        "GENERATED_PHYSICAL_IO_PCT": generated_pct,
        # Back-compat aliases (must not be mistaken for engineering coverage alone)
        "device_resolution_coverage_pct": resolution_pct,
        "generated_io_coverage_pct": generated_pct,
        "engineering_resolution_ok": engineering_resolution_ok,
        "resolution_threshold_pct": RESOLUTION_THRESHOLD_PCT,
        "critical_unresolved_count": len(critical_unresolved),
        "critical_unresolved": [
            {"canonical_device": d.get("canonical_name"), "status": d.get("final_status"), "reason": d.get("reason")}
            for d in critical_unresolved
        ],
        "devices": devices,
        "alias_children": alias_children,
        "pushbuttons": pb_devices,
        "safety": safety_summary,
        "evidence_reconcile": {
            "conservation_ok": evidence_recon.get("conservation_ok"),
            "silently_missing": evidence_recon.get("silently_missing"),
            "source_physical_candidates": evidence_recon.get("source_physical_candidates"),
            "coverage_status": evidence_recon.get("coverage_status"),
        },
        "missing_evidence_links": missing_evidence[:40],
        "engineer_confirmations": eng_stats,
        "active_configio_words": sorted(active_words)[:64],
        # Back-compat mirrors for older callers
        "conservation_ok": source_conservation_ok,
        "silently_missing": unique_silent + int(evidence_recon.get("silently_missing") or 0),
        "silently_missing_devices": list(evidence_recon.get("silently_missing_devices") or [])
        + missing_evidence[:20],
        "coverage_status": "PROVEN" if source_conservation_ok else evidence_recon.get("coverage_status"),
        "source_physical_candidates": len(evidence_rows),
        "canonical_physical_devices": local_denom,
        "mapped": unique_mapped,
        "spare": unique_spare,
        "foreign": len(unique_foreign),
        "alias_child": unique_aliases,
        "review": unique_review,
        "unsupported": unique_unsupported,
        "rows": evidence_rows,
        "metrics": {
            "SOURCE_CONSERVATION_PCT": source_conservation_pct,
            "PHYSICAL_DEVICE_RESOLUTION_PCT": resolution_pct,
            "GENERATED_PHYSICAL_IO_PCT": generated_pct,
            "note": "Three separate metrics — do not combine",
        },
    }


def write_canonical_ledger_artifacts(
    canonical: dict[str, Any],
    out_dir: Path | str,
) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    j = out / "CANONICAL_PHYSICAL_DEVICE_LEDGER.json"
    j.write_text(json.dumps(canonical, indent=2, default=str), encoding="utf-8")
    paths["json"] = str(j)

    cols = [
        "canonical_name",
        "device_type",
        "equipment_class",
        "evidence_class",
        "ownership",
        "controller",
        "source_machine",
        "word",
        "bit",
        "direction",
        "physical_endpoint",
        "module",
        "slot",
        "final_status",
        "confidence",
        "source_evidence_count",
        "assignable",
        "critical",
        "reason",
        "deterministic_code",
        "fortna_plus_hint",
    ]

    def _write(path: Path, rows: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in cols})

    _write(out / "CANONICAL_PHYSICAL_DEVICE_LEDGER.csv", list(canonical.get("devices") or []))
    paths["csv"] = str(out / "CANONICAL_PHYSICAL_DEVICE_LEDGER.csv")
    _write(out / "CANONICAL_PUSHBUTTONS.csv", list(canonical.get("pushbuttons") or []))
    paths["pushbuttons_csv"] = str(out / "CANONICAL_PUSHBUTTONS.csv")
    safety_rows = list((canonical.get("safety") or {}).get("devices") or [])
    # normalize keys
    safety_norm = []
    for s in safety_rows:
        safety_norm.append(
            {
                "canonical_name": s.get("canonical_device"),
                "device_type": s.get("device_type"),
                "ownership": s.get("ownership"),
                "physical_endpoint": s.get("physical_endpoint"),
                "final_status": s.get("final_status"),
                "source_evidence_count": s.get("source_evidence_count"),
                "assignable": s.get("assignable"),
                "reason": s.get("reason"),
            }
        )
    _write(out / "CANONICAL_SAFETY.csv", safety_norm)
    paths["safety_csv"] = str(out / "CANONICAL_SAFETY.csv")
    return paths


def audit_device_resolution(
    canonical: dict[str, Any],
    *,
    threshold_pct: float = RESOLUTION_THRESHOLD_PCT,
) -> list[dict[str, Any]]:
    """Auditor failures for engineering resolution / critical residual."""
    fails: list[dict[str, Any]] = []
    pct = float(canonical.get("device_resolution_coverage_pct") or 0.0)
    if pct < threshold_pct:
        fails.append(
            {
                "code": "IO_DEVICE_RESOLUTION_BELOW_THRESHOLD",
                "signature": f"IO:DEVICE_RESOLUTION_BELOW_THRESHOLD:{pct}<{threshold_pct}",
                "device": "",
                "detail": f"local resolution {pct}% < {threshold_pct}%",
            }
        )
    for d in canonical.get("critical_unresolved") or []:
        name = _norm(d.get("canonical_device") or d.get("name"))
        fails.append(
            {
                "code": "IO_CRITICAL_DEVICE_UNRESOLVED",
                "signature": f"IO:CRITICAL_DEVICE_UNRESOLVED:{name}",
                "device": name,
                "detail": d.get("reason") or d.get("status"),
            }
        )
    return fails

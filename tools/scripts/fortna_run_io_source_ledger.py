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

TERMINAL_STATUSES = (
    STATUS_MAPPED,
    STATUS_SPARE,
    STATUS_FOREIGN,
    STATUS_ALIAS,
    STATUS_REVIEW,
    STATUS_UNSUPPORTED,
)

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


def _is_pb_or_control(name: str) -> bool:
    return bool(_PB_RE.search(_norm(name)))


def _is_safety_name(name: str) -> bool:
    u = _norm(name).upper()
    if u.endswith("_AUX") and re.search(r"(?:ESR|MCR|ES|ESPB|ESLS)", u):
        return True
    return bool(re.search(r"^ESPB|^ESLS|^ESR\d|^MCR\d|ESLS\d|ESPB\d", u))


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
            # Physical channel rows without names are REVIEW if unresolved
            if row.get("source_type") == "physical_word_map" and not re.match(
                r"^[A-Za-z]", name
            ):
                status = STATUS_REVIEW
                reason = "unnamed physical channel"
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

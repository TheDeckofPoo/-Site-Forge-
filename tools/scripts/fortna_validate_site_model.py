#!/usr/bin/env python3
"""Validate a SiteModel JSON for common RUN-derived integrity issues (Validator V2).

Severity:
  INFO | WARNING | CONFIGURATION_REQUIRED | GENERATION_BLOCKED

Checks include:
  - active conveyor missing motor
  - active VFD with no owner
  - PE role references missing sensor
  - Jamcheck references missing conveyor
  - Fulljam references stale equipment
  - Motor chain references inactive motor
  - Saw lane references unavailable equipment
  - Sorter references missing encoder
  - MsgMap / communications references missing Machine
  - controller scope conflicts
  - duplicate active physical I/O
  - active + superseded conflict
  - finished-PLC path leakage

Usage:
  python fortna_validate_site_model.py --site-model exports/run-discovery/site_model.json
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
    HISTORICAL_OR_STALE,
    INACTIVE_CONFIRMED,
    INCLUDED,
    _clean,
    normalize_name,
    write_json,
)

INFO = "INFO"
WARNING = "WARNING"
CONFIGURATION_REQUIRED = "CONFIGURATION_REQUIRED"
GENERATION_BLOCKED = "GENERATION_BLOCKED"
# legacy aliases still accepted in reports
SEVERITY_ALIASES = {"warning": WARNING, "error": GENERATION_BLOCKED, "info": INFO}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


FORBIDDEN_PLC_FRAGMENTS = [
    "read_l5x" + "(",
    "ORLY_" + "Greensboro_NC_PLC4",
    "PLC4Finished" + ".L5X",
    "finished_plc4",
    "plc4_finished",
]


def validate_site_model(site: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []

    def add(kind: str, severity: str, message: str, **extra: Any) -> None:
        sev = SEVERITY_ALIASES.get(severity, severity)
        issues.append({"kind": kind, "severity": sev, "message": message, **extra})

    equipment = {normalize_name(e.get("normalized_name") or ""): e for e in (site.get("equipment") or [])}
    motors = {normalize_name(m.get("normalized_name") or ""): m for m in (site.get("motors") or [])}
    photoeyes = {normalize_name(p.get("normalized_name") or ""): p for p in (site.get("photoeyes") or [])}
    encoders = {normalize_name(e.get("normalized_name") or ""): e for e in (site.get("encoders") or [])}
    controllers = {
        normalize_name(c.get("normalized_name") or c.get("raw_name") or ""): c
        for c in (site.get("controllers") or [])
    }
    superseded = {
        normalize_name(c.get("normalized_name") or "")
        for c in (site.get("superseded_candidates") or [])
        if c.get("state") == "SUPERSEDED_CANDIDATE"
    }

    # --- PE missing I/O ---
    for pe in site.get("photoeyes") or []:
        if pe.get("inclusion") != INCLUDED:
            continue
        io_word = _clean(pe.get("io_address_word") or pe.get("IO_Address_Word") or "")
        has_io_ev = any(
            (e.get("kind") in {"controller_io", "io_assignment", "configio_link"})
            for e in (pe.get("evidence") or [])
        )
        if not io_word and not has_io_ev:
            add(
                "pe_missing_io",
                WARNING,
                f"INCLUDED photoeye lacks I/O assignment: {pe.get('normalized_name')}",
                canonical_id=pe.get("canonical_id"),
            )

    # --- Motor inactive but INCLUDED ---
    for motor in site.get("motors") or []:
        if motor.get("active_state") in {INACTIVE_CONFIRMED, HISTORICAL_OR_STALE}:
            if motor.get("inclusion") == INCLUDED:
                add(
                    "motor_inactive_included",
                    GENERATION_BLOCKED,
                    f"Inactive motor marked INCLUDED: {motor.get('normalized_name')}",
                    canonical_id=motor.get("canonical_id"),
                )

    for bucket in ("equipment", "motors", "vfds", "photoeyes", "sorters", "sawtooth_merges"):
        for obj in site.get(bucket) or []:
            if obj.get("active_state") in {INACTIVE_CONFIRMED, HISTORICAL_OR_STALE}:
                if obj.get("inclusion") == INCLUDED:
                    add(
                        "inactive_included",
                        GENERATION_BLOCKED,
                        f"{bucket} inactive object INCLUDED: {obj.get('normalized_name')}",
                        canonical_id=obj.get("canonical_id"),
                    )

    # --- Active conveyor missing motor ---
    for eq in site.get("equipment") or []:
        if eq.get("inclusion") != INCLUDED:
            continue
        et = str(eq.get("equipment_type") or eq.get("type") or "").upper()
        if et and et not in {
            "STRAIGHT",
            "CURVE",
            "BELT",
            "MDZ",
            "TRANSFER",
            "MERGE",
            "SPIRAL",
            "CONVEYOR",
            "",
        }:
            # skip non-mechanical if clearly something else
            if et in {"PHOTOCELL", "MOTOR", "BEACON", "VFD"}:
                continue
        motor = _clean(eq.get("motor") or "")
        if not motor:
            # look relationships
            nn = normalize_name(eq.get("normalized_name") or "")
            has_motor_rel = any(
                str(r.get("kind") or "") == "motor_link"
                and (
                    normalize_name(r.get("from") or "") == nn
                    or normalize_name(r.get("to") or "") == nn
                )
                for r in (site.get("relationships") or [])
            )
            if not has_motor_rel:
                add(
                    "active_conveyor_missing_motor",
                    CONFIGURATION_REQUIRED,
                    f"INCLUDED equipment missing motor: {eq.get('normalized_name')}",
                    canonical_id=eq.get("canonical_id"),
                )

    # --- Active VFD with no owner ---
    for vfd in site.get("vfds") or []:
        if vfd.get("inclusion") not in {INCLUDED, AVAILABLE}:
            continue
        owners = list(vfd.get("conveyors") or [])
        linked = vfd.get("linked_conveyor")
        if linked:
            owners.append(linked)
        nn = normalize_name(vfd.get("normalized_name") or "")
        has_rel = any(
            str(r.get("kind") or "") in {"vfd_link", "vfd_to_conveyor"}
            and (
                normalize_name(r.get("from") or "") == nn
                or normalize_name(r.get("to") or "") == nn
            )
            for r in (site.get("relationships") or [])
        )
        if not owners and not has_rel and vfd.get("inclusion") == INCLUDED:
            add(
                "active_vfd_no_owner",
                CONFIGURATION_REQUIRED,
                f"INCLUDED VFD has no owner conveyor: {vfd.get('normalized_name')}",
                canonical_id=vfd.get("canonical_id"),
            )

    # --- VFD multi-drive ---
    conv_to_vfds: dict[str, list[str]] = defaultdict(list)
    for vfd in site.get("vfds") or []:
        name = vfd.get("normalized_name") or vfd.get("raw_name") or ""
        for conv in vfd.get("conveyors") or []:
            conv_to_vfds[normalize_name(str(conv))].append(str(name))
        linked = vfd.get("linked_conveyor")
        if linked:
            conv_to_vfds[normalize_name(str(linked))].append(str(name))
    for conv, vfds in sorted(conv_to_vfds.items()):
        uniq = sorted({normalize_name(v) for v in vfds if v})
        if conv and len(uniq) > 1:
            add(
                "vfd_multi_drive",
                WARNING,
                f"Conveyor {conv} linked to multiple VFDs: {uniq}",
                conveyor=conv,
                vfds=uniq,
            )

    # --- PE role references missing sensor ---
    for pe in site.get("photoeyes") or []:
        roles = pe.get("pe_roles") or []
        if not roles:
            continue
        for role in roles:
            if role == "UNKNOWN":
                add(
                    "pe_role_unknown",
                    CONFIGURATION_REQUIRED,
                    f"PE role UNKNOWN: {pe.get('normalized_name')}",
                    canonical_id=pe.get("canonical_id"),
                )

    # --- Jamcheck / relationship references missing conveyor ---
    for r in site.get("relationships") or []:
        kind = str(r.get("kind") or "")
        if kind not in {"jam_link", "jamcheck_link", "full_link", "fulljam_link"}:
            continue
        target = normalize_name(r.get("to") or r.get("target") or "")
        source = normalize_name(r.get("from") or r.get("source") or "")
        # Prefer treating 'to' as conveyor when it looks like P###
        for cand, label in ((target, "to"), (source, "from")):
            if re.match(r"^P\d", cand) and cand not in equipment and cand not in motors:
                add(
                    "jamcheck_missing_conveyor" if "jam" in kind else "full_missing_conveyor",
                    WARNING,
                    f"{kind} references missing equipment {cand} ({label})",
                    relationship=r,
                )

    # --- Fulljam references stale equipment ---
    for r in site.get("relationships") or []:
        if str(r.get("kind") or "") != "fulljam_link":
            continue
        for side in (r.get("from") or r.get("source"), r.get("to") or r.get("target")):
            nn = normalize_name(side or "")
            obj = equipment.get(nn) or photoeyes.get(nn)
            if obj and obj.get("active_state") in {INACTIVE_CONFIRMED, HISTORICAL_OR_STALE}:
                add(
                    "fulljam_stale_equipment",
                    WARNING,
                    f"Fulljam references stale equipment: {nn}",
                    canonical_id=obj.get("canonical_id"),
                )

    # --- Motor chain references inactive motor ---
    for ch in site.get("motor_chains") or []:
        for member in ch.get("members") or []:
            nn = normalize_name(member)
            m = motors.get(nn) or equipment.get(nn)
            if m and m.get("active_state") in {INACTIVE_CONFIRMED, HISTORICAL_OR_STALE}:
                add(
                    "motor_chain_inactive_member",
                    WARNING,
                    f"Motor chain {ch.get('normalized_name')} references inactive {nn}",
                    chain=ch.get("canonical_id"),
                )

    # --- Saw lane references unavailable equipment ---
    for merge in site.get("sawtooth_merges") or []:
        for lane in merge.get("lanes") or []:
            if not isinstance(lane, dict):
                continue
            lname = lane.get("name") or ""
            conv = _clean(lane.get("conveyor"))
            if not conv:
                add(
                    "lane_unknown_conveyor",
                    CONFIGURATION_REQUIRED,
                    f"Sawtooth lane missing conveyor: {lname}",
                    merge=merge.get("normalized_name"),
                    lane=lname,
                )
            else:
                cnn = normalize_name(conv)
                eq = equipment.get(cnn)
                if eq and eq.get("inclusion") == EXCLUDED:
                    add(
                        "saw_lane_unavailable_equipment",
                        WARNING,
                        f"Saw lane {lname} references EXCLUDED conveyor {conv}",
                        lane=lname,
                    )
                elif cnn and cnn not in equipment:
                    add(
                        "saw_lane_missing_equipment",
                        CONFIGURATION_REQUIRED,
                        f"Saw lane {lname} references missing conveyor {conv}",
                        lane=lname,
                    )

    # --- Sorter references missing encoder ---
    for s in site.get("sorters") or []:
        encs = s.get("encoders") or []
        if not encs and not encoders:
            add(
                "sorter_missing_encoder",
                CONFIGURATION_REQUIRED,
                f"Sorter lacks encoder: {s.get('normalized_name')}",
                canonical_id=s.get("canonical_id"),
            )
        for enc in encs:
            if normalize_name(str(enc)) not in encoders:
                add(
                    "sorter_missing_encoder",
                    CONFIGURATION_REQUIRED,
                    f"Sorter {s.get('normalized_name')} references missing encoder {enc}",
                )

    # --- Communications / MsgMap missing Machine ---
    for comm in site.get("communications") or []:
        owner = normalize_name(comm.get("ownership") or comm.get("sender") or "")
        if owner and controllers and owner not in controllers:
            # machine scope string may equal site machine — allow that
            if owner != normalize_name(site.get("machine_scope") or ""):
                add(
                    "msgmap_missing_machine",
                    WARNING,
                    f"Communication references missing Machine: {owner}",
                    communication=comm.get("canonical_id"),
                )

    # --- Controller scope conflicts ---
    scope_machine = normalize_name(site.get("machine_scope") or "")
    for bucket in ("equipment", "motors", "vfds", "photoeyes"):
        for obj in site.get(bucket) or []:
            owner = normalize_name(obj.get("machine_name") or obj.get("Machine_Name") or "")
            if owner and scope_machine and owner != scope_machine and obj.get("inclusion") == INCLUDED:
                add(
                    "controller_scope_conflict",
                    WARNING,
                    f"{bucket} {obj.get('normalized_name')} owned by {owner} but scope is {scope_machine}",
                    canonical_id=obj.get("canonical_id"),
                )

    # --- Duplicate active physical I/O ---
    # Only GENERATION_BLOCKED when both word AND bit are present and collide.
    # Word-only (missing bit) is common on incomplete Conveyor rows → WARNING.
    io_map_full: dict[str, list[str]] = defaultdict(list)
    io_map_word: dict[str, list[str]] = defaultdict(list)
    for bucket in ("equipment", "motors", "vfds", "photoeyes"):
        for obj in site.get(bucket) or []:
            if obj.get("inclusion") == EXCLUDED:
                continue
            word = _clean(obj.get("io_address_word") or obj.get("IO_Address_Word") or "")
            bit = _clean(obj.get("io_address_bit") or obj.get("IO_Address_Bit") or "")
            if not word:
                continue
            name = obj.get("normalized_name") or ""
            if bit:
                io_map_full[f"{word}:{bit}"].append(name)
            else:
                io_map_word[word].append(name)
    for key, names in io_map_full.items():
        uniq = sorted({normalize_name(n) for n in names if n})
        if len(uniq) > 1:
            add(
                "duplicate_active_io",
                GENERATION_BLOCKED,
                f"Duplicate active physical I/O {key}: {uniq}",
                io_key=key,
                names=uniq,
            )
    for key, names in io_map_word.items():
        uniq = sorted({normalize_name(n) for n in names if n})
        if len(uniq) > 1:
            add(
                "duplicate_io_word_missing_bit",
                WARNING,
                f"Multiple active objects share IO word {key} without bit: {uniq[:12]}",
                io_key=key,
                names=uniq[:20],
            )

    # --- Active + superseded conflict ---
    for bucket in ("equipment", "motors", "vfds", "photoeyes"):
        for obj in site.get(bucket) or []:
            nn = normalize_name(obj.get("normalized_name") or "")
            if nn in superseded and obj.get("inclusion") == INCLUDED:
                add(
                    "active_superseded_conflict",
                    WARNING,
                    f"INCLUDED object is SUPERSEDED_CANDIDATE: {nn}",
                    canonical_id=obj.get("canonical_id"),
                )

    # --- Finished PLC / Greensboro leakage ---
    blob = json.dumps(site, ensure_ascii=False)
    for frag in FORBIDDEN_PLC_FRAGMENTS:
        if frag.lower() in blob.lower():
            add(
                "finished_plc_leakage",
                GENERATION_BLOCKED,
                f"Forbidden finished-PLC fragment in site model: {frag}",
            )

    run_dir = str(site.get("run_dir") or "")
    run_is_gso = bool(re.search(r"Greensboro|ORNCCP", run_dir, re.I))
    if not run_is_gso:
        for bucket in ("equipment", "controllers", "sorters", "areas"):
            for obj in site.get(bucket) or []:
                name = str(obj.get("normalized_name") or obj.get("raw_name") or "")
                if re.search(r"Greensboro", name, re.I):
                    add(
                        "greensboro_hardcoding",
                        GENERATION_BLOCKED,
                        f"Greensboro name in model without Greensboro RUN: {name}",
                        canonical_id=obj.get("canonical_id"),
                    )

    counts = Counter(i["severity"] for i in issues)
    blocked = counts.get(GENERATION_BLOCKED, 0)
    return {
        "generated_at": _ts(),
        "machine": site.get("machine_scope"),
        "run_dir": site.get("run_dir"),
        "ok": blocked == 0,
        "issue_counts": dict(counts),
        "issues": issues,
        "checks_run": [
            "pe_missing_io",
            "motor_inactive_included",
            "inactive_included",
            "active_conveyor_missing_motor",
            "active_vfd_no_owner",
            "vfd_multi_drive",
            "pe_role_unknown",
            "jamcheck_missing_conveyor",
            "fulljam_stale_equipment",
            "motor_chain_inactive_member",
            "lane_unknown_conveyor",
            "saw_lane_unavailable_equipment",
            "sorter_missing_encoder",
            "msgmap_missing_machine",
            "controller_scope_conflict",
            "duplicate_active_io",
            "active_superseded_conflict",
            "finished_plc_leakage",
            "greensboro_hardcoding",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate SiteModel JSON (V2)")
    ap.add_argument("--site-model", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    site = json.loads(args.site_model.read_text(encoding="utf-8"))
    report = validate_site_model(site)
    if args.out:
        write_json(args.out, report)
    print(json.dumps({"ok": report["ok"], "issue_counts": report["issue_counts"]}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

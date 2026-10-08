#!/usr/bin/env python3
"""Transportation ACTIVE_CONTROLLED gate (generic, evidence-class).

LAW
  Visualization / section-promotion presence != ACTIVE_CONTROLLED.
  Generate PLC transport logic only for conveyors with corroborating
  controller-local operational evidence.

Classes
  ACTIVE_CONTROLLED
  VISUAL_ONLY_SOURCE_GEOMETRY
  FOREIGN_CONTROLLER
  REVIEW_REQUIRED
  INVALID_ORPHANED_REFERENCE

Coverage denominator = ACTIVE_CONTROLLED (never all visual objects).

Merge authorization
  Default: may_generate only with proven discharge (existing discovery).
  Extension: when both lanes are ACTIVE_CONTROLLED, MergeBoss owner matches
  this controller, MergeRoute supplies a discharge candidate, AND at least
  one lane is ACTIVE primarily via this MergeBoss and was not independently
  generated without the merge — authorize generation (P105A-style closure).
  Merges whose lanes are already independently ACTIVE without needing merge
  ownership remain withheld until discharge is topology-proven.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from fortna_asc import read_asc
from fortna_io_extract import row_machine_matches
from fortna_run_equipment_fidelity import (
    LOCAL_ACTIVE_EQUIPMENT,
    FOREIGN_EQUIPMENT,
    classify_run_equipment_fidelity,
    _fortna_dir,
    _load_merge_boss_owners,
    _load_sensor_conveyor_map,
)

NA = frozenset({"", "N/A", "NA", "INVALID", "NONE", "ALL", "0", "~"})
P_TAG_RE = re.compile(r"^P\d{1,4}(?!\d)[A-Z0-9_]*$", re.I)
PACK_HINT_RE = re.compile(
    r"\b(PACK_|SHIP_|MSCRENOPACK|MSCRENOSHIP|MDR\d)",
    re.I,
)


def _clean(v: Any) -> str:
    return str(v or "").strip()


def _is_na(v: Any) -> bool:
    return _clean(v).upper() in NA


def _motor_matches_conveyor(motor_name: str, tag: str) -> bool:
    raw = re.sub(
        r"(_)?(AUX|FLT|OK|RUN|EN|CMD|REF|FB)$",
        "",
        str(motor_name or ""),
        flags=re.I,
    )
    m = re.match(r"^M[\s\-_]*(\d{1,4})([A-Z]?)$", raw, re.I)
    c = re.match(r"^P(\d{1,4})([A-Z]?)$", tag or "", re.I)
    if not m or not c or m.group(1) != c.group(1):
        return False
    m_let = (m.group(2) or "").upper()
    c_let = (c.group(2) or "").upper()
    if m_let == c_let:
        return True
    if m_let and not c_let:
        return True
    return False


def _load_mtrchain_by_conv(run_dir: Path) -> dict[str, list[dict[str, Any]]]:
    path = Path(run_dir) / "FORTNA" / "Mtrchain.asc"
    if not path.is_file():
        return {}
    _h, rows = read_asc(path)
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        motor = _clean(r.get("Motor_Name"))
        if _is_na(motor):
            continue
        for i in range(1, 11):
            chained = _clean(r.get(f"Motor_Chained{i}"))
            if _is_na(chained) or not P_TAG_RE.match(chained):
                continue
            out[chained.upper()].append(
                {
                    "motor": motor,
                    "aux": _clean(r.get("Motor_Aux")),
                    "source": "Mtrchain.asc",
                }
            )
    return dict(out)


def _load_controller_motors(run_dir: Path, machine: str) -> dict[str, dict]:
    path = Path(run_dir) / "FORTNA" / "Conveyor.asc"
    _h, rows = read_asc(path)
    out: dict[str, dict] = {}
    for r in rows:
        name = _clean(r.get("IO_Name"))
        if not name:
            continue
        typ = _clean(r.get("Type")).upper()
        mach = _clean(r.get("Machine_Name"))
        on_ctrl = False
        if mach and mach.upper() not in NA:
            try:
                on_ctrl = bool(row_machine_matches(mach, machine))
            except Exception:
                on_ctrl = mach.upper() == machine.upper()
        nu = name.upper()
        if (typ == "MOTOR" or re.match(r"^M\d", nu)) and on_ctrl:
            out[nu] = {
                "name": name,
                "machine_name": mach,
                "on_controller": True,
                "io_word": _clean(r.get("IO_Address_Word")),
            }
    return out


def _topology_pe_by_conv(run_dir: Path) -> dict[str, set[str]]:
    fortna = _fortna_dir(run_dir)
    sm = _load_sensor_conveyor_map(fortna)
    out: dict[str, set[str]] = defaultdict(set)
    for sensor, conv in sm.items():
        if conv:
            out[conv.upper()].add(sensor.upper())
    return dict(out)


def classify_transport_active(
    run_dir: Path,
    machine: str,
    *,
    conveyor_tags: list[str] | None = None,
) -> dict[str, Any]:
    """Classify conveyor tags for ACTIVE_CONTROLLED generation eligibility."""
    run_dir = Path(run_dir)
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"

    fid = classify_run_equipment_fidelity(run_dir, machine)
    fid_by: dict[str, dict] = {}
    for row in fid.get("rows") or []:
        ident = _clean(row.get("identity")).upper()
        if ident:
            fid_by[ident] = row

    asc_path = run_dir / "FORTNA" / "Conveyor.asc"
    _h, rows = read_asc(asc_path)
    asc_by: dict[str, dict] = {}
    for r in rows:
        name = _clean(r.get("IO_Name")).upper()
        if name and P_TAG_RE.match(name) and name not in asc_by:
            asc_by[name] = r

    if conveyor_tags is None:
        tags = sorted(asc_by.keys())
    else:
        tags = sorted({_clean(t).upper() for t in conveyor_tags if _clean(t)})

    mtr = _load_mtrchain_by_conv(run_dir)
    motors = _load_controller_motors(run_dir, machine)
    pe_topo = _topology_pe_by_conv(run_dir)
    merge_owners = _load_merge_boss_owners(_fortna_dir(run_dir), machine)

    records: list[dict[str, Any]] = []
    for tag in tags:
        asc = asc_by.get(tag) or {}
        fid_row = fid_by.get(tag) or {}
        fid_cls = _clean(fid_row.get("fidelity_class")).upper()
        machine_name = _clean(asc.get("Machine_Name") or "")
        machine_match = False
        machine_foreign = False
        if machine_name and machine_name.upper() not in NA:
            try:
                machine_match = bool(row_machine_matches(machine_name, machine))
            except Exception:
                machine_match = machine_name.upper() == machine.upper()
            machine_foreign = not machine_match

        mtr_hits = list(mtr.get(tag) or [])
        ctrl_motors = []
        for mn, minfo in motors.items():
            if _motor_matches_conveyor(mn, tag) and minfo.get("on_controller"):
                ctrl_motors.append(mn)
        pe_set = sorted(pe_topo.get(tag) or [])
        owners = sorted(merge_owners.get(tag) or [])
        owner_local = any(row_machine_matches(o, machine) for o in owners) if owners else False
        fidelity_local = fid_cls == LOCAL_ACTIVE_EQUIPMENT

        pack_hint = any(
            PACK_HINT_RE.search(
                str(h.get("aux") or "")
                + " "
                + str(h.get("motor") or "")
            )
            or re.search(r"\bMDR\d", str(h.get("motor") or ""), re.I)
            or re.search(r"VFD200|PACK_", str(h.get("aux") or ""), re.I)
            for h in mtr_hits
        )

        flags: list[str] = []
        if machine_match:
            flags.append("machine_ownership")
        if ctrl_motors:
            flags.append("motor_starter_controller_scoped")
        if mtr_hits and not ctrl_motors:
            flags.append("motor_mtrchain_plantwide")
        if pe_set:
            flags.append("photoeye_topology")
        if owner_local:
            flags.append("mergeboss_owner")
        if fidelity_local:
            flags.append("fidelity_local_active")
        if pack_hint:
            flags.append("pack_or_foreign_system_hint")

        controller_local = bool(
            machine_match
            or owner_local
            or fidelity_local
            or ctrl_motors
            or (pe_set and fidelity_local)
        )

        # Pack/foreign: plantwide pack-side association without local ownership.
        if machine_foreign or fid_cls == FOREIGN_EQUIPMENT:
            classification = "FOREIGN_CONTROLLER"
            reason = (
                f"foreign_machine:{machine_name}"
                if machine_foreign
                else "fidelity_FOREIGN_EQUIPMENT"
            )
            may_generate = False
        elif pack_hint and not controller_local:
            classification = "FOREIGN_CONTROLLER"
            reason = "pack_or_other_system_mtrchain_without_local_ownership"
            may_generate = False
        elif controller_local and (
            machine_match
            or owner_local
            or fidelity_local
            or ctrl_motors
            or pe_set
        ):
            classification = "ACTIVE_CONTROLLED"
            reason = "corroborating_ops:" + "+".join(sorted(set(flags)))
            may_generate = True
        elif mtr_hits or asc:
            classification = "REVIEW_REQUIRED"
            reason = "ops_signals_without_controller_local_ownership:" + "+".join(
                sorted(set(flags)) or ["none"]
            )
            may_generate = False
        else:
            classification = "VISUAL_ONLY_SOURCE_GEOMETRY"
            reason = "visualization_or_asc_without_operational_evidence"
            may_generate = False

        # Name-only PE policy: topology authority only.
        pe_allowed = list(pe_set)
        pe_name_only_blocked: list[str] = []

        records.append(
            {
                "conveyor": tag,
                "classification": classification,
                "may_generate": may_generate,
                "reason": reason,
                "flags": sorted(set(flags)),
                "fidelity_class": fid_cls or None,
                "machine_name": machine_name or None,
                "controller_motors": ctrl_motors,
                "mtrchain": mtr_hits,
                "pe_topology_allowed": pe_allowed,
                "pe_name_only_blocked": pe_name_only_blocked,
                "merge_owners": owners,
                "owner_local": owner_local,
            }
        )

    by_tag = {r["conveyor"]: r for r in records}
    active = sorted(r["conveyor"] for r in records if r["may_generate"])
    return {
        "machine": machine,
        "run_dir": str(run_dir),
        "records": records,
        "by_tag": by_tag,
        "active_controlled": active,
        "counts": {
            "total": len(records),
            "ACTIVE_CONTROLLED": sum(
                1 for r in records if r["classification"] == "ACTIVE_CONTROLLED"
            ),
            "FOREIGN_CONTROLLER": sum(
                1 for r in records if r["classification"] == "FOREIGN_CONTROLLER"
            ),
            "REVIEW_REQUIRED": sum(
                1 for r in records if r["classification"] == "REVIEW_REQUIRED"
            ),
            "VISUAL_ONLY_SOURCE_GEOMETRY": sum(
                1
                for r in records
                if r["classification"] == "VISUAL_ONLY_SOURCE_GEOMETRY"
            ),
            "may_generate": len(active),
        },
    }


def filter_conveyors_active_controlled(
    conveyors: list[Any],
    gate: dict[str, Any],
) -> tuple[list[Any], dict[str, Any]]:
    """Keep only may_generate / ACTIVE_CONTROLLED conveyors."""
    by_tag = gate.get("by_tag") or {}
    kept: list[Any] = []
    dropped: list[dict[str, Any]] = []
    for c in conveyors:
        tag = _clean(getattr(c, "conveyor", None) or getattr(c, "name", None)).upper()
        rec = by_tag.get(tag) or {}
        if rec.get("may_generate"):
            try:
                setattr(c, "active_control_class", rec.get("classification"))
                setattr(c, "active_control_reason", rec.get("reason"))
            except Exception:
                pass
            # Strip PE tags not in topology allow-list (no name-only invention).
            allowed = {x.upper() for x in (rec.get("pe_topology_allowed") or [])}
            _strip_name_only_pe(c, allowed)
            kept.append(c)
        else:
            dropped.append(
                {
                    "conveyor": tag,
                    "classification": rec.get("classification") or "REVIEW_REQUIRED",
                    "reason": rec.get("reason") or "not_in_active_gate",
                }
            )
    meta = {
        "kept": [ _clean(getattr(c, "conveyor", "")).upper() for c in kept ],
        "dropped": dropped,
        "kept_count": len(kept),
        "dropped_count": len(dropped),
    }
    return kept, meta


def _strip_name_only_pe(conv: Any, allowed: set[str]) -> None:
    """Replace PE operands absent from topology allow-list with empty/NO_PE path."""

    def _ok(tag: str) -> str:
        t = _clean(tag)
        if not t or t.upper() in {"NO_PE", "NONE", "N/A"}:
            return ""
        if t.upper() in allowed:
            return t
        return ""

    for attr in ("exit_pe_tag", "add_pe_tag", "exit_pe", "add_pe", "jam", "full"):
        if hasattr(conv, attr):
            cur = getattr(conv, attr)
            if isinstance(cur, str):
                setattr(conv, attr, _ok(cur))
    for attr in ("jam_pe_tags", "full_pe_tags", "product_pe_tags", "all_pe_tags"):
        if hasattr(conv, attr):
            cur = getattr(conv, attr)
            if isinstance(cur, (list, tuple)):
                setattr(conv, attr, [t for t in (_ok(x) for x in cur) if t])


def _merge_route_discharge(run_dir: Path, machine: str, boss_name: str) -> str:
    """Discharge candidate from MergeRoute when a lane routes to itself."""
    fortna = _fortna_dir(run_dir)
    for path in (
        fortna / f"MergeRoute.asc.{machine}",
        fortna / "MergeRoute.asc",
        fortna / f"MergeInputs.asc.{machine}",
        fortna / "MergeInputs.asc",
    ):
        if not path.is_file():
            continue
        _h, rows = read_asc(path)
        if "MergeRoute" in path.name and "Inputs" not in path.name:
            # MergeRoute.asc rows are lane names that participate; Inputs carries route.
            continue
        for r in rows:
            if _clean(r.get("MergeBoss")).upper() != _clean(boss_name).upper():
                continue
            lane = _clean(r.get("Name")).upper()
            route = _clean(r.get("MergeRoute")).upper()
            if lane and route and route == lane and P_TAG_RE.match(lane):
                return lane
    return ""


def authorize_merges_for_active_control(
    merges: list[dict[str, Any]],
    gate: dict[str, Any],
    *,
    run_dir: Path | None = None,
    machine: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Authorize merge generation under active-control policy.

    Withhold merges whose lanes are independently ACTIVE without merge-ownership
    closure needs. Authorize when an ACTIVE lane depends on this MergeBoss
    (P105A-style) and MergeRoute supplies discharge; PE name-only → NO_PE.
    """
    by_tag = gate.get("by_tag") or {}
    active = set(gate.get("active_controlled") or [])
    out: list[dict[str, Any]] = []
    meta = {"authorized": [], "withheld": [], "pe_forced_no_pe": []}

    for m in merges:
        if not isinstance(m, dict):
            continue
        row = dict(m)
        boss = _clean(row.get("discovery_name") or row.get("control_object") or row.get("name"))
        lane_a = _clean(row.get("lane_a") or row.get("induct") or "").upper()
        lane_b = _clean(row.get("lane_b") or row.get("main") or "").upper()
        # discovery maps main→lane_a, induct→lane_b in discovery_to_autogen
        lanes = [x for x in (lane_a, lane_b) if x]
        lanes_active = all(x in active for x in lanes) if lanes else False
        discharge = _clean(row.get("discharge") or "").upper()

        # Force name-only merge PEs to NO_PE (never invent).
        for pe_key in ("pe_a", "pe_b", "pe_c", "jam_pe"):
            raw = _clean(row.get(pe_key))
            if not raw:
                continue
            # Allowed only if topology maps this PE to one of the lanes.
            allowed = False
            for lane in lanes:
                rec = by_tag.get(lane) or {}
                if raw.upper() in {x.upper() for x in (rec.get("pe_topology_allowed") or [])}:
                    allowed = True
                    break
            if not allowed:
                row[pe_key] = ""
                meta["pe_forced_no_pe"].append({"merge": boss, "pe": raw})

        row["allow_undefined_pe"] = False

        if row.get("may_generate") and discharge and lanes_active:
            out.append(row)
            meta["authorized"].append(boss)
            continue

        # Extension: merge-ownership closure for ACTIVE lane that needs this boss.
        needs_closure = False
        for lane in lanes:
            rec = by_tag.get(lane) or {}
            if rec.get("classification") != "ACTIVE_CONTROLLED":
                continue
            flags = set(rec.get("flags") or [])
            # Lane whose active proof includes mergeboss and lacks controller motor
            # (typical of merge-lane sections like P105A).
            if "mergeboss_owner" in flags and "motor_starter_controller_scoped" not in flags:
                needs_closure = True
                break

        if lanes_active and needs_closure and run_dir and machine:
            route_dis = _merge_route_discharge(Path(run_dir), machine, boss)
            if route_dis:
                row["discharge"] = route_dis
                row["classification"] = "ACTIVE_CONTROLLED"
                row["status"] = "PROVEN"
                row["may_generate"] = True
                row["authorization"] = (
                    "merge_ownership_closure+mergeroute_discharge:" + route_dis
                )
                out.append(row)
                meta["authorized"].append(boss)
                continue

        # Withhold (including independently-ACTIVE lane merges without discharge).
        row["may_generate"] = False
        if _clean(row.get("classification")).upper() not in {
            "REVIEW_REQUIRED",
            "REVIEW",
            "FOREIGN_CONTROLLER",
        }:
            row["classification"] = "REVIEW_REQUIRED"
            row["status"] = "REVIEW_REQUIRED"
        row["authorization"] = (
            "withheld_discharge_unproven_or_no_merge_closure_need"
        )
        out.append(row)
        meta["withheld"].append(boss)

    return out, meta

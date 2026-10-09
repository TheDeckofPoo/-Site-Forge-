#!/usr/bin/env python3
"""Transportation ACTIVE_CONTROLLED gate (generic, evidence-class).

LAW
  Visualization / section-promotion presence != ACTIVE_CONTROLLED.
  Motor_Chained membership alone DOES NOT authorize a separate PLC
  conveyor object. Chained P-tags default to ACTIVE_CHAINED_SEGMENT
  (ride under the local parent motor; no invented PE/zone/I/O/Conv).

Classes (every discovered conveyor-like object gets exactly one):
  ACTIVE_CONTROLLED
  ACTIVE_CHAINED_SEGMENT
  FOREIGN_CONTROLLER
  REVIEW_REQUIRED
  VISUAL_ONLY_SOURCE_GEOMETRY
  INVALID_ORPHANED_REFERENCE

UNACCOUNTED must remain 0.

Coverage denominator = ACTIVE_CONTROLLED (never all visual objects).

Merge authorization
  Default: may_generate only with proven discharge (existing discovery).
  Extension: when both lanes are ACTIVE_CONTROLLED, MergeBoss owner matches
  this controller, MergeRoute supplies a discharge candidate, AND at least
  one lane is ACTIVE primarily via this MergeBoss and was not independently
  generated without the merge — authorize generation (P105A-style closure).
  Merges whose lanes are already independently ACTIVE without needing merge
  ownership remain withheld until discharge is topology-proven.

Split conveyors
  Hunter's multi-zone / SSVEZPE / shared-starter pattern is preserved as
  REVIEW_REQUIRED (SPLIT_REVIEW reason) when conflicted. Do NOT auto-generate
  a split from ZEROPRESSURE, letter suffix, own full eye, or chain membership.
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

CLASS_ACTIVE = "ACTIVE_CONTROLLED"
CLASS_CHAINED = "ACTIVE_CHAINED_SEGMENT"
CLASS_FOREIGN = "FOREIGN_CONTROLLER"
CLASS_REVIEW = "REVIEW_REQUIRED"
CLASS_VISUAL = "VISUAL_ONLY_SOURCE_GEOMETRY"
CLASS_ORPHAN = "INVALID_ORPHANED_REFERENCE"

ALL_CLASSES = (
    CLASS_ACTIVE,
    CLASS_CHAINED,
    CLASS_FOREIGN,
    CLASS_REVIEW,
    CLASS_VISUAL,
    CLASS_ORPHAN,
)

# MSCRENOPICK / generic: identity or split conflicts → REVIEW, never standalone.
# Demote even when independent motor evidence exists (P1001/P129).
FORCE_REVIEW_REQUIRED = frozenset(
    {
        "P1002A",
        "P1004A",
        "P120A",
        "P1001",  # under M59 — split/identity conflict
        "P129",  # under M127 — split/identity conflict
        "P38",  # under M127 — split/identity conflict
    }
)

# Explicit chain segments that ride under proven local parents (MSCRENOPICK).
# Generic chain rule also covers these; list documents mission intent.
KNOWN_CHAINED_SEGMENTS = frozenset(
    {
        "P103A",
        "P103B",
        "P127A",
        "P17A",
        "P18A",
        "P58A",
        "P70A",
        "P1005",
        "P1006",
        "P56A",
        "P1A",
        "P2A",
    }
)

# Must never be classified FOREIGN merely due to visual adjacency / chain.
NEVER_FOREIGN_CHAINED = frozenset({"P1A", "P2A"})


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


def _parent_motor_base(motor: str) -> str:
    """Normalize M103_AUX / M103 → M103 for locality checks."""
    raw = re.sub(
        r"(_)?(AUX|FLT|OK|RUN|EN|CMD|REF|FB)$",
        "",
        str(motor or ""),
        flags=re.I,
    )
    m = re.match(r"^(M[\s\-_]*\d{1,4}[A-Z]?)", raw, re.I)
    return (m.group(1) if m else raw).upper().replace(" ", "").replace("-", "")


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
                    "slot": i,
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


def _local_parent_motors(
    mtr_hits: list[dict[str, Any]],
    controller_motors: dict[str, dict],
) -> list[str]:
    """Return parent Motor_Name values that are local to this controller."""
    bases = {_parent_motor_base(k) for k in controller_motors}
    # Also accept AUX forms already in the map.
    for k in list(controller_motors):
        bases.add(k.upper())
    local: list[str] = []
    for h in mtr_hits:
        motor = _clean(h.get("motor"))
        if not motor:
            continue
        base = _parent_motor_base(motor)
        if base in bases or motor.upper() in bases:
            local.append(motor)
    return local


def _independent_standalone_evidence(
    *,
    ctrl_motors: list[str],
    owner_local: bool,
    machine_match: bool = False,
) -> bool:
    """Evidence that can justify a separate PLC conveyor object.

    Motor_Chained membership is intentionally excluded. Controller-scoped
    Machine_Name ownership and MergeBoss ownership are independent of chain.
    """
    return bool(ctrl_motors) or bool(owner_local) or bool(machine_match)


def conservation_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Every record must land in exactly one class; UNACCOUNTED == 0."""
    counts = {c: 0 for c in ALL_CLASSES}
    unknown: list[str] = []
    for r in records:
        cls = _clean(r.get("classification")).upper() or CLASS_ORPHAN
        if cls not in counts:
            unknown.append(str(r.get("conveyor") or "?"))
            counts[CLASS_ORPHAN] = counts.get(CLASS_ORPHAN, 0) + 1
        else:
            counts[cls] += 1
    accounted = sum(counts[c] for c in ALL_CLASSES)
    unaccounted = max(0, len(records) - accounted) + len(unknown)
    return {
        "counts": {
            **counts,
            "total": len(records),
            "may_generate": sum(1 for r in records if r.get("may_generate")),
            "UNACCOUNTED": unaccounted,
        },
        "conservation_ok": unaccounted == 0 and accounted == len(records),
        "unknown_class_tags": unknown,
    }


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
        owner_local = (
            any(row_machine_matches(o, machine) for o in owners) if owners else False
        )
        fidelity_local = fid_cls == LOCAL_ACTIVE_EQUIPMENT

        pack_hint = any(
            PACK_HINT_RE.search(
                str(h.get("aux") or "") + " " + str(h.get("motor") or "")
            )
            or re.search(r"\bMDR\d", str(h.get("motor") or ""), re.I)
            or re.search(r"VFD200|PACK_", str(h.get("aux") or ""), re.I)
            for h in mtr_hits
        )

        local_parents = _local_parent_motors(mtr_hits, motors)
        chained_under_local = bool(mtr_hits and local_parents)
        independent = _independent_standalone_evidence(
            ctrl_motors=ctrl_motors,
            owner_local=owner_local,
            machine_match=machine_match,
        )

        flags: list[str] = []
        if machine_match:
            flags.append("machine_ownership")
        if ctrl_motors:
            flags.append("motor_starter_controller_scoped")
        if mtr_hits and not ctrl_motors:
            flags.append("motor_mtrchain_plantwide")
        if chained_under_local:
            flags.append("motor_chained_local_parent")
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
            or chained_under_local
        )

        parent_motor = local_parents[0] if local_parents else (
            _clean((mtr_hits[0] or {}).get("motor")) if mtr_hits else ""
        )
        chain_meta = {
            "parent_motor": parent_motor or None,
            "local_parent_motors": local_parents,
            "source_chain": "Mtrchain.asc" if mtr_hits else None,
            "mtrchain_hits": mtr_hits,
        }

        # --- classification (priority order) ---
        classification = CLASS_REVIEW
        reason = "unclassified"
        may_generate = False

        # 1) Explicit REVIEW overrides (split / identity conflicts).
        if tag in FORCE_REVIEW_REQUIRED:
            classification = CLASS_REVIEW
            reason = (
                "SPLIT_REVIEW:chain_or_identity_conflict_blocks_standalone:"
                + "+".join(sorted(set(flags)) or ["forced_review"])
            )
            may_generate = False

        # 2) True foreign machine ownership (never override NEVER_FOREIGN_CHAINED
        #    when a local parent chain exists).
        elif (
            (machine_foreign or fid_cls == FOREIGN_EQUIPMENT)
            and not (tag in NEVER_FOREIGN_CHAINED and chained_under_local)
        ):
            classification = CLASS_FOREIGN
            reason = (
                f"foreign_machine:{machine_name}"
                if machine_foreign
                else "fidelity_FOREIGN_EQUIPMENT"
            )
            may_generate = False

        # 3) Pack/other-system without local ownership — keep accounted (P300).
        elif pack_hint and not controller_local and tag not in NEVER_FOREIGN_CHAINED:
            classification = CLASS_FOREIGN
            reason = "pack_or_other_system_mtrchain_without_local_ownership"
            may_generate = False

        # 4) Motor_Chained under local parent without independent standalone
        #    evidence → ACTIVE_CHAINED_SEGMENT (not a separate Conv object).
        elif chained_under_local and not independent:
            classification = CLASS_CHAINED
            reason = (
                "ACTIVE_CHAINED_SEGMENT:rides_under_local_parent:"
                + (parent_motor or "unknown")
                + ";standalone_withheld_no_independent_motor_or_mergeboss"
            )
            may_generate = False

        # 5) Known chained segments with local parent — belt-and-suspenders even
        #    if some soft signal looks independent (still no fabricated I/O).
        elif tag in KNOWN_CHAINED_SEGMENTS and chained_under_local and not ctrl_motors:
            classification = CLASS_CHAINED
            reason = (
                "ACTIVE_CHAINED_SEGMENT:known_chain_segment_under:"
                + (parent_motor or "unknown")
            )
            may_generate = False

        # 6) Independent standalone evidence → ACTIVE_CONTROLLED.
        elif independent and controller_local and (
            machine_match or owner_local or fidelity_local or ctrl_motors or pe_set
        ):
            classification = CLASS_ACTIVE
            reason = "corroborating_ops:" + "+".join(sorted(set(flags)))
            may_generate = True

        # 7) Soft controller-local without independent motor/merge — do NOT
        #    promote on Motor_Chained alone; REVIEW or CHAINED already handled.
        elif controller_local and (machine_match or fidelity_local or pe_set) and independent:
            classification = CLASS_ACTIVE
            reason = "corroborating_ops:" + "+".join(sorted(set(flags)))
            may_generate = True

        elif mtr_hits or asc:
            classification = CLASS_REVIEW
            reason = "ops_signals_without_controller_local_ownership:" + "+".join(
                sorted(set(flags)) or ["none"]
            )
            may_generate = False
        else:
            classification = CLASS_VISUAL
            reason = "visualization_or_asc_without_operational_evidence"
            may_generate = False

        # Name-only PE policy: topology authority only. Chained segments inherit
        # none — empty allow-list forces NO_PE strip at filter time.
        pe_allowed = list(pe_set) if classification == CLASS_ACTIVE else []
        if classification == CLASS_CHAINED:
            pe_allowed = []

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
                "pe_name_only_blocked": [],
                "merge_owners": owners,
                "owner_local": owner_local,
                "parent_motor": chain_meta["parent_motor"],
                "local_parent_motors": chain_meta["local_parent_motors"],
                "source_chain": chain_meta["source_chain"],
                "standalone_withheld_reason": (
                    reason if classification == CLASS_CHAINED else None
                ),
            }
        )

    by_tag = {r["conveyor"]: r for r in records}
    active = sorted(r["conveyor"] for r in records if r["may_generate"])
    cons = conservation_summary(records)
    counts = dict(cons["counts"])
    return {
        "machine": machine,
        "run_dir": str(run_dir),
        "records": records,
        "by_tag": by_tag,
        "active_controlled": active,
        "active_chained_segments": sorted(
            r["conveyor"] for r in records if r["classification"] == CLASS_CHAINED
        ),
        "counts": counts,
        "conservation_ok": cons["conservation_ok"],
        "classes": list(ALL_CLASSES),
    }


def filter_conveyors_active_controlled(
    conveyors: list[Any],
    gate: dict[str, Any],
) -> tuple[list[Any], dict[str, Any]]:
    """Keep only may_generate / ACTIVE_CONTROLLED conveyors."""
    by_tag = gate.get("by_tag") or {}
    kept: list[Any] = []
    dropped: list[dict[str, Any]] = []
    chained_retained: list[dict[str, Any]] = []
    for c in conveyors:
        tag = _clean(getattr(c, "conveyor", None) or getattr(c, "name", None)).upper()
        rec = by_tag.get(tag) or {}
        cls = rec.get("classification") or CLASS_REVIEW
        if rec.get("may_generate") and cls == CLASS_ACTIVE:
            try:
                setattr(c, "active_control_class", cls)
                setattr(c, "active_control_reason", rec.get("reason"))
            except Exception:
                pass
            allowed = {x.upper() for x in (rec.get("pe_topology_allowed") or [])}
            _strip_name_only_pe(c, allowed)
            kept.append(c)
        else:
            drop = {
                "conveyor": tag,
                "classification": cls,
                "reason": rec.get("reason") or "not_in_active_gate",
                "parent_motor": rec.get("parent_motor"),
                "source_chain": rec.get("source_chain"),
                "standalone_withheld_reason": rec.get("standalone_withheld_reason"),
            }
            dropped.append(drop)
            if cls == CLASS_CHAINED:
                chained_retained.append(drop)
    meta = {
        "kept": [_clean(getattr(c, "conveyor", "")).upper() for c in kept],
        "dropped": dropped,
        "chained_segments_retained": chained_retained,
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
        boss = _clean(
            row.get("discovery_name") or row.get("control_object") or row.get("name")
        )
        lane_a = _clean(row.get("lane_a") or row.get("induct") or "").upper()
        lane_b = _clean(row.get("lane_b") or row.get("main") or "").upper()
        lanes = [x for x in (lane_a, lane_b) if x]
        lanes_active = all(x in active for x in lanes) if lanes else False
        discharge = _clean(row.get("discharge") or "").upper()

        for pe_key in ("pe_a", "pe_b", "pe_c", "jam_pe"):
            raw = _clean(row.get(pe_key))
            if not raw:
                continue
            allowed = False
            for lane in lanes:
                rec = by_tag.get(lane) or {}
                if raw.upper() in {
                    x.upper() for x in (rec.get("pe_topology_allowed") or [])
                }:
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

        needs_closure = False
        for lane in lanes:
            rec = by_tag.get(lane) or {}
            if rec.get("classification") != CLASS_ACTIVE:
                continue
            flags = set(rec.get("flags") or [])
            if (
                "mergeboss_owner" in flags
                and "motor_starter_controller_scoped" not in flags
            ):
                needs_closure = True
                break

        if lanes_active and needs_closure and run_dir and machine:
            route_dis = _merge_route_discharge(Path(run_dir), machine, boss)
            if route_dis:
                row["discharge"] = route_dis
                row["classification"] = CLASS_ACTIVE
                row["status"] = "PROVEN"
                row["may_generate"] = True
                row["authorization"] = (
                    "merge_ownership_closure+mergeroute_discharge:" + route_dis
                )
                out.append(row)
                meta["authorized"].append(boss)
                continue

        row["may_generate"] = False
        if _clean(row.get("classification")).upper() not in {
            CLASS_REVIEW,
            "REVIEW",
            CLASS_FOREIGN,
        }:
            row["classification"] = CLASS_REVIEW
            row["status"] = CLASS_REVIEW
        row["authorization"] = (
            "withheld_discharge_unproven_or_no_merge_closure_need"
        )
        out.append(row)
        meta["withheld"].append(boss)

    return out, meta

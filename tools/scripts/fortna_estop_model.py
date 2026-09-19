#!/usr/bin/env python3
"""E-stop Device / Circuit / Zone model.

E-stop device != E-stop circuit != E-stop zone.
Do not group devices merely because names share digits.
Safety generation is gated on membership confidence or engineer confirm.

GATE 8 — Part→Conveyor proves MACHINE ownership only.
Rockwell operational Safety-zone membership requires engineer Assign+Apply.
Never mint operational `{machine}_ESZone1` / `{Area}_ESZone1` placeholders.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from fortna_fortna_table_resolver import resolve_active_asc
from fortna_site_model import (
    PROV_RUN_EXPLICIT,
    _clean,
    normalize_name,
)

CONFIRMED = "CONFIRMED"
HIGH = "HIGH_CONFIDENCE"
CANDIDATE = "CANDIDATE"
ENGINEER_REQUIRED = "ENGINEER_REQUIRED"

# Site Forge ownership vocabulary (GATE 8)
OWN_PROVEN = "PROVEN"
OWN_REVIEW = "REVIEW_REQUIRED"
OWN_UNKNOWN = "UNKNOWN"

_BLANK_PART = frozenset({"", "N/A", "NONE", "INVALID", "~", "-", "0"})


def _looks_like_device(name: str) -> bool:
    n = name.upper()
    return bool(
        re.match(r"^\d*ES\d*", n)
        or re.match(r"^ES\d+", n)
        or re.match(r"^\d+ES$", n)
        or n.startswith("ESR")
        or n.startswith("MCR")
    )


def _is_blank(val: str | None) -> bool:
    return not val or str(val).strip().upper() in _BLANK_PART


def _device_name(row: dict[str, Any], part: str) -> str:
    """Prefer Desc/Name/IO_Name; fall back to Part when Desc is blank/N/A."""
    for key in ("Name", "IO_Name", "Desc"):
        raw = _clean(row.get(key))
        if raw and not _is_blank(raw):
            return raw
    return part


def _index_conveyors(resolved: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in resolved.get("merged_rows") or []:
        row = item.get("row") or {}
        ident = item.get("identity") or _clean(
            row.get("IO_Name") or row.get("Name") or row.get("Conveyor")
        )
        if not ident:
            continue
        out.setdefault(normalize_name(ident), item)
    return out


def _closure_conveyor_ids(run_dir, machine: str) -> set[str]:
    try:
        from fortna_machine_closure import build_machine_closure

        closure = build_machine_closure(run_dir, machine)
    except Exception:
        return set()
    ids: set[str] = set()
    for m in closure.get("members") or []:
        if m.get("source_table") != "Conveyor":
            continue
        ident = m.get("identity")
        if ident:
            ids.add(normalize_name(ident))
    return ids


def _part_machine_ownership(
    *,
    part: str,
    machine: str,
    conv_item: dict[str, Any] | None,
    conv_resolved: dict[str, Any],
    closure_ids: set[str],
) -> tuple[str | None, str]:
    """Return (part_conveyor identity, machine_ownership class)."""
    if _is_blank(part):
        return None, OWN_UNKNOWN
    if conv_item is None:
        return None, OWN_UNKNOWN

    row = conv_item.get("row") or {}
    ident = (
        conv_item.get("identity")
        or _clean(row.get("IO_Name") or row.get("Name") or row.get("Conveyor"))
        or part
    )
    mach_bind = normalize_name(row.get("Machine_Name") or row.get("Owner") or "")
    target = normalize_name(machine)

    if mach_bind and mach_bind == target:
        return ident, OWN_PROVEN
    if mach_bind and mach_bind not in {"", "n/a", "na", "none", "invalid", "all", "0"}:
        # Explicit foreign Machine_Name — never treat as current-machine inventory
        return ident, "FOREIGN"
    if normalize_name(ident) in closure_ids:
        return ident, OWN_PROVEN
    # Do NOT take-all MACHINE_SPECIFIC overlays when Machine_Name is blank —
    # N/A parts still need a real closure relationship.
    return ident, OWN_REVIEW


def build_estop_model(run_dir, machine: str, site: dict[str, Any] | None = None) -> dict[str, Any]:
    from pathlib import Path

    run_dir = Path(run_dir)
    fortna = run_dir / "FORTNA"
    site = site or {}
    machine = str(machine or "").strip()

    devices: list[dict[str, Any]] = []
    circuits: list[dict[str, Any]] = []
    zones: list[dict[str, Any]] = []
    memberships: list[dict[str, Any]] = []

    conv_resolved: dict[str, Any] = {"kind": "MISSING", "merged_rows": []}
    conv_index: dict[str, dict[str, Any]] = {}
    closure_ids: set[str] = set()
    if fortna.is_dir():
        try:
            conv_resolved = resolve_active_asc(fortna, "Conveyor", machine)
            conv_index = _index_conveyors(conv_resolved)
        except Exception:
            conv_resolved = {"kind": "MISSING", "merged_rows": []}
            conv_index = {}
        closure_ids = _closure_conveyor_ids(run_dir, machine)

    # Prefer EStop.asc rows via native shadow resolver; fall back to site.estop_zones
    rows: list[dict[str, Any]] = []
    if fortna.is_dir() and (
        (fortna / f"EStop.asc.{machine}").is_file() or (fortna / "EStop.asc").is_file()
    ):
        resolved = resolve_active_asc(fortna, "EStop", machine)
        for item in resolved.get("merged_rows") or []:
            row = item.get("row") or {}
            part = _clean(row.get("Part"))
            name = _device_name(row, part)
            if not name or name.startswith("==="):
                continue
            rows.append({"name": name, "part": part, "row": row, "item": item})
    else:
        for z in site.get("estop_zones") or []:
            name = z.get("raw_name") or z.get("normalized_name")
            if name:
                rows.append(
                    {
                        "name": name,
                        "part": _clean(z.get("Part") or z.get("part") or ""),
                        "row": z,
                        "item": z,
                    }
                )

    ownership_counts = {OWN_PROVEN: 0, OWN_REVIEW: 0, OWN_UNKNOWN: 0}

    for r in rows:
        name = r["name"]
        row = r["row"]
        item = r["item"]
        part = r.get("part") or _clean(row.get("Part"))
        if _looks_like_device(name) or "ZONE" not in name.upper():
            conv_item = conv_index.get(normalize_name(part)) if part else None
            part_conveyor, mach_own = _part_machine_ownership(
                part=part,
                machine=machine,
                conv_item=conv_item,
                conv_resolved=conv_resolved,
                closure_ids=closure_ids,
            )
            ownership_counts[mach_own] = ownership_counts.get(mach_own, 0) + 1
            if mach_own == "FOREIGN":
                # Explicit foreign Machine_Name on Part conveyor — exclude.
                continue
            devices.append(
                {
                    "kind": "EStopDevice",
                    "name": name,
                    "normalized_name": normalize_name(name),
                    "controller": machine,
                    "part": part or None,
                    "part_conveyor": part_conveyor,
                    "machine_ownership": mach_own,
                    # Part→Conveyor proves MACHINE ownership only — never zone membership
                    "zone_membership": OWN_REVIEW,
                    "confidence": HIGH,
                    "evidence": [
                        {
                            "kind": "estop_table_row",
                            "table": "EStop.asc",
                            "provenance": item.get("provenance") or PROV_RUN_EXPLICIT,
                            "part": part or None,
                            "part_conveyor": part_conveyor,
                            "machine_ownership": mach_own,
                        }
                    ],
                    "io_word": _clean(row.get("IO_Address_Word") or row.get("io_address_word")),
                    "io_bit": _clean(row.get("IO_Address_Bit") or row.get("io_bit")),
                    "reset_station": _clean(row.get("Reset") or row.get("ControlStation") or ""),
                    "engineer_override": None,
                }
            )
        else:
            # Named zone rows from EStop.asc are CANDIDATE shells only — never auto-operational
            zones.append(
                {
                    "kind": "EStopZone",
                    "name": name,
                    "normalized_name": normalize_name(name),
                    "controller": machine,
                    "confidence": CANDIDATE,
                    "membership": [],
                    "membership_confidence": ENGINEER_REQUIRED,
                    "evidence": [{"kind": "estop_zone_named_row", "table": "EStop.asc"}],
                    "engineer_override": None,
                    "generation_allowed": False,
                }
            )

    # Circuit inference: only when explicit circuit/field evidence exists — NOT digit sharing.
    circuit_keys: dict[str, list[str]] = defaultdict(list)
    for d in devices:
        rst = d.get("reset_station") or ""
        if rst:
            circuit_keys[f"reset:{normalize_name(rst)}"].append(d["name"])
    for key, members in circuit_keys.items():
        if len(members) < 2:
            continue
        circuits.append(
            {
                "kind": "EStopCircuit",
                "name": key,
                "members": members,
                "confidence": CANDIDATE,
                "evidence": [
                    {
                        "kind": "shared_reset_station",
                        "detail": "Devices sharing explicit reset/control-station field",
                        "provenance": PROV_RUN_EXPLICIT,
                    }
                ],
                "note": "Not inferred from shared digits in device names",
                "engineer_override": None,
            }
        )

    # GATE 8 — do NOT mint `{machine}_ESZone1` / `{Area}_ESZone1` placeholder zones.
    # Empty zones=[] ; devices may still be PROVEN for machine ownership while
    # zone_membership stays REVIEW_REQUIRED until engineer Assign+Apply.
    proven = 0
    engineer_req = 0
    if zones:
        for z in zones:
            if z.get("membership_confidence") in {CONFIRMED, HIGH} and z.get("membership"):
                proven += 1
            else:
                engineer_req += 1
                memberships.append(
                    {
                        "zone": z["name"],
                        "status": "CONFIGURATION_REQUIRED",
                        "devices_unassigned": [d["name"] for d in devices[:50]],
                        "reason": "No explicit device→zone membership evidence in RUN",
                    }
                )
    else:
        engineer_req = 1 if devices else 0
        if devices:
            memberships.append(
                {
                    "zone": None,
                    "status": "CONFIGURATION_REQUIRED",
                    "devices_unassigned": [
                        d["name"]
                        for d in devices
                        if d.get("machine_ownership") == OWN_PROVEN
                    ][:50],
                    "reason": (
                        "Part→Conveyor proves machine ownership only; "
                        "engineer must Assign+Apply operational Safety zone membership"
                    ),
                }
            )

    # Attach into site operational_groups without conflating types
    og = dict(site.get("operational_groups") or {})
    og["estop_devices"] = devices
    og["estop_circuits"] = circuits
    og["estop_zones_operational"] = zones
    og["estop_zones"] = [
        {
            **z,
            "legacy_note": "operational zone object — not device list",
        }
        for z in zones
    ]
    site["operational_groups"] = og
    site["estop_devices"] = devices
    site["estop_circuits"] = circuits

    return {
        "machine": machine,
        "devices": devices,
        "circuits": circuits,
        "zones": zones,
        "memberships": memberships,
        "counts": {
            "devices": len(devices),
            "circuits": len(circuits),
            "zones": len(zones),
            "memberships_proven": proven,
            "memberships_engineer_required": engineer_req,
            "machine_ownership_proven": ownership_counts.get(OWN_PROVEN, 0),
            "machine_ownership_review": ownership_counts.get(OWN_REVIEW, 0),
            "machine_ownership_unknown": ownership_counts.get(OWN_UNKNOWN, 0),
        },
        "safety_generation_gate": {
            "allowed": proven > 0,
            "reason": (
                "Membership CONFIRMED/HIGH"
                if proven > 0
                else "Blocked until engineer confirms zone membership"
            ),
            "blocks": ["safety_zone_logic"] if proven == 0 else [],
            "does_not_block": ["transport", "sorter_partial", "io_map", "pe_logic"],
        },
        "policy": [
            "Do not group E-stop devices by shared digits in names",
            "Safety uncertainty blocks safety generation only",
            "EStopDevice != EStopCircuit != EStopZone",
            "EStop.Part→Conveyor proves MACHINE ownership only — not Rockwell Safety-zone membership",
            "Jamzones / Areas are not automatic ES zones",
            "Default Safety / Unassigned Safety is an editor bucket only and must never compile into an operational ES zone",
            "Do not auto-create operational {machine}_ESZone1 or {Area}_ESZone1 placeholders",
            "zone_membership stays REVIEW_REQUIRED until engineer Assign+Apply",
        ],
        "notes": [
            "Part→Conveyor (resolve_active_asc + MachineClosure when available) sets machine_ownership.",
            "Empty zones=[] until engineer creates/assigns operational ES zones.",
        ],
    }


def safety_generation_allowed(estop_model: dict[str, Any], engineer_confirmed: bool = False) -> bool:
    gate = estop_model.get("safety_generation_gate") or {}
    if engineer_confirmed:
        return True
    return bool(gate.get("allowed"))

#!/usr/bin/env python3
"""E-stop Device / Circuit / Zone model.

E-stop device != E-stop circuit != E-stop zone.
Do not group devices merely because names share digits.
Safety generation is gated on membership confidence or engineer confirm.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from fortna_site_model import (
    AVAILABLE,
    GEN_CFG,
    GEN_NOT_SUPPORTED,
    PROV_ENGINEER,
    PROV_RUN_EXPLICIT,
    _clean,
    merge_table_rows,
    normalize_name,
)

CONFIRMED = "CONFIRMED"
HIGH = "HIGH_CONFIDENCE"
CANDIDATE = "CANDIDATE"
ENGINEER_REQUIRED = "ENGINEER_REQUIRED"


def _looks_like_device(name: str) -> bool:
    n = name.upper()
    return bool(
        re.match(r"^\d*ES\d*", n)
        or re.match(r"^ES\d+", n)
        or re.match(r"^\d+ES$", n)
        or n.startswith("ESR")
        or n.startswith("MCR")
    )


def build_estop_model(run_dir, machine: str, site: dict[str, Any] | None = None) -> dict[str, Any]:
    from pathlib import Path

    run_dir = Path(run_dir)
    fortna = run_dir / "FORTNA"
    site = site or {}

    devices: list[dict[str, Any]] = []
    circuits: list[dict[str, Any]] = []
    zones: list[dict[str, Any]] = []
    memberships: list[dict[str, Any]] = []

    # Prefer EStop.asc rows; fall back to site.estop_zones (legacy mislabeled devices)
    rows: list[dict[str, Any]] = []
    if fortna.is_dir() and list(fortna.glob("EStop.asc*")):
        merged = merge_table_rows(fortna, "EStop.asc", machine)
        for item in merged.get("rows") or []:
            row = item.get("row") or {}
            name = _clean(row.get("Name") or row.get("IO_Name") or row.get("Desc"))
            if not name or name.startswith("==="):
                continue
            rows.append({"name": name, "row": row, "item": item})
    else:
        for z in site.get("estop_zones") or []:
            name = z.get("raw_name") or z.get("normalized_name")
            if name:
                rows.append({"name": name, "row": z, "item": z})

    for r in rows:
        name = r["name"]
        row = r["row"]
        item = r["item"]
        if _looks_like_device(name) or "ZONE" not in name.upper():
            devices.append(
                {
                    "kind": "EStopDevice",
                    "name": name,
                    "normalized_name": normalize_name(name),
                    "controller": machine,
                    "confidence": HIGH,
                    "evidence": [
                        {
                            "kind": "estop_table_row",
                            "table": "EStop.asc",
                            "provenance": item.get("provenance") or PROV_RUN_EXPLICIT,
                        }
                    ],
                    "io_word": _clean(row.get("IO_Address_Word") or row.get("io_address_word")),
                    "io_bit": _clean(row.get("IO_Address_Bit") or row.get("io_address_bit")),
                    "reset_station": _clean(row.get("Reset") or row.get("ControlStation") or ""),
                    "engineer_override": None,
                }
            )
        else:
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
    # Documented latch/reset groups if present in row fields.
    circuit_keys: dict[str, list[str]] = defaultdict(list)
    for d in devices:
        # Explicit reset/control-station relationship can imply a circuit family
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

    # Memberships: without explicit zone table links → engineer required
    proven = 0
    engineer_req = 0
    if not zones:
        # No operational zones proven — expose empty zone requiring engineer
        zones.append(
            {
                "kind": "EStopZone",
                "name": f"{machine}_ESZone1",
                "normalized_name": normalize_name(f"{machine}_ESZone1"),
                "controller": machine,
                "confidence": ENGINEER_REQUIRED,
                "membership": [],
                "membership_confidence": ENGINEER_REQUIRED,
                "evidence": [
                    {
                        "kind": "default_safety_placeholder",
                        "detail": "No operational E-stop zone proven from RUN; engineer must confirm",
                    }
                ],
                "engineer_override": None,
                "generation_allowed": False,
            }
        )
        engineer_req += 1
    else:
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

    # Attach into site operational_groups without conflating types
    og = dict(site.get("operational_groups") or {})
    og["estop_devices"] = devices
    og["estop_circuits"] = circuits
    og["estop_zones_operational"] = zones
    # Keep legacy key but annotate
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
        ],
    }


def safety_generation_allowed(estop_model: dict[str, Any], engineer_confirmed: bool = False) -> bool:
    gate = estop_model.get("safety_generation_gate") or {}
    if engineer_confirmed:
        return True
    return bool(gate.get("allowed"))

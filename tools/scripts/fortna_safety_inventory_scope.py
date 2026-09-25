#!/usr/bin/env python3
"""Active-controller Safety inventory classification (GATE D).

LOCAL_PHYSICAL      — current-machine physical Safety devices (normal assign list)
REMOTE_DEPENDENCY    — proven cross-controller Safety dependency (explicit contract)
UNRELATED_FOREIGN    — other controllers' devices (hidden from normal assignment)

ACTIVE MACHINE OWNS COMPILER STATE. Name similarity is never ownership proof.
"""
from __future__ import annotations

import re
from typing import Any


LOCAL_PHYSICAL = "LOCAL_PHYSICAL"
REMOTE_DEPENDENCY = "REMOTE_DEPENDENCY"
UNRELATED_FOREIGN = "UNRELATED_FOREIGN"


def classify_safety_device_scope(
    device: dict[str, Any] | str,
    *,
    active_machine: str,
    proven_remote_deps: set[str] | None = None,
) -> str:
    """Classify a Safety device relative to the active controller."""
    mach = str(active_machine or "").strip().upper()
    proven_remote_deps = proven_remote_deps or set()
    if isinstance(device, str):
        name = device
        dev_mach = ""
        cross = False
    else:
        name = str(
            device.get("name")
            or device.get("canonicalTag")
            or device.get("id")
            or ""
        ).strip()
        dev_mach = str(
            device.get("machine")
            or device.get("Machine_Name")
            or device.get("controller")
            or ""
        ).strip().upper()
        cross = bool(
            device.get("crossControllerDependency")
            or device.get("remote_dependency")
            or device.get("isRemoteDependency")
        )
    key = name.upper()
    if key in {p.upper() for p in proven_remote_deps} or cross:
        return REMOTE_DEPENDENCY
    if not mach:
        return LOCAL_PHYSICAL  # no active machine → treat as local (session incomplete)
    if not dev_mach or dev_mach in {"N/A", "NA", "ALL", "", "NONE"}:
        return LOCAL_PHYSICAL
    if dev_mach == mach:
        return LOCAL_PHYSICAL
    return UNRELATED_FOREIGN


def partition_safety_inventory(
    devices: list[dict[str, Any]],
    *,
    active_machine: str,
    proven_remote_deps: set[str] | None = None,
) -> dict[str, Any]:
    """Partition inventory for UI + External Safety Dependency Manifest."""
    buckets = {
        LOCAL_PHYSICAL: [],
        REMOTE_DEPENDENCY: [],
        UNRELATED_FOREIGN: [],
    }
    for d in devices or []:
        scope = classify_safety_device_scope(
            d, active_machine=active_machine, proven_remote_deps=proven_remote_deps
        )
        row = dict(d) if isinstance(d, dict) else {"name": str(d)}
        row["inventory_scope"] = scope
        buckets[scope].append(row)
    remote_manifest = []
    for d in buckets[REMOTE_DEPENDENCY]:
        remote_manifest.append(
            {
                "local_consumer": d.get("name"),
                "remote_plc_owner": d.get("machine") or d.get("controller") or "UNKNOWN",
                "produced_tag": d.get("produced_tag") or "",
                "consumed_tag": d.get("consumed_tag") or "",
                "status": (
                    "PROVEN"
                    if (d.get("produced_tag") and d.get("consumed_tag"))
                    else "REVIEW_REQUIRED"
                ),
                "note": (
                    "Do not invent Produced/Consumed endpoints — "
                    "engineer/communication mapping required"
                ),
            }
        )
    return {
        "active_machine": active_machine,
        "counts": {k: len(v) for k, v in buckets.items()},
        "local_physical": buckets[LOCAL_PHYSICAL],
        "remote_dependency": buckets[REMOTE_DEPENDENCY],
        "unrelated_foreign": buckets[UNRELATED_FOREIGN],
        "external_safety_dependency_manifest": remote_manifest,
        "assignable": buckets[LOCAL_PHYSICAL],  # normal Safety assignment list
    }

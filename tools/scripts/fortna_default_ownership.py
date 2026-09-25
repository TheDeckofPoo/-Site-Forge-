#!/usr/bin/env python3
"""Default Area / Default Safety ownership conservation (Gates 2, 3, 7, 8).

Site Forge canonical ownership buckets — NOT RUN provenance and NOT operational
E-stop zones. Equipment/devices not in an engineer Area/Zone belong to Default.

Invariant:
  discovered == default + sum(engineer buckets) + proven_exclusions
  (no duplicates, nothing disappears on create/move/delete)
"""
from __future__ import annotations

import re
from typing import Any, Iterable

DEFAULT_AREA_NAME = "Default Area"
DEFAULT_SAFETY_NAME = "Default Safety"
UNASSIGNED_SAFETY_NAME = "Unassigned Safety"
DEFAULT_SAFETY_ALIASES = frozenset(
    {
        DEFAULT_SAFETY_NAME.lower(),
        UNASSIGNED_SAFETY_NAME.lower(),
        "default",
        "unassigned",
        # Underscore / Logix-tag forms (Warden: Default_Safety emitted operational)
        "default_safety",
        "unassigned_safety",
        "default_safety_zone",
        "unassigned_safety_zone",
    }
)
# Legacy SiteModel / discovery placeholders still treated as default ownership.
DEFAULT_AREA_ALIASES = frozenset(
    {
        DEFAULT_AREA_NAME.lower(),
        "area_1",
        "unassigned",
        "main_area",
    }
)


def is_default_area_name(name: str | None) -> bool:
    s = str(name or "").strip().lower()
    if not s:
        return True
    if s in DEFAULT_AREA_ALIASES:
        return True
    if s.endswith("_imported") or s == "run_imported":
        return True
    return False


def is_default_safety_name(name: str | None) -> bool:
    """True for Default/Unassigned Safety ownership buckets (never operational).

    Accepts space and underscore forms: 'Default Safety', 'Default_Safety',
    'UNASSIGNED_SAFETY', etc. These must never receive ES_PI20 / ES_SIL1 /
    Fast_Conv Safety operands.
    """
    s = str(name or "").strip().lower()
    if not s:
        return True
    if s in DEFAULT_SAFETY_ALIASES:
        return True
    # Normalize spaces/hyphens → underscore for alias match
    su = re.sub(r"[\s\-]+", "_", s)
    if su in DEFAULT_SAFETY_ALIASES:
        return True
    if su.startswith("default_") and "eszone" in su:
        return True
    if su.startswith("unassigned_") and "eszone" in su:
        return True
    return False


def area_is_default(area: dict[str, Any] | None) -> bool:
    if not isinstance(area, dict):
        return False
    if area.get("isDefault") or area.get("defaultArea") or area.get("default_area"):
        return True
    return is_default_area_name(
        area.get("name") or area.get("raw_name") or area.get("area_id")
    )


def safety_zone_is_default(zone: dict[str, Any] | None) -> bool:
    if not isinstance(zone, dict):
        return False
    if zone.get("isDefault") or zone.get("isUnassignedBucket") or zone.get("defaultSafety"):
        return True
    if zone.get("operational") is False and (
        zone.get("isDefault") or zone.get("isUnassignedBucket")
    ):
        return True
    sid = str(zone.get("source_id") or zone.get("id") or "").strip()
    name = str(zone.get("engineering_name") or zone.get("name") or sid).strip()
    return is_default_safety_name(sid) or is_default_safety_name(name)


def _norm_tag(tag: Any) -> str:
    return str(tag or "").strip().upper()


def transport_ownership_counts(
    areas: Iterable[dict[str, Any]],
    *,
    discovered: int | None = None,
    proven_exclusions: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Count plc-owned transport nodes by Default vs engineer Areas.

    Proven exclusions (displayContext / EXTERNAL_REFERENCE / OUT_OF_SCOPE) are
    counted separately and do not belong to Default or engineer Areas.
    """
    excl = {_norm_tag(x) for x in (proven_exclusions or []) if _norm_tag(x)}
    seen: set[str] = set()
    default_tags: list[str] = []
    engineer: dict[str, list[str]] = {}
    dupes: list[str] = []

    for area in areas or []:
        if not isinstance(area, dict):
            continue
        aname = str(area.get("name") or area.get("id") or "").strip() or "(unnamed)"
        bucket_default = area_is_default(area)
        for n in area.get("nodes") or []:
            if not isinstance(n, dict):
                continue
            if n.get("displayContext") or n.get("plcOwned") is False:
                tag = _norm_tag(n.get("conveyorTag") or n.get("label") or n.get("id"))
                if tag:
                    excl.add(tag)
                continue
            if str(n.get("scopeClass") or "").upper() in {
                "OUT_OF_SCOPE",
                "UNRESOLVED",
                "EXTERNAL_REFERENCE",
            }:
                tag = _norm_tag(n.get("conveyorTag") or n.get("label") or n.get("id"))
                if tag:
                    excl.add(tag)
                continue
            tag = _norm_tag(n.get("conveyorTag") or n.get("label") or n.get("id"))
            if not tag:
                continue
            if tag in seen:
                dupes.append(tag)
                continue
            seen.add(tag)
            if bucket_default:
                default_tags.append(tag)
            else:
                engineer.setdefault(aname, []).append(tag)

    eng_total = sum(len(v) for v in engineer.values())
    default_n = len(default_tags)
    excl_n = len(excl - seen)
    owned = default_n + eng_total
    disc = int(discovered) if discovered is not None else owned + excl_n
    ok = disc == owned + excl_n and not dupes
    return {
        "discovered": disc,
        "default": default_n,
        "default_tags": default_tags,
        "engineer": {k: len(v) for k, v in engineer.items()},
        "engineer_tags": engineer,
        "engineer_total": eng_total,
        "proven_exclusions": excl_n,
        "dupes": dupes,
        "ok": ok,
        "invariant": "discovered == default + sum(engineer) + proven_exclusions",
    }


def safety_ownership_counts(
    devices: Iterable[dict[str, Any] | str],
    zones: Iterable[dict[str, Any]],
    *,
    discovered: int | None = None,
) -> dict[str, Any]:
    """Count safety devices by Default/Unassigned vs engineer operational zones."""
    device_names: list[str] = []
    for d in devices or []:
        if isinstance(d, str):
            nm = _norm_tag(d)
        elif isinstance(d, dict):
            nm = _norm_tag(d.get("name") or d.get("originalName"))
        else:
            nm = ""
        if nm:
            device_names.append(nm)
    disc = int(discovered) if discovered is not None else len(device_names)
    assigned: dict[str, str] = {}
    dupes: list[str] = []
    engineer: dict[str, list[str]] = {}
    for z in zones or []:
        if not isinstance(z, dict):
            continue
        if safety_zone_is_default(z):
            continue  # virtual bucket — members are unassigned
        zname = str(
            z.get("engineering_name") or z.get("name") or z.get("source_id") or ""
        ).strip()
        for m in z.get("members") or []:
            key = _norm_tag(m)
            if not key:
                continue
            if key in assigned:
                dupes.append(key)
                continue
            assigned[key] = zname
            engineer.setdefault(zname, []).append(key)

    device_set = set(device_names)
    assigned_in_inventory = {k: v for k, v in assigned.items() if k in device_set or not device_set}
    if device_set:
        default_n = len(device_set - set(assigned_in_inventory))
        eng_total = len(set(assigned_in_inventory) & device_set)
    else:
        eng_total = len(assigned_in_inventory)
        default_n = max(0, disc - eng_total)
    ok = disc == default_n + eng_total and not dupes
    return {
        "discovered": disc,
        "default": default_n,
        "unassigned": default_n,
        "engineer": {k: len(v) for k, v in engineer.items()},
        "engineer_total": eng_total,
        "assigned": eng_total,
        "dupes": dupes,
        "ok": ok,
        "invariant": "discovered == default/unassigned + sum(engineer zones)",
        "default_safety_name": DEFAULT_SAFETY_NAME,
        "unassigned_safety_name": UNASSIGNED_SAFETY_NAME,
    }


def make_default_area(*, area_id: str = "area_default", nodes: list | None = None) -> dict[str, Any]:
    """Site Forge Default Area shell (canonical ownership — not RUN provenance)."""
    return {
        "id": area_id,
        "name": DEFAULT_AREA_NAME,
        "isDefault": True,
        "defaultArea": True,
        "provenance": "SITE_FORGE_DEFAULT",
        "nodes": list(nodes or []),
        "wires": [],
        "defaultSafetyZone": "",
    }


def make_default_safety_zone(
    *,
    unassigned_members: Iterable[str] | None = None,
    devices_found: int = 0,
) -> dict[str, Any]:
    """Non-operational Default/Unassigned Safety bucket for UI + conservation."""
    members = [str(m).strip() for m in (unassigned_members or []) if str(m).strip()]
    return {
        "id": DEFAULT_SAFETY_NAME,
        "source_id": DEFAULT_SAFETY_NAME,
        "name": DEFAULT_SAFETY_NAME,
        "engineering_name": DEFAULT_SAFETY_NAME,
        "display_name": UNASSIGNED_SAFETY_NAME,
        "isDefault": True,
        "isUnassignedBucket": True,
        "defaultSafety": True,
        "operational": False,
        "areaRef": "",
        "conveyorRefs": [],
        "members": members,
        "membersOrigin": "UNASSIGNED",
        "membership_status": "REVIEW_REQUIRED",
        "status": "REVIEW_REQUIRED",
        "provenance": "SITE_FORGE_DEFAULT",
        "origin": "SITE_FORGE_DEFAULT",
        "hard_missing": ["SafetyDevices"] if members or devices_found else [],
        "eStops": [],
        "esrDevices": [],
        "mcrDevices": [],
        "csDevices": [],
        "eslsDevices": [],
        "note": (
            "Default/Unassigned Safety — ownership bucket only, "
            "NOT an operational E-stop zone. UNASSIGNED → REVIEW_REQUIRED fail-safe."
        ),
    }


def return_transport_to_default(
    areas: list[dict[str, Any]],
    area_id: str,
) -> list[dict[str, Any]]:
    """Delete engineer area by id; move members into Default Area (nothing lost)."""
    areas = [a for a in areas if isinstance(a, dict)]
    target = next((a for a in areas if str(a.get("id") or "") == str(area_id)), None)
    if target is None:
        target = next(
            (
                a
                for a in areas
                if str(a.get("name") or "").strip().lower() == str(area_id).strip().lower()
            ),
            None,
        )
    if target is None:
        raise KeyError(f"area not found: {area_id}")
    if area_is_default(target):
        raise ValueError("cannot delete Default Area")

    default = next((a for a in areas if area_is_default(a)), None)
    if default is None:
        default = make_default_area()
        areas.insert(0, default)

    moving = list(target.get("nodes") or [])
    default.setdefault("nodes", []).extend(moving)
    # Drop area-local wires (cross-area visuals not supported); tag topology on nodes preserved
    target["nodes"] = []
    target["wires"] = []
    areas = [a for a in areas if a is not target]
    return areas


def assign_safety_members(
    zones: list[dict[str, Any]],
    device_names: Iterable[str],
    dest_zone: str,
) -> list[dict[str, Any]]:
    """Add devices into an engineer zone (many-to-many). Idempotent.

    Does NOT remove the device from other zones — a canonical Safety device may
    participate in multiple zones (e.g. shared MCR). Removing a membership is a
    separate explicit action on that zone only.
    """
    dest = str(dest_zone or "").strip()
    if not dest or is_default_safety_name(dest):
        raise ValueError("destination must be an engineer Safety Zone (not Default/Unassigned)")
    names = [str(n).strip() for n in device_names if str(n).strip()]
    if not names:
        return zones
    dest_z = next(
        (
            z
            for z in zones
            if not safety_zone_is_default(z)
            and (
                str(z.get("source_id") or "").strip() == dest
                or str(z.get("engineering_name") or z.get("name") or "").strip() == dest
            )
        ),
        None,
    )
    if dest_z is None:
        dest_z = {
            "id": dest,
            "source_id": dest,
            "name": dest,
            "engineering_name": dest,
            "members": [],
            "memberMeta": {},
            "membersOrigin": "ENGINEER_ASSIGNED",
            "engineerEdited": True,
            "createdBy": "engineer",
            "provenance": "ENGINEER_CREATED",
            "origin": "ENGINEER_CREATED",
            "operational": True,
            "status": "REVIEW_REQUIRED",
        }
        zones.append(dest_z)
    seen = {str(m).strip().upper() for m in (dest_z.get("members") or [])}
    meta = dest_z.setdefault("memberMeta", {})
    if not isinstance(meta, dict):
        meta = {}
        dest_z["memberMeta"] = meta
    for n in names:
        if n.upper() in seen:
            continue
        dest_z.setdefault("members", []).append(n)
        seen.add(n.upper())
        prev = meta.get(n) if isinstance(meta.get(n), dict) else {}
        # Never upgrade engineer membership to PROVEN; preserve RUN edges.
        if prev.get("origin") and re.search(r"PROVEN|RUN", str(prev.get("origin") or ""), re.I):
            meta[n] = dict(prev)
        else:
            meta[n] = {
                "origin": "ENGINEER_ASSIGNED",
                "assignedBy": "engineer",
                **({k: v for k, v in prev.items() if k == "assignedAt"}),
            }
    dest_z["membersOrigin"] = "ENGINEER_ASSIGNED"
    dest_z["engineerEdited"] = True
    return zones


def delete_safety_zone_return_to_default(
    zones: list[dict[str, Any]],
    zone_name: str,
) -> list[dict[str, Any]]:
    """Remove engineer zone; members become Default/Unassigned (conservation)."""
    zname = str(zone_name or "").strip()
    if not zname:
        return zones
    if is_default_safety_name(zname):
        raise ValueError("cannot delete Default/Unassigned Safety bucket")
    out: list[dict[str, Any]] = []
    for z in zones:
        sid = str(z.get("source_id") or z.get("id") or "").strip()
        eng = str(z.get("engineering_name") or z.get("name") or "").strip()
        if sid == zname or eng == zname:
            if safety_zone_is_default(z):
                raise ValueError("cannot delete Default/Unassigned Safety bucket")
            continue
        out.append(z)
    return out

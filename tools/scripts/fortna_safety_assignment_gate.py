#!/usr/bin/env python3
"""ORI-061/065/067/068: engineer-assigned Safety intent integrity.

Never silently drop an assigned Safety device from Safe_Logic while declaring
the build CURRENT.

ORI-068: engineer intent is explicit operational-zone membership only —
Default / Unassigned inventory is NOT engineer build intent.
"""
from __future__ import annotations

import re
from typing import Any


def _norm(name: str) -> str:
    return str(name or "").strip().upper()


def _strip_t(name: str) -> str:
    n = _norm(name)
    return n[2:] if n.startswith("T_") else n


_DEFAULT_ZONE_NAMES = frozenset(
    {
        "DEFAULT SAFETY",
        "UNASSIGNED SAFETY",
        "DEFAULT_SAFETY",
        "UNASSIGNED_SAFETY",
        "DEFAULT",
        "UNASSIGNED",
        "DEFAULT SAFETY / UNASSIGNED SAFETY",
    }
)


def _is_default_zone(z: dict[str, Any]) -> bool:
    """System Default/Unassigned bucket — explicit flags or exact identity only.

    ORI-045: ordinary engineer labels containing the substring "default" /
    "unassigned" (e.g. "Default Packaging EStops") are NOT system Default.
    """
    if (
        z.get("defaultSafety")
        or z.get("isDefault")
        or z.get("isUnassignedBucket")
        or str(z.get("zoneOrigin") or "").strip().upper() in {"DEFAULT", "UNASSIGNED", "SITE_FORGE_DEFAULT"}
    ):
        return True
    if z.get("operational") is False and not (
        z.get("engineerEdited")
        or z.get("createdBy") == "engineer"
        or str(z.get("zoneOrigin") or "").upper() == "ENGINEER"
    ):
        return True
    for key in ("name", "engineering_name", "id", "source_id"):
        n = _norm(str(z.get(key) or ""))
        if n in _DEFAULT_ZONE_NAMES:
            return True
        # Exact "Default Safety …" system bucket spelling only — not substring.
        if n == "DEFAULT SAFETY" or n.startswith("DEFAULT SAFETY /"):
            return True
        if n == "UNASSIGNED SAFETY" or n.startswith("UNASSIGNED SAFETY /"):
            return True
    return False


def _is_engineer_zone(z: dict[str, Any]) -> bool:
    """True when zone carries durable engineer authorship / assignment.

    ORI-045: prefer explicit zoneOrigin=ENGINEER / ENGINEER_CREATED provenance.
    Must NOT require Area existence, areaRef, or szone_ name shape alone.
    """
    if _is_default_zone(z):
        return False
    zo = str(z.get("zoneOrigin") or "").strip().upper()
    if zo == "ENGINEER":
        return True
    origin = str(z.get("membersOrigin") or z.get("membership_origin") or "").upper()
    if z.get("engineerEdited") or z.get("createdBy") == "engineer":
        return True
    if "ENGINEER" in origin:
        return True
    sid = str(z.get("source_id") or z.get("id") or "")
    if sid.startswith("szone_"):
        return True
    prov = str(z.get("provenance") or z.get("origin") or "").upper()
    if "ENGINEER" in prov:
        return True
    # Member-bearing non-RUN zones are engineer intent after Area delete
    if (z.get("members") or []) and not z.get("runDiscovered") and "RUN" not in prov:
        if z.get("areaUnlinked") or zo == "ENGINEER":
            return True
    return False


def explicit_engineer_assigned_members(
    engineer_zones: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """ORI-068: canonical engineer-intent set.

    Returns list of {zone, device} for explicit engineer operational-zone
    memberships only. Default / Unassigned / discovered inventory are excluded.
    """
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for z in engineer_zones or []:
        if not isinstance(z, dict):
            continue
        if _is_default_zone(z):
            continue
        if not _is_engineer_zone(z):
            # Hollow RUN shells / inventory buckets are not engineer intent
            continue
        zname = str(z.get("name") or z.get("engineering_name") or "").strip()
        for raw in z.get("members") or []:
            mem = str(raw or "").strip()
            if not mem:
                continue
            key = (_norm(zname), _norm(mem))
            if key in seen:
                continue
            seen.add(key)
            out.append({"zone": zname, "device": mem, "zone_ref": z})
    return out


def _device_index(safety_devices: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    for d in safety_devices or []:
        if not isinstance(d, dict):
            continue
        for key in (
            d.get("name"),
            d.get("canonicalTag"),
            d.get("id"),
        ):
            k = _norm(str(key or ""))
            if k:
                idx[k] = d
                idx[_strip_t(k)] = d
                idx["T_" + _strip_t(k)] = d
    return idx


def validate_engineer_assigned_safety_members(
    *,
    engineer_zones: list[dict[str, Any]] | None,
    safety_devices: list[dict[str, Any]] | None,
    written_tags: set[str] | None = None,
) -> dict[str, Any]:
    """Return {ok, blocked, violations[]} for engineer-assigned zone members.

    ORI-068: only explicit engineer operational-zone memberships are validated.
    Default inventory is never treated as engineer intent.

    A member is invalid when the canonical device is present and:
      - assignable is False, OR
      - review_reason indicates DIRECTION_MISMATCH / ENDPOINT conflict / WORD_ONLY /
        UNKNOWN_OWNER / NO_MODULE_CHANNEL_PROOF, OR
      - hardwareBacked is False with an explicit non-assignable reason

    ORI-067: writer check uses resolved AUX/feedback operand, not the command coil.
    """
    from fortna_es_compiler import (
        build_device_evidence_index,
        resolve_safety_feedback_operand,
        safety_operand_has_writer,
        studio_safety_tag,
    )

    idx = _device_index(safety_devices)
    evidence = build_device_evidence_index(safety_devices)
    violations: list[dict[str, Any]] = []
    intent = explicit_engineer_assigned_members(engineer_zones)
    for item in intent:
        mem = item["device"]
        zname = item["zone"]
        d = idx.get(_norm(mem)) or idx.get(_strip_t(mem))
        reason = ""
        code = ""
        if d is not None:
            why = str(d.get("review_reason") or "").upper()
            if d.get("assignable") is False:
                code = "SAFETY_ASSIGNED_DEVICE_INVALID"
                reason = why or "ASSIGNABLE_FALSE"
            elif "DIRECTION" in why:
                code = "SAFETY_ASSIGNED_DEVICE_INVALID"
                reason = why
            elif d.get("endpointConflict"):
                code = "SAFETY_ASSIGNED_DEVICE_INVALID"
                reason = "ENDPOINT_OWNERSHIP_CONFLICT"
            elif why in {
                "WORD_ONLY_EVIDENCE",
                "NO_MODULE_CHANNEL_PROOF",
                "UNKNOWN_OWNER",
                "NO_PHYSICAL_ENDPOINT",
                "FOREIGN_EVIDENCE",
            }:
                code = "SAFETY_ASSIGNED_DEVICE_INVALID"
                reason = why
            elif d.get("hardwareBacked") is False and why:
                code = "SAFETY_ASSIGNED_DEVICE_INVALID"
                reason = why
            # Writer required when written_tags provided (post IO_MAP plan)
            if (
                not code
                and written_tags is not None
                and d.get("assignable") is not False
            ):
                fo = resolve_safety_feedback_operand(mem, device_evidence=evidence)
                check_tag = (
                    fo.operand
                    if fo.status == "RESOLVED" and fo.operand
                    else (studio_safety_tag(mem) or mem)
                )
                if not safety_operand_has_writer(
                    check_tag,
                    written_tags=written_tags,
                    device_evidence=evidence,
                ):
                    # Also try canonical member — safety_operand_has_writer resolves
                    # feedback internally (ORI-067).
                    if not safety_operand_has_writer(
                        studio_safety_tag(mem) or mem,
                        written_tags=written_tags,
                        device_evidence=evidence,
                    ):
                        if d.get("hardwareBacked") is True or fo.status == "RESOLVED":
                            code = "SAFETY_ASSIGNED_DEVICE_MISSING_WRITER"
                            reason = "NO_IO_MAP_WRITER"
        if code:
            violations.append(
                {
                    "code": code,
                    "zone": zname,
                    "device": mem,
                    "reason": reason or code,
                    "assignable": (d or {}).get("assignable"),
                    "review_reason": (d or {}).get("review_reason"),
                    "physicalEndpoint": (d or {}).get("physicalEndpoint"),
                }
            )
    blocked = len(violations) > 0
    detail = ""
    if blocked:
        parts = [
            f"{v['device']} — {v['reason']}"
            + (f" (zone {v['zone']})" if v.get("zone") else "")
            for v in violations[:12]
        ]
        detail = (
            "SAFETY_ASSIGNED_DEVICE_INVALID — engineer-assigned Safety member(s) "
            "cannot be emitted; BUILD BLOCKED: " + "; ".join(parts)
        )
    return {
        "ok": not blocked,
        "blocked": blocked,
        "violations": violations,
        "detail": detail,
        "status": "ERROR" if blocked else "OK",
        "engineer_intent_count": len(intent),
        "engineer_intent_devices": sorted({i["device"] for i in intent}),
    }


# ---------------------------------------------------------------------------
# ORI-076 — canonical engineer-zone collection / durable identity dedupe
# ---------------------------------------------------------------------------

_AUTO_ESZONE_RE = re.compile(r"^.+_ESZONE\d+$", re.I)


def durable_zone_identity(z: dict[str, Any] | None) -> str:
    """Prefer immutable szone_* over name-as-sid / auto _ESZoneN shells."""
    if not isinstance(z, dict):
        return ""
    sid = str(z.get("source_id") or z.get("sourceId") or z.get("id") or "").strip()
    if sid.startswith("szone_"):
        return sid
    eng = str(z.get("engineering_name") or "").strip()
    if eng:
        return eng
    name = str(z.get("name") or "").strip()
    if name and not name.startswith("szone_"):
        return name
    return sid or name


def _zone_display_key(z: dict[str, Any]) -> str:
    return _norm(
        str(z.get("engineering_name") or z.get("name") or z.get("source_id") or "")
    )


def _zone_area_key(z: dict[str, Any]) -> str:
    return _norm(str(z.get("areaRef") or z.get("area") or ""))


def _looks_like_eszone_n(z: dict[str, Any]) -> bool:
    for key in ("source_id", "id", "name", "engineering_name"):
        if _AUTO_ESZONE_RE.match(str(z.get(key) or "").strip()):
            return True
    return False


def _is_auto_eszone_shell(z: dict[str, Any]) -> bool:
    """Hollow Transport/machine auto shell (e.g. MSCRENOPICK_ESZone1).

    RUN-discovered ``*_ESZoneN`` shells and engineer-authored zones are NOT
    auto phantoms — multiple ``*_ESZoneN`` zones may coexist on one Area.
    """
    if _is_default_zone(z):
        return False
    if z.get("runDiscovered") or str(z.get("provenance") or "").upper() == "RUN_DISCOVERED":
        return False
    if z.get("members"):
        return False
    if (
        z.get("zoneOrigin") == "ENGINEER"
        or z.get("engineerEdited")
        or z.get("createdBy") == "engineer"
        or str(z.get("source_id") or "").startswith("szone_")
    ):
        return False
    return _looks_like_eszone_n(z)


def _is_custom_engineer_anchor(z: dict[str, Any]) -> bool:
    """Engineer zone that is NOT merely an ``*_ESZoneN`` auto name — collapse target."""
    if not _is_engineer_zone(z) or _is_default_zone(z):
        return False
    if str(z.get("source_id") or "").startswith("szone_"):
        return True
    if z.get("zoneOrigin") == "ENGINEER" or z.get("engineerEdited") or z.get(
        "createdBy"
    ) == "engineer":
        # Custom name like PICK_ESZ — not Module_ESZone1
        if not _looks_like_eszone_n(z):
            return True
    return False


def _zone_rank(z: dict[str, Any]) -> tuple[int, int, int]:
    """Higher rank = preferred survivor when collapsing duplicates."""
    sid = str(z.get("source_id") or z.get("id") or "").strip()
    szone = 100 if sid.startswith("szone_") else 0
    eng = 50 if _is_engineer_zone(z) else 0
    mem = min(len(z.get("members") or []), 40)
    auto_pen = -30 if _is_auto_eszone_shell(z) else 0
    return (szone + eng + auto_pen, mem, len(str(z.get("engineering_name") or "")))


def _merge_zone_row(prev: dict[str, Any], z: dict[str, Any]) -> dict[str, Any]:
    """Fold duplicate zone state onto the preferred durable identity."""
    keep, drop = (prev, z) if _zone_rank(prev) >= _zone_rank(z) else (z, prev)
    out = dict(keep)
    # Members — union (ORI-076: no phantom loss across identity collapse)
    mems: list[str] = []
    seen_m: set[str] = set()
    for m in list(keep.get("members") or []) + list(drop.get("members") or []):
        ms = str(m or "").strip()
        if not ms or ms.upper() in seen_m:
            continue
        seen_m.add(ms.upper())
        mems.append(ms)
    out["members"] = mems
    out["membersOrigin"] = keep.get("membersOrigin") or drop.get("membersOrigin")
    # Conveyors — union
    convs: list[str] = []
    seen_c: set[str] = set()
    for c in list(keep.get("conveyors") or keep.get("conveyorRefs") or []) + list(
        drop.get("conveyors") or drop.get("conveyorRefs") or []
    ):
        cs = str(c or "").strip()
        if not cs or cs.upper() in seen_c:
            continue
        seen_c.add(cs.upper())
        convs.append(cs)
    if convs:
        out["conveyors"] = convs
        out["conveyorRefs"] = convs
    # Preserve engineer identity stamps (ORI-045)
    if (
        keep.get("zoneOrigin") == "ENGINEER"
        or drop.get("zoneOrigin") == "ENGINEER"
        or keep.get("engineerEdited")
        or drop.get("engineerEdited")
        or keep.get("createdBy") == "engineer"
        or drop.get("createdBy") == "engineer"
        or str(keep.get("source_id") or "").startswith("szone_")
        or str(drop.get("source_id") or "").startswith("szone_")
    ):
        out["zoneOrigin"] = "ENGINEER"
        out["engineerEdited"] = True
        out.setdefault("createdBy", "engineer")
        out.setdefault("provenance", "ENGINEER_CREATED")
    # Prefer szone_* source_id
    ks = str(keep.get("source_id") or keep.get("id") or "").strip()
    ds = str(drop.get("source_id") or drop.get("id") or "").strip()
    if ks.startswith("szone_"):
        out["source_id"] = ks
    elif ds.startswith("szone_"):
        out["source_id"] = ds
    else:
        out["source_id"] = ks or ds or durable_zone_identity(out)
    out["id"] = out.get("source_id") or out.get("id")
    # Prefer human engineering_name over raw szone_* / auto shell
    for cand in (
        keep.get("engineering_name"),
        drop.get("engineering_name"),
        keep.get("name"),
        drop.get("name"),
    ):
        cn = str(cand or "").strip()
        if cn and not cn.startswith("szone_") and not _AUTO_ESZONE_RE.match(cn):
            out["engineering_name"] = cn
            out["name"] = cn
            break
    else:
        out.setdefault(
            "engineering_name",
            str(keep.get("engineering_name") or keep.get("name") or out.get("source_id") or ""),
        )
        out.setdefault("name", out.get("engineering_name"))
    # Area — preserve cleared / unlinked
    if keep.get("areaUnlinked") or drop.get("areaUnlinked"):
        out["areaRef"] = ""
        out["area"] = ""
        out["areaUnlinked"] = True
    elif not str(out.get("areaRef") or out.get("area") or "").strip():
        area = str(
            keep.get("areaRef")
            or keep.get("area")
            or drop.get("areaRef")
            or drop.get("area")
            or ""
        ).strip()
        if area:
            out["areaRef"] = area
            out["area"] = area
    return out


def dedupe_engineer_zones(
    zones: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """ORI-076: one canonical row per durable engineer-zone identity.

    Collapses:
      - same source_id / szone_*
      - same display name (name-as-sid vs szone_*)
      - hollow auto ``*_ESZoneN`` shells onto an engineer zone for the same Area
    Default/Unassigned rows pass through unchanged (still separate).
    """
    if not zones:
        return []
    defaults: list[dict[str, Any]] = []
    by_sid: dict[str, dict[str, Any]] = {}
    by_disp: dict[str, str] = {}
    area_eng: dict[str, str] = {}  # area → preferred sid for engineer zone

    def _put(row: dict[str, Any]) -> None:
        sid = str(row.get("source_id") or row.get("id") or durable_zone_identity(row) or "").strip()
        if not sid:
            sid = durable_zone_identity(row) or f"zone_{len(by_sid)+1}"
            row = dict(row)
            row["source_id"] = sid
        by_sid[sid] = row
        disp = _zone_display_key(row)
        if disp:
            by_disp[disp] = sid
        area = _zone_area_key(row)
        # Only custom engineer anchors (PICK_ESZ / szone_*) absorb auto shells
        if area and _is_custom_engineer_anchor(row):
            prev = area_eng.get(area)
            if not prev or _zone_rank(row) >= _zone_rank(by_sid.get(prev) or {}):
                area_eng[area] = sid

    for raw in zones:
        if not isinstance(raw, dict):
            continue
        z = dict(raw)
        if _is_default_zone(z):
            defaults.append(z)
            continue
        sid = str(z.get("source_id") or z.get("sourceId") or z.get("id") or "").strip()
        disp = _zone_display_key(z)
        # Collapse onto existing display-name / sid
        existing_sid = None
        if sid and sid in by_sid:
            existing_sid = sid
        elif disp and disp in by_disp:
            other_sid = by_disp[disp]
            # Only fold when one side is szone_* (ORI-045 durable identity).
            # Never merge two distinct non-szone source_ids that merely share a
            # display name (Gate 8 — EngineerAlt_ESZone1 vs ORNCCP5_ESZone1).
            sid_szone = sid.startswith("szone_")
            other_szone = str(other_sid).startswith("szone_")
            if sid_szone or other_szone:
                existing_sid = other_sid
        elif _is_auto_eszone_shell(z):
            area = _zone_area_key(z)
            if area and area in area_eng:
                existing_sid = area_eng[area]
        if existing_sid and existing_sid in by_sid:
            merged = _merge_zone_row(by_sid[existing_sid], z)
            by_sid.pop(existing_sid, None)
            _put(merged)
            continue
        _put(z)

    # Second pass: hollow auto shells → custom engineer anchor on same Area only
    final_sids = list(by_sid.keys())
    for sid in final_sids:
        z = by_sid.get(sid)
        if not z or not _is_auto_eszone_shell(z):
            continue
        area = _zone_area_key(z)
        pref = area_eng.get(area) if area else None
        if pref and pref != sid and pref in by_sid and _is_custom_engineer_anchor(
            by_sid[pref]
        ):
            merged = _merge_zone_row(by_sid[pref], z)
            by_sid.pop(sid, None)
            by_sid[str(merged.get("source_id") or pref)] = merged
            disp = _zone_display_key(merged)
            if disp:
                by_disp[disp] = str(merged.get("source_id") or pref)

    out = defaults + list(by_sid.values())
    return out


def canonical_engineer_zones(
    zones: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """ORI-076/045: operational engineer zones only, deduped by durable identity."""
    deduped = dedupe_engineer_zones(zones)
    return [z for z in deduped if _is_engineer_zone(z) and not _is_default_zone(z)]


def engineer_assigned_member_count(
    zones: list[dict[str, Any]] | None,
) -> int:
    """Devices actually assigned to engineer zones (Default excluded)."""
    seen: set[str] = set()
    for z in canonical_engineer_zones(zones):
        for m in z.get("members") or []:
            nm = _norm(str(m or ""))
            if nm:
                seen.add(nm)
    return len(seen)

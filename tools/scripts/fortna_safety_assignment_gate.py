#!/usr/bin/env python3
"""ORI-061/065/067/068: engineer-assigned Safety intent integrity.

Never silently drop an assigned Safety device from Safe_Logic while declaring
the build CURRENT.

ORI-068: engineer intent is explicit operational-zone membership only —
Default / Unassigned inventory is NOT engineer build intent.
"""
from __future__ import annotations

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
    for key in ("name", "engineering_name", "id", "source_id"):
        n = _norm(str(z.get(key) or ""))
        if n in _DEFAULT_ZONE_NAMES:
            return True
        if "DEFAULT SAFETY" in n or n.startswith("UNASSIGNED"):
            return True
    return False


def _is_engineer_zone(z: dict[str, Any]) -> bool:
    """True when zone carries explicit engineer authorship / assignment."""
    if _is_default_zone(z):
        return False
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

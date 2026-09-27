#!/usr/bin/env python3
"""ORI-061: engineer-assigned Safety members must be valid or BUILD BLOCKS.

Never silently drop an assigned Safety device from Safe_Logic while declaring
the build CURRENT.
"""
from __future__ import annotations

from typing import Any


def _norm(name: str) -> str:
    return str(name or "").strip().upper()


def _strip_t(name: str) -> str:
    n = _norm(name)
    return n[2:] if n.startswith("T_") else n


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

    A member is invalid when the canonical device is present and:
      - assignable is False, OR
      - review_reason indicates DIRECTION_MISMATCH / ENDPOINT conflict / WORD_ONLY /
        UNKNOWN_OWNER / NO_MODULE_CHANNEL_PROOF, OR
      - hardwareBacked is False with an explicit non-assignable reason

    Missing devices (not in inventory) are reported as REVIEW but do not alone
    hard-block unless assignable=False is known — Warden's primary case is
    DIRECTION_MISMATCH with assignable=false still assigned.
    """
    from fortna_es_compiler import safety_operand_has_writer, studio_safety_tag

    idx = _device_index(safety_devices)
    violations: list[dict[str, Any]] = []
    for z in engineer_zones or []:
        if not isinstance(z, dict):
            continue
        zname = str(z.get("name") or z.get("engineering_name") or "").strip()
        members = list(z.get("members") or [])
        if not members:
            continue
        # Only engineer / applied membership
        origin = str(z.get("membersOrigin") or z.get("membership_origin") or "").upper()
        eng = bool(
            z.get("engineerEdited")
            or z.get("createdBy") == "engineer"
            or "ENGINEER" in origin
        )
        if not eng and origin and "ENGINEER" not in origin:
            continue
        for raw in members:
            mem = str(raw or "").strip()
            if not mem:
                continue
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
                    and not safety_operand_has_writer(
                        studio_safety_tag(mem) or mem,
                        written_tags=written_tags,
                        device_evidence={mem: d},
                    )
                ):
                    # Direction-mismatch devices already caught; writer miss for
                    # otherwise-ready assigned members also blocks.
                    if d.get("assignable") is not False and d.get("hardwareBacked") is True:
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
            f"{v['device']} — {v['reason']}" + (f" (zone {v['zone']})" if v.get("zone") else "")
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
    }

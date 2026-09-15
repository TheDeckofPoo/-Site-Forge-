#!/usr/bin/env python3
"""Reusable ES / Safety Program emitter (PLC4/PLC5 structural pattern).

Program ES
  Main_Routine: JSR(<Zone>_Safe_Logic) + JSR(<Zone>_Safe_PI) per Safety Zone
  Safe_Logic:   ES_SIL1_Cat1 per member
  Safe_PI:      ES_PI20 aggregator group(s) + Reset/Silence/Tripped maps

Conveyor→SafetyZone comes from Transportation (engineer-authoritative).
Safety-device membership must be proven RUN evidence or explicit engineer
members — never inferred from similar names / Area alone.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable


ES_PI20_CAPACITY = 20
NO_ESNULL = "NO_ESNull"


@dataclass
class AggregatorGroup:
    tag: str  # e.g. Zone_ES_PI or Zone_ES_PI2
    members: list[str]  # device tag names (padded later)


@dataclass
class SafetyZoneIR:
    name: str
    area: str
    members: list[str] = field(default_factory=list)
    conveyors: list[str] = field(default_factory=list)
    reset_source: str = ""
    silence_source: str = ""
    aggregator_groups: list[AggregatorGroup] = field(default_factory=list)
    device_membership_status: str = "UNRESOLVED"  # RESOLVED | UNRESOLVED | NONE

    def ensure_aggregators(self) -> None:
        if self.aggregator_groups:
            return
        mems = [m for m in self.members if m]
        if not mems:
            self.aggregator_groups = []
            return
        groups: list[AggregatorGroup] = []
        for i in range(0, len(mems), ES_PI20_CAPACITY):
            chunk = mems[i : i + ES_PI20_CAPACITY]
            suffix = "" if i == 0 else str(i // ES_PI20_CAPACITY + 1)
            tag = f"{self.name}_ES_PI{suffix}"
            groups.append(AggregatorGroup(tag=tag, members=chunk))
        self.aggregator_groups = groups


def _safe(name: str) -> str:
    s = re.sub(r"[^\w]", "_", str(name or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def _looks_like_safety_device(name: str) -> bool:
    n = (name or "").upper()
    return bool(
        re.match(r"^\d*ES\d", n)
        or re.match(r"^ES\d+", n)
        or re.match(r"^T_\d*ES\d", n)
        or n.startswith("ESR")
        or re.search(r"(^|_)ESR\d*", n)
        or re.search(r"(^|_)MCR\d*", n)
        or re.search(r"MCR\d*", n)
    )


def build_safety_zone_irs(
    *,
    safety_zones: list[str] | None = None,
    areas: list[str] | None = None,
    estop_model: dict[str, Any] | None = None,
    engineer_zones: list[dict[str, Any]] | None = None,
    default_area: str = "",
) -> list[SafetyZoneIR]:
    """Build SafetyZone IR from Transportation engineer assignment + proven estop.

    engineer_zones (from Transport Apply safetyBuild):
      {name, area, conveyors: [P###,...], members: [dev,...]}
    """
    zones: list[SafetyZoneIR] = []
    seen: set[str] = set()
    em = estop_model or {}
    proven_by_zone: dict[str, list[str]] = {}
    for z in em.get("zones") or []:
        name = _safe(z.get("name") or "")
        conf = str(z.get("membership_confidence") or "").upper()
        mem = list(z.get("membership") or [])
        if name and conf in {"CONFIRMED", "HIGH", "HIGH_CONFIDENCE"} and mem:
            proven_by_zone[name.upper()] = [_safe(m) for m in mem if _safe(m)]

    for z in engineer_zones or []:
        name = _safe(z.get("name") or z.get("safetyZone") or "")
        if not name or name in seen:
            continue
        area = _safe(z.get("area") or default_area or "")
        conveyors = [str(c).strip() for c in (z.get("conveyors") or []) if str(c).strip()]
        members = [
            _safe(m) if isinstance(m, str) else _safe((m or {}).get("name") or "")
            for m in (z.get("members") or [])
        ]
        members = [m for m in members if m and _looks_like_safety_device(m)]
        # Only fill from proven estop when zone NAMES match — no guessing
        if not members and name.upper() in proven_by_zone:
            members = list(proven_by_zone[name.upper()])
        status = "RESOLVED" if members else ("UNRESOLVED" if conveyors else "NONE")
        if not area and (areas or []):
            area = _safe(areas[0])
        if not area:
            area = "Main_Area"
        ir = SafetyZoneIR(
            name=name,
            area=area,
            members=members,
            conveyors=conveyors,
            reset_source=f"{area}.Reset",
            silence_source=f"{area}.Silence",
            device_membership_status=status,
        )
        ir.ensure_aggregators()
        zones.append(ir)
        seen.add(name)

    for z in em.get("zones") or []:
        name = _safe(z.get("name") or "")
        if not name or name in seen:
            continue
        conf = str(z.get("membership_confidence") or "").upper()
        mem = list(z.get("membership") or [])
        if conf not in {"CONFIRMED", "HIGH", "HIGH_CONFIDENCE"} or not mem:
            continue
        area = _safe(z.get("area") or default_area or (areas or [""])[0] or "Main_Area")
        members = [_safe(m) for m in mem if _safe(m)]
        ir = SafetyZoneIR(
            name=name,
            area=area,
            members=members,
            conveyors=[],
            reset_source=f"{area}.Reset",
            silence_source=f"{area}.Silence",
            device_membership_status="RESOLVED",
        )
        ir.ensure_aggregators()
        zones.append(ir)
        seen.add(name)

    return zones


def safety_readiness(zones: list[SafetyZoneIR], *, library_has_aois: bool = True) -> dict[str, Any]:
    if not zones:
        return {
            "status": "NOT_DETECTED",
            "detail": "No Safety Zones from Transportation or proven RUN membership",
            "unresolved": 0,
            "zones": [],
        }
    issues: list[str] = []
    zone_diag: list[dict[str, Any]] = []
    for z in zones:
        zd: dict[str, Any] = {
            "name": z.name,
            "area": z.area,
            "conveyors": list(z.conveyors),
            "conveyor_membership": "RESOLVED" if z.conveyors else "NONE",
            "safety_device_membership": z.device_membership_status,
            "members": list(z.members),
        }
        if not z.area:
            issues.append(f"{z.name}: missing Area")
            zd["gap"] = "missing Area"
        elif z.conveyors and not z.members:
            issues.append(
                f"{z.name}: conveyor membership RESOLVED ({len(z.conveyors)}) but "
                "safety-device membership UNRESOLVED — no proven E-stop/ESR/MCR "
                "links in RUN for this zone"
            )
            zd["gap"] = "safety-device membership UNRESOLVED"
        elif not z.members:
            issues.append(f"{z.name}: no safety-device members")
            zd["gap"] = "no members"
        zone_diag.append(zd)
    if not library_has_aois:
        issues.append("ES_SIL1_Cat1 / ES_PI20 AOIs missing from library")
    ready_zones = [z for z in zones if z.members and z.area]
    blocked = any(z.conveyors and not z.members for z in zones) or any(
        "AOIs missing" in i or "missing Area" in i for i in issues
    )
    if ready_zones and not blocked and not issues:
        return {
            "status": "READY",
            "detail": (
                f"{len(ready_zones)} Safety Zone(s) · "
                f"members={sum(len(z.members) for z in ready_zones)} · "
                f"conveyors={sum(len(z.conveyors) for z in ready_zones)}"
            ),
            "unresolved": 0,
            "zones": zone_diag,
        }
    if zones and issues:
        # Prefer actionable per-zone lines for UI / activity log
        actionable = []
        for zd in zone_diag:
            if zd.get("safety_device_membership") == "RESOLVED" and zd.get("area"):
                continue
            gap = zd.get("gap") or "needs review"
            actionable.append(
                f"Safety Zone: {zd.get('name') or '—'} | Area: {zd.get('area') or '—'} | "
                f"Conveyors: {len(zd.get('conveyors') or [])} | "
                f"Safety members: {zd.get('safety_device_membership') or 'UNRESOLVED'} | "
                f"Missing: {gap}"
            )
        return {
            "status": "REVIEW_REQUIRED",
            "detail": " | ".join(actionable[:4]) if actionable else "; ".join(issues[:6]),
            "unresolved": len(issues),
            "zones": zone_diag,
        }
    return {
        "status": "NOT_DETECTED",
        "detail": "No emitable Safety Zones",
        "unresolved": 0,
        "zones": zone_diag,
    }


def _pad_es_slots(members: list[str], n: int = ES_PI20_CAPACITY) -> list[str]:
    out = [m for m in members if m][:n]
    while len(out) < n:
        out.append(NO_ESNULL)
    return out


def emit_es_program(
    zones: list[SafetyZoneIR],
    *,
    _rung_xml: Callable[..., str],
    routine: Callable[[str, list[str]], str],
    extract_tag_block: Callable[[str, str], str | None],
    library_text: str,
    ensure_tag: Callable[[str], None] | None = None,
    add_tag_block: Callable[[str], None] | None = None,
) -> dict[str, Any] | None:
    """Emit Program ES XML + required tags. Returns None if nothing to emit."""
    ready = [z for z in zones if z.members and z.area and z.name]
    if not ready:
        return None

    if ensure_tag:
        ensure_tag(NO_ESNULL)

    tag_blocks: list[str] = []

    def _clone(lib_name: str, new_name: str, *extra_repl: tuple[str, str]) -> None:
        block = extract_tag_block(library_text, lib_name)
        if not block:
            return
        cloned = block
        repls = [(lib_name, new_name), *extra_repl]
        for old, new in sorted(repls, key=lambda x: -len(x[0])):
            cloned = cloned.replace(old, new)
        tag_blocks.append(cloned)
        if add_tag_block:
            add_tag_block(cloned)

    main_rungs: list[str] = []
    zone_routines: list[str] = []

    for z in ready:
        z.ensure_aggregators()
        _clone("Main_Area_Safe", z.name, ("Main_Area", z.area))
        for g in z.aggregator_groups:
            _clone("Main_Area_Safe_ES_PI", g.tag, ("Main_Area_Safe", z.name), ("Main_Area", z.area))
        for dev in z.members:
            _clone("NO_ES", dev)
            aoi = f"{dev}_AOI"
            src_aoi = "ES1000_AOI"
            if not extract_tag_block(library_text, src_aoi):
                src_aoi = "ES3000_AOI"
            _clone(src_aoi, aoi)

        logic_rungs: list[str] = [
            _rung_xml(0, "NOP();", f"{z.name} Safe_Logic — ES_SIL1_Cat1 per member"),
        ]
        for dev in z.members:
            logic_rungs.append(
                _rung_xml(
                    0,
                    f"ES_SIL1_Cat1({dev}_AOI,{dev},{z.area},{z.name}.PI.Reset,{z.name}.PI.Silence);",
                    f"{dev} → {z.name}",
                )
            )
        zone_routines.append(routine(f"{z.name}_Safe_Logic", logic_rungs))

        pi_rungs: list[str] = [
            _rung_xml(0, "NOP();", f"{z.name} Safe_PI — ES_PI20 aggregator(s)"),
        ]
        for g in z.aggregator_groups:
            slots = _pad_es_slots(g.members)
            args = ",".join([g.tag, z.name, *slots])
            pi_rungs.append(
                _rung_xml(0, f"ES_PI20({args});", f"aggregator {g.tag} ({len(g.members)} members)")
            )
        primary = z.aggregator_groups[0].tag if z.aggregator_groups else f"{z.name}_ES_PI"
        pi_rungs.extend(
            [
                _rung_xml(0, f"XIC({z.area}.Reset)OTE({z.name}.PI.Reset);", "Area.Reset → Zone.PI.Reset"),
                _rung_xml(0, f"XIC({z.area}.Silence)OTE({z.name}.PI.Silence);", "Area.Silence → Zone.PI.Silence"),
                _rung_xml(0, f"XIC({primary}.O_Tripped)OTE({z.name}.PI.Tripped);", "ES_PI.O_Tripped → Zone.PI.Tripped"),
                _rung_xml(
                    0,
                    f"XIC({primary}.O_Silenced_Tripped)OTE({z.name}.PI.Silenced_Tripped);",
                    "ES_PI.O_Silenced_Tripped → Zone.PI.Silenced_Tripped",
                ),
                _rung_xml(
                    0,
                    f"XIC({primary}.O_ESPX_Not_OK)OTE({z.name}.PI.ESPX_Not_OK);",
                    "ES_PI.O_ESPX_Not_OK → Zone.PI.ESPX_Not_OK",
                ),
            ]
        )
        zone_routines.append(routine(f"{z.name}_Safe_PI", pi_rungs))

        main_rungs.append(_rung_xml(0, f"JSR({z.name}_Safe_Logic,0);", f"{z.name} Safe_Logic"))
        main_rungs.append(_rung_xml(0, f"JSR({z.name}_Safe_PI,0);", f"{z.name} Safe_PI"))

    program_xml = (
        '<Program Name="ES" TestEdits="false" MainRoutineName="Main_Routine" '
        'Disabled="false" UseAsFolder="false">'
        "<Tags/><Routines>"
        f'{routine("Main_Routine", main_rungs)}'
        f'{"".join(zone_routines)}'
        "</Routines></Program>"
    )
    return {
        "program_xml": program_xml,
        "tag_blocks": tag_blocks,
        "zones": [
            {
                "name": z.name,
                "area": z.area,
                "members": z.members,
                "conveyors": z.conveyors,
                "aggregators": [g.tag for g in z.aggregator_groups],
            }
            for z in ready
        ],
        "es_sil1_count": sum(len(z.members) for z in ready),
        "es_pi20_count": sum(len(z.aggregator_groups) for z in ready),
    }

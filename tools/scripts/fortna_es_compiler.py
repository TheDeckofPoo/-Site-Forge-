#!/usr/bin/env python3
"""Reusable ES / Safety Program emitter (PLC4/PLC5 structural pattern).

Program ES
  Main_Routine: JSR(<Zone>_Safe_Logic) + JSR(<Zone>_Safe_PI) per Safety Zone
  Safe_Logic:   ES_SIL1_Cat1 per member
  Safe_PI:      ES_PI20 aggregator group(s) + Reset/Silence/Tripped maps

Membership must be proven RUN evidence or engineer assignment — never Area-name inference alone.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable


ES_PI20_CAPACITY = 20
NO_ESLS = "NO_ESLS"


@dataclass
class AggregatorGroup:
    tag: str  # e.g. Zone_ES_PI or Zone_ES_PI2
    members: list[str]  # device tag names (padded later)


@dataclass
class SafetyZoneIR:
    name: str
    area: str
    members: list[str] = field(default_factory=list)
    reset_source: str = ""
    silence_source: str = ""
    aggregator_groups: list[AggregatorGroup] = field(default_factory=list)

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
    """Build SafetyZone IR from engineer assignment and/or proven estop membership.

    engineer_zones entries: {name, area, members: [dev,...]}
    """
    zones: list[SafetyZoneIR] = []
    seen: set[str] = set()

    # 1) Engineer-authoritative zones (Transport / workbook / UI)
    for z in engineer_zones or []:
        name = _safe(z.get("name") or z.get("safetyZone") or "")
        if not name or name in seen:
            continue
        area = _safe(z.get("area") or default_area or (areas or [""])[0] or "Main_Area")
        members = [
            _safe(m) if isinstance(m, str) else _safe((m or {}).get("name") or "")
            for m in (z.get("members") or [])
        ]
        members = [m for m in members if m and _looks_like_safety_device(m)]
        ir = SafetyZoneIR(
            name=name,
            area=area,
            members=members,
            reset_source=f"{area}.Reset",
            silence_source=f"{area}.Silence",
        )
        ir.ensure_aggregators()
        zones.append(ir)
        seen.add(name)

    # 2) Proven estop model zones with CONFIRMED/HIGH membership
    em = estop_model or {}
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
            reset_source=f"{area}.Reset",
            silence_source=f"{area}.Silence",
        )
        ir.ensure_aggregators()
        zones.append(ir)
        seen.add(name)

    # Do NOT invent zones from Area names alone.
    return zones


def safety_readiness(zones: list[SafetyZoneIR], *, library_has_aois: bool = True) -> dict[str, Any]:
    if not zones:
        return {
            "status": "NOT_DETECTED",
            "detail": "No Safety Zones with proven/engineer membership",
            "unresolved": 0,
        }
    issues: list[str] = []
    for z in zones:
        if not z.area:
            issues.append(f"{z.name}: missing Area")
        if not z.name:
            issues.append("(unnamed zone)")
        if not z.members:
            issues.append(f"{z.name}: empty member list")
        if not z.aggregator_groups:
            issues.append(f"{z.name}: no aggregator groups")
    if not library_has_aois:
        issues.append("ES_SIL1_Cat1 / ES_PI20 AOIs missing from library")
    if issues:
        return {
            "status": "REVIEW_REQUIRED" if any("empty" in i or "missing Area" in i for i in issues) else "ERROR",
            "detail": "; ".join(issues[:8]),
            "unresolved": len(issues),
        }
    return {
        "status": "READY",
        "detail": f"{len(zones)} Safety Zone(s) · members={sum(len(z.members) for z in zones)}",
        "unresolved": 0,
    }


def _pad_es_slots(members: list[str], n: int = ES_PI20_CAPACITY) -> list[str]:
    out = [m for m in members if m][:n]
    while len(out) < n:
        out.append(NO_ESLS)
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
        ensure_tag(NO_ESLS)

    tag_blocks: list[str] = []

    def _clone(lib_name: str, new_name: str, *extra_repl: tuple[str, str]) -> None:
        block = extract_tag_block(library_text, lib_name)
        if not block:
            return
        cloned = block
        # Longer keys first
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
        # Zone UDT + Area (Area may already exist)
        _clone("Main_Area_Safe", z.name, ("Main_Area", z.area))
        for g in z.aggregator_groups:
            _clone("Main_Area_Safe_ES_PI", g.tag, ("Main_Area_Safe", z.name), ("Main_Area", z.area))
        for dev in z.members:
            # Device ES_UDT + SIL1 AOI instance
            _clone("NO_ES", dev)
            aoi = f"{dev}_AOI"
            # Prefer ES1000_AOI template if present
            src_aoi = "ES1000_AOI"
            if not extract_tag_block(library_text, src_aoi):
                src_aoi = "ES3000_AOI"
            _clone(src_aoi, aoi)

        # Safe_Logic
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

        # Safe_PI
        pi_rungs: list[str] = [
            _rung_xml(0, "NOP();", f"{z.name} Safe_PI — ES_PI20 aggregator(s)"),
        ]
        for g in z.aggregator_groups:
            slots = _pad_es_slots(g.members)
            # Library / gold order often Input20..Input1; pass members then pad
            args = ",".join([g.tag, z.name, *slots])
            pi_rungs.append(
                _rung_xml(0, f"ES_PI20({args});", f"aggregator {g.tag} ({len(g.members)} members)")
            )
        # Standard zone mappings (first aggregator is primary PI feedback)
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
                "aggregators": [g.tag for g in z.aggregator_groups],
            }
            for z in ready
        ],
    }

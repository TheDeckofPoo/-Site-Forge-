#!/usr/bin/env python3
"""Reusable ES / Safety Program emitter (PLC4/PLC5 structural pattern).

Structural reference (do not copy site membership):
  docs/es-reference/ES_Program_PLC5_structural.L5X

Program ES
  Main_Routine: JSR(<Zone>_Safe_Logic) + JSR(<Zone>_Safe_PI) per Safety Zone
  Safe_Logic:   ES_SIL1_Cat1 per member
  Safe_PI:      ES_PI20 aggregator group(s) + Reset/Silence/Tripped maps

Conveyor→SafetyZone comes from Transportation (engineer-authoritative).
Safety-device membership must be proven RUN evidence or explicit engineer
members on safety_build.zones[].members — never inferred from similar names
or copied from PLC4/PLC5 site lists.
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
    area_conveyors: dict[str, list[str]] | None = None,
) -> list[SafetyZoneIR]:
    """Build SafetyZone IR from Transportation engineer assignment + proven estop.

    engineer_zones (from Transport Apply safetyBuild):
      {name, area, conveyors: [P###,...], members: [dev,...]}

    area_conveyors: optional Area → [P-tag,…] from Autogen conveyors so a named
    Safety Zone stub can show conveyor membership READY while devices remain
    UNRESOLVED (never invents E-stop membership).
    """
    zones: list[SafetyZoneIR] = []
    seen: set[str] = set()
    em = estop_model or {}
    area_conveyors = {str(k): list(v or []) for k, v in (area_conveyors or {}).items()}
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
        # Fill conveyors from Area map when engineer zone omitted them
        if not ir.conveyors and ir.area and ir.area in area_conveyors:
            ir.conveyors = list(area_conveyors[ir.area])
            if not ir.members:
                ir.device_membership_status = "UNRESOLVED"
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
            conveyors=list(area_conveyors.get(area) or []),
            reset_source=f"{area}.Reset",
            silence_source=f"{area}.Silence",
            device_membership_status="RESOLVED",
        )
        ir.ensure_aggregators()
        zones.append(ir)
        seen.add(name)

    # Named Safety Zones from workbook (Area ≠ Safety Zone). Create REVIEW stubs
    # so Program ES omission is never silent when an Area/zone is known.
    for raw in safety_zones or []:
        name = _safe(raw)
        if not name or name in seen:
            continue
        # Heuristic link: Test1_ESZone1 → area test1 / Test1; never invents devices
        area = ""
        for a in areas or []:
            au = _safe(a).upper()
            nu = name.upper()
            if au and (nu.startswith(au) or au in nu):
                area = _safe(a)
                break
        if not area:
            area = _safe(default_area or (areas or ["Main_Area"])[0] if (areas or []) else "Main_Area")
        convs = list(area_conveyors.get(area) or [])
        # Also try Area without _Area suffix
        if not convs and area.endswith("_Area"):
            convs = list(area_conveyors.get(area[: -len("_Area")]) or [])
        members = list(proven_by_zone.get(name.upper()) or [])
        ir = SafetyZoneIR(
            name=name,
            area=area,
            members=members,
            conveyors=convs,
            reset_source=f"{area}.Reset",
            silence_source=f"{area}.Silence",
            device_membership_status="RESOLVED" if members else ("UNRESOLVED" if convs else "NONE"),
        )
        ir.ensure_aggregators()
        zones.append(ir)
        seen.add(name)

    return zones


def safety_readiness(zones: list[SafetyZoneIR], *, library_has_aois: bool = True) -> dict[str, Any]:
    """Field-by-field READY / UNRESOLVED gate — never a vague 'members unresolved'.

    Only two normal outcomes when Safety is detected:
      READY            → emit complete Program ES
      REVIEW_REQUIRED  → tell engineer exactly which fields are missing
    Silent omit is forbidden unless the engineer sets omit_unresolved_safety.
    """
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
        members = list(z.members or [])
        estops = [m for m in members if re.match(r"(?i)^(T_)?\d*ES\d", m) and "ESR" not in m.upper()]
        esrs = [m for m in members if "ESR" in m.upper()]
        mcrs = [m for m in members if "MCR" in m.upper()]
        reset_src = (z.reset_source or "").strip()
        silence_src = (z.silence_source or "").strip()
        fields = {
            "Area": "READY" if z.area else "UNRESOLVED",
            "Conveyors": "READY" if z.conveyors else "NONE",
            "E-Stops": "READY" if estops else ("UNRESOLVED" if z.conveyors else "NONE"),
            "ESR": "READY" if esrs else ("UNRESOLVED" if z.conveyors else "NONE"),
            "MCR": "READY" if mcrs else ("UNRESOLVED" if z.conveyors else "NONE"),
            "SafetyDevices": "READY" if members else ("UNRESOLVED" if z.conveyors else "NONE"),
            "Reset": "READY" if reset_src else "UNRESOLVED",
            "Silence": "READY" if silence_src else "UNRESOLVED",
            "AOI_ES_SIL1_Cat1": "READY" if library_has_aois else "UNRESOLVED",
            "AOI_ES_PI20": "READY" if library_has_aois else "UNRESOLVED",
        }
        missing = [k for k, v in fields.items() if v == "UNRESOLVED"]
        # Soft: ESR/MCR may be absent on small zones — only require SafetyDevices + Area + Reset/Silence + AOIs
        hard_missing = [
            k for k in missing
            if k in {"Area", "SafetyDevices", "Reset", "Silence", "AOI_ES_SIL1_Cat1", "AOI_ES_PI20"}
        ]
        zd: dict[str, Any] = {
            "name": z.name,
            "area": z.area,
            "conveyors": list(z.conveyors),
            "conveyor_membership": fields["Conveyors"],
            "safety_device_membership": fields["SafetyDevices"],
            "members": members,
            "estops": estops,
            "esrs": esrs,
            "mcrs": mcrs,
            "reset_source": reset_src or None,
            "silence_source": silence_src or None,
            "fields": fields,
            "missing": missing,
            "hard_missing": hard_missing,
            "zone_status": "READY" if not hard_missing and z.area and members else "UNRESOLVED",
        }
        if hard_missing:
            gap = ", ".join(hard_missing)
            issues.append(
                f"{z.name}: SAFETY REVIEW REQUIRED — missing {gap} "
                f"(Area={z.area or '—'}; Conveyors={len(z.conveyors)}; "
                f"E-Stops={estops or '—'}; Reset={reset_src or '—'}; Silence={silence_src or '—'})"
            )
            zd["gap"] = gap
        zone_diag.append(zd)
    if not library_has_aois:
        issues.append("ES_SIL1_Cat1 / ES_PI20 AOIs missing from library")
    ready_zones = [z for z in zones if z.members and z.area and (z.reset_source or "").strip() and (z.silence_source or "").strip()]
    blocked = any(zd.get("zone_status") == "UNRESOLVED" for zd in zone_diag) or not library_has_aois
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
        actionable = []
        for zd in zone_diag:
            if zd.get("zone_status") == "READY":
                continue
            actionable.append(
                f"Safety Zone: {zd.get('name') or '—'} | Area: {zd.get('area') or '—'} | "
                f"Conveyors: {len(zd.get('conveyors') or [])} | "
                f"E-Stops: {', '.join(zd.get('estops') or []) or 'UNRESOLVED'} | "
                f"Reset: {zd.get('reset_source') or 'UNRESOLVED'} | "
                f"Silence: {zd.get('silence_source') or 'UNRESOLVED'} | "
                f"Missing: {zd.get('gap') or 'needs review'}"
            )
        return {
            "status": "REVIEW_REQUIRED",
            "detail": " | ".join(actionable[:6]) if actionable else "; ".join(issues[:6]),
            "unresolved": len(issues),
            "zones": zone_diag,
            "silent_omit_forbidden": True,
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

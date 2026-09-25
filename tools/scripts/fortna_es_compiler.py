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
# PLC4/PLC5 cookie-cutter pad tag (gold structural template uses NO_ESLS).
NO_ESNULL = "NO_ESLS"


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
    # Bare MCR command coils stripped by normalize_safety_membership (not zone-eligible)
    skipped_mcr_coils: list[str] = field(default_factory=list)

    def normalize_safety_membership(self) -> None:
        """Single canonical stage: members and aggregators can never disagree.

        PD-0034 / PD-0002: bare MCR energize coils (1MCR1 / T_1MCR1 / CP1_MCR1)
        are COMMAND signals — never ES_PI20 / ES_SIL1 operands. MCR*_AUX feedback
        remains Safety-member eligible.

        Idempotent: re-running after an earlier normalize preserves skipped_mcr_coils
        provenance so emit can still surface REVIEW NOPs for stripped COMMAND coils.
        """
        prior_skipped = [
            studio_safety_tag(m)
            for m in (self.skipped_mcr_coils or [])
            if m and is_mcr_energize_coil(studio_safety_tag(m))
        ]
        raw = [studio_safety_tag(m) for m in (self.members or []) if m]
        # de-dupe alias forms after canonicalization
        seen: set[str] = set()
        canon: list[str] = []
        skipped: list[str] = []
        for m in raw:
            if not m:
                continue
            if is_mcr_energize_coil(m):
                if m not in skipped:
                    skipped.append(m)
                continue
            if m in seen:
                continue
            seen.add(m)
            canon.append(m)
        # Preserve prior skips that are not now legitimate members (idempotent re-entry)
        for p in prior_skipped:
            if p and p not in skipped and p not in seen:
                skipped.append(p)
        self.skipped_mcr_coils = skipped
        self.members = canon
        # Always rebuild aggregators from normalized members
        self.aggregator_groups = []
        self.ensure_aggregators(force=True)

    def ensure_aggregators(self, *, force: bool = False) -> None:
        """Build ES_PI20 groups from *current* members.

        force=True rebuilds even when aggregator_groups already exists — required
        after membership normalization so stale MCR coils cannot linger in PI packs.
        """
        if self.aggregator_groups and not force:
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
            groups.append(AggregatorGroup(tag=tag, members=list(chunk)))
        self.aggregator_groups = groups

    def assert_aggregator_subset_of_members(self) -> None:
        """Hard invariant: every ES_PI20 aggregator member ⊆ normalized members."""
        allowed = set(self.members or [])
        for g in self.aggregator_groups or []:
            for m in g.members or []:
                if m and m not in allowed:
                    raise AssertionError(
                        f"PD-0034: aggregator {g.tag} contains {m!r} which is not in "
                        f"normalized Safety members {sorted(allowed)} "
                        f"(bare MCR coils must never leak into ES_PI20)"
                    )


def _safe(name: str) -> str:
    s = re.sub(r"[^\w]", "_", str(name or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def studio_safety_tag(name: str) -> str:
    """Map Fortna / engineer Safety identity → Rockwell-legal controller tag.

    Studio rejects tags that start with a digit (e.g. Fortna ``4ES``).
    Canonical Logix form for digit-leading ESTOP/MCR/ESR/ESLS:
      4ES / 4ES1 / 2ES     → T_4ES / T_4ES1 / T_2ES
      2MCR1 / 2ESR1_AUX    → T_2MCR1 / T_2ESR1_AUX
      CP2_ES / ES422 / T_* → unchanged when already legal
    NAME and T_NAME alias pairs therefore emit one controller tag.
    """
    try:
        from fortna_tag_registry import canonical_safety_logix_tag

        return canonical_safety_logix_tag(name)
    except Exception:
        raw = str(name or "").strip()
        n = _safe(raw)
        if not n:
            return ""
        if re.match(r"^[A-Za-z_]", n):
            return n
        if re.match(r"^\d", n):
            return f"T_{n}"
        return n


def is_mcr_energize_coil(name: str) -> bool:
    """PD-0002: bare MCR coil (2MCR1 / T_2MCR1 / CP2_MCR1) — NOT an ES_UDT input.

    MCR*_AUX feedback is the separate ES_OK signal. Coils must never be cloned
    from NO_ES or passed to ES_SIL1_Cat1 as structure operands.
    """
    n = re.sub(r"^T_", "", (name or "").strip(), flags=re.I)
    if not n:
        return False
    if re.search(r"_AUX$", n, re.I):
        return False
    return bool(
        re.match(r"^\d*MCR\d*$", n, re.I)
        or re.match(r"^CP\d+_MCR\d*$", n, re.I)
        or re.match(r"^MCR\d*$", n, re.I)
    )


def _looks_like_safety_device(name: str) -> bool:
    """Heuristic for RUN-proven / auto-discovered Safety device tags.

    Must accept Fortna panel forms Curtis assigns in Safety Build:
      2ES / 4ES / 5ES / 6ES
      CP2_ES / CP3_ES
      CP2_ESR1 / CP2_MCR1_AUX / ES422 / ESLS*
    PD-0002: bare MCR coils are NOT Safety ES_UDT devices (AUX feedback is).
    """
    n = (name or "").upper().strip()
    if not n:
        return False
    if is_mcr_energize_coil(n):
        return False
    return bool(
        # Panel E-Stop: 2ES, 4ES, 4ES1, 12ES2
        re.match(r"^\d+ES\d*$", n)
        # Bare / numbered ES: ES422, ES1002
        or re.match(r"^ES\d+", n)
        or re.match(r"^ESLS", n)
        # Controller-prefixed: CP2_ES, CP3_ES, CP2_ESR1, CP2_MCR1_AUX
        or re.match(r"^CP\d+_ES\d*$", n)
        or re.match(r"^CP\d+_ESR\d*", n)
        or re.match(r"^CP\d+_MCR\d*_AUX$", n)
        # Terminal / remote: T_2MCR1_AUX, T_3ES1
        or re.match(r"^T_\d*ES\d*", n)
        or re.match(r"^T_\d*MCR\d*_AUX$", n)
        or re.match(r"^T_\d*ESR\d*", n)
        or n.startswith("ESR")
        or re.search(r"(^|_)ESR\d*", n)
        or re.search(r"(^|_)MCR\d*_AUX$", n)
        # Legacy pattern kept for older tags like 2ES1 (digit after ES required)
        or re.match(r"^\d*ES\d", n)
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
        raw_members = []
        for m in (z.get("members") or []):
            src = m if isinstance(m, str) else ((m or {}).get("name") or "")
            # Keep Fortna identity for membership proof; map to Studio tag for emit
            tag = studio_safety_tag(src)
            if tag:
                raw_members.append(tag)
        # de-dupe preserving order
        seen_m: set[str] = set()
        raw_members = [m for m in raw_members if not (m in seen_m or seen_m.add(m))]
        # ENGINEER ASSIGNMENTS ARE AUTHORITATIVE (Gate C).
        # Do not drop explicit Safety Build members via heuristic filter —
        # that caused HAHAHA_ESZone1 (4ES/5ES/CP2_ES…) to arrive as members=[]
        # and emit a false NOP shell while the UI showed READY.
        eng_origin = str(
            z.get("membersOrigin") or z.get("members_origin") or ""
        ).upper()
        # GATE 5 — PROVEN_RUN / ENGINEER_ASSIGNED / explicit Safety Build members
        # are authoritative. Never heuristic-drop assigned devices (Gate C).
        membership_proven = eng_origin in {
            "ENGINEER_ASSIGNED",
            "ENGINEER",
            "ASSIGNED",
            "PROVEN_RUN",
            "AUTO_RUN_PROVEN",
            "RUN_PROVEN",
            "PROVEN",
        } or bool(z.get("engineerEdited")) or bool(raw_members)
        if membership_proven and raw_members:
            members = list(raw_members)
        else:
            members = [m for m in raw_members if _looks_like_safety_device(m)]
        # Only fill from proven estop when zone NAMES match — no guessing
        if not members and name.upper() in proven_by_zone:
            members = [studio_safety_tag(m) for m in proven_by_zone[name.upper()]]
            members = [m for m in members if m]
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
        # PD-0034: normalize BEFORE aggregators so bare MCR coils never enter ES_PI20
        ir.normalize_safety_membership()
        if ir.skipped_mcr_coils and not ir.members and ir.device_membership_status == "RESOLVED":
            ir.device_membership_status = "UNRESOLVED"
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
        members = [studio_safety_tag(m) for m in mem if studio_safety_tag(m)]
        # de-dupe alias forms (2ES / T_2ES → T_2ES once)
        _seen_m: set[str] = set()
        members = [m for m in members if not (m in _seen_m or _seen_m.add(m))]
        ir = SafetyZoneIR(
            name=name,
            area=area,
            members=members,
            conveyors=list(area_conveyors.get(area) or []),
            reset_source=f"{area}.Reset",
            silence_source=f"{area}.Silence",
            device_membership_status="RESOLVED",
        )
        ir.normalize_safety_membership()
        if ir.skipped_mcr_coils and not ir.members:
            ir.device_membership_status = "UNRESOLVED"
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
        ir.normalize_safety_membership()
        if ir.skipped_mcr_coils and not ir.members and ir.device_membership_status == "RESOLVED":
            ir.device_membership_status = "UNRESOLVED"
        zones.append(ir)
        seen.add(name)

    return zones


def safety_readiness(zones: list[SafetyZoneIR], *, library_has_aois: bool = True) -> dict[str, Any]:
    """Field-by-field READY / UNRESOLVED gate — never a vague 'members unresolved'.

    Outcomes when Safety is detected:
      READY            → ALL expected zones (conveyors and/or devices) are READY; emit complete Program ES
      REVIEW_REQUIRED  → some/all expected zones incomplete; READY zones remain partially emitable
    Silent omit is forbidden unless the engineer sets omit_unresolved_safety.
    Partial emit is allowed: READY zones are emitable while incomplete zones stay omitted.
    """
    if not zones:
        return {
            "status": "NOT_DETECTED",
            "detail": "No Safety Zones from Transportation or proven RUN membership",
            "unresolved": 0,
            "zones": [],
            "ready_zones": [],
            "review_zones": [],
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

    # Expected = zones with conveyors and/or device membership expectations
    expected = [
        zd for zd in zone_diag
        if (zd.get("conveyors") or zd.get("members"))
    ]
    ready_zone_names = [
        str(zd.get("name") or "")
        for zd in expected
        if zd.get("zone_status") == "READY" and zd.get("name")
    ]
    review_zone_names = [
        str(zd.get("name") or "")
        for zd in expected
        if zd.get("zone_status") != "READY" and zd.get("name")
    ]
    # Also include non-expected unresolved zones that raised hard gaps (area-only stubs)
    for zd in zone_diag:
        n = str(zd.get("name") or "")
        if n and zd.get("zone_status") != "READY" and n not in review_zone_names and zd.get("hard_missing"):
            review_zone_names.append(n)

    all_expected_ready = bool(expected) and not review_zone_names and library_has_aois
    if all_expected_ready and not issues:
        return {
            "status": "READY",
            "detail": (
                f"{len(ready_zone_names)} Safety Zone(s) · "
                f"members={sum(len(zd.get('members') or []) for zd in expected)} · "
                f"conveyors={sum(len(zd.get('conveyors') or []) for zd in expected)}"
            ),
            "unresolved": 0,
            "zones": zone_diag,
            "ready_zones": ready_zone_names,
            "review_zones": [],
            "partial_emit_allowed": True,
        }

    if zones and (issues or review_zone_names or ready_zone_names):
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
        detail_parts = []
        if ready_zone_names and review_zone_names:
            detail_parts.append(
                f"partial: {len(ready_zone_names)} READY / {len(review_zone_names)} REVIEW"
            )
        detail_parts.append(
            " | ".join(actionable[:6]) if actionable else "; ".join(issues[:6])
        )
        return {
            "status": "REVIEW_REQUIRED",
            "detail": " · ".join(p for p in detail_parts if p),
            "unresolved": len(review_zone_names) or len(issues),
            "zones": zone_diag,
            "ready_zones": ready_zone_names,
            "review_zones": review_zone_names,
            "partial_emit_allowed": bool(ready_zone_names),
            "silent_omit_forbidden": True,
        }
    return {
        "status": "NOT_DETECTED",
        "detail": "No emitable Safety Zones",
        "unresolved": 0,
        "zones": zone_diag,
        "ready_zones": [],
        "review_zones": [],
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
    """Emit Program ES XML + required tags. Returns None if nothing to emit.

    Filters to zones with members (partial emit). Zones that have conveyors but
    no members are listed in omitted_zones and are not emitted.
    """
    # PD-0034: single canonical membership-normalization stage BEFORE ready filter /
    # aggregator use. Bare MCR coils never become ES_PI20 operands; aggregators always
    # rebuild from the normalized member set (members and aggregator_groups cannot disagree).
    for z in zones or []:
        z.normalize_safety_membership()
        z.assert_aggregator_subset_of_members()

    ready = [z for z in zones if z.members and z.area and z.name]
    omitted = [z for z in zones if z.conveyors and not z.members and z.name]
    # Cookie-cutter shell when zones/devices exist but membership is unresolved.
    # Fail-safe (PL-6):
    #   - status is always REVIEW_REQUIRED (never READY merely because Program ES exists)
    #   - Main_Routine is NOP only — does NOT OTE any .OK / permissive / reset path
    #   - no Safe_Logic / Safe_PI / ES_SIL1_Cat1 / ES_PI20 calls → UNKNOWN ≠ TRUE
    #   - NO_ESNULL kept available as the non-permissive pad identity
    # Unrelated PLC subsystems may still generate; Safety commissioning remains blocked.
    if not ready:
        if ensure_tag:
            ensure_tag(NO_ESNULL)
        shell_rungs = [
            _rung_xml(
                0,
                "NOP();",
                "SAFETY REVIEW REQUIRED — Program ES shell (FAIL-SAFE). "
                "Assign E-Stop/ESR/MCR membership in Safety Build before zone Safe_Logic/Safe_PI emit. "
                "UNKNOWN membership is never treated as permissive. "
                "COMMISSIONING READY = NO until membership resolved.",
            ),
        ]
        if omitted:
            shell_rungs.append(
                _rung_xml(
                    0,
                    "NOP();",
                    "Unresolved zones (no members): " + ", ".join(z.name for z in omitted[:12]),
                )
            )
        program_xml = (
            '<Program Name="ES" TestEdits="false" MainRoutineName="Main_Routine" '
            'Disabled="false" UseAsFolder="false">'
            "<Tags/><Routines>"
            f'{routine("Main_Routine", shell_rungs)}'
            "</Routines></Program>"
        )
        return {
            "program_xml": program_xml,
            "tag_blocks": [],
            "zones": [],
            "emitted_zones": [],
            "omitted_zones": [z.name for z in omitted],
            "shell": True,
            "status": "REVIEW_REQUIRED",
        }

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
        # Aggregators already rebuilt by normalize_safety_membership above.
        z.assert_aggregator_subset_of_members()
        _clone("Main_Area_Safe", z.name, ("Main_Area", z.area))
        for g in z.aggregator_groups:
            _clone("Main_Area_Safe_ES_PI", g.tag, ("Main_Area_Safe", z.name), ("Main_Area", z.area))
        es_members = list(z.members)
        skipped_mcr = list(z.skipped_mcr_coils or [])
        for dev in es_members:
            _clone("NO_ES", dev)
            aoi = f"{dev}_AOI"
            src_aoi = "ES1000_AOI"
            if not extract_tag_block(library_text, src_aoi):
                src_aoi = "ES3000_AOI"
            _clone(src_aoi, aoi)

        # Cookie-cutter Safe_Logic: ES_SIL1_Cat1 per member (no decorative NOP).
        logic_rungs: list[str] = []
        for dev in skipped_mcr:
            logic_rungs.append(
                _rung_xml(
                    0,
                    "NOP();",
                    f"REVIEW_REQUIRED (PD-0002): {dev} is MCR energize coil — not ES_UDT; "
                    f"use {dev}_AUX feedback for zone membership",
                )
            )
        for dev in es_members:
            logic_rungs.append(
                _rung_xml(
                    0,
                    f"ES_SIL1_Cat1({dev}_AOI,{dev},{z.area},{z.name}.PI.Reset,{z.name}.PI.Silence);",
                    f"{dev} → {z.name}",
                )
            )
        if not logic_rungs:
            logic_rungs.append(
                _rung_xml(0, "NOP();", f"{z.name} Safe_Logic — no members")
            )
        zone_routines.append(routine(f"{z.name}_Safe_Logic", logic_rungs))

        # Cookie-cutter Safe_PI: ES_PI20 aggregator(s) + Area/Zone PI maps (no decorative NOP).
        pi_rungs: list[str] = []
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
    # PD-0003: every operational zone that emits Safe_Logic also emits Safe_PI —
    # one valid PI/zone writer per operational Safety Zone with membership.
    zones_with_pi_writers = [z.name for z in ready]
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
                "has_pi_writer": True,
            }
            for z in ready
        ],
        "emitted_zones": [z.name for z in ready],
        "zones_with_pi_writers": zones_with_pi_writers,
        "omitted_zones": [z.name for z in omitted],
        "es_sil1_count": sum(len(z.members) for z in ready),
        "es_pi20_count": sum(len(z.aggregator_groups) for z in ready),
        # Invariant: no operational zone without a PI writer
        "pi_writer_invariant_ok": all(
            z.name in zones_with_pi_writers for z in ready
        ),
    }

#!/usr/bin/env python3
"""Bridge SiteModel evidence into AutogenInput without inventing site facts.

Primary path: fortna_autogen.load_from_run(run_dir) which already scopes
conveyors/PEs/IO to the controller. SiteModel optionally enriches:
  - PE roles from knowledge enrichment (pe_roles / role)
  - engineer area_id overrides when present
  - encoder list cross-check

SOURCE FIREWALL: RUN + SiteModel (from RUN) + overrides only.
Never imports finished PLC / answer-sheet modules.
"""
from __future__ import annotations

import re
from typing import Any

from fortna_autogen import AutogenInput, load_from_run
from fortna_site_model import INCLUDED, _clean, normalize_name


def bridge_site_model_to_autogen(
    run_dir: str | Any,
    site: dict[str, Any] | None = None,
    *,
    processor: str = "1756-L83E",
) -> tuple[AutogenInput, dict[str, Any]]:
    """Build AutogenInput from RUN; optionally enrich from SiteModel."""
    inp = load_from_run(run_dir, processor=processor)
    report: dict[str, Any] = {
        "source": "load_from_run",
        "conveyors_from_run": len(inp.conveyors),
        "pe_devices_from_run": len(inp.pe_devices),
        "io_points_from_run": len(inp.io_points),
        "modules_from_run": len(inp.modules),
        "enrichments": [],
    }
    if not site:
        return inp, report

    # --- PE role enrichment from SiteModel ---
    pe_by_name: dict[str, dict] = {}
    for pe in site.get("photoeyes") or []:
        nn = normalize_name(pe.get("normalized_name") or pe.get("raw_name") or "")
        if nn:
            pe_by_name[nn] = pe

    role_map = {"jam": "jam", "full": "full", "product": "product", "other": "other"}
    enriched = 0
    for pe in inp.pe_devices:
        nn = normalize_name(pe.get("fortna_name") or pe.get("name") or "")
        sm = pe_by_name.get(nn)
        if not sm:
            continue
        # Prefer engineer override, else SiteModel pe_roles → legacy role
        ov = sm.get("engineer_override") or {}
        if ov.get("pe_roles"):
            roles = ov["pe_roles"]
        else:
            roles = sm.get("pe_roles") or []
        legacy = sm.get("role") or pe.get("role") or "other"
        if "JAM" in roles and "FULL" not in roles:
            legacy = "jam"
        elif "FULL_JAM" in roles:
            legacy = "jam"
        elif "FULL" in roles:
            legacy = "full"
        elif "DETECTION" in roles or "MERGE" in roles:
            legacy = "product"
        if legacy in role_map and pe.get("role") != legacy:
            pe["role"] = legacy
            pe["site_model_pe_roles"] = roles
            enriched += 1
    if enriched:
        report["enrichments"].append({"kind": "pe_roles", "count": enriched})

    # --- Area override from SiteModel equipment.area_id when engineer-set ---
    area_by_eq: dict[str, str] = {}
    for eq in site.get("equipment") or []:
        if eq.get("inclusion") != INCLUDED:
            continue
        aid = eq.get("area_id")
        if not aid or str(aid).upper() in {"AREA_1", "AREA1"}:
            # default placeholder — keep RUN provisional area
            continue
        # Only apply non-default / engineer areas
        if eq.get("engineer_override") or eq.get("provenance") == "ENGINEER_CONFIGURED":
            nn = normalize_name(eq.get("normalized_name") or eq.get("raw_name") or "")
            if nn:
                area_by_eq[nn] = str(aid)

    area_applied = 0
    if area_by_eq:
        for row in inp.conveyors:
            key = normalize_name(row.conveyor or "")
            if key in area_by_eq:
                row.main_area = area_by_eq[key]
                area_applied += 1
                if row.main_area not in inp.areas:
                    inp.areas.append(row.main_area)
        report["enrichments"].append({"kind": "engineer_area", "count": area_applied})

    # --- Encoder cross-check (informational; Autogen encoder path uses IO points) ---
    sm_enc = [
        e.get("raw_name") or e.get("normalized_name")
        for e in (site.get("encoders") or [])
        if e.get("inclusion") == INCLUDED
    ]
    report["site_model_encoders"] = sm_enc
    report["site_model_equipment_included"] = sum(
        1 for e in (site.get("equipment") or []) if e.get("inclusion") == INCLUDED
    )
    return inp, report


def disposition_for_equipment(
    eq: dict[str, Any],
    *,
    generated_names: set[str],
    superseded: set[str],
) -> str:
    """Classify why an INCLUDED SiteModel equipment item was or was not generated."""
    nn = normalize_name(eq.get("normalized_name") or eq.get("raw_name") or "")
    raw = eq.get("raw_name") or eq.get("normalized_name") or ""
    et = str(eq.get("equipment_type") or eq.get("type") or "").upper()
    if nn in generated_names or normalize_name(raw) in generated_names:
        return "GENERATED"
    if nn in superseded:
        return "SUPERSEDED"
    if eq.get("active_state") in {"INACTIVE_CONFIRMED", "HISTORICAL_OR_STALE"}:
        return "INACTIVE"
    if eq.get("inclusion") != INCLUDED:
        return "INTENTIONALLY_EXCLUDED"
    if et in {"PHOTOCELL", "MOTOR", "BEACON", "VFD", "PROXPART", "IMAGE"}:
        return "NOT_MECHANICAL_CONVEYOR"
    if not re.match(r"^P\d", str(raw), re.I):
        return "UNSUPPORTED_TYPE"
    # Mechanical P-tag present in SiteModel but not in Autogen load_from_run scope
    # usually means no controller I/O / word_map ownership proof
    return "CONFIGURATION_REQUIRED"

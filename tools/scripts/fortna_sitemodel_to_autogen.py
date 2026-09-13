#!/usr/bin/env python3
"""Bridge SiteModel evidence into AutogenInput without inventing site facts.

Primary path: fortna_autogen.load_from_run(run_dir) which already scopes
conveyors/PEs/IO to the controller. SiteModel optionally enriches:
  - PE roles from knowledge enrichment (pe_roles / role)
  - engineer area_id overrides when present
  - encoder list cross-check

Also projects SiteModel → dashboard workbook shapes:
  - site_model_to_sawtooth_build(site)
  - site_model_to_sorter_build(site)

SOURCE FIREWALL: RUN + SiteModel (from RUN) + overrides only.
Never imports finished PLC / answer-sheet modules.
"""
from __future__ import annotations

import re
from typing import Any

from fortna_autogen import AutogenInput, load_from_run
from fortna_site_model import INCLUDED, _clean, normalize_name


def _mrg_id_from_collector(collector: str | None, motor_io: str | None = None) -> str:
    for raw in (collector, motor_io):
        m = re.search(r"(\d{2,4}[A-Za-z]?)", str(raw or ""))
        if m:
            return m.group(1)
    return ""


def site_model_to_sawtooth_build(site: dict[str, Any] | None) -> dict[str, Any]:
    """Project SiteModel → dashboard `sawtooth_build` shape (best-effort, no invent).

    Prefers enriched `editors.sawtooth.merges`; falls back to `sawtooth_merges`.
    Unresolved collector/encoder/downstream stay empty and listed in
    `configuration_required`.
    """
    site = site or {}
    editor = ((site.get("editors") or {}).get("sawtooth")) or {}
    merges = list(editor.get("merges") or [])
    needs_enrich = (not merges) or any(
        not (m.get("collector_conveyor") and (m.get("collector_encoder") or m.get("encoder")))
        for m in merges
        if isinstance(m, dict)
    )
    if needs_enrich:
        # Re-derive collector/encoder even when a stale editors.sawtooth is cached
        try:
            from fortna_knowledge_enrich import build_sawtooth_editor_v2

            editor = build_sawtooth_editor_v2(site)
            merges = list(editor.get("merges") or [])
        except Exception:
            if not merges:
                merges = []
    if not merges:
        # Minimal fallback from raw sawtooth_merges
        for m in site.get("sawtooth_merges") or []:
            if (m.get("inclusion") or INCLUDED) not in {INCLUDED, "INCLUDED", None}:
                if m.get("inclusion") and m.get("inclusion") != INCLUDED:
                    continue
            merges.append(
                {
                    "merge_identity": m.get("raw_name") or m.get("normalized_name"),
                    "motor": m.get("motor_io"),
                    "lanes": [
                        {
                            "lane_conveyor": ln.get("conveyor"),
                            "lane_pe": ln.get("photoeye"),
                            "drive": ln.get("drive") or ln.get("vfd"),
                        }
                        for ln in (m.get("lanes") or [])
                        if isinstance(ln, dict)
                    ],
                    "collector_conveyor": None,
                    "collector_encoder": None,
                    "downstream_conveyor": None,
                    "configuration_required": ["collector conveyor", "collector encoder"],
                }
            )

    primary = merges[0] if merges else {}
    lanes_out: list[dict[str, Any]] = []
    for ln in primary.get("lanes") or []:
        if not isinstance(ln, dict):
            continue
        lanes_out.append(
            {
                "conveyor": ln.get("lane_conveyor") or ln.get("conveyor") or "",
                "pe": ln.get("lane_pe") or ln.get("photoeye") or ln.get("pe") or "",
                "jam_pe": ln.get("jam_pe") or "",
                "merge_pe": ln.get("merge_pe") or "",
                "has_encoder": "yes" if ln.get("encoder") else "no",
                "encoder_type": "Enc_RIOCard",
                "encoder_tag": ln.get("encoder") or "",
            }
        )

    collector = primary.get("collector_conveyor") or ""
    encoder = primary.get("collector_encoder") or primary.get("encoder") or ""
    downstream = primary.get("downstream_conveyor") or ""
    # Discharge/downstream is engineer-optional when RUN has no Mtrchain successor —
    # do not block Apply/READY on it. Keep collector + encoder as hard requirements.
    _optional_cfg = {
        "downstream conveyor",
        "downstream_conveyor",
        "discharge_conveyor",
        "jam_pe",
    }
    cfg_req = [
        x
        for x in (
            primary.get("configuration_required")
            or primary.get("config_required")
            or []
        )
        if str(x).strip().lower() not in _optional_cfg
    ]
    if not collector and "collector conveyor" not in cfg_req:
        cfg_req.append("collector conveyor")
    if not encoder and "collector encoder" not in cfg_req:
        cfg_req.append("collector encoder")

    motor = primary.get("motor") or ""
    return {
        "collector_conveyor": collector or "",
        "downstream_conveyor": downstream or "",
        "collector_has_encoder": "yes" if encoder else "no",
        "collector_encoder_type": "Enc_RIOCard",
        "collector_encoder": encoder or "",
        "clctr_speed_fpm": 140,
        "lane_count": len(lanes_out) or int(primary.get("lane_count") or 0),
        "lanes": lanes_out,
        "mrg_id": _mrg_id_from_collector(collector, motor),
        "motor_io": motor,
        "merge_identity": primary.get("merge_identity") or "",
        "merges": merges,
        "configuration_required": cfg_req,
        "source": "site_model",
        "detected": bool(merges),
    }


def site_model_to_sorter_build(site: dict[str, Any] | None) -> dict[str, Any]:
    """Project SiteModel → dashboard `sorter_build` shape (best-effort).

    Uses `editors.sorter` / `sorters` / research hints. Does not invent divert maps.
    Unresolved fields are listed in `configuration_required`.
    """
    site = site or {}
    editor = ((site.get("editors") or {}).get("sorter")) or {}
    sorters = list(editor.get("sorters") or site.get("sorters") or [])
    cfg_req: list[str] = [
        "divert_map",
        "conveyor_tracking_chain",
    ]
    primary = None
    for s in sorters:
        if not isinstance(s, dict):
            continue
        # Prefer non-sawtooth shoe/popup sorter rows when present
        name = str(s.get("raw_name") or s.get("normalized_name") or s.get("sorter") or "")
        stype = str(s.get("sorter_type") or s.get("type") or "").lower()
        if "sawtooth" in name.lower() and not stype:
            continue
        primary = s
        break
    if primary is None and sorters:
        primary = sorters[0] if isinstance(sorters[0], dict) else None

    encoders: list[str] = []
    if primary:
        for e in primary.get("encoders") or []:
            if isinstance(e, str) and e.strip():
                encoders.append(e.strip())
            elif isinstance(e, dict):
                n = _clean(e.get("raw_name") or e.get("normalized_name") or e.get("encoder") or "")
                if n:
                    encoders.append(n)
        enc_io = _clean(primary.get("encoder_io") or "")
        if enc_io and enc_io not in encoders:
            encoders.append(enc_io)
    if not encoders:
        for e in site.get("encoders") or []:
            if e.get("inclusion") and e.get("inclusion") != INCLUDED:
                continue
            n = _clean(e.get("raw_name") or e.get("normalized_name") or "")
            if n:
                encoders.append(n)
            if len(encoders) >= 3:
                break

    induct = ""
    induct_pe = ""
    tracking: list[dict[str, Any]] = []
    if primary:
        induct = _clean(
            primary.get("induct_conveyor")
            or primary.get("induct")
            or ""
        )
        induct_pe = _clean(primary.get("induct_pe") or "")
        for row in primary.get("tracking") or primary.get("lane_assignments") or []:
            if not isinstance(row, dict):
                continue
            conv = _clean(row.get("conveyor") or row.get("name") or "")
            if not conv:
                continue
            tracking.append(
                {
                    "conveyor": conv,
                    "pe": _clean(row.get("pe") or row.get("photoeye") or ""),
                    "has_encoder": "yes" if row.get("encoder") or row.get("has_encoder") == "yes" else "no",
                    "encoder_type": row.get("encoder_type") or "Enc_RIOCard",
                    "encoder_tag": _clean(row.get("encoder_tag") or row.get("encoder") or ""),
                }
            )

    if not induct:
        cfg_req.append("induct_conveyor")
    if not tracking:
        cfg_req.append("tracking_conveyors")
    divert_count = 0
    if primary:
        try:
            divert_count = int(primary.get("divert_count") or 0)
        except (TypeError, ValueError):
            divert_count = 0
    if divert_count <= 0:
        cfg_req.append("divert_count")

    sorter_type = ""
    if primary:
        sorter_type = str(primary.get("sorter_type") or primary.get("type") or "")
    leaves = editor.get("generation_leaves") or {}

    return {
        "sorter_type": sorter_type,
        "induct_conveyor": induct,
        "induct_pe": induct_pe,
        "induct_has_encoder": "yes" if encoders else "no",
        "induct_encoder_type": "Enc_RIOCard",
        "induct_encoder_tag": encoders[0] if encoders else "",
        "tracking_count": len(tracking),
        "tracking": tracking,
        "divert_count": divert_count,
        "tracking_pe_count": 0,
        "tracking_pes": [],
        "encoders": encoders,
        "configuration_required": cfg_req,
        "generation_leaves": leaves,
        "sorters_detected": len(sorters),
        "source": "site_model",
        "detected": bool(sorters),
        "note": (
            "Best-effort bridge from SiteModel/editors.sorter; divert map and "
            "tracking chain remain CONFIGURATION_REQUIRED unless engineer-provided."
        ),
    }


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

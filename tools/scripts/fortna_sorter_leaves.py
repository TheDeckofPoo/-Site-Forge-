#!/usr/bin/env python3
"""Proven sorter generation leaves — capability-by-capability, RUN-driven.

No monolithic Sorter_Track clone. No Greensboro constants.
Synthetic/blind sites must work with arbitrary names/numbers.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fortna_site_model import _clean, normalize_name, write_json

ROOT = Path(__file__).resolve().parents[2]

# Capability lifecycle states
MODELED = "MODELED"
GENERATABLE = "GENERATABLE"
GENERATED = "GENERATED"
CONFIGURATION_REQUIRED = "CONFIGURATION_REQUIRED"
NOT_SUPPORTED = "NOT_SUPPORTED"


CAPABILITY_CONTRACT: dict[str, dict[str, Any]] = {
    "encoder_speed": {
        "aoi_or_program": ["Enc_Routine_ST.L5X", "encoder tags"],
        "udt": ["optional ENC_* tags"],
        "run_fields": ["Encoders.Encoder Name", "Encoder I/O", "Ticks Per Foot", "Target FPM"],
        "equipment_relationships": ["sorter.encoder_io", "Encoders.asc"],
        "optional_config": ["Calculated FPM"],
        "engineer_required": [],
        "outputs": ["encoder controller tags", "optional enable/reset stubs"],
        "default_state": GENERATABLE,
    },
    "induct_detection": {
        "aoi_or_program": [],
        "udt": [],
        "run_fields": ["ScnScanDevice", "SrtScanBoss", "Conveyor PE"],
        "equipment_relationships": ["scanner→scan_zone", "PE role SCAN_TRIGGER/DETECTION"],
        "optional_config": [],
        "engineer_required": ["induct PE confirmation when ambiguous"],
        "outputs": ["induct structure tags"],
        "default_state": GENERATABLE,
    },
    "token_creation": {
        "aoi_or_program": [],
        "udt": [],
        "run_fields": ["SrtTrack* runtime (not equipment)"],
        "equipment_relationships": [],
        "optional_config": [],
        "engineer_required": ["tracking slot sizing"],
        "outputs": [],
        "default_state": MODELED,
    },
    "scanner_association": {
        "aoi_or_program": [],
        "udt": [],
        "run_fields": ["ScnScanDevice.Name", "ScanZone", "ScanType", "Machine"],
        "equipment_relationships": ["Machine serial/TCP peer"],
        "optional_config": [],
        "engineer_required": [],
        "outputs": ["scanner device tags", "scan zone tags"],
        "default_state": GENERATABLE,
    },
    "track_offset": {
        "aoi_or_program": [],
        "udt": [],
        "run_fields": [],
        "equipment_relationships": [],
        "optional_config": [],
        "engineer_required": ["encoder counts between induct and divert"],
        "outputs": [],
        "default_state": NOT_SUPPORTED,
    },
    "route_request": {
        "aoi_or_program": [],
        "udt": [],
        "run_fields": ["XfRouteBoss", "XfRouteTable", "MsgMap"],
        "equipment_relationships": ["WCS peer"],
        "optional_config": [],
        "engineer_required": ["destination map"],
        "outputs": [],
        "default_state": CONFIGURATION_REQUIRED,
    },
    "destination_response": {
        "aoi_or_program": [],
        "udt": [],
        "run_fields": ["MsgWCS", "WCSEvents"],
        "equipment_relationships": [],
        "optional_config": [],
        "engineer_required": ["WCS response contract"],
        "outputs": [],
        "default_state": NOT_SUPPORTED,
    },
    "divert_readiness": {
        "aoi_or_program": ["TRK_Divert_WaveFunction_AOI"],
        "udt": [],
        "run_fields": ["SrtZoneLane", "Sorters"],
        "equipment_relationships": ["lane PE", "lane conveyor"],
        "optional_config": ["wave parameters"],
        "engineer_required": ["lane→divert map"],
        "outputs": ["divert config model"],
        "default_state": CONFIGURATION_REQUIRED,
    },
    "divert_trigger": {
        "aoi_or_program": ["TRK_Divert_WaveFunction_AOI"],
        "udt": [],
        "run_fields": [],
        "equipment_relationships": [],
        "optional_config": [],
        "engineer_required": ["full divert timing contract"],
        "outputs": [],
        "default_state": NOT_SUPPORTED,
    },
    "divert_confirmation": {"default_state": NOT_SUPPORTED, "run_fields": [], "outputs": []},
    "divert_rate_limiting": {"default_state": NOT_SUPPORTED, "run_fields": [], "outputs": []},
    "recirculation": {"default_state": NOT_SUPPORTED, "run_fields": [], "outputs": []},
    "reason_code": {
        "aoi_or_program": [],
        "udt": ["reason code constants"],
        "run_fields": ["Srt* status vocab when present"],
        "equipment_relationships": [],
        "optional_config": [],
        "engineer_required": [],
        "outputs": ["reason code DINT/constants tags"],
        "default_state": GENERATABLE,
    },
    "wcs_event_reporting": {
        "default_state": NOT_SUPPORTED,
        "run_fields": ["WCSEvents", "MsgWCS"],
        "outputs": [],
    },
}


def _safe_tag(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", str(name or "").strip())
    if s and s[0].isdigit():
        s = "T_" + s
    return s[:40] or "Unnamed"


def assess_capabilities(site: dict[str, Any]) -> dict[str, Any]:
    has_sorter = bool(site.get("sorters"))
    has_enc = bool(site.get("encoders"))
    has_scan = bool(site.get("scanners"))
    has_wcs = any(
        "WCS" in str(c.get("message_class") or "").upper()
        or c.get("message_class") == "WCSEvents"
        for c in (site.get("communications") or [])
    )
    out = {}
    for cap, contract in CAPABILITY_CONTRACT.items():
        state = contract.get("default_state") or NOT_SUPPORTED
        if cap == "encoder_speed" and has_enc:
            state = GENERATABLE
        elif cap == "scanner_association" and has_scan:
            state = GENERATABLE
        elif cap == "induct_detection" and (has_scan or has_sorter):
            state = GENERATABLE
        elif cap == "reason_code" and has_sorter:
            state = GENERATABLE
        elif cap == "divert_readiness" and has_sorter:
            state = CONFIGURATION_REQUIRED
        elif cap in {"route_request"} and has_sorter:
            state = CONFIGURATION_REQUIRED
        elif cap == "wcs_event_reporting" and has_wcs:
            state = MODELED
        out[cap] = {
            "state": state,
            "contract": {k: contract.get(k) for k in (
                "aoi_or_program", "udt", "run_fields", "equipment_relationships",
                "optional_config", "engineer_required", "outputs",
            ) if k in contract},
        }
    return out


def generate_sorter_leaves(
    site: dict[str, Any],
    *,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """Emit generated leaf artifacts (tag XML fragments + model JSON).

    Does not implement divert trigger / WCS / full track clone.
    """
    caps = assess_capabilities(site)
    generated: dict[str, Any] = {}
    fragments: list[str] = []

    # --- encoder structures ---
    if caps.get("encoder_speed", {}).get("state") == GENERATABLE:
        enc_tags = []
        for e in site.get("encoders") or []:
            name = e.get("raw_name") or e.get("normalized_name")
            if not name:
                continue
            tag = _safe_tag(name)
            io = _clean(e.get("encoder_io") or "")
            enc_tags.append({"name": tag, "encoder_io": io or None, "source": e.get("source_table")})
            fragments.append(
                f'<Tag Name="{tag}" TagType="Base" DataType="DINT" Constant="false" ExternalAccess="Read/Write">'
                f"<Description><![CDATA[Sorter encoder leaf from RUN Encoders.asc]]></Description>"
                f"</Tag>"
            )
            if io:
                fragments.append(
                    f'<Tag Name="{_safe_tag(io)}" TagType="Base" DataType="BOOL" Constant="false" '
                    f'ExternalAccess="Read/Write">'
                    f"<Description><![CDATA[Encoder I/O pulse bit (structure only)]]></Description>"
                    f"</Tag>"
                )
        generated["encoder_speed"] = {"state": GENERATED, "encoders": enc_tags}
        caps["encoder_speed"]["state"] = GENERATED

    # --- scanner / scan-zone ---
    if caps.get("scanner_association", {}).get("state") == GENERATABLE:
        scanners = []
        for s in site.get("scanners") or []:
            name = s.get("name") or s.get("raw_name")
            if not name:
                continue
            tag = _safe_tag(name)
            zone = _safe_tag(s.get("scan_zone") or f"{name}_Zone")
            scanners.append({"scanner": tag, "scan_zone": zone, "scan_type": s.get("scan_type")})
            fragments.append(
                f'<Tag Name="{tag}" TagType="Base" DataType="DINT" Constant="false" ExternalAccess="Read/Write">'
                f"<Description><![CDATA[Scanner device structure from ScnScanDevice]]></Description>"
                f"</Tag>"
            )
            fragments.append(
                f'<Tag Name="{zone}" TagType="Base" DataType="DINT" Constant="false" ExternalAccess="Read/Write">'
                f"<Description><![CDATA[Scan zone configuration tag]]></Description>"
                f"</Tag>"
            )
        generated["scanner_association"] = {"state": GENERATED, "scanners": scanners}
        caps["scanner_association"]["state"] = GENERATED

    # --- induct structure ---
    if caps.get("induct_detection", {}).get("state") == GENERATABLE:
        inducts = []
        for s in site.get("scanners") or []:
            name = _safe_tag((s.get("name") or "Scanner") + "_Induct")
            inducts.append({"name": name, "scanner": s.get("name")})
            fragments.append(
                f'<Tag Name="{name}" TagType="Base" DataType="DINT" Constant="false" ExternalAccess="Read/Write">'
                f"<Description><![CDATA[Induct structure associated to scanner]]></Description>"
                f"</Tag>"
            )
        # Also from scan bosses if present on editors
        for boss in ((site.get("editors") or {}).get("sorter") or {}).get("scan_bosses") or []:
            name = _safe_tag((boss.get("name") or "ScanBoss") + "_Induct")
            if name not in {i["name"] for i in inducts}:
                inducts.append({"name": name, "scan_boss": boss.get("name")})
                fragments.append(
                    f'<Tag Name="{name}" TagType="Base" DataType="DINT" Constant="false" ExternalAccess="Read/Write">'
                    f"<Description><![CDATA[Induct structure from SrtScanBoss]]></Description>"
                    f"</Tag>"
                )
        generated["induct_detection"] = {"state": GENERATED, "inducts": inducts}
        caps["induct_detection"]["state"] = GENERATED

    # --- reason codes ---
    if caps.get("reason_code", {}).get("state") == GENERATABLE:
        reasons = [
            ("REASON_NO_READ", 1),
            ("REASON_NO_ROUTE", 2),
            ("REASON_LANE_FULL", 3),
            ("REASON_DIVERT_FAULT", 4),
            ("REASON_RECIRC", 5),
        ]
        for rname, val in reasons:
            fragments.append(
                f'<Tag Name="{rname}" TagType="Base" DataType="DINT" Constant="true" ExternalAccess="Read">'
                f"<Description><![CDATA[Generic sorter reason code]]></Description>"
                f'<Data Format="Dec"><DataValue Member="0" Value="{val}"/></Data></Tag>'
            )
        generated["reason_code"] = {
            "state": GENERATED,
            "codes": [{"name": n, "value": v} for n, v in reasons],
        }
        caps["reason_code"]["state"] = GENERATED

    # --- divert configuration model (structure only, no trigger) ---
    if site.get("sorters"):
        divert_cfg = []
        for s in site.get("sorters") or []:
            divert_cfg.append(
                {
                    "sorter": s.get("raw_name") or s.get("normalized_name"),
                    "encoder_io": s.get("encoder_io"),
                    "status": CONFIGURATION_REQUIRED,
                    "note": "Lane/divert map engineer-required; trigger NOT_SUPPORTED",
                }
            )
        generated["divert_configuration_model"] = {
            "state": CONFIGURATION_REQUIRED,
            "sorters": divert_cfg,
        }

    xml = ""
    if fragments:
        xml = "<Tags>\n" + "\n".join(fragments) + "\n</Tags>\n"

    result = {
        "capabilities": caps,
        "generated_leaves": generated,
        "generated_capability_names": sorted(
            k for k, v in caps.items() if v.get("state") == GENERATED
        ),
        "newly_generatable": sorted(
            k for k, v in caps.items() if v.get("state") in {GENERATABLE, GENERATED}
        ),
        "modeled": sorted(
            k for k, v in caps.items() if v.get("state") in {MODELED, CONFIGURATION_REQUIRED, GENERATABLE, GENERATED}
        ),
        "unsupported": sorted(k for k, v in caps.items() if v.get("state") == NOT_SUPPORTED),
        "tag_fragment_xml": xml,
        "greensboro_constants": False,
        "gold_sorter_track_cloned": False,
    }

    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        write_json(out_dir / "sorter_leaves_result.json", {k: v for k, v in result.items() if k != "tag_fragment_xml"})
        if xml:
            (out_dir / "sorter_leaves_tags.xml").write_text(xml, encoding="utf-8")
    return result


def build_synthetic_sorter_site() -> dict[str, Any]:
    """Non-Greensboro synthetic sorter for blind genericity."""
    return {
        "machine_scope": "ALPHASORT1",
        "sorters": [
            {
                "raw_name": "ALPHA_SORT_A",
                "normalized_name": "ALPHA_SORT_A",
                "encoder_io": "ENC9001",
                "inclusion": "INCLUDED",
            },
            {
                "raw_name": "ALPHA_SORT_B",
                "normalized_name": "ALPHA_SORT_B",
                "encoder_io": "ENC9002",
                "inclusion": "INCLUDED",
            },
        ],
        "encoders": [
            {"raw_name": "ENC9001", "encoder_io": "ENC9001_PULSE", "inclusion": "INCLUDED", "source_table": "Encoders.asc"},
            {"raw_name": "ENC9002", "encoder_io": "ENC9002_PULSE", "inclusion": "INCLUDED", "source_table": "Encoders.asc"},
        ],
        "scanners": [
            {
                "name": "ALPHA_SCAN_NORTH",
                "scan_zone": "ZONE_NORTH",
                "scan_type": "Scan",
            }
        ],
        "editors": {
            "sorter": {
                "scan_bosses": [{"name": "Alpha Scan Boss", "app_sorter": "ALPHA_SORT_A", "scan_zone": "ZONE_NORTH"}]
            }
        },
        "communications": [],
        "equipment": [
            {"raw_name": "P9001", "normalized_name": "P9001", "inclusion": "INCLUDED"},
            {"raw_name": "P9002", "normalized_name": "P9002", "inclusion": "INCLUDED"},
            {"raw_name": "P9003", "normalized_name": "P9003", "inclusion": "INCLUDED"},
        ],
    }

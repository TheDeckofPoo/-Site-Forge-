#!/usr/bin/env python3
"""Research sorter physical divert map + track offset from RUN (not finished PLC).

Produces divert_map.json and TrackOffsetModel candidates with provenance.
Does not derive constants from finished PLC5.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fortna_site_model import _clean, merge_table_rows, normalize_name, write_json


def _pe_from_timer(name: str) -> str | None:
    """Extract PE tag hint from FullClearTimer like tmfcEZPE602F_F / tmfcPE704A_F."""
    s = _clean(name)
    if not s:
        return None
    m = re.search(r"(EZPE\d{2,4}[A-Za-z]?_(?:F|P|J)\d*|PE\d{2,4}[A-Za-z]?_(?:F|P|J)\d*)", s, re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r"(EZPE\d{2,4}[A-Za-z]?|PE\d{2,4}[A-Za-z]?)", s, re.I)
    return m.group(1).upper() if m else None


def _conveyor_hint_from_lane(lane: str) -> str | None:
    """Lane strings like SHIP_LANE_F_508A1_LANES_18_19 may embed P/section ids — hint only."""
    s = _clean(lane)
    if not s:
        return None
    m = re.search(r"(P\d{2,4}[A-Za-z]?)", s, re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r"_(\d{3}[A-Za-z]?\d*)_", s)
    if m:
        # e.g. 508A1 → P508A candidate hint (not proof)
        core = m.group(1)
        if re.match(r"^\d{3}", core):
            return f"P{core}"
    return None


def research_divert_map(run_dir: Path, machine: str) -> dict[str, Any]:
    fortna = run_dir / "FORTNA"
    rows = []
    unresolved = []

    if list(fortna.glob("SrtZoneLane.asc*")):
        merged = merge_table_rows(fortna, "SrtZoneLane.asc", machine)
        for item in merged.get("rows") or []:
            row = item.get("row") or {}
            name = _clean(row.get("Name"))
            if not name or name.startswith("==="):
                continue
            enabled = _clean(row.get("Enabled")).upper()
            if enabled in {"N", "NO", "0"}:
                continue
            app = _clean(row.get("AppSorter"))
            lane = _clean(row.get("Lane"))
            host = _clean(row.get("HostZone"))
            full_tm = _clean(row.get("FullClearTimer"))
            pe = _pe_from_timer(full_tm)
            takeaway_hint = _conveyor_hint_from_lane(lane)
            entry = {
                "zone_lane_name": name,
                "app_sorter": app or None,
                "lane": lane or None,
                "host_zone": host or None,
                "full_clear_timer": full_tm or None,
                "confirm_pe_hint": pe,
                "takeaway_conveyor_hint": takeaway_hint,
                "divert_output": None,  # not explicit in SrtZoneLane sample
                "divert_number": None,
                "right_side_divert": _clean(row.get("RightSideDivert")) or None,
                "two_sided_shoe": _clean(row.get("TwoSidedShoe")) or None,
                "enabled": enabled or None,
                "source_table": "SrtZoneLane.asc",
                "source_scope": item.get("source_scope"),
                "provenance": item.get("provenance") or "RUN_EXPLICIT",
                "confidence": "MEDIUM" if pe or takeaway_hint else "LOW",
                "note": (
                    "Divert output IO not explicit in SrtZoneLane; "
                    "PE/takeaway are hints from timer/lane strings — not digit-matched proof"
                ),
            }
            if not pe and not takeaway_hint:
                unresolved.append(
                    {
                        "zone_lane_name": name,
                        "why": "No confirm PE or takeaway conveyor evidence in row fields",
                        "expected_engineer_action": "Confirm divert IO map / takeaway / confirm PE",
                    }
                )
            rows.append(entry)

    sorters = []
    if list(fortna.glob("Sorters.asc*")):
        merged = merge_table_rows(fortna, "Sorters.asc", machine)
        for item in merged.get("rows") or []:
            row = item.get("row") or {}
            name = _clean(row.get("Sorter Name") or row.get("Name"))
            if not name:
                continue
            sorters.append(
                {
                    "sorter": name,
                    "encoder_io": _clean(row.get("Encoder ioName") or row.get("Encoder Name")) or None,
                    "machine": _clean(row.get("Machine")) or None,
                    "max_cartons": _clean(row.get("Max Cartons")) or None,
                    "dump_ndx": _clean(row.get("Dump NDX")) or None,
                    "source_table": "Sorters.asc",
                }
            )

    return {
        "machine": machine,
        "divert_rows": rows,
        "sorter_sections": sorters,
        "unresolved": unresolved,
        "counts": {
            "divert_rows": len(rows),
            "with_confirm_pe_hint": sum(1 for r in rows if r.get("confirm_pe_hint")),
            "with_takeaway_hint": sum(1 for r in rows if r.get("takeaway_conveyor_hint")),
            "unresolved": len(unresolved),
            "sorter_sections": len(sorters),
        },
        "policy": [
            "Do not rely on matching device numbers as sole evidence",
            "Finished PLC5 is validation only — not used here",
            "Missing divert output IO stays CONFIGURATION_REQUIRED",
        ],
    }


def research_track_offset(run_dir: Path, machine: str, divert_map: dict[str, Any]) -> dict[str, Any]:
    """TrackOffsetModel candidates from encoder ticks + lane/sorter relationships."""
    fortna = run_dir / "FORTNA"
    encoders = {}
    if list(fortna.glob("Encoders.asc*")):
        merged = merge_table_rows(fortna, "Encoders.asc", machine)
        for item in merged.get("rows") or []:
            row = item.get("row") or {}
            name = _clean(row.get("Encoder Name"))
            if not name:
                continue
            encoders[normalize_name(name)] = {
                "name": name,
                "io": _clean(row.get("Encoder I/O")) or None,
                "ticks_per_foot": _clean(row.get("Ticks Per Foot")) or None,
                "target_fpm": _clean(row.get("Target FPM")) or None,
                "enable_bit": _clean(row.get("EnableBit")) or None,
                "source_table": "Encoders.asc",
            }

    models = []
    for s in divert_map.get("sorter_sections") or []:
        enc_name = s.get("encoder_io")
        enc = encoders.get(normalize_name(enc_name or "")) if enc_name else None
        models.append(
            {
                "source": "induct",
                "destination": "divert",
                "sorter": s.get("sorter"),
                "encoder": enc_name,
                "offset_counts": None,
                "offset_distance": None,
                "ticks_per_foot": (enc or {}).get("ticks_per_foot"),
                "confidence": "LOW",
                "provenance": "RUN_PARTIAL",
                "evidence": [
                    {"kind": "sorter_encoder_link", "sorter": s.get("sorter"), "encoder": enc_name},
                    {
                        "kind": "encoder_scale",
                        "ticks_per_foot": (enc or {}).get("ticks_per_foot"),
                        "note": "Scale known; induct→divert count offset not in RUN tables reviewed",
                    },
                ],
                "generation_state": "CONFIGURATION_REQUIRED",
                "note": "Offset counts not found as explicit RUN field — engineer/config required",
            }
        )

    return {
        "machine": machine,
        "encoders": list(encoders.values()),
        "track_offsets": models,
        "counts": {
            "encoders": len(encoders),
            "track_offset_models": len(models),
            "offsets_with_counts": sum(1 for m in models if m.get("offset_counts") is not None),
        },
    }


def build_token_model(site: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generic SorterTokenModel schema — generate structures only with proven UDT/AOI support."""
    site = site or {}
    has_sorter = bool(site.get("sorters"))
    schema = {
        "token_id": "DINT",
        "tracking_group": "DINT",
        "barcode": "STRING",
        "package_length": "DINT",
        "destination": "DINT",
        "reason_status": "DINT",
        "induct_encoder_position": "DINT",
        "current_encoder_position": "DINT",
        "divert_target": "DINT",
        "state": "DINT",
    }
    return {
        "schema": schema,
        "generation_state": "MODELED" if has_sorter else "NOT_DISCOVERED",
        "udt_proven": False,
        "note": (
            "Token structure modeled generically; UDT/AOI emit deferred until library contract proves UDT"
        ),
        "sorter_count": len(site.get("sorters") or []),
    }


def divert_readiness_model(divert_map: dict[str, Any], site: dict[str, Any] | None = None) -> dict[str, Any]:
    """Divert readiness inputs — generate only when inputs known generically."""
    site = site or {}
    inputs = [
        "sorter_at_speed",
        "takeaway_running",
        "takeaway_not_manual",
        "lane_enabled",
        "no_full_condition",
        "no_fault",
        "rate_limit_clear",
    ]
    rows = []
    for d in divert_map.get("divert_rows") or []:
        known = {
            "lane_enabled": d.get("enabled") == "Y",
            "no_full_condition": bool(d.get("confirm_pe_hint") or d.get("full_clear_timer")),
            "sorter_at_speed": False,  # needs encoder/speed leaf + link
            "takeaway_running": False,
            "takeaway_not_manual": False,
            "no_fault": False,
            "rate_limit_clear": False,
        }
        missing = [k for k, v in known.items() if not v]
        rows.append(
            {
                "zone_lane": d.get("zone_lane_name"),
                "app_sorter": d.get("app_sorter"),
                "inputs_known": known,
                "missing_inputs": missing,
                "generation_state": "CONFIGURATION_REQUIRED" if missing else "GENERATABLE",
            }
        )
    generatable = sum(1 for r in rows if r["generation_state"] == "GENERATABLE")
    return {
        "required_inputs": inputs,
        "rows": rows,
        "counts": {
            "lanes": len(rows),
            "generatable": generatable,
            "configuration_required": len(rows) - generatable,
        },
        "trigger_state": "NOT_SUPPORTED",
        "note": "Readiness modeled; trigger stays NOT_SUPPORTED until offset+token+IO+timing proven",
    }

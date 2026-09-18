#!/usr/bin/env python3
"""Sorter Program Pack Compiler — Phase 1 (hot Sorter_Track emit).

Canonical SorterModel / sorter_build → configured Sorter_Track L5X program.

Uses the reusable Fortna Sorter_Track program pack as PACK_STANDARD architecture
and expands instances from the canonical model (N encoders, N diverts, tracking).

Does NOT:
  - read finished PLC as generation input
  - invent ENC### from P### numeric suffixes
  - hard-code site/machine decisions (controller names, sorter name tokens, …)
  - claim byte-for-byte finished-PLC match
  - emit WCS_Interface_TCP_IP (Phase 1 boundary: Sorter-side only)

Severity:
  FATAL_ERROR — structurally unsafe/invalid
  REVIEW_REQUIRED — useful emit with engineer follow-up
  ENGINEER_REQUIRED — commissioning blanks
  OPTIONAL_UNRESOLVED — feature omitted
  WARNING — noteworthy non-blocking
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fortna_sorter_build import (
    SORTER_TRACK_PACK,
    build_configured_sorter_track,
    build_sorter_track,
    sorter_build_is_configured,
)

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]

# Pack-template encoder slot tokens inside Sorter_Track_Program.L5X (PACK_STANDARD).
# These are reusable pack placeholders — not site decision logic.
PACK_TEMPLATE_ENC_SLOTS = ("P504", "P506", "P508", "P509", "P510")


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _field_val(v: Any) -> str:
    if isinstance(v, dict):
        return str(v.get("value") or "").strip()
    return str(v or "").strip()


def _is_blank(v: Any) -> bool:
    s = _field_val(v).upper()
    return s in {"", "N/A", "INVALID", "NONE", "UNKNOWN", "—", "-"}


def sorter_model_to_build_config(model: dict[str, Any] | None) -> dict[str, Any]:
    """Map canonical SorterModel → sorter_build editor shape for pack emit."""
    model = model or {}
    tracking_path = model.get("tracking_path") or []
    divert_rows = model.get("divert_rows") or []
    induct = model.get("induct") or {}
    sorters = model.get("sorters") or []

    tracking = []
    for tp in tracking_path:
        enc = _field_val(tp.get("encoder_tag") or tp.get("encoder_io"))
        conv = _field_val(tp.get("conveyor"))
        pe = _field_val(tp.get("photoeye") or tp.get("induct_pe"))
        tracking.append(
            {
                "conveyor": conv,
                "pe": pe,
                "has_encoder": "yes" if enc else "no",
                "encoder_type": "Enc_RIOCard",
                "encoder_tag": enc,
                "authority": tp.get("authority") or {},
            }
        )

    # Fallback: one tracking stub per sorter encoder (encoder proven, conveyor maybe blank)
    if not tracking:
        for s in sorters:
            enc = _field_val(s.get("encoder_io") or s.get("encoder_tag"))
            if not enc:
                continue
            tracking.append(
                {
                    "conveyor": "",
                    "pe": "",
                    "has_encoder": "yes",
                    "encoder_type": "Enc_RIOCard",
                    "encoder_tag": enc,
                    "authority": {"encoder_tag": "PROVEN", "conveyor": "UNKNOWN"},
                }
            )

    divert_n = len(divert_rows) or int(model.get("divert_count") or 0)
    induct_conv = _field_val(induct.get("conveyor"))
    induct_pe = _field_val(induct.get("photoeye"))
    induct_enc = _field_val(induct.get("encoder"))
    if not induct_enc and tracking:
        induct_enc = tracking[0].get("encoder_tag") or ""

    primary = sorters[0] if sorters else {}
    name = _field_val(primary.get("name") or model.get("sorter_name"))

    return {
        "sorter_name": name,
        "sorter_type": _field_val(model.get("sorter_type") or primary.get("sorter_type")),
        "area_name": _field_val(model.get("transport_area") or primary.get("area")),
        "induct_conveyor": induct_conv,
        "induct_pe": induct_pe,
        "induct_has_encoder": "yes" if induct_enc else "no",
        "induct_encoder_type": "Enc_RIOCard",
        "induct_encoder_tag": induct_enc,
        "tracking_count": len(tracking),
        "tracking": tracking,
        "divert_count": divert_n,
        "divert_rows": [
            {
                "name": _field_val(d.get("name") or d.get("lane")),
                "lane": _field_val(d.get("lane")),
                "host_zone": _field_val(d.get("host_zone")),
                "divert_output_io": _field_val(
                    d.get("divert_output_io") or d.get("lane_enable_signal")
                ),
                "authority": d.get("authority") or {},
            }
            for d in divert_rows
        ],
        "known_sorters": [
            {
                "name": _field_val(s.get("name")),
                "encoder": _field_val(s.get("encoder_io")),
            }
            for s in sorters
        ],
        "discovery_source": "sorter_model",
        "coverage": model.get("coverage") or {},
        "field_authority": model.get("field_authority") or {},
        "application_structure": model.get("application_structure"),
        "wcs_boundary": "WCS_INTERFACE_REQUIRED_EXTERNAL",
        "plc_generation": "PHASE1_SUPPORTED",
        "generation_state": "GENERATABLE",
    }


def assess_severity(cfg: dict[str, Any]) -> dict[str, Any]:
    """Classify emit issues without fatal-blocking optional blanks."""
    fatal: list[str] = []
    review: list[str] = []
    engineer: list[str] = []
    optional: list[str] = []
    warnings: list[str] = []

    if not SORTER_TRACK_PACK.is_file():
        fatal.append("Sorter_Track program pack file missing")

    enc_n = sum(
        1
        for t in (cfg.get("tracking") or [])
        if (t or {}).get("has_encoder") == "yes" and (t or {}).get("encoder_tag")
    )
    if (cfg.get("induct_has_encoder") == "yes") and cfg.get("induct_encoder_tag"):
        enc_n = max(enc_n, 1)
    if enc_n == 0 and not (cfg.get("known_sorters") or []):
        # No sorter evidence at all → caller should not emit
        fatal.append("no_encoder_or_sorter_evidence")

    if not cfg.get("induct_pe"):
        engineer.append("induct_pe")
    if not cfg.get("induct_conveyor"):
        review.append("induct_conveyor_derived_or_blank")
    if not cfg.get("sorter_type"):
        engineer.append("sorter_type")
    if not cfg.get("area_name"):
        optional.append("transport_area")

    blank_track_conv = sum(
        1 for t in (cfg.get("tracking") or []) if not (t or {}).get("conveyor")
    )
    if blank_track_conv:
        review.append(f"tracking_conveyor_blank_rows={blank_track_conv}")

    blank_track_pe = sum(
        1 for t in (cfg.get("tracking") or []) if not (t or {}).get("pe")
    )
    if blank_track_pe:
        review.append(f"tracking_pe_blank_rows={blank_track_pe}")

    divert_n = int(cfg.get("divert_count") or 0)
    if divert_n == 0:
        warnings.append("divert_count_zero — Wave_Divert left at pack default or empty")

    # Confirm PE / global offset — optional for Phase 1
    optional.append("divert_confirm_pe")
    optional.append("global_track_offset")
    warnings.append("wcs_interface_external_not_emitted")

    return {
        "FATAL_ERROR": fatal,
        "REVIEW_REQUIRED": review,
        "ENGINEER_REQUIRED": engineer,
        "OPTIONAL_UNRESOLVED": optional,
        "WARNING": warnings,
        "can_emit": not fatal,
    }


def compile_sorter_track_pack(
    *,
    sorter_build: dict[str, Any] | None = None,
    sorter_model: dict[str, Any] | None = None,
    library_text: str = "",
    io_points: list | None = None,
    word_map: dict | None = None,
) -> dict[str, Any]:
    """Phase 1 compiler entry: produce Sorter_Track program XML + report."""
    cfg = dict(sorter_build or {})
    if sorter_model and (
        not sorter_build_is_configured(cfg)
        or int(cfg.get("divert_count") or 0) == 0
        or not (cfg.get("tracking") or [])
    ):
        # Prefer richer model when editor is hollow
        merged = sorter_model_to_build_config(sorter_model)
        for k, v in merged.items():
            if k not in cfg or cfg.get(k) in (None, "", [], 0, "NOT_STARTED", "NOT_SUPPORTED"):
                cfg[k] = v
            elif k in ("tracking", "divert_rows", "known_sorters") and not cfg.get(k):
                cfg[k] = v

    if sorter_model and not cfg.get("divert_count"):
        cfg["divert_count"] = len(sorter_model.get("divert_rows") or []) or int(
            sorter_model.get("divert_count") or 0
        )

    severity = assess_severity(cfg)
    if not severity["can_emit"]:
        return {
            "ok": False,
            "emitted": False,
            "plc_generation": "BLOCKED",
            "generation_state": "FATAL_ERROR",
            "severity": severity,
            "report": {"mode": "blocked", "reasons": severity["FATAL_ERROR"]},
            "generated_at": _ts(),
        }

    # Ensure divert_count drives Wave_Divert expansion (model multiplicity)
    if int(cfg.get("divert_count") or 0) <= 0 and (cfg.get("divert_rows") or []):
        cfg["divert_count"] = len(cfg["divert_rows"])

    live = build_sorter_track(
        cfg,
        library_text or "",
        io_points=io_points,
        word_map=word_map,
    )
    report = dict(live.get("report") or {})
    report["phase"] = "1"
    report["pack_definition"] = "Sorter_Track_Program.L5X + model expansion"
    report["wcs_boundary"] = "WCS_INTERFACE_REQUIRED_EXTERNAL"
    report["severity"] = severity
    report["encoder_slots_from_model"] = [
        (t or {}).get("encoder_tag")
        for t in (cfg.get("tracking") or [])
        if (t or {}).get("encoder_tag")
    ]
    if cfg.get("induct_encoder_tag"):
        report["induct_encoder"] = cfg.get("induct_encoder_tag")
    report["divert_count_model"] = int(cfg.get("divert_count") or 0)
    report["tracking_count_model"] = int(cfg.get("tracking_count") or len(cfg.get("tracking") or []))
    report["routines"] = _list_routines(live.get("program_xml") or "")
    report["populated_routines"] = [
        r for r in report["routines"] if r != "Build_Config"
    ]

    return {
        "ok": True,
        "emitted": True,
        "name": "Sorter_Track",
        "program_xml": live.get("program_xml"),
        "tags": live.get("tags") or [],
        "aoi_xml": live.get("aoi_xml") or "",
        "datatypes_xml": live.get("datatypes_xml") or "",
        "plc_generation": "PHASE1_GENERATED",
        "generation_state": "GENERATED",
        "severity": severity,
        "sorter_build": cfg,
        "report": report,
        "generated_at": _ts(),
    }


def _list_routines(program_xml: str) -> list[str]:
    return re.findall(r'<Routine Name="([^"]+)"', program_xml or "")


def should_emit_sorter(sorter_build: dict | None, sorter_model: dict | None = None) -> bool:
    """True when Phase 1 should emit Sorter_Track (model or configured build)."""
    if sorter_build_is_configured(sorter_build):
        return True
    if sorter_model and int(sorter_model.get("sorter_count") or 0) > 0:
        return True
    if sorter_model and (sorter_model.get("sorters") or []):
        return True
    return False


def mark_model_generation_supported(model: dict[str, Any]) -> dict[str, Any]:
    """Update canonical model generation flags for Phase 1."""
    out = dict(model or {})
    if int(out.get("sorter_count") or 0) > 0 or (out.get("sorters") or []):
        out["plc_generation"] = "PHASE1_SUPPORTED"
        out["generation_state"] = "GENERATABLE"
        out["note"] = (
            "Sorter_Track Phase 1 pack compiler available — "
            "emit from SorterModel multiplicity; WCS external."
        )
    else:
        out["plc_generation"] = "NOT_APPLICABLE"
        out["generation_state"] = "NO_SORTERS"
    return out


def write_generation_report(result: dict[str, Any], out_dir: Path | str) -> dict[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    jp = out_dir / "plc5_sorter_phase1_generation.json"
    slim = {
        k: result.get(k)
        for k in (
            "ok",
            "emitted",
            "plc_generation",
            "generation_state",
            "severity",
            "generated_at",
            "report",
        )
    }
    jp.write_text(json.dumps(slim, indent=2), encoding="utf-8")
    paths["json"] = str(jp)
    rep = result.get("report") or {}
    md = out_dir / "plc5_sorter_phase1_generation.md"
    lines = [
        "# Sorter Phase 1 Generation Report",
        "",
        f"**emitted:** `{result.get('emitted')}`  ",
        f"**plc_generation:** `{result.get('plc_generation')}`  ",
        f"**generated_at:** `{result.get('generated_at')}`",
        "",
        "## Multiplicity (from model)",
        "",
        f"- encoders: **{rep.get('encoder_count')}**",
        f"- tracking: **{rep.get('tracking_count_model', rep.get('tracking_count'))}**",
        f"- diverts: **{rep.get('divert_count_model', rep.get('divert_count'))}**",
        f"- wave rungs kept: **{rep.get('wave_rungs_kept')}** / pack **{rep.get('wave_rungs_in_pack')}**",
        "",
        "## Routines",
        "",
        ", ".join(rep.get("routines") or []) or "(none)",
        "",
        "## Severity",
        "",
        f"```json\n{json.dumps(result.get('severity'), indent=2)}\n```",
        "",
        "## WCS boundary",
        "",
        str(rep.get("wcs_boundary")),
        "",
    ]
    md.write_text("\n".join(lines), encoding="utf-8")
    paths["md"] = str(md)
    return paths

#!/usr/bin/env python3
"""CP4 Compiler Pass 1 — generate candidate L5X from frozen discovery + libraries.

INPUTS (allowed):
  - exports/cp4-discovery/*  (immutable evidence snapshot)
  - workspace/cp4-run/RUN
  - tools/libraries/* generic Fortna L5X templates
  - optional engineer workbook overlay

FORBIDDEN:
  - finished / reference PLC4 L5X as generation input
  - mutating discovery artifacts from validation results
  - silent Sorter_Track / WCS_Interface activation
  - inventing Area / ES / downstream when unproven

Usage:
  python tools/scripts/fortna_cp4_pass1.py \\
    --discovery exports/cp4-discovery \\
    --run-dir workspace/cp4-run/RUN \\
    --out exports/cp4-pass1
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_autogen import (  # noqa: E402
    DEFAULT_LIBRARY,
    FORTNA_TYPE_TO_AUTOGEN,
    FORTNA_TYPE_TO_AUTOGEN_VFD,
    OPTIONAL_PROGRAMS,
    AutogenInput,
    ConveyorRow,
    generate,
    load_from_run,
)

PROV_RUN_EXPLICIT = "RUN_EXPLICIT"
PROV_RUN_DERIVED = "RUN_DERIVED"
PROV_ENGINEER = "ENGINEER_CONFIGURED"
PROV_UNKNOWN = "UNKNOWN"
PROV_CONFIG_REQUIRED = "CONFIGURATION REQUIRED"
PROV_NOT_SUPPORTED = "GENERATION NOT YET SUPPORTED"

SAWTOOTH_TEMPLATE = ROOT / "tools" / "libraries" / "programs" / "Sawtooth_Merge_Program.L5X"
ENC_ROUTINE_TEMPLATE = ROOT / "tools" / "libraries" / "Enc_Routine_ST.L5X"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def load_discovery(discovery_dir: Path) -> dict[str, Any]:
    """Load frozen discovery snapshot — never mutate source files."""
    discovery_dir = discovery_dir.resolve()
    required = [
        "site_model.json",
        "equipment.json",
        "vfd.json",
        "sawtooth.json",
        "encoders.json",
        "tracking_wcs.json",
        "unknowns.json",
        "report.md",
    ]
    missing = [n for n in required if not (discovery_dir / n).exists()]
    if missing:
        raise FileNotFoundError(f"Discovery snapshot incomplete under {discovery_dir}: {missing}")

    def _load(name: str) -> Any:
        p = discovery_dir / name
        if name.endswith(".md"):
            return p.read_text(encoding="utf-8")
        return json.loads(p.read_text(encoding="utf-8"))

    snap = {n.replace(".json", "").replace(".md", "_md"): _load(n) for n in required}
    # normalize keys
    return {
        "dir": str(discovery_dir),
        "site_model": _load("site_model.json"),
        "equipment": _load("equipment.json"),
        "vfd": _load("vfd.json"),
        "sawtooth": _load("sawtooth.json"),
        "encoders": _load("encoders.json"),
        "tracking_wcs": _load("tracking_wcs.json"),
        "unknowns": _load("unknowns.json"),
        "report_md": _load("report.md"),
        "loaded_at": _ts(),
        "immutable": True,
    }


def build_vfd_conveyor_index(vfd_doc: dict) -> dict[str, dict[str, Any]]:
    """conveyor_tag → {vfd_base, provenance, evidence} from explicit discovery only."""
    out: dict[str, dict[str, Any]] = {}
    for row in vfd_doc.get("vfds") or []:
        base = (row.get("vfd") or "").upper()
        prov = row.get("conveyor_mapping_provenance") or PROV_UNKNOWN
        for conv in row.get("conveyors") or []:
            cu = str(conv).upper()
            out[cu] = {
                "vfd_base": base,
                "provenance": prov,
                "evidence": row.get("conveyor_mapping_evidence") or [],
                "device_points": row.get("device_points") or [],
                "saw_lanes": row.get("saw_lanes") or [],
            }
    return out


def _equip_type_for(conv_type: str, is_vfd: bool) -> str:
    typ = (conv_type or "STRAIGHT").upper()
    if is_vfd:
        return FORTNA_TYPE_TO_AUTOGEN_VFD.get(typ, "Transport with VFD")
    return FORTNA_TYPE_TO_AUTOGEN.get(typ, "Transport with MS")


def merge_discovery_conveyors(
    inp: AutogenInput,
    discovery: dict[str, Any],
    vfd_index: dict[str, dict[str, Any]],
) -> AutogenInput:
    """Ensure every discovery mechanical conveyor exists on AutogenInput."""
    existing = {(c.conveyor or "").upper(): c for c in (inp.conveyors or [])}
    machine = "ORNCCP4"
    added = 0
    for e in discovery.get("equipment", {}).get("equipment") or []:
        tag = (e.get("conveyor_tag") or e.get("tag") or "").upper()
        if not tag or not tag.startswith("P"):
            continue
        eq_typ = e.get("equipment_type") or e.get("type") or "STRAIGHT"
        is_vfd = tag in vfd_index
        ag_type = _equip_type_for(eq_typ, is_vfd=is_vfd)
        if tag in existing:
            # Refresh type if explicit VFD
            if is_vfd:
                existing[tag].type = ag_type
                existing[tag].motor_starter = ""
            continue
        added += 1
        existing[tag] = ConveyorRow(
            number=0,
            system=machine,
            main_area=f"{machine}_Area",
            safety_zone=f"{machine}_ESZone1",
            conveyor=tag,
            type=ag_type,
            downstream="",
            motor_starter="" if is_vfd else "Yes",
        )
    ordered = sorted(existing.values(), key=lambda c: c.conveyor or "")
    for i, c in enumerate(ordered, start=1):
        c.number = i
    inp.conveyors = ordered
    if machine not in (inp.areas or []):
        inp.areas = list(inp.areas or []) + [f"{machine}_Area"]
    sz = f"{machine}_ESZone1"
    if sz not in (inp.safety_zones or []):
        inp.safety_zones = list(inp.safety_zones or []) + [sz]
    print(f"discovery conveyor merge: +{added} → total {len(ordered)}", file=sys.stderr)
    return inp


def apply_explicit_vfd_to_input(
    inp: AutogenInput, vfd_index: dict[str, dict[str, Any]], equipment_doc: dict
) -> list[dict[str, Any]]:
    """Force VFD transport/accum types from discovery mappings (beats name heuristic)."""
    type_by_tag = {
        (e.get("conveyor_tag") or e.get("tag") or "").upper(): (
            e.get("equipment_type") or e.get("type") or "STRAIGHT"
        )
        for e in (equipment_doc.get("equipment") or [])
    }
    provenance_rows: list[dict[str, Any]] = []
    for c in inp.conveyors or []:
        tag = (c.conveyor or "").upper()
        hit = vfd_index.get(tag)
        eq_typ = type_by_tag.get(tag, "STRAIGHT")
        if hit and hit.get("provenance") == PROV_RUN_EXPLICIT:
            new_type = _equip_type_for(eq_typ, is_vfd=True)
            old = c.type
            c.type = new_type
            c.motor_starter = ""
            provenance_rows.append(
                {
                    "conveyor": tag,
                    "drive_class": "VFD",
                    "vfd_base": hit["vfd_base"],
                    "autogen_type": new_type,
                    "previous_type": old,
                    "rule": "explicit_discovery_mapping_beats_name_heuristic",
                    "provenance": PROV_RUN_EXPLICIT,
                    "evidence": hit.get("evidence") or [],
                }
            )
        else:
            # Keep load_from_run classification but record provenance
            is_vfd = "VFD" in (c.type or "").upper()
            provenance_rows.append(
                {
                    "conveyor": tag,
                    "drive_class": "VFD" if is_vfd else "MOTOR_STARTER",
                    "vfd_base": None,
                    "autogen_type": c.type,
                    "rule": "load_from_run_heuristic" if is_vfd else "ms_default",
                    "provenance": PROV_RUN_DERIVED if is_vfd else PROV_RUN_EXPLICIT,
                }
            )
    return provenance_rows


def mark_areas_es_config_required(inp: AutogenInput) -> list[dict[str, Any]]:
    """Do not invent Module* areas — keep controller provisional names as CONFIGURATION REQUIRED."""
    rows = []
    for c in inp.conveyors or []:
        area = c.main_area or ""
        es = c.safety_zone or ""
        area_req = (not area) or bool(re.search(r"_Area$", area)) or "Imported" in area
        es_req = (not es) or bool(re.search(r"_ESZone1$", es)) or es.upper() == "UNKNOWN"
        # Keep provisional placeholders for scaffold generation but flag them
        if not area:
            c.main_area = f"{(c.system or 'ORNCCP4')}_Area"
            area_req = True
        if not es:
            c.safety_zone = f"{(c.system or 'ORNCCP4')}_ESZone1"
            es_req = True
        rows.append(
            {
                "conveyor": c.conveyor,
                "main_area": c.main_area,
                "safety_zone": c.safety_zone,
                "area_status": PROV_CONFIG_REQUIRED if area_req else PROV_ENGINEER,
                "es_zone_status": PROV_CONFIG_REQUIRED if es_req else PROV_ENGINEER,
                "downstream": c.downstream or "",
                "downstream_status": PROV_CONFIG_REQUIRED
                if not (c.downstream or "").strip()
                else PROV_ENGINEER,
            }
        )
    # Architecture note: multiple areas supported via workbook/Transport; Pass 1 uses provisional
    return rows


def build_sawtooth_generation(sawtooth: dict, template_path: Path) -> dict[str, Any]:
    """Describe sawtooth generation from RUN + template status (no finished PLC4)."""
    template_ok = template_path.is_file()
    template_notes = []
    if template_ok:
        text = template_path.read_text(encoding="utf-8", errors="replace")
        template_notes = [
            "tools/libraries/programs/Sawtooth_Merge_Program.L5X is a reusable gold *program pack* "
            "(TargetType=Program), not a finished PLC4 controller export used as input.",
            "Pack contains Greensboro-shaped MRG414_* / lane PE tags that require parameterization.",
            "Pass 1 merges the pack via --include-programs Sawtooth_Merge and records RUN lane "
            "bindings; full MRG/lane retarget is CONFIGURATION REQUIRED for Pass 2.",
        ]
        if "ORLY_Greensboro_NC_PLC4" in text:
            template_notes.append(
                "Controller attribute strings inside the pack are retargeted by autogen "
                "_retarget_gold_site_names; collector/lane identity still needs parameter map."
            )
    lanes_out = []
    for lane in sawtooth.get("lanes") or []:
        lanes_out.append(
            {
                "lane_name": lane.get("name"),
                "conveyor": lane.get("conveyor"),
                "lane_index": lane.get("lane_index"),
                "approach": lane.get("approach"),
                "collision": lane.get("collision"),
                "lane_input": lane.get("lane_input"),
                "photoeye": lane.get("photoeye"),
                "drive": lane.get("drive") or lane.get("vfd"),
                "slice_seconds": lane.get("slice_seconds"),
                "reserve_seconds": lane.get("reserve_seconds"),
                "saw_merge": lane.get("saw_merge"),
                "provenance": lane.get("provenance") or PROV_RUN_EXPLICIT,
                "note": lane.get("conveyor_note")
                or "Conveyor from Name token — not P-number / PE / VFD equality",
                "generation": "BOUND_IN_REPORT — template lane slots need Pass-2 parameterizer",
            }
        )
    merges_out = []
    for m in sawtooth.get("merges") or []:
        merges_out.append(
            {
                "name": m.get("name"),
                "motor_io": m.get("motor_io"),
                "reservation": m.get("reservation"),
                "slice_seconds": m.get("slice_seconds"),
                "lanes": m.get("lanes") or [],
                "provenance": m.get("provenance") or PROV_RUN_EXPLICIT,
                "template_included": template_ok,
                "parameterization_status": PROV_CONFIG_REQUIRED,
            }
        )
    return {
        "generated_at": _ts(),
        "template_path": str(template_path.relative_to(ROOT)) if template_ok else None,
        "template_reusable": template_ok,
        "template_notes": template_notes,
        "include_program_key": "Sawtooth_Merge",
        "merges": merges_out,
        "lanes": lanes_out,
        "lane_count": len(lanes_out),
        "rules": [
            "explicit SawLane / Mtrchain / Motor relationship beats naming heuristic",
            "LANE_3_P116 + PE118_P + VFD118_EN is valid when RUN defines it",
            "do not assume lane conveyor number equals PE or VFD number",
        ],
        "status": "INCLUDED_WITH_RUN_BINDINGS"
        if template_ok and lanes_out
        else PROV_CONFIG_REQUIRED,
    }


def build_encoder_generation(encoders: dict) -> dict[str, Any]:
    rows = []
    for e in encoders.get("encoders") or []:
        rows.append(
            {
                "encoder": e.get("encoder"),
                "io": e.get("io"),
                "ticks_per_foot": e.get("ticks_per_foot"),
                "target_fpm": e.get("target_fpm"),
                "enable": e.get("enable"),
                "jamzone": e.get("jamzone"),
                "description": e.get("description"),
                "associations": e.get("associations") or [],
                "provenance": e.get("provenance") or PROV_RUN_EXPLICIT,
                "library_pattern": "Enc_Routine_ST.L5X / Enc_UDT (library) — Pass 1 preserves params in report; "
                "sawtooth ENC414 association recorded; full routine emit is scaffolded via Sawtooth pack tags",
                "generation_status": "PARAMETERS_PRESERVED",
            }
        )
    return {
        "generated_at": _ts(),
        "encoders": rows,
        "count": len(rows),
        "library_candidates": [
            str(ENC_ROUTINE_TEMPLATE.relative_to(ROOT)) if ENC_ROUTINE_TEMPLATE.is_file() else None,
            "OReilly_Library_v3.L5X Enc_* AOIs",
        ],
    }


def build_tracking_status(tracking: dict) -> dict[str, Any]:
    tables = []
    for name, text in (tracking.get("characterization") or {}).items():
        tables.append(
            {
                "table": name,
                "characterization": text,
                "generation": PROV_NOT_SUPPORTED,
            }
        )
    return {
        "generated_at": _ts(),
        "policy": "Do not silently add Sorter_Track or WCS_Interface_TCP_IP",
        "include_programs_blocked": ["Sorter_Track", "WCS_Interface_TCP_IP"],
        "tables": tables,
        "counts": tracking.get("counts") or {},
        "status": PROV_NOT_SUPPORTED,
    }


def build_library_provenance(include_programs: list[str]) -> dict[str, Any]:
    libs = ROOT / "tools" / "libraries"
    used = [
        {"path": "tools/libraries/OReilly_Library_v3.L5X", "role": "main_aoi_library", "provenance": "GENERIC_LIBRARY"},
        {"path": "tools/libraries/validation_oracles/Sys_Program.L5X", "role": "sys_program_oracle", "provenance": "VALIDATION_ORACLE"},
        {"path": "tools/libraries/validation_oracles/System_Program.L5X", "role": "system_program_oracle", "provenance": "VALIDATION_ORACLE"},
        {"path": "tools/libraries/Slow_Flt_AOI.L5X", "role": "slow_flt_overlay", "provenance": "GENERIC_LIBRARY"},
        {"path": "tools/libraries/validation_oracles/IO_MAP_Program.L5X", "role": "io_map_oracle", "provenance": "VALIDATION_ORACLE", "included": False},
    ]
    for key in include_programs:
        rel = OPTIONAL_PROGRAMS.get(key)
        used.append(
            {
                "path": f"tools/libraries/programs/{rel}" if rel else None,
                "role": f"optional_program:{key}",
                "provenance": "GENERIC_LIBRARY_TEMPLATE",
                "included": True,
                "note": "Gold program pack — not finished PLC4 controller input",
            }
        )
    if ENC_ROUTINE_TEMPLATE.is_file():
        used.append(
            {
                "path": "tools/libraries/Enc_Routine_ST.L5X",
                "role": "encoder_routine_pattern",
                "provenance": "GENERIC_LIBRARY",
                "included": False,
                "note": "Referenced for encoder parameter preservation / future emit",
            }
        )
    return {
        "generated_at": _ts(),
        "finished_plc4_used": False,
        "libraries": used,
        "libraries_root": str(libs),
    }


def build_conveyor_provenance(
    inp: AutogenInput,
    vfd_rows: list[dict],
    area_rows: list[dict],
) -> dict[str, Any]:
    vfd_by = {r["conveyor"]: r for r in vfd_rows}
    area_by = {r["conveyor"]: r for r in area_rows}
    rows = []
    for c in inp.conveyors or []:
        tag = c.conveyor
        vr = vfd_by.get(tag.upper()) or vfd_by.get(tag) or {}
        ar = area_by.get(tag) or {}
        rows.append(
            {
                "conveyor": tag,
                "identity_provenance": PROV_RUN_EXPLICIT,
                "motor_type": vr.get("drive_class") or ("VFD" if "VFD" in (c.type or "") else "MOTOR_STARTER"),
                "drive_provenance": vr.get("provenance") or PROV_UNKNOWN,
                "vfd_base": vr.get("vfd_base"),
                "autogen_type": c.type,
                "pe_roles": {
                    "exit": c.exit_pe_tag,
                    "add": c.add_pe_tag,
                    "jam": c.jam_pe_tags,
                    "full": c.full_pe_tags,
                    "note": "PE tags from RUN suffix classification in load_from_run; engineer confirm still required where uncertain",
                },
                "downstream": c.downstream or "",
                "downstream_status": ar.get("downstream_status") or PROV_CONFIG_REQUIRED,
                "area": c.main_area,
                "area_status": ar.get("area_status") or PROV_CONFIG_REQUIRED,
                "es_zone": c.safety_zone,
                "es_zone_status": ar.get("es_zone_status") or PROV_CONFIG_REQUIRED,
            }
        )
    return {"generated_at": _ts(), "count": len(rows), "conveyors": rows}


def build_configuration_required(
    area_rows: list[dict],
    sawtooth_gen: dict,
    tracking: dict,
) -> dict[str, Any]:
    items = []
    for r in area_rows:
        if r.get("area_status") == PROV_CONFIG_REQUIRED:
            items.append({"kind": "area", "conveyor": r["conveyor"], "status": PROV_CONFIG_REQUIRED})
        if r.get("es_zone_status") == PROV_CONFIG_REQUIRED:
            items.append({"kind": "es_zone", "conveyor": r["conveyor"], "status": PROV_CONFIG_REQUIRED})
        if r.get("downstream_status") == PROV_CONFIG_REQUIRED:
            items.append({"kind": "downstream", "conveyor": r["conveyor"], "status": PROV_CONFIG_REQUIRED})
    if sawtooth_gen.get("status") != "COMPLETE":
        items.append(
            {
                "kind": "sawtooth_parameterization",
                "detail": "Sawtooth_Merge pack included; MRG/lane PE retarget map still CONFIGURATION REQUIRED",
                "status": PROV_CONFIG_REQUIRED,
            }
        )
    items.append(
        {
            "kind": "tracking_wcs",
            "detail": "SrtTrack/MsgWCS/WCSEvents/XfrTrack inventory only",
            "status": PROV_NOT_SUPPORTED,
        }
    )
    return {
        "generated_at": _ts(),
        "counts": {
            "total": len(items),
            "area": sum(1 for i in items if i["kind"] == "area"),
            "es_zone": sum(1 for i in items if i["kind"] == "es_zone"),
            "downstream": sum(1 for i in items if i["kind"] == "downstream"),
        },
        "items": items,
    }


def run_pass1(
    *,
    discovery_dir: Path,
    run_dir: Path,
    out_dir: Path,
    library: Path,
    workbook: Path | None = None,
) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    gen_dir = out_dir / "generated"
    gen_dir.mkdir(parents=True, exist_ok=True)

    discovery = load_discovery(discovery_dir)
    # Freeze copy of discovery pointer (do not rewrite discovery)
    _write_json(
        out_dir / "discovery_pointer.json",
        {
            "discovery_dir": str(discovery_dir.resolve()),
            "immutable": True,
            "note": "Generation consumes this snapshot; validation must not mutate it",
            "loaded_at": discovery["loaded_at"],
        },
    )

    vfd_index = build_vfd_conveyor_index(discovery["vfd"])
    inp = load_from_run(run_dir, processor="1756-L83E")

    if workbook and workbook.is_file():
        try:
            from fortna_workbook import apply_workbook_to_input, load_workbook

            wb = load_workbook(workbook)
            if wb:
                inp = apply_workbook_to_input(inp, wb)
        except Exception as exc:  # pragma: no cover
            print(f"workbook overlay skipped: {exc}", file=sys.stderr)

    # Expand to all discovery mechanical conveyors (load_from_run PE/VFD scope undercounts)
    inp = merge_discovery_conveyors(inp, discovery, vfd_index)

    # Explicit VFD mappings from discovery beat name heuristics
    vfd_rows = apply_explicit_vfd_to_input(inp, vfd_index, discovery["equipment"])
    area_rows = mark_areas_es_config_required(inp)

    # Include Sawtooth pack only — never Sorter_Track / WCS in Pass 1
    include_programs = ["Sawtooth_Merge"]
    inp.include_programs = list(include_programs)
    # Ensure project naming reflects CP4
    if not (inp.project_name or "").upper().endswith("ORNCCP4"):
        inp.project_name = "OReillyGreensboro_ORNCCP4"

    sawtooth_gen = build_sawtooth_generation(discovery["sawtooth"], SAWTOOTH_TEMPLATE)
    encoder_gen = build_encoder_generation(discovery["encoders"])
    tracking_status = build_tracking_status(discovery["tracking_wcs"])
    library_prov = build_library_provenance(include_programs)

    # Generate L5X
    result = generate(inp, library, gen_dir)
    if not result.get("ok"):
        raise RuntimeError(f"generate() failed: {result}")

    conveyor_prov = build_conveyor_provenance(inp, vfd_rows, area_rows)
    config_req = build_configuration_required(area_rows, sawtooth_gen, tracking_status)

    vfd_generation = {
        "generated_at": _ts(),
        "rule": "explicit RUN VFD mapping beats naming heuristic",
        "multi_equipment_ok": True,
        "example": "VFD414 may drive P414 and P416 when Mtrchain/RUN says so",
        "mapped_conveyors": [r for r in vfd_rows if r.get("drive_class") == "VFD" and r.get("vfd_base")],
        "counts": {
            "vfd_bases_discovery": discovery["vfd"]["counts"].get("unique_vfd_bases"),
            "conveyors_forced_vfd": sum(
                1 for r in vfd_rows if r.get("rule") == "explicit_discovery_mapping_beats_name_heuristic"
            ),
        },
    }

    summary = {
        "generated_at": _ts(),
        "machine": "ORNCCP4",
        "pass": "cp4-compiler-pass1",
        "finished_plc4_used": False,
        "discovery_dir": str(discovery_dir.resolve()),
        "run_dir": str(run_dir.resolve()),
        "out_dir": str(out_dir),
        "l5x": result.get("l5x") or result.get("l5x_path") or result.get("out_l5x"),
        "counts": {
            "conveyors_generated": len(inp.conveyors or []),
            "include_programs": include_programs,
            "saw_lanes": sawtooth_gen.get("lane_count"),
            "encoders": encoder_gen.get("count"),
            "vfd_forced": vfd_generation["counts"]["conveyors_forced_vfd"],
        },
        "tracking_wcs": PROV_NOT_SUPPORTED,
        "ok": True,
    }

    _write_json(out_dir / "generation_summary.json", summary)
    _write_json(out_dir / "conveyor_provenance.json", conveyor_prov)
    _write_json(out_dir / "vfd_generation.json", vfd_generation)
    _write_json(out_dir / "encoder_generation.json", encoder_gen)
    _write_json(out_dir / "sawtooth_generation.json", sawtooth_gen)
    _write_json(out_dir / "configuration_required.json", config_req)
    _write_json(out_dir / "library_provenance.json", library_prov)
    _write_json(out_dir / "tracking_wcs_status.json", tracking_status)
    _write_json(out_dir / "autogen_result.json", result)

    report = f"""# CP4 Compiler Pass 1

Generated: {summary['generated_at']}
Finished PLC4 used: **NO**

## Inputs
- Discovery snapshot: `{discovery_dir}` (immutable)
- RUN: `{run_dir}`
- Library: `{library}`

## Outputs
- L5X under `generated/`
- Reports: generation_summary, conveyor_provenance, vfd_generation, encoder_generation,
  sawtooth_generation, configuration_required, library_provenance

## Counts
- Conveyors generated: {summary['counts']['conveyors_generated']}
- VFD forced from explicit discovery: {summary['counts']['vfd_forced']}
- Sawtooth lanes bound in report: {summary['counts']['saw_lanes']}
- Encoders: {summary['counts']['encoders']}

## Sawtooth
Template: `{sawtooth_gen.get('template_path')}`
Status: {sawtooth_gen.get('status')}
Lane identities preserved from RUN Name tokens (not PE/VFD number equality).

## Tracking / WCS
**GENERATION NOT YET SUPPORTED** — evidence preserved; Sorter_Track / WCS_Interface not auto-included.

## Configuration required
See `configuration_required.json` for Area / ES / downstream / sawtooth parameterization gaps.
"""
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CP4 Compiler Pass 1")
    ap.add_argument("--discovery", default="exports/cp4-discovery")
    ap.add_argument("--run-dir", default="workspace/cp4-run/RUN")
    ap.add_argument("--out", default="exports/cp4-pass1")
    ap.add_argument("--library", default=str(DEFAULT_LIBRARY))
    ap.add_argument("--workbook", default="", help="Optional engineer workbook overlay")
    args = ap.parse_args(argv)

    discovery = Path(args.discovery)
    if not discovery.is_absolute():
        discovery = (ROOT / discovery).resolve()
    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = (ROOT / run_dir).resolve()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = (ROOT / out_dir).resolve()
    library = Path(args.library)
    if not library.is_absolute():
        library = (ROOT / library).resolve()
    workbook = Path(args.workbook) if args.workbook else None
    if workbook and not workbook.is_absolute():
        workbook = (ROOT / workbook).resolve()

    summary = run_pass1(
        discovery_dir=discovery,
        run_dir=run_dir,
        out_dir=out_dir,
        library=library,
        workbook=workbook,
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

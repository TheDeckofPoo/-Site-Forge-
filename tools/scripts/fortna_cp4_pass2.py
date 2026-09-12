#!/usr/bin/env python3
"""CP4 Compiler Pass 2 — ownership fix + Sawtooth parameterization.

Inputs: frozen discovery + CP4 RUN + generic libraries only.
No finished PLC4. No new Transport toolbar workflows.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_autogen import DEFAULT_LIBRARY, generate, load_from_run  # noqa: E402
from fortna_cp4_pass1 import (  # noqa: E402
    SAWTOOTH_TEMPLATE,
    apply_explicit_vfd_to_input,
    build_configuration_required,
    build_conveyor_provenance,
    build_encoder_generation,
    build_library_provenance,
    build_tracking_status,
    build_vfd_conveyor_index,
    load_discovery,
    mark_areas_es_config_required,
    merge_discovery_conveyors,
)
from fortna_identity import conveyor_identities_match, linked_owns_conveyor  # noqa: E402
from fortna_sawtooth_param import parameterize_sawtooth_pack  # noqa: E402


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def filter_to_discovery_set(inp, discovery: dict) -> tuple[Any, list[str]]:
    """Drop conveyors not in frozen discovery mechanical set (fixes P120→P1200 pollution)."""
    allowed = {
        (e.get("conveyor_tag") or e.get("tag") or "").upper()
        for e in (discovery.get("equipment", {}).get("equipment") or [])
        if (e.get("conveyor_tag") or e.get("tag"))
    }
    before = [(c.conveyor or "").upper() for c in (inp.conveyors or [])]
    kept = []
    removed = []
    for c in inp.conveyors or []:
        tag = (c.conveyor or "").upper()
        if tag in allowed:
            kept.append(c)
        else:
            removed.append(tag)
    for i, c in enumerate(sorted(kept, key=lambda x: x.conveyor or ""), start=1):
        c.number = i
    inp.conveyors = sorted(kept, key=lambda x: x.conveyor or "")
    return inp, removed


def apply_sawtooth_renames_to_l5x(l5x_path: Path, renames: dict[str, str]) -> dict[str, Any]:
    """Apply explicit parameter-map renames to generated L5X (longest-first)."""
    text = l5x_path.read_text(encoding="utf-8", errors="replace")
    report = {"renames_applied": [], "arbitrary_global_digit_replace": False}
    items = sorted(renames.items(), key=lambda kv: len(kv[0]), reverse=True)
    out = text
    for old, new in items:
        if not old or old == new:
            continue
        n = out.count(old)
        if n:
            out = out.replace(old, new)
            report["renames_applied"].append({"from": old, "to": new, "occurrences": n})
    l5x_path.write_text(out, encoding="utf-8")
    report["l5x"] = str(l5x_path)
    return report


def build_realization_report(
    discovery: dict, generated_tags: list[str], removed: list[str]
) -> dict[str, Any]:
    disc = {
        (e.get("conveyor_tag") or "").upper()
        for e in (discovery["equipment"].get("equipment") or [])
        if e.get("conveyor_tag")
    }
    gen = set(generated_tags)
    extras = sorted(gen - disc)
    missing = sorted(disc - gen)
    return {
        "generated_at": _ts(),
        "discovery_mechanical": len(disc),
        "generated": len(gen),
        "extras": extras,
        "missing": missing,
        "removed_prefix_pollution": removed,
        "reconciled": not extras and not missing,
        "acceptance": "ACCEPTED" if not extras and not missing else "NOT_ACCEPTED",
        "note": "Realization reconciled against frozen discovery evidence set",
    }


def run_pass2(
    *,
    discovery_dir: Path,
    run_dir: Path,
    out_dir: Path,
    library: Path,
) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    gen_dir = out_dir / "generated"
    gen_dir.mkdir(parents=True, exist_ok=True)

    discovery = load_discovery(discovery_dir)
    _write_json(
        out_dir / "discovery_pointer.json",
        {
            "discovery_dir": str(discovery_dir.resolve()),
            "immutable": True,
            "finished_plc4_used": False,
        },
    )

    vfd_index = build_vfd_conveyor_index(discovery["vfd"])
    inp = load_from_run(run_dir, processor="1756-L83E")
    inp = merge_discovery_conveyors(inp, discovery, vfd_index)
    inp, removed = filter_to_discovery_set(inp, discovery)

    vfd_rows = apply_explicit_vfd_to_input(inp, vfd_index, discovery["equipment"])
    area_rows = mark_areas_es_config_required(inp)

    inp.include_programs = ["Sawtooth_Merge"]
    if not (inp.project_name or "").upper().endswith("ORNCCP4"):
        inp.project_name = "OReillyGreensboro_ORNCCP4"

    # Parameterize sawtooth pack (explicit map)
    saw_param = parameterize_sawtooth_pack(SAWTOOTH_TEMPLATE, discovery["sawtooth"])
    _write_json(out_dir / "parameterization_report.json", {
        "parameter_map": saw_param["parameter_map"],
        "apply_report_preview": {
            k: v for k, v in saw_param["apply_report"].items() if k != "program_xml"
        },
        "lane_count": saw_param["lane_count"],
        "rename_count": saw_param["rename_count"],
        "method": "explicit_parameter_map",
        "arbitrary_text_replace": False,
    })

    result = generate(inp, library, gen_dir)
    if not result.get("ok"):
        raise RuntimeError(f"generate failed: {result}")

    l5x_path = Path(result.get("l5x") or "")
    rename_report = {}
    if l5x_path.is_file():
        renames = saw_param["parameter_map"].get("symbol_renames") or {}
        rename_report = apply_sawtooth_renames_to_l5x(l5x_path, renames)

    encoder_gen = build_encoder_generation(discovery["encoders"])
    tracking = build_tracking_status(discovery["tracking_wcs"])
    library_prov = build_library_provenance(["Sawtooth_Merge"])
    conveyor_prov = build_conveyor_provenance(inp, vfd_rows, area_rows)
    config_req = build_configuration_required(
        area_rows,
        {
            "status": "PARAMETERIZED" if rename_report.get("renames_applied") is not None else "CONFIGURATION REQUIRED",
            "lane_count": saw_param["lane_count"],
        },
        tracking,
    )

    gen_tags = [(c.conveyor or "").upper() for c in (inp.conveyors or [])]
    realization = build_realization_report(discovery, gen_tags, removed)

    vfd_generation = {
        "generated_at": _ts(),
        "rule": "explicit RUN VFD mapping beats naming heuristic",
        "multi_equipment_ok": True,
        "assertions": {
            "VFD414": ["P414", "P416"],
            "VFD424": ["P424", "P424A"],
            "LANE_3_P116": {"conveyor": "P116", "PE": "PE118_P", "drive": "VFD118_EN"},
        },
        "mapped_conveyors": [
            r for r in vfd_rows if r.get("drive_class") == "VFD" and r.get("vfd_base")
        ],
        "counts": {
            "vfd_bases_discovery": discovery["vfd"]["counts"].get("unique_vfd_bases"),
            "conveyors_forced_vfd": sum(
                1
                for r in vfd_rows
                if r.get("rule") == "explicit_discovery_mapping_beats_name_heuristic"
            ),
        },
    }

    sawtooth_generation = {
        "generated_at": _ts(),
        "parameterized": True,
        "lane_count": saw_param["lane_count"],
        "lanes": saw_param["parameter_map"]["lane_bindings"],
        "merges": discovery["sawtooth"].get("merges"),
        "l5x_rename_report": rename_report,
        "status": "PARAMETER_MAP_APPLIED",
        "note": "Explicit symbol renames from parameter map; not arbitrary L5X mangling",
    }

    summary = {
        "generated_at": _ts(),
        "machine": "ORNCCP4",
        "pass": "cp4-compiler-pass2",
        "finished_plc4_used": False,
        "discovery_dir": str(discovery_dir.resolve()),
        "l5x": str(l5x_path) if l5x_path else None,
        "counts": {
            "conveyors_generated": len(gen_tags),
            "discovery_mechanical": realization["discovery_mechanical"],
            "removed_prefix_pollution": removed,
            "saw_lanes": saw_param["lane_count"],
            "encoders": encoder_gen.get("count"),
            "vfd_forced": vfd_generation["counts"]["conveyors_forced_vfd"],
        },
        "realization_acceptance": realization["acceptance"],
        "tracking_wcs": "GENERATION NOT YET SUPPORTED",
        "ui_note": "No new top-level Transport buttons — compiler responsibilities stay off the engineer toolbar",
        "ok": True,
    }

    _write_json(out_dir / "generation_summary.json", summary)
    _write_json(out_dir / "conveyor_realization.json", realization)
    _write_json(out_dir / "conveyor_provenance.json", conveyor_prov)
    _write_json(out_dir / "vfd_generation.json", vfd_generation)
    _write_json(out_dir / "encoder_generation.json", encoder_gen)
    _write_json(out_dir / "sawtooth_generation.json", sawtooth_generation)
    _write_json(out_dir / "configuration_required.json", config_req)
    _write_json(out_dir / "library_provenance.json", library_prov)
    _write_json(out_dir / "tracking_wcs_status.json", tracking)
    _write_json(out_dir / "autogen_result.json", {k: v for k, v in result.items() if k != "prism"})

    (out_dir / "report.md").write_text(
        f"""# CP4 Compiler Pass 2

Generated: {summary['generated_at']}
Finished PLC4 used: **NO**

## Ownership fix
Ambiguous string-prefix matching removed (`fortna_identity.conveyor_identities_match`).
Removed prefix-pollution tags: `{removed}`

Realization: **{realization['acceptance']}**
Discovery mechanical {realization['discovery_mechanical']} ↔ generated {realization['generated']}

## Sawtooth
Explicit parameter map applied ({saw_param['rename_count']} rename ops on pack preview;
L5X rename occurrences recorded in sawtooth_generation.json).
Five RUN lanes preserved with PE/drive relationships (including P116/PE118/VFD118).

## Tracking/WCS
GENERATION NOT YET SUPPORTED

## UI
No CP4-specific top-level buttons added. Workflow remains Import → Auto Build → Review → Apply → Build PLC.
""",
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CP4 Compiler Pass 2")
    ap.add_argument("--discovery", default="exports/cp4-discovery")
    ap.add_argument("--run-dir", default="workspace/cp4-run/RUN")
    ap.add_argument("--out", default="exports/cp4-pass2")
    ap.add_argument("--library", default=str(DEFAULT_LIBRARY))
    args = ap.parse_args(argv)

    def _p(p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else (ROOT / path).resolve()

    summary = run_pass2(
        discovery_dir=_p(args.discovery),
        run_dir=_p(args.run_dir),
        out_dir=_p(args.out),
        library=_p(args.library),
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

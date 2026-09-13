#!/usr/bin/env python3
"""Canonical SawtoothMergeModel from RUN cross-table evidence.

SOURCE OF TRUTH: RUN SawMerge/SawLane (+ HSSaw* when active) + Conveyor/VFD/encoder
relationships via fortna_cp4_discovery.discover_sawtooth / discover_vfd / discover_encoders.

Finished PLC4 is validation-only — never read here.

Provenance categories:
  RUN_EXPLICIT | RUN_DERIVED | DOC_DEFINED | GENERIC_LIBRARY | ENGINEER_CONFIGURED | UNRESOLVED
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_cp4_discovery import (  # noqa: E402
    discover_encoders,
    discover_sawtooth,
    discover_vfd,
)

RUN_EXPLICIT = "RUN_EXPLICIT"
RUN_DERIVED = "RUN_DERIVED"
DOC_DEFINED = "DOC_DEFINED"
GENERIC_LIBRARY = "GENERIC_LIBRARY"
ENGINEER_CONFIGURED = "ENGINEER_CONFIGURED"
UNRESOLVED = "UNRESOLVED"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(v: Any) -> str:
    return str(v or "").strip()


def _field(
    value: Any,
    *,
    source_table: str,
    source_key: str,
    relationship_rule: str,
    provenance: str,
) -> dict[str, Any]:
    empty = value is None or value == "" or value == []
    return {
        "value": None if empty and provenance == UNRESOLVED else value,
        "source_table": source_table,
        "source_row_key": source_key,
        "relationship_rule": relationship_rule,
        "provenance": UNRESOLVED if empty and provenance != GENERIC_LIBRARY else provenance,
    }


def _collector_from_motor(motor_io: str) -> str:
    m = re.match(r"^VFD(\d+[A-Z]?)", _clean(motor_io), re.I)
    return f"P{m.group(1)}" if m else ""


def _encoder_for_merge(
    encoders: list[dict[str, Any]],
    *,
    merge_name: str,
    motor_io: str,
) -> tuple[str, str]:
    """Return (encoder_name, provenance)."""
    merge_u = _clean(merge_name).upper().replace(" ", "_")
    digits = ""
    mm = re.match(r"^VFD(\d+[A-Z]?)", _clean(motor_io), re.I)
    if mm:
        digits = mm.group(1)
    for enc in encoders:
        name = _clean(enc.get("name") or enc.get("encoder") or enc.get("raw_name") or "")
        if not name:
            continue
        for assoc in enc.get("associations") or enc.get("relationships") or []:
            if not isinstance(assoc, dict):
                continue
            to = _clean(assoc.get("to") or "").upper().replace(" ", "_")
            if merge_u and merge_u in to:
                return name, RUN_DERIVED
        if digits and re.fullmatch(rf"ENC{re.escape(digits)}", name, re.I):
            return name, RUN_DERIVED
    return "", UNRESOLVED


def build_sawtooth_merge_model(
    run_dir: Path | str,
    machine: str,
) -> dict[str, Any]:
    """Build canonical SawtoothMergeModel list for one controller from RUN."""
    run_dir = Path(run_dir)
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"
    machine = (machine or "").strip() or "Machine"

    saw = discover_sawtooth(run_dir, machine)
    vfd = discover_vfd(run_dir, machine, saw)
    try:
        enc = discover_encoders(run_dir, machine, saw, vfd)
    except TypeError:
        # Older signature variants
        try:
            enc = discover_encoders(run_dir, machine, vfd)
        except TypeError:
            enc = discover_encoders(run_dir, machine, saw)

    enc_list = list(enc.get("encoders") or enc.get("devices") or [])
    lanes_by_merge: dict[str, list[dict[str, Any]]] = {}
    for ln in saw.get("lanes") or []:
        mn = _clean(ln.get("saw_merge"))
        lanes_by_merge.setdefault(mn, []).append(ln)

    merges_out: list[dict[str, Any]] = []
    for m in saw.get("merges") or []:
        name = _clean(m.get("name"))
        if not name:
            continue
        motor_io = _clean(m.get("motor_io"))
        collector = _collector_from_motor(motor_io)
        enc_name, enc_prov = _encoder_for_merge(enc_list, merge_name=name, motor_io=motor_io)
        lane_rows = lanes_by_merge.get(name) or []
        # Sort by lane_index when present
        lane_rows = sorted(
            lane_rows,
            key=lambda r: (
                r.get("lane_index") is None,
                r.get("lane_index") if r.get("lane_index") is not None else 999,
                _clean(r.get("name")),
            ),
        )

        lanes_out: list[dict[str, Any]] = []
        unresolved: list[str] = []
        for ln in lane_rows:
            lname = _clean(ln.get("name"))
            conv = _clean(ln.get("conveyor"))
            pe = _clean(ln.get("photoeye"))
            drive = _clean(ln.get("drive") or ln.get("vfd"))
            lane_obj = {
                "lane_identity": _field(
                    lname,
                    source_table="SawLane.asc",
                    source_key=lname,
                    relationship_rule="SawLane.Name",
                    provenance=RUN_EXPLICIT,
                ),
                "lane_index": _field(
                    ln.get("lane_index"),
                    source_table="SawLane.asc",
                    source_key=lname,
                    relationship_rule="SawLane.LaneNdx",
                    provenance=RUN_EXPLICIT if ln.get("lane_index") is not None else UNRESOLVED,
                ),
                "conveyor": _field(
                    conv or None,
                    source_table="SawLane.asc",
                    source_key=lname,
                    relationship_rule="P-tag token in SawLane.Name (not LaneNdx order)",
                    provenance=ln.get("conveyor_provenance") or (RUN_EXPLICIT if conv else UNRESOLVED),
                ),
                "product_pe": _field(
                    pe or None,
                    source_table="SawLane.asc",
                    source_key=lname,
                    relationship_rule="SawLane.PhotoEyeIO",
                    provenance=RUN_EXPLICIT if pe else UNRESOLVED,
                ),
                "drive": _field(
                    drive or None,
                    source_table="SawLane.asc",
                    source_key=lname,
                    relationship_rule="SawLane.DisableIO (VFD when token starts with VFD)",
                    provenance=RUN_EXPLICIT if drive else UNRESOLVED,
                ),
                "vfd": _field(
                    drive if drive.upper().startswith("VFD") else None,
                    source_table="SawLane.asc",
                    source_key=lname,
                    relationship_rule="DisableIO is VFD*",
                    provenance=RUN_EXPLICIT if drive.upper().startswith("VFD") else UNRESOLVED,
                ),
                "motor": _field(
                    motor_io or None,
                    source_table="SawMerge.asc",
                    source_key=name,
                    relationship_rule="SawMerge.MotorIO (shared merge motor / aux)",
                    provenance=RUN_EXPLICIT if motor_io else UNRESOLVED,
                ),
                "approach": _field(
                    _clean(ln.get("approach")) or None,
                    source_table="SawLane.asc",
                    source_key=lname,
                    relationship_rule="SawLane.ApproachUP",
                    provenance=RUN_EXPLICIT if _clean(ln.get("approach")) else UNRESOLVED,
                ),
                "collision": _field(
                    _clean(ln.get("collision")) or None,
                    source_table="SawLane.asc",
                    source_key=lname,
                    relationship_rule="SawLane.CollisionUP",
                    provenance=RUN_EXPLICIT if _clean(ln.get("collision")) else UNRESOLVED,
                ),
                "lane_input": _field(
                    _clean(ln.get("lane_input")) or None,
                    source_table="SawLane.asc",
                    source_key=lname,
                    relationship_rule="SawLane.LaneIN",
                    provenance=RUN_EXPLICIT if _clean(ln.get("lane_input")) else UNRESOLVED,
                ),
                "slice_seconds": _field(
                    ln.get("slice_seconds"),
                    source_table="SawLane.asc",
                    source_key=lname,
                    relationship_rule="SawLane.SliceSeconds",
                    provenance=RUN_EXPLICIT if ln.get("slice_seconds") is not None else UNRESOLVED,
                ),
                "reserve_seconds": _field(
                    ln.get("reserve_seconds"),
                    source_table="SawLane.asc",
                    source_key=lname,
                    relationship_rule="SawLane.ReserveSeconds",
                    provenance=RUN_EXPLICIT if ln.get("reserve_seconds") is not None else UNRESOLVED,
                ),
                "allowed_to_run": _field(
                    _clean(ln.get("allowed_to_run")) or None,
                    source_table="SawLane.asc",
                    source_key=lname,
                    relationship_rule="SawLane.AllowedToRun",
                    provenance=RUN_EXPLICIT if _clean(ln.get("allowed_to_run")) else UNRESOLVED,
                ),
                "jam_pe": _field(
                    None,
                    source_table="",
                    source_key=lname,
                    relationship_rule="No dedicated jam PE column on SawLane for this RUN",
                    provenance=UNRESOLVED,
                ),
            }
            for k, fld in lane_obj.items():
                if isinstance(fld, dict) and fld.get("provenance") == UNRESOLVED and k in (
                    "conveyor",
                    "product_pe",
                    "drive",
                ):
                    unresolved.append(f"{lname}.{k}")
            lanes_out.append(lane_obj)

        if not collector:
            unresolved.append("collector_conveyor")
        if not enc_name:
            unresolved.append("merge_encoder")

        merge_obj = {
            "name": name,
            "merge_identity": name,
            "lane_count": _field(
                len(lanes_out),
                source_table="SawLane.asc",
                source_key=name,
                relationship_rule="count of SawLane rows with SawMerge=this merge",
                provenance=RUN_EXPLICIT,
            ),
            "collector_conveyor": _field(
                collector or None,
                source_table="SawMerge.asc",
                source_key=name,
                relationship_rule="VFD### from MotorIO → P### when MotorIO is VFD###_AUX/EN",
                provenance=RUN_DERIVED if collector else UNRESOLVED,
            ),
            "discharge_conveyor": _field(
                None,
                source_table="",
                source_key=name,
                relationship_rule="No Convpath successor; leave UNRESOLVED for engineer",
                provenance=UNRESOLVED,
            ),
            "merge_encoder": _field(
                enc_name or None,
                source_table="Encoders / Conveyor associations",
                source_key=enc_name or name,
                relationship_rule="ENC### matching VFD### digits or encoder→merge association",
                provenance=enc_prov,
            ),
            "motor_io": _field(
                motor_io or None,
                source_table="SawMerge.asc",
                source_key=name,
                relationship_rule="SawMerge.MotorIO",
                provenance=RUN_EXPLICIT if motor_io else UNRESOLVED,
            ),
            "reservation": _field(
                _clean(m.get("reservation")) or None,
                source_table="SawMerge.asc",
                source_key=name,
                relationship_rule="SawMerge.ReserveIN",
                provenance=RUN_EXPLICIT if _clean(m.get("reservation")) else UNRESOLVED,
            ),
            "lane_enable_delay_tm": _field(
                _clean(m.get("lane_enable_delay_tm")) or None,
                source_table="SawMerge.asc",
                source_key=name,
                relationship_rule="SawMerge.LaneEnableDelayTM",
                provenance=RUN_EXPLICIT if _clean(m.get("lane_enable_delay_tm")) else UNRESOLVED,
            ),
            "slice_seconds_merge": _field(
                m.get("slice_seconds"),
                source_table="SawMerge.asc",
                source_key=name,
                relationship_rule="SawMerge.pSliceSeconds",
                provenance=RUN_EXPLICIT if m.get("slice_seconds") is not None else UNRESOLVED,
            ),
            "parameters": {
                "slice_seconds_merge": m.get("slice_seconds"),
                "reservation": _clean(m.get("reservation")),
                "lane_enable_delay_tm": _clean(m.get("lane_enable_delay_tm")),
            },
            "lanes": lanes_out,
            "tables_used": [
                "SawMerge.asc",
                "SawLane.asc",
                "HSSawMerge.asc",
                "HSSawLane.asc",
                "HSSawParm.asc",
                "Conveyor.asc",
                "Encoders (associations)",
            ],
            "hs_tables_active": saw.get("hs_tables_active") or {},
            "unresolved": unresolved,
            "provenance": RUN_EXPLICIT,
            "source_file": m.get("source_file"),
            "notes": list(saw.get("notes") or []),
        }
        merges_out.append(merge_obj)

    return {
        "generated_at": _ts(),
        "machine": machine,
        "run_dir": str(run_dir),
        "source_of_truth": "RUN SawMerge/SawLane + VFD/encoder relationships — finished PLC4 never read",
        "detected": bool(merges_out),
        "merge_count": len(merges_out),
        "lane_count": sum(int((m.get("lane_count") or {}).get("value") or 0) for m in merges_out),
        "merges": merges_out,
        "vfd_summary": {
            "unique_bases": (vfd.get("counts") or {}).get("unique_vfd_bases"),
            "mapped_to_conveyor_explicit": (vfd.get("counts") or {}).get("mapped_to_conveyor_explicit"),
            "mapped_to_saw_lane_explicit": (vfd.get("counts") or {}).get("mapped_to_saw_lane_explicit"),
        },
        "encoder_summary": {
            "count": (enc.get("counts") or {}).get("encoders")
            or (enc.get("counts") or {}).get("devices")
            or len(enc_list),
        },
        "raw_discovery_counts": saw.get("counts") or {},
    }


def model_to_editor_shape(model: dict[str, Any]) -> dict[str, Any]:
    """Shape consumed by dashboard sawtoothBuildFromSiteModel / editors.sawtooth."""
    merges_ed = []
    for m in model.get("merges") or []:
        def _v(fld: dict | None) -> Any:
            if not isinstance(fld, dict):
                return fld
            return fld.get("value")

        lanes = []
        for ln in m.get("lanes") or []:
            lanes.append(
                {
                    "name": _v(ln.get("lane_identity")),
                    "lane_identity": _v(ln.get("lane_identity")),
                    "lane_index": _v(ln.get("lane_index")),
                    "conveyor": _v(ln.get("conveyor")),
                    "lane_conveyor": _v(ln.get("conveyor")),
                    "photoeye": _v(ln.get("product_pe")),
                    "lane_pe": _v(ln.get("product_pe")),
                    "jam_pe": _v(ln.get("jam_pe")) or "",
                    "drive": _v(ln.get("drive")),
                    "vfd": _v(ln.get("vfd")),
                    "motor": _v(ln.get("motor")),
                    "approach": _v(ln.get("approach")),
                    "collision": _v(ln.get("collision")),
                    "lane_input": _v(ln.get("lane_input")),
                    "slice_seconds": _v(ln.get("slice_seconds")),
                    "reserve_seconds": _v(ln.get("reserve_seconds")),
                    "allowed_to_run": _v(ln.get("allowed_to_run")),
                    "provenance": RUN_EXPLICIT,
                    "field_provenance": {
                        k: (ln[k].get("provenance") if isinstance(ln.get(k), dict) else None)
                        for k in ln
                    },
                    "configuration_required": [
                        k
                        for k, fld in ln.items()
                        if isinstance(fld, dict)
                        and fld.get("provenance") == UNRESOLVED
                        and k in ("conveyor", "product_pe", "drive")
                    ],
                }
            )
        merges_ed.append(
            {
                "merge_identity": m.get("merge_identity") or m.get("name"),
                "raw_name": m.get("name"),
                "normalized_name": m.get("name"),
                "lane_count": _v(m.get("lane_count")),
                "lanes": lanes,
                "motor": _v(m.get("motor_io")),
                "motor_io": _v(m.get("motor_io")),
                "collector_conveyor": _v(m.get("collector_conveyor")),
                "collector_encoder": _v(m.get("merge_encoder")),
                "encoder": _v(m.get("merge_encoder")),
                "downstream_conveyor": _v(m.get("discharge_conveyor")),
                "reservation": _v(m.get("reservation")),
                "slice_seconds": _v(m.get("slice_seconds_merge")),
                "lane_enable_delay_tm": _v(m.get("lane_enable_delay_tm")),
                "configuration_required": list(m.get("unresolved") or []),
                "config_required": list(m.get("unresolved") or []),
                "provenance": m.get("provenance"),
                "sawtooth_merge_model": True,
            }
        )
    return {
        "editor": "sawtooth_merge_model_v1",
        "detected": bool(merges_ed),
        "merges": merges_ed,
        "merge_count": model.get("merge_count") or 0,
        "lane_count": model.get("lane_count") or 0,
        "note": "Auto-built on RUN import from SawMerge/SawLane cross-table evidence",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Build SawtoothMergeModel from RUN")
    ap.add_argument("--run-dir", default=str(REPO_ROOT / "workspace" / "cp4-run" / "RUN"))
    ap.add_argument("--machine", default="ORNCCP4")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    model = build_sawtooth_merge_model(args.run_dir, args.machine)
    out = Path(args.out) if args.out else REPO_ROOT / "exports" / "cp4-sawtooth-model" / "sawtooth_merge_model.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(model, indent=2), encoding="utf-8")
    editor = model_to_editor_shape(model)
    (out.parent / "sawtooth_editor.json").write_text(json.dumps(editor, indent=2), encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "out": str(out),
        "merge_count": model.get("merge_count"),
        "lane_count": model.get("lane_count"),
        "unresolved": [u for m in model.get("merges") or [] for u in (m.get("unresolved") or [])],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

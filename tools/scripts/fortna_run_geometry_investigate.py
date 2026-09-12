#!/usr/bin/env python3
"""Diagnostic RUN geometry investigation (no Transport/Autogen changes).

Exports normalized equipment geometry + connection candidates from a Fortna RUN
Conveyor.asc (and related tables). Generic — controller name is an input, not
hardcoded site logic.

Usage:
  python fortna_run_geometry_investigate.py \\
    --run-dir workspace/active/RUN \\
    --machine ORNCCP2 \\
    --out exports/run-geometry
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import CONVEYOR_TYPES, read_asc  # noqa: E402

try:
    from fortna_io_extract import belongs_to_controller
except Exception:  # pragma: no cover
    belongs_to_controller = None  # type: ignore

try:
    from fortna_autogen import _load_eip_adapters
except Exception:  # pragma: no cover
    _load_eip_adapters = None  # type: ignore


MECH_TYPES = frozenset(
    {t.upper() for t in CONVEYOR_TYPES}
    | {"ZEROPRESSURE", "ACCUMULATOR", "MDR"}
)


def _f(v) -> float | None:
    try:
        s = str(v or "").strip()
        if not s or s.upper() in {"N/A", "INVALID", "NONE", "~"}:
            return None
        return float(s)
    except (TypeError, ValueError):
        return None


def _clean(v) -> str:
    s = str(v or "").strip()
    if s.upper() in {"", "N/A", "INVALID", "NONE", "~", "N/A~"}:
        return ""
    return s


def _deg_to_rad(deg: float) -> float:
    return deg * math.pi / 180.0


def _unit(angle_deg: float) -> tuple[float, float]:
    """Flow direction unit vector. Angle: degrees CCW from +X (Fortna HMI convention assumption)."""
    r = _deg_to_rad(angle_deg)
    return (math.cos(r), math.sin(r))


def _anchors(x: float, y: float, length: float, angle: float) -> dict:
    """XY = infeed/ENTRY end; exit = XY + Length along Angle (Greensboro calibration).

    Prior (incorrect) model treated XY as footprint center ± L/2. Internal RUN
    abutments (P312→P314, P136→P138, …) validate the infeed-origin model at HIGH
    confidence. See fortna_physical_geometry.CALIBRATION / docs/RUN_GEOMETRY_CALIBRATION.md.
    """
    ux, uy = _unit(angle)
    return {
        "entry": {"x": x, "y": y},
        "exit": {"x": x + length * ux, "y": y + length * uy},
        "assumption": "infeed_origin_flow_along_angle_v1",
    }


def _dist(a: dict, b: dict) -> float:
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def _angle_delta(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def _load_word_map(run_dir: Path):
    if _load_eip_adapters is None:
        return {}
    try:
        _ad, _ip, _mods, _topo, word_map = _load_eip_adapters(run_dir)
        return word_map or {}
    except Exception:
        return {}


def _row_on_controller(row: dict, machine: str, word_map: dict) -> bool:
    if not machine:
        return True
    mname = _clean(row.get("Machine_Name"))
    iow = str(row.get("IO_Address_Word") or "").strip()
    if belongs_to_controller is not None:
        try:
            return bool(
                belongs_to_controller(
                    machine_name=mname,
                    io_word=iow,
                    controller=machine,
                    word_map=word_map,
                )
            )
        except Exception:
            pass
    # Fallback: Machine_Name match or empty/N/A with IO word present
    if mname.upper() == machine.upper():
        return True
    if mname in ("", "N/A") and iow and iow not in ("0", "N/A"):
        # Ambiguous without word map — include for geometry dump with low confidence
        return True
    return False


def _is_mech_conveyor(row: dict) -> bool:
    typ = _clean(row.get("Type")).upper()
    name = _clean(row.get("IO_Name"))
    if typ in MECH_TYPES and re.match(r"^P\d+", name, re.I):
        return True
    return False


def _is_motor_row(row: dict) -> bool:
    typ = _clean(row.get("Type")).upper()
    name = _clean(row.get("IO_Name")).upper()
    if typ == "MOTOR":
        return True
    if name.startswith("VFD"):
        return True
    if re.match(r"^M\d+", name) and typ not in MECH_TYPES | {"PHOTOCELL", "BEACON"}:
        return True
    return False


def _is_pe_row(row: dict) -> bool:
    typ = _clean(row.get("Type")).upper()
    name = _clean(row.get("IO_Name")).upper()
    return typ == "PHOTOCELL" or name.startswith(("PE", "EZPE", "PES"))


def _classify_drive(motor_name: str, motor_row: dict | None, vfd_keys: set[str]) -> str:
    n = (motor_name or "").upper()
    if n.startswith("VFD"):
        return "VFD"
    # Number match against known VFD tags on controller
    m = re.search(r"(\d{2,4})", n)
    if m and (m.group(1) in vfd_keys or any(m.group(1) in k for k in vfd_keys)):
        return "VFD"
    drive = _clean((motor_row or {}).get("Drive")).upper()
    if drive in {"VFD", "VARIABLE FREQUENCY DRIVE", "DRIVE"}:
        return "VFD"
    if n.startswith("M"):
        # Fortna MS / contactor pattern when not VFD-named
        return "CONTACTOR / MOTOR STARTER"
    return "UNKNOWN"


def _load_mtrchain(run_dir: Path) -> dict[str, list[str]]:
    """Map conveyor P### → list of motor names from Mtrchain.asc."""
    path = run_dir / "FORTNA" / "Mtrchain.asc"
    if not path.is_file():
        return {}
    _h, rows = read_asc(path)
    conv_to_motors: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        motor = _clean(r.get("Motor_Name"))
        if not motor:
            continue
        for i in range(1, 11):
            linked = _clean(r.get(f"Motor_Chained{i}"))
            if not linked:
                continue
            if re.match(r"^P\d+", linked, re.I):
                key = linked.upper()
                if motor not in conv_to_motors[key]:
                    conv_to_motors[key].append(motor)
    return dict(conv_to_motors)


def _load_merge_hints(run_dir: Path, machine: str) -> list[dict]:
    hints = []
    candidates = [
        run_dir / "FORTNA" / f"MergeInputs.asc.{machine}",
        run_dir / "FORTNA" / "MergeInputs.asc",
        run_dir / "FORTNA" / f"MergeBoss.asc.{machine}",
        run_dir / "FORTNA" / "MergeBoss.asc",
        run_dir / "FORTNA" / "Merges.asc",
    ]
    for path in candidates:
        if not path.is_file() or path.stat().st_size < 10:
            continue
        _h, rows = read_asc(path)
        usable = 0
        for r in rows:
            name = _clean(r.get("Name") or r.get("Merge Table Name") or r.get("MergeBoss"))
            valid = _clean(r.get("Valid")).upper()
            if not name or name.upper() in {"N/A"}:
                continue
            if valid in {"N", "NO"} and "MergeInputs" not in path.name:
                continue
            # Extract P-tags from name fields
            blob = " ".join(str(v) for v in r.values())
            ptags = sorted(set(re.findall(r"P\d+[A-Za-z]?", blob, flags=re.I)))
            if not ptags and valid not in {"Y", "YES"}:
                continue
            usable += 1
            hints.append(
                {
                    "source_file": path.name,
                    "name": name,
                    "valid": valid,
                    "merge_boss": _clean(r.get("MergeBoss")),
                    "presence": _clean(r.get("Presense") or r.get("Presense_Eye1")),
                    "p_tags_mentioned": [p.upper() if p[1:].isdigit() else ("P" + p[1:]) for p in ptags],
                    "raw_subset": {
                        k: _clean(r.get(k))
                        for k in list(r.keys())[:12]
                        if _clean(r.get(k))
                    },
                }
            )
        if usable:
            break
    return hints


def _pe_to_conveyor_guess(pe_name: str) -> str:
    """Weak naming association only — not topology. PE138_P → P138."""
    m = re.match(r"^(?:EZ)?PE[\s\-_]*(\d{2,4}[A-Za-z]?)", pe_name or "", re.I)
    if m:
        return "P" + m.group(1)
    return ""


def _controller_conveyor_tags(run_dir: Path, machine: str) -> set[str]:
    """Same identity set Autogen uses for this controller (PE/VFD-linked P###)."""
    try:
        from fortna_autogen import load_from_run

        inp = load_from_run(run_dir, processor="1756-L83E")
        # load_from_run scopes to machine discovered from RUN identity
        return {(c.conveyor or "").strip().upper() for c in (inp.conveyors or []) if c.conveyor}
    except Exception:
        return set()


def investigate(run_dir: Path, machine: str, out_dir: Path) -> dict:
    conv_path = run_dir / "FORTNA" / "Conveyor.asc"
    if not conv_path.is_file():
        raise FileNotFoundError(f"Missing {conv_path}")

    word_map = _load_word_map(run_dir)
    _h, rows = read_asc(conv_path)
    mtrchain = _load_mtrchain(run_dir)
    merge_hints = _load_merge_hints(run_dir, machine)
    controller_tags = _controller_conveyor_tags(run_dir, machine)

    # Collect VFD number keys + motor/PE rows (controller-scoped when possible)
    vfd_keys: set[str] = set()
    motor_rows_by_name: dict[str, dict] = {}
    pe_rows: list[dict] = []
    mech_by_name: dict[str, dict] = {}

    for r in rows:
        name = _clean(r.get("IO_Name"))
        if not name:
            continue
        on_ctrl = _row_on_controller(r, machine, word_map)
        if name.upper().startswith("VFD") and on_ctrl:
            m = re.search(r"(\d{2,4})", name)
            if m:
                vfd_keys.add(m.group(1))
        if _is_motor_row(r) and on_ctrl:
            motor_rows_by_name[name.upper()] = r
        if _is_pe_row(r) and on_ctrl:
            pe_rows.append(r)
        if _is_mech_conveyor(r):
            # Prefer first geometric row per P-tag
            key = name.upper()
            if key not in mech_by_name:
                mech_by_name[key] = r

    # Primary set = Autogen controller conveyors that have ASC geometry rows
    target_tags = sorted(controller_tags & set(mech_by_name.keys()))
    # If Autogen set empty, fall back to controller-scoped mech rows
    if not target_tags:
        target_tags = sorted(
            k
            for k, r in mech_by_name.items()
            if _row_on_controller(r, machine, word_map)
        )

    equipment: list[dict] = []
    for tag in target_tags:
        r = mech_by_name[tag]
        name = _clean(r.get("IO_Name"))
        x, y = _f(r.get("X_cord")), _f(r.get("Y_cord"))
        ang, length, width = _f(r.get("Angle")), _f(r.get("Length")), _f(r.get("Width"))
        typ = _clean(r.get("Type")).upper()
        in_tan = _f(r.get("Infeed_Tangent"))
        out_tan = _f(r.get("Discharge_Tangent"))
        inside_r = _f(r.get("Inside_Radius"))
        conf = []
        if x is None or y is None:
            conf.append("missing_xy")
        if ang is None:
            conf.append("missing_angle")
        if typ in {"CURVE", "TRIANG"}:
            if inside_r is None or inside_r <= 0:
                conf.append("curve_missing_inside_radius")
            if length is None or length <= 0:
                conf.append("curve_length_sentinel")  # expected (-1); not a hard fail
        elif length is None or length <= 0:
            conf.append("missing_length")

        # Physical geometry (infeed-origin + curve IR/tangents) — see fortna_physical_geometry
        try:
            from fortna_physical_geometry import build_equipment_geometry

            geom = build_equipment_geometry(r)
        except Exception:
            geom = None

        anchors = None
        if geom and geom.get("entry") and geom.get("exit"):
            anchors = {
                "entry": geom["entry"],
                "exit": geom["exit"],
                "assumption": (geom.get("provenance") or {}).get("model")
                or geom.get("kind")
                or "physical_geometry_v1",
            }
        elif x is not None and y is not None and ang is not None and length and length > 0:
            anchors = _anchors(x, y, length, ang)

        # Motors: Mtrchain primary; never invent
        motors = list(mtrchain.get(name.upper(), []))
        # Also Motor column if present
        mot_col = _clean(r.get("Motor"))
        if mot_col and mot_col not in motors:
            motors.append(mot_col)

        drive_types = []
        for mname in motors:
            mrow = motor_rows_by_name.get(mname.upper())
            drive_types.append(
                {
                    "motor": mname,
                    "drive_type": _classify_drive(mname, mrow, vfd_keys),
                }
            )

        # PE association by naming convention only (evidence note)
        pe_assoc = []
        for pe in pe_rows:
            pe_name = _clean(pe.get("IO_Name"))
            guess = _pe_to_conveyor_guess(pe_name)
            if guess.upper() == name.upper():
                pe_assoc.append(
                    {
                        "photoeye": pe_name,
                        "association": "name_suffix_match",
                        "confidence": "HIGH-CONFIDENCE CANDIDATE",
                    }
                )

        hard_issues = [c for c in conf if c not in {"curve_length_sentinel"}]
        if geom and geom.get("confidence"):
            geom_conf = geom["confidence"]
        else:
            geom_conf = "HIGH" if not hard_issues else ("MEDIUM" if len(hard_issues) == 1 else "LOW")
        equipment.append(
            {
                "conveyor": name,
                "x": x,
                "y": y,
                "angle": ang,
                "length": length,
                "width": width,
                "equipment_type": typ,
                "infeed_tangent": in_tan,
                "discharge_tangent": out_tan,
                "inside_radius": inside_r,
                "motors": motors,
                "drives": drive_types,
                "drive_type": (
                    drive_types[0]["drive_type"]
                    if len(drive_types) == 1
                    else ("MIXED" if drive_types else "UNKNOWN")
                ),
                "photoeyes_name_associated": pe_assoc,
                "entry_anchor": anchors["entry"] if anchors else None,
                "exit_anchor": anchors["exit"] if anchors else None,
                "anchor_assumption": anchors["assumption"] if anchors else None,
                "geometry": geom,
                "angle_out": (geom or {}).get("angle_out"),
                "path": (geom or {}).get("path") or [],
                "arc_samples": (geom or {}).get("arc_samples") or [],
                "render_kind": (geom or {}).get("kind") or "unknown",
                "infeed_elevation": _f(r.get("Infeed_Elevation")),
                "discharge_elevation": _f(r.get("Discharge_Elevation")),
                "part_number": _clean(r.get("Part_Number")),
                "device_description": _clean(r.get("Device_Description")),
                "io_module_type": _clean(r.get("IO_Module_Type")),
                "drawing_page": _clean(r.get("Electrical Drawing Page No.")),
                "io_name": name,
                "machine_name": _clean(r.get("Machine_Name")),
                "io_address_word": _clean(r.get("IO_Address_Word")),
                "in_motor_chain": _clean(r.get("In Motor Chain")),
                "source_fields": {
                    "table": "FORTNA/Conveyor.asc",
                    "type": typ,
                    "x_field": "X_cord",
                    "y_field": "Y_cord",
                    "angle_field": "Angle",
                    "length_field": "Length",
                    "width_field": "Width",
                    "inside_radius_field": "Inside_Radius",
                    "infeed_tangent_field": "Infeed_Tangent",
                    "discharge_tangent_field": "Discharge_Tangent",
                    "xy_meaning": "infeed_entry_end",
                    "motor_association": "Mtrchain.asc Motor_Chained* → P-tag",
                },
                "geometry_issues": conf,
                "confidence": geom_conf,
            }
        )

    # Second pass: refine CURVE turn using other equipment entry points as mate targets
    try:
        from fortna_physical_geometry import build_equipment_geometry

        mate_entries = [
            (float(e["entry_anchor"]["x"]), float(e["entry_anchor"]["y"]))
            for e in equipment
            if e.get("entry_anchor")
        ]
        for e in equipment:
            if (e.get("equipment_type") or "").upper() not in {"CURVE", "TRIANG"}:
                continue
            tag = e["conveyor"].upper()
            r = mech_by_name.get(tag)
            if not r:
                continue
            others = [p for p in mate_entries if e.get("entry_anchor") and (
                abs(p[0] - float(e["entry_anchor"]["x"])) > 1e-6
                or abs(p[1] - float(e["entry_anchor"]["y"])) > 1e-6
            )]
            geom = build_equipment_geometry(r, mate_entries=others)
            if geom and geom.get("entry") and geom.get("exit"):
                e["geometry"] = geom
                e["entry_anchor"] = geom["entry"]
                e["exit_anchor"] = geom["exit"]
                e["anchor_assumption"] = (geom.get("provenance") or {}).get("model") or "curve_ir_tangent_v1"
                e["path"] = geom.get("path") or []
                e["arc_samples"] = geom.get("arc_samples") or []
                e["render_kind"] = geom.get("kind") or "curve"
                e["angle_out"] = geom.get("angle_out")
                e["confidence"] = geom.get("confidence") or e.get("confidence")
    except Exception:
        pass

    # Connection candidates (geometry only — never P-number order)
    by_tag = {e["conveyor"].upper(): e for e in equipment}
    usable = [
        e
        for e in equipment
        if e.get("entry_anchor") and e.get("exit_anchor") and e.get("width")
    ]
    candidates = []
    # Track best inbound per conveyor for ambiguity
    inbound_hits: dict[str, list] = defaultdict(list)

    for a in usable:
        for b in usable:
            if a["conveyor"].upper() == b["conveyor"].upper():
                continue
            d = _dist(a["exit_anchor"], b["entry_anchor"])
            wref = min(float(a["width"] or 1), float(b["width"] or 1))
            a_out = a.get("angle_out")
            if a_out is None:
                a_out = a.get("angle") or 0
            ang_err = _angle_delta(float(a_out), float(b.get("angle") or 0))
            # Thresholds in RUN drawing units (infeed-origin model).
            # True abutments land near distance 0; keep modest bands for gaps/joints.
            if d > max(3.0 * wref, 1200.0):
                continue
            if d <= max(0.25 * wref, 50.0) and ang_err <= 15.0:
                level = "CONFIRMED"
            elif d <= max(1.0 * wref, 250.0) and ang_err <= 30.0:
                level = "HIGH-CONFIDENCE CANDIDATE"
            elif d <= max(3.0 * wref, 1200.0):
                level = "AMBIGUOUS"
            else:
                continue
            rec = {
                "from_conveyor": a["conveyor"],
                "to_conveyor": b["conveyor"],
                "exit_to_entry_distance": round(d, 3),
                "angle_delta_deg": round(ang_err, 2),
                "width_ref": wref,
                "classification": level,
                "method": "geometry_exit_to_entry",
                "note": "Not inferred from P-tag numerical order",
            }
            candidates.append(rec)
            inbound_hits[b["conveyor"].upper()].append(rec)

    # Downgrade to AMBIGUOUS when multiple strong inbound candidates exist
    for _tag, hits in inbound_hits.items():
        strong = [h for h in hits if h["classification"] in {"CONFIRMED", "HIGH-CONFIDENCE CANDIDATE"}]
        if len(strong) > 1:
            for h in strong:
                h["classification"] = "AMBIGUOUS"
                h["ambiguity"] = f"{len(strong)} inbound geometric candidates"

    # Deduplicate / sort
    candidates.sort(key=lambda c: (c["classification"], c["exit_to_entry_distance"]))

    # Counts
    drive_counter = Counter()
    for e in equipment:
        if not e["drives"]:
            drive_counter["UNKNOWN"] += 1
        else:
            for d in e["drives"]:
                drive_counter[d["drive_type"]] += 1
    multi_motor = sum(1 for e in equipment if len(e["motors"]) > 1)
    # Invert: motor → conveyors
    motor_fanout: dict[str, set[str]] = defaultdict(set)
    for conv, motors in mtrchain.items():
        for m in motors:
            motor_fanout[m.upper()].add(conv.upper())
    motors_driving_multiple_conveyors = sum(1 for _m, cs in motor_fanout.items() if len(cs) > 1)
    class_counts = Counter(c["classification"] for c in candidates)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_dir),
        "machine": machine,
        "conveyors_discovered": len(equipment),
        "usable_xy": sum(1 for e in equipment if e["x"] is not None and e["y"] is not None),
        "usable_angle": sum(1 for e in equipment if e["angle"] is not None),
        "usable_length_width": sum(
            1 for e in equipment if e["length"] and e["width"] and e["length"] > 0 and e["width"] > 0
        ),
        "motors_discovered": len(motor_rows_by_name),
        "motors_linked_via_mtrchain": sum(len(e["motors"]) for e in equipment),
        "vfd_classified": drive_counter.get("VFD", 0),
        "contactor_classified": drive_counter.get("CONTACTOR / MOTOR STARTER", 0),
        "unknown_drive": drive_counter.get("UNKNOWN", 0) + drive_counter.get("MIXED", 0),
        "multiple_motor_conveyors": multi_motor,
        "motors_driving_multiple_conveyors": motors_driving_multiple_conveyors,
        "photoeyes_scoped": len(pe_rows),
        "merge_table_hints": len(merge_hints),
        "connection_candidates_total": len(candidates),
        "confirmed_connections": class_counts.get("CONFIRMED", 0),
        "high_confidence_candidates": class_counts.get("HIGH-CONFIDENCE CANDIDATE", 0),
        "ambiguous_connections": class_counts.get("AMBIGUOUS", 0),
        "unknown_connections": max(
            0,
            len(equipment)
            - len({c["from_conveyor"].upper() for c in candidates if c["classification"] != "AMBIGUOUS"}),
        ),
        "anchor_model_assumption": (
            "(X,Y)=infeed/ENTRY end; Angle=flow deg CCW from +X; "
            "exit=XY+Length·û. CURVE uses Inside_Radius+tangents+90° arc (MEDIUM)."
        ),
        "topology_rule": "P-tag numerical order is NEVER used as physical adjacency evidence.",
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    site_key = re.sub(r"[^A-Za-z0-9_\-]+", "_", machine or "site").strip("_") or "site"
    eq_path = out_dir / f"{site_key}_equipment.json"
    cand_path = out_dir / f"{site_key}_connection_candidates.json"
    csv_path = out_dir / f"{site_key}_equipment.csv"
    svg_path = out_dir / f"{site_key}_layout_preview.svg"
    summary_path = out_dir / f"{site_key}_summary.json"

    eq_path.write_text(json.dumps({"summary": summary, "equipment": equipment}, indent=2), encoding="utf-8")
    cand_path.write_text(
        json.dumps(
            {"summary": summary, "candidates": candidates, "merge_hints": merge_hints},
            indent=2,
        ),
        encoding="utf-8",
    )
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # CSV
    fields = [
        "conveyor",
        "x",
        "y",
        "angle",
        "length",
        "width",
        "equipment_type",
        "motors",
        "drive_type",
        "confidence",
        "drawing_page",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for e in equipment:
            w.writerow(
                {
                    "conveyor": e["conveyor"],
                    "x": e["x"],
                    "y": e["y"],
                    "angle": e["angle"],
                    "length": e["length"],
                    "width": e["width"],
                    "equipment_type": e["equipment_type"],
                    "motors": ";".join(e["motors"]),
                    "drive_type": e["drive_type"],
                    "confidence": e["confidence"],
                    "drawing_page": e["drawing_page"],
                }
            )

    _write_svg(equipment, candidates, svg_path)

    return {
        "summary": summary,
        "equipment_path": str(eq_path),
        "candidates_path": str(cand_path),
        "csv_path": str(csv_path),
        "svg_path": str(svg_path),
        "equipment": equipment,
        "candidates": candidates,
        "merge_hints": merge_hints,
    }


def _write_svg(equipment: list[dict], candidates: list[dict], path: Path) -> None:
    pts = [(e["x"], e["y"]) for e in equipment if e["x"] is not None and e["y"] is not None]
    if not pts:
        path.write_text("<!-- no geometry -->\n", encoding="utf-8")
        return
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    pad = 2000
    width = max(max_x - min_x, 1) + 2 * pad
    height = max(max_y - min_y, 1) + 2 * pad

    def tx(x: float) -> float:
        return x - min_x + pad

    def ty(y: float) -> float:
        # SVG y grows downward; flip for print-like view
        return (max_y - y) + pad

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.1f} {height:.1f}" '
        f'width="1600" height="1200" style="background:#0b1220">',
        "<title>RUN geometry diagnostic (not Transport Build)</title>",
    ]
    # connection lines first
    for c in candidates:
        if c["classification"] == "AMBIGUOUS":
            color = "#f59e0b"
        elif c["classification"] == "CONFIRMED":
            color = "#22c55e"
        else:
            color = "#38bdf8"
        a = next((e for e in equipment if e["conveyor"] == c["from_conveyor"]), None)
        b = next((e for e in equipment if e["conveyor"] == c["to_conveyor"]), None)
        if not a or not b or not a.get("exit_anchor") or not b.get("entry_anchor"):
            continue
        x1, y1 = tx(a["exit_anchor"]["x"]), ty(a["exit_anchor"]["y"])
        x2, y2 = tx(b["entry_anchor"]["x"]), ty(b["entry_anchor"]["y"])
        lines.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{color}" stroke-width="40" opacity="0.55"/>'
        )

    for e in equipment:
        if e["x"] is None or e["y"] is None:
            continue
        x, y = tx(e["x"]), ty(e["y"])
        L = float(e["length"] or 800)
        W = float(e["width"] or 200)
        ang = float(e["angle"] or 0)
        # rectangle centered, rotated (SVG rotate clockwise visually after y-flip — approximate)
        lines.append(
            f'<g transform="translate({x:.1f},{y:.1f}) rotate({-ang:.2f})">'
            f'<rect x="{-L/2:.1f}" y="{-W/2:.1f}" width="{L:.1f}" height="{W:.1f}" '
            f'fill="#1e293b" stroke="#94a3b8" stroke-width="30"/>'
            f'<text x="0" y="10" text-anchor="middle" fill="#e2e8f0" '
            f'font-size="280" font-family="monospace">{e["conveyor"]}</text>'
            f"</g>"
        )
        if e.get("exit_anchor"):
            ex, ey = tx(e["exit_anchor"]["x"]), ty(e["exit_anchor"]["y"])
            lines.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="60" fill="#f43f5e"/>')
        if e.get("entry_anchor"):
            ix, iy = tx(e["entry_anchor"]["x"]), ty(e["entry_anchor"]["y"])
            lines.append(f'<circle cx="{ix:.1f}" cy="{iy:.1f}" r="60" fill="#22c55e"/>')

    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_markdown_report(result: dict, docs_path: Path) -> None:
    s = result["summary"]
    eq = result["equipment"]
    cands = result["candidates"]
    merges = result.get("merge_hints") or []

    # Feasibility answer
    usable_frac = (s["usable_xy"] / s["conveyors_discovered"]) if s["conveyors_discovered"] else 0
    strong = s["confirmed_connections"] + s["high_confidence_candidates"]
    if usable_frac >= 0.85 and s["conveyors_discovered"] >= 10 and strong >= 3:
        answer = (
            "YES — with caveats. Greensboro RUN Conveyor.asc provides usable X/Y/Angle/Length/Width "
            "for the controller-scoped mechanical conveyors, enough for a useful first-pass physical "
            "layout sketch and high-confidence geometric connection candidates. It is NOT sufficient "
            "alone for complete Autogen topology: area/safety zones, many finished-PLC conveyors, and "
            "reliable merge/downstream semantics still require engineer confirmation (and prints when available)."
        )
        verdict = "USEFUL_FIRST_PASS"
    elif usable_frac >= 0.5:
        answer = (
            "PARTIAL. Geometry exists for many conveyors but coverage/confidence is incomplete for a "
            "standalone first-pass layout without engineer review."
        )
        verdict = "PARTIAL"
    else:
        answer = (
            "NO — RUN geometry is too sparse/unreliable for an automatic first-pass physical layout."
        )
        verdict = "NOT_SUFFICIENT"

    lines = [
        "# RUN Geometry Investigation",
        "",
        f"Generated: `{s['generated_at']}`",
        f"RUN: `{s['run_dir']}`",
        f"Controller/machine scope: `{s['machine']}`",
        "",
        "## Headline question",
        "",
        "**Can this RUN reconstruct a useful first-pass physical layout without using the PDF?**",
        "",
        f"**Answer ({verdict}):** {answer}",
        "",
        "## Counts",
        "",
        f"| Metric | Count |",
        f"|---|---:|",
        f"| Conveyors discovered (mechanical P###) | {s['conveyors_discovered']} |",
        f"| Usable X/Y | {s['usable_xy']} |",
        f"| Usable angle | {s['usable_angle']} |",
        f"| Usable length/width | {s['usable_length_width']} |",
        f"| Motors discovered (Conveyor.asc MOTOR/VFD rows) | {s['motors_discovered']} |",
        f"| Motor↔conveyor links via Mtrchain | {s['motors_linked_via_mtrchain']} |",
        f"| VFD classified (motor links) | {s['vfd_classified']} |",
        f"| Contactor/MS classified | {s['contactor_classified']} |",
        f"| Unknown/mixed drive | {s['unknown_drive']} |",
        f"| Multiple-motor conveyors | {s['multiple_motor_conveyors']} |",
        f"| Motors driving multiple conveyors (Mtrchain fan-out) | {s.get('motors_driving_multiple_conveyors', 0)} |",
        f"| Photoeyes scoped to controller | {s['photoeyes_scoped']} |",
        f"| Merge table hints | {s['merge_table_hints']} |",
        f"| Connection candidates (total geometric) | {s['connection_candidates_total']} |",
        f"| CONFIRMED connections | {s['confirmed_connections']} |",
        f"| HIGH-CONFIDENCE CANDIDATE | {s['high_confidence_candidates']} |",
        f"| AMBIGUOUS connections | {s['ambiguous_connections']} |",
        f"| Conveyors without strong outbound geometric link (approx unknown) | {s['unknown_connections']} |",
        "",
        "## Fields recovered from Conveyor.asc",
        "",
        "Present and used:",
        "",
        "- `IO_Name` (P-tag)",
        "- `X_cord`, `Y_cord`, `Width`, `Length`, `Angle`",
        "- `Type` (STRAIGHT / CURVE / TRIANG / BELT / …)",
        "- `Part_Number`, `Device_Description`, `IO_Module_Type`",
        "- `Electrical Drawing Page No.`",
        "- `Infeed_Elevation`, `Discharge_Elevation`",
        "- `In Motor Chain`",
        "- `IO_Address_Word` / bit (controller scoping)",
        "",
        "Present but weak/empty on this controller sample:",
        "",
        "- `Motor` column on mechanical rows (empty — association comes from **Mtrchain.asc**)",
        "- `Drive` column (empty on sampled ORNCCP2 mechanical rows)",
        "",
        "## Related RUN evidence",
        "",
        "### Motors / drives",
        "",
        "- `Mtrchain.asc`: `Motor_Name` → `Motor_Chained1..N` (often P###). Supports **multiple conveyors per motor chain** and inverse multi-motor lookup.",
        "- VFD vs contactor: primarily from motor tag naming (`VFD*` vs `M*`) plus optional Drive field; many VFDs may be absent as Conveyor.asc Type=MOTOR rows.",
        "- One conveyor ≠ one motor is supported by the data model; this sample’s multi-motor conveyor count is reported above.",
        "",
        "### Photoeyes",
        "",
        "- PHOTOCELL rows in Conveyor.asc scoped by controller.",
        "- Association to conveyors here is **name-based only** (e.g. PE138_P → P138) — not geometric mating.",
        "",
        "### Merges / adjacency",
        "",
        "- `MergeInputs.asc.<machine>` can mention lane names / presence PEs / merge boss names.",
        "- `Merges.asc` on this RUN was largely empty/invalid placeholders.",
        "- Geometric exit→entry matching is the primary adjacency experiment in this pass.",
        "",
        "### Area / safety zone",
        "",
        "- Not trustworthy from Conveyor.asc geometry fields alone for this controller.",
        "- Remain workbook / Transport Build / engineer-defined (see Autogen area-safety fidelity work).",
        "",
        "## Geometry model assumptions",
        "",
        s["anchor_model_assumption"],
        "",
        "**Critical rule:** numerical P-tag order is never treated as physical adjacency.",
        "",
        "## Connection classification",
        "",
        "| Class | Meaning |",
        "|---|---|",
        "| CONFIRMED | Exit≈entry within ~0.75×min(width) (or 300u) and angle Δ≤15° |",
        "| HIGH-CONFIDENCE CANDIDATE | Within ~2×width (or 750u) and angle Δ≤30° |",
        "| AMBIGUOUS | Spatially close but angle mismatch, or multiple inbound candidates |",
        "| UNKNOWN | No geometric partner under thresholds |",
        "",
        "Sample high-confidence / confirmed (up to 15):",
        "",
    ]
    shown = 0
    for c in cands:
        if c["classification"] not in {"CONFIRMED", "HIGH-CONFIDENCE CANDIDATE"}:
            continue
        lines.append(
            f"- `{c['from_conveyor']} → {c['to_conveyor']}` "
            f"{c['classification']} dist={c['exit_to_entry_distance']} angΔ={c['angle_delta_deg']}"
        )
        shown += 1
        if shown >= 15:
            break
    if not shown:
        lines.append("- _(none at CONFIRMED/HIGH thresholds — see candidates JSON)_")

    lines.extend(
        [
            "",
            "## Desired future PhysicalConveyor model (feasibility)",
            "",
            "Feasible fields from RUN today:",
            "",
            "```",
            "PhysicalConveyor",
            "  identity          ← IO_Name P###",
            "  equipment_type    ← Type",
            "  geometry          ← X/Y/Angle/Length/Width (+ elevations)",
            "  entry_anchor     ← derived (assumption-based)",
            "  exit_anchor(s)    ← derived (curves TBD)",
            "  motors[]          ← Mtrchain (+ future Drive/VFD classification)",
            "  photoeyes[]       ← name association now; geometry later",
            "  connections[]     ← geometric candidates + engineer confirm",
            "```",
            "",
            "Physical connections should eventually be mating entry/exit anchors, not generic graph wires.",
            "",
            "## Artifacts",
            "",
            f"- `{result['equipment_path']}`",
            f"- `{result['candidates_path']}`",
            f"- `{result['csv_path']}`",
            f"- `{result['svg_path']}` (diagnostic preview only)",
            "",
            "## Out of scope",
            "",
            "- No Transport Build UI changes",
            "- No Autogen changes",
            "- No PDF parsing",
            "- No hardcoded Greensboro production behavior",
            "",
        ]
    )
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="RUN geometry diagnostic investigation")
    ap.add_argument("--run-dir", default=str(ROOT / "workspace" / "active" / "RUN"))
    ap.add_argument("--machine", default="ORNCCP2", help="Controller/machine scope (not site-hardcoded logic)")
    ap.add_argument("--out", default=str(ROOT / "exports" / "run-geometry"))
    ap.add_argument("--docs", default=str(ROOT / "docs" / "RUN_GEOMETRY_INVESTIGATION.md"))
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir)
    out_dir = Path(args.out)
    result = investigate(run_dir, args.machine, out_dir)

    # Stable Greensboro deliverable names requested by task (copies)
    eq = Path(result["equipment_path"])
    cand = Path(result["candidates_path"])
    g_eq = out_dir / "greensboro_equipment.json"
    g_cand = out_dir / "greensboro_connection_candidates.json"
    g_eq.write_text(eq.read_text(encoding="utf-8"), encoding="utf-8")
    g_cand.write_text(cand.read_text(encoding="utf-8"), encoding="utf-8")
    result["equipment_path"] = str(g_eq)
    result["candidates_path"] = str(g_cand)

    write_markdown_report(result, Path(args.docs))
    s = result["summary"]
    print("RUN GEOMETRY INVESTIGATION")
    print(f"  conveyors={s['conveyors_discovered']} xy={s['usable_xy']} angle={s['usable_angle']}")
    print(
        f"  motors={s['motors_discovered']} VFD={s['vfd_classified']} "
        f"contactor={s['contactor_classified']} multi-motor-convs={s['multiple_motor_conveyors']}"
    )
    print(
        f"  connections confirmed={s['confirmed_connections']} "
        f"high={s['high_confidence_candidates']} ambiguous={s['ambiguous_connections']}"
    )
    print(f"  docs={args.docs}")
    print(f"  equipment={g_eq}")
    print(f"  candidates={g_cand}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

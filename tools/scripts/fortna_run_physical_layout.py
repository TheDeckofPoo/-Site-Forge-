#!/usr/bin/env python3
"""Build a Transport Build graph from RUN physical geometry (Auto Build From RUN).

SOURCE-OF-TRUTH (see docs/SOURCE_OF_TRUTH_POLICY.md):
  INPUT SIDE only — RUN tables + engineer config later.
  Must NEVER read a finished/reference L5X to populate conveyors, areas,
  safety zones, downstream, PEs, motors, or merges.

Uses the same geometry/connection logic as fortna_run_geometry_investigate.py.
Does not invent area/ES zone names from P-tags. Does not use P-number order.

Usage:
  python fortna_run_physical_layout.py --run-dir workspace/active/RUN --machine ORNCCP2 --out exports/run-geometry
  python fortna_run_physical_layout.py --run-dir ... --stdout-graph
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_run_geometry_investigate import investigate  # noqa: E402


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _kind_from_type(equipment_type: str) -> str:
    t = (equipment_type or "").upper()
    if t == "CURVE":
        return "conv_right"
    if t in {"TRIANG", "SPUR"}:
        return "conv_straight"
    return "conv_straight"


def _infer_pe_roles(tag: str) -> list[str]:
    u = (tag or "").upper()
    if re.search(r"_F\d*$|_FULL|FULL", u) and "_JF" not in u and "_FDJ" not in u:
        return ["full"]
    if re.search(r"_J\d*$|_JAM|JAM|_JF|_FDJ", u):
        return ["jam"]
    if re.search(r"_P\d*$|PRODUCT|PRESENT|DISCHARGE", u) or u.endswith("_P"):
        return ["exit", "jam"]
    return ["exit"]


def _normalize_canvas(
    equipment: list[dict],
    *,
    # Fixed RUN→canvas scale. Do NOT compress plant geometry into a viewport box;
    # Electron fitView zooms to the resulting extents (Curtis Phase 5 acceptance).
    pixels_per_run_unit: float = 0.045,
    pad: float = 120.0,
    # Legacy kwargs retained for callers; ignored so geometry is never squashed.
    canvas_w: float | None = None,
    canvas_h: float | None = None,
) -> tuple[dict[str, tuple[float, float]], float]:
    """Map RUN source XY → canvas pixels at a stable scale.

    Returns tag→(x,y) and scale. Viewport fitting is the UI's job — never shrink
    spacing to fit 1600×1000 (that produced the compressed-knot failure mode).
    """
    del canvas_w, canvas_h  # intentionally unused
    pts = [
        (e["conveyor"].upper(), e["x"], e["y"])
        for e in equipment
        if e.get("x") is not None and e.get("y") is not None
    ]
    if not pts:
        return {}, float(pixels_per_run_unit)
    xs = [p[1] for p in pts]
    ys = [p[2] for p in pts]
    min_x = min(xs)
    max_y = max(ys)
    scale = float(pixels_per_run_unit)
    if scale <= 0:
        scale = 0.045
    out: dict[str, tuple[float, float]] = {}
    for tag, x, y in pts:
        # Flip Y for screen coords (RUN Y often increases "up" on prints)
        cx = pad + (x - min_x) * scale
        cy = pad + (max_y - y) * scale
        out[tag] = (cx, cy)
    return out, scale


def build_transport_graph(
    run_dir: Path,
    machine: str,
    *,
    connect_threshold: str = "HIGH_CONFIDENCE",
) -> dict:
    """Return Transport Build graph JSON + metrics."""
    tmp_out = run_dir.parent / "_run_physical_layout_tmp"
    result = investigate(run_dir, machine, tmp_out)
    equipment = result.get("equipment") or []
    candidates = result.get("candidates") or []
    summary = result.get("summary") or {}

    # Auto-connect only clear thresholds
    auto_levels = {"CONFIRMED"}
    if connect_threshold.upper() in {"HIGH_CONFIDENCE", "HIGH-CONFIDENCE", "HIGH"}:
        auto_levels |= {"HIGH-CONFIDENCE CANDIDATE", "HIGH_CONFIDENCE"}

    canvas_pos, scale = _normalize_canvas(equipment)
    area_id = _uid("area")
    # Organizational container only — provenance SUGGESTED; do not invent ModuleB/Trash
    area_name = f"{machine}_Imported" if machine else "RUN_Imported"

    nodes: list[dict] = []
    id_by_tag: dict[str, str] = {}
    placed = 0
    motors_vfd = motors_contactor = motors_unknown = 0
    motors_total = 0

    for e in equipment:
        tag = e["conveyor"]
        nid = _uid("node")
        id_by_tag[tag.upper()] = nid
        sx, sy = e.get("x"), e.get("y")
        cx, cy = canvas_pos.get(tag.upper(), (80.0 + placed * 20, 120.0))
        if tag.upper() in canvas_pos:
            placed += 1
        angle = float(e["angle"] or 0.0)
        # Keep continuous rotation for physical display; portSides uses 90° steps
        rot_step = int(round(angle / 90.0) * 90) % 360
        geom = e.get("geometry") or {}
        # Canvas x/y = schematic body center; sourceX/Y remain RUN infeed (never mutated)
        body_cx, body_cy = cx, cy
        if e.get("x") is not None and e.get("y") is not None and geom.get("center"):
            try:
                gcx = float(geom["center"]["x"])
                gcy = float(geom["center"]["y"])
                sx, sy = float(e["x"]), float(e["y"])
                body_cx = cx + (gcx - sx) * scale
                body_cy = cy - (gcy - sy) * scale  # Y flip matches _normalize_canvas
            except Exception:
                body_cx, body_cy = cx, cy

        devices = []
        for d in e.get("drives") or []:
            motors_total += 1
            dt = (d.get("drive_type") or "UNKNOWN").upper()
            if "VFD" in dt:
                motors_vfd += 1
            elif "CONTACTOR" in dt or "STARTER" in dt:
                motors_contactor += 1
            else:
                motors_unknown += 1
            devices.append(
                {
                    "id": _uid("dev"),
                    "kind": "motor",
                    "tag": d.get("motor") or "",
                    "name": d.get("motor") or "",
                    "driveType": d.get("drive_type") or "UNKNOWN",
                }
            )
        for pe in e.get("photoeyes_name_associated") or []:
            ptag = pe.get("photoeye") or ""
            if not ptag:
                continue
            devices.append(
                {
                    "id": _uid("dev"),
                    "kind": "photoeye",
                    "tag": ptag,
                    "name": ptag,
                    "roles": _infer_pe_roles(ptag),
                    "rolesManual": False,
                    "association": pe.get("association") or "name_suffix_match",
                }
            )

        kind = _kind_from_type(e.get("equipment_type") or "")
        # Project RUN-world path points into canvas space for schematic SVG
        def _proj_pt(pt: dict | None) -> dict | None:
            if not pt or e.get("x") is None or e.get("y") is None:
                return None
            try:
                return {
                    "x": round(cx + (float(pt["x"]) - float(e["x"])) * scale, 2),
                    "y": round(cy - (float(pt["y"]) - float(e["y"])) * scale, 2),
                }
            except Exception:
                return None

        canvas_path = []
        for cmd in e.get("path") or geom.get("path") or []:
            item = {"cmd": cmd.get("cmd")}
            if "x" in cmd and "y" in cmd:
                p = _proj_pt({"x": cmd["x"], "y": cmd["y"]})
                if p:
                    item.update(p)
            if cmd.get("cmd") == "arc":
                item["radius"] = round(float(cmd.get("radius") or 0) * scale, 2)
                item["sweep_deg"] = cmd.get("sweep_deg")
                # SVG Y-flip reverses arc sweep direction
                sf = cmd.get("sweep_flag")
                if sf is not None:
                    item["sweep_flag"] = 0 if sf else 1
                else:
                    item["sweep_flag"] = 1 if float(cmd.get("sweep_deg") or 0) < 0 else 0
                if cmd.get("center"):
                    item["center"] = _proj_pt(cmd["center"])
            canvas_path.append(item)

        canvas_arc_samples = []
        for pt in e.get("arc_samples") or geom.get("arc_samples") or []:
            p = _proj_pt(pt)
            if p:
                canvas_arc_samples.append(p)

        node = {
            "id": nid,
            "kind": kind,
            "label": tag,
            "conveyorTag": tag,
            "x": round(body_cx, 2),
            "y": round(body_cy, 2),
            "rotation": rot_step,
            "sourceX": sx,
            "sourceY": sy,
            "sourceAngle": angle,
            "length": e.get("length"),
            "width": e.get("width"),
            "equipmentType": e.get("equipment_type") or "",
            "infeedTangent": e.get("infeed_tangent"),
            "dischargeTangent": e.get("discharge_tangent"),
            "insideRadius": e.get("inside_radius"),
            "entryAnchor": e.get("entry_anchor"),
            "exitAnchor": e.get("exit_anchor"),
            "entryCanvas": _proj_pt(e.get("entry_anchor")),
            "exitCanvas": _proj_pt(e.get("exit_anchor")),
            "pathCanvas": canvas_path,
            "arcSamplesCanvas": canvas_arc_samples,
            "renderKind": e.get("render_kind") or geom.get("kind") or "unknown",
            "angleOut": e.get("angle_out") or geom.get("angle_out"),
            "physical": True,
            "schematic": True,
            "provenance": {
                "geometry": "IMPORTED",
                "xy_meaning": "infeed_entry_end",
                "calibration": "greensboro-infeed-v1",
                "area": "SUGGESTED",
                "safetyZone": "UNKNOWN",
                "source": "RUN/Conveyor.asc+Mtrchain",
            },
            "safetyZone": "",  # do not invent
            "downstream": "",
            "terminal": False,
            "asMerge": False,
            "devices": devices,
            "motorsMeta": e.get("drives") or [],
            "geometryConfidence": e.get("confidence") or "LOW",
            "drawingPage": e.get("drawing_page") or "",
            # RUN evidence for Control Panel inference (presentation only — not PLC ownership)
            "machineName": e.get("machine_name") or "",
            "ioAddressWord": e.get("io_address_word") or "",
            "controlPanel": "",  # filled by UI only when Machine_Name/CP evidence is clear
            # display_context / EXTERNAL_REFERENCE neighbors complete physical runs
            # (curves/U-turns) but are NOT Autogen/PLC ownership — Apply must skip them.
            # Compact rendering remains available via downstream label for EXTERNAL.
            "displayContext": bool(e.get("display_context")),
            "externalReference": bool(
                e.get("external_reference")
                or (e.get("display_context") and not e.get("plc_owned", True))
            ),
            "scopeClass": (
                "EXTERNAL_REFERENCE"
                if (
                    e.get("external_reference")
                    or (e.get("display_context") and not e.get("plc_owned", True))
                )
                else "LOCAL"
            ),
            "plcOwned": bool(e.get("plc_owned", not e.get("display_context"))),
            "layer": e.get("layer") or "",
            "fieldB": e.get("field_b"),
            "fieldC": e.get("field_c"),
        }
        nodes.append(node)

    # Wires from geometric candidates
    wires: list[dict] = []
    auto_connected = 0
    ambiguous = 0
    inbound_count: dict[str, int] = {}

    for c in candidates:
        level = c.get("classification") or "UNKNOWN"
        if level == "AMBIGUOUS":
            ambiguous += 1
        frm = (c.get("from_conveyor") or "").upper()
        to = (c.get("to_conveyor") or "").upper()
        if frm not in id_by_tag or to not in id_by_tag:
            continue
        if level not in auto_levels:
            # Keep as flagged candidate on nodes for engineer review
            to_node = next(n for n in nodes if n["id"] == id_by_tag[to])
            to_node.setdefault("ambiguousInbound", []).append(
                {
                    "from": c.get("from_conveyor"),
                    "distance": c.get("exit_to_entry_distance"),
                    "classification": level,
                }
            )
            continue
        wid = _uid("wire")
        wires.append(
            {
                "id": wid,
                "from": id_by_tag[frm],
                "to": id_by_tag[to],
                "toPort": "in",
                "physical": True,
                "fromAnchor": "exit",
                "toAnchor": "entry",
                "confidence": "HIGH_CONFIDENCE"
                if "HIGH" in level.upper()
                else "CONFIRMED",
                "distance": c.get("exit_to_entry_distance"),
                "angleDelta": c.get("angle_delta_deg"),
            }
        )
        auto_connected += 1
        inbound_count[to] = inbound_count.get(to, 0) + 1
        # Sync downstream tag
        src = next(n for n in nodes if n["id"] == id_by_tag[frm])
        dst = next(n for n in nodes if n["id"] == id_by_tag[to])
        src["downstream"] = dst["conveyorTag"]
        src["terminal"] = False

    # Overlay proven Mtrchain Timer_Name topology when geometric mate is missing.
    # Same canonical section model as Autogen — never invent edges.
    try:
        from fortna_conveyor_section_model import (
            discover_sections,
            infer_downstream_from_mtrchain,
        )

        section_model = discover_sections(run_dir, machine)
        prefer = section_model.get("preferred_induct") or {}
        mtr_ds = infer_downstream_from_mtrchain(run_dir, preferred_induct=prefer) or {}
        for src_tag, ds in mtr_ds.items():
            ds = str(ds or "").strip()
            if not ds:
                continue
            frm = src_tag.upper()
            to = ds.upper()
            if frm not in id_by_tag or to not in id_by_tag:
                continue
            src = next(n for n in nodes if n["id"] == id_by_tag[frm])
            if (src.get("downstream") or "").strip():
                continue  # geometric mate already won
            dst = next(n for n in nodes if n["id"] == id_by_tag[to])
            src["downstream"] = dst["conveyorTag"]
            src["terminal"] = False
            src.setdefault("topologyProvenance", {
                "rule": "mtrchain_timer_startup_order",
                "confidence": "PROVEN_CROSS_TABLE",
                "source_table": "Mtrchain.asc",
            })
            wires.append(
                {
                    "id": _uid("wire"),
                    "from": id_by_tag[frm],
                    "to": id_by_tag[to],
                    "toPort": "in",
                    "physical": False,
                    "fromAnchor": "exit",
                    "toAnchor": "entry",
                    "confidence": "PROVEN_CROSS_TABLE",
                    "provenance": "mtrchain_timer",
                }
            )
            auto_connected += 1
            inbound_count[to] = inbound_count.get(to, 0) + 1
    except Exception:
        pass

    # Merge detection: 2+ auto inbound → asMerge
    merges_detected = 0
    for tag_u, count in inbound_count.items():
        if count < 2:
            continue
        node = next(n for n in nodes if n["id"] == id_by_tag[tag_u])
        node["asMerge"] = True
        node["inPorts"] = max(2, count)
        node["mergeDetected"] = True
        node["mergeGenSupported"] = count == 2
        if count > 2:
            node["mergeNote"] = "CONFIGURATION REQUIRED / GENERATION NOT YET SUPPORTED"
        merges_detected += 1
        # Normalize ports on inbound wires
        idx = 0
        for w in wires:
            if w["to"] == node["id"]:
                w["toPort"] = f"in{idx}"
                idx += 1

    # Disconnected = no inbound and no outbound wire
    connected_ids = set()
    for w in wires:
        connected_ids.add(w["from"])
        connected_ids.add(w["to"])
    disconnected = sum(1 for n in nodes if n["id"] not in connected_ids)

    graph = {
        "version": 2,
        "physicalLayout": True,
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "source": {
            "run_dir": str(run_dir),
            "machine": machine,
            "builder": "fortna_run_physical_layout",
        },
        # Presentation hint for Transport Build (UI scale only — does not alter RUN geometry)
        "canvasScale": scale,
        "areas": [
            {
                "id": area_id,
                "name": area_name,
                "provenance": "SUGGESTED",
                "nodes": nodes,
                "wires": wires,
            }
        ],
        "activeAreaId": area_id,
        "metrics": {
            "conveyors_discovered": len(equipment),
            "conveyors_placed": placed,
            "conveyors_with_usable_xy": summary.get("usable_xy", placed),
            "conveyors_with_usable_angle": summary.get("usable_angle", 0),
            "conveyors_with_usable_length": summary.get("usable_length_width", 0),
            "motors_discovered": motors_total,
            "vfd_motors": motors_vfd,
            "contactor_motors": motors_contactor,
            "unknown_motors": motors_unknown,
            "auto_connections": auto_connected,
            "ambiguous_connections": ambiguous,
            "disconnected_equipment": disconnected,
            "merges_detected": merges_detected,
            "canvas_scale": scale,
            "geometry_summary": summary,
        },
    }
    return graph


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Auto Build Transport graph from RUN geometry")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--machine", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--stdout-graph", action="store_true", help="Print graph JSON to stdout")
    ap.add_argument(
        "--connect-threshold",
        default="HIGH_CONFIDENCE",
        help="CONFIRMED or HIGH_CONFIDENCE (default)",
    )
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir)
    machine = (args.machine or "").strip()
    if not machine:
        # Discover from RUN identity if possible
        try:
            from fortna_autogen import load_from_run

            inp = load_from_run(run_dir, processor="1756-L83E")
            # project_name like OReillyGreensboro_ORNCCP2
            pn = getattr(inp, "project_name", "") or ""
            m = re.search(r"_([A-Z0-9]+)$", pn)
            machine = m.group(1) if m else "ORNCCP2"
        except Exception:
            machine = "ORNCCP2"

    graph = build_transport_graph(
        run_dir, machine, connect_threshold=args.connect_threshold
    )
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "transport_graph_from_run.json"
        path.write_text(json.dumps(graph, indent=2), encoding="utf-8")
        metrics_path = out / "auto_build_metrics.json"
        metrics_path.write_text(json.dumps(graph.get("metrics") or {}, indent=2), encoding="utf-8")
        print(json.dumps({"ok": True, "graph_path": str(path), "metrics": graph.get("metrics")}, separators=(",", ":")))
    if args.stdout_graph or not args.out:
        if args.stdout_graph:
            print(json.dumps(graph))
        elif not args.out:
            print(json.dumps({"ok": True, "metrics": graph.get("metrics")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

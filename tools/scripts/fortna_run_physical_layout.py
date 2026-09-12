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
    canvas_w: float = 1600.0,
    canvas_h: float = 1000.0,
    pad: float = 80.0,
) -> tuple[dict[str, tuple[float, float]], float]:
    """Map RUN source XY → canvas pixels. Returns tag→(x,y) and scale."""
    pts = [(e["conveyor"].upper(), e["x"], e["y"]) for e in equipment if e.get("x") is not None and e.get("y") is not None]
    if not pts:
        return {}, 1.0
    xs = [p[1] for p in pts]
    ys = [p[2] for p in pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    usable_w = canvas_w - 2 * pad
    usable_h = canvas_h - 2 * pad
    scale = min(usable_w / span_x, usable_h / span_y)
    # Center the layout
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
        node = {
            "id": nid,
            "kind": kind,
            "label": tag,
            "conveyorTag": tag,
            "x": round(cx, 2),
            "y": round(cy, 2),
            "rotation": rot_step,
            "sourceX": sx,
            "sourceY": sy,
            "sourceAngle": angle,
            "length": e.get("length"),
            "width": e.get("width"),
            "equipmentType": e.get("equipment_type") or "",
            "entryAnchor": e.get("entry_anchor"),
            "exitAnchor": e.get("exit_anchor"),
            "physical": True,
            "provenance": {
                "geometry": "IMPORTED",
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

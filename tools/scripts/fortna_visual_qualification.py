#!/usr/bin/env python3
"""Visual + GUI/backend parity qualification package.

Produces:
  visuals/*.svg (+ *.png when renderable)
  geometry/*.json
  gui_backend_parity.json

Backend-only green is insufficient — this package is required evidence.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
import sys

sys.path.insert(0, str(SCRIPTS))


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _svg_to_png_pillow(svg_text: str, out_png: Path, size: tuple[int, int] = (1400, 900)) -> bool:
    """Best-effort raster: draw viewBox paths with Pillow (no cairosvg required)."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return False
    m = re.search(r'viewBox="([^"]+)"', svg_text)
    if not m:
        return False
    try:
        minx, miny, width, height = [float(x) for x in m.group(1).split()]
    except Exception:
        return False
    if width <= 0 or height <= 0:
        return False
    img = Image.new("RGB", size, (11, 18, 32))
    draw = ImageDraw.Draw(img)
    sx = size[0] / width
    sy = size[1] / height
    scale = min(sx, sy)

    def tx(x: float, y: float) -> tuple[float, float]:
        return ((x - minx) * scale, (y - miny) * scale)

    for pm in re.finditer(r'<path[^>]*\sd="([^"]+)"[^>]*/?>', svg_text):
        d = pm.group(1)
        pts: list[tuple[float, float]] = []
        for tok in re.finditer(r"([ML])\s*([-\d.]+)\s+([-\d.]+)", d):
            pts.append(tx(float(tok.group(2)), float(tok.group(3))))
        if len(pts) >= 2:
            draw.line(pts, fill=(168, 180, 196), width=3)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)
    return True


def _curve_geometry_report(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    from fortna_curve_geometry import (
        build_physical_curve_display_path,
        path_self_crosses,
    )

    issues: list[dict[str, Any]] = []
    checked = 0
    for n in nodes:
        kind = str(n.get("renderKind") or n.get("equipmentType") or "").lower()
        if "curve" not in kind and not n.get("sweepDeg"):
            continue
        entry = n.get("entryCanvas")
        exit_ = n.get("exitCanvas")
        if not entry or not exit_:
            continue
        checked += 1
        path = build_physical_curve_display_path(n)
        if not path:
            issues.append({"id": n.get("id") or n.get("conveyorTag"), "code": "CURVE_PATH_UNKNOWN"})
            continue
        # Immutable anchors: first move + final arc endpoint must match entry/exit
        move = next((c for c in path if str(c.get("cmd")).lower() == "move"), None)
        arc = next((c for c in path if str(c.get("cmd")).lower() == "arc"), None)
        if move and (
            abs(float(move.get("x")) - float(entry["x"])) > 0.75
            or abs(float(move.get("y")) - float(entry["y"])) > 0.75
        ):
            issues.append({"id": n.get("id") or n.get("conveyorTag"), "code": "GEOMETRY_ANCHOR_MOVED"})
        if arc and (
            abs(float(arc.get("x")) - float(exit_["x"])) > 0.75
            or abs(float(arc.get("y")) - float(exit_["y"])) > 0.75
        ):
            issues.append({"id": n.get("id") or n.get("conveyorTag"), "code": "GEOMETRY_ANCHOR_MOVED"})
        if path_self_crosses(path):
            issues.append({"id": n.get("id") or n.get("conveyorTag"), "code": "GEOMETRY_SELF_CROSS"})
    status = "FAIL" if any(i["code"].startswith("GEOMETRY_") for i in issues) else (
        "REVIEW" if issues else "PASS"
    )
    return {"status": status, "checked": checked, "issues": issues}


def _endpoint_continuity(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    by_tag: dict[str, dict] = {}
    for n in nodes:
        tag = str(n.get("conveyorTag") or n.get("label") or "").upper()
        if tag:
            by_tag[tag] = n
    gaps: list[dict[str, Any]] = []
    for n in nodes:
        down = str(n.get("downstream") or n.get("downstreamTag") or "").upper()
        if not down or down not in by_tag:
            continue
        a = n.get("exitCanvas")
        b = by_tag[down].get("entryCanvas")
        if not a or not b:
            continue
        dist = math.hypot(float(a["x"]) - float(b["x"]), float(a["y"]) - float(b["y"]))
        if dist > 2.0:
            gaps.append({
                "from": n.get("conveyorTag"),
                "to": down,
                "distance_px": round(dist, 3),
                "code": "GEOMETRY_CONNECTION_GAP",
            })
    return {
        "status": "FAIL" if gaps else "PASS",
        "gaps": gaps,
        "checked_links": len(gaps) + sum(1 for _ in nodes if _.get("downstream")),
    }


def build_gui_backend_parity(run_dir: Path, machine: str) -> dict[str, Any]:
    """Compare canonical backend models to GUI eligibility contracts."""
    from fortna_safety_model import build_safety_model, safety_zone_is_default
    from fortna_hardware_io_model import build_hardware_io_model

    safety = build_safety_model(
        run_dir=run_dir,
        machine=machine,
        engineer_safety_build={
            "zones": [{"name": f"{machine}_ESZone1", "members": [], "engineerEdited": True}]
        },
    )
    c = safety.get("counts") or {}
    found = int(c.get("devices_found") or 0)
    unassigned = int(c.get("unassigned") or 0)
    auto_n = int(c.get("automatically_resolved") or 0)
    eng_n = int(c.get("engineer_assigned") or 0)
    conservation_ok = found == auto_n + eng_n + unassigned

    # GUI available candidates (Default bucket eligible)
    avail = []
    for d in safety.get("devices") or []:
        st = str(d.get("status") or "").upper()
        ref = str(d.get("safetyZoneRef") or "")
        if st == "UNASSIGNED" or d.get("defaultSafety") or safety_zone_is_default({"name": ref}) or not ref:
            avail.append(d.get("name"))

    hw = build_hardware_io_model(run_dir, machine)
    adapters = [
        {
            "rio_name": a.get("rio_name"),
            "eipcfg_name": a.get("eipcfg_name") or a.get("name"),
            "module_count": len(a.get("modules") or []),
        }
        for a in (hw.get("adapters") or [])
    ]
    owner_states = (hw.get("stats") or {}).get("owner_states") or {}
    unresolved_reasons = (hw.get("stats") or {}).get("unresolved_reason_counts") or {}

    failures: list[str] = []
    if not conservation_ok:
        failures.append(
            f"SAFETY_CONSERVATION_FAIL: found={found} auto={auto_n} eng={eng_n} unassigned={unassigned}"
        )
    if found and unassigned != len(avail):
        failures.append(
            f"SAFETY_AVAILABLE_MISMATCH: unassigned={unassigned} gui_available={len(avail)}"
        )
    if not adapters:
        failures.append("HARDWARE_NO_ADAPTERS")

    return {
        "ok": not failures,
        "status": "FAIL" if failures else "PASS",
        "failures": failures,
        "safety": {
            "devices_found": found,
            "unassigned": unassigned,
            "automatically_resolved": auto_n,
            "engineer_assigned": eng_n,
            "gui_available_count": len(avail),
            "conservation_ok": conservation_ok,
        },
        "hardware": {
            "adapters": adapters,
            "owner_states": owner_states,
            "unresolved_reason_counts": unresolved_reasons,
        },
    }


def run_visual_qualification(
    *,
    run_dir: Path,
    machine: str,
    out_dir: Path,
    transport_graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from fortna_schematic_svg_export import export_svg

    out_dir = Path(out_dir)
    visuals = out_dir / "visuals"
    geometry = out_dir / "geometry"
    visuals.mkdir(parents=True, exist_ok=True)
    geometry.mkdir(parents=True, exist_ok=True)

    graph = transport_graph or {"areas": [], "nodes": []}
    # Attempt live transport graph discovery when empty
    if not graph.get("areas") and not graph.get("nodes"):
        try:
            # Prefer physical layout export when present; else empty canvas card.
            from fortna_run_physical_layout import build_physical_layout_from_run

            graph = build_physical_layout_from_run(run_dir, machine) or graph
        except Exception as ex:
            graph = {"areas": [], "nodes": [], "error": str(ex)}

    nodes: list[dict[str, Any]] = []
    for a in graph.get("areas") or []:
        nodes.extend(a.get("nodes") or [])
    if not nodes:
        nodes = list(graph.get("nodes") or [])

    svg = export_svg(graph, title=f"{machine} transportation_full")
    svg_path = visuals / "transportation_full.svg"
    svg_path.write_text(svg, encoding="utf-8")
    png_path = visuals / "transportation_full.png"
    png_ok = _svg_to_png_pillow(svg, png_path)

    # Lite Schematic visual (default Site Forge presentation — centerlines only)
    lite_svg = export_svg(graph, title=f"{machine} transportation_lite", mode="lite")
    lite_svg_path = visuals / "transportation_lite.svg"
    lite_svg_path.write_text(lite_svg, encoding="utf-8")
    lite_png_path = visuals / "transportation_lite.png"
    lite_png_ok = _svg_to_png_pillow(lite_svg, lite_png_path)

    # Per-area SVGs
    area_svgs: list[str] = []
    for a in graph.get("areas") or []:
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(a.get("name") or "area"))[:40]
        g = {"areas": [a]}
        s = export_svg(g, title=f"{machine} {name}")
        p = visuals / f"transportation_{name}.svg"
        p.write_text(s, encoding="utf-8")
        _svg_to_png_pillow(s, visuals / f"transportation_{name}.png")
        area_svgs.append(str(p))

    # Safety / hardware placeholder canvases (model summary cards as PNG)
    try:
        from PIL import Image, ImageDraw, ImageFont

        def _card(path: Path, title: str, lines: list[str]) -> None:
            img = Image.new("RGB", (900, 500), (12, 18, 28))
            dr = ImageDraw.Draw(img)
            dr.text((24, 24), title, fill=(226, 232, 240))
            y = 70
            for ln in lines[:18]:
                dr.text((24, y), ln[:110], fill=(148, 163, 184))
                y += 22
            path.parent.mkdir(parents=True, exist_ok=True)
            img.save(path)

        parity = build_gui_backend_parity(run_dir, machine)
        _card(
            visuals / "safety_build.png",
            f"Safety Build — {machine}",
            [
                f"devices_found={parity['safety']['devices_found']}",
                f"unassigned={parity['safety']['unassigned']}",
                f"gui_available={parity['safety']['gui_available_count']}",
                f"conservation_ok={parity['safety']['conservation_ok']}",
                f"auto={parity['safety']['automatically_resolved']} eng={parity['safety']['engineer_assigned']}",
            ],
        )
        hw_lines = [
            f"adapters={len(parity['hardware']['adapters'])}",
            f"owner_states={parity['hardware']['owner_states']}",
            f"unresolved_reasons={parity['hardware']['unresolved_reason_counts']}",
        ]
        for ad in parity["hardware"]["adapters"]:
            hw_lines.append(
                f"adapter rio_name={ad.get('rio_name')} eipcfg={ad.get('eipcfg_name')} modules={ad.get('module_count')}"
            )
        _card(visuals / "hardware_io.png", f"Hardware I/O — {machine}", hw_lines)
    except Exception as ex:
        parity = build_gui_backend_parity(run_dir, machine)
        _write_json(visuals / "safety_build_error.json", {"error": str(ex)})

    curve = _curve_geometry_report(nodes)
    continuity = _endpoint_continuity(nodes)
    overlap = {"status": "REVIEW", "note": "overlap detector not fully ported; see continuity/curve"}
    _write_json(geometry / "curve_validation.json", curve)
    _write_json(geometry / "endpoint_continuity.json", continuity)
    _write_json(geometry / "overlap_validation.json", overlap)
    _write_json(out_dir / "gui_backend_parity.json", parity)

    geom_fail = curve.get("status") == "FAIL" or continuity.get("status") == "FAIL"
    report = {
        "ok": parity.get("ok") and not geom_fail,
        "status": "FAIL" if (not parity.get("ok") or geom_fail) else "PASS",
        "generated_at": _ts(),
        "machine": machine,
        "visuals": {
            "transportation_full_svg": str(svg_path),
            "transportation_full_png": str(png_path) if png_ok else None,
            "transportation_lite_svg": str(lite_svg_path),
            "transportation_lite_png": str(lite_png_path) if lite_png_ok else None,
            "area_svgs": area_svgs,
            "safety_build_png": str(visuals / "safety_build.png"),
            "hardware_io_png": str(visuals / "hardware_io.png"),
        },
        "render_modes": {
            "default": "lite",
            "detailed_optional": True,
            "note": "Lite is presentation-only; canonical Autogen graph must match Detailed.",
        },
        "geometry": {
            "curve": curve.get("status"),
            "continuity": continuity.get("status"),
            "overlap": overlap.get("status"),
        },
        "gui_backend_parity": parity.get("status"),
        "node_count": len(nodes),
    }
    _write_json(out_dir / "visual_qualification_report.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Visual + GUI/backend parity qualification")
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--machine", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--transport-graph", type=Path, default=None)
    args = ap.parse_args(argv)
    graph = None
    if args.transport_graph and args.transport_graph.is_file():
        graph = json.loads(args.transport_graph.read_text(encoding="utf-8"))
    report = run_visual_qualification(
        run_dir=args.run_dir,
        machine=args.machine,
        out_dir=args.out,
        transport_graph=graph,
    )
    print(json.dumps({"status": report.get("status"), "out": str(args.out), "ok": report.get("ok")}, indent=2))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())

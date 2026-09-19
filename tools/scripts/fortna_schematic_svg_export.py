#!/usr/bin/env python3
"""Export a presentation-only SVG schematic from a Transport physical graph.

Does NOT mutate RUN / workbook / topology / L5X. Evidence aid for drawing pass.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _path_d(path_canvas: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for cmd in path_canvas or []:
        c = str(cmd.get("cmd") or "").lower()
        if c == "move":
            parts.append(f"M {cmd['x']} {cmd['y']}")
        elif c == "line":
            parts.append(f"L {cmd['x']} {cmd['y']}")
        elif c == "arc":
            r = max(1.0, float(cmd.get("radius") or 1))
            sweep = int(cmd["sweep_flag"]) if cmd.get("sweep_flag") is not None else 1
            large = int(cmd.get("large_arc") or 0)
            parts.append(f"A {r} {r} 0 {large} {sweep} {cmd['x']} {cmd['y']}")
    return " ".join(parts)


def _stroke(n: dict[str, Any]) -> float:
    w = float(n.get("width") or 200)
    # graph already in canvas units; approximate scale-free stroke
    is_curve = "curve" in str(n.get("renderKind") or n.get("equipmentType") or "").lower()
    if is_curve:
        arc = next((c for c in (n.get("pathCanvas") or []) if str(c.get("cmd")).lower() == "arc"), None)
        r = float(arc.get("radius") or 0) if arc else 0
        return max(2.5, min(r * 0.55 if r else 4.0, 8.0))
    return max(4.0, min(12.0, w * 0.02))


def _lite_path_d(n: dict[str, Any]) -> str:
    """Presentation-only centerline for Lite Schematic (never writes back to model)."""
    a = n.get("entryCanvas")
    b = n.get("exitCanvas")
    if not a or not b:
        return _path_d(n.get("pathCanvas") or [])
    rk = str(n.get("renderKind") or n.get("equipmentType") or n.get("kind") or "").lower()
    is_curve = "curve" in rk or "conv_right" in rk or "conv_left" in rk or n.get("sweepDeg")
    if not is_curve:
        return f"M {a['x']} {a['y']} L {b['x']} {b['y']}"
    # Prefer proven centerline arc when present
    d = _path_d(n.get("pathCanvas") or [])
    if d and "A " in d:
        return d
    ax, ay = float(a["x"]), float(a["y"])
    bx, by = float(b["x"]), float(b["y"])
    mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy) or 1.0
    bend = min(40.0, length * 0.30)
    sign = 1.0 if float(n.get("sweepDeg") or n.get("sweep_deg") or 90) >= 0 else -1.0
    cx = mx + (-dy / length) * bend * sign
    cy = my + (dx / length) * bend * sign
    return f"M {ax} {ay} Q {cx} {cy} {bx} {by}"


def export_svg(
    graph: dict[str, Any],
    *,
    title: str = "",
    labels: bool = True,
    mode: str = "detailed",
) -> str:
    """Export presentation SVG. mode='lite' → centerline one-line schematic."""
    areas = graph.get("areas") or [{"nodes": graph.get("nodes") or [], "wires": graph.get("wires") or []}]
    nodes = []
    for a in areas:
        nodes.extend(a.get("nodes") or [])
    schematic = [
        n
        for n in nodes
        if n.get("physical") and (n.get("pathCanvas") or n.get("entryCanvas"))
        or (n.get("entryCanvas") and n.get("exitCanvas"))
    ]
    # De-dupe while preserving order
    seen: set[str] = set()
    uniq: list[dict[str, Any]] = []
    for n in schematic:
        key = str(n.get("id") or n.get("conveyorTag") or id(n))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(n)
    schematic = uniq
    xs: list[float] = []
    ys: list[float] = []
    for n in schematic:
        for pt in (n.get("entryCanvas"), n.get("exitCanvas")):
            if pt:
                xs.append(float(pt["x"]))
                ys.append(float(pt["y"]))
        for cmd in n.get("pathCanvas") or []:
            if "x" in cmd and "y" in cmd:
                xs.append(float(cmd["x"]))
                ys.append(float(cmd["y"]))
    if not xs:
        return '<svg xmlns="http://www.w3.org/2000/svg"></svg>'
    pad = 40
    minx, maxx = min(xs) - pad, max(xs) + pad
    miny, maxy = min(ys) - pad, max(ys) + pad
    width = maxx - minx
    height = maxy - miny
    lite = str(mode or "detailed").lower() == "lite"
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{minx:.2f} {miny:.2f} {width:.2f} {height:.2f}" '
        f'width="1400" height="{max(400, int(1400 * height / max(width, 1)))}" data-render-mode="{ "lite" if lite else "detailed" }">',
        '<rect x="100%" y="100%" width="0" height="0"/>',
        f'<rect x="{minx}" y="{miny}" width="{width}" height="{height}" fill="#0b1220"/>',
        f'<text x="{minx + 12}" y="{miny + 18}" fill="#94a3b8" font-size="12" font-family="monospace">{_esc(title)}</text>',
    ]
    if lite:
        parts.append(
            '<defs><marker id="tbArrow" viewBox="0 0 10 10" refX="8" refY="5" '
            'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            '<path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8"/></marker></defs>'
        )
    for n in schematic:
        tag = n.get("conveyorTag") or n.get("label") or "?"
        if lite:
            d = _lite_path_d(n)
            if not d:
                continue
            nid = _esc(str(n.get("id") or tag))
            parts.append(f'<g class="tb-lite-node" data-id="{nid}">')
            parts.append(
                f'<path class="tb-lite-hit" data-id="{nid}" d="{d}" fill="none" '
                f'stroke="transparent" stroke-width="14"/>'
            )
            parts.append(
                f'<path class="tb-lite-belt" data-id="{nid}" d="{d}" fill="none" stroke="#94a3b8" '
                f'stroke-width="2.5" stroke-linecap="round" marker-end="url(#tbArrow)">'
                f"<title>{_esc(tag)}</title></path>"
            )
            if labels and n.get("entryCanvas") and n.get("exitCanvas"):
                mx = (float(n["entryCanvas"]["x"]) + float(n["exitCanvas"]["x"])) / 2
                my = (float(n["entryCanvas"]["y"]) + float(n["exitCanvas"]["y"])) / 2 - 6
                parts.append(
                    f'<text class="tb-lite-label" data-id="{nid}" x="{mx:.2f}" y="{my:.2f}" '
                    f'fill="#cbd5e1" font-size="11" font-family="monospace" '
                    f'text-anchor="middle">{_esc(tag)}</text>'
                )
            parts.append("</g>")
            continue

        d = _path_d(n.get("pathCanvas") or [])
        if not d and n.get("entryCanvas") and n.get("exitCanvas"):
            a, b = n["entryCanvas"], n["exitCanvas"]
            d = f"M {a['x']} {a['y']} L {b['x']} {b['y']}"
        if not d:
            continue
        rk = str(n.get("renderKind") or n.get("equipmentType") or "unknown").lower()
        color = "#67e8f9" if "belt" in rk else ("#c4b5fd" if "curve" in rk else "#38bdf8")
        sw = _stroke(n)
        parts.append(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw:.2f}" '
            f'stroke-linecap="round" stroke-linejoin="round">'
            f"<title>{_esc(tag)}</title></path>"
        )
        if labels and n.get("entryCanvas") and n.get("exitCanvas"):
            mx = (float(n["entryCanvas"]["x"]) + float(n["exitCanvas"]["x"])) / 2
            my = (float(n["entryCanvas"]["y"]) + float(n["exitCanvas"]["y"])) / 2
            parts.append(
                f'<text x="{mx:.2f}" y="{my:.2f}" fill="#e2e8f0" font-size="10" '
                f'font-family="monospace" text-anchor="middle" dominant-baseline="middle" '
                f'stroke="#0a0f14" stroke-width="3" paint-order="stroke">{_esc(tag)}</text>'
            )
            # flow tick
            ex, en = n["exitCanvas"], n["entryCanvas"]
            ang = math.atan2(float(ex["y"]) - float(en["y"]), float(ex["x"]) - float(en["x"]))
            fx = float(ex["x"]) - math.cos(ang) * 4
            fy = float(ex["y"]) - math.sin(ang) * 4
            ax = fx - math.cos(ang - 0.45) * 7
            ay = fy - math.sin(ang - 0.45) * 7
            bx = fx - math.cos(ang + 0.45) * 7
            by = fy - math.sin(ang + 0.45) * 7
            parts.append(
                f'<path d="M {ax:.2f} {ay:.2f} L {fx:.2f} {fy:.2f} L {bx:.2f} {by:.2f}" '
                f'fill="none" stroke="#94a3b8" stroke-width="1.2"/>'
            )
    parts.append("</svg>")
    return "\n".join(parts)


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="")
    args = ap.parse_args(argv)
    graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    svg = export_svg(graph, title=args.title or Path(args.graph).name)
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

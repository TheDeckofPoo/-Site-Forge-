#!/usr/bin/env python3
"""Physical CURVE centerline geometry — mirrors dashboard/transport-build.js.

Contract:
  - Entry/exit anchors are IMMUTABLE (never grown for min radius)
  - Prefer tangent-constrained arc; fall back to chord + signed sweep
  - Symbolic UNKNOWN oblong is a UI-only fallback when anchors cannot resolve

Does not mutate topology / RUN source coordinates.
"""
from __future__ import annotations

import math
from typing import Any

PROVENANCE_PHYSICAL = "PHYSICAL_CENTERLINE"
PROVENANCE_CHORD_SWEEP = "CHORD_SWEEP"
PROVENANCE_TANGENTS = "TANGENTS"


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _unit_from_deg(deg: float) -> tuple[float, float]:
    r = math.radians(float(deg))
    return (math.cos(r), math.sin(r))


def _perp(u: tuple[float, float], ccw: bool) -> tuple[float, float]:
    ux, uy = u
    return (-uy, ux) if ccw else (uy, -ux)


def _line_intersect(
    p1: tuple[float, float],
    d1: tuple[float, float],
    p2: tuple[float, float],
    d2: tuple[float, float],
) -> tuple[float, float] | None:
    det = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(det) < 1e-9:
        return None
    t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / det
    return (p1[0] + t * d1[0], p1[1] + t * d1[1])


def snap_signed_sweep(signed_sweep: float | None, fallback: float = -90.0) -> float:
    sweep = float(signed_sweep) if signed_sweep is not None else fallback
    if not math.isfinite(sweep) or abs(sweep) < 1:
        sweep = fallback
    if abs(abs(sweep) - 90) <= 45:
        return 90.0 if sweep >= 0 else -90.0
    if abs(sweep) > 170:
        return 90.0 if sweep >= 0 else -90.0
    return sweep


def curve_from_chord_and_sweep(
    entry: tuple[float, float],
    exit_pt: tuple[float, float],
    signed_sweep: float,
) -> dict[str, Any] | None:
    """Chord + signed sweep → centerline arc. Anchors immutable."""
    dx = exit_pt[0] - entry[0]
    dy = exit_pt[1] - entry[1]
    chord = math.hypot(dx, dy)
    if chord <= 0.5:
        return None
    sweep = snap_signed_sweep(signed_sweep)
    half = math.radians(abs(sweep)) / 2.0
    sin_half = math.sin(half)
    if sin_half <= 1e-9:
        return None
    r = chord / (2.0 * sin_half)
    mx = (entry[0] + exit_pt[0]) / 2.0
    my = (entry[1] + exit_pt[1]) / 2.0
    d = r * math.cos(half)
    hx, hy = dx / chord, dy / chord
    nx, ny = -hy, hx
    c1 = (mx + nx * d, my + ny * d)
    c2 = (mx - nx * d, my - ny * d)

    def cross_of(c: tuple[float, float]) -> float:
        return (entry[0] - c[0]) * (exit_pt[1] - c[1]) - (entry[1] - c[1]) * (exit_pt[0] - c[0])

    want_positive = sweep > 0
    center = c1 if (cross_of(c1) > 0) == want_positive else c2
    r_cl = math.hypot(entry[0] - center[0], entry[1] - center[1]) or r
    return {
        "entry": {"x": entry[0], "y": entry[1]},
        "exit": {"x": exit_pt[0], "y": exit_pt[1]},
        "center": {"x": center[0], "y": center[1]},
        "radius": r_cl,
        "sweep_deg": sweep,
        "sweep_flag": 1 if sweep > 0 else 0,
        "method": PROVENANCE_CHORD_SWEEP,
    }


def curve_from_tangents(
    entry: tuple[float, float],
    exit_pt: tuple[float, float],
    te: tuple[float, float],
    tx: tuple[float, float],
) -> dict[str, Any] | None:
    """Tangent-constrained centerline arc. Anchors immutable."""
    te_l = math.hypot(te[0], te[1])
    tx_l = math.hypot(tx[0], tx[1])
    if te_l <= 1e-9 or tx_l <= 1e-9:
        return None
    te_u = (te[0] / te_l, te[1] / te_l)
    tx_u = (tx[0] / tx_l, tx[1] / tx_l)
    candidates: list[dict[str, Any]] = []
    for entry_ccw in (True, False):
        for exit_ccw in (True, False):
            ne = _perp(te_u, entry_ccw)
            nx = _perp(tx_u, exit_ccw)
            c = _line_intersect(entry, ne, exit_pt, nx)
            if c is None:
                continue
            r1 = math.hypot(c[0] - entry[0], c[1] - entry[1])
            r2 = math.hypot(c[0] - exit_pt[0], c[1] - exit_pt[1])
            if r1 <= 0.5 or abs(r1 - r2) > max(2.0, 0.08 * r1):
                continue
            rx, ry = entry[0] - c[0], entry[1] - c[1]
            if abs(te_u[0] * rx + te_u[1] * ry) > 0.2 * r1:
                continue
            a0 = math.atan2(entry[1] - c[1], entry[0] - c[0])
            a1 = math.atan2(exit_pt[1] - c[1], exit_pt[0] - c[0])
            delta = a1 - a0
            while delta > math.pi:
                delta -= 2 * math.pi
            while delta < -math.pi:
                delta += 2 * math.pi
            # SVG Y-down: CW tangent from radius = (ry, -rx)
            cw_dot = te_u[0] * ry + te_u[1] * (-rx)
            ccw_dot = te_u[0] * (-ry) + te_u[1] * rx
            if cw_dot >= ccw_dot:
                if delta < 0:
                    delta += 2 * math.pi
                sweep_deg = math.degrees(delta)
                sweep_flag = 1
            else:
                if delta > 0:
                    delta -= 2 * math.pi
                sweep_deg = math.degrees(delta)
                sweep_flag = 0
            if abs(sweep_deg) < 5 or abs(sweep_deg) > 270:
                continue
            candidates.append(
                {
                    "entry": {"x": entry[0], "y": entry[1]},
                    "exit": {"x": exit_pt[0], "y": exit_pt[1]},
                    "center": {"x": c[0], "y": c[1]},
                    "radius": r1,
                    "sweep_deg": sweep_deg,
                    "sweep_flag": sweep_flag,
                    "method": PROVENANCE_TANGENTS,
                    "score": abs(abs(sweep_deg) - 90) + abs(r1 - r2),
                }
            )
    if not candidates:
        return None
    candidates.sort(key=lambda s: float(s.get("score") or 0))
    best = candidates[0]
    best.pop("score", None)
    return best


def solved_to_path(solved: dict[str, Any] | None) -> list[dict[str, Any]] | None:
    if not solved:
        return None
    entry = solved["entry"]
    exit_pt = solved["exit"]
    center = solved["center"]
    sweep = float(solved["sweep_deg"])
    return [
        {"cmd": "move", "x": float(entry["x"]), "y": float(entry["y"])},
        {
            "cmd": "arc",
            "x": float(exit_pt["x"]),
            "y": float(exit_pt["y"]),
            "radius": max(1e-3, float(solved.get("radius") or 1)),
            "sweep_deg": sweep,
            "sweep_flag": int(solved.get("sweep_flag", 1 if sweep > 0 else 0)),
            "large_arc": 1 if abs(sweep) > 180 else 0,
            "center": {"x": float(center["x"]), "y": float(center["y"])},
            "method": solved.get("method") or PROVENANCE_PHYSICAL,
        },
    ]


def resolve_signed_sweep(node: dict[str, Any]) -> float:
    path = node.get("pathCanvas") or []
    existing = next((c for c in path if str(c.get("cmd") or "").lower() == "arc"), None)
    signed: float | None = None
    if existing and existing.get("sweep_deg") is not None:
        signed = _f(existing.get("sweep_deg"))
    elif node.get("sweepDeg") is not None or node.get("sweep_deg") is not None:
        signed = _f(node.get("sweepDeg", node.get("sweep_deg")))
    elif node.get("sourceAngle") is not None and (
        node.get("angleOut") not in (None, "")
        or node.get("runB") is not None
        or node.get("b") is not None
    ):
        exit_bearing = _f(node.get("angleOut"))
        if exit_bearing is None:
            exit_bearing = _f(node.get("runB", node.get("b")))
        d = float(exit_bearing or 0) - float(node.get("sourceAngle") or 0)
        while d > 180:
            d -= 360
        while d < -180:
            d += 360
        signed = -d  # canvas Y-flip
    elif str(node.get("kind") or "") == "conv_left":
        signed = 90.0
    else:
        signed = -90.0
    fallback = 90.0 if str(node.get("kind") or "") == "conv_left" else -90.0
    return snap_signed_sweep(signed, fallback)


def build_physical_curve_display_path(
    node: dict[str, Any],
    *,
    loose: bool = True,
    anchors: dict[str, Any] | None = None,
) -> list[dict[str, Any]] | None:
    """Mirror of JS buildPhysicalCurveDisplayPath — anchors never stretch."""
    anchors = anchors or {}
    entry_d = anchors.get("entry") or node.get("entryCanvas")
    exit_d = anchors.get("exit") or node.get("exitCanvas")
    entry = None
    exit_pt = None
    if isinstance(entry_d, dict) and entry_d.get("x") is not None:
        entry = (float(entry_d["x"]), float(entry_d["y"]))
    if isinstance(exit_d, dict) and exit_d.get("x") is not None:
        exit_pt = (float(exit_d["x"]), float(exit_d["y"]))
    if (entry is None or exit_pt is None) and loose:
        path = node.get("pathCanvas") or []
        if path:
            mv = next((c for c in path if str(c.get("cmd") or "").lower() == "move"), None)
            last = path[-1]
            if entry is None and mv and mv.get("x") is not None:
                entry = (float(mv["x"]), float(mv["y"]))
            if exit_pt is None and last.get("x") is not None:
                exit_pt = (float(last["x"]), float(last["y"]))
    if entry is None or exit_pt is None:
        return None
    chord = math.hypot(exit_pt[0] - entry[0], exit_pt[1] - entry[1])
    if chord <= (0.5 if loose else 2.0):
        return None

    te = tx = None
    sa = _f(node.get("sourceAngle"))
    if sa is not None:
        te = _unit_from_deg(-sa)
    exit_bearing = _f(node.get("angleOut"))
    if exit_bearing is None:
        exit_bearing = _f(node.get("runB", node.get("b")))
    if exit_bearing is not None:
        tx = _unit_from_deg(-exit_bearing)

    solved = None
    if te and tx:
        solved = curve_from_tangents(entry, exit_pt, te, tx)
    if not solved:
        solved = curve_from_chord_and_sweep(entry, exit_pt, resolve_signed_sweep(node))
    return solved_to_path(solved)


def project_shared_topology_joints(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """If A.downstream=B and exits nearly mate, average joint for display only."""
    by_tag: dict[str, dict[str, Any]] = {}
    for n in nodes:
        t = str(n.get("conveyorTag") or n.get("label") or "").strip().upper()
        if t:
            by_tag[t] = n
    overlay: dict[str, dict[str, Any]] = {}
    for a in nodes:
        ds = str(a.get("downstream") or "").strip().upper()
        if not ds or not a.get("exitCanvas"):
            continue
        b = by_tag.get(ds)
        if not b or not b.get("entryCanvas") or b is a:
            continue
        ax = float(a["exitCanvas"]["x"])
        ay = float(a["exitCanvas"]["y"])
        bx = float(b["entryCanvas"]["x"])
        by = float(b["entryCanvas"]["y"])
        gap = math.hypot(ax - bx, ay - by)
        if gap >= 40:
            continue
        mid = {"x": (ax + bx) / 2.0, "y": (ay + by) / 2.0}
        overlay.setdefault(str(a.get("id")), {})["exit"] = mid
        overlay.setdefault(str(b.get("id")), {})["entry"] = mid
    return overlay


def path_self_crosses(path: list[dict[str, Any]] | None, samples: int = 16) -> bool:
    """True if sampled polyline segments intersect non-adjacently (simple self-cross)."""
    if not path:
        return False
    pts: list[tuple[float, float]] = []
    x0 = y0 = None
    for cmd in path:
        c = str(cmd.get("cmd") or "").lower()
        if c == "move":
            x0, y0 = float(cmd["x"]), float(cmd["y"])
            pts.append((x0, y0))
        elif c == "line":
            x0, y0 = float(cmd["x"]), float(cmd["y"])
            pts.append((x0, y0))
        elif c == "arc" and x0 is not None:
            cx = float((cmd.get("center") or {}).get("x", cmd["x"]))
            cy = float((cmd.get("center") or {}).get("y", cmd["y"]))
            x1, y1 = float(cmd["x"]), float(cmd["y"])
            a0 = math.atan2(y0 - cy, x0 - cx)
            a1 = math.atan2(y1 - cy, x1 - cx)
            delta = a1 - a0
            flag = int(cmd.get("sweep_flag", 1))
            if flag == 1:
                if delta < 0:
                    delta += 2 * math.pi
            else:
                if delta > 0:
                    delta -= 2 * math.pi
            r = math.hypot(x0 - cx, y0 - cy) or float(cmd.get("radius") or 1)
            for i in range(1, samples + 1):
                a = a0 + delta * i / samples
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
            x0, y0 = x1, y1

    def orient(a, b, c) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def segments_intersect(p, q, r, s) -> bool:
        o1, o2 = orient(p, q, r), orient(p, q, s)
        o3, o4 = orient(r, s, p), orient(r, s, q)
        if o1 == 0 and o2 == 0 and o3 == 0 and o4 == 0:
            return False
        return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)

    segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    for i in range(len(segs)):
        for j in range(i + 2, len(segs)):
            if i == 0 and j == len(segs) - 1:
                continue
            if segments_intersect(segs[i][0], segs[i][1], segs[j][0], segs[j][1]):
                return True
    return False


def consecutive_curves_form_x(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    path_a: list[dict[str, Any]] | None = None,
    path_b: list[dict[str, Any]] | None = None,
) -> bool:
    """Detect X-cross from endpoint inflation between consecutive curves.

    With immutable anchors, properly joined A.exit≈B.entry should not cross.
    """
    pa = path_a or build_physical_curve_display_path(a)
    pb = path_b or build_physical_curve_display_path(b)
    if not pa or not pb:
        return False
    # Sample midpoints of each arc; if chords cross and joint is shared, flag X
    ae = a.get("entryCanvas") or {}
    ax = a.get("exitCanvas") or {}
    be = b.get("entryCanvas") or {}
    bx = b.get("exitCanvas") or {}
    if not (ae and ax and be and bx):
        return False

    def mid(p0, p1):
        return ((float(p0["x"]) + float(p1["x"])) / 2.0, (float(p0["y"]) + float(p1["y"])) / 2.0)

    def orient(p, q, r) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    a0 = (float(ae["x"]), float(ae["y"]))
    a1 = (float(ax["x"]), float(ax["y"]))
    b0 = (float(be["x"]), float(be["y"]))
    b1 = (float(bx["x"]), float(bx["y"]))
    # Shared joint → chords share endpoint → not an X from inflation
    if math.hypot(a1[0] - b0[0], a1[1] - b0[1]) < 1.0:
        return False
    o1 = orient(a0, a1, b0)
    o2 = orient(a0, a1, b1)
    o3 = orient(b0, b1, a0)
    o4 = orient(b0, b1, a1)
    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)


__all__ = [
    "build_physical_curve_display_path",
    "consecutive_curves_form_x",
    "curve_from_chord_and_sweep",
    "curve_from_tangents",
    "path_self_crosses",
    "project_shared_topology_joints",
    "snap_signed_sweep",
    "solved_to_path",
]

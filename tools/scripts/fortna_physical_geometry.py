#!/usr/bin/env python3
"""Physical conveyor geometry from RUN — Site Forge schematic model.

SOURCE OF TRUTH
---------------
Only RUN / Conveyor.asc fields. Finished PLC is never consulted.

COORDINATE CALIBRATION (Greensboro ORNCCP2 — 2026-09-12)
--------------------------------------------------------
Validated against internal RUN abutments (P312→P314, P320→P322, P136→P138,
P102→P104, P126→P128, …). Engineering print may be used only AFTER this
hypothesis to visually confirm — not to invent topology.

| Field | Meaning | Confidence |
|-------|---------|------------|
| X_cord, Y_cord | **Infeed / ENTRY end** of the conveyor body (NOT footprint center) | HIGH |
| Angle | Flow direction at infeed, degrees **CCW from +X** | HIGH (non-curve) |
| Length | Centerline body length along Angle from infeed (full length, not L/2) | HIGH |
| Width | Cross-belt / frame width | HIGH |
| Type | STRAIGHT / ZEROPRESSURE / BELT / CURVE / … | HIGH |
| Length == -1 on CURVE | Sentinel — linear length unused; use Inside_Radius + tangents | HIGH |
| Inside_Radius | Inner radius of CURVE | HIGH |
| Infeed_Tangent, Discharge_Tangent | Tangent **stub lengths** (drawing units), not topology FKs | HIGH |
| CURVE sweep | Default **90°**; prefer RUN `b` exit bearing when mate-consistent | MEDIUM |
| CURVE turn | Prefer turn/sweep whose exit mates a neighbor; else CW default | MEDIUM |
| CURVE field `b` | Absolute exit bearing deg (mod 360; 450→90); mate-validated | MEDIUM |
| Screen Y | Canvas normalizer flips Y for display | MEDIUM |

Provenance codes: RUN | RUN_EXPLICIT | INFERRED_GEOMETRY | ASSUMPTION | UNKNOWN
"""
from __future__ import annotations

import math
from typing import Any

PROVENANCE_RUN = "RUN"
PROVENANCE_RUN_EXPLICIT = "RUN_EXPLICIT"
PROVENANCE_INFERRED = "INFERRED_GEOMETRY"
PROVENANCE_ASSUMPTION = "ASSUMPTION"
PROVENANCE_UNKNOWN = "UNKNOWN"

CALIBRATION = {
    "version": "greensboro-infeed-v1",
    "documented_at": "2026-09-12",
    "xy_meaning": "infeed_entry_end",
    "xy_confidence": "HIGH",
    "angle_meaning": "flow_direction_deg_ccw_from_plus_x",
    "angle_confidence": "HIGH",
    "length_meaning": "centerline_body_length_from_infeed",
    "length_confidence": "HIGH",
    "curve_length_sentinel": -1,
    "curve_sweep_deg_default": 90.0,
    "curve_sweep_confidence": "MEDIUM",
    "curve_turn_default": "CW",
    "curve_turn_confidence": "MEDIUM",
    "curve_b_meaning": "absolute_exit_bearing_deg_mod_360",
    "curve_b_confidence": "MEDIUM",
    "curve_b_rule": "shortest_delta(Angle,b%360) as mate-scored candidate; else 90+mate",
    "centerline_radius": "Inside_Radius + Width/2",
    "tangents_meaning": "stub_lengths_drawing_units",
    "prior_incorrect_model": "footprint_center_plus_minus_length_over_2",
    "notes": [
        "Prior Auto Build treated XY as footprint center; that produced scattered cards and false mate gaps.",
        "Infeed model yields exit→entry distance 0 for true abutments (P312→P314, P136→P138, …).",
        "CURVE Length=-1; body from Inside_Radius + Infeed_Tangent/Discharge_Tangent stubs + arc.",
        "Field b is absolute exit bearing when mate-consistent; blind b without mate check is unsafe.",
    ],
}


def _f(v: Any) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s or s.upper() in {"N/A", "INVALID", "NONE", "~"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _clean(v: Any) -> str:
    return str(v or "").strip()


def _unit(angle_deg: float) -> tuple[float, float]:
    r = math.radians(angle_deg)
    return (math.cos(r), math.sin(r))


def _norm360(angle_deg: float) -> float:
    return float(angle_deg) % 360.0


def _shortest_delta_deg(angle_in: float, exit_bearing: float) -> float:
    """Signed shortest turn from angle_in to exit_bearing, degrees in (-180, 180]."""
    return (_norm360(exit_bearing) - float(angle_in) + 180.0) % 360.0 - 180.0


def _norm_type(t: str) -> str:
    u = (t or "").strip().upper()
    if u in {"STRAIGHT", "ZEROPRESSURE", "ZERO_PRESSURE", "ZP"}:
        return "STRAIGHT" if u == "STRAIGHT" else "ZEROPRESSURE"
    if u in {"BELT", "TRANSITION", "NOSOVER", "NOSEOVER"}:
        return "BELT"
    if u in {"CURVE", "TRIANG", "TRIANGLE"}:
        return "CURVE"
    return u or "UNKNOWN"


def linear_body(
    x: float,
    y: float,
    length: float,
    angle: float,
    width: float | None = None,
) -> dict[str, Any]:
    """XY = infeed; exit = XY + Length * unit(Angle)."""
    ux, uy = _unit(angle)
    entry = {"x": x, "y": y}
    exit_pt = {"x": x + length * ux, "y": y + length * uy}
    cx = (entry["x"] + exit_pt["x"]) / 2.0
    cy = (entry["y"] + exit_pt["y"]) / 2.0
    return {
        "kind": "linear",
        "entry": entry,
        "exit": exit_pt,
        "center": {"x": cx, "y": cy},
        "angle_in": angle,
        "angle_out": angle,
        "length": length,
        "width": width,
        "path": [
            {"cmd": "move", "x": entry["x"], "y": entry["y"]},
            {"cmd": "line", "x": exit_pt["x"], "y": exit_pt["y"]},
        ],
        "provenance": {
            "xy": PROVENANCE_RUN,
            "angle": PROVENANCE_RUN,
            "length": PROVENANCE_RUN,
            "anchors": PROVENANCE_INFERRED,
            "model": "infeed_origin_v1",
        },
        "confidence": "HIGH",
    }


def _arc_path(
    entry: tuple[float, float],
    angle_in: float,
    *,
    inside_radius: float,
    width: float,
    infeed_tangent: float,
    discharge_tangent: float,
    sweep_deg: float,
    turn_ccw: bool,
) -> dict[str, Any]:
    ux, uy = _unit(angle_in)
    it = max(0.0, float(infeed_tangent or 0.0))
    ot = max(0.0, float(discharge_tangent or 0.0))
    p1 = (entry[0] + it * ux, entry[1] + it * uy)
    r_cl = float(inside_radius) + float(width or 0.0) / 2.0
    if r_cl <= 1e-6:
        # Degenerate — fall back to short linear
        return linear_body(entry[0], entry[1], max(it + ot, width or 200.0), angle_in, width)

    if turn_ccw:
        nx, ny = -uy, ux
        signed_sweep = sweep_deg
    else:
        nx, ny = uy, -ux
        signed_sweep = -sweep_deg

    center = (p1[0] + r_cl * nx, p1[1] + r_cl * ny)
    start = math.degrees(math.atan2(p1[1] - center[1], p1[0] - center[0]))
    end = start + signed_sweep
    p2 = (
        center[0] + r_cl * math.cos(math.radians(end)),
        center[1] + r_cl * math.sin(math.radians(end)),
    )
    angle_out = angle_in + signed_sweep
    dx, dy = _unit(angle_out)
    exit_pt = (p2[0] + ot * dx, p2[1] + ot * dy)

    # Sample arc for SVG polyline fallback (UI can also use arc cmd)
    samples = []
    steps = max(8, int(abs(sweep_deg) / 5))
    for i in range(steps + 1):
        t = i / steps
        a = start + signed_sweep * t
        samples.append(
            {
                "x": center[0] + r_cl * math.cos(math.radians(a)),
                "y": center[1] + r_cl * math.sin(math.radians(a)),
            }
        )

    path = [{"cmd": "move", "x": entry[0], "y": entry[1]}]
    if it > 1e-6:
        path.append({"cmd": "line", "x": p1[0], "y": p1[1]})
    path.append(
        {
            "cmd": "arc",
            "x": p2[0],
            "y": p2[1],
            "radius": r_cl,
            "sweep_deg": signed_sweep,
            "center": {"x": center[0], "y": center[1]},
            "large_arc": 1 if abs(sweep_deg) > 180 else 0,
            "sweep_flag": 0 if turn_ccw else 1,  # SVG sweep: 1 = CW
        }
    )
    if ot > 1e-6:
        path.append({"cmd": "line", "x": exit_pt[0], "y": exit_pt[1]})

    return {
        "kind": "curve",
        "entry": {"x": entry[0], "y": entry[1]},
        "exit": {"x": exit_pt[0], "y": exit_pt[1]},
        "center": {"x": (entry[0] + exit_pt[0]) / 2.0, "y": (entry[1] + exit_pt[1]) / 2.0},
        "arc_center": {"x": center[0], "y": center[1]},
        "angle_in": angle_in,
        "angle_out": angle_out % 360.0,
        "length": it + r_cl * math.radians(abs(sweep_deg)) + ot,
        "width": width,
        "inside_radius": inside_radius,
        "centerline_radius": r_cl,
        "infeed_tangent": it,
        "discharge_tangent": ot,
        "sweep_deg": signed_sweep,
        "turn": "CCW" if turn_ccw else "CW",
        "path": path,
        "arc_samples": samples,
        "provenance": {
            "xy": PROVENANCE_RUN,
            "angle": PROVENANCE_RUN,
            "inside_radius": PROVENANCE_RUN,
            "tangents": PROVENANCE_RUN,
            "sweep": PROVENANCE_ASSUMPTION,
            "turn": PROVENANCE_INFERRED,
            "anchors": PROVENANCE_INFERRED,
            "model": "curve_ir_tangent_v1",
        },
        "confidence": "MEDIUM",
    }


def _mate_score(
    body: dict[str, Any],
    mate_points: list[tuple[float, float]] | None,
    *,
    default_prefer: bool,
) -> float:
    if mate_points:
        ex = body["exit"]
        best = min(math.hypot(ex["x"] - mx, ex["y"] - my) for mx, my in mate_points)
        if best < 5.0:
            return 1000.0 - best
        if best < 50.0:
            return 100.0 - best
        return -best
    return 1.0 if default_prefer else 0.0


def curve_body(
    x: float,
    y: float,
    angle: float,
    *,
    inside_radius: float,
    width: float,
    infeed_tangent: float | None = 0.0,
    discharge_tangent: float | None = 0.0,
    sweep_deg: float = 90.0,
    prefer_turn: str | None = None,
    mate_points: list[tuple[float, float]] | None = None,
    exit_bearing: float | None = None,
) -> dict[str, Any]:
    """Build CURVE body. XY = RUN infeed.

    Candidates:
      - default sweep_deg (90°) CW and CCW
      - if exit_bearing (RUN field b) is present and yields a non-zero shortest
        sweep to b%360, that explicit sweep is also mate-scored
    Winner is chosen by neighbor entry mating when mate_points are provided.
    """
    candidates: list[tuple[float, str, dict[str, Any], str]] = []
    turns = [("CW", False), ("CCW", True)]
    if prefer_turn:
        pref = prefer_turn.upper()
        turns = sorted(turns, key=lambda t: 0 if t[0] == pref else 1)

    default_pref_name = (prefer_turn or "CW").upper()
    for name, ccw in turns:
        body = _arc_path(
            (x, y),
            angle,
            inside_radius=inside_radius,
            width=width,
            infeed_tangent=float(infeed_tangent or 0.0),
            discharge_tangent=float(discharge_tangent or 0.0),
            sweep_deg=sweep_deg,
            turn_ccw=ccw,
        )
        score = _mate_score(body, mate_points, default_prefer=(name == default_pref_name))
        candidates.append((score, name, body, "default_90"))

    # RUN b = absolute exit bearing candidate (mod 360; shortest signed sweep)
    if exit_bearing is not None:
        signed = _shortest_delta_deg(angle, exit_bearing)
        if abs(signed) >= 1e-6:
            ccw = signed > 0
            name = "CCW" if ccw else "CW"
            body = _arc_path(
                (x, y),
                angle,
                inside_radius=inside_radius,
                width=width,
                infeed_tangent=float(infeed_tangent or 0.0),
                discharge_tangent=float(discharge_tangent or 0.0),
                sweep_deg=abs(signed),
                turn_ccw=ccw,
            )
            # Slight preference for RUN-explicit when mate scores tie
            score = _mate_score(body, mate_points, default_prefer=True) + 0.05
            body = dict(body)
            body["provenance"] = dict(body.get("provenance") or {})
            body["provenance"]["sweep"] = PROVENANCE_RUN_EXPLICIT
            body["provenance"]["turn"] = PROVENANCE_RUN_EXPLICIT
            body["exit_bearing"] = _norm360(exit_bearing)
            body["b_signed_sweep"] = signed
            candidates.append((score, name, body, "b_exit_bearing"))

    candidates.sort(key=lambda c: c[0], reverse=True)
    best_score, best_name, best, best_src = candidates[0]
    if best_src == "b_exit_bearing":
        best["confidence"] = "HIGH" if mate_points and best_score >= 50 else "MEDIUM"
        best["provenance"]["sweep"] = PROVENANCE_RUN_EXPLICIT
        best["provenance"]["turn"] = PROVENANCE_RUN_EXPLICIT
    elif mate_points and best_score >= 50:
        best["confidence"] = "HIGH"
        best["provenance"]["turn"] = PROVENANCE_INFERRED
    elif mate_points and best_score > 0:
        best["confidence"] = "MEDIUM"
    else:
        best["confidence"] = "MEDIUM"
        best["provenance"]["turn"] = PROVENANCE_ASSUMPTION
    best["turn_selected"] = best_name
    best["turn_score"] = best_score
    best["sweep_source"] = best_src
    return best


def build_equipment_geometry(row: dict[str, Any], *, mate_entries: list[tuple[float, float]] | None = None) -> dict[str, Any]:
    """Build schematic geometry dict from a Conveyor.asc-like row mapping."""
    typ = _norm_type(_clean(row.get("Type") or row.get("equipment_type") or row.get("equipmentType")))
    x = _f(row.get("X_cord", row.get("x", row.get("sourceX"))))
    y = _f(row.get("Y_cord", row.get("y", row.get("sourceY"))))
    angle = _f(row.get("Angle", row.get("angle", row.get("sourceAngle"))))
    length = _f(row.get("Length", row.get("length")))
    width = _f(row.get("Width", row.get("width")))
    ir = _f(row.get("Inside_Radius", row.get("inside_radius", row.get("insideRadius"))))
    in_t = _f(row.get("Infeed_Tangent", row.get("infeed_tangent", row.get("infeedTangent"))))
    out_t = _f(row.get("Discharge_Tangent", row.get("discharge_tangent", row.get("dischargeTangent"))))
    b_exit = _f(row.get("b", row.get("exit_bearing", row.get("exitBearing"))))

    base = {
        "equipment_type": typ,
        "source": {
            "X_cord": x,
            "Y_cord": y,
            "Angle": angle,
            "Length": length,
            "Width": width,
            "Inside_Radius": ir,
            "Infeed_Tangent": in_t,
            "Discharge_Tangent": out_t,
            "b": b_exit,
            "Type": typ,
        },
        "calibration": CALIBRATION["version"],
    }

    if x is None or y is None or angle is None:
        return {
            **base,
            "kind": "unknown",
            "entry": None,
            "exit": None,
            "path": [],
            "confidence": "LOW",
            "provenance": {"geometry": PROVENANCE_UNKNOWN},
            "issues": ["missing_xy_or_angle"],
        }

    if typ == "CURVE" or (length is not None and length <= 0):
        if ir is None or ir <= 0:
            return {
                **base,
                "kind": "unknown",
                "entry": {"x": x, "y": y},
                "exit": None,
                "path": [],
                "confidence": "LOW",
                "issues": ["curve_missing_inside_radius"],
                "provenance": {"geometry": PROVENANCE_UNKNOWN},
            }
        body = curve_body(
            x,
            y,
            angle,
            inside_radius=ir,
            width=width or 200.0,
            infeed_tangent=in_t or 0.0,
            discharge_tangent=out_t or 0.0,
            mate_points=mate_entries,
            exit_bearing=b_exit,
        )
        return {**base, **body}

    if length is None or length <= 0:
        return {
            **base,
            "kind": "unknown",
            "entry": {"x": x, "y": y},
            "exit": None,
            "path": [],
            "confidence": "LOW",
            "issues": ["missing_length"],
            "provenance": {"geometry": PROVENANCE_UNKNOWN},
        }

    body = linear_body(x, y, length, angle, width)
    if typ == "BELT":
        body["kind"] = "belt"
        body["render_hint"] = "belt_transition"
    elif typ == "ZEROPRESSURE":
        body["kind"] = "linear"
        body["render_hint"] = "zeropressure"
    else:
        body["render_hint"] = "straight"
    return {**base, **body}


def dist(a: dict | None, b: dict | None) -> float:
    if not a or not b:
        return float("inf")
    return math.hypot(float(a["x"]) - float(b["x"]), float(a["y"]) - float(b["y"]))


def classify_mate(exit_pt: dict, entry_pt: dict, width_ref: float) -> str:
    """Geometry-only mate class (never P-number order)."""
    d = dist(exit_pt, entry_pt)
    w = max(float(width_ref or 200.0), 1.0)
    if d <= max(0.75 * w, 50.0):
        return "CONFIRMED"
    if d <= max(2.0 * w, 400.0):
        return "HIGH_CONFIDENCE"
    if d <= max(3.0 * w, 1200.0):
        return "AMBIGUOUS"
    return "UNKNOWN"

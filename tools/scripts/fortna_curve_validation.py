#!/usr/bin/env python3
"""Validate CURVE geometry interpretations against RUN Conveyor.asc (CP2 + CP4).

SOURCE OF TRUTH: RUN only. Does not mutate RUN coordinates. Does not read finished PLC.

Hypotheses tested per curve:
  A) Current model: default 90° sweep; CW/CCW by nearest neighbor entry mate
  B_short) Field b = absolute exit bearing (mod 360); sweep = shortest signed delta
  B_cont) Field b = absolute exit bearing; sweep = continuous (b - Angle), so b>360
          can encode the long way
  C) Field b = absolute exit bearing; both routes to b%360; mate picks direction
  D_mag) Field b = sweep magnitude (deg); mate picks CW/CCW — only scored as fallback

Outputs:
  exports/layout-research/curve_validation.json
  exports/layout-research/curve_validation.md
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import read_asc  # noqa: E402
from fortna_physical_geometry import (  # noqa: E402
    _arc_path,
    curve_body,
    linear_body,
)
from fortna_run_geometry_investigate import (  # noqa: E402
    MECH_TYPES,
    _clean,
    _f,
)

CURVE_TYPES = frozenset({"CURVE", "TRIANG", "TRIANGLE"})
INTERP_ORDER = ("A", "B_short", "B_cont", "C", "D_mag")
TIE_TOL = 1.0  # drawing units
GOOD_ERR = 50.0
EXCELLENT_ERR = 5.0


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm360(a: float) -> float:
    return float(a) % 360.0


def _shortest_delta(angle_in: float, exit_bearing: float) -> float:
    """Signed shortest turn from angle_in to exit_bearing, degrees in (-180, 180]."""
    return (_norm360(exit_bearing) - float(angle_in) + 180.0) % 360.0 - 180.0


def _is_mech_row(row: dict) -> bool:
    typ = _clean(row.get("Type")).upper()
    if typ not in MECH_TYPES and typ not in CURVE_TYPES:
        return False
    tag = _clean(row.get("IO_Name"))
    return bool(tag)


def _row_fields(row: dict) -> dict[str, Any] | None:
    tag = _clean(row.get("IO_Name")).upper()
    typ = _clean(row.get("Type")).upper()
    x = _f(row.get("X_cord"))
    y = _f(row.get("Y_cord"))
    angle = _f(row.get("Angle"))
    if not tag or x is None or y is None or angle is None:
        return None
    return {
        "tag": tag,
        "type": typ,
        "x": x,
        "y": y,
        "angle": angle,
        "width": _f(row.get("Width")) or 200.0,
        "length": _f(row.get("Length")),
        "inside_radius": _f(row.get("Inside_Radius")),
        "infeed_tangent": _f(row.get("Infeed_Tangent")) or 0.0,
        "discharge_tangent": _f(row.get("Discharge_Tangent")) or 0.0,
        "b": _f(row.get("b")),
        "c": _f(row.get("c")),
    }


def load_run(run_dir: Path, site: str) -> dict[str, Any]:
    path = run_dir / "FORTNA" / "Conveyor.asc"
    _h, rows = read_asc(path)
    mech: list[dict[str, Any]] = []
    curves: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not _is_mech_row(row):
            continue
        rec = _row_fields(row)
        if rec is None:
            continue
        if rec["tag"] in seen:
            continue
        seen.add(rec["tag"])
        mech.append(rec)
        ir = rec["inside_radius"]
        if rec["type"] in CURVE_TYPES and ir is not None and ir > 0:
            curves.append(rec)
    return {
        "site": site,
        "run_dir": str(run_dir),
        "conveyor_asc": str(path),
        "mechanical": mech,
        "curves": curves,
    }


def _entry_points(mech: list[dict[str, Any]], exclude: str) -> list[tuple[float, float]]:
    return [(m["x"], m["y"]) for m in mech if m["tag"] != exclude]


def _nearest_entry(
    exit_x: float,
    exit_y: float,
    mech: list[dict[str, Any]],
    self_tag: str,
) -> dict[str, Any]:
    best_d = float("inf")
    best_tag = ""
    best_xy = (None, None)
    for m in mech:
        if m["tag"] == self_tag:
            continue
        d = math.hypot(exit_x - m["x"], exit_y - m["y"])
        if d < best_d:
            best_d = d
            best_tag = m["tag"]
            best_xy = (m["x"], m["y"])
    return {
        "tag": best_tag,
        "distance": best_d if best_d < float("inf") else None,
        "entry_x": best_xy[0],
        "entry_y": best_xy[1],
    }


def _pack_body(body: dict[str, Any], mech: list[dict[str, Any]], self_tag: str) -> dict[str, Any]:
    ex = body["exit"]
    mate = _nearest_entry(ex["x"], ex["y"], mech, self_tag)
    return {
        "calculated_exit_x": ex["x"],
        "calculated_exit_y": ex["y"],
        "calculated_exit_angle": float(body.get("angle_out", 0.0)) % 360.0,
        "sweep_deg": body.get("sweep_deg"),
        "turn": body.get("turn"),
        "nearest_next_tag": mate["tag"],
        "endpoint_error": mate["distance"],
        "nearest_entry_x": mate["entry_x"],
        "nearest_entry_y": mate["entry_y"],
    }


def _arc(
    curve: dict[str, Any],
    *,
    sweep_deg: float,
    turn_ccw: bool,
) -> dict[str, Any]:
    return _arc_path(
        (curve["x"], curve["y"]),
        curve["angle"],
        inside_radius=float(curve["inside_radius"]),
        width=float(curve["width"]),
        infeed_tangent=float(curve["infeed_tangent"]),
        discharge_tangent=float(curve["discharge_tangent"]),
        sweep_deg=abs(float(sweep_deg)),
        turn_ccw=turn_ccw,
    )


def interpret_A(curve: dict[str, Any], mech: list[dict[str, Any]]) -> dict[str, Any]:
    mates = _entry_points(mech, curve["tag"])
    body = curve_body(
        curve["x"],
        curve["y"],
        curve["angle"],
        inside_radius=float(curve["inside_radius"]),
        width=float(curve["width"]),
        infeed_tangent=curve["infeed_tangent"],
        discharge_tangent=curve["discharge_tangent"],
        sweep_deg=90.0,
        mate_points=mates,
    )
    out = _pack_body(body, mech, curve["tag"])
    out["interpretation"] = "A"
    out["detail"] = "default_90_sweep_mate_turn"
    return out


def interpret_B_short(curve: dict[str, Any], mech: list[dict[str, Any]]) -> dict[str, Any] | None:
    b = curve.get("b")
    if b is None:
        return None
    signed = _shortest_delta(curve["angle"], b)
    if abs(signed) < 1e-9:
        return {
            "interpretation": "B_short",
            "detail": "zero_sweep_b_equals_angle",
            "endpoint_error": None,
            "skipped": True,
            "signed_sweep": 0.0,
            "exit_bearing_norm": _norm360(b),
        }
    body = _arc(curve, sweep_deg=abs(signed), turn_ccw=signed > 0)
    out = _pack_body(body, mech, curve["tag"])
    out["interpretation"] = "B_short"
    out["detail"] = "b_exit_bearing_shortest_delta"
    out["signed_sweep"] = signed
    out["exit_bearing_norm"] = _norm360(b)
    out["b_raw"] = b
    return out


def interpret_B_cont(curve: dict[str, Any], mech: list[dict[str, Any]]) -> dict[str, Any] | None:
    b = curve.get("b")
    if b is None:
        return None
    signed = float(b) - float(curve["angle"])
    if abs(signed) < 1e-9:
        return {
            "interpretation": "B_cont",
            "detail": "zero_sweep_continuous",
            "endpoint_error": None,
            "skipped": True,
            "signed_sweep": 0.0,
            "exit_bearing_norm": _norm360(b),
        }
    body = _arc(curve, sweep_deg=abs(signed), turn_ccw=signed > 0)
    out = _pack_body(body, mech, curve["tag"])
    out["interpretation"] = "B_cont"
    out["detail"] = "b_exit_bearing_continuous_delta"
    out["signed_sweep"] = signed
    out["exit_bearing_norm"] = _norm360(b)
    out["b_raw"] = b
    return out


def interpret_C(curve: dict[str, Any], mech: list[dict[str, Any]]) -> dict[str, Any] | None:
    b = curve.get("b")
    if b is None:
        return None
    bn = _norm360(b)
    sw_ccw = (bn - float(curve["angle"])) % 360.0
    sw_cw = -((float(curve["angle"]) - bn) % 360.0)
    best: dict[str, Any] | None = None
    for signed in (sw_ccw, sw_cw):
        if abs(signed) < 1e-9:
            continue
        body = _arc(curve, sweep_deg=abs(signed), turn_ccw=signed > 0)
        cand = _pack_body(body, mech, curve["tag"])
        cand["signed_sweep"] = signed
        if best is None or (cand["endpoint_error"] or 1e18) < (best["endpoint_error"] or 1e18):
            best = cand
    if best is None:
        return {
            "interpretation": "C",
            "detail": "no_nonzero_route_to_b",
            "endpoint_error": None,
            "skipped": True,
            "exit_bearing_norm": bn,
        }
    best["interpretation"] = "C"
    best["detail"] = "b_exit_bearing_mate_chooses_route"
    best["exit_bearing_norm"] = bn
    best["b_raw"] = b
    return best


def interpret_D_mag(curve: dict[str, Any], mech: list[dict[str, Any]]) -> dict[str, Any] | None:
    b = curve.get("b")
    if b is None:
        return None
    mags: list[float] = []
    bn = abs(_norm360(b))
    if bn > 1e-9:
        mags.append(bn)
    ab = abs(float(b))
    if ab > 1e-9:
        # raw |b| capped into (0, 360]
        m = ab if ab <= 360.0 else (ab % 360.0 or 360.0)
        mags.append(m)
    uniq: list[float] = []
    for m in mags:
        if not any(abs(m - u) < 1e-9 for u in uniq):
            uniq.append(m)
    if not uniq:
        return {
            "interpretation": "D_mag",
            "detail": "b_zero_no_magnitude",
            "endpoint_error": None,
            "skipped": True,
        }
    best: dict[str, Any] | None = None
    for mag in uniq:
        for ccw in (False, True):
            body = _arc(curve, sweep_deg=mag, turn_ccw=ccw)
            cand = _pack_body(body, mech, curve["tag"])
            cand["magnitude"] = mag
            cand["turn"] = "CCW" if ccw else "CW"
            if best is None or (cand["endpoint_error"] or 1e18) < (best["endpoint_error"] or 1e18):
                best = cand
    assert best is not None
    best["interpretation"] = "D_mag"
    best["detail"] = "b_as_sweep_magnitude_mate_turn"
    best["b_raw"] = b
    return best


def evaluate_curve(curve: dict[str, Any], mech: list[dict[str, Any]]) -> dict[str, Any]:
    interps: dict[str, Any] = {}
    for name, fn in (
        ("A", interpret_A),
        ("B_short", interpret_B_short),
        ("B_cont", interpret_B_cont),
        ("C", interpret_C),
        ("D_mag", interpret_D_mag),
    ):
        try:
            interps[name] = fn(curve, mech)
        except Exception as exc:  # noqa: BLE001 — research harness
            interps[name] = {
                "interpretation": name,
                "endpoint_error": None,
                "error": str(exc),
                "skipped": True,
            }

    scored = []
    for name in INTERP_ORDER:
        rec = interps.get(name)
        if not rec or rec.get("skipped") or rec.get("endpoint_error") is None:
            continue
        scored.append((name, float(rec["endpoint_error"]), rec))
    scored.sort(key=lambda t: t[1])

    if scored:
        best_name, best_err, best_rec = scored[0]
        tied = [n for n, e, _ in scored if abs(e - best_err) <= TIE_TOL]
    else:
        best_name, best_err, best_rec, tied = None, None, None, []

    return {
        "tag": curve["tag"],
        "type": curve["type"],
        "x": curve["x"],
        "y": curve["y"],
        "angle": curve["angle"],
        "width": curve["width"],
        "inside_radius": curve["inside_radius"],
        "infeed_tangent": curve["infeed_tangent"],
        "discharge_tangent": curve["discharge_tangent"],
        "length": curve["length"],
        "b": curve["b"],
        "c": curve["c"],
        "interpretations": interps,
        "best_interpretation": best_name,
        "best_endpoint_error": best_err,
        "tied_interpretations": tied,
        "best_mate": (best_rec or {}).get("nearest_next_tag"),
        "best_exit_angle": (best_rec or {}).get("calculated_exit_angle"),
        "best_sweep_deg": (best_rec or {}).get("sweep_deg"),
    }


def _err_stats(errors: list[float]) -> dict[str, Any]:
    if not errors:
        return {"n": 0}
    xs = sorted(errors)
    n = len(xs)

    def pct(q: float) -> float:
        return xs[min(n - 1, int(q * (n - 1)))]

    return {
        "n": n,
        "median": round(pct(0.5), 3),
        "p90": round(pct(0.9), 3),
        "mean": round(sum(xs) / n, 3),
        "min": round(xs[0], 3),
        "max": round(xs[-1], 3),
        "good_lt_50": sum(1 for e in xs if e < GOOD_ERR),
        "excellent_lt_5": sum(1 for e in xs if e < EXCELLENT_ERR),
        "good_pct": round(100.0 * sum(1 for e in xs if e < GOOD_ERR) / n, 1),
    }


def summarize(site_results: list[dict[str, Any]]) -> dict[str, Any]:
    win_counts: Counter[str] = Counter()
    sole_wins: Counter[str] = Counter()
    tie_sets: Counter[str] = Counter()
    per_interp_errors: dict[str, list[float]] = defaultdict(list)
    hybrid_errors: list[float] = []
    hybrid_sources: Counter[str] = Counter()
    hybrid_improves = 0
    decisive_b_over_a: list[dict[str, Any]] = []
    decisive_a_over_b: list[dict[str, Any]] = []
    good_fits: list[dict[str, Any]] = []
    bad_fits: list[dict[str, Any]] = []
    classic_90_cw = 0
    classic_90_cw_agree = 0
    zero_sweep_b = 0
    curve_total = 0

    fingerprint_fields = ("tag", "x", "y", "angle", "b", "inside_radius", "infeed_tangent", "discharge_tangent")
    fingerprints: dict[str, set[str]] = defaultdict(set)

    for site in site_results:
        for c in site["curves"]:
            curve_total += 1
            fp = tuple(round(float(c[k]), 4) if isinstance(c.get(k), (int, float)) else c.get(k) for k in fingerprint_fields)
            fingerprints[str(fp)].add(site["site"])

            best = c.get("best_interpretation")
            tied = c.get("tied_interpretations") or []
            if best:
                win_counts[best] += 1
            if len(tied) == 1:
                sole_wins[tied[0]] += 1
            elif len(tied) > 1:
                tie_sets[",".join(sorted(tied))] += 1
                for t in tied:
                    win_counts[f"tie_member:{t}"] += 1

            interps = c.get("interpretations") or {}
            for name in INTERP_ORDER:
                rec = interps.get(name) or {}
                if rec.get("endpoint_error") is not None and not rec.get("skipped"):
                    per_interp_errors[name].append(float(rec["endpoint_error"]))

            a = interps.get("A") or {}
            b = interps.get("B_short") or {}
            a_err = a.get("endpoint_error")
            b_err = None if b.get("skipped") else b.get("endpoint_error")
            # Hybrid H: mate-consistent b (B_short) when better/tied, else A
            if a_err is not None:
                if b_err is not None and b_err <= a_err + TIE_TOL:
                    hybrid_errors.append(float(min(a_err, b_err)))
                    hybrid_sources["B_short" if b_err < a_err - TIE_TOL else "A_or_B_tie"] += 1
                    if b_err < a_err - TIE_TOL:
                        hybrid_improves += 1
                else:
                    hybrid_errors.append(float(a_err))
                    hybrid_sources["A_fallback"] += 1

            if a_err is not None and b_err is not None:
                if b_err + 10.0 < a_err:
                    decisive_b_over_a.append(
                        {
                            "site": site["site"],
                            "tag": c["tag"],
                            "angle": c["angle"],
                            "b": c["b"],
                            "a_err": round(a_err, 3),
                            "b_err": round(b_err, 3),
                            "b_sweep": b.get("sweep_deg"),
                            "mate": b.get("nearest_next_tag"),
                        }
                    )
                if a_err + 10.0 < b_err and a_err < GOOD_ERR:
                    decisive_a_over_b.append(
                        {
                            "site": site["site"],
                            "tag": c["tag"],
                            "angle": c["angle"],
                            "b": c["b"],
                            "a_err": round(a_err, 3),
                            "b_err": round(b_err, 3),
                            "a_turn": a.get("turn"),
                            "mate": a.get("nearest_next_tag"),
                            "b_skipped": bool(b.get("skipped")),
                        }
                    )

            # Classic 90° pattern: |shortest(Angle→b%360)| ≈ 90
            if c.get("b") is not None:
                signed = _shortest_delta(c["angle"], c["b"])
                if abs(signed) < 1e-9:
                    zero_sweep_b += 1
                if abs(abs(signed) - 90.0) < 1.0:
                    classic_90_cw += 1
                    if a_err is not None and b_err is not None and abs(a_err - b_err) <= TIE_TOL:
                        classic_90_cw_agree += 1

            brief = {
                "site": site["site"],
                "tag": c["tag"],
                "angle": c["angle"],
                "b": c["b"],
                "best": best,
                "err": None if c.get("best_endpoint_error") is None else round(c["best_endpoint_error"], 3),
                "mate": c.get("best_mate"),
                "tied": tied,
                "errors": {
                    n: (None if (interps.get(n) or {}).get("endpoint_error") is None
                        else round(float((interps.get(n) or {})["endpoint_error"]), 2))
                    for n in INTERP_ORDER
                    if interps.get(n)
                },
            }
            if c.get("best_endpoint_error") is not None and c["best_endpoint_error"] < EXCELLENT_ERR:
                good_fits.append(brief)
            if c.get("best_endpoint_error") is None or c["best_endpoint_error"] > 200.0:
                bad_fits.append(brief)

    shared_geometry = sum(1 for sites in fingerprints.values() if len(sites) > 1)
    unique_geometry = sum(1 for sites in fingerprints.values() if len(sites) == 1)

    interp_stats = {k: _err_stats(v) for k, v in per_interp_errors.items()}
    hybrid_stats = _err_stats(hybrid_errors)

    preferred_wins: Counter[str] = Counter()
    for site in site_results:
        for c in site["curves"]:
            tied = c.get("tied_interpretations") or []
            if not tied:
                continue
            preference = ["B_short", "C", "A", "B_cont", "D_mag"]
            pick = next((p for p in preference if p in tied), tied[0])
            preferred_wins[pick] += 1

    n_decisive_b = len(decisive_b_over_a)
    n_decisive_a = len(decisive_a_over_b)
    a_stats = interp_stats.get("A") or {"n": 0}

    notes: list[str] = []
    if shared_geometry and unique_geometry == 0:
        notes.append(
            "CP2 and CP4 mechanical CURVE geometry fingerprints are identical "
            "(same plant extract) — not independent multi-site replication."
        )
    if classic_90_cw and classic_90_cw_agree >= max(1, int(0.8 * classic_90_cw)):
        notes.append(
            f"On {classic_90_cw_agree}/{classic_90_cw} classic |shortest(Angle→b%360)|≈90° cases, "
            "A and B_short endpoint errors tie — b is consistent with the current 90° model."
        )
    if n_decisive_b > 0:
        notes.append(
            f"{n_decisive_b} curve(s) where B_short beats A by >10u (non-90° sweep from b), "
            "e.g. P446 shallow turn."
        )
    if n_decisive_a > 0:
        notes.append(
            f"{n_decisive_a} curve(s) where A beats B_short with a good A mate "
            "(e.g. P600F family b=190) — blind b is unsafe; require mate consistency."
        )
    if zero_sweep_b:
        notes.append(
            f"{zero_sweep_b} curve(s) have b≡Angle (shortest) — b uninformative; "
            "fall back to default 90°+mate."
        )
    notes.append(
        f"Hybrid H=mate-min(A, B_short-if-informative): improves {hybrid_improves} vs A, "
        f"never worse by construction; sources={dict(hybrid_sources)}; "
        f"stats={hybrid_stats}."
    )

    # Blind b confidence vs hybrid confidence
    blind_ok = (
        n_decisive_b > 0
        and n_decisive_a == 0
        and (interp_stats.get("B_short") or {}).get("good_lt_50", 0)
        >= a_stats.get("good_lt_50", 0)
    )
    hybrid_ok = hybrid_improves > 0 and (
        classic_90_cw_agree >= max(1, int(0.8 * classic_90_cw)) if classic_90_cw else True
    )

    if blind_ok and unique_geometry > 0:
        confidence = "HIGH"
        supports_b = True
        recommended_rule = (
            "Use b as absolute exit bearing (shortest delta Angle→b%360); "
            "fall back to 90°+mate only when b missing or zero-sweep."
        )
    elif hybrid_ok:
        confidence = "MEDIUM"
        supports_b = True
        recommended_rule = (
            "Treat b as absolute exit bearing candidate (normalize b%360; "
            "signed_sweep=shortest_delta(Angle,b)). Include that sweep as a mate-scored "
            "candidate alongside default 90° CW/CCW. Prefer b when mate-consistent; "
            "otherwise fall back to 90°+mate. Blind b without mate check is NOT safe "
            f"({n_decisive_a} counterexamples)."
        )
    else:
        confidence = "LOW"
        supports_b = False
        recommended_rule = (
            "Keep current default 90° + mate turn selection; do not bind b yet."
        )

    recommend_patch = confidence in {"MEDIUM", "HIGH"}
    overall_winner = "H_hybrid" if recommend_patch else (
        preferred_wins.most_common(1)[0][0] if preferred_wins else "A"
    )

    return {
        "curve_evaluations": curve_total,
        "win_counts_raw_best": dict(win_counts),
        "sole_wins": dict(sole_wins),
        "tie_sets": dict(tie_sets),
        "preferred_wins_tie_break": dict(preferred_wins),
        "overall_winner_preferred": overall_winner,
        "interpretation_error_stats": interp_stats,
        "hybrid_error_stats": hybrid_stats,
        "hybrid_sources": dict(hybrid_sources),
        "hybrid_improves_vs_a": hybrid_improves,
        "classic_90_count": classic_90_cw,
        "classic_90_a_b_agree": classic_90_cw_agree,
        "zero_sweep_b_count": zero_sweep_b,
        "decisive_b_short_over_a": decisive_b_over_a,
        "decisive_a_over_b_short": decisive_a_over_b,
        "geometry_fingerprint_shared_across_sites": shared_geometry,
        "geometry_fingerprint_unique": unique_geometry,
        "b_exit_bearing_confidence": confidence,
        "b_exit_bearing_supported": supports_b,
        "evidence_notes": notes,
        "recommended_rule": recommended_rule,
        "recommend_patch": recommend_patch,
        "good_fit_examples": good_fits[:25],
        "bad_fit_examples": bad_fits[:25],
        "svg_y_flip_note": (
            "fortna_run_physical_layout.py projects pathCanvas with screen Y flip "
            "(cy - (y - sourceY)*scale) and inverts SVG sweep_flag for arc commands. "
            "Plant-space signed_sweep from this validator must stay unflipped; only the "
            "canvas projection layer inverts sweep_flag."
        ),
    }


def render_md(payload: dict[str, Any]) -> str:
    s = payload["summary"]
    lines = [
        "# CURVE geometry validation (RUN Conveyor.asc)",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "Raw RUN coordinates were **not** modified. Finished PLC was **not** consulted.",
        "",
        "## Winning rule",
        "",
        f"- **Preferred winner:** `{s['overall_winner_preferred']}`",
        f"- **b-as-exit-bearing confidence:** **{s['b_exit_bearing_confidence']}**",
        f"- **Supported?** {s['b_exit_bearing_supported']}",
        f"- **Recommend Site Forge patch?** {s['recommend_patch']}",
        f"- **Hybrid improves vs A:** {s.get('hybrid_improves_vs_a')}",
        "",
        s["recommended_rule"],
        "",
        "### Evidence notes",
        "",
    ]
    for n in s["evidence_notes"]:
        lines.append(f"- {n}")
    if not s["evidence_notes"]:
        lines.append("- (none)")

    lines += [
        "",
        "## Population",
        "",
        f"- Curve evaluations (CP2+CP4): **{s['curve_evaluations']}**",
        f"- Shared geometry fingerprints across sites: {s['geometry_fingerprint_shared_across_sites']}",
        f"- Unique geometry fingerprints: {s['geometry_fingerprint_unique']}",
        f"- Classic |Δ|≈90° from Angle→b: {s['classic_90_count']} (A/B agree {s['classic_90_a_b_agree']})",
        f"- b≡Angle zero-sweep cases: {s['zero_sweep_b_count']}",
        "",
        "### Preferred wins (tie-break order B_short > C > A > B_cont > D_mag)",
        "",
        "```",
        json.dumps(s["preferred_wins_tie_break"], indent=2),
        "```",
        "",
        "### Endpoint-error stats by interpretation",
        "",
        "| Interp | n | median | p90 | good&lt;50 | excellent&lt;5 | good% |",
        "|--------|---|--------|-----|-----------|----------------|-------|",
    ]
    for name in INTERP_ORDER:
        st = s["interpretation_error_stats"].get(name) or {"n": 0}
        if not st.get("n"):
            lines.append(f"| {name} | 0 | — | — | — | — | — |")
            continue
        lines.append(
            f"| {name} | {st['n']} | {st['median']} | {st['p90']} | "
            f"{st['good_lt_50']} | {st['excellent_lt_5']} | {st['good_pct']}% |"
        )
    st = s.get("hybrid_error_stats") or {"n": 0}
    if st.get("n"):
        lines.append(
            f"| H_hybrid | {st['n']} | {st['median']} | {st['p90']} | "
            f"{st['good_lt_50']} | {st['excellent_lt_5']} | {st['good_pct']}% |"
        )

    lines += ["", "## Decisive B_short over A (non-90° signal)", ""]
    if s["decisive_b_short_over_a"]:
        for ex in s["decisive_b_short_over_a"][:15]:
            lines.append(
                f"- **{ex['site']} {ex['tag']}** Angle={ex['angle']} b={ex['b']}: "
                f"A_err={ex['a_err']} → B_err={ex['b_err']} (sweep={ex['b_sweep']}) mate {ex['mate']}"
            )
    else:
        lines.append("- None")

    lines += ["", "## Decisive A over B_short (fallback needed)", ""]
    if s["decisive_a_over_b_short"]:
        for ex in s["decisive_a_over_b_short"][:15]:
            lines.append(
                f"- **{ex['site']} {ex['tag']}** Angle={ex['angle']} b={ex['b']}: "
                f"A_err={ex['a_err']} B_err={ex['b_err']} skipped={ex.get('b_skipped')}"
            )
    else:
        lines.append("- None")

    lines += ["", "## Good fits (best endpoint_error < 5)", ""]
    for ex in s["good_fit_examples"][:12]:
        lines.append(
            f"- **{ex['site']} {ex['tag']}** Angle={ex['angle']} b={ex['b']} "
            f"best={ex['best']} err={ex['err']} mate={ex['mate']} tied={ex['tied']}"
        )

    lines += ["", "## Poor fits (best endpoint_error > 200 or unscored)", ""]
    for ex in s["bad_fit_examples"][:12]:
        lines.append(
            f"- **{ex['site']} {ex['tag']}** Angle={ex['angle']} b={ex['b']} "
            f"best={ex['best']} err={ex['err']} errors={ex['errors']}"
        )

    lines += [
        "",
        "## Recommended Site Forge change",
        "",
    ]
    if s["recommend_patch"]:
        lines += [
            "Patch `fortna_physical_geometry.py`:",
            "",
            "1. When Conveyor.asc field `b` is present, treat it as an **absolute exit bearing "
            "candidate** (normalize `b % 360`, including values like 450→90).",
            "2. `signed_sweep = shortest_delta(Angle, b%360)`.",
            "3. Score that candidate via neighbor mating **alongside** default 90° CW/CCW.",
            "4. If `|signed_sweep| < ε` or `b` missing → only the 90°+mate path "
            "(`ASSUMPTION` / `INFERRED_GEOMETRY`).",
            "5. If the b-derived candidate wins the mate score → apply it with "
            "`provenance.sweep/turn = RUN_EXPLICIT`.",
            "6. Do **not** invent site-specific constants; do not bind continuous b−Angle "
            "(B_cont underperforms B_short).",
        ]
    else:
        lines.append("No patch — evidence for binding `b` is too weak.")

    lines += [
        "",
        "## SVG Y-flip / pathCanvas",
        "",
        s["svg_y_flip_note"],
        "",
        "## Sites",
        "",
    ]
    for site in payload["sites"]:
        lines.append(
            f"- **{site['site']}**: mechanical={site['mechanical_count']}, "
            f"curves_scored={site['curve_count']}, asc=`{site['conveyor_asc']}`"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="exports/layout-research")
    ap.add_argument(
        "--cp2-run",
        default=str(ROOT / "workspace" / "active" / "RUN"),
    )
    ap.add_argument(
        "--cp4-run",
        default=str(ROOT / "workspace" / "cp4-run" / "RUN"),
    )
    args = ap.parse_args(argv)
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)

    sites_in = [
        ("ORNCCP2", Path(args.cp2_run)),
        ("ORNCCP4", Path(args.cp4_run)),
    ]
    site_payloads = []
    for name, run_dir in sites_in:
        if not (run_dir / "FORTNA" / "Conveyor.asc").is_file():
            print(f"SKIP missing Conveyor.asc under {run_dir}")
            continue
        loaded = load_run(run_dir, name)
        scored = [evaluate_curve(c, loaded["mechanical"]) for c in loaded["curves"]]
        site_payloads.append(
            {
                "site": name,
                "run_dir": loaded["run_dir"],
                "conveyor_asc": loaded["conveyor_asc"],
                "mechanical_count": len(loaded["mechanical"]),
                "curve_count": len(scored),
                "curves": scored,
            }
        )

    summary = summarize(site_payloads)
    payload = {
        "generated_at": _ts(),
        "calibration_reference": "greensboro-infeed-v1",
        "constraints": {
            "run_coords_mutated": False,
            "finished_plc_used": False,
            "decoder": "generic",
        },
        "hypotheses": {
            "A": "default 90° sweep; CW/CCW by nearest neighbor entry mate",
            "B_short": "b = absolute exit bearing (mod 360); shortest signed sweep",
            "B_cont": "b = absolute exit bearing; continuous sweep = b - Angle",
            "C": "b = absolute exit bearing; mate chooses CW vs CCW route to b%360",
            "D_mag": "b = sweep magnitude; mate chooses turn",
        },
        "sites": [
            {
                "site": s["site"],
                "run_dir": s["run_dir"],
                "conveyor_asc": s["conveyor_asc"],
                "mechanical_count": s["mechanical_count"],
                "curve_count": s["curve_count"],
                "curves": s["curves"],
            }
            for s in site_payloads
        ],
        "summary": summary,
    }

    json_path = out / "curve_validation.json"
    md_path = out / "curve_validation.md"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_md(payload), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(
        f"winner={summary['overall_winner_preferred']} "
        f"b_confidence={summary['b_exit_bearing_confidence']} "
        f"patch={summary['recommend_patch']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Group RUN mechanical conveyors into display runs (geometry only).

Groups via endpoint proximity + heading continuity + type family + layer.
Does NOT invent PLC topology / downstream. Does NOT mutate RUN coordinates.

Outputs: exports/layout-research/physical_runs.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import read_asc  # noqa: E402
from fortna_physical_geometry import build_equipment_geometry, dist  # noqa: E402
from fortna_run_geometry_investigate import (  # noqa: E402
    _clean,
    _f,
    _is_mech_conveyor,
)

TYPE_FAMILY = {
    "STRAIGHT": "LINEAR",
    "ZEROPRESSURE": "LINEAR",
    "ZP": "LINEAR",
    "ZERO_PRESSURE": "LINEAR",
    "BELT": "BELT",
    "CURVE": "CURVE",
    "TRIANG": "CURVE",
    "TRIANGLE": "CURVE",
}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ang_delta(a: float | None, b: float | None) -> float:
    if a is None or b is None:
        return 999.0
    d = abs(float(a) - float(b)) % 360.0
    return min(d, 360.0 - d)


def _family(t: str) -> str:
    return TYPE_FAMILY.get((t or "").upper(), (t or "OTHER").upper())


def load_equip(run_dir: Path) -> list[dict[str, Any]]:
    _h, rows = read_asc(run_dir / "FORTNA" / "Conveyor.asc")
    raw: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        if not _is_mech_conveyor(r):
            continue
        tag = _clean(r.get("IO_Name")).upper()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        raw.append(r)
    mates = [
        (_f(r.get("X_cord")), _f(r.get("Y_cord")))
        for r in raw
        if _f(r.get("X_cord")) is not None and _f(r.get("Y_cord")) is not None
    ]
    mates_f = [(x, y) for x, y in mates if x is not None and y is not None]
    out: list[dict[str, Any]] = []
    for r in raw:
        g = build_equipment_geometry(r, mate_entries=mates_f)
        if not g.get("entry") or not g.get("exit"):
            continue
        ang_out = g.get("angle_out")
        if ang_out is None:
            ang_out = _f(r.get("Angle"))
        out.append(
            {
                "tag": _clean(r.get("IO_Name")).upper(),
                "type": _clean(r.get("Type")).upper(),
                "family": _family(_clean(r.get("Type"))),
                "layer": _clean(r.get("Layer")) or "0",
                "x": _f(r.get("X_cord")),
                "y": _f(r.get("Y_cord")),
                "angle": _f(r.get("Angle")),
                "angle_out": float(ang_out) % 360.0 if ang_out is not None else None,
                "width": _f(r.get("Width")) or 200.0,
                "length": _f(r.get("Length")),
                "entry": g["entry"],
                "exit": g["exit"],
                "kind": g.get("kind"),
                "sweep": g.get("sweep_deg"),
            }
        )
    return out


def _mate_ok(a: dict, b: dict) -> tuple[bool, float, str]:
    """Return (ok, distance, confidence) for a.exit → b.entry as serial continuation."""
    d = dist(a["exit"], b["entry"])
    w = max(float(a.get("width") or 200), float(b.get("width") or 200))
    # Heading continuity: a.angle_out vs b.angle_in
    head = _ang_delta(a.get("angle_out"), b.get("angle"))
    # Curves may turn — allow larger heading jump when either is CURVE
    head_lim = 35.0 if a["family"] == "CURVE" or b["family"] == "CURVE" else 25.0
    layer_ok = (a.get("layer") or "0") == (b.get("layer") or "0")
    if not layer_ok:
        return False, d, "DIFFERENT_LAYER"
    if d <= max(0.75 * w, 50) and head <= head_lim:
        return True, d, "CONFIRMED"
    if d <= max(2.0 * w, 400) and head <= head_lim + 10:
        return True, d, "HIGH"
    if d <= max(3.0 * w, 900) and head <= head_lim + 20:
        return True, d, "AMBIGUOUS"
    return False, d, "NONE"


def build_runs(equip: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_tag = {e["tag"]: e for e in equip}
    # Best downstream per equipment
    down: dict[str, tuple[str, float, str]] = {}
    up_count: dict[str, int] = defaultdict(int)
    for a in equip:
        best: tuple[str, float, str] | None = None
        for b in equip:
            if a["tag"] == b["tag"]:
                continue
            ok, d, conf = _mate_ok(a, b)
            if not ok:
                continue
            if best is None or d < best[1]:
                best = (b["tag"], d, conf)
        if best:
            down[a["tag"]] = best
            up_count[best[0]] += 1

    # Resolve conflicts: if multiple upstream claim same target, keep nearest
    claimed_by: dict[str, list[tuple[str, float, str]]] = defaultdict(list)
    for src, (dst, d, conf) in down.items():
        claimed_by[dst].append((src, d, conf))
    final_down: dict[str, tuple[str, float, str]] = {}
    used_dst: set[str] = set()
    # Prefer CONFIRMED/HIGH and shorter distance
    conf_rank = {"CONFIRMED": 0, "HIGH": 1, "AMBIGUOUS": 2}
    candidates = sorted(
        ((s, d, dist_, c) for s, (d, dist_, c) in down.items()),
        key=lambda t: (conf_rank.get(t[3], 9), t[2]),
    )
    for src, dst, dist_, conf in candidates:
        if src in final_down:
            continue
        if dst in used_dst:
            continue
        # avoid branching for display runs — one-in one-out
        final_down[src] = (dst, dist_, conf)
        used_dst.add(dst)

    # Walk chains from heads (nodes with no selected upstream)
    has_up = {dst for dst, _, _ in final_down.values()}
    heads = [e["tag"] for e in equip if e["tag"] not in has_up]
    visited: set[str] = set()
    runs: list[dict[str, Any]] = []

    def walk(start: str) -> dict[str, Any]:
        ordered = [start]
        confs: list[str] = []
        gaps: list[float] = []
        visited.add(start)
        cur = start
        while cur in final_down:
            nxt, d, conf = final_down[cur]
            if nxt in visited:
                break
            ordered.append(nxt)
            confs.append(conf)
            gaps.append(d)
            visited.add(nxt)
            cur = nxt
        members = [by_tag[t] for t in ordered if t in by_tag]
        types = sorted({m["type"] for m in members})
        families = sorted({m["family"] for m in members})
        if not confs:
            run_conf = "SINGLE"
        elif all(c == "CONFIRMED" for c in confs):
            run_conf = "CONFIRMED"
        elif all(c in {"CONFIRMED", "HIGH"} for c in confs):
            run_conf = "HIGH"
        else:
            run_conf = "AMBIGUOUS"
        xs = [m["x"] for m in members if m.get("x") is not None]
        ys = [m["y"] for m in members if m.get("y") is not None]
        return {
            "id": f"run_{ordered[0]}_{ordered[-1]}",
            "member_count": len(ordered),
            "ordered_tags": ordered,
            "entry_tag": ordered[0],
            "exit_tag": ordered[-1],
            "types": types,
            "families": families,
            "layer": members[0]["layer"] if members else "",
            "connection_confidence": run_conf,
            "edge_confidences": confs,
            "edge_endpoint_distances": [round(g, 3) for g in gaps],
            "bbox": {
                "min_x": min(xs) if xs else None,
                "max_x": max(xs) if xs else None,
                "min_y": min(ys) if ys else None,
                "max_y": max(ys) if ys else None,
            },
            "has_curve": any(m["family"] == "CURVE" for m in members),
        }

    for h in sorted(heads):
        if h in visited:
            continue
        runs.append(walk(h))
    # orphans not visited (cycles) — break arbitrarily
    for e in equip:
        if e["tag"] not in visited:
            runs.append(walk(e["tag"]))

    runs.sort(key=lambda r: (-r["member_count"], r["ordered_tags"][0]))
    return runs


def analyze_site(run_dir: Path, site: str) -> dict[str, Any]:
    equip = load_equip(run_dir)
    runs = build_runs(equip)
    return {
        "site": site,
        "run_dir": str(run_dir),
        "equipment_count": len(equip),
        "run_count": len(runs),
        "runs_with_curve": sum(1 for r in runs if r["has_curve"]),
        "multi_member_runs": sum(1 for r in runs if r["member_count"] >= 2),
        "confidence_counts": {
            k: sum(1 for r in runs if r["connection_confidence"] == k)
            for k in ("CONFIRMED", "HIGH", "AMBIGUOUS", "SINGLE")
        },
        "runs": runs,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="exports/layout-research")
    ap.add_argument("--cp2-run", default="workspace/active/RUN")
    ap.add_argument("--cp4-run", default="workspace/cp4-run/RUN")
    ap.add_argument("--skip-cp4", action="store_true")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {
        "generated_at": _ts(),
        "calibration": "greensboro-infeed-v1",
        "constraints": {
            "run_coords_mutated": False,
            "finished_plc_used": False,
            "plc_topology_invented": False,
        },
        "method": {
            "grouping": "exit→entry proximity + heading continuity + layer; one-in/one-out display chains",
            "note": "Display runs only — not Autogen downstream",
        },
        "sites": {},
    }

    cp2 = Path(args.cp2_run)
    if not cp2.is_absolute():
        cp2 = ROOT / cp2
    if (cp2 / "FORTNA" / "Conveyor.asc").exists():
        results["sites"]["ORNCCP2"] = analyze_site(cp2, "ORNCCP2")

    if not args.skip_cp4:
        cp4 = Path(args.cp4_run)
        if not cp4.is_absolute():
            cp4 = ROOT / cp4
        if (cp4 / "FORTNA" / "Conveyor.asc").exists():
            results["sites"]["ORNCCP4"] = analyze_site(cp4, "ORNCCP4")

    (out / "physical_runs.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    summary = {
        s: {
            "equipment": v["equipment_count"],
            "runs": v["run_count"],
            "multi": v["multi_member_runs"],
            "with_curve": v["runs_with_curve"],
            "conf": v["confidence_counts"],
            "top": [
                {"n": r["member_count"], "tags": r["ordered_tags"][:8], "conf": r["connection_confidence"]}
                for r in v["runs"][:5]
            ],
        }
        for s, v in results["sites"].items()
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

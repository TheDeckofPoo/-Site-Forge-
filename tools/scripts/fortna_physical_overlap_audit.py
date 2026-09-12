#!/usr/bin/env python3
"""Audit nearly-identical physical geometry among imported conveyors.

Does NOT move equipment. Classifies overlaps as:
  SAME_PHYSICAL_EQUIPMENT | PARALLEL_EQUIPMENT | PARENT_CHILD |
  VALID_OVERLAP | SUSPECT_GEOMETRY | UNKNOWN

SOURCE: RUN geometry only (infeed-origin model). Finished PLC never consulted.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import read_asc  # noqa: E402
from fortna_physical_geometry import build_equipment_geometry, dist  # noqa: E402
from fortna_run_geometry_investigate import (  # noqa: E402
    _clean,
    _f,
    _is_mech_conveyor,
    _load_word_map,
    _row_on_controller,
)

OVERLAP_CLASSES = (
    "SAME_PHYSICAL_EQUIPMENT",
    "PARALLEL_EQUIPMENT",
    "PARENT_CHILD",
    "VALID_OVERLAP",
    "SUSPECT_GEOMETRY",
    "UNKNOWN",
)


def _load_mech(run_dir: Path, machine: str) -> list[dict]:
    headers, rows = read_asc(run_dir / "FORTNA" / "Conveyor.asc")
    # Prefer machine overlay if present for row preference — still plant rows
    word_map = _load_word_map(run_dir)
    by: dict[str, dict] = {}
    for r in rows:
        if not _is_mech_conveyor(r):
            continue
        name = _clean(r.get("IO_Name")).upper()
        if not name:
            continue
        if machine and not _row_on_controller(r, machine, word_map):
            # Keep for plant-wide audit when machine filter yields few — still
            # prefer scoped when Machine_Name/IO match
            pass
        if name not in by:
            by[name] = r
    # If machine scoping via autogen tags available, prefer those
    try:
        from fortna_autogen import load_from_run

        inp = load_from_run(run_dir, processor="1756-L83E")
        tags = {c.upper() for c in (getattr(inp, "conveyor_tags", None) or [])}
        if not tags and hasattr(inp, "conveyors"):
            tags = {str(getattr(c, "name", c) or "").upper() for c in (inp.conveyors or [])}
        # Also collect from equipment plan style
        if not tags:
            for attr in ("machines", "equipment"):
                pass
    except Exception:
        tags = set()

    # Fallback: use geometry investigate target set
    try:
        from fortna_run_geometry_investigate import investigate

        tmp = run_dir.parent / "_overlap_audit_tmp"
        result = investigate(run_dir, machine, tmp)
        tags = {e["conveyor"].upper() for e in (result.get("equipment") or [])}
    except Exception:
        tags = set(by.keys())

    out = []
    for tag in sorted(tags):
        r = by.get(tag)
        if not r:
            continue
        geom = build_equipment_geometry(r)
        out.append(
            {
                "tag": tag,
                "type": _clean(r.get("Type")).upper(),
                "x": _f(r.get("X_cord")),
                "y": _f(r.get("Y_cord")),
                "length": _f(r.get("Length")),
                "width": _f(r.get("Width")),
                "angle": _f(r.get("Angle")),
                "entry": geom.get("entry"),
                "exit": geom.get("exit"),
                "machine_name": _clean(r.get("Machine_Name")),
                "drawing_page": _clean(r.get("Electrical Drawing Page No.")),
            }
        )
    return out


def _angle_delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    d = abs(float(a) - float(b)) % 360.0
    return min(d, 360.0 - d)


def _classify_pair(a: dict, b: dict, entry_d: float, exit_d: float, mid_d: float) -> str:
    """Heuristic classification — never invent topology."""
    same_xy = (
        a.get("x") is not None
        and b.get("x") is not None
        and abs(float(a["x"]) - float(b["x"])) < 1.0
        and abs(float(a["y"]) - float(b["y"])) < 1.0
    )
    ang_d = _angle_delta(a.get("angle"), b.get("angle"))
    same_angle = ang_d is not None and ang_d < 1.0
    parallel_angle = ang_d is not None and ang_d < 8.0
    ta, tb = a["tag"], b["tag"]
    wref = max(float(a.get("width") or 200), float(b.get("width") or 200))

    # Parent/child naming: P136 / P136A
    if ta.rstrip("ABCDEFGH") == tb.rstrip("ABCDEFGH") and ta != tb:
        if (same_angle or parallel_angle) and (entry_d < 50 or exit_d < 50 or mid_d < 80):
            return "PARENT_CHILD"

    # Same physical body: nearly identical entry+exit (or identical XY+angle)
    if entry_d < 5 and exit_d < 5 and same_angle:
        return "SAME_PHYSICAL_EQUIPMENT"
    if same_xy and same_angle and mid_d < 25:
        return "SAME_PHYSICAL_EQUIPMENT"

    # Parallel equipment: similar heading, close midpoints, distinct ends
    if parallel_angle and mid_d < wref * 1.5:
        if entry_d > 20 and exit_d > 20:
            return "PARALLEL_EQUIPMENT"

    # Valid mate-like proximity (one end coincides, other far — curve→straight)
    if min(entry_d, exit_d) < 25 and max(entry_d, exit_d) > max(wref, 200):
        return "VALID_OVERLAP"

    # Bodies nearly stacked but not identical — suspect RUN geometry
    if mid_d < wref * 0.75 and entry_d < wref and exit_d < wref:
        return "SUSPECT_GEOMETRY"
    if same_xy and not same_angle:
        return "SUSPECT_GEOMETRY"

    return "UNKNOWN"


def audit(run_dir: Path, machine: str) -> dict:
    equipment = _load_mech(run_dir, machine)
    pairs = []
    for i, a in enumerate(equipment):
        if not a.get("entry") or not a.get("exit"):
            continue
        for b in equipment[i + 1 :]:
            if not b.get("entry") or not b.get("exit"):
                continue
            entry_d = dist(a["entry"], b["entry"])
            exit_d = dist(a["exit"], b["exit"])
            mid_a = {
                "x": (a["entry"]["x"] + a["exit"]["x"]) / 2,
                "y": (a["entry"]["y"] + a["exit"]["y"]) / 2,
            }
            mid_b = {
                "x": (b["entry"]["x"] + b["exit"]["x"]) / 2,
                "y": (b["entry"]["y"] + b["exit"]["y"]) / 2,
            }
            mid_d = dist(mid_a, mid_b)
            # Near-identical or tightly overlapping bodies
            wref = max(float(a.get("width") or 200), float(b.get("width") or 200))
            if min(entry_d, exit_d, mid_d) > max(2.5 * wref, 500):
                continue
            if mid_d > max(3.0 * wref, 600) and entry_d > 100 and exit_d > 100:
                continue
            cls = _classify_pair(a, b, entry_d, exit_d, mid_d)
            pairs.append(
                {
                    "a": a["tag"],
                    "b": b["tag"],
                    "a_type": a["type"],
                    "b_type": b["type"],
                    "entry_distance": round(entry_d, 3),
                    "exit_distance": round(exit_d, 3),
                    "midpoint_distance": round(mid_d, 3),
                    "classification": cls,
                    "provenance": "RUN_INFERRED",
                    "action": "DO_NOT_AUTO_SPREAD — engineer review",
                }
            )

    by_class: dict[str, int] = defaultdict(int)
    for p in pairs:
        by_class[p["classification"]] += 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "machine": machine,
        "run_dir": str(run_dir),
        "equipment_count": len(equipment),
        "overlap_pairs": pairs,
        "counts_by_class": dict(by_class),
        "policy": {
            "move_equipment_to_fix_text": False,
            "move_equipment_to_fix_overlap": False,
            "finished_plc_used": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Physical body overlap audit (no moves)")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--machine", default="ORNCCP2")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)
    run_dir = Path(args.run_dir)
    result = audit(run_dir, args.machine.strip())
    out = Path(args.out) if args.out else ROOT / "exports" / "cp2-gate" / "physical_overlap_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"equipment={result['equipment_count']} pairs={len(result['overlap_pairs'])}")
    print(f"classes={result['counts_by_class']}")
    print(f"wrote={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

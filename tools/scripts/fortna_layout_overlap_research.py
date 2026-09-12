#!/usr/bin/env python3
"""Analyze RUN equipment overlap clusters (CP2 + CP4) — research only.

Does NOT mutate engineering coordinates.
Outputs exports/layout-research/overlap_clusters.json and report.md
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
from fortna_physical_geometry import build_equipment_geometry  # noqa: E402
from fortna_run_geometry_investigate import (  # noqa: E402
    _clean,
    _f,
    _is_mech_conveyor,
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_mech(run_dir: Path, tags: set[str] | None = None) -> list[dict]:
    _h, rows = read_asc(run_dir / "FORTNA" / "Conveyor.asc")
    out = []
    seen = set()
    for r in rows:
        if not _is_mech_conveyor(r):
            continue
        tag = _clean(r.get("IO_Name")).upper()
        if not tag or tag in seen:
            continue
        if tags is not None and tag not in tags:
            continue
        seen.add(tag)
        geom = build_equipment_geometry(r)
        entry = geom.get("entry")
        exit_pt = geom.get("exit")
        if not entry or not exit_pt:
            continue
        out.append(
            {
                "tag": tag,
                "type": _clean(r.get("Type")).upper(),
                "layer": _clean(r.get("Layer")),
                "angle": _f(r.get("Angle")),
                "length": _f(r.get("Length")),
                "width": _f(r.get("Width")),
                "x": _f(r.get("X_cord")),
                "y": _f(r.get("Y_cord")),
                "entry": entry,
                "exit": exit_pt,
                "motor_chain": _clean(r.get("In Motor Chain")),
            }
        )
    return out


def _bb(e: dict) -> tuple[float, float, float, float]:
    xs = [e["entry"]["x"], e["exit"]["x"]]
    ys = [e["entry"]["y"], e["exit"]["y"]]
    w = float(e.get("width") or 200) / 2
    return min(xs) - w, min(ys) - w, max(xs) + w, max(ys) + w


def _overlap_area(a: tuple, b: tuple) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    return (x2 - x1) * (y2 - y1)


def _mid(e: dict) -> tuple[float, float]:
    return (
        (e["entry"]["x"] + e["exit"]["x"]) / 2,
        (e["entry"]["y"] + e["exit"]["y"]) / 2,
    )


def _ang_delta(a: float | None, b: float | None) -> float:
    if a is None or b is None:
        return 999.0
    d = abs(a - b) % 360
    return min(d, 360 - d)


def classify_pair(a: dict, b: dict) -> dict[str, Any]:
    ba, bb = _bb(a), _bb(b)
    oa = _overlap_area(ba, bb)
    ma, mb = _mid(a), _mid(b)
    center_d = math.hypot(ma[0] - mb[0], ma[1] - mb[1])
    ang_d = _ang_delta(a.get("angle"), b.get("angle"))
    end_d = min(
        math.hypot(a["exit"]["x"] - b["entry"]["x"], a["exit"]["y"] - b["entry"]["y"]),
        math.hypot(b["exit"]["x"] - a["entry"]["x"], b["exit"]["y"] - a["entry"]["y"]),
        math.hypot(a["entry"]["x"] - b["entry"]["x"], a["entry"]["y"] - b["entry"]["y"]),
        math.hypot(a["exit"]["x"] - b["exit"]["x"], a["exit"]["y"] - b["exit"]["y"]),
    )
    len_sim = 0.0
    if a.get("length") and b.get("length") and a["length"] > 0 and b["length"] > 0:
        len_sim = min(a["length"], b["length"]) / max(a["length"], b["length"])
    wref = max(float(a.get("width") or 200), float(b.get("width") or 200))
    layer_diff = (a.get("layer") or "") != (b.get("layer") or "") and bool(
        a.get("layer") or b.get("layer")
    )

    # Parent/child naming
    ta, tb = a["tag"], b["tag"]
    parent_child = (
        ta.rstrip("ABCDEFGH") == tb.rstrip("ABCDEFGH") and ta != tb and ang_d < 20
    )

    cls = "UNKNOWN"
    if layer_diff and oa > 0:
        cls = "DIFFERENT_LAYER"
    elif parent_child and center_d < 3 * wref:
        cls = "PARENT_CHILD"
    elif ang_d < 15 and center_d < 1.5 * wref and end_d > 0.5 * wref:
        cls = "PARALLEL_CONVEYOR"
    elif end_d < 0.5 * wref and ang_d < 25:
        cls = "SERIAL_OVERLAP"
    elif oa > 0 and center_d < 0.5 * wref and ang_d < 10 and len_sim > 0.85:
        cls = "SAME_PHYSICAL_ASSEMBLY"
    elif oa > 0 and center_d < wref:
        cls = "VALID_PHYSICAL_OVERLAP"
    elif oa > 0:
        cls = "SUSPECT_RUN_GEOMETRY"

    return {
        "a": ta,
        "b": tb,
        "bbox_overlap_area": round(oa, 2),
        "centerline_distance": round(center_d, 2),
        "angle_delta_deg": round(ang_d, 2),
        "endpoint_distance": round(end_d, 2),
        "length_similarity": round(len_sim, 3),
        "types": [a["type"], b["type"]],
        "layers": [a.get("layer"), b.get("layer")],
        "classification": cls,
    }


def cluster_equipment(equipment: list[dict], machine: str) -> dict[str, Any]:
    pairs = []
    for i, a in enumerate(equipment):
        for b in equipment[i + 1 :]:
            ba, bb = _bb(a), _bb(b)
            if _overlap_area(ba, bb) <= 0:
                # also catch near-centers without bbox overlap
                ma, mb = _mid(a), _mid(b)
                if math.hypot(ma[0] - mb[0], ma[1] - mb[1]) > 800:
                    continue
            rec = classify_pair(a, b)
            if rec["bbox_overlap_area"] > 0 or rec["centerline_distance"] < 400:
                pairs.append(rec)

    # Union-find clusters from overlapping pairs
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for p in pairs:
        if p["bbox_overlap_area"] > 0 or p["classification"] in {
            "PARALLEL_CONVEYOR",
            "SAME_PHYSICAL_ASSEMBLY",
            "PARENT_CHILD",
            "SERIAL_OVERLAP",
        }:
            union(p["a"], p["b"])

    clusters_map: dict[str, list[str]] = defaultdict(list)
    for e in equipment:
        clusters_map[find(e["tag"])].append(e["tag"])
    clusters = [
        {"members": sorted(v), "size": len(v)}
        for v in clusters_map.values()
        if len(v) >= 2
    ]
    clusters.sort(key=lambda c: -c["size"])

    by_cls: dict[str, int] = defaultdict(int)
    for p in pairs:
        by_cls[p["classification"]] += 1

    return {
        "machine": machine,
        "equipment_count": len(equipment),
        "pair_count": len(pairs),
        "cluster_count": len(clusters),
        "classification_counts": dict(by_cls),
        "clusters": clusters[:50],
        "pairs": pairs,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="exports/layout-research")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)

    results = {"generated_at": _ts(), "sites": {}}

    # CP2 — use discovery/equipment from run geometry or all mech with autogen scope via equipment json if present
    cp2_tags = None
    eq_path = ROOT / "exports" / "run-geometry" / "ORNCCP2_equipment.json"
    if eq_path.exists():
        eq = json.loads(eq_path.read_text(encoding="utf-8"))
        items = eq.get("equipment") if isinstance(eq, dict) else eq
        cp2_tags = {(e.get("conveyor") or "").upper() for e in (items or []) if e.get("conveyor")}

    cp2_run = ROOT / "workspace" / "active" / "RUN"
    if (cp2_run / "FORTNA" / "Conveyor.asc").exists():
        results["sites"]["ORNCCP2"] = cluster_equipment(load_mech(cp2_run, cp2_tags), "ORNCCP2")

    cp4_tags = None
    disc = ROOT / "exports" / "cp4-discovery" / "equipment.json"
    if disc.exists():
        d = json.loads(disc.read_text(encoding="utf-8"))
        cp4_tags = {
            (e.get("conveyor_tag") or "").upper()
            for e in (d.get("equipment") or [])
            if e.get("conveyor_tag")
        }
    cp4_run = ROOT / "workspace" / "cp4-run" / "RUN"
    if (cp4_run / "FORTNA" / "Conveyor.asc").exists():
        results["sites"]["ORNCCP4"] = cluster_equipment(load_mech(cp4_run, cp4_tags), "ORNCCP4")

    (out / "overlap_clusters.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )

    lines = [
        "# Layout overlap research",
        "",
        f"Generated: {results['generated_at']}",
        "",
        "Raw engineering coordinates were **not** modified.",
        "",
        "Classifications are geometric hypotheses for display-lane separation design.",
        "",
    ]
    for mach, site in results["sites"].items():
        lines += [
            f"## {mach}",
            "",
            f"- Equipment analyzed: {site['equipment_count']}",
            f"- Pairs of interest: {site['pair_count']}",
            f"- Clusters (size≥2): {site['cluster_count']}",
            f"- Classification counts: `{site['classification_counts']}`",
            "",
            "Top clusters:",
            "",
        ]
        for c in site["clusters"][:10]:
            lines.append(f"- size {c['size']}: {', '.join(c['members'][:12])}")
        lines.append("")
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: {"eq": v["equipment_count"], "pairs": v["pair_count"], "clusters": v["cluster_count"], "cls": v["classification_counts"]} for k, v in results["sites"].items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

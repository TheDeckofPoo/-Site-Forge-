#!/usr/bin/env python3
"""Identify circular/spiral-looking conveyor assemblies from RUN Conveyor.asc.

SOURCE OF TRUTH: RUN only. Does not mutate RUN coordinates. Does not read finished PLC.
Does NOT invent a spiral symbol — reports which mechanical records cluster into
turning/looping corridors that match the CP2 print dense spiral region.

Outputs: exports/layout-research/spiral_area_analysis.json
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
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

CURVE_TYPES = frozenset({"CURVE", "TRIANG", "TRIANGLE"})
LINEAR_TYPES = frozenset({"STRAIGHT", "BELT", "ZEROPRESSURE", "ZP", "ZERO_PRESSURE"})
SHORT_LENGTH = 2500.0
ARC_CENTER_JOIN = 2500.0
MID_JOIN = 3000.0
END_JOIN = 500.0
ATTACH_END = 450.0


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pt(p: dict | None) -> dict | None:
    if not p:
        return None
    return {"x": round(float(p["x"]), 3), "y": round(float(p["y"]), 3)}


def _mid(e: dict) -> tuple[float, float]:
    a, b = e.get("entry"), e.get("exit")
    if not a or not b:
        return (float(e.get("x") or 0), float(e.get("y") or 0))
    return ((a["x"] + b["x"]) / 2.0, (a["y"] + b["y"]) / 2.0)


def _load_autogen_tags(root: Path) -> set[str]:
    tags: set[str] = set()
    graph = root / "exports" / "run-geometry" / "auto-build" / "transport_graph_from_run.json"
    if graph.exists():
        g = json.loads(graph.read_text(encoding="utf-8"))
        for area in g.get("areas") or []:
            for n in area.get("nodes") or []:
                t = (n.get("conveyorTag") or n.get("label") or "").upper()
                if t:
                    tags.add(t)
    eq = root / "exports" / "run-geometry" / "ORNCCP2_equipment.json"
    if eq.exists():
        data = json.loads(eq.read_text(encoding="utf-8"))
        for e in data.get("equipment") or []:
            t = (e.get("conveyor") or "").upper()
            if t:
                tags.add(t)
    return tags


def _spiral_text_evidence(run_dir: Path) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for name in ("Errors.asc", "old.Errors.asc"):
        path = run_dir / "FORTNA" / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "SPIRAL" not in line.upper():
                continue
            parts = line.split("~")
            tag = _clean(parts[0]) if parts else ""
            desc = ""
            for p in parts:
                if "SPIRAL" in p.upper():
                    desc = _clean(p)
                    break
            out.append({"source": name, "tag": tag, "text": desc[:160]})
    return out


def load_mechanical(run_dir: Path) -> list[dict[str, Any]]:
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
        geom = build_equipment_geometry(r, mate_entries=mates_f)
        entry, exit_pt = geom.get("entry"), geom.get("exit")
        if not entry or not exit_pt:
            continue
        tag = _clean(r.get("IO_Name")).upper()
        typ = _clean(r.get("Type")).upper()
        out.append(
            {
                "tag": tag,
                "type": typ,
                "x": _f(r.get("X_cord")),
                "y": _f(r.get("Y_cord")),
                "angle": _f(r.get("Angle")),
                "width": _f(r.get("Width")),
                "length": _f(r.get("Length")),
                "inside_radius": _f(r.get("Inside_Radius")),
                "infeed_tangent": _f(r.get("Infeed_Tangent")),
                "discharge_tangent": _f(r.get("Discharge_Tangent")),
                "b": _f(r.get("b")),
                "c": _f(r.get("c")),
                "layer": _clean(r.get("Layer")),
                "infeed_elevation": _f(r.get("Infeed_Elevation")),
                "discharge_elevation": _f(r.get("Discharge_Elevation")),
                "kind": geom.get("kind"),
                "entry": _pt(entry),
                "exit": _pt(exit_pt),
                "arc_center": _pt(geom.get("arc_center")),
                "sweep": geom.get("sweep_deg"),
                "turn": geom.get("turn"),
                "centerline_radius": geom.get("centerline_radius"),
                "geometry_confidence": geom.get("confidence"),
                "sweep_source": geom.get("sweep_source"),
            }
        )
    return out


def _nearest_endpoints(
    equip: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    by_tag = {e["tag"]: e for e in equip}
    result: dict[str, dict[str, Any]] = {}
    for e in equip:
        up_best = None
        up_d = float("inf")
        dn_best = None
        dn_d = float("inf")
        for o in equip:
            if o["tag"] == e["tag"]:
                continue
            d_up = dist(o["exit"], e["entry"])
            if d_up < up_d:
                up_d = d_up
                up_best = o["tag"]
            d_dn = dist(e["exit"], o["entry"])
            if d_dn < dn_d:
                dn_d = d_dn
                dn_best = o["tag"]
        w = float(e.get("width") or 200)
        result[e["tag"]] = {
            "nearest_upstream": {
                "tag": up_best,
                "endpoint_distance": None if up_best is None else round(up_d, 3),
                "class": None
                if up_best is None
                else (
                    "CONFIRMED"
                    if up_d <= max(0.75 * w, 50)
                    else "HIGH"
                    if up_d <= max(2 * w, 400)
                    else "AMBIGUOUS"
                    if up_d <= max(3 * w, 1200)
                    else "FAR"
                ),
            },
            "nearest_downstream": {
                "tag": dn_best,
                "endpoint_distance": None if dn_best is None else round(dn_d, 3),
                "class": None
                if dn_best is None
                else (
                    "CONFIRMED"
                    if dn_d <= max(0.75 * w, 50)
                    else "HIGH"
                    if dn_d <= max(2 * w, 400)
                    else "AMBIGUOUS"
                    if dn_d <= max(3 * w, 1200)
                    else "FAR"
                ),
            },
            "upstream_type": by_tag.get(up_best or "", {}).get("type"),
            "downstream_type": by_tag.get(dn_best or "", {}).get("type"),
        }
    return result


class _UF:
    def __init__(self) -> None:
        self.p: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def cluster_curve_assemblies(equip: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Cluster CURVE (+ adjacent short/tangent linear) into candidate assemblies."""
    curves = [e for e in equip if e.get("kind") == "curve" or e.get("type") in CURVE_TYPES]
    linears = [e for e in equip if e["tag"] not in {c["tag"] for c in curves}]
    uf = _UF()
    for c in curves:
        uf.find(c["tag"])

    for i, a in enumerate(curves):
        for b in curves[i + 1 :]:
            ma, mb = _mid(a), _mid(b)
            d_mid = math.hypot(ma[0] - mb[0], ma[1] - mb[1])
            d_ac = float("inf")
            if a.get("arc_center") and b.get("arc_center"):
                d_ac = math.hypot(
                    a["arc_center"]["x"] - b["arc_center"]["x"],
                    a["arc_center"]["y"] - b["arc_center"]["y"],
                )
            d_end = min(
                dist(a["exit"], b["entry"]),
                dist(b["exit"], a["entry"]),
                dist(a["exit"], b["exit"]),
                dist(a["entry"], b["entry"]),
            )
            same_letter_bank = bool(
                re.match(r"^P\d+[A-Z]$", a["tag"])
                and re.match(r"^P\d+[A-Z]$", b["tag"])
                and a["tag"].rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                == b["tag"].rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
            )
            aligned_bank = (
                abs((a.get("y") or 0) - (b.get("y") or 0)) < 400
                and abs((a.get("angle") or 0) - (b.get("angle") or 0)) % 360 < 15
                and abs((a.get("inside_radius") or 0) - (b.get("inside_radius") or 0)) < 30
                and d_mid < 12000
            )
            if d_ac < ARC_CENTER_JOIN or d_mid < MID_JOIN or d_end < END_JOIN or same_letter_bank or aligned_bank:
                uf.union(a["tag"], b["tag"])

    # Attach nearby short / elev-changing / same-x linear pieces
    for c in curves:
        for L in linears:
            length = float(L.get("length") or 0)
            short = 0 < length <= SHORT_LENGTH
            elev_chg = abs(float(L.get("infeed_elevation") or 0) - float(L.get("discharge_elevation") or 0)) > 1
            same_xy = (
                abs((c.get("x") or 0) - (L.get("x") or 0)) < 50
                and abs((c.get("y") or 0) - (L.get("y") or 0)) < 50
            )
            d_end = min(
                dist(c["exit"], L["entry"]),
                dist(L["exit"], c["entry"]),
                dist(c["entry"], L["entry"]),
                dist(c["exit"], L["exit"]),
            )
            letter_sib = (
                c["tag"].rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                and L["tag"].rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                and c["tag"].rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                == L["tag"].rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                and c["tag"] != L["tag"]
            )
            if same_xy or (d_end < ATTACH_END and (short or elev_chg or letter_sib)):
                uf.union(c["tag"], L["tag"])

    # Attach letter-bank siblings of clustered curves (P602F next to P600F, etc.)
    by_tag = {e["tag"]: e for e in equip}
    by_root_tags: dict[str, set[str]] = defaultdict(set)
    for c in curves:
        by_root_tags[uf.find(c["tag"])].add(c["tag"])
    for e in equip:
        base = e["tag"].rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        suf = e["tag"][len(base) :] if base else ""
        if not re.fullmatch(r"[A-Z]", suf or ""):
            continue
        for root, tags in by_root_tags.items():
            for t in tags:
                if not t.endswith(suf) or t == e["tag"]:
                    continue
                te = by_tag.get(t)
                if not te:
                    continue
                if abs((e.get("x") or 0) - (te.get("x") or 0)) < 1200 and abs(
                    (e.get("y") or 0) - (te.get("y") or 0)
                ) < 8000:
                    uf.union(root, e["tag"])
                    break

    clusters_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    claimed = set(uf.p.keys())
    for tag in claimed:
        if tag in by_tag:
            clusters_map[uf.find(tag)].append(by_tag[tag])
    # Ensure pure curve singletons still appear
    for c in curves:
        clusters_map[uf.find(c["tag"])].append(c)
    deduped: list[list[dict[str, Any]]] = []
    for members in clusters_map.values():
        uniq = {m["tag"]: m for m in members}
        deduped.append(list(uniq.values()))
    deduped.sort(
        key=lambda ms: (
            -sum(1 for m in ms if m.get("kind") == "curve"),
            -len(ms),
            -sum(abs(float(m.get("sweep") or 0)) for m in ms),
        )
    )
    return deduped


def classify_composition(members: list[dict[str, Any]]) -> dict[str, Any]:
    types = Counter(m["type"] for m in members)
    n_curve = sum(1 for m in members if m.get("kind") == "curve" or m["type"] in CURVE_TYPES)
    n_linear = sum(1 for m in members if m["type"] in LINEAR_TYPES or m.get("kind") in {"linear", "belt"})
    layers = {m.get("layer") or "" for m in members}
    bases = {m["tag"].rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for m in members}
    lettered = sum(1 for m in members if re.search(r"[A-Z]$", m["tag"]))
    elev_chg = sum(
        1
        for m in members
        if m.get("infeed_elevation") is not None
        and m.get("discharge_elevation") is not None
        and abs(m["infeed_elevation"] - m["discharge_elevation"]) > 1
    )
    # Concentric nested?
    arcs = [m for m in members if m.get("arc_center") and m.get("centerline_radius")]
    nested = False
    for i, a in enumerate(arcs):
        for b in arcs[i + 1 :]:
            d = math.hypot(
                a["arc_center"]["x"] - b["arc_center"]["x"],
                a["arc_center"]["y"] - b["arc_center"]["y"],
            )
            if d < 800 and abs((a["centerline_radius"] or 0) - (b["centerline_radius"] or 0)) > 50:
                nested = True
    classes: list[str] = []
    if n_curve >= 2:
        classes.append("multiple_CURVE_records")
    if nested:
        classes.append("nested_curves")
    if n_curve >= 1 and n_linear >= 1:
        classes.append("curve_plus_straight")
    if lettered >= 3 and len(bases) <= 4:
        classes.append("parent_child_letter_bank")
    if len(layers) > 1:
        classes.append("multi_layer")
    if elev_chg:
        classes.append("elevation_change_members")
    if not classes:
        classes.append("other")
    primary = classes[0]
    if "parent_child_letter_bank" in classes and n_curve >= 3:
        primary = "curve_plus_straight_letter_bank"
    elif n_curve >= 5 and "curve_plus_straight" in classes:
        primary = "multiple_CURVE_records"
    return {
        "primary": primary,
        "flags": classes,
        "type_counts": dict(types),
        "curve_count": n_curve,
        "linear_count": n_linear,
        "lettered_count": lettered,
        "base_families": sorted(bases),
        "layers": sorted(layers),
        "elevation_changing_count": elev_chg,
        "nested_concentric": nested,
    }


def score_assembly(
    members: list[dict[str, Any]],
    *,
    spiral_text: list[dict[str, str]],
    autogen: set[str],
) -> dict[str, Any]:
    n_curve = sum(1 for m in members if m.get("kind") == "curve")
    xs = [m["x"] for m in members if m.get("x") is not None]
    ys = [m["y"] for m in members if m.get("y") is not None]
    bbox = {
        "min_x": min(xs) if xs else None,
        "max_x": max(xs) if xs else None,
        "min_y": min(ys) if ys else None,
        "max_y": max(ys) if ys else None,
    }
    sweep_sum = sum(abs(float(m.get("sweep") or 0)) for m in members)
    tags = {m["tag"] for m in members}
    # Text evidence linkage via PE608* / P600* / P700*
    text_hits = []
    for t in spiral_text:
        blob = (t.get("tag") + " " + t.get("text")).upper()
        if any(x in blob for x in ("P600", "P608", "P700", "SPIRAL")):
            # lane letter overlap
            letters = set(re.findall(r"P60[028]([A-Z])", " ".join(tags))) | set(
                re.findall(r"P608([A-Z])", blob)
            )
            text_hits.append(t)
    # Aligned same-Y curve bank (shipping sorter spiral exits)
    curve_ys = [m["y"] for m in members if m.get("kind") == "curve" and m.get("y") is not None]
    aligned_bank = False
    if len(curve_ys) >= 3:
        med = sorted(curve_ys)[len(curve_ys) // 2]
        aligned_bank = sum(1 for y in curve_ys if abs(y - med) < 300) >= 3

    evidence: list[str] = []
    conf = "LOW"
    if n_curve >= 5 and aligned_bank:
        evidence.append(f"{n_curve} CURVE records aligned in a lettered bank (same Y/angle/IR)")
        conf = "HIGH"
    elif n_curve >= 3:
        evidence.append(f"{n_curve} CURVE records clustered by arc/midpoint/endpoint")
        conf = "MEDIUM"
    if text_hits:
        evidence.append(
            f"Errors.asc names SPIRAL EXIT near this bank ({len(text_hits)} text hits)"
        )
        if conf == "MEDIUM":
            conf = "HIGH"
        elif conf == "LOW":
            conf = "MEDIUM"
    if sweep_sum >= 360:
        evidence.append(f"aggregate |sweep|={round(sweep_sum,1)} deg")
    in_auto = sorted(tags & autogen)
    out_auto = sorted(tags - autogen)
    if out_auto and n_curve >= 3:
        evidence.append(f"{len(out_auto)}/{len(tags)} members outside Autogen scope")

    # Prefer CP2 print dense spiral region around y≈55000 shipping sorter
    region_bonus = 0
    if ys and min(ys) < 62000 and max(ys) > 52000 and xs and min(xs) > 45000:
        region_bonus = 100
        evidence.append("bbox overlaps CP2 print shipping-sorter / divert dense region (y~55k)")
    score = n_curve * 10 + sweep_sum / 10 + len(members) + region_bonus + (50 if text_hits else 0)
    if aligned_bank:
        score += 40
    return {
        "score": round(score, 2),
        "confidence": conf,
        "evidence": evidence,
        "bbox": bbox,
        "aggregate_abs_sweep_deg": round(sweep_sum, 2),
        "aligned_curve_bank": aligned_bank,
        "spiral_text_hits": text_hits[:12],
        "autogen_in_scope": in_auto,
        "autogen_omitted": out_auto,
        "autogen_coverage": round(len(in_auto) / max(len(tags), 1), 3),
    }


def pack_member(e: dict[str, Any], neigh: dict[str, Any], autogen: set[str]) -> dict[str, Any]:
    return {
        "tag": e["tag"],
        "type": e["type"],
        "x": e["x"],
        "y": e["y"],
        "angle": e["angle"],
        "width": e["width"],
        "length": e["length"],
        "IR": e["inside_radius"],
        "IT": e["infeed_tangent"],
        "OT": e["discharge_tangent"],
        "b": e["b"],
        "c": e["c"],
        "layer": e["layer"],
        "infeed_elevation": e["infeed_elevation"],
        "discharge_elevation": e["discharge_elevation"],
        "entry": e["entry"],
        "exit": e["exit"],
        "arc_center": e["arc_center"],
        "sweep": e["sweep"],
        "turn": e["turn"],
        "centerline_radius": e["centerline_radius"],
        "geometry_confidence": e["geometry_confidence"],
        "nearest_upstream": neigh.get("nearest_upstream"),
        "nearest_downstream": neigh.get("nearest_downstream"),
        "in_autogen_scope": e["tag"] in autogen,
    }


def geometry_gaps(equip: list[dict[str, Any]], spiral_text: list[dict[str, str]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    triang = [e for e in equip if e["type"] in {"TRIANG", "TRIANGLE"}]
    if not triang:
        gaps.append(
            {
                "gap": "TRIANG_not_mechanical_P_tags",
                "detail": "Conveyor.asc TRIANG rows are SSV*/solenoid labels, not P### mechanical conveyors; geometry interpreter correctly ignores them for spiral body reconstruction.",
                "action": "none_required",
            }
        )
    # Referenced P608 missing
    mentioned = set()
    for t in spiral_text:
        mentioned.update(re.findall(r"P608[A-Z]?", (t.get("tag") + " " + t.get("text")).upper()))
    pe_refs = mentioned
    present = {e["tag"] for e in equip}
    missing_p608 = sorted(x for x in pe_refs if x.startswith("P608") and x not in present)
    # Also from PE descriptions we'd expect P608C etc.
    if "P608" not in "".join(present) and spiral_text:
        gaps.append(
            {
                "gap": "P608_spiral_exit_tag_missing",
                "detail": "Errors/PE text refer to P608* / SPIRAL EXIT lanes, but no P608* mechanical Conveyor.asc rows exist. Spiral exit geometry is carried by P600* CURVE (+ P602/P610/P612 lane family).",
                "missing_tags": missing_p608 or ["P608*"],
                "action": "document_only",
            }
        )
    # No concentric multi-turn body
    arcs = [e for e in equip if e.get("arc_center") and e.get("centerline_radius")]
    nested = 0
    for i, a in enumerate(arcs):
        for b in arcs[i + 1 :]:
            d = math.hypot(
                a["arc_center"]["x"] - b["arc_center"]["x"],
                a["arc_center"]["y"] - b["arc_center"]["y"],
            )
            if d < 800 and abs((a["centerline_radius"] or 0) - (b["centerline_radius"] or 0)) > 50:
                nested += 1
    if nested == 0:
        gaps.append(
            {
                "gap": "no_concentric_nested_curve_body",
                "detail": "No multi-turn concentric CURVE stack shares an arc center with differing radii. The print's multi-turn spiral graphic is not reconstructable as nested IR arcs from Conveyor.asc; only the exit curve bank is present.",
                "action": "do_not_invent_spiral_symbol",
            }
        )
    elev = [
        e
        for e in equip
        if e.get("infeed_elevation") is not None
        and e.get("discharge_elevation") is not None
        and abs(e["infeed_elevation"] - e["discharge_elevation"]) > 1
    ]
    gaps.append(
        {
            "gap": "elevation_not_in_2d_path",
            "detail": f"{len(elev)} mechanical rows change Infeed/Discharge elevation; fortna_physical_geometry builds planar entry/exit only (elevation unused for path).",
            "action": "document_only_unless_multi_record_3d_needed",
            "example_tags": [e["tag"] for e in elev[:8]],
        }
    )
    return gaps


def analyze_site(
    run_dir: Path,
    site: str,
    *,
    autogen: set[str],
) -> dict[str, Any]:
    equip = load_mechanical(run_dir)
    neigh = _nearest_endpoints(equip)
    spiral_text = _spiral_text_evidence(run_dir)
    clusters = cluster_curve_assemblies(equip)
    assemblies: list[dict[str, Any]] = []
    for members in clusters:
        n_curve = sum(1 for m in members if m.get("kind") == "curve")
        if n_curve < 2 and len(members) < 3:
            continue
        comp = classify_composition(members)
        scored = score_assembly(members, spiral_text=spiral_text, autogen=autogen)
        # Core shipping-sorter spiral-exit bank vs extended cluster neighbors
        core_tags = []
        extended_tags = []
        for m in members:
            t = m["tag"]
            core = bool(
                re.match(r"^P600[A-Z]$", t)
                or re.match(r"^P700[A-Z]$", t)
                or t in {"P720", "P714", "P716", "P718", "P712"}
                or re.match(r"^P602[A-Z]$", t)
                or re.match(r"^P610[A-Z]$", t)
                or re.match(r"^P612[A-Z]$", t)
                or re.match(r"^P702[A-Z]$", t)
                or re.match(r"^P704[A-Z]$", t)
                or re.match(r"^P706[A-Z]$", t)
                or re.match(r"^P708[A-Z]$", t)
                or re.match(r"^P710[A-Z]$", t)
            )
            (core_tags if core else extended_tags).append(t)
        assemblies.append(
            {
                "member_count": len(members),
                "composition": comp,
                "score": scored["score"],
                "confidence": scored["confidence"],
                "evidence": scored["evidence"],
                "bbox": scored["bbox"],
                "aggregate_abs_sweep_deg": scored["aggregate_abs_sweep_deg"],
                "aligned_curve_bank": scored["aligned_curve_bank"],
                "spiral_text_hits": scored["spiral_text_hits"],
                "autogen_in_scope": scored["autogen_in_scope"],
                "autogen_omitted": scored["autogen_omitted"],
                "autogen_coverage": scored["autogen_coverage"],
                "core_spiral_exit_bank_tags": sorted(core_tags),
                "extended_neighbor_tags": sorted(extended_tags),
                "members": [
                    pack_member(m, neigh.get(m["tag"], {}), autogen)
                    for m in sorted(members, key=lambda x: (x.get("x") or 0, x.get("y") or 0, x["tag"]))
                ],
            }
        )
    assemblies.sort(key=lambda a: (-a["score"], -a["composition"]["curve_count"]))

    best = assemblies[0] if assemblies else None
    # Prefer the shipping-sorter bank when present even if another cluster scores close
    for a in assemblies[:8]:
        tags = {m["tag"] for m in a["members"]}
        if any(t.startswith("P600") for t in tags) and a["composition"]["curve_count"] >= 5:
            best = a
            break

    return {
        "site": site,
        "run_dir": str(run_dir),
        "mechanical_count": len(equip),
        "curve_count": sum(1 for e in equip if e.get("kind") == "curve"),
        "autogen_scope_size": len(autogen),
        "spiral_text_evidence": spiral_text,
        "geometry_gaps": geometry_gaps(equip, spiral_text),
        "candidate_count": len(assemblies),
        "best_candidate": best,
        "candidates": assemblies[:12],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="exports/layout-research")
    ap.add_argument("--cp2-run", default="workspace/active/RUN")
    ap.add_argument("--cp4-run", default="workspace/cp4-run/RUN")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)

    autogen = _load_autogen_tags(ROOT)
    results: dict[str, Any] = {
        "generated_at": _ts(),
        "calibration": "greensboro-infeed-v1",
        "constraints": {
            "run_coords_mutated": False,
            "finished_plc_used": False,
            "spiral_symbol_invented": False,
        },
        "method": {
            "geometry": "fortna_physical_geometry.build_equipment_geometry",
            "clustering": "CURVE arc_center/midpoint/endpoint union + adjacent short/elev/letter-bank linears",
            "note": "Plant-wide mechanical conveyors; Autogen membership annotated per tag",
        },
        "autogen_scope_tags": sorted(autogen),
        "sites": {},
    }

    cp2 = Path(args.cp2_run)
    if not cp2.is_absolute():
        cp2 = ROOT / cp2
    if (cp2 / "FORTNA" / "Conveyor.asc").exists():
        results["sites"]["ORNCCP2"] = analyze_site(cp2, "ORNCCP2", autogen=autogen)

    cp4 = Path(args.cp4_run)
    if not cp4.is_absolute():
        cp4 = ROOT / cp4
    if (cp4 / "FORTNA" / "Conveyor.asc").exists():
        # CP4 uses its own discovery tags when present; still annotate vs CP2 autogen for contrast
        cp4_auto: set[str] = set()
        disc = ROOT / "exports" / "cp4-discovery" / "equipment.json"
        if disc.exists():
            d = json.loads(disc.read_text(encoding="utf-8"))
            cp4_auto = {
                (e.get("conveyor_tag") or "").upper()
                for e in (d.get("equipment") or [])
                if e.get("conveyor_tag")
            }
        results["sites"]["ORNCCP4"] = analyze_site(cp4, "ORNCCP4", autogen=cp4_auto or autogen)

    # Summary markdown fragment
    md_lines = [
        "## Spiral / circular assembly (RUN analysis)",
        "",
        f"Generated: `{results['generated_at']}`",
        "",
        "RUN coordinates were **not** modified. Finished PLC was **not** used. No spiral symbol was invented.",
        "",
    ]
    for site, data in results["sites"].items():
        best = data.get("best_candidate")
        md_lines += [f"### {site}", ""]
        if not best:
            md_lines += ["No multi-curve assembly candidate found.", ""]
            continue
        tags = [m["tag"] for m in best["members"]]
        curve_tags = [m["tag"] for m in best["members"] if m["type"] == "CURVE"]
        core = best.get("core_spiral_exit_bank_tags") or []
        md_lines += [
            f"- **Confidence:** {best['confidence']}",
            f"- **Composition:** `{best['composition']['primary']}` flags={best['composition']['flags']}",
            f"- **Core spiral-exit bank ({len(core)}):** {', '.join(core) or '(n/a)'}",
            f"- **CURVE tags ({len(curve_tags)}):** {', '.join(curve_tags)}",
            f"- **Cluster members ({len(tags)}):** {', '.join(tags)}",
            f"- **Autogen in-scope:** {len(best['autogen_in_scope'])} — {', '.join(best['autogen_in_scope']) or '(none)'}",
            f"- **Autogen omitted:** {len(best['autogen_omitted'])} — explains missing spiral on Autogen-scoped canvas",
            "- **Evidence:**",
        ]
        for ev in best["evidence"]:
            md_lines.append(f"  - {ev}")
        md_lines.append("")
        if data.get("geometry_gaps"):
            md_lines.append("- **Geometry interpreter gaps:**")
            for g in data["geometry_gaps"]:
                md_lines.append(f"  - `{g['gap']}`: {g['detail']}")
            md_lines.append("")

    (out / "spiral_area_analysis.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    (out / "spiral_area_summary.md").write_text("\n".join(md_lines), encoding="utf-8")
    summary = {
        site: {
            "curves": v["curve_count"],
            "candidates": v["candidate_count"],
            "best_curves": (v.get("best_candidate") or {}).get("composition", {}).get("curve_count"),
            "best_conf": (v.get("best_candidate") or {}).get("confidence"),
            "best_primary": (v.get("best_candidate") or {}).get("composition", {}).get("primary"),
            "autogen_omitted": len((v.get("best_candidate") or {}).get("autogen_omitted") or []),
        }
        for site, v in results["sites"].items()
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

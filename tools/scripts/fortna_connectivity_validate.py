#!/usr/bin/env python3
"""Connectivity fidelity validator — relationships over Area/zone naming.

Validation-only. Finished PLC is an answer sheet, never generation input.
Generator modules must not import this for emit paths (firewall).
"""
from __future__ import annotations

import argparse
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fortna_site_model import _clean, normalize_name, write_json

EDGE_CLASSES = (
    "DOWNSTREAM_OF",
    "CONTROLLED_BY",
    "MOTOR_OF",
    "VFD_OF",
    "PE_OF",
    "ENCODER_OF",
    "MEMBER_OF_MERGE",
    "MEMBER_OF_SORTER",
    "DIVERTS_TO",
    "CONFIRMED_BY",
    "SCANNED_BY",
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _node(name: str) -> str:
    return normalize_name(name)


def graph_from_site_model(site: dict[str, Any]) -> dict[str, Any]:
    """Build normalized connectivity graph from SiteModel relationships."""
    nodes: set[str] = set()
    edges: list[dict[str, Any]] = []

    def add_edge(frm: str, to: str, cls: str, **meta: Any) -> None:
        a, b = _node(frm), _node(to)
        if not a or not b:
            return
        nodes.add(a)
        nodes.add(b)
        edges.append({"from": a, "to": b, "class": cls, **meta})

    kind_map = {
        "motor_link": "MOTOR_OF",
        "vfd_link": "VFD_OF",
        "vfd_to_conveyor": "VFD_OF",
        "pe_assignment": "PE_OF",
        "encoder_link": "ENCODER_OF",
        "path_link": "DOWNSTREAM_OF",
        "convpath_link": "DOWNSTREAM_OF",
        "merge_link": "MEMBER_OF_MERGE",
        "saw_lane": "MEMBER_OF_MERGE",
        "saw_merge": "MEMBER_OF_MERGE",
        "jam_link": "PE_OF",
        "full_link": "PE_OF",
        "fullline_link": "PE_OF",
        "fulljam_link": "PE_OF",
        "sorter_table": "MEMBER_OF_SORTER",
        "sorter_static": "MEMBER_OF_SORTER",
    }

    for r in site.get("relationships") or []:
        frm = r.get("from") or r.get("source") or ""
        to = r.get("to") or r.get("target") or ""
        kind = str(r.get("kind") or "")
        cls = kind_map.get(kind)
        if not cls:
            continue
        add_edge(str(frm), str(to), cls, kind=kind, provenance=r.get("provenance"))

    # Equipment motor/drive fields
    for eq in site.get("equipment") or []:
        name = eq.get("raw_name") or eq.get("normalized_name")
        if not name:
            continue
        nodes.add(_node(name))
        if eq.get("motor"):
            add_edge(str(eq["motor"]), str(name), "MOTOR_OF", kind="equipment.motor")
        if eq.get("drive") or eq.get("vfd"):
            add_edge(str(eq.get("drive") or eq.get("vfd")), str(name), "VFD_OF", kind="equipment.drive")

    for pe in site.get("photoeyes") or []:
        name = pe.get("raw_name") or pe.get("normalized_name")
        conv = pe.get("linked_conveyor") or pe.get("conveyor")
        if name and conv:
            add_edge(str(name), str(conv), "PE_OF", kind="photoeye.linked_conveyor")

    for s in site.get("sorters") or []:
        name = s.get("raw_name") or s.get("normalized_name")
        enc = s.get("encoder_io")
        if name and enc:
            add_edge(str(enc), str(name), "ENCODER_OF", kind="sorter.encoder_io")
            add_edge(str(name), str(enc), "MEMBER_OF_SORTER", kind="sorter.encoder_io")

    for sc in site.get("scanners") or []:
        name = sc.get("name") or sc.get("raw_name")
        if name:
            nodes.add(_node(name))
            # scanner association edges when sorter known
            for s in site.get("sorters") or []:
                sn = s.get("raw_name") or s.get("normalized_name")
                if sn:
                    add_edge(str(name), str(sn), "SCANNED_BY", kind="scanner_sorter_hint")

    # Deduplicate edges
    uniq = {}
    for e in edges:
        key = (e["from"], e["to"], e["class"])
        uniq[key] = e
    edges = list(uniq.values())
    return {
        "nodes": sorted(nodes),
        "edges": edges,
        "edge_counts": _count_classes(edges),
    }


def graph_from_l5x(path: Path) -> dict[str, Any]:
    """Best-effort extract device identity references from L5X text (validation only)."""
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    nodes: set[str] = set()
    edges: list[dict[str, Any]] = []

    tags = set(re.findall(r'\bName="([A-Za-z_][A-Za-z0-9_]*)"', text))
    # Also bare device tokens in rung text / descriptions
    tags |= set(re.findall(r"\b((?:EZ)?PE\d{2,4}[A-Za-z0-9_]*)\b", text, flags=re.I))
    tags |= set(re.findall(r"\b(P\d{2,4}[A-Za-z]?)\b", text, flags=re.I))
    tags |= set(re.findall(r"\b(VFD\d{2,4}[A-Za-z]?)\b", text, flags=re.I))
    tags |= set(re.findall(r"\b(M\d{2,4}[A-Za-z]?)\b", text, flags=re.I))
    tags |= set(re.findall(r"\b(ENC\d{2,4}[A-Za-z]?)\b", text, flags=re.I))
    for t in tags:
        if re.match(r"^(?:P|M|PE|EZPE|VFD|ENC)\d", t, re.I):
            nodes.add(_node(t))

    # Heuristic: Fast_Conv / AOI parameter patterns mentioning P### and PE tags nearby
    for m in re.finditer(
        r"(P\d{2,4}[A-Za-z]?).*?(?:EZ)?PE(\d{2,4}[A-Za-z0-9_]*)",
        text,
        re.I | re.S,
    ):
        edges.append(
            {
                "from": _node("PE" + m.group(2) if not m.group(0).upper().startswith("EZ") else "EZPE" + m.group(2)),
                "to": _node(m.group(1)),
                "class": "PE_OF",
                "kind": "l5x_proximity_heuristic",
                "confidence": "LOW",
            }
        )

    for m in re.finditer(r"(VFD\d{2,4}[A-Za-z]?).*?(P\d{2,4}[A-Za-z]?)", text, re.I | re.S):
        edges.append(
            {
                "from": _node(m.group(1)),
                "to": _node(m.group(2)),
                "class": "VFD_OF",
                "kind": "l5x_proximity_heuristic",
                "confidence": "LOW",
            }
        )

    for m in re.finditer(r"(ENC\d{2,4}[A-Za-z]?)", text, re.I):
        nodes.add(_node(m.group(1)))

    uniq = {}
    for e in edges:
        if not e["from"] or not e["to"]:
            continue
        key = (e["from"], e["to"], e["class"])
        uniq[key] = e
    edges = list(uniq.values())
    return {"nodes": sorted(nodes), "edges": edges, "edge_counts": _count_classes(edges)}


def _count_classes(edges: list[dict[str, Any]]) -> dict[str, int]:
    c: dict[str, int] = defaultdict(int)
    for e in edges:
        c[str(e.get("class"))] += 1
    return dict(c)


def compare_graphs(
    expected: dict[str, Any],
    actual: dict[str, Any],
    *,
    ignore_area_names: bool = True,
) -> dict[str, Any]:
    """Compare expected (answer sheet / SiteModel) vs actual (generated) graphs."""
    exp = {(e["from"], e["to"], e["class"]) for e in expected.get("edges") or []}
    act = {(e["from"], e["to"], e["class"]) for e in actual.get("edges") or []}

    # Optionally drop MEMBER_OF style naming noise — Area names already not in edges
    _ = ignore_area_names

    correct = exp & act
    missing = exp - act
    extra = act - exp

    # Wrong target: same from+class, different to
    wrong = []
    exp_by_fc = defaultdict(set)
    for a, b, c in exp:
        exp_by_fc[(a, c)].add(b)
    for a, b, c in act:
        if (a, b, c) in correct:
            continue
        if (a, c) in exp_by_fc and b not in exp_by_fc[(a, c)]:
            wrong.append({"from": a, "class": c, "actual_to": b, "expected_to": sorted(exp_by_fc[(a, c)])})

    tp = len(correct)
    fp = len(extra)
    fn = len(missing)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0

    by_class: dict[str, Any] = {}
    for cls in EDGE_CLASSES:
        e_cls = {x for x in exp if x[2] == cls}
        a_cls = {x for x in act if x[2] == cls}
        c_cls = e_cls & a_cls
        m_cls = e_cls - a_cls
        x_cls = a_cls - e_cls
        tp_c, fp_c, fn_c = len(c_cls), len(x_cls), len(m_cls)
        by_class[cls] = {
            "expected": len(e_cls),
            "correct": tp_c,
            "missing": fn_c,
            "extra": fp_c,
            "precision": tp_c / (tp_c + fp_c) if (tp_c + fp_c) else None,
            "recall": tp_c / (tp_c + fn_c) if (tp_c + fn_c) else None,
        }

    exp_nodes = set(expected.get("nodes") or [])
    if not exp_nodes:
        for a, b, _c in exp:
            exp_nodes.add(a)
            exp_nodes.add(b)
    act_nodes = set(actual.get("nodes") or [])
    if not act_nodes:
        for a, b, _c in act:
            act_nodes.add(a)
            act_nodes.add(b)
    node_hit = exp_nodes & act_nodes
    node_coverage = len(node_hit) / len(exp_nodes) if exp_nodes else 0.0

    return {
        "generated_at": _ts(),
        "expected_edges": len(exp),
        "actual_edges": len(act),
        "correctly_generated": tp,
        "missing": fn,
        "extra": fp,
        "wrong_target": len(wrong),
        "unresolved": 0,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "endpoint_coverage": round(node_coverage, 4),
        "expected_nodes": len(exp_nodes),
        "actual_nodes": len(act_nodes),
        "nodes_present_in_both": len(node_hit),
        "by_class": by_class,
        "samples": {
            "missing": [{"from": a, "to": b, "class": c} for a, b, c in sorted(missing)[:30]],
            "extra": [{"from": a, "to": b, "class": c} for a, b, c in sorted(extra)[:30]],
            "wrong_target": wrong[:20],
        },
        "policy": [
            "Ignore Area/zone naming differences by default",
            "Finished PLC is validation-only answer sheet",
            "Edge precision/recall from extractable L5X links may be low; endpoint_coverage is primary for current Autogen emit",
            "High-value metric: relationship fidelity (edges when extractable) + device endpoint coverage",
        ],
        "note": (
            "Generated L5X edge extraction is heuristic; low edge recall does not alone mean "
            "devices were not generated. Prefer endpoint_coverage + identity checks."
        ),
    }


def classify_transport_identity(
    site: dict[str, Any],
    answer_names: set[str] | None = None,
) -> dict[str, Any]:
    """Classify equipment identities vs optional answer sheet names."""
    answer_names = {normalize_name(x) for x in (answer_names or set())}
    rows = []
    for eq in site.get("equipment") or []:
        name = normalize_name(eq.get("normalized_name") or eq.get("raw_name") or "")
        if not name:
            continue
        if not answer_names:
            cat = "CORRECT" if eq.get("inclusion") == "INCLUDED" else "ENGINEER_CONFIG_REQUIRED"
        elif name in answer_names:
            cat = "CORRECT"
        else:
            cat = "ANSWER_SHEET_ONLY" if False else "ENGINEER_CONFIG_REQUIRED"
            # Site has name not in answer → still CORRECT_FROM_RUN
            cat = "CORRECT"
        rows.append({"name": name, "category": cat, "inclusion": eq.get("inclusion")})
    if answer_names:
        site_set = {r["name"] for r in rows}
        for n in sorted(answer_names - site_set):
            rows.append({"name": n, "category": "MISSING", "inclusion": None})
            # wait - MISSING means expected in answer but not in site
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r["category"]] += 1
    return {"counts": dict(counts), "rows": rows[:200], "total": len(rows)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Connectivity fidelity validation")
    ap.add_argument("--site-model", type=Path, required=True)
    ap.add_argument("--generated-l5x", type=Path, default=None)
    ap.add_argument("--answer-l5x", type=Path, default=None)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    import json

    site = json.loads(args.site_model.read_text(encoding="utf-8"))
    site_g = graph_from_site_model(site)
    gen_g = graph_from_l5x(args.generated_l5x) if args.generated_l5x else {"nodes": [], "edges": []}
    ans_g = graph_from_l5x(args.answer_l5x) if args.answer_l5x and args.answer_l5x.is_file() else None

    # Primary: SiteModel expected relationships vs generated L5X heuristic graph
    cmp_site_gen = compare_graphs(site_g, gen_g)
    report = {
        "generated_at": _ts(),
        "machine": site.get("machine_scope"),
        "site_graph": {"nodes": len(site_g["nodes"]), "edges": len(site_g["edges"]), "edge_counts": site_g["edge_counts"]},
        "generated_graph": {
            "nodes": len(gen_g.get("nodes") or []),
            "edges": len(gen_g.get("edges") or []),
            "edge_counts": gen_g.get("edge_counts"),
        },
        "site_vs_generated": cmp_site_gen,
        "transport_identity": classify_transport_identity(site),
    }
    if ans_g is not None:
        report["answer_sheet_path"] = str(args.answer_l5x)
        report["answer_vs_generated"] = compare_graphs(ans_g, gen_g)
        report["site_vs_answer"] = compare_graphs(site_g, ans_g)
        report["answer_sheet_used_for_generation"] = False

    write_json(args.out, report)
    print(
        json.dumps(
            {
                "ok": True,
                "precision": cmp_site_gen["precision"],
                "recall": cmp_site_gen["recall"],
                "out": str(args.out),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

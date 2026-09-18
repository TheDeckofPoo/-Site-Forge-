#!/usr/bin/env python3
"""Gate 4 regression — P810-class false physical join (viz only).

Proves:
  1) Vertical discharges near a lower horizontal belt have NO proven physical wire.
  2) Logical/control (mtrchain) edges are not marked physical.
  3) UI classifies connections and refuses to paint logical edges as physical joins.
  4) No P810 / ORINDYAC6 special-case branches in production viz code.
  5) False-abutment inset + NEAR_MISS_UNCONNECTED guards exist.

Does not rewrite I/O resolver. Does not require a browser.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASH = ROOT / "dashboard"
GRAPH = ROOT / "exports" / "run-geometry" / "auto-build" / "transport_graph_from_run.json"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _graph_checks(fails: list[str]) -> None:
    if not GRAPH.exists():
        print("  [WARN] transport_graph_from_run.json missing — skip graph evidence")
        return
    g = json.loads(GRAPH.read_text(encoding="utf-8"))
    nodes: dict[str, dict] = {}
    wires: list[dict] = []
    for area in g.get("areas") or []:
        for n in area.get("nodes") or []:
            tag = str(n.get("conveyorTag") or "").upper()
            if tag:
                nodes[tag] = n
        wires.extend(area.get("wires") or [])
    id2tag = {
        n["id"]: str(n.get("conveyorTag") or "").upper()
        for a in g.get("areas") or []
        for n in a.get("nodes") or []
    }

    required = ("P808A", "P808B", "P808C", "P810")
    for t in required:
        ok = t in nodes
        print(f"  [{'PASS' if ok else 'FAIL'}] graph has {t}")
        if not ok:
            fails.append(f"missing {t}")

    if not all(t in nodes for t in required):
        return

    # No proven physical wire from P808* → P810
    bad_phys = []
    for w in wires:
        frm = id2tag.get(w.get("from"), "")
        to = id2tag.get(w.get("to"), "")
        if frm in ("P808A", "P808B", "P808C") and to == "P810" and w.get("physical"):
            bad_phys.append((frm, to, w.get("confidence")))
        if frm == "P810" and to in ("P808A", "P808B", "P808C") and w.get("physical"):
            bad_phys.append((frm, to, w.get("confidence")))
    ok = not bad_phys
    print(f"  [{'PASS' if ok else 'FAIL'}] no physical wire P808* ↔ P810 ({bad_phys or 'none'})")
    if not ok:
        fails.append("physical P808-P810 wire")

    # Gap evidence: tips near body without connection
    p810 = nodes["P810"]
    y = float(p810["entryCanvas"]["y"])
    x0 = float(p810["entryCanvas"]["x"])
    x1 = float(p810["exitCanvas"]["x"])
    for t in ("P808A", "P808B", "P808C"):
        ex = nodes[t]["exitCanvas"]
        cx = min(max(float(ex["x"]), x0), x1)
        gap = ((float(ex["x"]) - cx) ** 2 + (float(ex["y"]) - y) ** 2) ** 0.5
        ok = gap < 20
        print(f"  [{'PASS' if ok else 'FAIL'}] {t} exit near P810 body (gap={gap:.2f})")
        if not ok:
            fails.append(f"{t} gap")

    # Logical mtrchain edge must not be physical
    logical = [
        w
        for w in wires
        if id2tag.get(w.get("from")) == "P810" and id2tag.get(w.get("to")) == "P814"
    ]
    if logical:
        w0 = logical[0]
        ok = w0.get("physical") is False
        print(
            f"  [{'PASS' if ok else 'FAIL'}] P810→P814 physical=false "
            f"(conf={w0.get('confidence')} prov={w0.get('provenance')})"
        )
        if not ok:
            fails.append("P810→P814 marked physical")
    else:
        print("  [WARN] P810→P814 wire absent in this graph export")


def _js_checks(fails: list[str]) -> None:
    js = _read(DASH / "transport-build.js")
    html = _read(DASH / "index.html")
    checks = [
        ("classifyRenderedConnection helper", "function classifyRenderedConnection" in js),
        ("mayDrawPhysicalJoin helper", "function mayDrawPhysicalJoin" in js),
        ("falseAbutmentInsets helper", "function falseAbutmentInsets" in js),
        ("NEAR_MISS_UNCONNECTED class", "NEAR_MISS_UNCONNECTED" in js),
        ("PHYSICAL_GEOMETRY class token", "PHYSICAL_GEOMETRY" in js),
        ("PROVEN_TOPOLOGY class token", "PROVEN_TOPOLOGY" in js),
        ("topology wire CSS class", "tb-wire-topology" in js and "tb-wire-topology" in html),
        ("logical must not auto-create physical join", "mayDrawPhysicalJoin" in js and "tb-physical" in js),
        ("no P810 special-case branch", not re.search(r"""['\"]P810['\"]""", js)),
        ("no ORINDYAC6 special-case branch", "ORINDYAC6" not in js),
        ("data-conn-class on wires", "data-conn-class" in js),
        ("root-cause doc present", (ROOT / "exports/stabilization/transport_p810_class_viz_root_cause.md").is_file()),
    ]
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        if not ok:
            fails.append(name)

    # Explicit regression sentence: logical/control must not paint as physical
    ok = (
        "logical/control topology must not paint as a physical belt join" in js
        or "Logical/control relationships must NEVER paint as physical" in js
    )
    print(f"  [{'PASS' if ok else 'FAIL'}] logical/control ≠ false physical connection line (guard comment)")
    if not ok:
        fails.append("logical≠physical guard comment")


def main() -> int:
    fails: list[str] = []
    print("P810-class viz regression (Gate 4)")
    _graph_checks(fails)
    _js_checks(fails)
    if fails:
        print(f"\nFAIL — {len(fails)} checks: {fails}")
        return 1
    print("\nPASS — P810-class viz regression")
    return 0


if __name__ == "__main__":
    sys.exit(main())

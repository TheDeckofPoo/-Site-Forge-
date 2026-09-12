#!/usr/bin/env python3
"""Greensboro acceptance: Auto Build physical layout from RUN geometry."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_run_physical_layout import build_transport_graph  # noqa: E402

OUT = ROOT / "exports" / "run-geometry" / "auto-build"
RUN = ROOT / "workspace" / "active" / "RUN"


def main() -> int:
    print("=== Auto Build From RUN — Greensboro acceptance ===")
    if not (RUN / "FORTNA" / "Conveyor.asc").is_file():
        print("FAIL — missing RUN Conveyor.asc")
        return 1
    graph = build_transport_graph(RUN, "ORNCCP2", connect_threshold="HIGH_CONFIDENCE")
    m = graph.get("metrics") or {}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "transport_graph_from_run.json").write_text(json.dumps(graph, indent=2), encoding="utf-8")
    (OUT / "auto_build_metrics.json").write_text(json.dumps(m, indent=2), encoding="utf-8")

    report = {
        "conveyors_discovered": m.get("conveyors_discovered"),
        "conveyors_placed": m.get("conveyors_placed"),
        "conveyors_with_usable_xy": m.get("conveyors_with_usable_xy"),
        "conveyors_with_usable_angle": m.get("conveyors_with_usable_angle"),
        "conveyors_with_usable_length": m.get("conveyors_with_usable_length"),
        "motors_discovered": m.get("motors_discovered"),
        "vfd_motors": m.get("vfd_motors"),
        "contactor_motors": m.get("contactor_motors"),
        "unknown_motors": m.get("unknown_motors"),
        "auto_connections": m.get("auto_connections"),
        "ambiguous_connections": m.get("ambiguous_connections"),
        "disconnected_equipment": m.get("disconnected_equipment"),
        "merges_detected": m.get("merges_detected"),
    }
    (OUT / "greensboro_acceptance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    checks = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        checks.append((name, cond))
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    check("discovered > 0", (m.get("conveyors_discovered") or 0) > 0, str(m.get("conveyors_discovered")))
    check(
        "all discovered placed when XY present",
        m.get("conveyors_placed") == m.get("conveyors_with_usable_xy"),
        f"{m.get('conveyors_placed')}/{m.get('conveyors_with_usable_xy')}",
    )
    check("usable xy == discovered", m.get("conveyors_with_usable_xy") == m.get("conveyors_discovered"))
    check("usable angle == discovered", m.get("conveyors_with_usable_angle") == m.get("conveyors_discovered"))
    check("graph has one area", len(graph.get("areas") or []) == 1)
    area = (graph.get("areas") or [{}])[0]
    nodes = area.get("nodes") or []
    check("nodes == discovered", len(nodes) == m.get("conveyors_discovered"))
    check(
        "auto wires == auto_connections",
        len(area.get("wires") or []) == m.get("auto_connections"),
        f"{len(area.get('wires') or [])} vs {m.get('auto_connections')}",
    )
    owned = [n for n in nodes if n.get("plcOwned") and not n.get("displayContext")]
    ctx = [n for n in nodes if n.get("displayContext")]
    check("plc-owned Autogen set still 35", len(owned) == 35, str(len(owned)))
    check("display_context neighbors present", len(ctx) >= 6, str(len(ctx)))
    # Hairpin completeness (presentation)
    tags = {n.get("conveyorTag") for n in nodes}
    check("west hairpin has P128/P130/P132", {"P128", "P130", "P132"} <= tags)
    check("east hairpin has P144/P145/P146", {"P144", "P145", "P146"} <= tags)
    # Physical fields present
    sample = nodes[0] if nodes else None
    check("physical flag on nodes", bool(sample and sample.get("physical")))
    check("entry/exit anchors present", bool(sample and sample.get("entryAnchor") and sample.get("exitAnchor")))
    check("no invented ModuleB area name", "ModuleB" not in (area.get("name") or ""))
    # P-number order not used: ensure we have geometric wires only when confidence set
    for w in area.get("wires") or []:
        check("wire has confidence", bool(w.get("confidence")))
        check("wire marked physical", bool(w.get("physical")))
        break

    print("")
    print("GREENSBORO AUTO BUILD REPORT")
    for k, v in report.items():
        print(f"  {k}: {v}")
    print("")
    md = ["# Greensboro Auto Build From RUN — acceptance", ""]
    for k, v in report.items():
        md.append(f"- **{k}**: {v}")
    (OUT / "greensboro_acceptance.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    failed = sum(1 for _, ok in checks if not ok)
    print(f"{'PASS' if failed == 0 else 'FAIL'} — {len(checks) - failed}/{len(checks)} checks")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

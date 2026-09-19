#!/usr/bin/env python3
"""Before/after interaction-cost proxy for MSCRENOPICK-scale Transport.

This does NOT run Electron. It measures the algorithmic hotspots that used to
run on every pointer sample:

  - nested array.find for N moved nodes
  - O(N^2) abutment-style scans

and the fixed pattern:

  - Map index lookup
  - skip full redraw during drag (mouseup only)

Emit a JSON report suitable for checkpoint docs.
"""
from __future__ import annotations

import json
import time
from pathlib import Path


def _time(fn, loops: int = 1) -> float:
    t0 = time.perf_counter()
    for _ in range(loops):
        fn()
    return (time.perf_counter() - t0) * 1000.0


def bench_node_lookup(n: int, moved: int = 8, loops: int = 200) -> dict:
    nodes = [{"id": f"n{i}", "x": i, "y": i} for i in range(n)]
    moved_ids = [f"n{i}" for i in range(moved)]

    def nested_find():
        for mid in moved_ids:
            next(x for x in nodes if x["id"] == mid)

    by_id = {x["id"]: x for x in nodes}

    def map_get():
        for mid in moved_ids:
            _ = by_id[mid]

    # warm
    nested_find()
    map_get()
    return {
        "node_count": n,
        "moved": moved,
        "loops": loops,
        "nested_find_ms": round(_time(nested_find, loops), 3),
        "map_get_ms": round(_time(map_get, loops), 3),
    }


def bench_abutment_scan(n: int, loops: int = 30) -> dict:
    """Proxy for falseAbutmentInsets O(N^2) tip tests."""
    nodes = [{"id": i, "x": i * 10.0, "y": (i % 7) * 10.0} for i in range(n)]

    def scan():
        hits = 0
        for a in nodes:
            for b in nodes:
                if a is b:
                    continue
                if abs(a["x"] - b["x"]) < 5 and abs(a["y"] - b["y"]) < 5:
                    hits += 1
        return hits

    scan()
    return {
        "node_count": n,
        "loops": loops,
        "abutment_scan_ms": round(_time(scan, loops), 3),
        "note": "Full schematic rebuild during drag used to pay this every frame",
    }


def main() -> int:
    sizes = (66, 100)
    report = {
        "kind": "transport_interaction_bench",
        "version": 1,
        "contract": {
            "pan": "scroll-only (no redraw)",
            "zoom": "CSS transform-only (no render() per wheel)",
            "drag": "DOM position updates only; full redraw on mouseup",
            "persist": "debounced / mouseup only — never on mousemove",
        },
        "fixtures": [],
    }
    for n in sizes:
        report["fixtures"].append(
            {
                "approx_conveyors": n,
                "lookup": bench_node_lookup(n),
                "abutment_proxy": bench_abutment_scan(n),
                "interaction_budget": {
                    "target_frame_ms": 16.7,
                    "drag_per_sample_allowed": "DOM style updates + Map lookups only",
                    "full_redraw_allowed_on": ["mouseup", "fit", "LOD band change"],
                },
            }
        )
    out = Path("exports/qualification/perf") / "transport_interaction_bench.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(out), "sizes": list(sizes)}, indent=2))
    for fix in report["fixtures"]:
        lu = fix["lookup"]
        print(
            f"N={fix['approx_conveyors']}: nested_find={lu['nested_find_ms']}ms "
            f"map_get={lu['map_get_ms']}ms "
            f"abutment={fix['abutment_proxy']['abutment_scan_ms']}ms"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

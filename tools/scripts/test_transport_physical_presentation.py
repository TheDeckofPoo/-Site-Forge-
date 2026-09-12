#!/usr/bin/env python3
"""Smoke checks for Transport Build physical presentation (CP2 layout viz).

Does not claim browser acceptance — only that presentation code + CSS hooks exist
and that Auto Build graph still carries source RUN geometry fields.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASH = ROOT / "dashboard"
EXPORTS = ROOT / "exports" / "cp2-gate" / "layout"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    fails: list[str] = []
    js = _read(DASH / "transport-build.js")
    p2 = _read(DASH / "transport-build-pass2.js")
    html = _read(DASH / "index.html")

    checks = [
        ("tb-seg CSS", ".tb-seg" in html),
        ("Fit Site button", 'id="tb-fit-site"' in html),
        ("Fit Area button", 'id="tb-fit-area"' in html),
        ("isPhysicalSeg helper", "function isPhysicalSeg" in js),
        ("physicalAnchors helper", "function physicalAnchors" in js),
        ("fitSite helper", "function fitSite" in js),
        ("fitArea helper", "function fitArea" in js),
        ("ENTRY/EXIT labels", "ENTRY" in js and "EXIT" in js),
        ("view.zoom presentation", "view" in js and "canvasScale" in js),
        ("pass2 skips card rewrite for segs", "tb-schematic-proxy" in p2 or ("tb-seg" in p2 and "schematic" in p2)),
        ("schematic layer present", "tb-schematic" in html and "drawSchematic" in js),
        ("isSchematicNode helper", "function isSchematicNode" in js),
        ("pass2 Fit Visible after Auto Build", "fitVisible" in p2),
        ("ctrl+wheel zoom", "ctrlKey" in p2 and "wheel" in p2),
        ("layers prepared", "tb-layer-physical" in html and "tb-layer-motors" in html),
        ("Fit button", 'id="tb-fit"' in html),
        ("Fit menu retains Fit All", 'id="tb-fit-all"' in html),
        ("fitVisible helper", "function fitVisible" in js),
        ("fitAll helper", "function fitAll" in js),
        ("label collision helper", "placeSchematicLabels" in js),
        ("outlier classifier", "classifySpatialOutliers" in js),
        ("workflow strip", 'id="tb-workflow-strip"' in html),
        ("Apply to Autogen", 'id="tb-apply-autogen"' in html),
        ("canonical apply graph", "function buildCanonicalApplyGraph" in js),
        ("Advanced menu", 'id="tb-advanced-menu"' in html),
        ("Build PLC CTA", 'id="tb-goto-build-plc"' in html),
        ("presentation offsets", "computePresentationOffsets" in js),
    ]
    for name, ok in checks:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
        if not ok:
            fails.append(name)

    graph_path = EXPORTS / "transport_graph_from_run.json"
    if not graph_path.exists():
        graph_path = ROOT / "exports" / "run-geometry" / "auto-build" / "transport_graph_from_run.json"
    if graph_path.exists():
        g = json.loads(graph_path.read_text(encoding="utf-8"))
        nodes = []
        for a in g.get("areas") or []:
            nodes.extend(a.get("nodes") or [])
        phys = [n for n in nodes if n.get("physical")]
        if not phys:
            fails.append("physical nodes in graph")
            print("  [FAIL] physical nodes in graph")
        else:
            sample = phys[0]
            for field in ("sourceX", "sourceY", "sourceAngle", "length", "width", "entryAnchor", "exitAnchor"):
                ok = field in sample and sample.get(field) is not None
                print(f"  [{'PASS' if ok else 'FAIL'}] graph field {field}")
                if not ok:
                    fails.append(field)
            # Ensure presentation did not invent P-number topology into source
            if g.get("physicalLayout") is not True:
                fails.append("physicalLayout flag")
                print("  [FAIL] physicalLayout flag")
            else:
                print("  [PASS] physicalLayout flag")
    else:
        print("  [WARN] no transport_graph_from_run.json — skip geometry field checks")

    if fails:
        print(f"\nFAIL — {len(fails)} checks: {fails}")
        return 1
    print("\nPASS — physical presentation smoke")
    return 0


if __name__ == "__main__":
    sys.exit(main())

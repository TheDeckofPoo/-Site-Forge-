#!/usr/bin/env python3
"""Transport physical drawing pass — presentation firewall + canvas label rules.

Proves:
  - canvas label code no longer paints AREA?/ES?/zone names
  - display offsets / layout interpreter do not mutate canonical Apply fields
  - curve pathCanvas includes SVG arc commands for CURVE equipment
  - raw sourceX/Y remain distinct from display_dx/dy
  - layout research curve_validation artifacts exist
"""
from __future__ import annotations
# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys
_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / 'tools' / 'scripts'
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
# Prefer canonical names used by existing tests:
SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO
REPO_ROOT = _SF_REPO
# --- end bootstrap ---


import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _js() -> str:
    return (ROOT / "dashboard" / "transport-build.js").read_text(encoding="utf-8")


def test_no_area_es_canvas_labels() -> None:
    js = _js()
    start = js.index("function drawSchematic")
    end = js.index("function flowAngleDeg", start)
    block = js[start:end]
    # Forbidden as emitted label text (string literals), not mere comments
    assert re.search(r'''["'][^"']*AREA\?[^"']*["']''', block) is None
    assert re.search(r'''["'][^"']*ES\?[^"']*["']''', block) is None
    assert "labelCandidates.push" in block
    assert "areaRequired" in block  # warn indicator may still read the flag
    assert "tb-schematic-warn" in block
    assert "tb-schematic-flow" in block
    # Primary label payload is the P-tag variable `tag`, not area/zone fields
    push = block.split("labelCandidates.push")[1][:500]
    assert "tag," in push or "tag:" in push or "tag\n" in push or "tag" in push
    assert "safetyZone" not in push
    print("  [PASS] canvas labels are P-tag (+ optional motor); no AREA/ES text")


def test_canonical_apply_excludes_presentation() -> None:
    js = _js()
    start = js.index("function buildCanonicalApplyGraph")
    end = js.index("function setWorkflowStep", start)
    block = js[start:end]
    for bad in (
        "display_dx",
        "display_dy",
        "display_lane",
        "display_reason",
        "pathCanvas",
        "entryCanvas",
        "arcSamplesCanvas",
        "sourceX",
        "sourceY",
    ):
        assert bad not in block, f"canonical Apply must not emit {bad}"
    assert "displayContext" in block, "Apply must filter displayContext neighbors"
    print("  [PASS] canonical Apply excludes presentation/raw canvas fields")


def test_overlap_classifies_connected_serial() -> None:
    js = _js()
    assert "CONNECTED_SERIAL" in js
    assert "PARALLEL_LANE_SEPARATION" in js
    assert "CONNECTED_RUN_MATE" in js or "CONNECTIVITY_MATE" in js
    assert "CURVE_ASSEMBLY" in js
    assert "SAME_PHYSICAL_ASSEMBLY" in js
    assert "PARALLEL_CONVEYOR" in js
    print("  [PASS] overlap classifier distinguishes serial vs parallel")


def test_display_context_firewall() -> None:
    p = ROOT / "exports/run-geometry/auto-build/transport_graph_from_run.json"
    if not p.exists():
        print("  [SKIP] transport graph missing")
        return
    g = json.loads(p.read_text(encoding="utf-8"))
    nodes = (g["areas"][0]["nodes"] if g.get("areas") else g.get("nodes")) or []
    owned = [n for n in nodes if n.get("plcOwned") and not n.get("displayContext")]
    ctx = [n for n in nodes if n.get("displayContext")]
    assert len(owned) == 35
    assert len(ctx) >= 6
    # Raw coords present on both; display offsets are UI-only (not in graph JSON)
    for n in owned[:3] + ctx[:3]:
        assert n.get("sourceX") is not None and n.get("sourceY") is not None
        assert "display_dx" not in n
    print(f"  [PASS] display_context firewall owned={len(owned)} ctx={len(ctx)}")


def test_layout_pass2_artifacts() -> None:
    for rel in (
        "exports/layout-research/spiral_area_analysis.json",
        "exports/layout-research/physical_runs.json",
        "exports/layout-research/layout_before_after.md",
        "exports/layout-research/curve_validation.json",
        "exports/layout-research/overlap_clusters.json",
    ):
        assert (ROOT / rel).exists(), rel
    print("  [PASS] layout pass2 research artifacts present")


def test_curve_arc_in_graph() -> None:
    p = ROOT / "exports/run-geometry/auto-build/transport_graph_from_run.json"
    if not p.exists():
        print("  [SKIP] transport_graph_from_run.json missing")
        return
    g = json.loads(p.read_text(encoding="utf-8"))
    nodes = (g["areas"][0]["nodes"] if g.get("areas") else g.get("nodes")) or []
    curves = [
        n
        for n in nodes
        if str(n.get("equipmentType") or "").upper() == "CURVE"
        or str(n.get("renderKind") or "").lower() == "curve"
    ]
    assert curves, "expected CURVE nodes in CP2 graph"
    with_arc = 0
    for n in curves:
        cmds = [str(c.get("cmd") or "").lower() for c in (n.get("pathCanvas") or [])]
        if "arc" in cmds:
            with_arc += 1
        # raw engineering coords present
        assert n.get("sourceX") is not None and n.get("sourceY") is not None
    assert with_arc == len(curves), f"all curves need arc cmds, got {with_arc}/{len(curves)}"
    print(f"  [PASS] {with_arc}/{len(curves)} CURVE nodes render SVG arcs")


def test_curve_validation_artifacts() -> None:
    j = ROOT / "exports/layout-research/curve_validation.json"
    m = ROOT / "exports/layout-research/curve_validation.md"
    assert j.exists() and m.exists()
    data = json.loads(j.read_text(encoding="utf-8"))
    assert "curves" in data or "sites" in data or "results" in data or "evaluations" in data or "summary" in data
    print("  [PASS] curve_validation artifacts present")


def test_geometry_hybrid_b_still_safe() -> None:
    sys.path.insert(0, str(ROOT / "tools" / "scripts"))
    from fortna_physical_geometry import curve_body

    # b≡angle → must not invent zero-sweep; default 90 still available
    body = curve_body(
        0,
        0,
        90,
        inside_radius=266.667,
        width=200,
        infeed_tangent=50,
        discharge_tangent=50,
        exit_bearing=90,
        mate_points=[(50, 366.667)],
    )
    assert abs(abs(body.get("sweep_deg") or 0) - 90) < 1e-6 or body.get("sweep_source") == "default_90"
    print("  [PASS] b≡angle falls back safely")


def main() -> int:
    print("=== transport physical drawing tests ===")
    fails = 0
    for fn in [
        test_no_area_es_canvas_labels,
        test_canonical_apply_excludes_presentation,
        test_overlap_classifies_connected_serial,
        test_display_context_firewall,
        test_layout_pass2_artifacts,
        test_curve_arc_in_graph,
        test_curve_validation_artifacts,
        test_geometry_hybrid_b_still_safe,
    ]:
        try:
            fn()
        except Exception as exc:
            fails += 1
            print(f"  [FAIL] {fn.__name__}: {exc}")
    if fails:
        print(f"FAIL — {fails}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

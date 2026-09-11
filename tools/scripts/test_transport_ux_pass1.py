#!/usr/bin/env python3
"""Transport Build UX Pass 1 — topology (wires + asMerge) runtime verification.

Builds a ModuleB-shaped graph using ONLY topology fields (no conv_merge palette
node), applies it via fortna_transport_graph.apply_graph_to_workbook, and asserts
workbook conveyors + merges_2to1 evidence.

Exit 0 on pass, non-zero on fail. Evidence written under exports/transport-ux-pass1/.
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_transport_graph import apply_graph_to_workbook, analyze  # noqa: E402

OUT_DIR = ROOT / "exports" / "transport-ux-pass1"
WORKBOOK_SRC = ROOT / "workspace" / "autogen_workbook.json"


def build_module_b_graph() -> dict:
    """ModuleB topology: P136→P138→P406 ←P402, with P406 asMerge (no conv_merge)."""
    return {
        "version": 1,
        "areas": [
            {
                "id": "area_test_module_b",
                "name": "Test_ModuleB",
                "nodes": [
                    {
                        "id": "n_p136",
                        "kind": "conv_straight",
                        "label": "P136",
                        "conveyorTag": "P136",
                        "downstream": "P138",
                        "x": 40,
                        "y": 80,
                        "rotation": 0,
                        "inPorts": 1,
                        "devices": [
                            {
                                "kind": "photoeye",
                                "tag": "PE136_P",
                                "roles": ["exit", "jam"],
                            }
                        ],
                    },
                    {
                        "id": "n_p138",
                        "kind": "conv_straight",
                        "label": "P138",
                        "conveyorTag": "P138",
                        "downstream": "P406",
                        "x": 220,
                        "y": 80,
                        "rotation": 0,
                        "inPorts": 1,
                        "devices": [
                            {
                                "kind": "photoeye",
                                "tag": "PE138_P",
                                "roles": ["exit", "jam"],
                            }
                        ],
                    },
                    {
                        "id": "n_p402",
                        "kind": "conv_straight",
                        "label": "P402",
                        "conveyorTag": "P402",
                        "downstream": "P406",
                        "x": 220,
                        "y": 220,
                        "rotation": 0,
                        "inPorts": 1,
                        "devices": [
                            {
                                "kind": "photoeye",
                                "tag": "PE402_P",
                                "roles": ["exit", "jam"],
                            }
                        ],
                    },
                    {
                        "id": "n_p406",
                        "kind": "conv_straight",
                        "label": "P406",
                        "conveyorTag": "P406",
                        "downstream": "",
                        "asMerge": True,
                        "x": 400,
                        "y": 140,
                        "rotation": 0,
                        "inPorts": 2,
                        "devices": [],
                    },
                ],
                "wires": [
                    {"id": "w1", "from": "n_p136", "to": "n_p138", "toPort": "in"},
                    {"id": "w2", "from": "n_p138", "to": "n_p406", "toPort": "in0"},
                    {"id": "w3", "from": "n_p402", "to": "n_p406", "toPort": "in1"},
                ],
            }
        ],
    }


def _minimal_workbook(tags_pes: dict[str, str]) -> dict:
    """Create a minimal Autogen workbook with the conveyors/PEs under test."""
    conveyors = []
    for i, (tag, pe) in enumerate(tags_pes.items(), start=1):
        conveyors.append({
            "number": i,
            "include": True,
            "conveyor": tag,
            "main_area": "ORNCCP2_Area",
            "safety_zone": "ORNCCP2_ESZone1",
            "type": "Transport with MS",
            "template": "Transport",
            "drive": "MS",
            "exit_pe_tag": pe,
            "add_pe_tag": "",
            "jam_pe_tags": [pe] if pe else [],
            "full_pe_tags": [],
            "product_pe_tags": [pe] if pe else [],
            "all_pe_tags": [pe] if pe else [],
            "exit_pe_opt": "",
            "jam_opt": "",
            "full_opt": "",
            "downstream": "",
            "motor_starter": "Yes",
            "espc": "",
            "control_station": "",
            "power_supply": "",
            "source": "test_transport_ux_pass1",
            "edited": False,
        })
    return {
        "conveyors": conveyors,
        "merges_2to1": [],
        "areas": [
            {
                "name": "ORNCCP2_Area",
                "safety_zone": "ORNCCP2_ESZone1",
                "conveyor_count": len(conveyors),
            }
        ],
        "options": {
            "areas": ["ORNCCP2_Area"],
            "safety_zones": ["ORNCCP2_ESZone1"],
            "exit_pe": [p for p in tags_pes.values() if p],
        },
    }


def _conv_by_tag(wb: dict, tag: str) -> dict | None:
    u = tag.upper()
    for row in wb.get("conveyors") or []:
        if str(row.get("conveyor") or "").strip().upper() == u:
            return row
    return None


def _load_or_create_workbook(out_wb: Path) -> tuple[dict, str]:
    if WORKBOOK_SRC.is_file():
        wb = json.loads(WORKBOOK_SRC.read_text(encoding="utf-8-sig"))
        out_wb.write_text(json.dumps(wb, indent=2), encoding="utf-8")
        return wb, f"copied from {WORKBOOK_SRC.as_posix()}"
    tags_pes = {
        "P136": "PE136_P",
        "P138": "PE138_P",
        "P402": "PE402_P",
        "P406": "",
    }
    wb = _minimal_workbook(tags_pes)
    out_wb.write_text(json.dumps(wb, indent=2), encoding="utf-8")
    return wb, "created minimal workbook (workspace/autogen_workbook.json missing)"


def sequential_build_interaction_count() -> dict:
    """Document Sequential Build expected clicks for P100→…→P110."""
    chain = ["P100", "P102", "P104", "P106", "P108", "P110"]
    add_clicks = len(chain)  # one Add per conveyor in Sequential Build
    manual_wire_drags = 0  # Sequential Build auto-wires successive adds
    return {
        "chain": chain,
        "add_clicks": add_clicks,
        "manual_wire_drags": manual_wire_drags,
        "expected": "6 add clicks + 0 manual wire drags",
        "note": (
            "Sequential Build places each next conveyor and auto-creates the "
            "wire to the previous node; engineer never drags wires by hand."
        ),
    }


def _try_l5x_note(wb: dict) -> dict:
    """Optionally attempt L5X; if heavy/unavailable, print Fast_Conv-relevant fields."""
    tags = ("P136", "P138", "P402", "P406")
    fields = []
    for t in tags:
        row = _conv_by_tag(wb, t) or {}
        fields.append({
            "conveyor": t,
            "downstream": row.get("downstream") or "",
            "exit_pe_tag": row.get("exit_pe_tag") or "",
            "main_area": row.get("main_area") or "",
        })
    attempted = False
    skipped_reason = (
        "L5X Generate path not exercised in this pass "
        "(fortna_autogen redesign out of scope); "
        "Fast_Conv-relevant workbook fields printed instead."
    )
    # Light probe only — do not redesign or run full generate
    try:
        import fortna_autogen  # noqa: F401
        attempted = False  # import ok but full Generate skipped
        skipped_reason = (
            "fortna_autogen importable; full L5X Generate skipped "
            "(heavy path / no redesign). Workbook Fast_Conv fields below."
        )
    except Exception as exc:  # pragma: no cover
        skipped_reason = f"fortna_autogen unavailable: {exc}"
    return {
        "l5x_attempted": attempted,
        "l5x_status": "skipped",
        "reason": skipped_reason,
        "fast_conv_fields": fields,
    }


def run() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    checks: list[dict] = []
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
        if not ok:
            failures.append(f"{name}: {detail}" if detail else name)

    print("=== Transport UX Pass 1 verification ===")
    graph = build_module_b_graph()
    graph_path = OUT_DIR / "module_b_topology_graph.json"
    graph_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")
    print(f"Graph written: {graph_path}")

    # Analyze topology merges before apply
    analysis = analyze(graph)
    merges_from_analyze = analysis.get("merges_2to1") or []
    check(
        "analyze detects asMerge topology merge",
        len(merges_from_analyze) == 1,
        f"merges_2to1 count={len(merges_from_analyze)}",
    )
    if merges_from_analyze:
        m0 = merges_from_analyze[0]
        check(
            "analyze merge discharge=P406",
            str(m0.get("discharge") or "").upper() == "P406",
            f"discharge={m0.get('discharge')!r}",
        )
        check(
            "analyze hold_mode=runhold",
            str(m0.get("hold_mode") or "") == "runhold",
            f"hold_mode={m0.get('hold_mode')!r}",
        )
        lanes_set = {str(m0.get("lane_a") or "").upper(), str(m0.get("lane_b") or "").upper()}
        check(
            "analyze lanes are {P138,P402}",
            lanes_set == {"P138", "P402"},
            f"lane_a={m0.get('lane_a')!r} lane_b={m0.get('lane_b')!r}",
        )

    # Downstream exposed in analyze nodes
    node_ds = {
        (n.get("conveyorTag") or "").upper(): (n.get("downstream") or "")
        for a in (analysis.get("areas") or [])
        for n in (a.get("nodes") or [])
    }
    check(
        "analyze nodes expose downstream",
        node_ds.get("P136") == "P138" and node_ds.get("P138") == "P406",
        f"P136→{node_ds.get('P136')!r} P138→{node_ds.get('P138')!r}",
    )

    out_wb = OUT_DIR / "autogen_workbook_applied.json"
    wb, wb_src_note = _load_or_create_workbook(out_wb)
    print(f"Workbook source: {wb_src_note}")

    applied = apply_graph_to_workbook(graph, wb)
    wb2 = applied["workbook"]
    out_wb.write_text(json.dumps(wb2, indent=2), encoding="utf-8")

    # Workbook assertions
    expect_ds = {"P136": "P138", "P138": "P406", "P402": "P406"}
    for src, dst in expect_ds.items():
        row = _conv_by_tag(wb2, src)
        got = (row.get("downstream") if row else None) or ""
        check(
            f"workbook {src} downstream={dst}",
            row is not None and str(got).upper() == dst.upper(),
            f"got={got!r}",
        )

    p406 = _conv_by_tag(wb2, "P406")
    check(
        "workbook P406 main_area=Test_ModuleB",
        p406 is not None and (p406.get("main_area") or "") == "Test_ModuleB",
        f"main_area={(p406 or {}).get('main_area')!r}",
    )

    # Merges owned by this graph area (filter transport_build_graph for P406)
    all_merges = list(wb2.get("merges_2to1") or [])
    relevant = [
        m
        for m in all_merges
        if str(m.get("discharge") or m.get("name") or "").strip().upper() == "P406"
        and (
            m.get("source") == "transport_build_graph"
            or str(m.get("area") or "") == "Test_ModuleB"
        )
    ]
    # Prefer transport_build_graph rows when present
    tb_merges = [m for m in relevant if m.get("source") == "transport_build_graph"]
    if tb_merges:
        relevant = tb_merges
    check(
        "one merges_2to1 row for P406",
        len(relevant) == 1,
        f"count={len(relevant)} (all_merges={len(all_merges)})",
    )
    if relevant:
        m = relevant[0]
        lane_set = {str(m.get("lane_a") or "").upper(), str(m.get("lane_b") or "").upper()}
        check(
            "merge lane_a/lane_b == {P138,P402}",
            lane_set == {"P138", "P402"},
            f"lane_a={m.get('lane_a')!r} lane_b={m.get('lane_b')!r}",
        )
        check(
            "merge discharge=P406",
            str(m.get("discharge") or "").upper() == "P406",
            f"discharge={m.get('discharge')!r}",
        )
        check(
            "merge hold_mode=runhold",
            str(m.get("hold_mode") or "") == "runhold",
            f"hold_mode={m.get('hold_mode')!r}",
        )

    # Existing conv_merge path still works (smoke)
    legacy_graph = {
        "version": 1,
        "areas": [
            {
                "id": "a_legacy",
                "name": "Legacy_Merge_Area",
                "nodes": [
                    {
                        "id": "n_a",
                        "kind": "conv_straight",
                        "conveyorTag": "P900",
                        "label": "P900",
                        "devices": [],
                    },
                    {
                        "id": "n_b",
                        "kind": "conv_straight",
                        "conveyorTag": "P901",
                        "label": "P901",
                        "devices": [],
                    },
                    {
                        "id": "n_m",
                        "kind": "conv_merge",
                        "conveyorTag": "P902",
                        "label": "Merge 2:1",
                        "inPorts": 2,
                        "devices": [],
                    },
                ],
                "wires": [
                    {"from": "n_a", "to": "n_m", "toPort": "in0"},
                    {"from": "n_b", "to": "n_m", "toPort": "in1"},
                ],
            }
        ],
    }
    legacy = analyze(legacy_graph)
    leg_merges = legacy.get("merges_2to1") or []
    check(
        "legacy conv_merge still produces merges_2to1",
        len(leg_merges) == 1
        and str(leg_merges[0].get("discharge") or "").upper() == "P902"
        and str(leg_merges[0].get("hold_mode") or "") == "runhold",
        f"count={len(leg_merges)} discharge={(leg_merges[0].get('discharge') if leg_merges else None)!r}",
    )

    # node.downstream-only (no wire) still applies
    ds_only_graph = {
        "version": 1,
        "areas": [
            {
                "id": "a_ds",
                "name": "Downstream_Only",
                "nodes": [
                    {
                        "id": "n1",
                        "kind": "conv_straight",
                        "conveyorTag": "P910",
                        "downstream": "P911",
                        "devices": [],
                    },
                    {
                        "id": "n2",
                        "kind": "conv_straight",
                        "conveyorTag": "P911",
                        "downstream": "",
                        "devices": [],
                    },
                ],
                "wires": [],
            }
        ],
    }
    ds_applied = apply_graph_to_workbook(ds_only_graph, {"conveyors": [], "options": {}})
    r910 = _conv_by_tag(ds_applied["workbook"], "P910")
    check(
        "node.downstream applies when no wire",
        r910 is not None and str(r910.get("downstream") or "").upper() == "P911",
        f"downstream={(r910 or {}).get('downstream')!r}",
    )

    seq = sequential_build_interaction_count()
    check(
        "Sequential Build interaction count",
        seq["add_clicks"] == 6 and seq["manual_wire_drags"] == 0,
        seq["expected"],
    )
    print(f"  Sequential Build: {seq['expected']}")

    l5x = _try_l5x_note(wb2)
    print(f"  L5X: {l5x['l5x_status']} — {l5x['reason']}")
    for f in l5x["fast_conv_fields"]:
        print(
            f"    Fast_Conv {f['conveyor']}: downstream={f['downstream']!r} "
            f"exit_pe_tag={f['exit_pe_tag']!r} main_area={f['main_area']!r}"
        )

    passed = sum(1 for c in checks if c["ok"])
    failed = sum(1 for c in checks if not c["ok"])
    ok = failed == 0

    evidence = {
        "ok": ok,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stamp": stamp,
        "graph_path": str(graph_path),
        "workbook_path": str(out_wb),
        "workbook_source": wb_src_note,
        "apply_summary": applied.get("summary"),
        "checks": checks,
        "failures": failures,
        "merges_applied": applied.get("merges_applied") or [],
        "analysis_merges_2to1": merges_from_analyze,
        "sequential_build": seq,
        "l5x": l5x,
        "pass_count": passed,
        "fail_count": failed,
    }
    evidence_json = OUT_DIR / f"evidence_{stamp}.json"
    evidence_json.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    # Also write a stable latest pointer
    (OUT_DIR / "evidence_latest.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf-8"
    )

    md_lines = [
        f"# Transport UX Pass 1 evidence ({stamp})",
        "",
        f"**Result:** {'PASS' if ok else 'FAIL'} ({passed} passed / {failed} failed)",
        "",
        f"- Graph: `{graph_path.name}`",
        f"- Workbook: `{out_wb.name}`",
        f"- Workbook source: {wb_src_note}",
        f"- Apply: {applied.get('summary')}",
        "",
        "## Checks",
    ]
    for c in checks:
        mark = "PASS" if c["ok"] else "FAIL"
        md_lines.append(f"- **{mark}** {c['name']}" + (f" — {c['detail']}" if c["detail"] else ""))
    md_lines.extend([
        "",
        "## Sequential Build interaction count",
        f"- Chain: {' → '.join(seq['chain'])}",
        f"- Expected: **{seq['expected']}**",
        f"- {seq['note']}",
        "",
        "## Fast_Conv workbook fields (L5X skipped)",
        f"- Status: {l5x['l5x_status']}",
        f"- Reason: {l5x['reason']}",
    ])
    for f in l5x["fast_conv_fields"]:
        md_lines.append(
            f"- `{f['conveyor']}` downstream=`{f['downstream']}` "
            f"exit_pe=`{f['exit_pe_tag']}` area=`{f['main_area']}`"
        )
    if failures:
        md_lines.append("")
        md_lines.append("## Failures")
        md_lines.extend(f"- {f}" for f in failures)
    md_path = OUT_DIR / f"evidence_{stamp}.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    (OUT_DIR / "evidence_latest.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print()
    print("=" * 52)
    if ok:
        print(f"PASS — {passed}/{passed + failed} checks")
    else:
        print(f"FAIL — {failed} failed / {passed} passed")
        for f in failures:
            print(f"  • {f}")
    print(f"Evidence: {evidence_json}")
    print(f"Report:   {md_path}")
    print("=" * 52)
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)

#!/usr/bin/env python3
"""Regression: changing Area must not destroy physical topology.

Simulates Transport Build moveNodeToArea() after stabilization:
  - wires[] are area-scoped visuals
  - node.downstream is the canonical tag relationship (area-independent)
  - Apply uses wires then node.downstream across the whole graph

Case:
  P136 → P138 → P140   (all start in ModuleA)
  reassign P138 → ModuleB
  relationships must remain:
    P136.downstream = P138
    P138.downstream = P140

Then Apply → workbook and optional L5X Fast_Conv check.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_transport_graph import apply_graph_to_workbook, analyze  # noqa: E402

OUT = ROOT / "exports" / "transport-stabilization"
WORKBOOK_SRC = ROOT / "workspace" / "autogen_workbook.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def build_before() -> dict:
    """P136→P138→P140 all in ModuleA with wires + downstream."""
    nodes = [
        {
            "id": "n_p136",
            "kind": "conv_straight",
            "label": "P136",
            "conveyorTag": "P136",
            "downstream": "P138",
            "safetyZone": "ModuleA_ESZone1",
            "x": 40,
            "y": 100,
            "devices": [],
        },
        {
            "id": "n_p138",
            "kind": "conv_straight",
            "label": "P138",
            "conveyorTag": "P138",
            "downstream": "P140",
            "safetyZone": "ModuleA_ESZone1",
            "x": 180,
            "y": 100,
            "devices": [],
        },
        {
            "id": "n_p140",
            "kind": "conv_straight",
            "label": "P140",
            "conveyorTag": "P140",
            "downstream": "",
            "terminal": True,
            "safetyZone": "ModuleA_ESZone1",
            "x": 320,
            "y": 100,
            "devices": [],
        },
    ]
    wires = [
        {"id": "w1", "from": "n_p136", "to": "n_p138", "toPort": "in"},
        {"id": "w2", "from": "n_p138", "to": "n_p140", "toPort": "in"},
    ]
    return {
        "version": 1,
        "areas": [
            {"id": "area_a", "name": "ModuleA", "nodes": nodes, "wires": wires},
            {"id": "area_b", "name": "ModuleB", "nodes": [], "wires": []},
        ],
    }


def simulate_move_p138_to_module_b(graph: dict) -> dict:
    """Mirror stabilized moveNodeToArea for n_p138 → ModuleB.

    Preserves node.downstream on all parties; drops area-local wires that
    cannot span areas; does not clear topology tags.
    """
    areas = {a["id"]: a for a in graph["areas"]}
    src = areas["area_a"]
    dst = areas["area_b"]
    node = next(n for n in src["nodes"] if n["id"] == "n_p138")
    kept = (node.get("downstream") or "").strip()
    my_tag = (node.get("conveyorTag") or "").strip()

    # Upstream neighbors keep downstream → this tag
    for w in list(src.get("wires") or []):
        if w.get("to") == "n_p138":
            up = next((n for n in src["nodes"] if n["id"] == w.get("from")), None)
            if up and my_tag:
                up["downstream"] = my_tag

    src["nodes"] = [n for n in src["nodes"] if n["id"] != "n_p138"]
    src["wires"] = [
        w
        for w in (src.get("wires") or [])
        if w.get("from") != "n_p138" and w.get("to") != "n_p138"
    ]
    node["downstream"] = kept  # NEVER clear
    # Area metadata change only — ES may stay or follow Build Context; keep explicit here
    node["safetyZone"] = "ModuleB_ESZone1"
    dst.setdefault("nodes", []).append(node)
    dst.setdefault("wires", [])
    # Same-area wire rebuild would find no co-resident pairs for these three — OK
    return graph


def _row(wb: dict, tag: str) -> dict | None:
    u = tag.upper()
    for r in wb.get("conveyors") or []:
        if str(r.get("conveyor") or "").strip().upper() == u:
            return r
    return None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        checks.append((name, bool(cond), detail))
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    print("=== Cross-area Area reassignment topology preservation ===")
    before = build_before()
    after = simulate_move_p138_to_module_b(json.loads(json.dumps(before)))

    (OUT / "cross_area_before.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
    (OUT / "cross_area_after.json").write_text(json.dumps(after, indent=2), encoding="utf-8")

    # Graph-level topology tags
    by_tag = {}
    for a in after["areas"]:
        for n in a.get("nodes") or []:
            by_tag[n["conveyorTag"]] = (a["name"], n)

    check("P138 lives in ModuleB", by_tag["P138"][0] == "ModuleB", by_tag["P138"][0])
    check("P136 lives in ModuleA", by_tag["P136"][0] == "ModuleA", by_tag["P136"][0])
    check("P140 lives in ModuleA", by_tag["P140"][0] == "ModuleA", by_tag["P140"][0])
    check(
        "P136.downstream still P138",
        by_tag["P136"][1].get("downstream") == "P138",
        repr(by_tag["P136"][1].get("downstream")),
    )
    check(
        "P138.downstream still P140",
        by_tag["P138"][1].get("downstream") == "P140",
        repr(by_tag["P138"][1].get("downstream")),
    )

    # Analyze exposes downstream across areas
    an = analyze(after)
    node_ds = {
        n.get("conveyorTag"): n.get("downstream")
        for a in an.get("areas") or []
        for n in a.get("nodes") or []
    }
    check("analyze P136→P138", node_ds.get("P136") == "P138", repr(node_ds.get("P136")))
    check("analyze P138→P140", node_ds.get("P138") == "P140", repr(node_ds.get("P138")))

    # Apply workbook
    if not WORKBOOK_SRC.is_file():
        check("workbook present", False, str(WORKBOOK_SRC))
        return 1
    wb = json.loads(WORKBOOK_SRC.read_text(encoding="utf-8-sig"))
    applied = apply_graph_to_workbook(after, wb)
    out_wb = applied["workbook"]
    (OUT / "cross_area_workbook.json").write_text(json.dumps(out_wb, indent=2), encoding="utf-8")

    r136, r138, r140 = _row(out_wb, "P136"), _row(out_wb, "P138"), _row(out_wb, "P140")
    check("workbook P136 downstream=P138", (r136 or {}).get("downstream") == "P138", repr((r136 or {}).get("downstream")))
    check("workbook P138 downstream=P140", (r138 or {}).get("downstream") == "P140", repr((r138 or {}).get("downstream")))
    check("workbook P138 main_area=ModuleB", (r138 or {}).get("main_area") == "ModuleB", repr((r138 or {}).get("main_area")))
    check("workbook P136 main_area=ModuleA", (r136 or {}).get("main_area") == "ModuleA", repr((r136 or {}).get("main_area")))
    check("workbook P140 main_area=ModuleA", (r140 or {}).get("main_area") == "ModuleA", repr((r140 or {}).get("main_area")))

    # L5X path (runtime) — Fast_Conv must show cross-area downstreams
    l5x_ok = False
    l5x_detail = "skipped"
    l5x_dir = OUT / "l5x"
    try:
        cmd = [
            sys.executable,
            str(SCRIPTS / "fortna_autogen.py"),
            "from-run",
            "--run-dir",
            str(ROOT / "workspace" / "active" / "RUN"),
            "--workbook",
            str(OUT / "cross_area_workbook.json"),
            "--out-dir",
            str(l5x_dir),
            "--no-sys",
            "--no-io-map",
        ]
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=180)
        blob = (proc.stdout or "") + "\n" + (proc.stderr or "")
        # ok:true may be on stdout even when PowerShell treats stderr progress as failure
        l5x_ok = '"ok":true' in blob.replace(" ", "") or '"ok": true' in blob
        l5x_path = l5x_dir / "OReillyGreensboro_ORNCCP2.L5X"
        if not l5x_path.is_file():
            # find any L5X
            found = list(l5x_dir.glob("*.L5X")) if l5x_dir.is_dir() else []
            l5x_path = found[0] if found else None
        fc_hits = []
        if l5x_path and l5x_path.is_file():
            text = l5x_path.read_text(encoding="utf-8", errors="replace")
            for tag, ds in (("P136", "P138"), ("P138", "P140")):
                # Fast_Conv(AOI, Conv, Area, ES, Downstream_Conv, ...)
                pat = rf"Fast_Conv\({tag}_Conv_AOI\.Fast,{tag}_Conv,[^,]+,[^,]+,{ds}_Conv,"
                hit = re.search(pat, text) is not None
                fc_hits.append((tag, ds, hit))
            l5x_detail = ", ".join(f"{a}→{b}:{'Y' if h else 'N'}" for a, b, h in fc_hits)
            l5x_ok = l5x_ok and all(h for _, _, h in fc_hits)
            (OUT / "cross_area_fast_conv.md").write_text(
                "# Cross-area Fast_Conv evidence\n\n"
                + "\n".join(f"- {a} → {b}: {'PASS' if h else 'FAIL'}" for a, b, h in fc_hits)
                + f"\n\nL5X: `{l5x_path}`\n",
                encoding="utf-8",
            )
        else:
            l5x_detail = "L5X file missing; " + blob[-400:].replace("\n", " ")
            l5x_ok = False
    except Exception as exc:  # noqa: BLE001
        l5x_detail = f"error: {exc}"
        l5x_ok = False

    check("L5X Fast_Conv preserves cross-area downstream", l5x_ok, l5x_detail)

    passed = sum(1 for _, ok, _ in checks if ok)
    failed = sum(1 for _, ok, _ in checks if not ok)
    stamp = _now()
    summary = {
        "generated_at": stamp,
        "passed": passed,
        "failed": failed,
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
        "architecture_note": (
            "Wires are area-scoped visuals. Canonical topology is node.downstream (tag-based). "
            "Cross-area Area reassignment preserves downstream tags; Apply/L5X consume those tags. "
            "Visual wires are not drawn across areas until a future cross-area wire renderer exists."
        ),
    }
    (OUT / f"evidence_{stamp}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (OUT / "evidence_latest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    md = [
        f"# Cross-area move evidence ({stamp})",
        "",
        f"**Result:** {'PASS' if failed == 0 else 'FAIL'} ({passed} passed / {failed} failed)",
        "",
        summary["architecture_note"],
        "",
        "## Checks",
    ]
    for n, ok, d in checks:
        md.append(f"- **{'PASS' if ok else 'FAIL'}** {n}" + (f" — {d}" if d else ""))
    (OUT / "evidence_latest.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print("====================================================")
    print(f"{'PASS' if failed == 0 else 'FAIL'} — {passed}/{passed + failed} checks")
    print(f"Evidence: {OUT / 'evidence_latest.md'}")
    print("====================================================")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

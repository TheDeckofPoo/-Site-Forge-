#!/usr/bin/env python3
"""Transport Build UX Pass 2 — long chain, branch/merge, bulk Area/ES, Pass 1 regression.

Exit 0 on pass, non-zero on fail. Evidence written under exports/transport-ux-pass2/.
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
import subprocess
import sys
import traceback
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_transport_graph import apply_graph_to_workbook, analyze  # noqa: E402

OUT_DIR = ROOT / "exports" / "transport-ux-pass2"
WORKBOOK_SRC = ROOT / "workspace" / "autogen_workbook.json"
_TESTS_TRANSPORT = Path(__file__).resolve().parent
PASS1 = _TESTS_TRANSPORT / "test_transport_ux_pass1.py"
PARSE_JS = _TESTS_TRANSPORT / "test_transport_pass2_parse.js"


# ---------------------------------------------------------------------------
# parseChainText parity (mirrors tools/scripts/test_transport_pass2_parse.js)
# ---------------------------------------------------------------------------

_CHAIN_SPLIT = re.compile(r"[\s,;|→>\-–—]+", re.UNICODE)
_TAG_RE = re.compile(r"^(P\d+[A-Z]?)$", re.IGNORECASE)


def parse_chain_text(text: str) -> list[str]:
    """Split chain text into ordered unique P###(+suffix) tags."""
    parts = [p.strip() for p in _CHAIN_SPLIT.split(str(text or "")) if p.strip()]
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        m = _TAG_RE.match(p)
        if not m:
            continue
        tag = m.group(1).upper()
        if tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
    return out


def _conv_by_tag(wb: dict, tag: str) -> dict | None:
    u = tag.upper()
    for row in wb.get("conveyors") or []:
        if str(row.get("conveyor") or "").strip().upper() == u:
            return row
    return None


def _load_workbook_copy(dest: Path) -> tuple[dict, str]:
    if not WORKBOOK_SRC.is_file():
        raise FileNotFoundError(f"missing workbook: {WORKBOOK_SRC}")
    wb = json.loads(WORKBOOK_SRC.read_text(encoding="utf-8-sig"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(wb, indent=2), encoding="utf-8")
    return wb, f"copied from {WORKBOOK_SRC.as_posix()}"


def build_long_chain_graph() -> dict:
    """P100→P102→…→P118 (even), Area Test_Area, safetyZone=Test_ESZone2."""
    tags = [f"P{n}" for n in range(100, 119, 2)]
    nodes = []
    wires = []
    for i, tag in enumerate(tags):
        nid = f"n_{tag.lower()}"
        nxt = tags[i + 1] if i + 1 < len(tags) else ""
        nodes.append({
            "id": nid,
            "kind": "conv_straight",
            "label": tag,
            "conveyorTag": tag,
            "downstream": nxt,
            "safetyZone": "Test_ESZone2",
            "x": 40 + i * 160,
            "y": 100,
            "rotation": 0,
            "inPorts": 1,
            "devices": [],
        })
        if nxt:
            wires.append({
                "id": f"w_{i}",
                "from": nid,
                "to": f"n_{nxt.lower()}",
                "toPort": "in",
            })
    return {
        "version": 1,
        "areas": [
            {
                "id": "area_test_area",
                "name": "Test_Area",
                "nodes": nodes,
                "wires": wires,
            }
        ],
    }


def build_branch_merge_graph() -> dict:
    """P136→P138→P406←P402, P406→P408, P406 asMerge, Area Test_ModuleB."""
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
                        "safetyZone": "Test_ModuleB_ESZone1",
                        "x": 40,
                        "y": 80,
                        "rotation": 0,
                        "inPorts": 1,
                        "devices": [
                            {"kind": "photoeye", "tag": "PE136_P", "roles": ["exit", "jam"]}
                        ],
                    },
                    {
                        "id": "n_p138",
                        "kind": "conv_straight",
                        "label": "P138",
                        "conveyorTag": "P138",
                        "downstream": "P406",
                        "safetyZone": "Test_ModuleB_ESZone1",
                        "x": 220,
                        "y": 80,
                        "rotation": 0,
                        "inPorts": 1,
                        "devices": [
                            {"kind": "photoeye", "tag": "PE138_P", "roles": ["exit", "jam"]}
                        ],
                    },
                    {
                        "id": "n_p402",
                        "kind": "conv_straight",
                        "label": "P402",
                        "conveyorTag": "P402",
                        "downstream": "P406",
                        "safetyZone": "Test_ModuleB_ESZone1",
                        "x": 220,
                        "y": 220,
                        "rotation": 0,
                        "inPorts": 1,
                        "devices": [
                            {"kind": "photoeye", "tag": "PE402_P", "roles": ["exit", "jam"]}
                        ],
                    },
                    {
                        "id": "n_p406",
                        "kind": "conv_straight",
                        "label": "P406",
                        "conveyorTag": "P406",
                        "downstream": "P408",
                        "asMerge": True,
                        "safetyZone": "Test_ModuleB_ESZone1",
                        "x": 400,
                        "y": 140,
                        "rotation": 0,
                        "inPorts": 2,
                        "devices": [],
                    },
                    {
                        "id": "n_p408",
                        "kind": "conv_straight",
                        "label": "P408",
                        "conveyorTag": "P408",
                        "downstream": "",
                        "safetyZone": "Test_ModuleB_ESZone1",
                        "x": 580,
                        "y": 140,
                        "rotation": 0,
                        "inPorts": 1,
                        "devices": [],
                    },
                ],
                "wires": [
                    {"id": "w1", "from": "n_p136", "to": "n_p138", "toPort": "in"},
                    {"id": "w2", "from": "n_p138", "to": "n_p406", "toPort": "in0"},
                    {"id": "w3", "from": "n_p402", "to": "n_p406", "toPort": "in1"},
                    {"id": "w4", "from": "n_p406", "to": "n_p408", "toPort": "in"},
                ],
            }
        ],
    }


def build_lanes3_graph() -> dict:
    """Topology merge with 3 inbound lanes — generation not yet supported."""
    return {
        "version": 1,
        "areas": [
            {
                "id": "a_lanes3",
                "name": "Test_Lanes3",
                "nodes": [
                    {
                        "id": "n_a",
                        "kind": "conv_straight",
                        "conveyorTag": "P910",
                        "label": "P910",
                        "devices": [],
                    },
                    {
                        "id": "n_b",
                        "kind": "conv_straight",
                        "conveyorTag": "P911",
                        "label": "P911",
                        "devices": [],
                    },
                    {
                        "id": "n_c",
                        "kind": "conv_straight",
                        "conveyorTag": "P912",
                        "label": "P912",
                        "devices": [],
                    },
                    {
                        "id": "n_d",
                        "kind": "conv_straight",
                        "conveyorTag": "P913",
                        "label": "P913",
                        "asMerge": True,
                        "inPorts": 3,
                        "devices": [],
                    },
                ],
                "wires": [
                    {"from": "n_a", "to": "n_d", "toPort": "in0"},
                    {"from": "n_b", "to": "n_d", "toPort": "in1"},
                    {"from": "n_c", "to": "n_d", "toPort": "in2"},
                ],
            }
        ],
    }


def build_bulk_area_graph(
    tags: list[str],
    area_name: str,
    safety_zone: str,
) -> dict:
    nodes = []
    for i, tag in enumerate(tags):
        nodes.append({
            "id": f"n_{tag.lower()}",
            "kind": "conv_straight",
            "label": tag,
            "conveyorTag": tag,
            "downstream": "",
            "safetyZone": safety_zone,
            "x": 40 + i * 120,
            "y": 80,
            "rotation": 0,
            "inPorts": 1,
            "devices": [],
        })
    return {
        "version": 1,
        "areas": [
            {
                "id": f"area_{area_name.lower()}",
                "name": area_name,
                "nodes": nodes,
                "wires": [],
            }
        ],
    }


def _try_l5x_note(wb: dict, tags: tuple[str, ...]) -> dict:
    fields = []
    for t in tags:
        row = _conv_by_tag(wb, t) or {}
        fields.append({
            "conveyor": t,
            "downstream": row.get("downstream") or "",
            "exit_pe_tag": row.get("exit_pe_tag") or "",
            "main_area": row.get("main_area") or "",
            "safety_zone": row.get("safety_zone") or "",
        })
    attempted = False
    skipped_reason = (
        "L5X Generate path not exercised in this pass "
        "(fortna_autogen redesign out of scope); "
        "Fast_Conv-relevant workbook fields printed instead."
    )
    try:
        import fortna_autogen  # noqa: F401
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

    print("=== Transport UX Pass 2 verification ===")

    # ------------------------------------------------------------------
    # parseChainText parity (Python + optional Node JS)
    # ------------------------------------------------------------------
    print("-- parseChainText parity --")
    chain_cases = [
        ("P100, P102, P104", ["P100", "P102", "P104"]),
        ("P100→P102→P104", ["P100", "P102", "P104"]),
        ("P100 > P102 > P104", ["P100", "P102", "P104"]),
        ("P100 P102 P104", ["P100", "P102", "P104"]),
        ("p100;p102;p104", ["P100", "P102", "P104"]),
        ("P100,P100,P102", ["P100", "P102"]),
        ("P136A → P138", ["P136A", "P138"]),
        ("", []),
        ("no tags here", []),
    ]
    for text, expect in chain_cases:
        got = parse_chain_text(text)
        check(
            f"parseChainText({text!r})",
            got == expect,
            f"got={got!r}",
        )

    js_result = {"ran": False, "ok": None, "detail": "not run"}
    if PARSE_JS.is_file():
        try:
            proc = subprocess.run(
                ["node", str(PARSE_JS)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(ROOT),
            )
            js_result = {
                "ran": True,
                "ok": proc.returncode == 0,
                "detail": (proc.stdout or proc.stderr or "").strip()[-500:],
                "returncode": proc.returncode,
            }
            check(
                "Node parseChainText unit file",
                proc.returncode == 0,
                f"rc={proc.returncode}",
            )
        except FileNotFoundError:
            js_result = {"ran": False, "ok": None, "detail": "node not on PATH"}
            check("Node parseChainText unit file", True, "skipped — node not on PATH")
        except Exception as exc:
            js_result = {"ran": True, "ok": False, "detail": str(exc)}
            check("Node parseChainText unit file", False, str(exc))
    else:
        check("Node parseChainText unit file", True, "skipped — JS file missing")

    # ------------------------------------------------------------------
    # A — Long chain
    # ------------------------------------------------------------------
    print("-- A: Long chain --")
    chain_tags = [f"P{n}" for n in range(100, 119, 2)]
    check("long chain has 10 tags", len(chain_tags) == 10, f"count={len(chain_tags)}")

    graph_a = build_long_chain_graph()
    graph_a_path = OUT_DIR / "long_chain_graph.json"
    graph_a_path.write_text(json.dumps(graph_a, indent=2), encoding="utf-8")

    # Positions monotonic in graph JSON
    xs = [n.get("x") for n in graph_a["areas"][0]["nodes"]]
    check(
        "graph positions x increasing",
        all(xs[i] < xs[i + 1] for i in range(len(xs) - 1)),
        f"xs={xs}",
    )

    analysis_a = analyze(graph_a)
    node_sz = {
        (n.get("conveyorTag") or "").upper(): (n.get("safetyZone") or "")
        for a in (analysis_a.get("areas") or [])
        for n in (a.get("nodes") or [])
    }
    check(
        "analyze nodes expose safetyZone",
        all(node_sz.get(t) == "Test_ESZone2" for t in chain_tags),
        f"sample P100={node_sz.get('P100')!r}",
    )

    out_wb_a = OUT_DIR / "autogen_workbook_long_chain.json"
    wb_a, wb_src = _load_workbook_copy(out_wb_a)
    print(f"Workbook source: {wb_src}")
    applied_a = apply_graph_to_workbook(graph_a, wb_a)
    wb_a2 = applied_a["workbook"]
    out_wb_a.write_text(json.dumps(wb_a2, indent=2), encoding="utf-8")

    area_rows = [
        r
        for r in (wb_a2.get("conveyors") or [])
        if str(r.get("main_area") or "").strip() == "Test_Area"
        and str(r.get("conveyor") or "").strip().upper() in {t.upper() for t in chain_tags}
    ]
    check(
        "10 conveyors in Test_Area",
        len(area_rows) == 10,
        f"count={len(area_rows)} tags={[r.get('conveyor') for r in area_rows]}",
    )

    ds_ok = 0
    for i in range(len(chain_tags) - 1):
        src, dst = chain_tags[i], chain_tags[i + 1]
        row = _conv_by_tag(wb_a2, src)
        got = (row.get("downstream") if row else None) or ""
        ok = row is not None and str(got).upper() == dst.upper()
        if ok:
            ds_ok += 1
        check(
            f"workbook {src} downstream={dst}",
            ok,
            f"got={got!r}",
        )
    check("9 downstream relationships", ds_ok == 9, f"ds_ok={ds_ok}")

    for t in chain_tags:
        row = _conv_by_tag(wb_a2, t)
        sz = (row.get("safety_zone") if row else None) or ""
        check(
            f"workbook {t} safety_zone=Test_ESZone2",
            row is not None and sz == "Test_ESZone2",
            f"got={sz!r}",
        )

    # ------------------------------------------------------------------
    # B — Branch / Merge
    # ------------------------------------------------------------------
    print("-- B: Branch/Merge --")
    graph_b = build_branch_merge_graph()
    graph_b_path = OUT_DIR / "branch_merge_graph.json"
    graph_b_path.write_text(json.dumps(graph_b, indent=2), encoding="utf-8")

    analysis_b = analyze(graph_b)
    merges_b = analysis_b.get("merges_2to1") or []
    check(
        "analyze detects asMerge topology merge",
        len(merges_b) == 1,
        f"count={len(merges_b)}",
    )
    if merges_b:
        m0 = merges_b[0]
        lanes_set = {
            str(m0.get("lane_a") or "").upper(),
            str(m0.get("lane_b") or "").upper(),
        }
        check(
            "analyze merge lanes {P138,P402} discharge P406",
            lanes_set == {"P138", "P402"}
            and str(m0.get("discharge") or "").upper() == "P406"
            and str(m0.get("hold_mode") or "") == "runhold",
            f"lane_a={m0.get('lane_a')!r} lane_b={m0.get('lane_b')!r} "
            f"discharge={m0.get('discharge')!r} hold={m0.get('hold_mode')!r}",
        )

    out_wb_b = OUT_DIR / "autogen_workbook_branch_merge.json"
    wb_b, _ = _load_workbook_copy(out_wb_b)
    applied_b = apply_graph_to_workbook(graph_b, wb_b)
    wb_b2 = applied_b["workbook"]
    out_wb_b.write_text(json.dumps(wb_b2, indent=2), encoding="utf-8")

    expect_ds_b = {
        "P136": "P138",
        "P138": "P406",
        "P402": "P406",
        "P406": "P408",
    }
    for src, dst in expect_ds_b.items():
        row = _conv_by_tag(wb_b2, src)
        got = (row.get("downstream") if row else None) or ""
        check(
            f"workbook {src} downstream={dst}",
            row is not None and str(got).upper() == dst.upper(),
            f"got={got!r}",
        )

    all_merges = list(wb_b2.get("merges_2to1") or [])
    relevant = [
        m
        for m in all_merges
        if str(m.get("discharge") or m.get("name") or "").strip().upper() == "P406"
        and (
            m.get("source") == "transport_build_graph"
            or str(m.get("area") or "") == "Test_ModuleB"
        )
    ]
    tb_merges = [m for m in relevant if m.get("source") == "transport_build_graph"]
    if tb_merges:
        relevant = tb_merges
    check(
        "one merges_2to1 row for P406",
        len(relevant) == 1,
        f"count={len(relevant)}",
    )
    if relevant:
        m = relevant[0]
        lane_set = {
            str(m.get("lane_a") or "").upper(),
            str(m.get("lane_b") or "").upper(),
        }
        check(
            "merge lane_a/lane_b == {P138,P402}",
            lane_set == {"P138", "P402"},
            f"lane_a={m.get('lane_a')!r} lane_b={m.get('lane_b')!r}",
        )
        check(
            "merge discharge=P406 hold_mode=runhold",
            str(m.get("discharge") or "").upper() == "P406"
            and str(m.get("hold_mode") or "") == "runhold",
            f"discharge={m.get('discharge')!r} hold={m.get('hold_mode')!r}",
        )

    # lanes > 2 flag on merge plan (analyze areas[].merges)
    lanes3 = analyze(build_lanes3_graph())
    plans = []
    for a in lanes3.get("areas") or []:
        plans.extend(a.get("merges") or [])
    check("lanes>2 merge plan present", len(plans) == 1, f"count={len(plans)}")
    if plans:
        p = plans[0]
        check(
            "lanes>2 merge_generation_supported=False",
            p.get("merge_generation_supported") is False and int(p.get("lanes") or 0) > 2,
            f"supported={p.get('merge_generation_supported')!r} lanes={p.get('lanes')!r}",
        )
        check(
            "lanes>2 note CONFIGURATION REQUIRED",
            "CONFIGURATION REQUIRED" in str(p.get("note") or ""),
            f"note={p.get('note')!r}",
        )

    l5x = _try_l5x_note(wb_b2, ("P136", "P138", "P402", "P406", "P408"))
    print(f"  L5X: {l5x['l5x_status']} — {l5x['reason']}")
    for f in l5x["fast_conv_fields"]:
        print(
            f"    Fast_Conv {f['conveyor']}: downstream={f['downstream']!r} "
            f"exit_pe_tag={f['exit_pe_tag']!r} main_area={f['main_area']!r} "
            f"safety_zone={f['safety_zone']!r}"
        )

    # ------------------------------------------------------------------
    # C — Bulk Area / ES + undo via re-apply
    # ------------------------------------------------------------------
    print("-- C: Bulk Area/ES --")
    bulk_tags = ["P100", "P102", "P104", "P106", "P110"]
    out_wb_c = OUT_DIR / "autogen_workbook_bulk_area.json"
    wb_c, _ = _load_workbook_copy(out_wb_c)

    # Snapshot "previous" graph (baseline area/ES) then apply bulk change
    prev_graph = build_bulk_area_graph(bulk_tags, "Test_Bulk_Prev", "Test_Bulk_Prev_ESZone1")
    prev_path = OUT_DIR / "bulk_prev_graph.json"
    prev_path.write_text(json.dumps(prev_graph, indent=2), encoding="utf-8")
    applied_prev = apply_graph_to_workbook(prev_graph, wb_c)
    wb_prev = applied_prev["workbook"]
    snapshot_prev = deepcopy(prev_graph)

    for t in bulk_tags:
        row = _conv_by_tag(wb_prev, t)
        check(
            f"prev {t} main_area=Test_Bulk_Prev",
            row is not None and (row.get("main_area") or "") == "Test_Bulk_Prev",
            f"main_area={(row or {}).get('main_area')!r}",
        )
        check(
            f"prev {t} safety_zone=Test_Bulk_Prev_ESZone1",
            row is not None
            and (row.get("safety_zone") or "") == "Test_Bulk_Prev_ESZone1",
            f"safety_zone={(row or {}).get('safety_zone')!r}",
        )

    new_graph = build_bulk_area_graph(bulk_tags, "Test_Bulk_New", "Test_ESZone2")
    new_path = OUT_DIR / "bulk_new_graph.json"
    new_path.write_text(json.dumps(new_graph, indent=2), encoding="utf-8")
    applied_new = apply_graph_to_workbook(new_graph, wb_prev)
    wb_new = applied_new["workbook"]

    for t in bulk_tags:
        row = _conv_by_tag(wb_new, t)
        check(
            f"bulk {t} main_area=Test_Bulk_New",
            row is not None and (row.get("main_area") or "") == "Test_Bulk_New",
            f"main_area={(row or {}).get('main_area')!r}",
        )
        check(
            f"bulk {t} safety_zone=Test_ESZone2",
            row is not None and (row.get("safety_zone") or "") == "Test_ESZone2",
            f"safety_zone={(row or {}).get('safety_zone')!r}",
        )

    # Undo: re-apply previous graph snapshot
    applied_undo = apply_graph_to_workbook(snapshot_prev, wb_new)
    wb_undo = applied_undo["workbook"]
    out_wb_c.write_text(json.dumps(wb_undo, indent=2), encoding="utf-8")

    for t in bulk_tags:
        row = _conv_by_tag(wb_undo, t)
        check(
            f"undo {t} main_area=Test_Bulk_Prev",
            row is not None and (row.get("main_area") or "") == "Test_Bulk_Prev",
            f"main_area={(row or {}).get('main_area')!r}",
        )
        check(
            f"undo {t} safety_zone=Test_Bulk_Prev_ESZone1",
            row is not None
            and (row.get("safety_zone") or "") == "Test_Bulk_Prev_ESZone1",
            f"safety_zone={(row or {}).get('safety_zone')!r}",
        )

    # ------------------------------------------------------------------
    # D — Pass 1 regression
    # ------------------------------------------------------------------
    print("-- D: Pass 1 regression --")
    check("pass1 script exists", PASS1.is_file(), str(PASS1))
    pass1_result = {"ran": False, "ok": False, "detail": ""}
    if PASS1.is_file():
        proc = subprocess.run(
            [sys.executable, str(PASS1)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(ROOT),
        )
        pass1_result = {
            "ran": True,
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-800:],
            "stderr_tail": (proc.stderr or "")[-400:],
        }
        check(
            "Pass 1 regression PASS",
            proc.returncode == 0,
            f"rc={proc.returncode}",
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr)

    passed = sum(1 for c in checks if c["ok"])
    failed = sum(1 for c in checks if not c["ok"])
    ok = failed == 0

    evidence = {
        "ok": ok,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stamp": stamp,
        "workbook_source": wb_src,
        "checks": checks,
        "failures": failures,
        "pass_count": passed,
        "fail_count": failed,
        "parse_js": js_result,
        "pass1": pass1_result,
        "l5x": l5x,
        "artifacts": {
            "long_chain_graph": str(graph_a_path),
            "long_chain_workbook": str(out_wb_a),
            "branch_merge_graph": str(graph_b_path),
            "branch_merge_workbook": str(out_wb_b),
            "bulk_workbook": str(out_wb_c),
        },
        "apply_summaries": {
            "long_chain": applied_a.get("summary"),
            "branch_merge": applied_b.get("summary"),
            "bulk_prev": applied_prev.get("summary"),
            "bulk_new": applied_new.get("summary"),
            "bulk_undo": applied_undo.get("summary"),
        },
    }
    evidence_json = OUT_DIR / f"evidence_{stamp}.json"
    evidence_json.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    (OUT_DIR / "evidence_latest.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf-8"
    )

    md_lines = [
        f"# Transport UX Pass 2 evidence ({stamp})",
        "",
        f"**Result:** {'PASS' if ok else 'FAIL'} ({passed} passed / {failed} failed)",
        "",
        f"- Workbook source: {wb_src}",
        f"- Long chain graph: `{graph_a_path.name}`",
        f"- Branch/merge graph: `{graph_b_path.name}`",
        "",
        "## Checks",
    ]
    for c in checks:
        mark = "PASS" if c["ok"] else "FAIL"
        md_lines.append(
            f"- **{mark}** {c['name']}"
            + (f" — {c['detail']}" if c["detail"] else "")
        )
    md_lines.extend([
        "",
        "## Fast_Conv workbook fields (L5X skipped)",
        f"- Status: {l5x['l5x_status']}",
        f"- Reason: {l5x['reason']}",
    ])
    for f in l5x["fast_conv_fields"]:
        md_lines.append(
            f"- `{f['conveyor']}` downstream=`{f['downstream']}` "
            f"exit_pe=`{f['exit_pe_tag']}` area=`{f['main_area']}` "
            f"safety=`{f['safety_zone']}`"
        )
    if failures:
        md_lines.append("")
        md_lines.append("## Failures")
        md_lines.extend(f"- {f}" for f in failures)
    md_path = OUT_DIR / f"evidence_{stamp}.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    (OUT_DIR / "evidence_latest.md").write_text(
        "\n".join(md_lines) + "\n", encoding="utf-8"
    )

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

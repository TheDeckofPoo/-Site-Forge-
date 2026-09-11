#!/usr/bin/env python3
"""Autogen Accuracy Pass 1 — area / safety-zone fidelity tests.

Two Greensboro-related scores are reported separately and must not be conflated:

1) REFERENCE-SEEDED FIDELITY TEST (plumbing / diagnostic only)
   - Copies area/safety from the finished reference L5X into a temporary workbook
   - Proves Autogen preserves metadata when correctly supplied
   - Must NOT be reported as end-to-end Site Forge workflow accuracy

2) ACTUAL WORKFLOW BACKTEST (truthful baseline)
   - Uses workspace/active/RUN + workspace/autogen_workbook.json as-is
   - Finished L5X is comparator reference only (never repairs the workbook)
   - Reports conveyor coverage / area / safety / downstream vs finished PLC
   - Does not attempt to improve those scores in this pass
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_autogen import (  # noqa: E402
    DEFAULT_LIBRARY,
    AutogenInput,
    ConveyorRow,
    generate,
    load_from_run,
)
from fortna_l5x_compare import extract_l5x, run_compare  # noqa: E402
from fortna_workbook import apply_workbook_to_input  # noqa: E402

OUT = ROOT / "exports" / "l5x-backtest" / "area-safety-fidelity"
LIB = Path(DEFAULT_LIBRARY)
REF_L5X = Path(
    r"C:\Users\curtiskricke\Desktop\WIth GPT\Folder to GPT\ORLY_GreensboroPLC2_NC_Finished.L5X"
)
WORKBOOK_SRC = ROOT / "workspace" / "autogen_workbook.json"
RUN_DIR = ROOT / "workspace" / "active" / "RUN"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _check(
    checks: list[tuple[str, bool, str]], name: str, cond: bool, detail: str = ""
) -> None:
    checks.append((name, bool(cond), detail))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# Synthetic plumbing (unchanged intent)
# ---------------------------------------------------------------------------

def test_synthetic_two_areas() -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    print("-- synthetic AreaA / AreaB --")
    inp = AutogenInput(
        project_name="FidelityTest_CTRL1",
        processor="1756-L83E",
        areas=["CTRL1_Area"],
        safety_zones=["CTRL1_ESZone1"],
        conveyors=[
            ConveyorRow(
                number=1,
                conveyor="P10",
                main_area="CTRL1_Area",
                safety_zone="CTRL1_ESZone1",
                type="Transport with MS",
                motor_starter="Yes",
            ),
            ConveyorRow(
                number=2,
                conveyor="P20",
                main_area="CTRL1_Area",
                safety_zone="CTRL1_ESZone1",
                type="Transport with MS",
                motor_starter="Yes",
            ),
        ],
    )
    wb = {
        "conveyors": [
            {
                "conveyor": "P10",
                "include": True,
                "main_area": "AreaA",
                "safety_zone": "ESZone1",
                "type": "Transport with MS",
            },
            {
                "conveyor": "P20",
                "include": True,
                "main_area": "AreaB",
                "safety_zone": "ESZone2",
                "type": "Transport with MS",
            },
        ],
        "options": {"safety_zones": ["ESZone1", "ESZone2"]},
    }
    inp2 = apply_workbook_to_input(inp, wb)
    c10 = next(c for c in inp2.conveyors if c.conveyor == "P10")
    c20 = next(c for c in inp2.conveyors if c.conveyor == "P20")
    _check(checks, "P10 main_area=AreaA after apply", c10.main_area == "AreaA", c10.main_area)
    _check(checks, "P10 safety=ESZone1 after apply", c10.safety_zone == "ESZone1", c10.safety_zone)
    _check(checks, "P20 main_area=AreaB after apply", c20.main_area == "AreaB", c20.main_area)
    _check(checks, "P20 safety=ESZone2 after apply", c20.safety_zone == "ESZone2", c20.safety_zone)
    _check(checks, "AreaA in inp.areas", "AreaA" in (inp2.areas or []), str(inp2.areas))
    _check(checks, "AreaB in inp.areas", "AreaB" in (inp2.areas or []), str(inp2.areas))
    _check(
        checks,
        "ESZone2 preserved in inp.safety_zones (not collapsed to ESZone1)",
        any(z == "ESZone2" for z in (inp2.safety_zones or [])),
        str(inp2.safety_zones),
    )
    _check(
        checks,
        "controller default CTRL1_Area does not overwrite P10",
        c10.main_area != "CTRL1_Area",
        c10.main_area,
    )

    out_dir = OUT / "synthetic"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not LIB.is_file():
        _check(checks, "library present", False, str(LIB))
        return checks
    result = generate(inp2, LIB, out_dir)
    _check(checks, "generate ok", bool(result.get("ok")), str(result.get("error") or result.get("l5x")))
    l5x_path = Path(result.get("l5x") or "")
    _check(checks, "l5x written", l5x_path.is_file(), str(l5x_path))
    if not l5x_path.is_file():
        return checks

    inv = extract_l5x(l5x_path)
    r10, r20 = inv.fast_conv.get("P10"), inv.fast_conv.get("P20")
    _check(checks, "Fast_Conv P10 area=AreaA", r10 is not None and r10.area == "AreaA", getattr(r10, "area", None))
    _check(
        checks,
        "Fast_Conv P10 safety=ESZone1",
        r10 is not None and r10.safety_zone == "ESZone1",
        getattr(r10, "safety_zone", None),
    )
    _check(checks, "Fast_Conv P20 area=AreaB", r20 is not None and r20.area == "AreaB", getattr(r20, "area", None))
    _check(
        checks,
        "Fast_Conv P20 safety=ESZone2",
        r20 is not None and r20.safety_zone == "ESZone2",
        getattr(r20, "safety_zone", None),
    )
    progs = set(inv.programs)
    _check(
        checks,
        "separate AreaA Fast program",
        any("AreaA" in p and p.endswith("_Fast") for p in progs),
        str(sorted(progs)),
    )
    _check(
        checks,
        "separate AreaB Fast program",
        any("AreaB" in p and p.endswith("_Fast") for p in progs),
        str(sorted(progs)),
    )
    s10 = inv.slow_flt.get("P10")
    _check(
        checks,
        "Slow_Flt P10 area=AreaA",
        s10 is not None and s10.area == "AreaA",
        getattr(s10, "area", None),
    )
    return checks


# ---------------------------------------------------------------------------
# REFERENCE-SEEDED FIDELITY TEST (plumbing only — not E2E accuracy)
# ---------------------------------------------------------------------------

def _workbook_from_reference_fast_conv(ref_path: Path, base_wb: dict) -> dict:
    """DIAGNOSTIC ONLY: copy area/safety from reference Fast_Conv into a temp workbook.

    This must never be used as the Site Forge actual-workflow accuracy score.
    """
    ref = extract_l5x(ref_path)
    wb = deepcopy(base_wb)
    by = {
        str(r.get("conveyor") or "").strip().upper(): r
        for r in (wb.get("conveyors") or [])
        if str(r.get("conveyor") or "").strip()
    }
    for key, rec in ref.fast_conv.items():
        row = by.get(key)
        if row is None:
            row = {
                "conveyor": rec.conveyor,
                "include": True,
                "type": "Transport with MS",
            }
            wb.setdefault("conveyors", []).append(row)
            by[key] = row
        row["main_area"] = rec.area
        row["safety_zone"] = rec.safety_zone
        row["include"] = True
    areas: list[dict] = []
    seen: set[str] = set()
    for r in wb.get("conveyors") or []:
        name = (r.get("main_area") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        areas.append({"name": name, "safety_zone": "", "conveyor_count": 0})
    wb["areas"] = areas
    opts = wb.get("options") if isinstance(wb.get("options"), dict) else {}
    opts["areas"] = [a["name"] for a in areas]
    opts["safety_zones"] = sorted(
        {
            str(r.get("safety_zone") or "").strip()
            for r in (wb.get("conveyors") or [])
            if str(r.get("safety_zone") or "").strip()
        }
    )
    wb["options"] = opts
    return wb


def test_reference_seeded_plumbing() -> tuple[list[tuple[str, bool, str]], dict]:
    """REFERENCE-SEEDED FIDELITY TEST — Autogen preserves supplied workbook metadata."""
    checks: list[tuple[str, bool, str]] = []
    metrics = {"area_ok": 0, "area_total": 0, "safety_ok": 0, "safety_total": 0}
    print("-- REFERENCE-SEEDED FIDELITY TEST (plumbing only; not E2E workflow) --")

    if not REF_L5X.is_file():
        _check(checks, "reference L5X present", False, str(REF_L5X))
        return checks, metrics
    if not WORKBOOK_SRC.is_file():
        _check(checks, "workbook present", False, str(WORKBOOK_SRC))
        return checks, metrics
    if not LIB.is_file():
        _check(checks, "library present", False, str(LIB))
        return checks, metrics
    if not RUN_DIR.is_dir():
        _check(checks, "RUN dir present", False, str(RUN_DIR))
        return checks, metrics

    base_wb = json.loads(WORKBOOK_SRC.read_text(encoding="utf-8-sig"))
    wb = _workbook_from_reference_fast_conv(REF_L5X, base_wb)
    wb_path = OUT / "reference_seeded_workbook.json"
    OUT.mkdir(parents=True, exist_ok=True)
    wb_path.write_text(json.dumps(wb, indent=2), encoding="utf-8")

    sample = next(r for r in wb["conveyors"] if str(r.get("conveyor")).upper() == "P138")
    _check(
        checks,
        "[plumbing] seeded workbook P138 area is non-controller",
        (sample.get("main_area") or "") not in ("", "ORNCCP2_Area"),
        sample.get("main_area"),
    )

    inp = load_from_run(RUN_DIR, processor="1756-L83E")
    inp = apply_workbook_to_input(inp, wb)
    c138 = next(c for c in inp.conveyors if c.conveyor.upper() == "P138")
    _check(
        checks,
        "[plumbing] apply preserves seeded P138 area",
        c138.main_area == sample["main_area"],
        f"{c138.main_area} vs {sample['main_area']}",
    )
    _check(
        checks,
        "[plumbing] apply preserves seeded P138 safety",
        c138.safety_zone == sample["safety_zone"],
        f"{c138.safety_zone} vs {sample['safety_zone']}",
    )
    _check(
        checks,
        "[plumbing] seeded safety zone listed in inp.safety_zones",
        sample["safety_zone"] in (inp.safety_zones or []),
        str(inp.safety_zones),
    )

    gen_dir = OUT / "reference_seeded_generated"
    gen_dir.mkdir(parents=True, exist_ok=True)
    result = generate(inp, LIB, gen_dir)
    _check(checks, "[plumbing] generate ok", bool(result.get("ok")), str(result.get("error") or ""))
    gen_l5x = Path(result.get("l5x") or "")
    _check(checks, "[plumbing] l5x exists", gen_l5x.is_file(), str(gen_l5x))
    if not gen_l5x.is_file():
        return checks, metrics

    inv = extract_l5x(gen_l5x)
    # Fidelity vs the *seeded workbook* (not vs finished L5X as a workflow claim)
    area_ok = safety_ok = total = 0
    for row in wb.get("conveyors") or []:
        tag = str(row.get("conveyor") or "").strip().upper()
        if not tag:
            continue
        g = inv.fast_conv.get(tag)
        if not g:
            continue
        want_area = (row.get("main_area") or "").strip()
        want_sz = (row.get("safety_zone") or "").strip()
        if not want_area and not want_sz:
            continue
        total += 1
        if want_area:
            metrics["area_total"] += 1
            if g.area == want_area:
                metrics["area_ok"] += 1
                area_ok += 1
        if want_sz:
            metrics["safety_total"] += 1
            if g.safety_zone == want_sz:
                metrics["safety_ok"] += 1
                safety_ok += 1

    _check(
        checks,
        "[plumbing] generated area matches seeded workbook for emitted conveyors",
        metrics["area_total"] > 0 and metrics["area_ok"] == metrics["area_total"],
        f"{metrics['area_ok']}/{metrics['area_total']}",
    )
    _check(
        checks,
        "[plumbing] generated safety matches seeded workbook for emitted conveyors",
        metrics["safety_total"] > 0 and metrics["safety_ok"] == metrics["safety_total"],
        f"{metrics['safety_ok']}/{metrics['safety_total']}",
    )
    print(
        f"  Plumbing fidelity: Area {metrics['area_ok']}/{metrics['area_total']}  "
        f"Safety {metrics['safety_ok']}/{metrics['safety_total']}"
    )
    metrics["generated_l5x"] = str(gen_l5x)
    metrics["workbook"] = str(wb_path)
    metrics["label"] = "REFERENCE-SEEDED FIDELITY TEST"
    metrics["note"] = (
        "Diagnostic plumbing only. Workbook was populated from reference Fast_Conv. "
        "Do not treat as Site Forge end-to-end Greensboro accuracy."
    )
    return checks, metrics


# ---------------------------------------------------------------------------
# ACTUAL WORKFLOW BACKTEST (truthful baseline)
# ---------------------------------------------------------------------------

def test_actual_workflow_backtest() -> tuple[list[tuple[str, bool, str]], dict]:
    """ACTUAL WORKFLOW: RUN + workspace workbook as-is; finished L5X is compare-only."""
    checks: list[tuple[str, bool, str]] = []
    metrics: dict = {}
    print("-- ACTUAL WORKFLOW BACKTEST (RUN + workspace workbook; no reference seeding) --")

    if not REF_L5X.is_file():
        _check(checks, "reference L5X present (compare-only)", False, str(REF_L5X))
        return checks, metrics
    if not WORKBOOK_SRC.is_file():
        _check(checks, "workspace workbook present", False, str(WORKBOOK_SRC))
        return checks, metrics
    if not LIB.is_file():
        _check(checks, "library present", False, str(LIB))
        return checks, metrics
    if not RUN_DIR.is_dir():
        _check(checks, "RUN dir present", False, str(RUN_DIR))
        return checks, metrics

    # Load workbook exactly as Site Forge left it — never repair from finished L5X
    wb = json.loads(WORKBOOK_SRC.read_text(encoding="utf-8-sig"))
    wb_snapshot = OUT / "actual_workflow_workbook_snapshot.json"
    OUT.mkdir(parents=True, exist_ok=True)
    wb_snapshot.write_text(json.dumps(wb, indent=2), encoding="utf-8")

    # Sanity: workbook must not have been pre-seeded by this test suite's overlay file
    p138 = next(
        (r for r in (wb.get("conveyors") or []) if str(r.get("conveyor") or "").upper() == "P138"),
        None,
    )
    _check(checks, "workbook snapshot written", wb_snapshot.is_file())
    if p138 is not None:
        print(
            f"  workspace P138 main_area={p138.get('main_area')!r} "
            f"safety_zone={p138.get('safety_zone')!r} (unchanged from Site Forge)"
        )

    inp = load_from_run(RUN_DIR, processor="1756-L83E")
    inp = apply_workbook_to_input(inp, wb)

    gen_dir = OUT / "actual_workflow_generated"
    gen_dir.mkdir(parents=True, exist_ok=True)
    result = generate(inp, LIB, gen_dir)
    _check(checks, "[workflow] generate ok", bool(result.get("ok")), str(result.get("error") or ""))
    gen_l5x = Path(result.get("l5x") or "")
    _check(checks, "[workflow] l5x exists", gen_l5x.is_file(), str(gen_l5x))
    if not gen_l5x.is_file():
        return checks, metrics

    cmp_dir = OUT / "actual_workflow_vs_finished"
    cmp = run_compare(gen_l5x, REF_L5X, cmp_dir)
    m = cmp["metrics"]
    metrics = {
        "label": "ACTUAL WORKFLOW BACKTEST",
        "generated_l5x": str(gen_l5x),
        "workbook": str(WORKBOOK_SRC),
        "workbook_snapshot": str(wb_snapshot),
        "reference_l5x": str(REF_L5X),
        "conveyor_coverage": m["conveyor_coverage"],
        "area_accuracy": m["area_accuracy"],
        "safety_zone_accuracy": m["safety_zone_accuracy"],
        "downstream_accuracy": m["downstream_accuracy"],
        "note": (
            "Truthful baseline using Site Forge RUN + workspace/autogen_workbook.json. "
            "Finished L5X used only as comparator. No reference seeding / workbook repair. "
            "Scores are not optimized in this pass."
        ),
    }

    # Structural success of the test harness — not a claim that scores are high
    _check(
        checks,
        "[workflow] comparator produced area metrics",
        "area_accuracy" in m and "compared" in m["area_accuracy"],
    )
    _check(
        checks,
        "[workflow] comparator produced safety metrics",
        "safety_zone_accuracy" in m and "compared" in m["safety_zone_accuracy"],
    )
    _check(
        checks,
        "[workflow] comparator produced downstream metrics",
        "downstream_accuracy" in m and "compared" in m["downstream_accuracy"],
    )
    _check(
        checks,
        "[workflow] reference has 57 Fast_Conv conveyors (fixture sanity)",
        m["conveyor_coverage"]["reference"] == 57,
        str(m["conveyor_coverage"]["reference"]),
    )

    cc = m["conveyor_coverage"]
    aa = m["area_accuracy"]
    sa = m["safety_zone_accuracy"]
    da = m["downstream_accuracy"]
    print("  Actual workflow:")
    print(
        f"    Conveyor coverage  {cc['matched']} / {cc['reference']}   {cc['pct_of_reference']}%"
    )
    print(f"    Area accuracy      {aa['correct']} / {aa['compared']}   {aa['pct']}%")
    print(f"    Safety accuracy    {sa['correct']} / {sa['compared']}   {sa['pct']}%")
    print(f"    Downstream accuracy {da['correct']} / {da['compared']}   {da['pct']}%")
    return checks, metrics


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("=== Autogen Area/Safety Fidelity — separated scores ===")
    checks: list[tuple[str, bool, str]] = []
    checks.extend(test_synthetic_two_areas())
    plumbing_checks, plumbing = test_reference_seeded_plumbing()
    checks.extend(plumbing_checks)
    workflow_checks, workflow = test_actual_workflow_backtest()
    checks.extend(workflow_checks)

    report = {
        "generated_at": _ts(),
        "plumbing_fidelity": plumbing,
        "actual_workflow": workflow,
        "distinction": {
            "REFERENCE-SEEDED FIDELITY TEST": (
                "Proves Autogen preserves area/safety when the workbook already has "
                "correct values (seeded from finished Fast_Conv for diagnosis only)."
            ),
            "ACTUAL WORKFLOW BACKTEST": (
                "Uses real RUN + workspace/autogen_workbook.json without modification. "
                "Finished L5X is compare-only. This is the truthful Greensboro baseline."
            ),
        },
    }
    (OUT / "fidelity_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    p = plumbing
    w = workflow
    md = [
        "# Autogen Area/Safety Fidelity — Separated Scores",
        "",
        "## REFERENCE-SEEDED FIDELITY TEST (plumbing only)",
        "",
        "> **Not** the real Greensboro end-to-end accuracy score.",
        "> Workbook was temporarily populated from finished Fast_Conv area/safety args",
        "> to prove Autogen preserves supplied metadata.",
        "",
        f"Plumbing fidelity:",
        f"- Area **{p.get('area_ok', 0)} / {p.get('area_total', 0)}**",
        f"- Safety **{p.get('safety_ok', 0)} / {p.get('safety_total', 0)}**",
        "",
        "## ACTUAL WORKFLOW BACKTEST (truthful baseline)",
        "",
        "> Uses `workspace/active/RUN` + `workspace/autogen_workbook.json` as Site Forge left them.",
        "> Finished Greensboro L5X is used **only** as the comparator reference.",
        "> The workbook is never populated or repaired from the finished L5X.",
        "",
        "Actual workflow:",
    ]
    if w:
        cc = w["conveyor_coverage"]
        aa = w["area_accuracy"]
        sa = w["safety_zone_accuracy"]
        da = w["downstream_accuracy"]
        md.extend(
            [
                f"- Conveyor coverage **{cc['matched']} / {cc['reference']}** ({cc['pct_of_reference']}%)",
                f"- Area accuracy **{aa['correct']} / {aa['compared']}** ({aa['pct']}%)",
                f"- Safety accuracy **{sa['correct']} / {sa['compared']}** ({sa['pct']}%)",
                f"- Downstream accuracy **{da['correct']} / {da['compared']}** ({da['pct']}%)",
                "",
                f"Generated L5X: `{w.get('generated_l5x')}`",
                f"Workbook: `{w.get('workbook')}`",
            ]
        )
    else:
        md.append("- _(workflow backtest did not run)_")
    md.append("")
    (OUT / "fidelity_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print("")
    print("====================================================")
    print("SUMMARY (do not conflate)")
    print(
        f"Plumbing fidelity:  Area {p.get('area_ok', 0)}/{p.get('area_total', 0)}  "
        f"Safety {p.get('safety_ok', 0)}/{p.get('safety_total', 0)}"
    )
    if w:
        cc, aa, sa, da = (
            w["conveyor_coverage"],
            w["area_accuracy"],
            w["safety_zone_accuracy"],
            w["downstream_accuracy"],
        )
        print(
            f"Actual workflow:    Conveyor coverage {cc['matched']}/{cc['reference']}  "
            f"Area {aa['correct']}/{aa['compared']}  "
            f"Safety {sa['correct']}/{sa['compared']}  "
            f"Downstream {da['correct']}/{da['compared']}"
        )
    print(f"Report: {OUT / 'fidelity_report.md'}")
    print("====================================================")

    passed = sum(1 for _, ok, _ in checks if ok)
    failed = sum(1 for _, ok, _ in checks if not ok)
    print(f"{'PASS' if failed == 0 else 'FAIL'} — {passed}/{passed + failed} checks")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

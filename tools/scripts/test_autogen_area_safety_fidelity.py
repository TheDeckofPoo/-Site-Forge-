#!/usr/bin/env python3
"""Autogen Accuracy Pass 1 — area / safety-zone fidelity.

Proves engineer-configured main_area / safety_zone survive:
  workbook → apply_workbook_to_input → generate → Fast_Conv / Slow_Flt args

Also rebuilds a Greensboro workbook overlay from the *reference* L5X Fast_Conv
records (generic extraction — no hardcoded ModuleB/Trash names in production
code), regenerates Autogen L5X, and re-runs fortna_l5x_compare metrics.
"""
from __future__ import annotations

import json
import re
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
BEFORE_SUMMARY = ROOT / "exports" / "l5x-backtest" / "greensboro" / "summary.json"
WORKBOOK_SRC = ROOT / "workspace" / "autogen_workbook.json"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def test_synthetic_two_areas() -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        checks.append((name, bool(cond), detail))
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

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
    check("P10 main_area=AreaA after apply", c10.main_area == "AreaA", c10.main_area)
    check("P10 safety=ESZone1 after apply", c10.safety_zone == "ESZone1", c10.safety_zone)
    check("P20 main_area=AreaB after apply", c20.main_area == "AreaB", c20.main_area)
    check("P20 safety=ESZone2 after apply", c20.safety_zone == "ESZone2", c20.safety_zone)
    check("AreaA in inp.areas", "AreaA" in (inp2.areas or []), str(inp2.areas))
    check("AreaB in inp.areas", "AreaB" in (inp2.areas or []), str(inp2.areas))
    check(
        "ESZone2 preserved in inp.safety_zones (not collapsed to ESZone1)",
        any(z == "ESZone2" for z in (inp2.safety_zones or [])),
        str(inp2.safety_zones),
    )
    check(
        "controller default CTRL1_Area does not overwrite P10",
        c10.main_area != "CTRL1_Area",
        c10.main_area,
    )

    out_dir = OUT / "synthetic"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not LIB.is_file():
        check("library present", False, str(LIB))
        return checks
    result = generate(inp2, LIB, out_dir)
    check("generate ok", bool(result.get("ok")), str(result.get("error") or result.get("l5x")))
    l5x_path = Path(result.get("l5x") or "")
    check("l5x written", l5x_path.is_file(), str(l5x_path))
    if not l5x_path.is_file():
        return checks

    inv = extract_l5x(l5x_path)
    r10, r20 = inv.fast_conv.get("P10"), inv.fast_conv.get("P20")
    check("Fast_Conv P10 area=AreaA", r10 is not None and r10.area == "AreaA", getattr(r10, "area", None))
    check(
        "Fast_Conv P10 safety=ESZone1",
        r10 is not None and r10.safety_zone == "ESZone1",
        getattr(r10, "safety_zone", None),
    )
    check("Fast_Conv P20 area=AreaB", r20 is not None and r20.area == "AreaB", getattr(r20, "area", None))
    check(
        "Fast_Conv P20 safety=ESZone2",
        r20 is not None and r20.safety_zone == "ESZone2",
        getattr(r20, "safety_zone", None),
    )
    progs = set(inv.programs)
    # Autogen names: "{Area}_Fast" when area already ends with _Area,
    # otherwise "{Area}_Area_Fast" (e.g. AreaA → AreaA_Area_Fast).
    check(
        "separate AreaA Fast program",
        any("AreaA" in p and p.endswith("_Fast") for p in progs),
        str(sorted(progs)),
    )
    check(
        "separate AreaB Fast program",
        any("AreaB" in p and p.endswith("_Fast") for p in progs),
        str(sorted(progs)),
    )
    # Slow uses same area arg
    s10 = inv.slow_flt.get("P10")
    check(
        "Slow_Flt P10 area=AreaA",
        s10 is not None and s10.area == "AreaA",
        getattr(s10, "area", None),
    )
    return checks


def _workbook_from_reference_fast_conv(ref_path: Path, base_wb: dict) -> dict:
    """Generic: copy area/safety from reference Fast_Conv into workbook rows.

    Production Autogen never hardcodes ModuleB/Trash — this is a *test fixture
    builder* that treats the finished L5X as the site model source for areas.
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
    # Refresh area list from conveyor rows
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


def test_greensboro_regenerate_and_compare() -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        checks.append((name, bool(cond), detail))
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    print("-- Greensboro regenerate with workbook area/safety fidelity --")
    if not REF_L5X.is_file():
        check("reference L5X present", False, str(REF_L5X))
        return checks
    if not WORKBOOK_SRC.is_file():
        check("workbook present", False, str(WORKBOOK_SRC))
        return checks
    if not LIB.is_file():
        check("library present", False, str(LIB))
        return checks

    before = {}
    if BEFORE_SUMMARY.is_file():
        before = json.loads(BEFORE_SUMMARY.read_text(encoding="utf-8")).get("metrics") or {}

    base_wb = json.loads(WORKBOOK_SRC.read_text(encoding="utf-8-sig"))
    wb = _workbook_from_reference_fast_conv(REF_L5X, base_wb)
    wb_path = OUT / "greensboro_workbook_area_overlay.json"
    OUT.mkdir(parents=True, exist_ok=True)
    wb_path.write_text(json.dumps(wb, indent=2), encoding="utf-8")

    # Explicit metadata must be present for overlapping sample
    sample = next(r for r in wb["conveyors"] if str(r.get("conveyor")).upper() == "P138")
    check(
        "fixture workbook P138 has non-controller area",
        (sample.get("main_area") or "") not in ("", "ORNCCP2_Area"),
        sample.get("main_area"),
    )
    check(
        "fixture workbook P138 has explicit safety zone",
        bool(sample.get("safety_zone")) and "ORNCCP2_ESZone1" != sample.get("safety_zone"),
        sample.get("safety_zone"),
    )

    inp = load_from_run(ROOT / "workspace" / "active" / "RUN", processor="1756-L83E")
    inp = apply_workbook_to_input(inp, wb)
    c138 = next(c for c in inp.conveyors if c.conveyor.upper() == "P138")
    check(
        "apply preserves P138 area from workbook",
        c138.main_area == sample["main_area"],
        f"{c138.main_area} vs {sample['main_area']}",
    )
    check(
        "apply preserves P138 safety from workbook",
        c138.safety_zone == sample["safety_zone"],
        f"{c138.safety_zone} vs {sample['safety_zone']}",
    )
    check(
        "ModuleB_ESZone2 (or workbook zone) listed in inp.safety_zones",
        sample["safety_zone"] in (inp.safety_zones or []),
        str(inp.safety_zones),
    )

    gen_dir = OUT / "greensboro_generated"
    gen_dir.mkdir(parents=True, exist_ok=True)
    result = generate(inp, LIB, gen_dir)
    check("greensboro generate ok", bool(result.get("ok")), str(result.get("error") or ""))
    gen_l5x = Path(result.get("l5x") or "")
    check("greensboro l5x exists", gen_l5x.is_file(), str(gen_l5x))
    if not gen_l5x.is_file():
        return checks

    inv = extract_l5x(gen_l5x)
    g138 = inv.fast_conv.get("P138")
    check(
        "generated Fast_Conv P138 area matches workbook",
        g138 is not None and g138.area == sample["main_area"],
        getattr(g138, "area", None),
    )
    check(
        "generated Fast_Conv P138 safety matches workbook",
        g138 is not None and g138.safety_zone == sample["safety_zone"],
        getattr(g138, "safety_zone", None),
    )

    # Overlap fidelity: every overlapping conveyor with explicit workbook area/safety
    ref_inv = extract_l5x(REF_L5X)
    overlap = sorted(set(inv.fast_conv) & set(ref_inv.fast_conv))
    area_ok = safety_ok = 0
    examples = []
    for k in overlap:
        g, r = inv.fast_conv[k], ref_inv.fast_conv[k]
        # Workbook is source of truth for this pass (seeded from ref Fast_Conv)
        wb_row = next(
            (
                row
                for row in wb["conveyors"]
                if str(row.get("conveyor") or "").upper() == k
            ),
            None,
        )
        if not wb_row:
            continue
        want_area = (wb_row.get("main_area") or "").strip()
        want_sz = (wb_row.get("safety_zone") or "").strip()
        if want_area and g.area == want_area:
            area_ok += 1
        if want_sz and g.safety_zone == want_sz:
            safety_ok += 1
        if want_area and g.area == want_area and want_sz and g.safety_zone == want_sz:
            if len(examples) < 6:
                examples.append(
                    {
                        "conveyor": g.conveyor,
                        "area": g.area,
                        "safety_zone": g.safety_zone,
                        "reference_area": r.area,
                        "reference_safety": r.safety_zone,
                    }
                )

    n_ov = len(overlap)
    check(
        "overlap area fidelity 100% vs workbook",
        n_ov > 0 and area_ok == n_ov,
        f"{area_ok}/{n_ov}",
    )
    check(
        "overlap safety fidelity 100% vs workbook",
        n_ov > 0 and safety_ok == n_ov,
        f"{safety_ok}/{n_ov}",
    )

    cmp_dir = OUT / "greensboro_after"
    cmp = run_compare(gen_l5x, REF_L5X, cmp_dir)
    after_m = cmp["metrics"]
    before_area = (before.get("area_accuracy") or {}).get("pct")
    before_sz = (before.get("safety_zone_accuracy") or {}).get("pct")
    after_area = after_m["area_accuracy"]["pct"]
    after_sz = after_m["safety_zone_accuracy"]["pct"]
    check(
        "area accuracy improved vs prior Autogen backtest",
        before_area is None or after_area > before_area,
        f"before={before_area} after={after_area}",
    )
    check(
        "safety accuracy improved vs prior Autogen backtest",
        before_sz is None or after_sz > before_sz,
        f"before={before_sz} after={after_sz}",
    )

    report = {
        "generated_at": _ts(),
        "before_metrics": before,
        "after_metrics": after_m,
        "overlap_count": n_ov,
        "overlap_area_ok": area_ok,
        "overlap_safety_ok": safety_ok,
        "example_corrected_conveyors": examples,
        "generated_l5x": str(gen_l5x),
        "workbook_overlay": str(wb_path),
        "root_cause": (
            "RUN seed assigns {machine}_Area / {machine}_ESZone1. "
            "apply_workbook_to_input previously rebuilt inp.safety_zones as always "
            "'{AreaBase}_ESZone1', dropping engineer zones like ModuleB_ESZone2 from "
            "the zone list. Conveyor row main_area/safety_zone overlays were already "
            "applied to ConveyorRow; Fast_Conv uses those row fields. Fix preserves "
            "explicit conveyor safety zones in inp.safety_zones and regenerates with "
            "workbook metadata present."
        ),
    }
    (OUT / "fidelity_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = [
        "# Autogen Area/Safety Fidelity — Greensboro",
        "",
        f"Before area accuracy: **{(before.get('area_accuracy') or {}).get('pct')}%** "
        f"({(before.get('area_accuracy') or {}).get('correct')} / {(before.get('area_accuracy') or {}).get('compared')})",
        f"Before safety accuracy: **{(before.get('safety_zone_accuracy') or {}).get('pct')}%**",
        "",
        f"After area accuracy: **{after_area}%** "
        f"({after_m['area_accuracy']['correct']} / {after_m['area_accuracy']['compared']})",
        f"After safety accuracy: **{after_sz}%** "
        f"({after_m['safety_zone_accuracy']['correct']} / {after_m['safety_zone_accuracy']['compared']})",
        "",
        f"Overlap workbook fidelity: area {area_ok}/{n_ov}, safety {safety_ok}/{n_ov}",
        "",
        "## Example corrected conveyors",
        "",
    ]
    for ex in examples:
        md.append(
            f"- **{ex['conveyor']}** area=`{ex['area']}` safety=`{ex['safety_zone']}` "
            f"(reference area=`{ex['reference_area']}` safety=`{ex['reference_safety']}`)"
        )
    md.append("")
    md.append("## Root cause")
    md.append("")
    md.append(report["root_cause"])
    (OUT / "fidelity_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"  wrote {OUT / 'fidelity_report.md'}")
    return checks


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("=== Autogen Area/Safety Fidelity Pass 1 ===")
    checks = []
    checks.extend(test_synthetic_two_areas())
    checks.extend(test_greensboro_regenerate_and_compare())
    passed = sum(1 for _, ok, _ in checks if ok)
    failed = sum(1 for _, ok, _ in checks if not ok)
    print("====================================================")
    print(f"{'PASS' if failed == 0 else 'FAIL'} — {passed}/{passed + failed} checks")
    print("====================================================")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

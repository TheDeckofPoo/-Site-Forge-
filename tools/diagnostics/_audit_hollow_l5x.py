#!/usr/bin/env python3
"""Boundary audit: hollow-vs-populated L5X for CP4 latest build."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))


def audit_l5x(path: Path) -> dict:
    t = path.read_text(encoding="utf-8", errors="replace")
    programs = re.findall(r'<Program Name="([^"]+)"', t)
    modules = re.findall(r'<Module Name="([^"]+)"', t)
    tags = re.findall(r'<Tag Name="([^"]+)"', t)
    tasks = re.findall(r'<Task Name="([^"]+)"', t)
    p_conv = [n for n in tags if re.match(r"^P\d+[A-Z]?_Conv$", n)]
    rio = [n for n in modules if "RIO" in n.upper()]
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "programs": programs,
        "program_count": len(programs),
        "module_count": len(modules),
        "modules_sample": modules[:40],
        "rio_modules": rio,
        "tag_count": len(tags),
        "p_conv_tags": len(p_conv),
        "p_conv_sample": p_conv[:15],
        "task_count": len(tasks),
        "tasks": tasks,
        "has_RSLogix": "RSLogix5000Content" in t,
        "has_Controller": "<Controller" in t,
        "has_IO_MAP": "IO_MAP" in programs,
        "has_Fast_Area": any("Fast" in p for p in programs),
        "has_Slow_Area": any("Slow" in p for p in programs),
        "Fast_Conv_mentions": t.count("Fast_Conv"),
        "Slow_Flt_mentions": t.count("Slow_Flt"),
        "Sawtooth_mentions": t.count("Sawtooth"),
    }


def main() -> int:
    latest = ROOT / "exports" / "current" / "ORNCCP4_2026_09_13_1517.L5X"
    manifest = json.loads((ROOT / "exports" / "current" / "build_manifest.json").read_text(encoding="utf-8"))
    latest_json = json.loads((ROOT / "exports" / "current" / "LATEST.json").read_text(encoding="utf-8"))

    # RUN / HardwareIOModel / workbook boundaries
    from fortna_hardware_io_model import build_hardware_io_model
    from fortna_asc import read_asc

    run = ROOT / "workspace" / "cp4-run" / "RUN"
    active = ROOT / "workspace" / "active" / "RUN"
    run_dir = active if (active / "FORTNA").is_dir() else run
    hw = build_hardware_io_model(run_dir, "ORNCCP4")
    ads = hw.get("adapters") or []
    mod_n = sum(len(a.get("modules") or []) for a in ads)

    # Conveyor.asc P### count (rough)
    conv_path = run_dir / "FORTNA" / "Conveyor.asc"
    _, rows = read_asc(conv_path)
    p_names = set()
    for r in rows:
        n = str(r.get("IO_Name") or "")
        if re.match(r"^P\d+[A-Z]?$", n, re.I):
            p_names.add(n.upper())

    wb_path = ROOT / "workspace" / "autogen_workbook.json"
    wb = json.loads(wb_path.read_text(encoding="utf-8")) if wb_path.is_file() else {}
    wb_convs = [c for c in (wb.get("conveyors") or []) if c.get("conveyor") or c.get("name")]

    l5x = audit_l5x(latest)
    out = {
        "run_dir": str(run_dir),
        "run_p_conveyor_names": len(p_names),
        "hardware_adapters": len(ads),
        "hardware_modules_incl_aent": mod_n,
        "workbook_conveyors": len(wb_convs),
        "workbook_sawtooth": bool((wb.get("sawtooth_build") or {}).get("collector_conveyor")),
        "manifest": {
            "output_path": manifest.get("output_path") or manifest.get("l5x"),
            "controller": manifest.get("controller") or manifest.get("controller_name"),
            "conveyor_count": (manifest.get("manifest") or manifest).get("conveyor_count")
            if isinstance(manifest.get("manifest"), dict)
            else manifest.get("conveyor_count"),
        },
        "latest_report": {
            "conveyor_count": (latest_json.get("report") or {}).get("conveyor_count"),
            "program_count": (latest_json.get("report") or {}).get("program_count"),
            "programs": (latest_json.get("report") or {}).get("programs"),
            "io_module_count": (latest_json.get("report") or {}).get("io_module_count"),
            "eip_child_count": (latest_json.get("report") or {}).get("eip_child_count"),
            "tag_count": (latest_json.get("report") or {}).get("tag_count"),
            "l5x": latest_json.get("l5x"),
            "generation_assertions": latest_json.get("report", {}).get("generation_assertions")
            or latest_json.get("generation_assertions"),
        },
        "l5x_audit": l5x,
        "hollow_verdict": None,
    }
    # Hollow if transport/IO missing despite RUN evidence
    hollow = []
    if out["run_p_conveyor_names"] > 10 and l5x["p_conv_tags"] == 0:
        hollow.append(
            f"BUILD FAILED — RUN had {out['run_p_conveyor_names']} P### conveyors but L5X has 0 P###_Conv tags"
        )
    if out["hardware_modules_incl_aent"] > 5 and l5x["module_count"] == 0:
        hollow.append(
            f"BUILD FAILED — Hardware model had {out['hardware_modules_incl_aent']} modules but L5X has 0 Module elements"
        )
    if not l5x["has_Fast_Area"] and out["workbook_conveyors"] > 0:
        hollow.append("BUILD FAILED — workbook had conveyors but L5X missing Fast area program")
    if not l5x["has_IO_MAP"]:
        hollow.append("BUILD FAILED — IO_MAP program missing from L5X")
    out["hollow_verdict"] = hollow or ["NOT_HOLLOW — L5X contains transport programs/tags and modules"]
    out_path = ROOT / "exports" / "plc2-validation" / "hollow_l5x_audit.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in out if k != "l5x_audit"}, indent=2))
    print("--- l5x_audit ---")
    print(json.dumps(l5x, indent=2))
    return 0 if not hollow else 2


if __name__ == "__main__":
    raise SystemExit(main())

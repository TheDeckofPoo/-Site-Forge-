#!/usr/bin/env python3
"""CP2 recovery validation — fresh product-path Build PLC for Curtis Studio.

Chain (same engines as Electron):
  apply_recipe import → discover → SiteModel → workbook (fresh)
  → fortna_autogen from-run --with-io-map → ORNCCP2_recovery_validation.L5X
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_autogen import load_from_run  # noqa: E402
from fortna_io_regression_baselines import (  # noqa: E402
    _parse_iomap_mappings,
    _parse_l5x_modules,
)
from fortna_runtime_acceptance_recovery import (  # noqa: E402
    _import_via_apply_recipe,
    _last_json,
    _l5x_counts,
    _py,
    _run,
    site_to_sawtooth_build,
    site_to_sorter_build,
)
from fortna_site_model import write_json  # noqa: E402
from fortna_studio_preflight import preflight_l5x, write_markdown  # noqa: E402


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _classify_modules(mods: list[dict[str, Any]]) -> dict[str, Any]:
    adapters = []
    children = []
    other = []
    for m in mods:
        name = str(m.get("name") or "")
        parent = m.get("parent")
        if parent:
            children.append(m)
        elif re.search(r"AENT|RIO|ENBT|EN2T", name, re.I):
            adapters.append(m)
        else:
            other.append(m)
    # If parent attribute missing, treat *_N children by name pattern
    if not children:
        for m in mods:
            name = str(m.get("name") or "")
            if re.search(r"AENT_\d+_\d+", name, re.I) or re.search(r"RIO\d+_\d+", name, re.I):
                children.append(m)
            elif re.search(r"AENT|RIO", name, re.I) and m not in adapters:
                adapters.append(m)
    return {
        "total": len(mods),
        "adapters": adapters,
        "child_modules": children,
        "other": other,
    }


def _device_relationship_checks(mappings: list[dict[str, Any]], points: list[Any]) -> list[dict[str, Any]]:
    """Representative PE / motor / VFD / jam / control-station mapping rows."""
    rows: list[dict[str, Any]] = []

    def add(kind: str, m: dict[str, Any], run_src: str = "") -> None:
        rows.append(
            {
                "kind": kind,
                "run_source": run_src,
                "generated_tag": m.get("tag"),
                "generated_module_channel": m.get("channel"),
                "slot": m.get("slot"),
                "bit": m.get("bit"),
                "direction": m.get("direction"),
                "rung": m.get("rung"),
                "ok": bool(m.get("tag") and m.get("channel")),
            }
        )

    pe = [m for m in mappings if re.search(r"PE\d", str(m.get("tag") or ""), re.I)]
    jam = [m for m in pe if re.search(r"_J|_JF|_F\b", str(m.get("tag") or ""), re.I)]
    motor = [
        m
        for m in mappings
        if re.search(r"VFD|_VFD|MTR|_MS\b|\.O\.Run|Auxiliary_Forward", str(m.get("tag") or ""), re.I)
    ]
    station = [
        m
        for m in mappings
        if re.search(r"PBSTART|PBSTOP|MCR|ESR|ESTOP", str(m.get("tag") or ""), re.I)
    ]

    for m in pe[:6]:
        add("photoeye", m, "Conveyor.asc / IO points")
    for m in jam[:4]:
        add("jam_or_full_pe", m, "Conveyor.asc PE role")
    for m in motor[:6]:
        add("motor_or_vfd", m, "Conveyor.asc VFD/motor IO")
    for m in station[:4]:
        add("control_station", m, "local rack / conveyor IO")

    # Exact golden mapping from io-regression-lock
    exact = next(
        (
            m
            for m in mappings
            if m.get("tag") == "PE215_J.I.PE_Clear"
            and m.get("channel") == "T_1794_AENT_1:I.Data[6].11"
        ),
        None,
    )
    rows.insert(
        0,
        {
            "kind": "exact_baseline_mapping",
            "run_source": "io-regression-lock CP2 baseline",
            "expected": "XIC(T_1794_AENT_1:I.Data[6].11)OTE(PE215_J.I.PE_Clear);",
            "generated_tag": (exact or {}).get("tag"),
            "generated_module_channel": (exact or {}).get("channel"),
            "slot": (exact or {}).get("slot"),
            "bit": (exact or {}).get("bit"),
            "direction": (exact or {}).get("direction"),
            "rung": (exact or {}).get("rung"),
            "ok": exact is not None,
        },
    )
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--archive",
        type=Path,
        default=ROOT
        / "workspace"
        / "inbox"
        / "20251016-0933-OReillyGreensboro-ORNCCP2-RUN.tar.gz",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "exports" / "cp2-recovery-validation",
    )
    ap.add_argument(
        "--library",
        type=Path,
        default=ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X",
    )
    args = ap.parse_args(argv)
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    studio = ROOT / "exports" / "studio-validation"
    studio.mkdir(parents=True, exist_ok=True)
    dest_l5x = studio / "ORNCCP2_recovery_validation.L5X"
    baseline_path = ROOT / "exports" / "io-regression-lock" / "cp2_io_baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.is_file() else {}

    report: dict[str, Any] = {
        "generated_at": _ts(),
        "branch_intent": "feature/cp2-recovery-validation",
        "archive": str(args.archive),
        "product_chain": [
            "apply_recipe import",
            "fortna_run_workspace_discover",
            "workspace/active/site_model.json",
            "fortna_workbook build (fresh, no merge-existing)",
            "fortna_autogen from-run --with-io-map --workbook",
        ],
        "ok": False,
    }
    if not args.archive.is_file():
        report["error"] = f"missing archive {args.archive}"
        write_json(out / "report.json", report)
        print(json.dumps(report, indent=2))
        return 1

    # 1) Import (Electron import-run engine)
    meta = _import_via_apply_recipe(args.archive)
    run_dir = Path(meta["run_dir"])
    machine = str(meta.get("machine") or "ORNCCP2").upper()
    report["import"] = {"ok": True, "run_dir": str(run_dir), "machine": machine, "device_count": meta.get("device_count")}

    # 2) Discover → SiteModel (Electron import-run discovery)
    disc_out = ROOT / "exports" / "run-discovery" / machine
    disc_out.mkdir(parents=True, exist_ok=True)
    dr = _run(
        _py()
        + [
            str(SCRIPTS / "fortna_run_workspace_discover.py"),
            "--run-dir",
            str(run_dir),
            "--out",
            str(disc_out),
            "--machine",
            machine,
        ]
    )
    site_path = disc_out / "site_model.json"
    if not site_path.is_file():
        report["discover"] = {"ok": False, "error": dr.get("stderr") or "site_model missing"}
        write_json(out / "report.json", report)
        return 1
    active = ROOT / "workspace" / "active"
    active.mkdir(parents=True, exist_ok=True)
    shutil.copy2(site_path, active / "site_model.json")
    shutil.copy2(site_path, ROOT / "exports" / "run-discovery" / "site_model.json")
    site = json.loads(site_path.read_text(encoding="utf-8"))
    report["discover"] = {
        "ok": True,
        "site_model": str(active / "site_model.json"),
        "counts": site.get("counts"),
        "has_sawtooth": bool(site.get("sawtooth_merges")),
        "has_sorter": bool(site.get("sorters")),
    }

    # 3) Canonical workbook (fresh — same as Import force rebuild)
    wb_path = ROOT / "workspace" / "autogen_workbook.json"
    if wb_path.is_file():
        wb_path.unlink()
    wr = _run(
        _py()
        + [
            str(SCRIPTS / "fortna_workbook.py"),
            "build",
            "--run-dir",
            str(run_dir),
            "--processor",
            "1756-L83E",
            "--out",
            str(wb_path),
        ]
    )
    wb: dict[str, Any] = {}
    if wb_path.is_file():
        wb = json.loads(wb_path.read_text(encoding="utf-8"))
    saw = site_to_sawtooth_build(site)
    sorter = site_to_sorter_build(site)
    if saw:
        wb["sawtooth_build"] = saw
    if sorter:
        wb["sorter_build"] = sorter
    wb_path.write_text(json.dumps(wb, indent=2), encoding="utf-8")
    report["workbook"] = {
        "ok": wb_path.is_file() and bool(wb.get("conveyors")),
        "path": str(wb_path),
        "conveyors": len(wb.get("conveyors") or []),
        "workbook_cmd_ok": wr.get("ok"),
    }

    # 4) Build PLC — from-run --with-io-map (Electron autogen-generate)
    build_out = out / "autogen"
    if build_out.exists():
        shutil.rmtree(build_out, ignore_errors=True)
    build_out.mkdir(parents=True, exist_ok=True)
    include = ["Devices_Comm", "NTP", "System_Logic", "System"]
    gr = _run(
        _py()
        + [
            str(SCRIPTS / "fortna_autogen.py"),
            "from-run",
            "--run-dir",
            str(run_dir),
            "--library",
            str(args.library),
            "--processor",
            "1756-L83E",
            "--with-io-map",
            "--workbook",
            str(wb_path),
            "--include-programs",
            ",".join(include),
            "--out-dir",
            str(build_out),
        ]
    )
    parsed = _last_json(gr.get("stdout") or "") or {}
    l5x = Path(parsed.get("l5x") or "")
    if not l5x.is_file():
        cands = sorted(build_out.rglob("*.L5X"), key=lambda p: p.stat().st_mtime, reverse=True)
        # Prefer controller L5X not the library copy
        cands = [c for c in cands if "Library" not in c.name]
        l5x = cands[0] if cands else Path()
    if not l5x.is_file():
        report["build"] = {"ok": False, "error": parsed.get("error") or gr.get("stderr") or "no L5X"}
        write_json(out / "report.json", report)
        return 1

    shutil.copy2(l5x, dest_l5x)
    sha = _sha256(dest_l5x)
    text = dest_l5x.read_text(encoding="utf-8", errors="replace")
    l5x_c = _l5x_counts(dest_l5x)
    mods = _parse_l5x_modules(text)
    classified = _classify_modules(mods)
    mappings = _parse_iomap_mappings(text, limit=800)
    inp = load_from_run(run_dir)
    gen_report = parsed.get("report") or {}

    # Transport program checks
    programs = l5x_c.get("programs") or []
    transport = {
        "programs": programs,
        "has_area_fast": any("Fast" in p for p in programs),
        "has_area_slow": any("Slow" in p for p in programs),
        "has_io_map": "IO_MAP" in programs,
        "has_sys": "Sys" in programs,
        "has_system": "System" in programs,
        "pe_udt_tags": l5x_c.get("pe_udt_tags"),
        "conveyor_count_report": gen_report.get("conveyor_count"),
        "pe_device_count_report": gen_report.get("pe_device_count"),
        "pe_logic_rungs_report": gen_report.get("pe_logic_rungs"),
    }

    relationships = _device_relationship_checks(mappings, list(getattr(inp, "io_points", None) or []))

    # Baseline compare
    bcounts = (baseline.get("counts") or {}) if baseline else {}
    baseline_compare = {
        "baseline_run_modules": bcounts.get("modules_from_run"),
        "baseline_l5x_modules": bcounts.get("l5x_module_entries"),
        "baseline_word_map": bcounts.get("word_map_entries"),
        "baseline_iomap_xic_ote": bcounts.get("l5x_io_map_xic_ote"),
        "actual_run_modules": len(getattr(inp, "modules", None) or []),
        "actual_word_map": len(getattr(inp, "io_word_map", None) or {}),
        "actual_l5x_modules": l5x_c.get("module_entries"),
        "actual_iomap_xic_ote": l5x_c.get("io_map_xic_ote_refs"),
        "actual_iomap_nop_only": l5x_c.get("io_map_nop_only"),
        "floor_run_modules_ok": (len(getattr(inp, "modules", None) or []) or 0) >= 37,
        "floor_l5x_modules_ok": (l5x_c.get("module_entries") or 0) >= 39,
        "floor_word_map_ok": (len(getattr(inp, "io_word_map", None) or {}) or 0) >= 27,
        "floor_iomap_ok": (l5x_c.get("io_map_xic_ote_refs") or 0) >= 68,
        "exact_pe215_ok": bool(relationships and relationships[0].get("ok")),
        "notes": [],
    }
    if baseline_compare["actual_l5x_modules"] != baseline_compare["baseline_l5x_modules"]:
        baseline_compare["notes"].append(
            f"L5X module count {baseline_compare['actual_l5x_modules']} vs baseline {baseline_compare['baseline_l5x_modules']}"
        )
    if baseline_compare["actual_iomap_xic_ote"] != baseline_compare["baseline_iomap_xic_ote"]:
        baseline_compare["notes"].append(
            f"IO_MAP XIC/OTE {baseline_compare['actual_iomap_xic_ote']} vs baseline {baseline_compare['baseline_iomap_xic_ote']}"
        )

    # Studio static precheck (not Studio PASS)
    pre = preflight_l5x(dest_l5x)
    write_json(out / "studio_precheck.json", pre)
    write_markdown(pre, out / "STUDIO_STATIC_PRECHECK.md")
    write_markdown(pre, studio / "CP2_RECOVERY_STUDIO_PRECHECK.md")

    exact_ok = all(r.get("ok") for r in relationships if r.get("kind") == "exact_baseline_mapping")
    io_ok = (
        (l5x_c.get("module_entries") or 0) > 0
        and not l5x_c.get("io_map_nop_only")
        and (l5x_c.get("io_map_xic_ote_refs") or 0) > 0
        and exact_ok
        and transport["has_io_map"]
        and transport["has_area_fast"]
        and transport["has_area_slow"]
    )

    report.update(
        {
            "ok": bool(io_ok and report["workbook"]["ok"] and report["discover"]["ok"]),
            "l5x_path": str(dest_l5x),
            "l5x_source_build": str(l5x),
            "sha256": sha,
            "build": {
                "ok": bool(parsed.get("ok", gr.get("ok"))),
                "generate_error": parsed.get("error"),
                "report_counts": {
                    "conveyors": gen_report.get("conveyor_count"),
                    "io_modules": gen_report.get("io_module_count"),
                    "io_points": gen_report.get("io_point_count"),
                    "io_map_mapped": gen_report.get("io_map_mapped"),
                    "io_map_rungs": gen_report.get("io_map_rungs"),
                    "pe_devices": gen_report.get("pe_device_count"),
                    "programs": gen_report.get("programs"),
                },
            },
            "modules": {
                "total": classified["total"],
                "adapters_count": len(classified["adapters"]),
                "child_modules_count": len(classified["child_modules"]),
                "adapters": classified["adapters"][:20],
                "child_modules": classified["child_modules"][:40],
                "all_names": [m.get("name") for m in mods],
                "catalog_numbers": sorted({m.get("catalog") for m in mods if m.get("catalog")}),
            },
            "word_map_entries": len(getattr(inp, "io_word_map", None) or {}),
            "io_map": {
                "program_present": "IO_MAP" in programs,
                "xic_ote_refs": l5x_c.get("io_map_xic_ote_refs"),
                "nop_only": l5x_c.get("io_map_nop_only"),
                "mapped_rungs_parsed": len(mappings),
                "representative_mappings": mappings[:15],
            },
            "device_relationships": relationships,
            "transport": transport,
            "baseline_compare": baseline_compare,
            "static_precheck": {
                "ok": pre.get("ok"),
                "summary": pre.get("summary") or pre.get("totals") or {
                    k: pre.get(k) for k in ("errors", "warnings", "issues", "duplicate_tags", "missing_aois") if k in pre
                },
                "studio_pass_claimed": False,
                "artifact": str(out / "studio_precheck.json"),
            },
            "ready_for_curtis_studio_test": bool(io_ok),
            "studio_pass_claimed": False,
        }
    )
    write_json(out / "report.json", report)
    print(json.dumps({
        "ok": report["ok"],
        "l5x_path": report["l5x_path"],
        "sha256": sha,
        "modules": report["modules"]["total"],
        "adapters": report["modules"]["adapters_count"],
        "children": report["modules"]["child_modules_count"],
        "io_map_xic_ote": report["io_map"]["xic_ote_refs"],
        "exact_ok": exact_ok,
        "ready": report["ready_for_curtis_studio_test"],
    }, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

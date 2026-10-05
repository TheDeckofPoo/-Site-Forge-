#!/usr/bin/env python3
"""MSCRENOPICK I/O source conservation proof — RUN ledger → L5X.

Produces engineer CSV/JSON tables for pushbuttons + Safety and regenerates
MSCRENOPICK under the conservation gate.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))
os.chdir(REPO)
os.environ["FORTNA_PRISM_DISABLE"] = "1"
os.environ["SITEFORGE_ESCALATION"] = "1"
os.environ["SITEFORGE_L5X_AUDITOR"] = "1"
os.environ.pop("SITEFORGE_SKIP_L5X_PROMOTE", None)

OUT = REPO / "exports" / "delivery_gate_20261002"
OUT.mkdir(parents=True, exist_ok=True)
SUMMARY = OUT / "mscrenopick_io_source_conservation_proof.json"
TAR = REPO / "workspace" / "inbox" / "20260813-1132-MSCRENO-MSCRENOPICK-RUN.tar.gz"
EXPECTED_TAR = "8F85D07D81368800E680B2C7861CF31825DA9DED6083A21335260BCAA0BED3CA"

AREA = "MSCRENOPICK_Area"
ZONE = "MSCRENOPICK_ESZone1"
MEMBERS = ["ESPB2", "ESPB24", "ESPB32", "ESLS2"]

BEFORE = {
    "qualification": "overnight_rc_false_100pct",
    "physical_points_discovered_csv": 118,
    "mapped": 114,
    "review": 4,
    "accounted": 118,
    "io_pass_claimed": True,
    "coverage_claimed_pct": 100.0,
    "denominator": "physical_io_map.csv",
}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest().upper()


def clear_project(repo: Path) -> None:
    for p in (
        repo / "workspace" / "active-meta.json",
        repo / "workspace" / "autogen_workbook.json",
        repo / "workspace" / "hardware_io_overrides.json",
    ):
        if p.is_file():
            p.unlink()
    active = repo / "workspace" / "active"
    if active.is_dir():
        for child in list(active.iterdir()):
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                try:
                    child.unlink()
                except OSError:
                    pass


def main() -> int:
    from apply_recipe import import_package
    from fortna_autogen import generate, load_from_run, resolve_production_library
    from fortna_run_io_source_ledger import (
        build_run_io_source_ledger,
        reconcile_ledger,
        write_ledger_artifacts,
    )

    git_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO), text=True
    ).strip()
    summary: dict = {
        "phase": "MSCRENOPICK_IO_SOURCE_CONSERVATION_PROOF",
        "git_sha": git_sha,
        "before": BEFORE,
        "root_cause": (
            "I/O qualification used physical_io_map.csv as both numerator and "
            "denominator (accounted == csv rows → fake 100%). Denominator must "
            "be upstream RUN_IO_SOURCE_LEDGER."
        ),
    }
    if not TAR.is_file():
        summary["error"] = f"TAR missing: {TAR}"
        SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return 2
    tar_sha = sha256_file(TAR)
    summary["tar_sha256"] = tar_sha
    summary["tar_sha_match"] = tar_sha == EXPECTED_TAR
    if tar_sha != EXPECTED_TAR:
        summary["error"] = "TAR SHA mismatch"
        SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return 2

    clear_project(REPO)
    meta = import_package(TAR)
    run_dir = Path(meta["run_dir"])

    # Pre-generate ledger snapshot (source inventory Curtis can inspect)
    ledger = build_run_io_source_ledger(run_dir, "MSCRENOPICK")
    pre = reconcile_ledger(
        ledger,
        physical_io_map_csv=None,
        l5x_path=None,
        machine="MSCRENOPICK",
        canonical_device_names=set(),  # force visibility of drops vs empty canon
    )
    # With empty canon, non-foreign interest → silently_missing (proves detection)
    detection_demo = {
        "with_empty_canonical_silently_missing": pre.get("silently_missing"),
        "sample_missing": (pre.get("silently_missing_devices") or [])[:20],
        "can_detect_disappearance_before_csv": int(pre.get("silently_missing") or 0) > 0,
    }
    summary["detection_demo_empty_canonical"] = detection_demo

    lib = resolve_production_library(None)
    inp = load_from_run(run_dir)
    inp.include_sys = True
    inp.include_io_map = True
    inp.machine = "MSCRENOPICK"
    inp.project_name = "MSCRENOPICK"
    inp.areas = [AREA]
    zone = {
        "name": ZONE,
        "engineering_name": ZONE,
        "area": AREA,
        "areaRef": AREA,
        "members": list(MEMBERS),
        "membersOrigin": "ENGINEER_ASSIGNED",
        "engineerEdited": True,
        "createdBy": "engineer",
        "zoneOrigin": "ENGINEER",
        "status": "READY",
        "operational": True,
        "conveyors": [],
    }
    wb = {
        "version": 1,
        "kind": "fortna_autogen_workbook",
        "machine": "MSCRENOPICK",
        "project_name": "MSCRENOPICK",
        "areas": [{"name": AREA, "source": "engineer"}],
        "options": {"areas": [AREA], "safety_zones": [ZONE]},
        "safety_build": {"version": 1, "source": "engineer", "zones": [zone], "devices": []},
    }
    (REPO / "workspace" / "autogen_workbook.json").write_text(
        json.dumps(wb, indent=2), encoding="utf-8"
    )
    inp.safety_zones = [ZONE]
    inp.safety_zone_members = [zone]
    inp.safety_build = wb["safety_build"]
    for c in inp.conveyors or []:
        try:
            c.area = AREA
            c.safety_zone = ZONE
        except Exception:
            pass

    print(f"[IO-CONS] generate MSCRENOPICK @ {git_sha[:12]}", flush=True)
    try:
        outer = generate(inp, lib, None)
    except Exception as ex:  # noqa: BLE001
        summary["generate_error"] = str(ex)
        SUMMARY.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(json.dumps({"ok": False, "error": str(ex)}, indent=2))
        return 1

    rep = outer.get("report") if isinstance(outer.get("report"), dict) else {}
    l5x_path = Path(str(outer.get("l5x") or ""))
    accept = rep.get("l5x_acceptance") or outer.get("l5x_acceptance") or {}
    cons = rep.get("io_source_conservation") or {}

    # Locate build dir artifacts
    build_dir = Path(str(rep.get("diagnostics_dir") or rep.get("out_dir") or ""))
    if not build_dir.is_dir():
        builds = REPO / "workspace" / ".internal" / "builds"
        cands = sorted(builds.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True) if builds.is_dir() else []
        for p in cands:
            if list(p.glob("MSCRENOPICK*.L5X")):
                build_dir = p
                break

    map_csv = build_dir / "physical_io_map.csv" if build_dir.is_dir() else None
    ledger2 = build_run_io_source_ledger(run_dir, "MSCRENOPICK")
    canon = set(rep.get("_io_source_canonical") or [])
    if not canon and isinstance(cons.get("artifacts"), dict):
        # reload from written ledger if needed
        pass
    recon = reconcile_ledger(
        ledger2,
        physical_io_map_csv=map_csv if map_csv and map_csv.is_file() else None,
        l5x_path=l5x_path if l5x_path.is_file() else None,
        machine="MSCRENOPICK",
        canonical_device_names=canon or None,
    )
    art = write_ledger_artifacts(recon, OUT / "mscrenopick_io_source_ledger")

    pb_table = [
        {
            "source_signal": r.get("source_signal"),
            "source_file": r.get("source_file"),
            "machine": r.get("machine"),
            "word": r.get("word"),
            "bit": r.get("bit"),
            "final_status": r.get("final_status"),
            "canonical_device": r.get("canonical_device"),
            "alias_parent": r.get("alias_parent"),
            "reason": r.get("reason"),
        }
        for r in (recon.get("pushbuttons") or [])
    ]
    safety_table = [
        {
            "source_signal": r.get("source_signal"),
            "source_file": r.get("source_file"),
            "machine": r.get("machine"),
            "endpoint": r.get("endpoint"),
            "word": r.get("word"),
            "bit": r.get("bit"),
            "final_status": r.get("final_status"),
            "canonical_device": r.get("canonical_device"),
            "alias_parent": r.get("alias_parent"),
            "reason": r.get("reason"),
        }
        for r in (recon.get("safety_rows") or [])
    ]

    summary.update(
        {
            "outer_ok": outer.get("ok"),
            "build_status": outer.get("build_status") or rep.get("build_status"),
            "promoted": bool(
                outer.get("l5x_promoted_to_current") or rep.get("l5x_promoted_to_current")
            ),
            "l5x": str(l5x_path) if l5x_path else "",
            "l5x_sha256": sha256_file(l5x_path) if l5x_path.is_file() else "",
            "l5x_acceptance": {
                "status": accept.get("status"),
                "ok": accept.get("ok"),
                "signatures": (accept.get("final_audit") or accept.get("initial_audit") or {}).get(
                    "signatures"
                ),
            },
            "after": {
                "source_physical_candidates": recon.get("source_physical_candidates"),
                "canonical_physical_devices": recon.get("canonical_physical_devices"),
                "mapped": recon.get("mapped"),
                "spare": recon.get("spare"),
                "foreign": recon.get("foreign"),
                "alias_child": recon.get("alias_child"),
                "review": recon.get("review"),
                "unsupported": recon.get("unsupported"),
                "silently_missing": recon.get("silently_missing"),
                "conservation_ok": recon.get("conservation_ok"),
                "coverage_status": recon.get("coverage_status"),
                "coverage_pct": recon.get("coverage_pct"),
                "denominator": "RUN_IO_SOURCE_LEDGER",
            },
            "report_conservation": cons,
            "pushbutton_inventory": pb_table,
            "safety_inventory": {
                "raw_signals": len(safety_table),
                "mapped": sum(1 for r in safety_table if r.get("final_status") == "MAPPED"),
                "alias_children": sum(
                    1
                    for r in safety_table
                    if str(r.get("final_status") or "").startswith("ALIAS_OF")
                ),
                "review": sum(
                    1 for r in safety_table if r.get("final_status") == "REVIEW_REQUIRED"
                ),
                "unsupported": sum(
                    1 for r in safety_table if r.get("final_status") == "UNSUPPORTED"
                ),
                "foreign": sum(
                    1
                    for r in safety_table
                    if r.get("final_status") == "FOREIGN_CONTROLLER"
                ),
                "silently_missing": sum(
                    1
                    for r in safety_table
                    if r.get("final_status") == "SILENTLY_MISSING"
                ),
                "rows": safety_table,
            },
            "artifacts": art,
            "gates": {
                "source_conservation": bool(recon.get("conservation_ok")),
                "audit": str(accept.get("status") or "") == "AUDIT_PASS",
                "promoted": bool(
                    outer.get("l5x_promoted_to_current") or rep.get("l5x_promoted_to_current")
                ),
            },
        }
    )
    summary["CAN_DETECT_RUN_DEVICE_DISAPPEARING_BEFORE_CSV"] = (
        "YES" if detection_demo["can_detect_disappearance_before_csv"] else "NO"
    )
    summary["proof_pass"] = bool(
        summary["gates"]["source_conservation"]
        and summary["gates"]["audit"]
        and summary["gates"]["promoted"]
    )
    SUMMARY.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "proof_pass": summary["proof_pass"],
                "CAN_DETECT": summary["CAN_DETECT_RUN_DEVICE_DISAPPEARING_BEFORE_CSV"],
                "after": summary["after"],
                "pb_n": len(pb_table),
                "safety_n": len(safety_table),
                "audit": accept.get("status"),
                "artifacts": art,
                "summary": str(SUMMARY),
            },
            indent=2,
            default=str,
        )
    )
    return 0 if summary["proof_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

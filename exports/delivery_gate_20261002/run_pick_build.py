#!/usr/bin/env python3
"""MSCRENOPICK delivery-gate build — normal Site Forge checkout exports/current."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))
os.chdir(REPO)
os.environ["FORTNA_PRISM_DISABLE"] = "1"

TAR = REPO / "workspace" / "inbox" / "20260813-1132-MSCRENO-MSCRENOPICK-RUN.tar.gz"
EXPECTED_TAR_SHA = "8F85D07D81368800E680B2C7861CF31825DA9DED6083A21335260BCAA0BED3CA"
OUT = REPO / "exports" / "delivery_gate_20261002"
OUT.mkdir(parents=True, exist_ok=True)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest().upper()


def main() -> int:
    from apply_recipe import import_package
    from fortna_autogen import generate, load_from_run, resolve_production_library

    summary: dict = {"site": "MSCRENOPICK", "repo": str(REPO), "git_sha": "804e5b4"}
    if not TAR.is_file():
        summary["error"] = f"TAR missing: {TAR}"
        (OUT / "pick_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 2

    tar_sha = sha256_file(TAR)
    summary["tar"] = str(TAR)
    summary["tar_sha256"] = tar_sha
    summary["tar_sha_match"] = tar_sha == EXPECTED_TAR_SHA
    if tar_sha != EXPECTED_TAR_SHA:
        summary["error"] = f"TAR SHA mismatch got={tar_sha}"
        (OUT / "pick_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 3

    meta = import_package(TAR)
    summary["import_meta"] = {
        "machine": meta.get("machine"),
        "run_dir": meta.get("run_dir"),
        "run_fingerprint": meta.get("run_fingerprint"),
        "tar_sha256": meta.get("tar_sha256"),
        "archive_name": meta.get("archive_name"),
    }

    run_dir = Path(meta["run_dir"])
    lib = resolve_production_library(None)

    # Engineer-confirmed Safety zone (same members as Phase B mandate).
    zone = {
        "name": "MSCRENOPICK_ESZone1",
        "area": "MSCRENOPICK_Area",
        "membersOrigin": "ENGINEER_ASSIGNED",
        "status": "ENGINEER_ASSIGNED",
        "members": ["ESPB2", "ESPB24", "ESPB32", "ESLS2"],
        "membership": [
            {"device": "ESPB2", "physical_endpoint": "AENTR3:I.Data[4].4", "safety_role": "FEEDBACK"},
            {"device": "ESPB24", "physical_endpoint": "AENTR1:I.Data[3].7", "safety_role": "FEEDBACK"},
            {"device": "ESPB32", "physical_endpoint": "AENTR2:I.Data[3].0", "safety_role": "FEEDBACK"},
            {"device": "ESLS2", "physical_endpoint": "AENTR2:I.Data[2].3", "safety_role": "FEEDBACK"},
        ],
        "operational": True,
    }

    inp = load_from_run(run_dir)
    inp.include_sys = True
    inp.include_io_map = True
    inp.machine = "MSCRENOPICK"
    inp.project_name = "MSCRENOPICK"
    inp.areas = ["MSCRENOPICK_Area"]
    inp.safety_zones = ["MSCRENOPICK_ESZone1"]
    inp.safety_zone_members = [zone]
    inp.safety_build = {
        "version": 1,
        "source": "engineer",
        "zones": [zone],
        "devices": [],
    }
    for c in inp.conveyors or []:
        c.safety_zone = "MSCRENOPICK_ESZone1"
        try:
            c.area = "MSCRENOPICK_Area"
        except Exception:
            pass

    # Persist workbook the UI would save (for restart/persistence identity).
    wb = {
        "version": 1,
        "kind": "fortna_autogen_workbook",
        "site": "MSCRENO",
        "machine": "MSCRENOPICK",
        "project_name": "MSCRENOPICK",
        "areas": [{"name": "MSCRENOPICK_Area", "source": "engineer"}],
        "options": {
            "areas": ["MSCRENOPICK_Area"],
            "safety_zones": ["MSCRENOPICK_ESZone1"],
        },
        "safety_build": inp.safety_build,
        "conveyors": [],
        "io_map": [],
        "merges_2to1": [],
    }
    wb_path = REPO / "workspace" / "autogen_workbook.json"
    wb_path.write_text(json.dumps(wb, indent=2), encoding="utf-8")

    # out_dir=None → promote to exports/current (engineer-facing).
    outer = generate(inp, lib, None)
    rep = outer.get("report") if isinstance(outer.get("report"), dict) else {}
    summary["outer_ok"] = outer.get("ok")
    summary["outer_error"] = outer.get("error")
    summary["build_status"] = outer.get("build_status") or rep.get("build_status")
    summary["commissioning_ready"] = (
        outer.get("commissioning_ready")
        or (rep.get("runnability") or {}).get("COMMISSIONING_READY")
        or rep.get("COMMISSIONING_READY")
    )
    summary["l5x"] = outer.get("l5x")
    summary["l5x_filename"] = outer.get("l5x_filename")
    summary["l5x_sha256"] = outer.get("l5x_sha256")
    summary["build_id"] = outer.get("build_id")
    summary["build_issues_txt"] = outer.get("build_issues_txt") or rep.get("build_issues_txt")
    summary["build_issues_json"] = outer.get("build_issues_json") or rep.get("build_issues_json")
    summary["actionable_issue_count"] = outer.get("actionable_issue_count") or (
        (rep.get("build_issues") or {}).get("actionable_issue_count")
    )
    summary["controller_name"] = outer.get("controller_name")
    summary["out_dir"] = outer.get("out_dir")
    summary["conveyor_count"] = rep.get("conveyor_count")
    summary["programs"] = rep.get("programs")
    summary["es_program"] = {
        "status": (rep.get("es_program") or {}).get("status"),
        "zones": (rep.get("es_program") or {}).get("zones"),
        "emitted_zones": (rep.get("es_program") or {}).get("emitted_zones"),
    }
    summary["writer_coverage"] = rep.get("writer_coverage")
    l5x_path = Path(str(outer.get("l5x") or ""))
    summary["promoted"] = l5x_path.is_file() and l5x_path.parent.name.lower() == "current"
    summary["filesystem"] = {
        "l5x_exists": l5x_path.is_file(),
        "l5x_under_exports_current": l5x_path.is_file() and "exports" in l5x_path.parts and "current" in l5x_path.parts,
        "issues_txt_exists": Path(str(summary.get("build_issues_txt") or "")).is_file(),
        "issues_json_exists": Path(str(summary.get("build_issues_json") or "")).is_file(),
        "latest_json_exists": (REPO / "exports" / "current" / "LATEST.json").is_file(),
        "absolute_l5x": str(l5x_path.resolve()) if l5x_path.is_file() else "",
    }
    if (REPO / "exports" / "current" / "LATEST.json").is_file():
        latest = json.loads((REPO / "exports" / "current" / "LATEST.json").read_text(encoding="utf-8"))
        summary["latest_build_status"] = latest.get("build_status") or (
            (latest.get("report") or {}).get("build_status")
        )
        summary["latest_controller"] = latest.get("controller_name")
        summary["latest_tar_sha"] = latest.get("tar_sha256") or latest.get("source_tar_sha256")
        summary["latest_run_hash"] = latest.get("source_run_hash")

    (OUT / "pick_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        "PICK BUILD",
        summary.get("build_status"),
        summary.get("l5x_filename"),
        "promoted",
        summary.get("promoted"),
        "issues",
        summary.get("actionable_issue_count"),
    )
    print(json.dumps({
        k: summary.get(k)
        for k in (
            "build_status",
            "commissioning_ready",
            "l5x_filename",
            "l5x_sha256",
            "build_id",
            "actionable_issue_count",
            "promoted",
            "filesystem",
            "tar_sha_match",
            "latest_build_status",
            "conveyor_count",
            "es_program",
            "outer_error",
        )
    }, indent=2))
    return 0 if summary.get("filesystem", {}).get("l5x_exists") else 1


if __name__ == "__main__":
    raise SystemExit(main())

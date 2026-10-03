#!/usr/bin/env python3
"""Phase D — true virgin TFCP1 build on frozen FINAL SHA (zero MSCRENO residue)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))
os.chdir(REPO)
os.environ["FORTNA_PRISM_DISABLE"] = "1"

OUT = REPO / "exports" / "delivery_gate_20261002"
OUT.mkdir(parents=True, exist_ok=True)
SRC_RUN = Path(r"C:\dev\worktree\FortnaPlus-mscreno-genclose\workspace\_cross_site_peek\TFCP1\RUN")
TAR = REPO / "workspace" / "inbox" / "TFCP1-VIRGIN-DELIVERY-GATE-RUN.tar.gz"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest().upper()


def clear_current_project_disk(repo: Path) -> dict:
    removed = []
    active = repo / "workspace" / "active"
    meta = repo / "workspace" / "active-meta.json"
    wb = repo / "workspace" / "autogen_workbook.json"
    wb_legacy = repo / "workspace" / "active" / "autogen_workbook.json"
    ov = repo / "workspace" / "hardware_io_overrides.json"
    current = repo / "exports" / "current"
    latest = current / "LATEST.json"

    # Invalidate CURRENT pointer (keep historical L5X files).
    if latest.is_file():
        raw = latest.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        hist = current / f"LATEST.historical.cleared.json"
        hist.write_text(raw, encoding="utf-8")
        data["current_invalidated"] = True
        data["current_artifact"] = False
        data["output_controls_enabled"] = False
        data["artifact_disposition"] = "HISTORICAL_CLEARED_PROJECT"
        latest.write_text(json.dumps(data, indent=2), encoding="utf-8")
        removed.append(str(hist))

    if active.is_dir():
        for child in list(active.iterdir()):
            if child.name == "autogen_workbook.json":
                continue
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                try:
                    child.unlink()
                except OSError:
                    pass
            removed.append(str(child))
    for p in (meta, wb, wb_legacy, ov):
        if p.is_file():
            p.unlink()
            removed.append(str(p))
    return {"removed": removed, "ok": True}


def pack_tfcp1_tar() -> tuple[Path, str]:
    if not (SRC_RUN / "project.cfg").is_file():
        raise FileNotFoundError(f"TFCP1 RUN missing: {SRC_RUN}")
    TAR.parent.mkdir(parents=True, exist_ok=True)
    if TAR.is_file():
        TAR.unlink()
    with tarfile.open(TAR, "w:gz") as tf:
        for path in sorted(SRC_RUN.rglob("*")):
            if not path.is_file():
                continue
            # Real Fortna archives use top-level RUN/... members.
            arc = Path("RUN") / path.relative_to(SRC_RUN)
            tf.add(path, arcname=str(arc).replace("\\", "/"))
    return TAR, sha256_file(TAR)


def residue_scan(text: str) -> dict:
    pats = [
        r"MSCRENO",
        r"MSCRENOPICK",
        r"MSCRENOPICK_Area",
        r"MSCRENOPICK_ESZone1",
        r"MSCRENOSHIP",
    ]
    hits = {}
    for p in pats:
        hits[p] = len(re.findall(p, text, flags=re.I))
    hits["total"] = sum(hits.values())
    return hits


def main() -> int:
    summary: dict = {
        "phase": "D_virgin_tfcp1",
        "final_sha": "804e5b40c2e6ea62d8d27ff3a07d16acc89dd8aa",
        "repo": str(REPO),
    }

    # 1) Clear current project
    summary["clear"] = clear_current_project_disk(REPO)

    # 2) Pre-import residue / active-state checks
    pre = {
        "active_meta_exists": (REPO / "workspace" / "active-meta.json").is_file(),
        "active_run_cfg": (REPO / "workspace" / "active" / "RUN" / "project.cfg").is_file(),
        "workbook_exists": (REPO / "workspace" / "autogen_workbook.json").is_file(),
        "latest_invalidated": False,
    }
    latest = REPO / "exports" / "current" / "LATEST.json"
    if latest.is_file():
        lj = json.loads(latest.read_text(encoding="utf-8"))
        pre["latest_invalidated"] = bool(lj.get("current_invalidated"))
        pre["latest_controller"] = lj.get("controller_name")
        pre["latest_current_artifact"] = lj.get("current_artifact")
    summary["pre_import"] = pre
    if pre["active_meta_exists"] or pre["active_run_cfg"] or pre["workbook_exists"]:
        summary["error"] = "Active project residue remains after clear"
        (OUT / "virgin_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 2
    if not pre["latest_invalidated"]:
        summary["error"] = "LATEST.json was not invalidated on clear"
        (OUT / "virgin_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 3

    # 3) Pack + import virgin TFCP1 only
    tar_path, tar_sha = pack_tfcp1_tar()
    summary["run_filename"] = tar_path.name
    summary["run_sha"] = tar_sha
    summary["run_source"] = str(SRC_RUN)

    from apply_recipe import import_package
    from fortna_autogen import generate, load_from_run, resolve_production_library

    meta = import_package(tar_path)
    summary["import_meta"] = {
        "machine": meta.get("machine"),
        "run_fingerprint": meta.get("run_fingerprint"),
        "tar_sha256": meta.get("tar_sha256"),
        "archive_name": meta.get("archive_name"),
    }
    # Reject if import somehow kept Reno machine identity
    mach = str(meta.get("machine") or "").upper()
    if "MSCRENO" in mach or "PICK" in mach:
        summary["error"] = f"Import produced Reno machine identity: {mach}"
        (OUT / "virgin_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 4

    run_dir = Path(meta["run_dir"])
    lib = resolve_production_library(None)
    inp = load_from_run(run_dir)
    inp.include_sys = True
    inp.include_io_map = True
    if mach:
        inp.machine = mach
        inp.project_name = mach

    outer = generate(inp, lib, None)
    rep = outer.get("report") if isinstance(outer.get("report"), dict) else {}
    summary["build_status"] = outer.get("build_status") or rep.get("build_status")
    summary["commissioning_ready"] = (
        outer.get("commissioning_ready")
        or (rep.get("runnability") or {}).get("COMMISSIONING_READY")
        or "NO"
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
    summary["conveyor_count"] = rep.get("conveyor_count")
    summary["outer_error"] = outer.get("error")
    summary["programs"] = rep.get("programs")

    l5x_path = Path(str(outer.get("l5x") or ""))
    summary["promoted"] = l5x_path.is_file() and l5x_path.parent.name.lower() == "current"
    summary["filesystem"] = {
        "l5x_exists": l5x_path.is_file(),
        "absolute_l5x": str(l5x_path.resolve()) if l5x_path.is_file() else "",
        "under_exports_current": l5x_path.is_file() and "current" in l5x_path.parts,
    }

    # Zero-residue scan on virgin L5X + BUILD_ISSUES + LATEST
    blobs = []
    if l5x_path.is_file():
        blobs.append(l5x_path.read_text(encoding="utf-8", errors="replace"))
    for key in ("build_issues_txt", "build_issues_json"):
        p = Path(str(summary.get(key) or ""))
        if p.is_file():
            blobs.append(p.read_text(encoding="utf-8", errors="replace"))
    latest_p = REPO / "exports" / "current" / "LATEST.json"
    if latest_p.is_file():
        blobs.append(latest_p.read_text(encoding="utf-8", errors="replace"))
    combined = "\n".join(blobs)
    summary["foreign_reno_residue"] = residue_scan(combined)
    # Also ensure active meta is TFCP1, not Reno
    am = json.loads((REPO / "workspace" / "active-meta.json").read_text(encoding="utf-8"))
    summary["active_after"] = {
        "machine": am.get("machine"),
        "archive_name": am.get("archive_name"),
        "tar_sha256": am.get("tar_sha256"),
    }

    structural = "PASS"
    if summary.get("build_status") == "BLOCKED":
        structural = "FAIL"
    sc = rep.get("symbol_closure") if isinstance(rep.get("symbol_closure"), dict) else {}
    sp = rep.get("studio_preflight") if isinstance(rep.get("studio_preflight"), dict) else {}
    if sc.get("ok") is False or sp.get("ok") is False:
        structural = "FAIL"
    summary["structural_validation"] = structural

    (OUT / "virgin_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        "VIRGIN",
        summary.get("controller_name"),
        summary.get("build_status"),
        summary.get("l5x_filename"),
        "residue",
        summary["foreign_reno_residue"].get("total"),
    )
    print(json.dumps({
        k: summary.get(k)
        for k in (
            "build_status",
            "structural_validation",
            "commissioning_ready",
            "l5x_filename",
            "l5x_sha256",
            "run_filename",
            "run_sha",
            "foreign_reno_residue",
            "filesystem",
            "active_after",
            "outer_error",
            "conveyor_count",
        )
    }, indent=2))
    ok = (
        summary.get("filesystem", {}).get("l5x_exists")
        and summary["foreign_reno_residue"].get("total", 1) == 0
        and "MSCRENO" not in str(summary.get("controller_name") or "").upper()
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

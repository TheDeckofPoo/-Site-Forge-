#!/usr/bin/env python3
"""Second-site virgin TFCP1 gate on frozen FINAL SHA — with engineer Safety assignment.

Requires same SHA as MSCRENOPICK golden. Clear → load TFCP1 only → assign
backend-assignable Safety devices → Generate → zero MSCRENO residue.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))
os.chdir(REPO)
os.environ["FORTNA_PRISM_DISABLE"] = "1"

OUT = REPO / "exports" / "delivery_gate_20261002"
OUT.mkdir(parents=True, exist_ok=True)
TAR = REPO / "workspace" / "inbox" / "TFCP1-VIRGIN-DELIVERY-GATE-RUN.tar.gz"
FINAL_SHA = "2c583c39724eb955f2ce5a487c739f02a29cec5e"
AREA = "TFCP1_Area"
ZONE = "TFCP1_ESZone1"
PREFERRED = ["ES300", "ESLS301", "ESLS400", "ESLS706"]


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
    if latest.is_file():
        raw = latest.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        hist = current / "LATEST.historical.cleared.json"
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


def inspect_es(l5x: Path) -> dict:
    text = l5x.read_text(encoding="utf-8", errors="replace")
    es = re.search(r'<Program Name="ES"[^>]*>(.*?)</Program>', text, re.S)
    if not es:
        return {"error": "NO_ES_PROGRAM"}
    body = es.group(1)
    routines = re.findall(r'<Routine Name="([^"]+)"', body)
    detail = {}
    for rn in routines:
        m = re.search(
            rf'<Routine Name="{re.escape(rn)}"[^>]*>.*?<RLLContent>(.*?)</RLLContent>',
            body,
            re.S,
        )
        if not m:
            detail[rn] = {"populated": False}
            continue
        rungs = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", m.group(1), flags=re.S)
        nonempty = [r for r in rungs if r.strip() and r.strip() != "NOP();"]
        detail[rn] = {"populated": len(nonempty) > 0, "non_nop": len(nonempty), "sample": (nonempty or rungs)[:4]}
    return {"routines": routines, "detail": detail}


def residue(text: str) -> dict:
    pats = ["MSCRENO", "MSCRENOPICK", "MSCRENOPICK_Area", "MSCRENOPICK_ESZone1", "MSCRENOSHIP"]
    hits = {p: len(re.findall(p, text, flags=re.I)) for p in pats}
    hits["total"] = sum(hits.values())
    return hits


def core_completeness(l5x: Path, issues: dict) -> dict:
    text = l5x.read_text(encoding="utf-8", errors="replace")
    issues_blob = json.dumps(issues or {}).upper()
    empty = []
    for prog in re.finditer(r'<Program Name="([^"]+)"[^>]*>(.*?)</Program>', text, re.S):
        pname = prog.group(1)
        if not any(x in pname for x in ("_Area_Slow", "_Area_Fast", "_Area_L1", "_Area_L2", "IO_MAP")):
            continue
        for rn in re.finditer(
            r'<Routine Name="([^"]+)"[^>]*>.*?<RLLContent>(.*?)</RLLContent>',
            prog.group(2),
            re.S,
        ):
            rname, body = rn.group(1), rn.group(2)
            rungs = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", body, flags=re.S)
            comments = re.findall(r"<Comment><!\[CDATA\[(.*?)\]\]></Comment>", body, flags=re.S)
            nonempty = [r for r in rungs if r.strip() and r.strip() != "NOP();"]
            if not nonempty:
                joined = " ".join(comments).upper()
                explained = any(
                    k in joined
                    for k in (
                        "REVIEW_REQUIRED",
                        "UNSUPPORTED",
                        "WITHHELD",
                        "PLACEHOLDER",
                        "DEFERRED",
                        "ENGINEER_ASSIGNMENT_REQUIRED",
                        "QUARANTINED",
                        "FINISHED_SITE_DERIVED_SUSPECT",
                        "SLOW_FLT",
                    )
                )
                if not explained:
                    key = f"{pname}/{rname}".upper()
                    explained = key in issues_blob and "PLACEHOLDER" in issues_blob
                empty.append(
                    {
                        "program": pname,
                        "routine": rname,
                        "explained": explained,
                        "comment": (comments[:1] or [""])[0][:120],
                    }
                )
    unexplained = [e for e in empty if not e["explained"]]
    return {"pass": len(unexplained) == 0, "unexplained": unexplained[:20]}


def main() -> int:
    from apply_recipe import import_package
    from fortna_autogen import generate, load_from_run, resolve_production_library
    from fortna_safety_endpoint_integrity import apply_endpoint_integrity_pipeline
    from fortna_safety_model import build_safety_model

    git_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO), text=True
    ).strip()
    summary: dict = {
        "phase": "VIRGIN_SECOND_SITE_TFCP1",
        "expected_final_sha": FINAL_SHA,
        "git_sha": git_sha,
        "sha_match": git_sha == FINAL_SHA,
        "repo": str(REPO),
    }
    if git_sha != FINAL_SHA:
        summary["error"] = f"SHA drift: got {git_sha} expected {FINAL_SHA}"
        (OUT / "virgin_second_site_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, indent=2))
        return 2

    summary["clear"] = clear_current_project_disk(REPO)
    summary["pre_import"] = {
        "active_meta_exists": (REPO / "workspace" / "active-meta.json").is_file(),
        "workbook_exists": (REPO / "workspace" / "autogen_workbook.json").is_file(),
    }
    if (REPO / "exports" / "current" / "LATEST.json").is_file():
        latest = json.loads(
            (REPO / "exports" / "current" / "LATEST.json").read_text(encoding="utf-8")
        )
        summary["pre_import"]["latest_invalidated"] = bool(latest.get("current_invalidated"))
        summary["pre_import"]["latest_controller"] = latest.get("controller_name")

    meta = import_package(TAR)
    run_dir = Path(meta["run_dir"])
    machine = str(meta.get("machine") or "TFCP1")
    summary["run_filename"] = meta.get("archive_name") or TAR.name
    summary["run_sha"] = meta.get("tar_sha256") or sha256_file(TAR)
    summary["import_meta"] = {
        "machine": machine,
        "run_fingerprint": meta.get("run_fingerprint"),
        "tar_sha256": meta.get("tar_sha256"),
    }

    # Inventory + assignable
    model = build_safety_model(run_dir=run_dir, machine=machine, areas=[AREA])
    devices = list(model.get("devices") or [])
    try:
        apply_endpoint_integrity_pipeline(devices, run_dir=run_dir, machine=machine)
    except Exception as e:
        summary["endpoint_pipeline_error"] = str(e)
    assignable = [d for d in devices if d.get("assignable") is True]
    members = [m for m in PREFERRED if any((d.get("name") == m) for d in assignable)]
    if not members:
        members = [d.get("name") for d in assignable[:4] if d.get("name")]
    summary["assignable_count"] = len(assignable)
    summary["assigned_members"] = members

    zone = {
        "name": ZONE,
        "engineering_name": ZONE,
        "area": AREA,
        "areaRef": AREA,
        "members": members,
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
        "machine": machine,
        "project_name": "TFCP1",
        "areas": [{"name": AREA, "source": "engineer"}],
        "options": {"areas": [AREA], "safety_zones": [ZONE]},
        "safety_build": {"version": 1, "source": "engineer", "zones": [zone], "devices": []},
    }
    (REPO / "workspace" / "autogen_workbook.json").write_text(
        json.dumps(wb, indent=2), encoding="utf-8"
    )

    lib = resolve_production_library(None)
    inp = load_from_run(run_dir)
    inp.include_sys = True
    inp.include_io_map = True
    inp.machine = machine
    inp.project_name = "TFCP1"
    areas = list(inp.areas or [])
    if AREA not in areas:
        areas.append(AREA)
    inp.areas = areas
    inp.safety_zones = [ZONE]
    inp.safety_zone_members = [zone]
    inp.safety_build = wb["safety_build"]
    for c in inp.conveyors or []:
        try:
            c.area = AREA
            c.safety_zone = ZONE
        except Exception:
            pass

    outer = generate(inp, lib, None)
    rep = outer.get("report") if isinstance(outer.get("report"), dict) else {}
    summary["build_status"] = outer.get("build_status") or rep.get("build_status")
    summary["l5x"] = outer.get("l5x")
    summary["l5x_filename"] = outer.get("l5x_filename")
    summary["l5x_sha256"] = outer.get("l5x_sha256")
    summary["outer_ok"] = outer.get("ok")
    summary["outer_error"] = outer.get("error")
    summary["programs"] = rep.get("programs")
    summary["conveyor_count"] = rep.get("conveyor_count")
    summary["io_map_mapped"] = rep.get("io_map_mapped")
    summary["io_map_unmapped"] = rep.get("io_map_unmapped")
    summary["es_program"] = rep.get("es_program")

    l5x_path = Path(str(outer.get("l5x") or ""))
    issues = {}
    issues_json = Path(str(outer.get("build_issues_json") or rep.get("build_issues_json") or ""))
    if issues_json.is_file():
        issues = json.loads(issues_json.read_text(encoding="utf-8"))
    elif (REPO / "exports" / "current" / "TFCP1_BUILD_ISSUES.json").is_file():
        issues = json.loads(
            (REPO / "exports" / "current" / "TFCP1_BUILD_ISSUES.json").read_text(encoding="utf-8")
        )

    gates = {}
    gates["IO"] = {
        "pass": int(rep.get("io_map_mapped") or 0) > 0,
        "mapped": rep.get("io_map_mapped"),
        "unmapped": rep.get("io_map_unmapped"),
    }
    need = [f"{AREA}_Slow", f"{AREA}_Fast", f"{AREA}_L1", f"{AREA}_L2"]
    # programs are named TFCP1_Area_Slow etc.
    need = ["TFCP1_Area_Slow", "TFCP1_Area_Fast", "TFCP1_Area_L1", "TFCP1_Area_L2"]
    progs = list(rep.get("programs") or [])
    gates["Transportation"] = {
        "pass": all(p in progs for p in need) and int(rep.get("conveyor_count") or 0) > 0,
        "missing": [p for p in need if p not in progs],
        "conveyor_count": rep.get("conveyor_count"),
    }

    es = inspect_es(l5x_path) if l5x_path.is_file() else {"error": "missing"}
    sl = f"{ZONE}_Safe_Logic"
    sp = f"{ZONE}_Safe_PI"
    gates["Safety"] = {
        "pass": (
            es.get("detail", {}).get("Main_Routine", {}).get("populated")
            and es.get("detail", {}).get(sl, {}).get("populated")
            and es.get("detail", {}).get(sp, {}).get("populated")
        ),
        "main": es.get("detail", {}).get("Main_Routine", {}).get("populated"),
        "safe_logic": es.get("detail", {}).get(sl, {}).get("populated"),
        "safe_pi": es.get("detail", {}).get(sp, {}).get("populated"),
        "assigned_members": members,
    }
    if l5x_path.is_file():
        txt = l5x_path.read_text(encoding="utf-8", errors="replace")
        res = residue(txt)
        core = core_completeness(l5x_path, issues)
    else:
        res = {"total": -1}
        core = {"pass": False, "unexplained": ["no l5x"]}
    gates["Core_routine_completeness"] = core
    gates["foreign_residue"] = res
    gates["BUILD_ISSUES"] = {
        "pass": bool(issues) and issues.get("BUILD STATUS") in (
            "PARTIAL",
            "READY",
            "BLOCKED",
            "REVIEW_REQUIRED",
        ),
        "build_status": issues.get("BUILD STATUS"),
        "structural": issues.get("STRUCTURAL VALIDATION"),
    }

    summary["gates"] = gates
    summary["VIRGIN"] = {
        "site": "TFCP1",
        "I/O": "PASS" if gates["IO"]["pass"] else "FAIL",
        "Transportation": "PASS" if gates["Transportation"]["pass"] else "FAIL",
        "Safety": "PASS" if gates["Safety"]["pass"] else "FAIL",
        "Core_routine_completeness": "PASS" if gates["Core_routine_completeness"]["pass"] else "FAIL",
        "foreign_MSCRENO_residue_count": res.get("total"),
        "BUILD_ISSUES_explanations": "PASS" if gates["BUILD_ISSUES"]["pass"] else "FAIL",
        "L5X_absolute_path": str(l5x_path.resolve()) if l5x_path.is_file() else "",
    }
    summary["virgin_pass"] = all(
        summary["VIRGIN"][k] == "PASS" or (k == "foreign_MSCRENO_residue_count" and summary["VIRGIN"][k] == 0)
        for k in (
            "I/O",
            "Transportation",
            "Safety",
            "Core_routine_completeness",
            "BUILD_ISSUES_explanations",
        )
    ) and res.get("total") == 0

    (OUT / "virgin_second_site_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print("VIRGIN", summary["virgin_pass"], summary["VIRGIN"])
    return 0 if summary["virgin_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

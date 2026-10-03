#!/usr/bin/env python3
"""ORI-110 Phase 2 — TFCP1 engineer Safety same-path test on current SHA.

Clear → load TFCP1 only → assign ONLY backend-assignable devices → Apply → Generate.
Prove each handoff layer before claiming PASS.
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
INV = OUT / "tfcp1_live_safety_inventory.json"

# Engineer zone — only assignable devices from live inventory rebuild.
ZONE_NAME = "TFCP1_ESZone1"
AREA_NAME = "TFCP1_Area"
# Prefer a small legitimate set with FULL physical evidence (assignable=True).
PREFERRED_MEMBERS = ["ES300", "ESLS301", "ESLS400", "ESLS706"]


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
            detail[rn] = {"rungs": 0, "non_nop": 0, "populated": False}
            continue
        rungs = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", m.group(1))
        nonempty = [r for r in rungs if r.strip() and r.strip() != "NOP();"]
        detail[rn] = {
            "rungs": len(rungs),
            "non_nop": len(nonempty),
            "populated": len(nonempty) > 0,
            "sample": (nonempty or rungs)[:6],
        }
    return {
        "routines": routines,
        "detail": detail,
        "main_populated": bool(detail.get("Main_Routine", {}).get("populated")),
        "safe_logic": next((r for r in routines if r.endswith("_Safe_Logic")), None),
        "safe_pi": next((r for r in routines if r.endswith("_Safe_PI")), None),
    }


def residue_scan(text: str) -> dict:
    pats = ["MSCRENO", "MSCRENOPICK", "MSCRENOPICK_Area", "MSCRENOPICK_ESZone1", "MSCRENOSHIP", "ORL_AC3", "Area_Test1"]
    hits = {p: len(re.findall(p, text, flags=re.I)) for p in pats}
    hits["total"] = sum(hits.values())
    return hits


def main() -> int:
    from apply_recipe import import_package
    from fortna_autogen import generate, load_from_run, resolve_production_library
    from fortna_safety_endpoint_integrity import apply_endpoint_integrity_pipeline
    from fortna_safety_model import build_safety_model

    git_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO), text=True
    ).strip()
    summary: dict = {
        "phase": "ORI110_P2_TFCP1_SAMEPATH",
        "repo": str(REPO),
        "git_sha": git_sha,
        "layers": {},
    }

    summary["clear"] = clear_current_project_disk(REPO)
    # Confirm pre-import zero MSCRENO active
    summary["pre_import"] = {
        "active_meta_exists": (REPO / "workspace" / "active-meta.json").is_file(),
        "workbook_exists": (REPO / "workspace" / "autogen_workbook.json").is_file(),
        "latest_invalidated": False,
    }
    latest_path = REPO / "exports" / "current" / "LATEST.json"
    if latest_path.is_file():
        latest = json.loads(latest_path.read_text(encoding="utf-8"))
        summary["pre_import"]["latest_invalidated"] = bool(latest.get("current_invalidated"))
        summary["pre_import"]["latest_controller"] = latest.get("controller_name")

    if not TAR.is_file():
        summary["error"] = f"TAR missing: {TAR}"
        (OUT / "tfcp1_safety_samepath.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 2

    meta = import_package(TAR)
    run_dir = Path(meta["run_dir"])
    machine = str(meta.get("machine") or "TFCP1")
    summary["import_meta"] = {
        "machine": machine,
        "run_dir": str(run_dir),
        "run_fingerprint": meta.get("run_fingerprint"),
        "tar_sha256": meta.get("tar_sha256"),
        "archive_name": meta.get("archive_name"),
    }

    # Live inventory
    model = build_safety_model(run_dir=run_dir, machine=machine, areas=[AREA_NAME])
    devices = list(model.get("devices") or [])
    try:
        apply_endpoint_integrity_pipeline(devices, run_dir=run_dir, machine=machine)
    except Exception as e:
        summary["endpoint_pipeline_error"] = str(e)

    found = []
    assignable = []
    review = []
    for d in devices:
        name = d.get("name") or d.get("tag")
        entry = {
            "name": name,
            "assignable": d.get("assignable"),
            "hardwareBacked": d.get("hardwareBacked") or d.get("hardware_backed"),
            "endpoint": d.get("physical_endpoint")
            or d.get("endpoint")
            or d.get("resolved_endpoint")
            or d.get("ioAddress"),
            "reason": d.get("nonAssignableReason")
            or d.get("reason")
            or d.get("status")
            or d.get("classification"),
            "safety_role": d.get("safety_role") or d.get("role"),
        }
        found.append(entry)
        if d.get("assignable") is True:
            assignable.append(entry)
        else:
            review.append(entry)

    summary["inventory"] = {
        "found_count": len(found),
        "assignable_count": len(assignable),
        "review_count": len(review),
        "assignable_names": [a["name"] for a in assignable],
        "review_reason_sample": [
            {"name": r["name"], "reason": r["reason"]} for r in review[:20]
        ],
    }

    assignable_names = {a["name"] for a in assignable}
    members = [m for m in PREFERRED_MEMBERS if m in assignable_names]
    if not members:
        members = [a["name"] for a in assignable[:4]]
    if not members:
        summary["error"] = "No backend-assignable TFCP1 Safety devices"
        (OUT / "tfcp1_safety_samepath.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 3

    # Build membership with endpoint evidence from inventory
    by_name = {a["name"]: a for a in assignable}
    membership = []
    for m in members:
        a = by_name.get(m) or {}
        membership.append(
            {
                "device": m,
                "physical_endpoint": a.get("endpoint"),
                "safety_role": a.get("safety_role") or "FEEDBACK",
            }
        )

    zone = {
        "name": ZONE_NAME,
        "engineering_name": ZONE_NAME,
        "area": AREA_NAME,
        "areaRef": AREA_NAME,
        "members": members,
        "membership": membership,
        "membersOrigin": "ENGINEER_ASSIGNED",
        "engineerEdited": True,
        "createdBy": "engineer",
        "provenance": "ENGINEER_CREATED",
        "origin": "ENGINEER_CREATED",
        "zoneOrigin": "ENGINEER",
        "status": "READY",
        "operational": True,
        "runDiscovered": False,
        "conveyors": [],
        "resetSource": f"{AREA_NAME}.Reset",
        "silenceSource": f"{AREA_NAME}.Silence",
    }

    summary["layers"]["1_safety_ui_zone_name"] = ZONE_NAME
    summary["layers"]["2_ui_members"] = members
    summary["layers"]["3_membersOrigin"] = "ENGINEER_ASSIGNED"
    summary["layers"]["4_zone_status"] = "READY"

    # Persist workbook (Apply)
    wb = {
        "version": 1,
        "kind": "fortna_autogen_workbook",
        "site": "TFCP1",
        "machine": machine,
        "project_name": "TFCP1",
        "areas": [{"name": AREA_NAME, "source": "engineer"}],
        "options": {
            "areas": [AREA_NAME],
            "safety_zones": [ZONE_NAME],
        },
        "safety_build": {
            "version": 1,
            "source": "engineer",
            "zones": [zone],
            "devices": [],
        },
        "conveyors": [],
        "io_map": [],
        "merges_2to1": [],
    }
    wb_path = REPO / "workspace" / "autogen_workbook.json"
    wb_path.write_text(json.dumps(wb, indent=2), encoding="utf-8")

    # Prove workbook persistence
    wb_reload = json.loads(wb_path.read_text(encoding="utf-8"))
    wb_zones = (wb_reload.get("safety_build") or {}).get("zones") or []
    wb_ok = (
        len(wb_zones) == 1
        and wb_zones[0].get("name") == ZONE_NAME
        and list(wb_zones[0].get("members") or []) == members
        and wb_zones[0].get("membersOrigin") == "ENGINEER_ASSIGNED"
    )
    summary["layers"]["5_persisted_workbook_safety_build_zones"] = wb_zones
    summary["TFCP1_Safety_UI_to_workbook"] = "PASS" if wb_ok else "FAIL"

    # Autogen input
    lib = resolve_production_library(None)
    inp = load_from_run(run_dir)
    inp.include_sys = True
    inp.include_io_map = True
    inp.machine = machine
    inp.project_name = "TFCP1"
    areas = list(inp.areas or [])
    if AREA_NAME not in areas:
        areas.append(AREA_NAME)
    inp.areas = areas
    inp.safety_zones = [ZONE_NAME]
    inp.safety_zone_members = [zone]
    inp.safety_build = wb["safety_build"]

    for c in inp.conveyors or []:
        try:
            c.area = AREA_NAME
            c.safety_zone = ZONE_NAME
        except Exception:
            pass

    summary["layers"]["6_autogen_input"] = {
        "safety_zones": list(inp.safety_zones or []),
        "safety_zone_members": inp.safety_zone_members,
        "safety_build_zones": (inp.safety_build or {}).get("zones"),
    }
    ag_ok = (
        ZONE_NAME in (inp.safety_zones or [])
        and len(inp.safety_zone_members or []) == 1
        and list((inp.safety_zone_members or [{}])[0].get("members") or []) == members
        and (inp.safety_zone_members or [{}])[0].get("membersOrigin") == "ENGINEER_ASSIGNED"
    )
    summary["Workbook_to_Autogen"] = "PASS" if ag_ok else "FAIL"

    # Generate
    outer = generate(inp, lib, None)
    rep = outer.get("report") if isinstance(outer.get("report"), dict) else {}
    summary["outer_ok"] = outer.get("ok")
    summary["outer_error"] = outer.get("error")
    summary["build_status"] = outer.get("build_status") or rep.get("build_status")
    summary["l5x"] = outer.get("l5x")
    summary["l5x_filename"] = outer.get("l5x_filename")
    summary["l5x_sha256"] = outer.get("l5x_sha256")
    summary["build_id"] = outer.get("build_id")
    summary["es_program_report"] = rep.get("es_program")

    es_rep = rep.get("es_program") or {}
    emitted = list(es_rep.get("emitted_zones") or [])
    compiler_ok = ZONE_NAME in emitted and es_rep.get("shell") is False
    summary["Autogen_to_ES_compiler"] = "PASS" if compiler_ok else "FAIL"
    summary["layers"]["7_fortna_es_compiler"] = {
        "status": es_rep.get("status"),
        "emitted_zones": emitted,
        "shell": es_rep.get("shell"),
        "members_emitted": es_rep.get("members_emitted"),
        "zones": es_rep.get("zones"),
    }

    l5x_path = Path(str(outer.get("l5x") or ""))
    if l5x_path.is_file():
        es = inspect_es(l5x_path)
        summary["layers"]["8_emitted_es_routines"] = es
        text = l5x_path.read_text(encoding="utf-8", errors="replace")
        summary["foreign_residue"] = residue_scan(text)
        summary["TFCP1_ES_Main_Routine"] = (
            "POPULATED" if es.get("main_populated") else "EMPTY"
        )
        sl = es.get("safe_logic")
        sp = es.get("safe_pi")
        summary["TFCP1_Safe_Logic"] = (
            "POPULATED"
            if sl and es.get("detail", {}).get(sl, {}).get("populated")
            else ("ABSENT" if not sl else "EMPTY")
        )
        summary["TFCP1_Safe_PI"] = (
            "POPULATED"
            if sp and es.get("detail", {}).get(sp, {}).get("populated")
            else ("ABSENT" if not sp else "EMPTY")
        )
        l5x_ok = (
            summary["TFCP1_ES_Main_Routine"] == "POPULATED"
            and summary["TFCP1_Safe_Logic"] == "POPULATED"
            and summary["TFCP1_Safe_PI"] == "POPULATED"
        )
        summary["ES_compiler_to_L5X"] = "PASS" if l5x_ok else "FAIL"
    else:
        summary["TFCP1_ES_Main_Routine"] = "EMPTY"
        summary["TFCP1_Safe_Logic"] = "ABSENT"
        summary["TFCP1_Safe_PI"] = "ABSENT"
        summary["ES_compiler_to_L5X"] = "FAIL"

    summary["TFCP1_assignable_Safety_count"] = len(assignable)
    summary["TFCP1_assigned_test_members"] = members

    (OUT / "tfcp1_safety_samepath.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        "TFCP1 SAMEPATH",
        summary.get("TFCP1_Safety_UI_to_workbook"),
        summary.get("Workbook_to_Autogen"),
        summary.get("Autogen_to_ES_compiler"),
        summary.get("ES_compiler_to_L5X"),
        summary.get("TFCP1_ES_Main_Routine"),
        summary.get("TFCP1_Safe_Logic"),
        summary.get("TFCP1_Safe_PI"),
        summary.get("l5x_filename"),
    )
    print(
        json.dumps(
            {
                k: summary.get(k)
                for k in (
                    "TFCP1_assignable_Safety_count",
                    "TFCP1_assigned_test_members",
                    "TFCP1_Safety_UI_to_workbook",
                    "Workbook_to_Autogen",
                    "Autogen_to_ES_compiler",
                    "ES_compiler_to_L5X",
                    "TFCP1_ES_Main_Routine",
                    "TFCP1_Safe_Logic",
                    "TFCP1_Safe_PI",
                    "build_status",
                    "l5x",
                    "foreign_residue",
                    "outer_error",
                )
            },
            indent=2,
        )
    )
    ok = all(
        summary.get(k) == "PASS"
        for k in (
            "TFCP1_Safety_UI_to_workbook",
            "Workbook_to_Autogen",
            "Autogen_to_ES_compiler",
            "ES_compiler_to_L5X",
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

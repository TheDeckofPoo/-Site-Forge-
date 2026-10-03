#!/usr/bin/env python3
"""ORI-110 Phase 1 — reproduce ORL_AC3 engineer Safety path on current SHA.

NO CODE CHANGES. Uses recovered known-good Area_Test1_ESZone1 membership from
workspace/.internal/builds/20260929-200817 (ORL_AC3_2026_09_29_2008.L5X era).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))
os.chdir(REPO)
os.environ["FORTNA_PRISM_DISABLE"] = "1"

TAR = REPO / "workspace" / "inbox" / "20260306-2131-ORL-LKL-ORL_AC3-RUN.tar.gz"
OUT = REPO / "exports" / "delivery_gate_20261002"
OUT.mkdir(parents=True, exist_ok=True)

# Exact engineer zone recovered from known-good autogen_input (20260929-200817).
ZONE = {
    "name": "Area_Test1_ESZone1",
    "source_id": "szone_orl_repro",
    "id": "szone_orl_repro",
    "engineering_name": "Area_Test1_ESZone1",
    "area": "Area_Test1",
    "areaRef": "Area_Test1",
    "members": [
        "1ES",
        "1ES1",
        "ESLS101",
        "ESLS103",
        "1ESR1",
        "1ESR2",
        "1MCR1",
        "3MCR1",
    ],
    "membersOrigin": "ENGINEER_ASSIGNED",
    "engineerEdited": True,
    "createdBy": "engineer",
    "provenance": "ENGINEER_CREATED",
    "origin": "ENGINEER_CREATED",
    "zoneOrigin": "ENGINEER",
    "status": "READY",
    "operational": True,
    "runDiscovered": False,
    "conveyors": [
        "P900",
        "P902",
        "P904",
        "P910",
        "P912",
        "P914",
        "P916",
        "P918",
        "P920",
    ],
    "conveyorRefs": [
        "P900",
        "P902",
        "P904",
        "P910",
        "P912",
        "P914",
        "P916",
        "P918",
        "P920",
    ],
    "eStops": ["1ES", "1ES1"],
    "esrDevices": ["1ESR1", "1ESR2"],
    "mcrDevices": ["1MCR1", "3MCR1"],
    "eslsDevices": ["ESLS101", "ESLS103"],
    "resetSource": "Area_Test1.Reset",
    "silenceSource": "Area_Test1.Silence",
    "reset_source": "Area_Test1.Reset",
    "silence_source": "Area_Test1.Silence",
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


def main() -> int:
    import subprocess

    from apply_recipe import import_package
    from fortna_autogen import generate, load_from_run, resolve_production_library

    git_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO), text=True
    ).strip()
    summary: dict = {
        "phase": "ORI110_P1_ORL_AC3",
        "repo": str(REPO),
        "git_sha": git_sha,
        "tar": str(TAR),
        "recovered_zone": ZONE,
        "layers": {},
    }
    if not TAR.is_file():
        summary["error"] = f"TAR missing: {TAR}"
        (OUT / "orl_safety_repro.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 2

    summary["tar_sha256"] = sha256_file(TAR)
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
    inp = load_from_run(run_dir)
    inp.include_sys = True
    inp.include_io_map = True
    inp.machine = str(meta.get("machine") or "ORL_AC3")
    inp.project_name = "ORL_AC3"
    # Ensure Area_Test1 present
    areas = list(inp.areas or [])
    if "Area_Test1" not in areas:
        areas.append("Area_Test1")
    inp.areas = areas

    # Layer 1-4: engineer Safety UI equivalent
    summary["layers"]["1_safety_ui_zone_name"] = ZONE["name"]
    summary["layers"]["2_ui_members"] = list(ZONE["members"])
    summary["layers"]["3_membersOrigin"] = ZONE["membersOrigin"]
    summary["layers"]["4_zone_status"] = ZONE["status"]

    inp.safety_zones = [ZONE["name"]]
    inp.safety_zone_members = [ZONE]
    inp.safety_build = {
        "version": 1,
        "source": "engineer",
        "zones": [ZONE],
        "devices": [],
    }

    # Tie Area_Test1 conveyors to the zone when present
    for c in inp.conveyors or []:
        name = getattr(c, "name", None) or (c.get("name") if isinstance(c, dict) else None)
        if name in ZONE["conveyors"]:
            try:
                c.safety_zone = ZONE["name"]
                c.area = "Area_Test1"
            except Exception:
                if isinstance(c, dict):
                    c["safety_zone"] = ZONE["name"]
                    c["area"] = "Area_Test1"

    # Layer 5: persist workbook
    wb = {
        "version": 1,
        "kind": "fortna_autogen_workbook",
        "site": "ORL",
        "machine": inp.machine,
        "project_name": "ORL_AC3",
        "areas": [{"name": "Area_Test1", "source": "engineer"}],
        "options": {
            "areas": ["Area_Test1"],
            "safety_zones": [ZONE["name"]],
        },
        "safety_build": inp.safety_build,
        "conveyors": [],
        "io_map": [],
        "merges_2to1": [],
    }
    wb_path = REPO / "workspace" / "autogen_workbook.json"
    wb_path.write_text(json.dumps(wb, indent=2), encoding="utf-8")
    summary["layers"]["5_persisted_workbook_safety_build_zones"] = wb["safety_build"]["zones"]

    # Layer 6: AutogenInput snapshot before generate
    summary["layers"]["6_autogen_input"] = {
        "safety_zones": list(inp.safety_zones or []),
        "safety_zone_members": inp.safety_zone_members,
        "safety_build": inp.safety_build,
        "areas": list(inp.areas or []),
        "conveyor_count": len(inp.conveyors or []),
    }

    # Generate into exports/current
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

    # Layer 7: fortna_es_compiler IR from build dir if present
    build_id = outer.get("build_id")
    build_dir = REPO / "workspace" / ".internal" / "builds" / str(build_id or "")
    ir_candidates = [
        build_dir / "es_ir.json",
        build_dir / "fortna_es_ir.json",
        build_dir / "es_compiler_ir.json",
        build_dir / "autogen_result.json",
    ]
    ir_found = None
    for c in ir_candidates:
        if c.is_file():
            ir_found = c
            break
    # Also search
    if ir_found is None and build_dir.is_dir():
        for p in build_dir.rglob("*es*"):
            if p.is_file() and p.suffix.lower() in {".json", ".txt"}:
                if "es" in p.name.lower():
                    ir_found = p
                    break
    summary["layers"]["7_es_compiler_ir_path"] = str(ir_found) if ir_found else None
    if ir_found and ir_found.name == "autogen_result.json":
        try:
            ar = json.loads(ir_found.read_text(encoding="utf-8"))
            summary["layers"]["7_es_from_autogen_result"] = {
                k: ar.get(k)
                for k in ("es_program", "es", "safety", "programs")
                if k in ar
            } or {
                "keys_sample": list(ar.keys())[:40],
                "es_program": (ar.get("report") or {}).get("es_program")
                if isinstance(ar.get("report"), dict)
                else None,
            }
        except Exception as e:
            summary["layers"]["7_es_compiler_ir_error"] = str(e)

    l5x_path = Path(str(outer.get("l5x") or ""))
    if l5x_path.is_file():
        es = inspect_es(l5x_path)
        summary["layers"]["8_emitted_es_routines"] = es
        summary["ORL_ES_Main_Routine"] = (
            "POPULATED" if es.get("main_populated") else "EMPTY"
        )
        sl = es.get("safe_logic")
        sp = es.get("safe_pi")
        summary["ORL_Safe_Logic"] = (
            "POPULATED"
            if sl and es.get("detail", {}).get(sl, {}).get("populated")
            else ("ABSENT" if not sl else "EMPTY")
        )
        summary["ORL_Safe_PI"] = (
            "POPULATED"
            if sp and es.get("detail", {}).get(sp, {}).get("populated")
            else ("ABSENT" if not sp else "EMPTY")
        )
        summary["ORL_current_SHA_reproduction"] = (
            "PASS"
            if summary["ORL_ES_Main_Routine"] == "POPULATED"
            and summary["ORL_Safe_Logic"] == "POPULATED"
            and summary["ORL_Safe_PI"] == "POPULATED"
            else "FAIL"
        )
    else:
        summary["ORL_current_SHA_reproduction"] = "FAIL"
        summary["ORL_ES_Main_Routine"] = "EMPTY"
        summary["ORL_Safe_Logic"] = "ABSENT"
        summary["ORL_Safe_PI"] = "ABSENT"

    (OUT / "orl_safety_repro.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        "ORL REPRO",
        summary.get("ORL_current_SHA_reproduction"),
        summary.get("ORL_ES_Main_Routine"),
        summary.get("ORL_Safe_Logic"),
        summary.get("ORL_Safe_PI"),
        summary.get("l5x_filename"),
    )
    print(json.dumps({k: summary.get(k) for k in (
        "ORL_current_SHA_reproduction",
        "ORL_ES_Main_Routine",
        "ORL_Safe_Logic",
        "ORL_Safe_PI",
        "build_status",
        "l5x",
        "outer_error",
        "es_program_report",
    )}, indent=2))
    return 0 if summary.get("ORL_current_SHA_reproduction") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

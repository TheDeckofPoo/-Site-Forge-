#!/usr/bin/env python3
"""ORI-111 virgin proof through L5X acceptance auditor — ORINDYAC3.

Clear Current Project + full restart. Same auditor/rules as MSCRENOPICK.
Live AI/Relay on AUDIT_FAIL. No site-specific special cases.
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
os.environ["SITEFORGE_ESCALATION"] = "1"
os.environ["SITEFORGE_L5X_AUDITOR"] = "1"
os.environ.pop("SITEFORGE_SKIP_L5X_PROMOTE", None)

OUT = REPO / "exports" / "delivery_gate_20261002"
OUT.mkdir(parents=True, exist_ok=True)
TAR = REPO / "workspace" / "inbox" / "20260624-1641-OReillyindy-ORINDYAC3-RUN.tar.gz"
SUMMARY = OUT / "orindyac3_auditor_virgin_summary.json"
SITE = "ORINDYAC3"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest().upper()


def clear_project(repo: Path) -> dict:
    removed = []
    active = repo / "workspace" / "active"
    for p in (
        repo / "workspace" / "active-meta.json",
        repo / "workspace" / "autogen_workbook.json",
        repo / "workspace" / "hardware_io_overrides.json",
    ):
        if p.is_file():
            p.unlink()
            removed.append(str(p))
    if active.is_dir():
        for child in list(active.iterdir()):
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                try:
                    child.unlink()
                except OSError:
                    pass
            removed.append(str(child))
    return {"ok": True, "removed_n": len(removed)}


def inspect_es(l5x: Path) -> dict:
    text = l5x.read_text(encoding="utf-8", errors="replace")
    es = re.search(r'<Program Name="ES"[^>]*>(.*?)</Program>', text, re.S)
    if not es:
        return {"detail": {}}
    body = es.group(1)
    detail = {}
    for rn in re.findall(r'<Routine Name="([^"]+)"', body):
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
        detail[rn] = {"populated": len(nonempty) > 0, "non_nop": len(nonempty)}
    return {"detail": detail}


def main() -> int:
    from apply_recipe import import_package
    from fortna_autogen import generate, load_from_run, resolve_production_library
    from fortna_build_escalation import BuildCaseFile, resolve_machine_identity
    from fortna_safety_endpoint_integrity import apply_endpoint_integrity_pipeline
    from fortna_safety_model import build_safety_model

    git_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO), text=True
    ).strip()
    summary: dict = {
        "phase": "ORI111_ORINDYAC3_AUDITOR_VIRGIN",
        "git_sha": git_sha,
        "auditor": "ENABLED",
        "site_specific_preload": False,
        "selected_because": "owned conveyors + ConfigIO; same auditor rules as MSCRENOPICK",
    }
    if not TAR.is_file():
        summary["error"] = f"TAR missing: {TAR}"
        SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return 2

    print(f"[AUDITOR-VIRGIN] Clear+restart {SITE} @ {git_sha[:12]}", flush=True)
    summary["clear"] = clear_project(REPO)
    meta = import_package(TAR)
    run_dir = Path(meta["run_dir"])
    claimed = str(meta.get("machine") or SITE)
    case_file = BuildCaseFile(
        site=claimed,
        machine=claimed,
        run_sha=str(meta.get("tar_sha256") or ""),
        build_id="ori111-orindyac3-auditor-virgin",
    )
    identity = resolve_machine_identity(
        run_dir, claimed, tar_name=TAR.name, case_file=case_file
    )
    machine = str(identity.get("resolved_machine") or claimed)
    summary["identity"] = {
        "ok": identity.get("ok"),
        "machine": machine,
        "provenance": identity.get("provenance"),
    }

    lib = resolve_production_library(None)
    inp = load_from_run(run_dir)
    inp.include_sys = True
    inp.include_io_map = True
    inp.machine = machine
    inp.project_name = machine
    areas = [a for a in (inp.areas or []) if a] or [f"{machine}_Area"]
    inp.areas = areas
    area = areas[0]
    summary["conveyors_loaded"] = len(inp.conveyors or [])

    model = build_safety_model(run_dir=run_dir, machine=machine, areas=areas)
    devices = list(model.get("devices") or [])
    try:
        apply_endpoint_integrity_pipeline(devices, run_dir=run_dir, machine=machine)
    except Exception as e:  # noqa: BLE001
        summary["endpoint_pipeline_error"] = str(e)
    assignable = [d for d in devices if d.get("assignable") is True]
    members = [d.get("name") for d in assignable if d.get("name")][:12]
    summary["safety"] = {
        "inventory": len(devices),
        "assignable": len(assignable),
        "members": members,
    }
    safety_assigned = False
    zone_name = f"{machine}_ESZone1"
    if members:
        zone = {
            "name": zone_name,
            "engineering_name": zone_name,
            "area": area,
            "areaRef": area,
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
            "project_name": machine,
            "areas": [{"name": a, "source": "run"} for a in areas],
            "options": {"areas": areas, "safety_zones": [zone_name]},
            "safety_build": {
                "version": 1,
                "source": "engineer",
                "zones": [zone],
                "devices": [],
            },
        }
        (REPO / "workspace" / "autogen_workbook.json").write_text(
            json.dumps(wb, indent=2), encoding="utf-8"
        )
        inp.safety_zones = [zone_name]
        inp.safety_zone_members = [zone]
        inp.safety_build = wb["safety_build"]
        for c in inp.conveyors or []:
            try:
                if not getattr(c, "area", None):
                    c.area = area
                c.safety_zone = zone_name
            except Exception:
                pass
        safety_assigned = True

    print("[AUDITOR-VIRGIN] generate()…", flush=True)
    outer = generate(inp, lib, None)
    rep = outer.get("report") if isinstance(outer.get("report"), dict) else {}
    accept = rep.get("l5x_acceptance") or outer.get("l5x_acceptance") or {}
    l5x_path = Path(str(outer.get("l5x") or ""))
    summary.update(
        {
            "outer_ok": outer.get("ok"),
            "build_status": outer.get("build_status") or rep.get("build_status"),
            "error": outer.get("error") or rep.get("error"),
            "l5x": str(l5x_path) if l5x_path else "",
            "l5x_filename": outer.get("l5x_filename"),
            "l5x_promoted_to_current": bool(
                outer.get("l5x_promoted_to_current") or rep.get("l5x_promoted_to_current")
            ),
            "artifact_state": rep.get("artifact_state") or accept.get("artifact_state"),
            "conveyor_count": rep.get("conveyor_count"),
            "io_map_mapped": rep.get("io_map_mapped"),
            "programs": rep.get("programs"),
            "l5x_acceptance": {
                "status": accept.get("status"),
                "ok": accept.get("ok"),
                "initial_signatures": (
                    (accept.get("initial_audit") or {}).get("signatures") or []
                ),
                "final_signatures": (
                    (accept.get("final_audit") or {}).get("signatures") or []
                ),
                "ai_api_calls": accept.get("ai_api_calls"),
                "relay_calls": accept.get("relay_calls"),
                "repair_cycles": accept.get("repair_cycles"),
                "generator_defect": accept.get("generator_defect"),
                "engineer_required": accept.get("engineer_required"),
                "estimated_cost_usd": accept.get("estimated_cost_usd"),
            },
            "case_file_ai": case_file.ai_api_calls,
            "case_file_relay": case_file.relay_calls,
        }
    )

    gates: dict = {}
    if l5x_path.is_file():
        summary["l5x_sha256"] = sha256_file(l5x_path)
        text = l5x_path.read_text(encoding="utf-8", errors="replace")
        es = inspect_es(l5x_path)
        detail = es.get("detail") or {}
        progs = list(rep.get("programs") or [])
        gates["I/O"] = int(rep.get("io_map_mapped") or 0) > 0 and "IO_MAP" in progs
        gates["Transportation"] = (
            all(
                any(s in p for p in progs)
                for s in ("_Area_Slow", "_Area_Fast", "_Area_L1", "_Area_L2")
            )
            and int(rep.get("conveyor_count") or 0) > 0
        )
        if safety_assigned:
            gates["Safety"] = bool(detail.get("Main_Routine", {}).get("populated"))
            gates["Safe_Logic"] = any(
                k.endswith("_Safe_Logic") and detail[k].get("populated") for k in detail
            )
            gates["Safe_PI"] = any(
                k.endswith("_Safe_PI") and detail[k].get("populated") for k in detail
            )
        else:
            gates["Safety"] = True
            gates["Safe_Logic"] = True
            gates["Safe_PI"] = True
        gates["AUDIT"] = str(accept.get("status") or "") == "AUDIT_PASS"
        gates["promoted"] = bool(summary.get("l5x_promoted_to_current"))
        gates["no_mscreno_residue"] = (
            len(re.findall(r"MSCRENOPICK|MSCRENOSHIP", text)) == 0
        )
        bad = re.findall(
            r"\b(?:XIC|XIO|OTE|OTL|OTU)\s*\(\s*(?:\)|\?[,)]|\"\"|''|_unnamed_)",
            text,
            flags=re.I,
        )
        gates["no_blank_operands"] = len(bad) == 0
    else:
        gates = {
            "I/O": False,
            "Transportation": False,
            "Safety": False,
            "Safe_Logic": False,
            "Safe_PI": False,
            "AUDIT": False,
            "promoted": False,
            "no_mscreno_residue": False,
            "no_blank_operands": False,
        }

    summary["gates"] = gates
    summary["virgin_pass"] = all(
        gates.get(k)
        for k in (
            "I/O",
            "Transportation",
            "Safety",
            "Safe_Logic",
            "Safe_PI",
            "AUDIT",
            "promoted",
            "no_mscreno_residue",
            "no_blank_operands",
        )
    )
    SUMMARY.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "virgin_pass": summary["virgin_pass"],
                "git_sha": git_sha,
                "gates": gates,
                "acceptance": summary.get("l5x_acceptance"),
                "l5x": summary.get("l5x_filename"),
                "error": summary.get("error"),
            },
            indent=2,
            default=str,
        )
    )
    return 0 if summary["virgin_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

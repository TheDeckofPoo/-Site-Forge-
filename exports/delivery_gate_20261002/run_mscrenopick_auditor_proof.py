#!/usr/bin/env python3
"""ORI-111: MSCRENOPICK real-build proof through L5X acceptance auditor.

Requires AUDIT_PASS before CURRENT promotion.
Known-good Safety membership: ESPB2 / ESPB24 / ESPB32 / ESLS2 → MSCRENOPICK_ESZone1.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
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
TAR = REPO / "workspace" / "inbox" / "20260813-1132-MSCRENO-MSCRENOPICK-RUN.tar.gz"
SUMMARY = OUT / "mscrenopick_auditor_proof_summary.json"

MEMBERS = ["ESPB2", "ESPB24", "ESPB32", "ESLS2"]
ZONE = "MSCRENOPICK_ESZone1"
AREA = "MSCRENOPICK_Area"


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
        return {"error": "NO_ES_PROGRAM", "detail": {}}
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
    from fortna_l5x_acceptance_auditor import audit_l5x, build_expected_artifact_manifest

    git_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO), text=True
    ).strip()
    summary: dict = {
        "phase": "ORI111_MSCRENOPICK_AUDITOR_PROOF",
        "git_sha": git_sha,
        "auditor": "ENABLED",
    }
    if not TAR.is_file():
        summary["error"] = f"TAR missing: {TAR}"
        SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 2

    meta = import_package(TAR)
    run_dir = Path(meta["run_dir"])
    machine = str(meta.get("machine") or "MSCRENOPICK")
    lib = resolve_production_library(None)
    inp = load_from_run(run_dir)
    inp.include_sys = True
    inp.include_io_map = True
    inp.machine = machine
    inp.project_name = machine
    areas = [a for a in (inp.areas or []) if a] or [AREA]
    if AREA not in areas:
        areas = [AREA] + areas
    inp.areas = areas
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
        "machine": machine,
        "project_name": machine,
        "areas": [{"name": a, "source": "run"} for a in areas],
        "options": {"areas": areas, "safety_zones": [ZONE]},
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
            if not getattr(c, "area", None):
                c.area = AREA
            c.safety_zone = ZONE
        except Exception:
            pass

    print(f"[AUDITOR] generate MSCRENOPICK @ {git_sha[:12]}", flush=True)
    outer = generate(inp, lib, None)
    rep = outer.get("report") if isinstance(outer.get("report"), dict) else {}
    l5x_path = Path(str(outer.get("l5x") or ""))
    accept = rep.get("l5x_acceptance") or outer.get("l5x_acceptance") or {}
    summary.update(
        {
            "outer_ok": outer.get("ok"),
            "build_status": outer.get("build_status") or rep.get("build_status"),
            "l5x": str(l5x_path) if l5x_path else "",
            "l5x_filename": outer.get("l5x_filename") or rep.get("l5x_filename"),
            "l5x_promoted_to_current": bool(
                outer.get("l5x_promoted_to_current") or rep.get("l5x_promoted_to_current")
            ),
            "artifact_state": rep.get("artifact_state") or accept.get("artifact_state"),
            "l5x_acceptance": {
                "status": accept.get("status"),
                "ok": accept.get("ok"),
                "failure_count": (accept.get("final_audit") or accept.get("initial_audit") or {}).get(
                    "failure_count"
                ),
                "signatures": (accept.get("final_audit") or accept.get("initial_audit") or {}).get(
                    "signatures"
                ),
                "ai_api_calls": accept.get("ai_api_calls"),
                "relay_calls": accept.get("relay_calls"),
                "repair_cycles": accept.get("repair_cycles"),
                "generator_defect": accept.get("generator_defect"),
            },
            "conveyor_count": rep.get("conveyor_count"),
            "io_map_mapped": rep.get("io_map_mapped"),
            "programs": rep.get("programs"),
            "error": outer.get("error") or rep.get("error"),
        }
    )

    gates: dict = {}
    if l5x_path.is_file():
        summary["l5x_sha256"] = sha256_file(l5x_path)
        es = inspect_es(l5x_path)
        detail = es.get("detail") or {}
        gates["I/O"] = int(rep.get("io_map_mapped") or 0) > 0 and "IO_MAP" in (
            rep.get("programs") or []
        )
        progs = list(rep.get("programs") or [])
        gates["Transportation"] = all(
            any(s in p for p in progs) for s in ("_Area_Slow", "_Area_Fast", "_Area_L1", "_Area_L2")
        ) and int(rep.get("conveyor_count") or 0) > 0
        gates["Safety"] = "ES" in progs
        gates["Main_Routine"] = bool(detail.get("Main_Routine", {}).get("populated"))
        gates["Safe_Logic"] = bool(
            detail.get(f"{ZONE}_Safe_Logic", {}).get("populated")
        )
        gates["Safe_PI"] = bool(detail.get(f"{ZONE}_Safe_PI", {}).get("populated"))
        text = l5x_path.read_text(encoding="utf-8", errors="replace")
        bad = re.findall(
            r"\b(?:XIC|XIO|OTE|OTL|OTU)\s*\(\s*(?:\)|\?[,)]|\"\"|''|_unnamed_)",
            text,
            flags=re.I,
        )
        gates["no_blank_operands"] = len(bad) == 0
        gates["no_foreign_residue"] = "MSCRENOSHIP" not in text or text.count(
            "MSCRENOSHIP"
        ) == 0
        # Re-audit with explicit manifest for report clarity
        man = build_expected_artifact_manifest(
            inp, report=rep, build_id="mscreno-auditor-proof", git_sha=git_sha
        )
        reaudit = audit_l5x(l5x_path, man)
        gates["AUDIT"] = bool(reaudit.get("ok"))
        summary["reaudit"] = {
            "status": reaudit.get("status"),
            "signatures": reaudit.get("signatures"),
        }
        summary["es_detail_populated"] = {
            k: v.get("populated") for k, v in detail.items()
        }
    else:
        gates = {
            "I/O": False,
            "Transportation": False,
            "Safety": False,
            "Main_Routine": False,
            "Safe_Logic": False,
            "Safe_PI": False,
            "no_blank_operands": False,
            "no_foreign_residue": False,
            "AUDIT": False,
        }

    gates["promoted"] = bool(summary.get("l5x_promoted_to_current"))
    summary["gates"] = gates
    summary["proof_pass"] = all(
        gates.get(k)
        for k in (
            "I/O",
            "Transportation",
            "Safety",
            "Main_Routine",
            "Safe_Logic",
            "Safe_PI",
            "no_blank_operands",
            "AUDIT",
            "promoted",
        )
    )
    SUMMARY.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "proof_pass": summary["proof_pass"],
                "git_sha": git_sha,
                "gates": gates,
                "l5x": summary.get("l5x"),
                "acceptance": summary.get("l5x_acceptance"),
                "error": summary.get("error"),
            },
            indent=2,
            default=str,
        )
    )
    return 0 if summary["proof_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

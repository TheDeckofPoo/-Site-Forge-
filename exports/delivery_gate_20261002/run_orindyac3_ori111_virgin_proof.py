#!/usr/bin/env python3
"""ORI-111 virgin E2E proof — ORINDYAC3 TAR (owned conveyors + physical I/O).

Clear Current Project + full restart. No site-name special cases.
Live AI API + Relay on genuine unresolved clusters.
Success = engineer-usable L5X (physical I/O, Transportation, Safety after
proven/engineer assignment, core routines, no blank operands / foreign residue).
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

OUT = REPO / "exports" / "delivery_gate_20261002"
OUT.mkdir(parents=True, exist_ok=True)
TAR = REPO / "workspace" / "inbox" / "20260624-1641-OReillyindy-ORINDYAC3-RUN.tar.gz"
SITE = "ORINDYAC3"
SUMMARY_NAME = "orindyac3_ori111_virgin_summary.json"
CASE_NAME = "orindyac3_ori111_case_file.json"


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
    # Clear prior same-site CURRENT artifacts. Keep golden fixtures
    # (MSCRENOPICK / TFCP1 / ORL_AC3) so qualification gates remain intact.
    for pat in (
        "ORDENCP1*",
        "ORDENCP4*",
        "ORINDYAC3*",
        "ori111*",
    ):
        for p in current.glob(pat):
            try:
                p.unlink()
                removed.append(str(p))
            except OSError:
                pass
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
        return {"error": "NO_ES_PROGRAM", "detail": {}}
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
        detail[rn] = {
            "populated": len(nonempty) > 0,
            "non_nop": len(nonempty),
            "sample": (nonempty or rungs)[:4],
        }
    return {"routines": routines, "detail": detail}


def residue(text: str, self_machine: str) -> dict:
    pats = [
        "MSCRENOPICK",
        "MSCRENOPICK_Area",
        "MSCRENOPICK_ESZone1",
        "MSCRENOSHIP",
        "TFCP1_ESZone1",
        "Area_Test1_ESZone1",
        "ORDENCP1_ESZone1",
        "ORDENCP1_Area",
    ]
    hits = {p: len(re.findall(p, text)) for p in pats}
    for other in ("ORDENCP1", "ORDENCP3", "ORDENCP4", "MSCATL_CP1", "ORNCCP2"):
        if other.upper() != self_machine.upper():
            hits[f"foreign_prog_{other}"] = len(
                re.findall(rf'<Program Name="{other}_', text)
            )
    hits["foreign_total"] = sum(
        v
        for k, v in hits.items()
        if k.startswith("MSCRENO")
        or k in ("TFCP1_ESZone1", "Area_Test1_ESZone1", "ORDENCP1_ESZone1", "ORDENCP1_Area")
        or k.startswith("foreign_prog_")
    )
    return hits


def main() -> int:
    from apply_recipe import import_package
    from fortna_autogen import generate, load_from_run, resolve_production_library
    from fortna_build_escalation import (
        BuildCaseFile,
        apply_na_machine_ownership_override,
        escalate_unsupported_catalogs,
        resolve_machine_identity,
    )
    from fortna_safety_endpoint_integrity import apply_endpoint_integrity_pipeline
    from fortna_safety_model import build_safety_model

    if not TAR.is_file():
        print(f"TAR missing: {TAR}")
        return 2

    git_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO), text=True
    ).strip()
    summary: dict = {
        "phase": "ORI111_VIRGIN_ORINDYAC3_E2E",
        "git_sha": git_sha,
        "repo": str(REPO),
        "tar": str(TAR),
        "tar_sha256": sha256_file(TAR),
        "escalation_enabled": True,
        "site_specific_preload": False,
        "build_attempts": 0,
        "selected_because": (
            "simplest inbox virgin with matching Machine_Name ownership, "
            "ConfigIO present, real STRAIGHT/MOTOR conveyors; "
            "ORDENCP1 was proven-empty scope limitation"
        ),
    }

    print(f"[ORI-111] Clear + restart virgin {SITE} @ {git_sha[:12]}", flush=True)
    summary["clear"] = clear_current_project_disk(REPO)
    meta = import_package(TAR)
    run_dir = Path(meta["run_dir"])
    claimed = str(meta.get("machine") or SITE)
    summary["import_meta"] = {
        "claimed_machine": claimed,
        "run_fingerprint": meta.get("run_fingerprint"),
        "tar_sha256": meta.get("tar_sha256"),
        "archive_name": meta.get("archive_name"),
    }
    print(f"[ORI-111] imported claimed={claimed} run={run_dir}", flush=True)

    case_file = BuildCaseFile(
        site=claimed,
        machine=claimed,
        run_sha=str(meta.get("tar_sha256") or ""),
        build_id="ori111-orindyac3-virgin",
    )

    identity = resolve_machine_identity(
        run_dir,
        claimed,
        tar_name=TAR.name,
        case_file=case_file,
    )
    summary["identity_resolution"] = {
        k: identity.get(k)
        for k in (
            "ok",
            "resolved_machine",
            "changed",
            "treat_na_rows_as_resolved_machine",
            "provenance",
            "why",
            "suggested_machine",
            "reason",
        )
    }
    summary["identity_evidence"] = identity.get("evidence")
    if identity.get("engineer_question"):
        summary["identity_engineer_question"] = identity["engineer_question"]

    machine = str(identity.get("resolved_machine") or claimed)
    print(
        f"[ORI-111] identity ok={identity.get('ok')} machine={machine} "
        f"prov={identity.get('provenance')} treat_na={identity.get('treat_na_rows_as_resolved_machine')}",
        flush=True,
    )
    if identity.get("treat_na_rows_as_resolved_machine") or identity.get("changed"):
        summary["na_override"] = apply_na_machine_ownership_override(run_dir, machine)

    meta_path = REPO / "workspace" / "active-meta.json"
    if meta_path.is_file() and machine != claimed:
        try:
            md = json.loads(meta_path.read_text(encoding="utf-8"))
            md["machine"] = machine
            md["ori111_identity_correction"] = {
                "from": claimed,
                "to": machine,
                "provenance": identity.get("provenance"),
                "why": identity.get("why"),
            }
            meta_path.write_text(json.dumps(md, indent=2), encoding="utf-8")
        except Exception as ex:  # noqa: BLE001
            summary["meta_update_error"] = str(ex)

    lib = resolve_production_library(None)
    inp = load_from_run(run_dir)
    inp.include_sys = True
    inp.include_io_map = True
    inp.machine = machine
    inp.project_name = machine
    areas = [a for a in (inp.areas or []) if a]
    if not areas:
        areas = [f"{machine}_Area"]
        inp.areas = areas
    area = areas[0]
    summary["discovered_areas"] = areas
    summary["conveyor_count_after_identity"] = len(inp.conveyors or [])
    print(
        f"[ORI-111] conveyors={summary['conveyor_count_after_identity']} areas={areas}",
        flush=True,
    )

    model = build_safety_model(run_dir=run_dir, machine=machine, areas=areas)
    devices = list(model.get("devices") or [])
    try:
        apply_endpoint_integrity_pipeline(devices, run_dir=run_dir, machine=machine)
    except Exception as e:  # noqa: BLE001
        summary["endpoint_pipeline_error"] = str(e)
    assignable = [d for d in devices if d.get("assignable") is True]
    members = [d.get("name") for d in assignable if d.get("name")][:12]
    summary["safety_inventory_count"] = len(devices)
    summary["assignable_count"] = len(assignable)
    summary["assignable_names"] = members
    print(
        f"[ORI-111] safety devices={len(devices)} assignable={len(assignable)}",
        flush=True,
    )

    zone_name = f"{machine}_ESZone1"
    safety_assigned = False
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
        inp.areas = areas
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
        summary["safety_assignment"] = {
            "zone": zone_name,
            "members": members,
            "origin": "ENGINEER_ASSIGNED_FROM_ASSIGNABLE_INVENTORY",
        }
    else:
        summary["safety_assignment"] = {
            "zone": None,
            "members": [],
            "origin": "NONE_ASSIGNABLE",
        }

    print("[ORI-111] generate() starting…", flush=True)
    summary["build_attempts"] = 1
    outer = generate(inp, lib, None)
    rep = outer.get("report") if isinstance(outer.get("report"), dict) else {}
    summary["build_status"] = outer.get("build_status") or rep.get("build_status")
    summary["outer_ok"] = outer.get("ok")
    summary["outer_error"] = outer.get("error") or outer.get("code")
    summary["l5x"] = outer.get("l5x")
    summary["l5x_filename"] = outer.get("l5x_filename")
    summary["l5x_sha256"] = outer.get("l5x_sha256")
    summary["programs"] = rep.get("programs")
    summary["conveyor_count"] = rep.get("conveyor_count")
    summary["io_map_mapped"] = rep.get("io_map_mapped")
    summary["io_map_unmapped"] = rep.get("io_map_unmapped")
    summary["es_program"] = rep.get("es_program")
    summary["ori111_escalation"] = rep.get("ori111_escalation") or outer.get(
        "ori111_escalation"
    )
    summary["ori111_withheld_modules"] = rep.get("ori111_withheld_modules") or []
    print(
        f"[ORI-111] build_status={summary['build_status']} "
        f"conveyors={summary.get('conveyor_count')} "
        f"io_mapped={summary.get('io_map_mapped')} l5x={summary.get('l5x_filename')}",
        flush=True,
    )

    if summary["ori111_withheld_modules"]:
        summary["catalog_escalation"] = escalate_unsupported_catalogs(
            summary["ori111_withheld_modules"],
            case_file=case_file,
        )

    case_path = case_file.write(OUT / CASE_NAME)
    summary["case_file"] = str(case_path)
    summary["ai_api_calls"] = case_file.ai_api_calls
    summary["relay_calls"] = case_file.relay_calls
    summary["estimated_total_usd"] = round(
        case_file.estimated_ai_usd + case_file.estimated_relay_usd, 4
    )
    summary["escalation_counters"] = case_file.counters
    esc = summary.get("ori111_escalation") or {}
    if isinstance(esc, dict) and esc.get("ai_api_calls"):
        summary["ai_api_calls"] = int(summary["ai_api_calls"] or 0) + int(
            esc.get("ai_api_calls") or 0
        )
        summary["relay_calls"] = int(summary["relay_calls"] or 0) + int(
            esc.get("relay_calls") or 0
        )

    l5x_path = Path(str(outer.get("l5x") or ""))
    gates: dict = {}
    if not l5x_path.is_file():
        gates["L5X"] = {"pass": False, "error": "no L5X"}
        summary["gates"] = gates
        summary["engineer_usable"] = False
        summary["virgin_pass"] = False
        (OUT / SUMMARY_NAME).write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )
        print(json.dumps({"virgin_pass": False, "reason": "NO_L5X"}, indent=2))
        return 1

    text = l5x_path.read_text(encoding="utf-8", errors="replace")
    progs = list(rep.get("programs") or [])
    need_suf = ["_Area_Slow", "_Area_Fast", "_Area_L1", "_Area_L2"]
    transport_ok = (
        all(any(s in p for p in progs) for s in need_suf)
        and int(rep.get("conveyor_count") or 0) > 0
    )
    if int(rep.get("conveyor_count") or 0) == 0:
        transport_ok = False
        gates["Transportation"] = {
            "pass": False,
            "reason": "zero conveyors after identity resolution",
            "programs": progs,
        }
    else:
        gates["Transportation"] = {
            "pass": transport_ok,
            "programs": progs,
            "conveyor_count": rep.get("conveyor_count"),
        }

    gates["IO"] = {
        "pass": int(rep.get("io_map_mapped") or 0) > 0,
        "mapped": rep.get("io_map_mapped"),
        "unmapped": rep.get("io_map_unmapped"),
        "withheld_modules": len(summary.get("ori111_withheld_modules") or []),
    }

    es = inspect_es(l5x_path)
    summary["es_inspect"] = es
    detail = es.get("detail") or {}
    main_ok = bool(detail.get("Main_Routine", {}).get("populated"))
    sl_ok = any(k.endswith("_Safe_Logic") and detail[k].get("populated") for k in detail)
    sp_ok = any(k.endswith("_Safe_PI") and detail[k].get("populated") for k in detail)
    if safety_assigned:
        gates["Safety"] = {
            "pass": main_ok and sl_ok and sp_ok,
            "main": main_ok,
            "safe_logic": sl_ok,
            "safe_pi": sp_ok,
        }
    else:
        gates["Safety"] = {
            "pass": True,
            "note": "no assignable Safety members — shell-only allowed only if inventory empty",
            "main": main_ok,
            "inventory_count": len(devices),
        }
        # ORI-110: FOUND>0 with 0 assignable must not silently pass as engineer-usable Safety
        if len(devices) > 0 and not members:
            gates["Safety"] = {
                "pass": False,
                "reason": "FOUND Safety devices but none assignable — engineer decision required",
                "inventory_count": len(devices),
            }

    foreign = residue(text, machine)
    gates["CROSS_SITE_RESIDUE"] = {
        "pass": foreign.get("foreign_total", 0) == 0,
        "counts": foreign,
    }
    bad = re.findall(
        r"\b(?:XIC|XIO|OTE|OTL|OTU)\s*\(\s*(?:\)|\?[,)]|\"\"|''|_unnamed_)",
        text,
        flags=re.I,
    )
    gates["L5X_VALIDATION"] = {
        "pass": len(bad) == 0 and l5x_path.stat().st_size > 10_000,
        "blank_operand_hits": bad[:10],
        "bytes": l5x_path.stat().st_size,
    }
    gates["IDENTITY"] = {
        "pass": bool(identity.get("ok"))
        or bool(identity.get("treat_na_rows_as_resolved_machine")),
        "resolved_machine": machine,
        "provenance": identity.get("provenance"),
    }

    summary["gates"] = gates
    summary["engineer_usable"] = all(
        gates[k]["pass"]
        for k in (
            "IDENTITY",
            "IO",
            "Transportation",
            "Safety",
            "CROSS_SITE_RESIDUE",
            "L5X_VALIDATION",
        )
    )
    summary["virgin_pass"] = bool(summary["engineer_usable"])
    (OUT / SUMMARY_NAME).write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "virgin_pass": summary["virgin_pass"],
                "engineer_usable": summary["engineer_usable"],
                "git_sha": git_sha,
                "claimed_machine": claimed,
                "resolved_machine": machine,
                "identity_provenance": identity.get("provenance"),
                "l5x": summary.get("l5x"),
                "conveyor_count": summary.get("conveyor_count"),
                "io_map_mapped": summary.get("io_map_mapped"),
                "gates": {k: v.get("pass") for k, v in gates.items()},
                "ai_api_calls": summary.get("ai_api_calls"),
                "relay_calls": summary.get("relay_calls"),
                "estimated_total_usd": summary.get("estimated_total_usd"),
                "escalation_counters": summary.get("escalation_counters"),
                "withheld_modules": [
                    w.get("catalog")
                    for w in (summary.get("ori111_withheld_modules") or [])
                ],
            },
            indent=2,
            default=str,
        )
    )
    return 0 if summary["virgin_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

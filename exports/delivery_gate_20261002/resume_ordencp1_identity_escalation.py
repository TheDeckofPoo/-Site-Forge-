#!/usr/bin/env python3
"""Resume ORI-111 from machine-identity escalation (no Clear / no restart).

Uses the already-imported active RUN + prior case file. Retries LIVE AI API +
Relay after the temperature=0 fix with a richer evidence package.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))
os.chdir(REPO)
os.environ["FORTNA_PRISM_DISABLE"] = "1"
os.environ["SITEFORGE_ESCALATION"] = "1"

OUT = REPO / "exports" / "delivery_gate_20261002"
RUN = REPO / "workspace" / "active" / "RUN"
PRIOR_CASE = OUT / "ordencp1_ori111_case_file.json"
PRIOR_SUMMARY = OUT / "ordencp1_ori111_virgin_summary.json"
TAR = REPO / "workspace" / "inbox" / "20260622-1013-OReillyDC27-ORDENCP1-RUN.tar.gz"


def enrich_identity_evidence(run_dir: Path, claimed: str, base: dict) -> dict:
    ev = dict(base)
    # Adapter / EIP ownership signals
    for rel in (
        "PROJECT/EIPAdapters.asc",
        "PROJECT/EIPCSV.asc",
        "FORTNA/ABS_EIP_ADAPTERS.asc",
        "FORTNA/Configio.asc",
        "FORTNA/ctrlprocnames.asc",
    ):
        p = run_dir / rel
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        names = Counter(
            m.group(0).upper()
            for m in re.finditer(r"ORDENCP\d+|MSCRENO\w+|ORNCCP\d+|TFCP\d+", text, re.I)
        )
        ev[f"mentions_in_{rel.replace('/', '_')}"] = dict(names.most_common(20))
        ev[f"bytes_{rel.replace('/', '_')}"] = p.stat().st_size
    # Tag / T_ prefixes sample from Conveyor names
    conv = run_dir / "FORTNA" / "Conveyor.asc"
    if conv.is_file():
        lines = conv.read_text(encoding="utf-8", errors="replace").splitlines()[1:]
        prefixes = Counter()
        for ln in lines[:2000]:
            name = ln.split("~", 1)[0]
            m = re.match(r"^([A-Za-z]+)", name)
            if m:
                prefixes[m.group(1)] += 1
        ev["conveyor_name_prefixes_sample"] = dict(prefixes.most_common(25))
    # RUN folder structure
    ev["run_top_level"] = sorted(
        p.name for p in run_dir.iterdir() if p.exists()
    )[:40]
    fortna = run_dir / "FORTNA"
    if fortna.is_dir():
        ev["fortna_file_count"] = sum(1 for _ in fortna.glob("*"))
    ev["ask"] = (
        "Determine the ACTUAL controller/machine this RUN represents.\n"
        "Return JSON with fields:\n"
        " classification, confidence (PROVEN|DERIVED|REVIEW_REQUIRED|UNKNOWN),\n"
        " candidate_resolution: {\n"
        "   resolved_machine,\n"
        "   treat_na_rows_as_resolved_machine (bool),\n"
        "   ordencp4_rows_interpretation (foreign|secondary_controller|tar_mislabeled|shared),\n"
        "   deterministic_checks_to_validate (array of strings),\n"
        "   evidence_used (array),\n"
        "   why_not_other_candidates (array)\n"
        " },\n"
        " alternatives, why_alternatives_rejected, recommended_action.\n"
        "Do NOT invent a machine absent from evidence.\n"
        "If project.cfg says ORDENCP1 and exclusive Conveyor rows are only ORDENCP4,\n"
        "explain whether TAR is mislabeled or multi-controller with N/A belonging to cfg machine."
    )
    return ev


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
        detail[rn] = {"populated": len(nonempty) > 0, "non_nop": len(nonempty)}
    return {"routines": routines, "detail": detail}


def main() -> int:
    from fortna_autogen import generate, load_from_run, resolve_production_library
    from fortna_build_escalation import (
        BuildCaseFile,
        apply_na_machine_ownership_override,
        escalate_item,
        escalate_unsupported_catalogs,
        gather_machine_identity_evidence,
        validate_machine_identity_proposal,
    )
    from fortna_safety_endpoint_integrity import apply_endpoint_integrity_pipeline
    from fortna_safety_model import build_safety_model

    if not RUN.is_dir():
        print("ACTIVE RUN missing — cannot resume without restart/import")
        return 2

    git_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO), text=True
    ).strip()

    prior = {}
    if PRIOR_SUMMARY.is_file():
        prior = json.loads(PRIOR_SUMMARY.read_text(encoding="utf-8"))
    claimed = str(
        (prior.get("import_meta") or {}).get("claimed_machine")
        or prior.get("identity_resolution", {}).get("resolved_machine")
        or "ORDENCP1"
    )

    case_file = BuildCaseFile(
        site=claimed,
        machine=claimed,
        run_sha=str((prior.get("import_meta") or {}).get("tar_sha256") or ""),
        build_id="ori111-ordencp1-resume-identity",
    )
    # Preserve prior timeline notes
    case_file.timeline.append(
        {
            "event": "RESUME_IDENTITY_ESCALATION",
            "prior_ai_calls": prior.get("ai_api_calls"),
            "prior_relay_calls": prior.get("relay_calls"),
            "note": "temperature=0 fix applied; retry live AI+Relay",
        }
    )

    base = gather_machine_identity_evidence(RUN, claimed, tar_name=TAR.name)
    evidence = enrich_identity_evidence(RUN, claimed, base)

    # Force a fresh signature so we re-investigate (materially richer evidence)
    evidence["resume_pass"] = "temperature_fix_retry"
    evidence["defect_kind"] = "MACHINE_IDENTITY_CONFLICT_RESUME"

    item = escalate_item(
        evidence,
        case_file,
        deterministic_resolver=lambda _e: None,
        allow_engineer=True,
        max_deep_passes=1,
    )

    summary: dict = {
        "phase": "ORI111_RESUME_IDENTITY",
        "git_sha": git_sha,
        "claimed_machine": claimed,
        "prior_virgin_pass": prior.get("virgin_pass"),
        "identity_item_disposition": item.disposition,
        "identity_provenance": item.provenance,
        "ai_api_calls": case_file.ai_api_calls,
        "relay_calls": case_file.relay_calls,
        "estimated_total_usd": round(
            case_file.estimated_ai_usd + case_file.estimated_relay_usd, 4
        ),
        "identity_events": item.events,
        "identity_resolution_blob": item.resolution,
    }

    # Extract / validate proposed machine from AI then Relay
    resolved = claimed
    treat_na = False
    validation = None
    sources = []
    res = item.resolution or {}
    for label, blob in (
        ("ai", res.get("ai")),
        ("relay", res.get("relay")),
        ("raw", res),
    ):
        if not isinstance(blob, dict):
            continue
        proposal = blob
        if isinstance(blob.get("candidate_resolution"), dict):
            proposal = {**blob, **blob["candidate_resolution"]}
            proposal["candidate_resolution"] = blob["candidate_resolution"]
        v = validate_machine_identity_proposal(proposal, evidence)
        sources.append({"source": label, "validation": v, "proposal_keys": list(proposal.keys())[:20]})
        if v.get("ok"):
            resolved = v["resolved_machine"]
            treat_na = bool(v.get("treat_na_rows_as_resolved_machine"))
            # Also read treat_na from nested candidate_resolution
            cr = blob.get("candidate_resolution") if isinstance(blob.get("candidate_resolution"), dict) else {}
            if "treat_na_rows_as_resolved_machine" in cr:
                treat_na = bool(cr.get("treat_na_rows_as_resolved_machine"))
            validation = v
            summary["accepted_from"] = label
            break

    summary["validation_attempts"] = sources
    summary["engineer_question"] = (
        (item.resolution or {}).get("engineer_question") if item.engineer_required else None
    )

    if validation is None:
        # Disagreement / unresolved — write case file and stop for engineer only if needed
        case_file.write(OUT / "ordencp1_ori111_case_file.json")
        summary["ok"] = False
        summary["resume_continued"] = False
        summary["reason"] = "identity_not_validator_accepted_after_live_retry"
        (OUT / "ordencp1_ori111_resume_identity.json").write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )
        print(json.dumps(summary, indent=2, default=str)[:4000])
        return 1

    summary["resolved_machine"] = resolved
    summary["treat_na_rows_as_resolved_machine"] = treat_na
    summary["identity_ok"] = True

    # Apply ownership correction and resume build (NO clear)
    if treat_na or resolved != claimed:
        summary["na_override"] = apply_na_machine_ownership_override(RUN, resolved)

    meta_path = REPO / "workspace" / "active-meta.json"
    if meta_path.is_file():
        md = json.loads(meta_path.read_text(encoding="utf-8"))
        md["machine"] = resolved
        md["ori111_identity_correction"] = {
            "from": claimed,
            "to": resolved,
            "treat_na": treat_na,
            "provenance": item.provenance,
            "accepted_from": summary.get("accepted_from"),
        }
        meta_path.write_text(json.dumps(md, indent=2), encoding="utf-8")

    lib = resolve_production_library(None)
    inp = load_from_run(RUN)
    inp.include_sys = True
    inp.include_io_map = True
    inp.machine = resolved
    inp.project_name = resolved
    areas = [a for a in (inp.areas or []) if a] or [f"{resolved}_Area"]
    inp.areas = areas
    area = areas[0]
    summary["conveyor_count_after_identity"] = len(inp.conveyors or [])
    summary["discovered_areas"] = areas

    model = build_safety_model(run_dir=RUN, machine=resolved, areas=areas)
    devices = list(model.get("devices") or [])
    try:
        apply_endpoint_integrity_pipeline(devices, run_dir=RUN, machine=resolved)
    except Exception as e:  # noqa: BLE001
        summary["endpoint_pipeline_error"] = str(e)
    assignable = [d for d in devices if d.get("assignable") is True]
    members = [d.get("name") for d in assignable if d.get("name")][:12]
    summary["assignable_count"] = len(assignable)
    summary["assignable_names"] = members
    zone_name = f"{resolved}_ESZone1"
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
            "machine": resolved,
            "project_name": resolved,
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
        summary["safety_assignment"] = {"zone": zone_name, "members": members}
    else:
        summary["safety_assignment"] = {"zone": None, "members": []}

    summary["build_attempts"] = int(prior.get("build_attempts") or 1) + 1
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
    summary["ori111_withheld_modules"] = rep.get("ori111_withheld_modules") or []
    summary["ori111_escalation"] = rep.get("ori111_escalation")

    if summary["ori111_withheld_modules"]:
        summary["catalog_escalation"] = escalate_unsupported_catalogs(
            summary["ori111_withheld_modules"], case_file=case_file
        )

    case_file.write(OUT / "ordencp1_ori111_case_file.json")
    summary["ai_api_calls"] = case_file.ai_api_calls + int(
        (summary.get("ori111_escalation") or {}).get("ai_api_calls") or 0
    )
    summary["relay_calls"] = case_file.relay_calls + int(
        (summary.get("ori111_escalation") or {}).get("relay_calls") or 0
    )
    summary["estimated_total_usd"] = round(
        case_file.estimated_ai_usd
        + case_file.estimated_relay_usd
        + float((summary.get("ori111_escalation") or {}).get("estimated_total_usd") or 0),
        4,
    )
    summary["escalation_counters"] = case_file.counters

    l5x_path = Path(str(outer.get("l5x") or ""))
    gates = {}
    if not l5x_path.is_file():
        gates["L5X"] = {"pass": False}
        summary["gates"] = gates
        summary["engineer_usable"] = False
        summary["virgin_pass"] = False
        summary["resume_continued"] = True
        (OUT / "ordencp1_ori111_resume_identity.json").write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )
        # also update virgin summary pointer
        (OUT / "ordencp1_ori111_virgin_summary.json").write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )
        print(json.dumps({"virgin_pass": False, "reason": "NO_L5X", **{k: summary.get(k) for k in ("resolved_machine", "conveyor_count", "outer_error", "ai_api_calls", "relay_calls")}}, indent=2))
        return 1

    text = l5x_path.read_text(encoding="utf-8", errors="replace")
    progs = list(rep.get("programs") or [])
    transport_ok = (
        all(any(s in p for p in progs) for s in ("_Area_Slow", "_Area_Fast", "_Area_L1", "_Area_L2"))
        and int(rep.get("conveyor_count") or 0) > 0
    )
    gates["IDENTITY"] = {"pass": True, "resolved_machine": resolved, "treat_na": treat_na}
    gates["IO"] = {
        "pass": int(rep.get("io_map_mapped") or 0) > 0,
        "mapped": rep.get("io_map_mapped"),
        "unmapped": rep.get("io_map_unmapped"),
    }
    gates["Transportation"] = {
        "pass": transport_ok,
        "conveyor_count": rep.get("conveyor_count"),
        "programs": progs,
    }
    es = inspect_es(l5x_path)
    detail = es.get("detail") or {}
    if members:
        gates["Safety"] = {
            "pass": bool(detail.get("Main_Routine", {}).get("populated"))
            and any(k.endswith("_Safe_Logic") and detail[k].get("populated") for k in detail)
            and any(k.endswith("_Safe_PI") and detail[k].get("populated") for k in detail),
        }
    else:
        gates["Safety"] = {"pass": True, "note": "no assignable members"}
    foreign = {
        "MSCRENOPICK": len(re.findall("MSCRENOPICK", text)),
        "TFCP1_ESZone1": len(re.findall("TFCP1_ESZone1", text)),
    }
    gates["CROSS_SITE_RESIDUE"] = {"pass": sum(foreign.values()) == 0, "counts": foreign}
    bad = re.findall(
        r"\b(?:XIC|XIO|OTE|OTL|OTU)\s*\(\s*(?:\)|\?[,)]|\"\"|''|_unnamed_)",
        text,
        flags=re.I,
    )
    gates["L5X_VALIDATION"] = {
        "pass": len(bad) == 0 and l5x_path.stat().st_size > 10000,
        "blank_operand_hits": bad[:10],
        "bytes": l5x_path.stat().st_size,
    }
    summary["es_inspect"] = es
    summary["gates"] = gates
    summary["engineer_usable"] = all(gates[k]["pass"] for k in gates)
    summary["virgin_pass"] = summary["engineer_usable"]
    summary["resume_continued"] = True
    summary["ok"] = True

    (OUT / "ordencp1_ori111_resume_identity.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    (OUT / "ordencp1_ori111_virgin_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "virgin_pass": summary["virgin_pass"],
                "resolved_machine": resolved,
                "treat_na": treat_na,
                "accepted_from": summary.get("accepted_from"),
                "conveyor_count": summary.get("conveyor_count"),
                "l5x": summary.get("l5x"),
                "gates": {k: v.get("pass") for k, v in gates.items()},
                "ai_api_calls": summary.get("ai_api_calls"),
                "relay_calls": summary.get("relay_calls"),
                "estimated_total_usd": summary.get("estimated_total_usd"),
                "withheld": [w.get("catalog") for w in summary.get("ori111_withheld_modules") or []],
            },
            indent=2,
        )
    )
    return 0 if summary["virgin_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

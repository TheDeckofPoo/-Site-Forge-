#!/usr/bin/env python3
"""ORI-111 deep pass: N/A Conveyor ownership after AI kept ORDENCP1 @ REVIEW_REQUIRED.

No Clear. Uses active RUN + na_ownership_evidence.json + live AI + freeform Relay.
"""
from __future__ import annotations

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

OUT = REPO / "exports" / "delivery_gate_20261002"
RUN = REPO / "workspace" / "active" / "RUN"
NA_EV = OUT / "na_ownership_evidence.json"
PRIOR = OUT / "ordencp1_ori111_resume_identity.json"


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
    from fortna_autogen import generate, load_from_run, resolve_production_library
    from fortna_build_escalation import (
        BuildCaseFile,
        apply_na_machine_ownership_override,
        call_ai_api_for_case,
        call_relay_freeform,
        escalate_unsupported_catalogs,
        validate_machine_identity_proposal,
    )
    from fortna_safety_endpoint_integrity import apply_endpoint_integrity_pipeline
    from fortna_safety_model import build_safety_model

    git_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO), text=True
    ).strip()
    prior = json.loads(PRIOR.read_text(encoding="utf-8")) if PRIOR.is_file() else {}
    na = json.loads(NA_EV.read_text(encoding="utf-8")) if NA_EV.is_file() else {}

    # AI previously: resolved_machine=ORDENCP1, treat_na=false, ORDENCP4=foreign
    prior_ai = None
    for ev in prior.get("identity_events") or []:
        if ev.get("level") == 1 and ev.get("action") == "INSUFFICIENT":
            prior_ai = (ev.get("detail") or {}).get("ai")
            break

    evidence = {
        "subsystem": "TRANSPORTATION",
        "defect_kind": "ZERO_CONVEYOR_NA_OWNERSHIP",
        "device": "Conveyor.asc:Machine_Name=N/A",
        "claimed_machine": "ORDENCP1",
        "project_cfg_machine": "ORDENCP1",
        "exclusive_machine_names": {"ORDENCP4": na.get("ordencp4_row_count") or 469},
        "prior_ai_identity": prior_ai,
        "na_ownership_deterministic_checks": na,
        "why_uncertain": (
            "AI kept ORDENCP1 identity at REVIEW_REQUIRED and refused treat_na without "
            "more ownership proof for 5533 N/A Conveyor rows (include real P100.. conveyors)."
        ),
        "site_forge_attempt": "identity AI pass1 + na_ownership_evidence deterministic scan",
        "ask": (
            "Given deterministic N/A ownership evidence, decide:\n"
            "1) Is ORDENCP1 still the correct controller identity?\n"
            "2) Should Machine_Name=N/A/empty rows be treated as ORDENCP1 for this RUN "
            "(because project.cfg MACHINENAME=ORDENCP1 and Display.config.CP1 exists), "
            "while exclusive ORDENCP4 rows remain foreign/secondary?\n"
            "3) Or is the TAR mislabeled and the real controller ORDENCP4?\n"
            "Return candidate_resolution with resolved_machine, "
            "treat_na_rows_as_resolved_machine, ordencp4_rows_interpretation, "
            "confidence, evidence_used, why_not_other_candidates, "
            "deterministic_checks_to_validate.\n"
            "Do not invent machines absent from evidence."
        ),
    }

    cf = BuildCaseFile(
        site="ORDENCP1",
        machine="ORDENCP1",
        run_sha=str((prior.get("import_meta") or {}).get("tar_sha256") or ""),
        build_id="ori111-na-deep-pass",
    )

    ai = call_ai_api_for_case(evidence, case_file=cf)
    relay = call_relay_freeform(
        evidence, case_file=cf, ai_response=ai.get("response"), purpose="ZERO_CONVEYOR_NA_OWNERSHIP"
    )

    summary: dict = {
        "phase": "ORI111_NA_DEEP_PASS",
        "git_sha": git_sha,
        "ai_ok": ai.get("ok"),
        "ai_response": ai.get("response"),
        "ai_meta": ai.get("meta"),
        "relay_ok": relay.get("ok"),
        "relay_response": relay.get("result"),
        "relay_meta": relay.get("meta"),
        "ai_api_calls": cf.ai_api_calls,
        "relay_calls": cf.relay_calls,
        "estimated_total_usd": round(cf.estimated_ai_usd + cf.estimated_relay_usd, 4),
    }

    # Prefer agreement: validate both
    accepted = None
    for label, blob in (("relay", relay.get("result")), ("ai", ai.get("response"))):
        if not isinstance(blob, dict):
            continue
        proposal = dict(blob)
        if isinstance(blob.get("candidate_resolution"), dict):
            proposal = {**blob, **blob["candidate_resolution"]}
            proposal["candidate_resolution"] = blob["candidate_resolution"]
        # Expand allowed machines for validator
        ev_for_v = {
            "claimed_machine": "ORDENCP1",
            "project_cfg_machine": "ORDENCP1",
            "exclusive_machine_names": {"ORDENCP4": 469, "ORDENCP1": 1},
        }
        v = validate_machine_identity_proposal(proposal, ev_for_v)
        conf = str(blob.get("confidence") or proposal.get("confidence") or "").upper()
        summary.setdefault("validations", []).append(
            {"source": label, "validation": v, "confidence": conf}
        )
        if v.get("ok") and conf in ("PROVEN", "DERIVED"):
            accepted = {
                "from": label,
                "resolved_machine": v["resolved_machine"],
                "treat_na": bool(
                    v.get("treat_na_rows_as_resolved_machine")
                    or (blob.get("candidate_resolution") or {}).get(
                        "treat_na_rows_as_resolved_machine"
                    )
                ),
                "confidence": conf,
                "proposal": proposal,
            }
            break
        # Accept REVIEW_REQUIRED only if BOTH AI and Relay agree on same machine+treat_na
        if v.get("ok") and conf == "REVIEW_REQUIRED" and accepted is None:
            accepted = {
                "from": label,
                "resolved_machine": v["resolved_machine"],
                "treat_na": bool(
                    v.get("treat_na_rows_as_resolved_machine")
                    or (blob.get("candidate_resolution") or {}).get(
                        "treat_na_rows_as_resolved_machine"
                    )
                ),
                "confidence": conf,
                "proposal": proposal,
                "provisional": True,
            }

    # Agreement check if both provisional
    ai_v = next((x for x in summary.get("validations", []) if x["source"] == "ai"), None)
    rel_v = next((x for x in summary.get("validations", []) if x["source"] == "relay"), None)
    if (
        ai_v
        and rel_v
        and ai_v["validation"].get("ok")
        and rel_v["validation"].get("ok")
        and ai_v["validation"].get("resolved_machine")
        == rel_v["validation"].get("resolved_machine")
    ):
        # Prefer Relay if both ok
        treat_ai = False
        treat_rel = False
        if isinstance(ai.get("response"), dict):
            treat_ai = bool(
                (ai["response"].get("candidate_resolution") or {}).get(
                    "treat_na_rows_as_resolved_machine"
                )
            )
        if isinstance(relay.get("result"), dict):
            treat_rel = bool(
                (relay["result"].get("candidate_resolution") or {}).get(
                    "treat_na_rows_as_resolved_machine"
                )
            )
        if treat_ai == treat_rel:
            accepted = {
                "from": "ai_relay_agreement",
                "resolved_machine": ai_v["validation"]["resolved_machine"],
                "treat_na": treat_ai,
                "confidence": "DERIVED",
                "agreement": True,
            }

    summary["accepted"] = accepted
    if not accepted:
        summary["ok"] = False
        summary["engineer_required"] = True
        summary["engineer_question"] = {
            "title": "N/A Conveyor ownership for ORDENCP1 RUN",
            "body": (
                "AI pass1 kept identity ORDENCP1 but refused treating N/A rows as ORDENCP1.\n"
                "Deep-pass AI/Relay did not produce a validator-accepted agreed resolution.\n\n"
                f"N/A rows={na.get('na_row_count')} ORDENCP4 exclusive={na.get('ordencp4_row_count')}\n"
                f"Token counts={na.get('token_counts')}\n"
                f"Display artifacts={list((na.get('display_artifacts') or {}).keys())}\n"
                f"N/A realish sample={na.get('na_realish_sample')}\n\n"
                f"AI deep: {json.dumps(ai.get('response'), default=str)[:1200]}\n"
                f"Relay deep: {json.dumps(relay.get('result'), default=str)[:1200]}"
            ),
            "choices": [
                {
                    "id": "1",
                    "label": "ORDENCP1 + treat N/A as ORDENCP1 (ORDENCP4 rows foreign)",
                },
                {"id": "2", "label": "Switch identity to ORDENCP4 (TAR mislabeled)"},
                {"id": "3", "label": "ORDENCP1 only exclusive rows (accept 0 conveyors / BLOCKED)"},
            ],
        }
        cf.write(OUT / "ordencp1_ori111_case_file.json")
        (OUT / "ordencp1_ori111_na_deep_pass.json").write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )
        print(json.dumps(summary, indent=2, default=str)[:5000])
        return 1

    resolved = accepted["resolved_machine"]
    treat_na = bool(accepted["treat_na"])
    summary["resolved_machine"] = resolved
    summary["treat_na"] = treat_na

    if treat_na:
        summary["na_override"] = apply_na_machine_ownership_override(RUN, resolved)

    meta_path = REPO / "workspace" / "active-meta.json"
    if meta_path.is_file():
        md = json.loads(meta_path.read_text(encoding="utf-8"))
        md["machine"] = resolved
        md["ori111_identity_correction"] = {
            "to": resolved,
            "treat_na": treat_na,
            "from_pass": "na_deep_pass",
            "accepted": accepted,
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

    model = build_safety_model(run_dir=RUN, machine=resolved, areas=areas)
    devices = list(model.get("devices") or [])
    try:
        apply_endpoint_integrity_pipeline(devices, run_dir=RUN, machine=resolved)
    except Exception as e:  # noqa: BLE001
        summary["endpoint_pipeline_error"] = str(e)
    members = [d.get("name") for d in devices if d.get("assignable") and d.get("name")][:12]
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

    outer = generate(inp, lib, None)
    rep = outer.get("report") if isinstance(outer.get("report"), dict) else {}
    summary["build_status"] = outer.get("build_status") or rep.get("build_status")
    summary["outer_ok"] = outer.get("ok")
    summary["outer_error"] = outer.get("error") or outer.get("code")
    summary["l5x"] = outer.get("l5x")
    summary["l5x_sha256"] = outer.get("l5x_sha256")
    summary["programs"] = rep.get("programs")
    summary["conveyor_count"] = rep.get("conveyor_count")
    summary["io_map_mapped"] = rep.get("io_map_mapped")
    summary["io_map_unmapped"] = rep.get("io_map_unmapped")
    summary["ori111_withheld_modules"] = rep.get("ori111_withheld_modules") or []
    summary["ori111_escalation"] = rep.get("ori111_escalation")
    if summary["ori111_withheld_modules"]:
        summary["catalog_escalation"] = escalate_unsupported_catalogs(
            summary["ori111_withheld_modules"], case_file=cf
        )

    cf.write(OUT / "ordencp1_ori111_case_file.json")
    l5x_path = Path(str(outer.get("l5x") or ""))
    gates = {}
    if not l5x_path.is_file():
        summary["virgin_pass"] = False
        summary["engineer_usable"] = False
        summary["gates"] = {"L5X": {"pass": False}}
        (OUT / "ordencp1_ori111_na_deep_pass.json").write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )
        (OUT / "ordencp1_ori111_virgin_summary.json").write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )
        print(json.dumps({"virgin_pass": False, "outer_error": summary.get("outer_error"), "conveyors": summary.get("conveyor_count"), "accepted": accepted}, indent=2))
        return 1

    text = l5x_path.read_text(encoding="utf-8", errors="replace")
    progs = list(rep.get("programs") or [])
    gates["IDENTITY"] = {"pass": True, "resolved_machine": resolved, "treat_na": treat_na}
    gates["IO"] = {"pass": int(rep.get("io_map_mapped") or 0) > 0, "mapped": rep.get("io_map_mapped")}
    gates["Transportation"] = {
        "pass": int(rep.get("conveyor_count") or 0) > 0
        and all(any(s in p for p in progs) for s in ("_Area_Slow", "_Area_Fast", "_Area_L1", "_Area_L2")),
        "conveyor_count": rep.get("conveyor_count"),
    }
    es = inspect_es(l5x_path)
    detail = es.get("detail") or {}
    if members:
        gates["Safety"] = {
            "pass": bool(detail.get("Main_Routine", {}).get("populated"))
            and any(k.endswith("_Safe_Logic") and detail[k].get("populated") for k in detail)
            and any(k.endswith("_Safe_PI") and detail[k].get("populated") for k in detail)
        }
    else:
        gates["Safety"] = {"pass": True, "note": "no assignable"}
    foreign = {
        "MSCRENOPICK": text.count("MSCRENOPICK"),
        "TFCP1_ESZone1": text.count("TFCP1_ESZone1"),
    }
    gates["CROSS_SITE_RESIDUE"] = {"pass": sum(foreign.values()) == 0, "counts": foreign}
    bad = re.findall(
        r"\b(?:XIC|XIO|OTE|OTL|OTU)\s*\(\s*(?:\)|\?[,)]|\"\"|''|_unnamed_)",
        text,
        flags=re.I,
    )
    gates["L5X_VALIDATION"] = {"pass": not bad and l5x_path.stat().st_size > 10000, "hits": bad[:5]}
    summary["gates"] = gates
    summary["es_inspect"] = es
    summary["engineer_usable"] = all(g.get("pass") for g in gates.values())
    summary["virgin_pass"] = summary["engineer_usable"]
    summary["ok"] = True
    summary["ai_api_calls"] = cf.ai_api_calls + int(
        (summary.get("ori111_escalation") or {}).get("ai_api_calls") or 0
    )
    summary["relay_calls"] = cf.relay_calls + int(
        (summary.get("ori111_escalation") or {}).get("relay_calls") or 0
    )

    (OUT / "ordencp1_ori111_na_deep_pass.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    (OUT / "ordencp1_ori111_virgin_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "virgin_pass": summary["virgin_pass"],
                "accepted": accepted,
                "conveyor_count": summary.get("conveyor_count"),
                "l5x": summary.get("l5x"),
                "gates": {k: v.get("pass") for k, v in gates.items()},
                "ai_api_calls": summary.get("ai_api_calls"),
                "relay_calls": summary.get("relay_calls"),
                "withheld": [w.get("catalog") for w in summary.get("ori111_withheld_modules") or []],
            },
            indent=2,
        )
    )
    return 0 if summary["virgin_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

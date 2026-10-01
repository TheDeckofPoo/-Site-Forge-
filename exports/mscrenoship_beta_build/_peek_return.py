#!/usr/bin/env python3
"""Peek MSCRENOSHIP beta build artifacts for mission RETURN."""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))

# Prefer diagnostics autogen_report
diag = summary.get("diagnostics_dir") or summary.get("out_dir")
rep = {}
if diag and (Path(diag) / "autogen_report.json").is_file():
    rep = json.loads((Path(diag) / "autogen_report.json").read_text(encoding="utf-8"))

bi_json = summary.get("build_issues_json") or rep.get("build_issues_json")
bi = {}
if bi_json and Path(bi_json).is_file():
    bi = json.loads(Path(bi_json).read_text(encoding="utf-8"))
elif (Path(diag) / "MSCRENOSHIP_BUILD_ISSUES.json").is_file() if diag else False:
    bi = json.loads(
        (Path(diag) / "MSCRENOSHIP_BUILD_ISSUES.json").read_text(encoding="utf-8")
    )

l5x = summary.get("l5x") or rep.get("l5x_path") or ""
l5x_p = Path(l5x) if l5x else None
text = l5x_p.read_text(encoding="utf-8", errors="replace") if l5x_p and l5x_p.is_file() else ""

# Programs / routines inventory
progs = {}
for pm in re.finditer(r"<Program\b([^>]*)>(.*?)</Program>", text, re.S):
    m = re.search(r'(?<![A-Za-z0-9_])Name="([^"]+)"', pm.group(1) or "")
    if not m:
        continue
    pname = m.group(1)
    routines = []
    for rm in re.finditer(r"<Routine\b([^>]*)>", pm.group(2) or ""):
        rn = re.search(r'(?<![A-Za-z0-9_])Name="([^"]+)"', rm.group(1) or "")
        if rn:
            routines.append(rn.group(1))
    progs[pname] = routines

rc = rep.get("routine_coverage") or {}
rc_rows = rc.get("rows") or []

def rows_by_status(st: str):
    return [
        f"{r.get('PROGRAM')}/{r.get('ROUTINE')}"
        for r in rc_rows
        if str(r.get("STATUS")) == st
    ]

# Collisions
coll = rep.get("io_map_dup_physical_review") or []
# Identifier map
idm = rep.get("logix_identifier_map") or {}

# Top 20 engineer actions from BUILD_ISSUES
actions = []
sections = bi.get("sections") if isinstance(bi.get("sections"), dict) else {}
for sec_name, items in (sections or {}).items():
    for it in items or []:
        if not isinstance(it, dict):
            continue
        actions.append(
            {
                "section": sec_name,
                "issue_id": it.get("issue_id"),
                "object": it.get("object/device"),
                "program": it.get("program"),
                "routine": it.get("routine"),
                "action": it.get("engineer action") or it.get("ENGINEER ACTION"),
                "site_forge": it.get("what Site Forge did"),
                "severity": it.get("severity/classification"),
            }
        )

# Sorter / sawtooth presence in L5X
sorter_hits = [p for p in progs if "sorter" in p.lower()]
saw_hits = [p for p in progs if "saw" in p.lower()]

out = {
    "summary_build_status": summary.get("build_status") or rep.get("build_status"),
    "structural": bi.get("STRUCTURAL VALIDATION")
    or ("PASS" if (rep.get("symbol_closure") or {}).get("ok") else "FAIL"),
    "commissioning": summary.get("commissioning_ready")
    or (rep.get("runnability") or {}).get("COMMISSIONING_READY"),
    "l5x_filename": summary.get("l5x_filename"),
    "l5x_path": summary.get("l5x"),
    "l5x_sha256": summary.get("l5x_sha256") or rep.get("l5x_sha256"),
    "promoted": summary.get("l5x_promoted_to_current") or rep.get("l5x_promoted_to_current"),
    "build_id": summary.get("build_id") or rep.get("build_id"),
    "build_issues_txt": summary.get("build_issues_txt") or rep.get("build_issues_txt") or bi_json,
    "build_issues_json": bi_json or summary.get("build_issues_json"),
    "actionable": bi.get("actionable_issue_count") or summary.get("actionable_issue_count"),
    "blockers": len(bi.get("BLOCKERS") or []),
    "symbol_closure": summary.get("symbol_closure") or {
        "ok": (rep.get("symbol_closure") or {}).get("ok")
    },
    "quarantine": summary.get("rung_quarantine") or rep.get("rung_quarantine"),
    "stage0": summary.get("stage0") or {
        k: (rep.get("stage0") or {}).get(k)
        for k in ("CLAIMS_CREATED", "CLAIMS_RESOLVED", "CLAIMS_UNRESOLVED")
    },
    "physical_io_unmapped_names": rep.get("physical_io_unmapped_names")
    or summary.get("physical_io_unmapped_names"),
    "writer_coverage": summary.get("writer_coverage") or {
        k: (rep.get("writer_coverage") or {}).get(k)
        for k in (
            "mapped_outputs",
            "outputs_with_valid_writers",
            "intentional_review_outputs",
            "writerless_defect_outputs",
        )
    },
    "conveyor_count": summary.get("conveyor_count") or rep.get("conveyor_count"),
    "programs": list(progs.keys()),
    "program_routines": progs,
    "merges_emitted": summary.get("merges_emitted") or rep.get("merges_emitted"),
    "merges_withheld": summary.get("merges_withheld_review")
    or rep.get("merges_withheld_review"),
    "es_program": summary.get("es_program") or {
        k: (rep.get("es_program") or {}).get(k) for k in ("status", "zones")
    },
    "sawtooth_inclusion": rep.get("sawtooth_inclusion") or summary.get("sawtooth_inclusion"),
    "sawtooth_build": summary.get("sawtooth_build"),
    "function_disclosure": {
        k: v
        for k, v in (rep.get("function_disclosure") or {}).items()
        if k != "policy"
    }
    if isinstance(rep.get("function_disclosure"), dict)
    else {},
    "sorter_programs": sorter_hits,
    "sawtooth_programs": saw_hits,
    "routine_coverage_summary": rc.get("summary") or bi.get("routine_coverage_summary"),
    "PLACEHOLDER": rows_by_status("PLACEHOLDER"),
    "PRESENT_PARTIAL": rows_by_status("PRESENT_PARTIAL"),
    "MISSING_EXPECTED": rows_by_status("MISSING_EXPECTED"),
    "EMPTY": rows_by_status("EMPTY"),
    "WITHHELD_REVIEW": rows_by_status("WITHHELD_REVIEW"),
    "UNSUPPORTED": rows_by_status("UNSUPPORTED"),
    "COMPLETE_count": (rc.get("summary") or {}).get("COMPLETE"),
    "collisions": [
        {
            "physical": c.get("physical_address"),
            "direction": c.get("direction"),
            "claimants": c.get("claimants"),
            "classification": c.get("classification"),
            "action": c.get("site_forge_action"),
            "effect": c.get("effect"),
            "engineer_action": c.get("engineer_action"),
        }
        for c in coll
    ],
    "collision_stats": {
        "total": len(coll),
        "output_withheld": rep.get("io_map_collision_output_withheld"),
        "input_withheld": rep.get("io_map_collision_input_withheld"),
        "safety_fail_closed": rep.get("io_map_collision_safety_fail_closed"),
        "whole_controller_blockers": rep.get(
            "io_map_collision_whole_controller_blockers"
        ),
    },
    "identifier_map": idm,
    "top20_actions": actions[:20],
    "total_actions": len(actions),
    "exports_current": [
        p.name
        for p in sorted((REPO / "exports" / "current").glob("MSCRENOSHIP*.L5X"))
    ],
    "foreign_generated": rep.get("foreign_generated"),
    "default_safety_refs": rep.get("default_unassigned_operational_safety_refs"),
}

(OUT / "return_peek.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(json.dumps(out, indent=2, default=str)[:12000])
print("\n... wrote", OUT / "return_peek.json")

#!/usr/bin/env python3
"""Audit CP8 R1 candidate support for decoder contamination.

Does not rewrite the original transcript. Adds evidence_purity_audit.json.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_evidence_purity import (  # noqa: E402
    CURRENT_DECODER_OUTPUT,
    classify_tool_evidence,
)

R1 = ROOT / "exports/learning/investigations/CP8_ALPHA_DIALECT/R1"
CAND = R1 / "final_decoder_rule_candidate.json"


def _tool_from_ref(ref: str) -> str:
    m = re.match(r"^([a-z_]+)\s*\(", ref.strip())
    if m:
        return m.group(1)
    # prose mentions
    for t in (
        "get_physical_word_resolution_trace",
        "get_configio_binding_trace",
        "get_adapter_modules",
        "get_eip_bank_map",
        "get_neighbor_claims",
        "compare_candidate_rule_against_site",
        "get_hardware_family",
        "get_project_identity",
        "get_configio_binding_cluster_summary",
    ):
        if t in ref:
            return t
    return ""


def main() -> int:
    cand = json.loads(CAND.read_text(encoding="utf-8"))
    items = []
    circular = []
    independent = []

    # observed_facts + evidence_refs + supporting_examples
    for section in ("observed_facts", "evidence_refs", "supporting_examples"):
        for claim in cand.get(section) or []:
            tool = _tool_from_ref(claim)
            meta = classify_tool_evidence(tool) if tool else {
                "tool": "",
                "evidence_class": "UNKNOWN",
                "independent_of_candidate_logic": False,
                "usable_for_rule_proof": False,
                "reason": "no tool identified — treat cautiously",
            }
            # Explicit contamination markers
            if (
                "shared_16ch_word" in claim
                or "get_physical_word_resolution_trace" in claim
                or "resolves through the paired Low" in claim
                or "High claim evidence is marked as High and shared_16ch_word" in claim
                or "High claims resolve as a High continuation" in claim
            ):
                meta = {
                    **meta,
                    "evidence_class": CURRENT_DECODER_OUTPUT,
                    "independent_of_candidate_logic": False,
                    "usable_for_rule_proof": False,
                    "reason": (
                        "Cites PhysicalWordResolver / shared_16ch_word behavior — "
                        "circular for proving High-half continuation"
                    ),
                }
            row = {
                "section": section,
                "claim": claim,
                "supporting_tool": meta.get("tool") or tool,
                **{k: meta[k] for k in (
                    "evidence_class",
                    "independent_of_candidate_logic",
                    "usable_for_rule_proof",
                    "reason",
                )},
            }
            items.append(row)
            if not row["usable_for_rule_proof"] and row["evidence_class"] == CURRENT_DECODER_OUTPUT:
                circular.append(row)
            elif row["usable_for_rule_proof"]:
                independent.append(row)

    # Counterexamples that cite raw bank rejection are still useful
    for claim in cand.get("counterexamples") or []:
        tool = _tool_from_ref(claim)
        meta = classify_tool_evidence(tool) if tool else classify_tool_evidence(
            "get_configio_binding_trace"
        )
        items.append(
            {
                "section": "counterexamples",
                "claim": claim,
                "supporting_tool": tool or "raw_occupancy_or_binding",
                "evidence_class": meta["evidence_class"],
                "independent_of_candidate_logic": True,
                "usable_for_rule_proof": True,
                "reason": "capacity/occupancy counterexample — independent of decoder inheritance",
            }
        )

    audit = {
        "kind": "evidence_purity_audit",
        "investigation_id": "CP8_ALPHA_DIALECT_REMAINING_R1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "original_status_preserved": cand.get("status"),
        "revised_status": "CANDIDATE",
        "reclassification": "CANDIDATE_SUPPORT_WITH_DECODER_CONTAMINATION",
        "independent_physical_proof": "INCOMPLETE",
        "contamination_root_cause": (
            "get_physical_word_resolution_trace → PhysicalWordResolver; "
            "baseline d237af6 already defaults half_mod=chosen and emits "
            "shared_16ch_word / module_offset=8 for capacity>=16. "
            "R1 supporting traces therefore reproduce decoder behavior under investigation."
        ),
        "items": items,
        "circular_support_count": len(circular),
        "circular_support_items": circular,
        "independent_support_count": len(independent),
        "note": "Original transcript preserved. Do not call R1 failed.",
        "r2_needed": "PENDING_SOURCE_AND_CORPUS — prepare only if ambiguity remains after independent analysis",
    }
    out = R1 / "evidence_purity_audit.json"
    out.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    # Patch summary without rewriting transcript
    summary_path = R1 / "investigation_summary.json"
    if summary_path.is_file():
        s = json.loads(summary_path.read_text(encoding="utf-8"))
        s["evidence_purity"] = {
            "reclassification": audit["reclassification"],
            "independent_physical_proof": "INCOMPLETE",
            "circular_support_count": len(circular),
            "audit_path": str(out),
        }
        s["final_status"] = "CANDIDATE"
        s["independent_physical_proof"] = "INCOMPLETE"
        summary_path.write_text(json.dumps(s, indent=2), encoding="utf-8")
    print(json.dumps({
        "audit": str(out),
        "circular": len(circular),
        "independent": len(independent),
        "reclassification": audit["reclassification"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

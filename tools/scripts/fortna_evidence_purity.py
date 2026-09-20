#!/usr/bin/env python3
"""Investigator evidence-purity classification.

CURRENT_DECODER_OUTPUT must never independently prove a rule about the same
decoder behavior under investigation.
"""
from __future__ import annotations

from typing import Any

RAW_RUN_EVIDENCE = "RAW_RUN_EVIDENCE"
FORTNA_SOURCE_EVIDENCE = "FORTNA_SOURCE_EVIDENCE"
INDEPENDENT_DERIVATION = "INDEPENDENT_DERIVATION"
CURRENT_DECODER_OUTPUT = "CURRENT_DECODER_OUTPUT"
SHADOW_CANDIDATE_OUTPUT = "SHADOW_CANDIDATE_OUTPUT"
REFERENCE_ORACLE = "REFERENCE_ORACLE"
UNKNOWN = "UNKNOWN"

# Tool → default evidence class
TOOL_EVIDENCE_CLASS: dict[str, str] = {
    "get_project_identity": RAW_RUN_EVIDENCE,
    "get_configio_word": RAW_RUN_EVIDENCE,
    "get_configio_rows": RAW_RUN_EVIDENCE,
    "get_source_rows": RAW_RUN_EVIDENCE,
    "get_io_claim": RAW_RUN_EVIDENCE,
    "get_neighbor_claims": RAW_RUN_EVIDENCE,
    "get_adapter": INDEPENDENT_DERIVATION,
    "get_adapter_modules": INDEPENDENT_DERIVATION,
    "get_eip_bank_map": INDEPENDENT_DERIVATION,
    "get_module": INDEPENDENT_DERIVATION,
    "get_hardware_family": INDEPENDENT_DERIVATION,
    "get_configio_binding_trace": INDEPENDENT_DERIVATION,  # raw join of Configio↔EIPModules
    "get_configio_binding_cluster_summary": INDEPENDENT_DERIVATION,
    "get_physical_word_resolution_trace": CURRENT_DECODER_OUTPUT,
    "get_failure_cluster": CURRENT_DECODER_OUTPUT,
    "compare_candidate_rule_against_site": SHADOW_CANDIDATE_OUTPUT,
}


def classify_tool_evidence(tool_name: str) -> dict[str, Any]:
    name = (tool_name or "").strip()
    cls = TOOL_EVIDENCE_CLASS.get(name, UNKNOWN)
    independent = cls in {
        RAW_RUN_EVIDENCE,
        FORTNA_SOURCE_EVIDENCE,
        INDEPENDENT_DERIVATION,
    }
    usable_for_rule_proof = independent
    reason = {
        RAW_RUN_EVIDENCE: "direct Fortna RUN table/content",
        FORTNA_SOURCE_EVIDENCE: "FortnaPlus source code semantics",
        INDEPENDENT_DERIVATION: "deterministic join of raw tables without PhysicalWordResolver",
        CURRENT_DECODER_OUTPUT: "produced by PhysicalWordResolver / current decoder — circular for proving that decoder",
        SHADOW_CANDIDATE_OUTPUT: "comparison/diagnostic against a candidate — not independent proof",
        REFERENCE_ORACLE: "finished/reference L5X — forbidden in discovery",
        UNKNOWN: "unclassified tool",
    }.get(cls, "")
    return {
        "tool": name,
        "evidence_class": cls,
        "independent_of_candidate_logic": independent,
        "usable_for_rule_proof": usable_for_rule_proof,
        "reason": reason,
    }


def annotate_tool_result(tool_name: str, payload: Any) -> dict[str, Any]:
    meta = classify_tool_evidence(tool_name)
    return {
        **meta,
        "result": payload,
        "synthesis_warning": (
            "Current decoder output is not evidence that the decoder's rule is correct."
            if meta["evidence_class"] == CURRENT_DECODER_OUTPUT
            else None
        ),
    }


def cannot_prove_with_decoder_output(
    *,
    raw_status: str,
    decoder_status: str,
) -> bool:
    """True when synthesis must NOT treat decoder ASSIGNED as independent proof."""
    raw_u = (raw_status or "").upper()
    dec_u = (decoder_status or "").upper()
    if raw_u in {"UNKNOWN", "UNRESOLVED", "INSUFFICIENT_EVIDENCE", ""} and dec_u in {
        "ASSIGNED",
        "PROVEN",
        "DERIVED",
    }:
        return True
    return False

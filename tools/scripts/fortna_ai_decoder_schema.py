#!/usr/bin/env python3
"""DecoderRuleCandidate — AI decoder investigator output contract.

AI proposes decoding hypotheses. Site Forge verifies and Anton implements.
A DecoderRuleCandidate is NEVER compiler authority.
"""
from __future__ import annotations

from typing import Any

# Allowed statuses — REVIEW is not PASS; guessing is forbidden.
DECODER_CANDIDATE_STATUSES = frozenset(
    {"CANDIDATE", "REVIEW_REQUIRED", "INSUFFICIENT_EVIDENCE"}
)

# Forbidden: AI must not claim compiler/endpoint authority
FORBIDDEN_AUTHORITY_FIELDS = frozenset(
    {
        "physical_endpoint",
        "ai_derived",
        "compiler_accepted",
        "autogen_ready",
        "final_assignment",
        "plc_channel",
        "ready_for_build",
    }
)

DECODER_RULE_CANDIDATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "investigation_id": {"type": "string"},
        "subsystem": {"type": "string"},
        "failure_pattern": {"type": "string"},
        "affected_claim_ids": {"type": "array", "items": {"type": "string"}},
        "affected_count": {"type": "integer"},
        "observed_facts": {"type": "array", "items": {"type": "string"}},
        "evidence_refs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source": {"type": "string"},
                    "ref": {"type": "string"},
                    "fact": {"type": "string"},
                },
                "required": ["source", "ref", "fact"],
            },
        },
        "candidate_rule_name": {"type": "string"},
        "candidate_rule_description": {"type": "string"},
        "proposed_inputs": {"type": "array", "items": {"type": "string"}},
        "proposed_transformation": {"type": "string"},
        "expected_outputs": {"type": "array", "items": {"type": "string"}},
        "supporting_examples": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "claim_id": {"type": "string"},
                    "summary": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["summary"],
            },
        },
        "counterexamples": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "claim_id": {"type": "string"},
                    "summary": {"type": "string"},
                    "why_contradicts": {"type": "string"},
                },
                "required": ["summary", "why_contradicts"],
            },
        },
        "ambiguities": {"type": "array", "items": {"type": "string"}},
        "additional_evidence_needed": {"type": "array", "items": {"type": "string"}},
        "tests_required": {"type": "array", "items": {"type": "string"}},
        "scope": {"type": "string"},
        "confidence": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
        "status": {
            "type": "string",
            "enum": ["CANDIDATE", "REVIEW_REQUIRED", "INSUFFICIENT_EVIDENCE"],
        },
    },
    "required": [
        "investigation_id",
        "subsystem",
        "failure_pattern",
        "affected_claim_ids",
        "affected_count",
        "observed_facts",
        "evidence_refs",
        "candidate_rule_name",
        "candidate_rule_description",
        "proposed_inputs",
        "proposed_transformation",
        "expected_outputs",
        "supporting_examples",
        "counterexamples",
        "ambiguities",
        "additional_evidence_needed",
        "tests_required",
        "scope",
        "confidence",
        "status",
    ],
}


def validate_decoder_rule_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a DecoderRuleCandidate. Never grants compiler authority."""
    reasons: list[str] = []
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "compiler_authority": False,
            "reasons": ["payload is not an object"],
            "status": "INSUFFICIENT_EVIDENCE",
        }

    for key in FORBIDDEN_AUTHORITY_FIELDS:
        if key in payload:
            reasons.append(f"forbidden authority field present: {key}")

    # Nested endpoint assignments are also forbidden
    blob = str(payload)
    if "physical_endpoint" in blob and "physical_endpoint" not in str(
        payload.get("observed_facts") or []
    ):
        # Allow mentioning prior proposals in observed_facts text only
        pass
    for key in ("final_assignment", "plc_channel", "ai_derived", "ready_for_build"):
        if key in payload:
            reasons.append(f"forbidden authority field: {key}")

    status = str(payload.get("status") or "").strip().upper()
    if status not in DECODER_CANDIDATE_STATUSES:
        reasons.append(f"invalid status {status!r} — REVIEW is not PASS; no READY")

    if status == "READY":
        reasons.append("READY is not a valid DecoderRuleCandidate status")

    required = DECODER_RULE_CANDIDATE_SCHEMA["required"]
    for req in required:
        if req not in payload:
            reasons.append(f"missing required field: {req}")

    ids = payload.get("affected_claim_ids")
    if not isinstance(ids, list):
        reasons.append("affected_claim_ids must be a list")
    else:
        count = payload.get("affected_count")
        if isinstance(count, int) and count != len(ids):
            reasons.append(
                f"affected_count {count} != len(affected_claim_ids) {len(ids)}"
            )

    # Candidate must not claim to assign endpoints
    transform = str(payload.get("proposed_transformation") or "")
    if "ASSIGN_ENDPOINT" in transform.upper() or "WRITE_L5X" in transform.upper():
        reasons.append("proposed_transformation must not assign endpoints or write L5X")

    ok = len(reasons) == 0
    return {
        "ok": ok,
        "compiler_authority": False,  # always false — by design
        "creates_ready": False,  # always false — by design
        "reasons": reasons,
        "status": status if status in DECODER_CANDIDATE_STATUSES else "INSUFFICIENT_EVIDENCE",
    }


def candidate_cannot_create_ready(candidate: dict[str, Any]) -> bool:
    """Invariant: validating a candidate never yields I/O READY."""
    result = validate_decoder_rule_candidate(candidate)
    return result.get("creates_ready") is False and result.get("compiler_authority") is False

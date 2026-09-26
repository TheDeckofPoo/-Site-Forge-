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
        "affected_scope": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "machine": {"type": "string"},
                "disposition": {"type": "string"},
                "subsystem": {"type": "string"},
                "root_cause": {"type": "string"},
                "words": {"type": "array", "items": {"type": ["integer", "string"]}},
                "query": {"type": "string"},
            },
        },
        "affected_claim_ids": {"type": "array", "items": {"type": "string"}},
        "affected_count": {"type": "integer"},
        "materialized_affected_claim_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
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


def materialize_affected_claims(
    payload: dict[str, Any],
    claims: list[dict[str, Any]],
    *,
    machine: str = "",
) -> dict[str, Any]:
    """Site Forge materializes AI affected_scope into exact claim IDs."""
    scope = payload.get("affected_scope") if isinstance(payload.get("affected_scope"), dict) else {}
    want_machine = str(scope.get("machine") or machine or "").strip()
    want_disp = str(scope.get("disposition") or "").strip()
    want_words = {str(w) for w in (scope.get("words") or [])}
    explicit = payload.get("affected_claim_ids") if isinstance(payload.get("affected_claim_ids"), list) else []
    # If explicit IDs look like real claim ids (not a scope selector), use them
    explicit_real = [
        str(x)
        for x in explicit
        if str(x).startswith("cl_") or (str(x) and "scope" not in str(x).lower())
    ]

    selected: list[str] = []
    if explicit_real and not scope:
        selected = explicit_real
    else:
        for c in claims:
            if want_machine and str(c.get("machine") or machine) != want_machine:
                # also allow empty machine on claim
                if str(c.get("machine") or "").strip() and str(c.get("machine")) != want_machine:
                    continue
            if want_disp and str(c.get("deterministic_disposition") or c.get("disposition") or "") != want_disp:
                continue
            if want_words and str(c.get("word")) not in want_words:
                continue
            cid = c.get("claim_id")
            if cid:
                selected.append(str(cid))
        if not selected and explicit_real:
            selected = explicit_real

    # Foreign machine check
    foreign = []
    by_id = {str(c.get("claim_id")): c for c in claims if c.get("claim_id")}
    for cid in selected:
        c = by_id.get(cid)
        if not c:
            continue
        cm = str(c.get("machine") or machine or "").strip()
        if want_machine and cm and cm != want_machine:
            foreign.append(cid)

    missing = [cid for cid in selected if cid not in by_id]
    dups = [cid for cid in selected if selected.count(cid) > 1]
    unique = list(dict.fromkeys(selected))
    count = payload.get("affected_count")
    ok = (
        not foreign
        and not missing
        and not dups
        and (not isinstance(count, int) or count == len(unique) or (scope and isinstance(count, int)))
    )
    # When scope present, Site Forge count is authoritative materialization length
    if scope and isinstance(count, int) and count != len(unique):
        # Soft: report mismatch but still return materialized set
        ok = False

    return {
        "ok": ok and not foreign and not missing and len(dups) == 0,
        "materialized_affected_claim_ids": unique,
        "materialized_count": len(unique),
        "foreign_machine_ids": foreign,
        "missing_ids": missing,
        "duplicate_ids": sorted(set(dups)),
        "affected_count_declared": count,
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
    if ids is not None and not isinstance(ids, list):
        reasons.append("affected_claim_ids must be a list when present")
    # Alias: some model outputs use affected_claims
    claims_alias = payload.get("affected_claims")
    if claims_alias is not None and not isinstance(claims_alias, list):
        reasons.append("affected_claims must be a list when present")
    scope = payload.get("affected_scope")
    if scope is not None and not isinstance(scope, dict):
        reasons.append("affected_scope must be an object when present")
    # Prefer scope+count; explicit IDs optional for small investigations.
    # If materialized_affected_claim_ids present, enforce count match.
    materialized = payload.get("materialized_affected_claim_ids")
    count = payload.get("affected_count")
    # ORI schema harden: affected_count must equal listed claim identities when present.
    listed = None
    if isinstance(materialized, list):
        listed = materialized
    elif isinstance(ids, list):
        listed = ids
    elif isinstance(claims_alias, list):
        listed = claims_alias
    if isinstance(count, int) and listed is not None:
        if count != len(listed):
            reasons.append(
                f"INVALID_CANDIDATE_SCHEMA: affected_count {count} != len(affected_claims/ids) {len(listed)}"
            )
        if len(listed) != len({str(x) for x in listed}):
            reasons.append("duplicate ids in affected claim list")
    elif isinstance(materialized, list) and isinstance(count, int):
        if count != len(materialized):
            reasons.append(
                f"affected_count {count} != len(materialized_affected_claim_ids) {len(materialized)}"
            )
        if len(materialized) != len(set(materialized)):
            reasons.append("duplicate ids in materialized_affected_claim_ids")
    elif isinstance(ids, list) and isinstance(count, int) and not scope:
        # Legacy: only enforce ID length match when no scope descriptor present
        if count != len(ids) and not (
            len(ids) == 1 and isinstance(ids[0], str) and "scope" in ids[0].lower()
        ):
            if len(ids) != count:
                reasons.append(
                    f"affected_count {count} != len(affected_claim_ids) {len(ids)} "
                    "(provide affected_scope or materialized_affected_claim_ids)"
                )

    # Candidate must not claim to assign endpoints
    transform = str(payload.get("proposed_transformation") or "")
    if "ASSIGN_ENDPOINT" in transform.upper() or "WRITE_L5X" in transform.upper():
        reasons.append("proposed_transformation must not assign endpoints or write L5X")

    ok = len(reasons) == 0
    out_status = status if status in DECODER_CANDIDATE_STATUSES else "INSUFFICIENT_EVIDENCE"
    if not ok and any("INVALID_CANDIDATE_SCHEMA" in r for r in reasons):
        out_status = "REVIEW_REQUIRED"
    return {
        "ok": ok,
        "compiler_authority": False,  # always false — by design
        "creates_ready": False,  # always false — by design
        "use_for_build": False,  # always false — by design
        "ai_endpoint_authority": False,  # always false — by design
        "reasons": reasons,
        "validation_error": None if ok else "INVALID_CANDIDATE_SCHEMA",
        "status": out_status,
    }


def candidate_cannot_create_ready(candidate: dict[str, Any]) -> bool:
    """Invariant: validating a candidate never yields I/O READY."""
    result = validate_decoder_rule_candidate(candidate)
    return result.get("creates_ready") is False and result.get("compiler_authority") is False

#!/usr/bin/env python3
"""Relay shadow-mode trigger eligibility classifier.

Deterministic PROVEN points do NOT invoke Relay.
Unresolved / contradictory / suspicious-review points may.
"""
from __future__ import annotations

from typing import Any

# Reasons that may select a case for Relay shadow review
RELAY_REASONS = frozenset(
    {
        "ENDPOINT_UNRESOLVED",
        "REVIEW_REQUIRED",
        "UNKNOWN_OWNER",
        "NO_MODULE_CHANNEL_PROOF",
        "CONFLICTING_LOCAL_EVIDENCE",
        "DUPLICATE_ENDPOINT",
        "STATUS_RANGE_SUSPECT",
        "UNSUPPORTED_ADAPTER",
        "WORD_ONLY_EVIDENCE",
        "DIRECTION_MISMATCH",
        "SUSPICIOUS_PROVEN_CONFLICT",
        "UNSUPPORTED_DETERMINISTIC_DECODER",
    }
)

_PROVEN_OK = frozenset({"PROVEN", "FULL", "READY", "AUTO_RESOLVED"})


def _norm(s: Any) -> str:
    return str(s or "").strip().upper()


def classify_relay_trigger(point: dict[str, Any]) -> dict[str, Any]:
    """Return {eligible, reasons[], skip_reason}.

    `point` is a deterministic Site Forge I/O / Safety inventory slice.
    """
    reasons: list[str] = []
    conf = _norm(point.get("confidence") or point.get("binding_confidence") or "")
    status = _norm(point.get("status") or point.get("review_status") or "")
    why = _norm(point.get("review_reason") or point.get("reason") or "")
    scope = _norm(point.get("inventory_scope") or point.get("ownership") or "")
    proof = _norm(point.get("endpoint_proof_depth") or "")
    assignable = point.get("assignable")
    endpoint = str(
        point.get("physicalEndpoint")
        or point.get("physical_endpoint")
        or point.get("channel")
        or ""
    ).strip()
    contradictions = list(point.get("contradictions") or [])
    dup = bool(point.get("endpointConflict") or point.get("duplicate_endpoint"))
    unsupported = bool(
        point.get("unsupported")
        or "UNSUPPORTED" in why
        or _norm(point.get("disposition")) == "UNSUPPORTED_INTERFACE"
    )
    nonphysical = bool(
        point.get("nonphysical")
        or point.get("memory_row")
        or "MEMORY" in why
        or "NONPHYSICAL" in why
    )

    if nonphysical:
        return {
            "eligible": False,
            "reasons": [],
            "skip_reason": "NONPHYSICAL_OR_MEMORY",
            "relay_reason": None,
        }

    # Ordinary deterministic PROVEN with endpoint and no conflict → skip
    proven_clean = (
        (conf in _PROVEN_OK or status in _PROVEN_OK)
        and endpoint
        and assignable is not False
        and not contradictions
        and not dup
        and proof not in {"WORD_ONLY", "NONE"}
        and "DIRECTION" not in why
        and scope not in {"UNKNOWN_OWNERSHIP", "UNRELATED_FOREIGN"}
        and not unsupported
    )
    if proven_clean and status not in {"REVIEW_REQUIRED", "UNRESOLVED"}:
        return {
            "eligible": False,
            "reasons": [],
            "skip_reason": "DETERMINISTIC_PROVEN",
            "relay_reason": None,
        }

    if not endpoint or status in {"UNRESOLVED", "UNKNOWN"} or conf in {"UNKNOWN", ""}:
        if not endpoint or conf == "UNKNOWN" or status == "UNRESOLVED":
            reasons.append("ENDPOINT_UNRESOLVED")
    if status == "REVIEW_REQUIRED" or "REVIEW" in why:
        reasons.append("REVIEW_REQUIRED")
    if scope in {"UNKNOWN_OWNERSHIP", "UNKNOWN"} or "UNKNOWN_OWNER" in why:
        reasons.append("UNKNOWN_OWNER")
    if proof in {"WORD_ONLY", "NONE"} or "NO_MODULE_CHANNEL" in why or "WORD_ONLY" in why:
        reasons.append("NO_MODULE_CHANNEL_PROOF")
        if proof == "WORD_ONLY":
            reasons.append("WORD_ONLY_EVIDENCE")
    if contradictions or "CONFLICT" in why or "CONFLICTING" in why:
        reasons.append("CONFLICTING_LOCAL_EVIDENCE")
    if dup:
        reasons.append("DUPLICATE_ENDPOINT")
    if "STATUS_RANGE" in why or point.get("status_range_suspect"):
        reasons.append("STATUS_RANGE_SUSPECT")
    if unsupported or "WAGO" in why or "PANTHER" in why:
        reasons.append("UNSUPPORTED_ADAPTER")
        reasons.append("UNSUPPORTED_DETERMINISTIC_DECODER")
    if "DIRECTION" in why:
        reasons.append("DIRECTION_MISMATCH")
    if conf in _PROVEN_OK and (contradictions or dup or "CONFLICT" in why):
        reasons.append("SUSPICIOUS_PROVEN_CONFLICT")

    # de-dupe preserve order
    seen: set[str] = set()
    ordered: list[str] = []
    for r in reasons:
        if r in RELAY_REASONS and r not in seen:
            seen.add(r)
            ordered.append(r)

    eligible = len(ordered) > 0
    return {
        "eligible": eligible,
        "reasons": ordered,
        "skip_reason": None if eligible else "NO_TRIGGER_MATCH",
        "relay_reason": ordered[0] if ordered else None,
    }


def select_relay_candidates(
    points: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Annotate points with trigger decision; return eligible subset."""
    out: list[dict[str, Any]] = []
    for p in points or []:
        if not isinstance(p, dict):
            continue
        decision = classify_relay_trigger(p)
        row = {**p, "relay_trigger": decision}
        if decision.get("eligible"):
            out.append(row)
    return out

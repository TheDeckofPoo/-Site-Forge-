#!/usr/bin/env python3
"""ORI-028: AI investigation escalation eligibility (deterministic-first).

AI remains advisory. Escalation only decides whether investigation is *available*.
"""
from __future__ import annotations

from typing import Any


def evaluate_ai_investigation_eligibility(
    *,
    deterministic_claims: int = 0,
    deterministic_resolved: int = 0,
    unresolved_physical: int = 0,
    unsupported_interface_count: int = 0,
    raw_evidence_count: int | None = None,
    min_unresolved: int = 5,
) -> dict[str, Any]:
    """Return whether AI investigation is eligible for a site snapshot.

    Total deterministic failure with meaningful raw evidence is eligible:
        raw_evidence > 0 AND deterministic_resolved == 0
    """
    raw = int(
        raw_evidence_count
        if raw_evidence_count is not None
        else unsupported_interface_count
    )
    reasons: list[str] = []
    if raw > 0 and int(deterministic_resolved) == 0 and int(deterministic_claims) == 0:
        reasons.append(
            f"total deterministic failure with raw unsupported/config evidence ({raw})"
        )
    if int(unresolved_physical) >= int(min_unresolved):
        reasons.append(f"≥{min_unresolved} unresolved physical endpoints ({unresolved_physical})")
    if int(unsupported_interface_count) > 0 and int(deterministic_resolved) == 0:
        if not any("total deterministic failure" in r for r in reasons):
            reasons.append(
                f"unsupported interface evidence present ({unsupported_interface_count}) "
                "with zero deterministic resolution"
            )
    # Empty/noisy: no meaningful evidence
    if raw <= 0 and int(unresolved_physical) <= 0 and int(deterministic_claims) <= 0:
        return {
            "eligible": False,
            "reasons": ["no meaningful raw or unresolved evidence"],
            "raw_evidence": raw,
            "deterministic_claims": int(deterministic_claims),
            "deterministic_resolved": int(deterministic_resolved),
            "unsupported_interface_count": int(unsupported_interface_count),
        }
    return {
        "eligible": len(reasons) > 0,
        "reasons": reasons,
        "raw_evidence": raw,
        "deterministic_claims": int(deterministic_claims),
        "deterministic_resolved": int(deterministic_resolved),
        "unsupported_interface_count": int(unsupported_interface_count),
        "ai_endpoint_authority": False,
        "use_for_build": False,
    }

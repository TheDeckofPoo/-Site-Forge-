#!/usr/bin/env python3
"""Stable unknown-pattern signatures for future learning-engine clustering.

No API calls. Emit deterministic classifications when decoding fails.
"""
from __future__ import annotations

import hashlib
from typing import Any

KNOWN_RULE_APPLIED = "KNOWN_RULE_APPLIED"
UNKNOWN_PATTERN = "UNKNOWN_PATTERN"
RULE_CONFLICT = "RULE_CONFLICT"
AMBIGUOUS_EVIDENCE = "AMBIGUOUS_EVIDENCE"


def classify_decode_outcome(
    *,
    resolved: bool,
    ambiguous: bool = False,
    conflict: bool = False,
    assign_how: str = "",
) -> str:
    if conflict:
        return RULE_CONFLICT
    if ambiguous:
        return AMBIGUOUS_EVIDENCE
    if resolved and assign_how:
        return KNOWN_RULE_APPLIED
    return UNKNOWN_PATTERN


def build_failure_signature(
    *,
    subsystem: str,
    hardware_family: str = "",
    configio_form: str = "",
    catalog_class: str = "",
    direction_evidence_class: str = "",
    bank_relationship_class: str = "",
    failure_reason: str = "",
) -> dict[str, Any]:
    parts = {
        "subsystem": (subsystem or "").strip().upper(),
        "hardware_family": (hardware_family or "").strip().upper(),
        "configio_form": (configio_form or "").strip().upper(),
        "catalog_class": (catalog_class or "").strip().upper(),
        "direction_evidence_class": (direction_evidence_class or "").strip().upper(),
        "bank_relationship_class": (bank_relationship_class or "").strip().upper(),
        "failure_reason": (failure_reason or "").strip().upper(),
    }
    raw = "|".join(f"{k}={v}" for k, v in parts.items())
    return {
        "signature_id": "fs_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16],
        "classification": UNKNOWN_PATTERN,
        **parts,
    }

#!/usr/bin/env python3
"""Multi-profile I/O ownership architecture (Gate 5).

PhysicalEndpoint
      +
IOOwnershipEvidence[]  (one or more profiles)
      ↓
IOOwnershipResolver
      ↓
ASSIGNED | UNRESOLVED_OWNER | PROVEN_SPARE | UNUSED_MAPPED | ENGINEER_ASSIGNED | UNKNOWN

Profiles are additive — no silent override. Conflicting proven owners → REVIEW.
Engineer Hardware Name override → ENGINEER_ASSIGNED (persisted via overrides).
"""
from __future__ import annotations

from typing import Any

# Profile IDs (evidence-backed; not site names)
PROFILE_CONVEYOR_WORD_BIT = "CONVEYOR_WORD_BIT"
PROFILE_CONFIGIO_PANEL_CATALOG = "CONFIGIO_PANEL_CATALOG"  # CP2-1794-IA16-3
PROFILE_CONFIGIO_PANEL_NODE = "CONFIGIO_PANEL_NODE"  # CP5-NODE53-1A
PROFILE_CONFIGIO_CATALOG_WORD_BANK = "CONFIGIO_CATALOG_WORD_BANK"  # 1794-IA16-600-4
PROFILE_CONFIGIO_CATALOG_INDEX = "CONFIGIO_CATALOG_INDEX"  # 1794-IA16-5 (MSCATL)
PROFILE_ENGINEER_ASSIGNED = "ENGINEER_ASSIGNED"
PROFILE_UNKNOWN = "UNKNOWN"


def classify_configio_profile(desc_form: str | None) -> str:
    f = str(desc_form or "").strip().lower()
    if f == "panel_catalog":
        return PROFILE_CONFIGIO_PANEL_CATALOG
    if f == "panel_node":
        return PROFILE_CONFIGIO_PANEL_NODE
    if f in ("catalog_word_bank", "catalog_aent_node_bank"):
        return PROFILE_CONFIGIO_CATALOG_WORD_BANK
    if f == "catalog_index":
        return PROFILE_CONFIGIO_CATALOG_INDEX
    return PROFILE_UNKNOWN


def ownership_evidence(
    *,
    profile_id: str,
    source_table: str,
    source_record: str = "",
    raw_address: str = "",
    normalized_endpoint: str = "",
    engineering_owner: str | None = None,
    evidence_authority: str = "PROVEN",
    rejection_reason: str | None = None,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "profile_id": profile_id,
        "source_table": source_table,
        "source_record": source_record,
        "raw_address": raw_address,
        "normalized_endpoint": normalized_endpoint,
        "engineering_owner": engineering_owner,
        "evidence_authority": evidence_authority,
        "rejection_reason": rejection_reason,
        "extras": extras or {},
    }


def merge_ownership_evidence(evidences: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine profile evidences. Conflicting owners → REVIEW_REQUIRED."""
    owners = []
    for e in evidences or []:
        o = str(e.get("engineering_owner") or "").strip()
        if o:
            owners.append((o, e.get("profile_id"), e.get("evidence_authority")))
    uniq = {o[0] for o in owners}
    if len(uniq) > 1:
        return {
            "owner_state": "UNRESOLVED_OWNER",
            "engineering_owner": None,
            "rejection_reason": "MULTIPLE_ENDPOINT_CANDIDATES",
            "review": "REVIEW_REQUIRED",
            "candidates": sorted(uniq),
            "evidences": evidences,
        }
    if len(uniq) == 1:
        owner = next(iter(uniq))
        eng = any(a == "ENGINEER_ASSIGNED" or p == PROFILE_ENGINEER_ASSIGNED for _, p, a in owners)
        return {
            "owner_state": "ENGINEER_ASSIGNED" if eng else "ASSIGNED",
            "engineering_owner": owner,
            "rejection_reason": None,
            "review": None,
            "evidences": evidences,
        }
    return {
        "owner_state": "UNKNOWN",
        "engineering_owner": None,
        "rejection_reason": None,
        "review": None,
        "evidences": evidences,
    }

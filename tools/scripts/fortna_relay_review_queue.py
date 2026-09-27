#!/usr/bin/env python3
"""Normalized Relay shadow review queue + defect pattern grouping."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fortna_relay_schema import suggest_action

SUGGESTED_ACTIONS = frozenset(
    {
        "ACCEPT_DETERMINISTIC",
        "ENGINEER_REVIEW",
        "WARDEN_VERIFY",
        "DETERMINISTIC_RULE_CANDIDATE",
        "UNSUPPORTED",
        "IGNORE_NONPHYSICAL",
    }
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def make_review_item(
    *,
    deterministic_point: dict[str, Any],
    evidence_packet: dict[str, Any],
    relay_invocation: dict[str, Any],
) -> dict[str, Any]:
    """Build one engineer review-queue item. Never APPLY ENDPOINT."""
    result = relay_invocation.get("result") if isinstance(relay_invocation, dict) else None
    result = result if isinstance(result, dict) else {}
    validation = relay_invocation.get("validation") or {}
    det = deterministic_point or {}
    action = suggest_action(result, deterministic=det)
    if relay_invocation.get("status") == "RELAY_POLICY_VIOLATION":
        action = "ENGINEER_REVIEW"
    if relay_invocation.get("status") == "RELAY_RESULT_INVALID":
        action = "ENGINEER_REVIEW"
    if det.get("nonphysical") or det.get("memory_row"):
        action = "IGNORE_NONPHYSICAL"
    if det.get("unsupported"):
        action = "UNSUPPORTED"

    item = {
        "review_id": f"rr_{_sha({'c': det.get('case_id') or det.get('name'), 'r': result.get('case_id')})[:12]}",
        "signal": det.get("name") or det.get("signal") or result.get("case_id"),
        "controller": evidence_packet.get("machine") or result.get("source_controller"),
        "panel": evidence_packet.get("panel") or result.get("source_panel"),
        "raw_address": (evidence_packet.get("case") or {}).get("raw_address")
        or result.get("raw_address"),
        "deterministic_site_forge_result": {
            "confidence": det.get("confidence") or det.get("binding_confidence"),
            "status": det.get("status"),
            "review_reason": det.get("review_reason"),
            "physicalEndpoint": det.get("physicalEndpoint"),
            "assignable": det.get("assignable"),
        },
        "relay_result": result or None,
        "relay_confidence": result.get("confidence"),
        "relay_status": relay_invocation.get("status"),
        "provenance": result.get("evidence") or [],
        "contradiction": list(result.get("contradictions") or det.get("contradictions") or []),
        "missing_proof": list(result.get("missing_proof") or []),
        "suggested_action": action if action in SUGGESTED_ACTIONS else "ENGINEER_REVIEW",
        "relay_reason": (evidence_packet.get("case") or {}).get("relay_reason"),
        "production_authority": False,
        "apply_endpoint_allowed": False,
        "schema_validation_status": validation.get("status"),
        "knowledge_bundle_hash": relay_invocation.get("knowledge_bundle_hash"),
        "generated_at": _ts(),
    }
    return item


def group_review_items(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Group repeated defect patterns into engineer decision cards."""
    groups: dict[str, dict[str, Any]] = {}
    for it in items or []:
        if not isinstance(it, dict):
            continue
        key_parts = [
            str(it.get("relay_reason") or "UNKNOWN"),
            str(it.get("suggested_action") or ""),
            str(it.get("panel") or ""),
            str((it.get("missing_proof") or ["_"])[0] if it.get("missing_proof") else "_"),
            str((it.get("contradiction") or ["_"])[0] if it.get("contradiction") else "_"),
        ]
        key = "|".join(key_parts)
        if key not in groups:
            groups[key] = {
                "group_id": f"rg_{_sha(key_parts)[:12]}",
                "defect_pattern": it.get("relay_reason") or it.get("suggested_action"),
                "panel": it.get("panel"),
                "controller": it.get("controller"),
                "suggested_action": it.get("suggested_action"),
                "affected_count": 0,
                "affected_points": [],
                "representative": it,
                "production_authority": False,
            }
        g = groups[key]
        g["affected_count"] += 1
        g["affected_points"].append(
            {
                "review_id": it.get("review_id"),
                "signal": it.get("signal"),
                "raw_address": it.get("raw_address"),
                "relay_confidence": it.get("relay_confidence"),
            }
        )
    # Sort largest groups first
    return sorted(groups.values(), key=lambda g: (-int(g["affected_count"]), str(g["group_id"])))

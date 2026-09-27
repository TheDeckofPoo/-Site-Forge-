#!/usr/bin/env python3
"""Validate Relay shadow results against RELAY_OUTPUT_SCHEMA.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_SCHEMA = REPO_ROOT / "ai" / "agents" / "relay" / "RELAY_OUTPUT_SCHEMA.json"

CONFIDENCES = frozenset(
    {"PROVEN", "DERIVED", "ENGINEER_ASSIGNED", "REVIEW_REQUIRED", "UNKNOWN"}
)
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


def load_schema(path: Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_SCHEMA
    return json.loads(p.read_text(encoding="utf-8"))


def validate_relay_result(
    result: Any,
    *,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return {ok, status, errors[], normalized}.

    status:
      OK
      RELAY_RESULT_INVALID
      RELAY_POLICY_VIOLATION
    """
    _ = schema or load_schema()
    errors: list[str] = []
    if not isinstance(result, dict):
        return {
            "ok": False,
            "status": "RELAY_RESULT_INVALID",
            "errors": ["result is not an object"],
            "normalized": None,
        }

    required = [
        "case_id",
        "source_controller",
        "source_panel",
        "raw_address",
        "evidence",
        "confidence",
        "cross_panel_evidence_encountered",
        "cross_panel_physical_mapping_used",
    ]
    for key in required:
        if key not in result:
            errors.append(f"missing required field: {key}")

    if "confidence" in result and result["confidence"] not in CONFIDENCES:
        errors.append(f"invalid confidence: {result.get('confidence')}")

    if "evidence" in result and not isinstance(result["evidence"], list):
        errors.append("evidence must be an array")
    elif isinstance(result.get("evidence"), list):
        for i, ev in enumerate(result["evidence"]):
            if not isinstance(ev, dict) or "source" not in ev or "detail" not in ev:
                errors.append(f"evidence[{i}] must have source+detail")

    if result.get("direction") not in (None, "I", "O"):
        errors.append(f"invalid direction: {result.get('direction')}")

    if not isinstance(result.get("cross_panel_evidence_encountered"), bool):
        if "cross_panel_evidence_encountered" in result:
            errors.append("cross_panel_evidence_encountered must be boolean")
    if not isinstance(result.get("cross_panel_physical_mapping_used"), bool):
        if "cross_panel_physical_mapping_used" in result:
            errors.append("cross_panel_physical_mapping_used must be boolean")

    if errors:
        return {
            "ok": False,
            "status": "RELAY_RESULT_INVALID",
            "errors": errors,
            "normalized": None,
        }

    # Policy: cross-panel physical mapping is never an actionable endpoint
    if result.get("cross_panel_physical_mapping_used") is True:
        return {
            "ok": False,
            "status": "RELAY_POLICY_VIOLATION",
            "errors": [
                "cross_panel_physical_mapping_used=true is forbidden as actionable endpoint"
            ],
            "normalized": dict(result),
            "keep_visible_for_review": True,
        }

    return {
        "ok": True,
        "status": "OK",
        "errors": [],
        "normalized": dict(result),
    }


def suggest_action(result: dict[str, Any], *, deterministic: dict[str, Any] | None = None) -> str:
    """Map Relay + deterministic state to an engineer suggested action."""
    det = deterministic or {}
    conf = str(result.get("confidence") or "").upper()
    if det.get("nonphysical") or det.get("memory_row"):
        return "IGNORE_NONPHYSICAL"
    if det.get("unsupported"):
        return "UNSUPPORTED"
    if conf == "REVIEW_REQUIRED" or result.get("missing_proof"):
        return "ENGINEER_REVIEW"
    if conf == "UNKNOWN":
        return "ENGINEER_REVIEW"
    if conf == "DERIVED":
        return "WARDEN_VERIFY"
    if conf == "PROVEN" and det.get("confidence") == "PROVEN":
        return "ACCEPT_DETERMINISTIC"
    if conf in {"PROVEN", "DERIVED"} and result.get("recommended_deterministic_check"):
        return "DETERMINISTIC_RULE_CANDIDATE"
    return "ENGINEER_REVIEW"

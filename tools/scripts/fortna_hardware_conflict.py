#!/usr/bin/env python3
"""Distinguish alias mismatches from true hardware type source conflicts.

ALIAS_CATALOG_MISMATCH:
  human Name/Desc resembles catalog A; authoritative Type says B

HARDWARE_TYPE_SOURCE_CONFLICT:
  eipcfg Module@type and EIPModules.Type disagree for same proven adapter+slot
  → REVIEW_REQUIRED / RULE_CONFLICT — do not silently pick a winner
"""
from __future__ import annotations

from typing import Any

ALIAS_CATALOG_MISMATCH = "ALIAS_CATALOG_MISMATCH"
HARDWARE_TYPE_SOURCE_CONFLICT = "HARDWARE_TYPE_SOURCE_CONFLICT"


def classify_catalog_disagreement(
    *,
    human_name_or_desc: str = "",
    eipmodules_type: str = "",
    eipcfg_type: str = "",
) -> dict[str, Any]:
    human = (human_name_or_desc or "").strip().upper()
    em = (eipmodules_type or "").strip().upper()
    ec = (eipcfg_type or "").strip().upper()

    # Extract catalog-looking token from human text if present
    import re

    m = re.search(r"(\d{4}-[A-Z0-9]+)", human)
    human_cat = m.group(1) if m else ""

    result: dict[str, Any] = {
        "human_raw": human_name_or_desc,
        "human_catalog_token": human_cat,
        "eipmodules_type": eipmodules_type,
        "eipcfg_type": eipcfg_type,
        "classification": None,
        "status": "OK",
    }

    if em and ec and em != ec:
        result["classification"] = HARDWARE_TYPE_SOURCE_CONFLICT
        result["status"] = "REVIEW_REQUIRED"
        result["reason"] = "eipcfg_type_disagrees_with_eipmodules_type"
        return result

    if human_cat and em and human_cat != em:
        result["classification"] = ALIAS_CATALOG_MISMATCH
        result["status"] = "HINT_ONLY"
        result["reason"] = "human_desc_or_name_catalog_differs_from_eipmodules_type"
        return result

    if human_cat and ec and not em and human_cat != ec:
        result["classification"] = ALIAS_CATALOG_MISMATCH
        result["status"] = "HINT_ONLY"
        result["reason"] = "human_catalog_differs_from_eipcfg_type"
        return result

    return result

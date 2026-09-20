"""Site Forge PostgreSQL warehouse foundation (offline-capable).

PostgreSQL is the primary persistent warehouse. DuckDB may be used later as an
optional analytics sidecar. CURRENT SITE EVIDENCE and CROSS-SITE KNOWLEDGE stay
isolated via repository interfaces.
"""
from __future__ import annotations

from typing import Any

EXTRACTOR_VERSION = "warehouse_hw_io_v1.0.0"


def seed_cp8_candidate_status() -> dict[str, Any]:
    """CP8 / PANEL_CATALOG_NUMERIC_ALPHA honesty seed — never auto-production.

    Returns a dict suitable for learning.rule_candidates staging. Status is
    CANDIDATE_RULE only; production promotion requires an explicit gate.
    """
    return {
        "rule_id": "panel_catalog_numeric_alpha_low_a_slot",
        "title": "PANEL_CATALOG_NUMERIC_ALPHA Low/A slot join (CP8 investigation)",
        "status": "CANDIDATE_RULE",
        "form": "PANEL_CATALOG_NUMERIC_ALPHA",
        "summary": (
            "Observed on ORNCCP4 Low/A rows with direct EIPModules slot agreement; "
            "High/B physical relationship is NOT proven. Identity is structural form, "
            "not the CP8 panel token."
        ),
        "production_auto_promote": False,
        "not_universal": True,
        "investigation_id": "CP8_ALPHA_DIALECT",
        "evidence_class": "INDEPENDENT_DERIVATION",
        "related_forms": ["PANEL_CATALOG_NUMERIC_ALPHA"],
        "related_modules": [
            "classify_configio_dialect",
            "cp8_evidence_integrity",
        ],
        "honesty_notes": [
            "Do not promote to PRODUCTION_RULE from warehouse seed alone.",
            "High half may have NO_PHYSICAL_CLAIMS (e.g. OA8I).",
            "Desc catalog may disagree with EIPModules.Type — record conflict, do not invent.",
        ],
        "extractor_version": EXTRACTOR_VERSION,
    }


__all__ = [
    "EXTRACTOR_VERSION",
    "seed_cp8_candidate_status",
]

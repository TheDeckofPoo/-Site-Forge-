#!/usr/bin/env python3
"""Stable unknown-pattern signatures for future learning-engine clustering.

No API calls. Emit deterministic classifications when decoding fails.
Identity fields are site-independent — same failure across sites → same signature_id.
Never include site/controller/machine names in the identity hash.
"""
from __future__ import annotations

import hashlib
from typing import Any

KNOWN_RULE_APPLIED = "KNOWN_RULE_APPLIED"
UNKNOWN_PATTERN = "UNKNOWN_PATTERN"
RULE_CONFLICT = "RULE_CONFLICT"
AMBIGUOUS_EVIDENCE = "AMBIGUOUS_EVIDENCE"

LEARNING_SIGNATURE_FIELDS = (
    "subsystem",
    "hardware_family",
    "adapter_family",
    "network_device_class",
    "configio_form",
    "catalog_signature",
    "catalog_authority_status",
    "direction_evidence_class",
    "lohi_shape",
    "bank_relationship_class",
    "interface",
    "hardware_topology_status",
    "adapter_identity_status",
    "failure_stage",
    "failure_reason",
)


def build_learning_signature(**kwargs: Any) -> dict[str, Any]:
    """Alias used by siteforge_learning.cluster_unknowns."""
    return build_failure_signature(**kwargs)

# Ordered identity fields for enriched learning signatures (site-independent).
LEARNING_SIGNATURE_FIELDS = (
    "subsystem",
    "hardware_family",
    "adapter_family",
    "network_device_class",
    "configio_form",
    "catalog_signature",
    "catalog_authority_status",
    "direction_evidence_class",
    "lohi_shape",
    "bank_relationship_class",
    "interface",
    "hardware_topology_status",
    "adapter_identity_status",
    "failure_stage",
    "failure_reason",
)


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


def _norm(v: Any) -> str:
    return str(v or "").strip().upper()


def _signature_id_from_parts(parts: dict[str, str]) -> str:
    raw = "|".join(f"{k}={parts.get(k) or ''}" for k in LEARNING_SIGNATURE_FIELDS)
    return "fs_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def build_learning_signature(
    *,
    subsystem: str = "",
    hardware_family: str = "",
    adapter_family: str = "",
    network_device_class: str = "",
    configio_form: str = "",
    catalog_signature: str = "",
    catalog_class: str = "",  # legacy alias → catalog_signature
    catalog_authority_status: str = "",
    direction_evidence_class: str = "",
    lohi_shape: str = "",
    bank_relationship_class: str = "",
    interface: str = "",
    hardware_topology_status: str = "",
    adapter_identity_status: str = "",
    failure_stage: str = "",
    failure_reason: str = "",
    classification: str = UNKNOWN_PATTERN,
) -> dict[str, Any]:
    """Build a site-independent learning signature.

    catalog_class is accepted as a legacy alias for catalog_signature.
    """
    cat_sig = _norm(catalog_signature) or _norm(catalog_class)
    parts = {
        "subsystem": _norm(subsystem),
        "hardware_family": _norm(hardware_family),
        "adapter_family": _norm(adapter_family),
        "network_device_class": _norm(network_device_class),
        "configio_form": _norm(configio_form),
        "catalog_signature": cat_sig,
        "catalog_authority_status": _norm(catalog_authority_status),
        "direction_evidence_class": _norm(direction_evidence_class),
        "lohi_shape": _norm(lohi_shape),
        "bank_relationship_class": _norm(bank_relationship_class),
        "interface": _norm(interface),
        "hardware_topology_status": _norm(hardware_topology_status),
        "adapter_identity_status": _norm(adapter_identity_status),
        "failure_stage": _norm(failure_stage),
        "failure_reason": _norm(failure_reason),
    }
    return {
        "signature_id": _signature_id_from_parts(parts),
        "classification": classification or UNKNOWN_PATTERN,
        **parts,
    }


def build_failure_signature(
    *,
    subsystem: str,
    hardware_family: str = "",
    configio_form: str = "",
    catalog_class: str = "",
    direction_evidence_class: str = "",
    bank_relationship_class: str = "",
    failure_reason: str = "",
    # enriched optional fields (backward compatible)
    adapter_family: str = "",
    network_device_class: str = "",
    catalog_signature: str = "",
    catalog_authority_status: str = "",
    lohi_shape: str = "",
    interface: str = "",
    hardware_topology_status: str = "",
    adapter_identity_status: str = "",
    failure_stage: str = "",
) -> dict[str, Any]:
    """Backward-compatible failure signature — delegates to enriched builder.

    Empty optional fields still participate in the hash so identical sparse
    PHYSICAL_RESOLUTION_FAILURE rows no longer all collapse to one id when
    callers supply richer dimensions.
    """
    return build_learning_signature(
        subsystem=subsystem,
        hardware_family=hardware_family,
        adapter_family=adapter_family,
        network_device_class=network_device_class,
        configio_form=configio_form,
        catalog_signature=catalog_signature or catalog_class,
        catalog_class=catalog_class,
        catalog_authority_status=catalog_authority_status,
        direction_evidence_class=direction_evidence_class,
        lohi_shape=lohi_shape,
        bank_relationship_class=bank_relationship_class,
        interface=interface,
        hardware_topology_status=hardware_topology_status,
        adapter_identity_status=adapter_identity_status,
        failure_stage=failure_stage or "PHYSICAL_RESOLUTION",
        failure_reason=failure_reason,
        classification=UNKNOWN_PATTERN,
    )

#!/usr/bin/env python3
"""CP4 Safety Evidence Adapter — NOT the final Site Forge SafetyModel.

Discovers safety-related identities via CP3 EStop (and related) edges only.
Does not assign Safety Zones from name prefixes.
"""
from __future__ import annotations

from typing import Any

from fortna_semantics.common import (
    AdapterResult,
    AdapterStatus,
    FactStatus,
    RuleClass,
    fact_from_edge,
    group_edges_by_record,
)


def run_safety_adapter(cp3: dict[str, Any]) -> AdapterResult:
    estop_edges = cp3["bySourceMenu"].get("EStop") or []
    by_rec = group_edges_by_record(estop_edges)
    devices = []
    facts = []
    diagnostics = []
    review_items = []

    for rec_i, cols in sorted(by_rec.items()):
        part = cols.get("Part")
        err = cols.get("Error")
        ident = (part or {}).get("sourceRawValue") or f"EStop#{rec_i}"
        entry = {
            "identity": ident,
            "kindHint": "ESTOP_PART_REF",
            "sourceRecord": rec_i,
            "part": _slot(part),
            "error": _slot(err),
            "safetyZoneRef": None,
            "safetyZoneStatus": FactStatus.UNKNOWN.value,
            "notes": [
                "Zone membership NOT inferred from names/prefixes.",
                "This is evidence only — not Site Forge SafetyModel.",
            ],
        }
        devices.append(entry)
        for e in (part, err):
            if not e:
                continue
            facts.append(
                fact_from_edge(
                    semantic_type="safety.estop_field",
                    identity=str(ident),
                    value=e.get("targetIdentity"),
                    edge=e,
                    status=FactStatus.PROVEN.value
                    if e.get("status") == "RESOLVED"
                    else FactStatus.REVIEW_REQUIRED.value,
                    interpretation_rule="estop_selection_is_safety_device_evidence",
                    provenance=RuleClass.RUN_PROVEN.value,
                ).to_dict()
            )
        review_items.append(
            {
                "identity": ident,
                "item": "safetyZoneRef",
                "status": FactStatus.REVIEW_REQUIRED.value,
                "reason": "zone_membership_not_established_by_cp3_estop_edges",
            }
        )

    # Validation targets — query only (not used to invent devices)
    validation_targets = [
        "CP2_MCR1",
        "CP3_MCR1",
        "T_2MCR1",
        "T_3MCR1",
        "CP2_ES",
        "CP2_ESR1",
        "CP2_ESR2",
        "CP2_ESR3",
        "CP3_ES",
        "CP3_ESR1",
        "CP3_ESR2",
        "CP3_ESR3",
        "CP3_ESR4",
        "CP3_ESR5",
        "2ES",
        "2MCR1",
        "ESLS125",
    ]
    # Search CP3 Conveyor/EStop identities
    found = {}
    all_ids = set()
    for key in cp3["byTargetIdentity"]:
        if "::" in key:
            all_ids.add(key.split("::", 1)[1])
    for d in devices:
        all_ids.add(d["identity"])
    for t in validation_targets:
        found[t] = {
            "presentInCp3Identities": t in all_ids,
            "status": FactStatus.PROVEN.value
            if t in all_ids
            else FactStatus.UNKNOWN.value,
        }

    status = AdapterStatus.REVIEW.value  # zone blanks => REVIEW by design
    if not devices:
        status = AdapterStatus.FAIL.value
        diagnostics.append({"kind": "NO_ESTOP_EVIDENCE"})
    elif all(d["part"]["status"] == FactStatus.PROVEN.value for d in devices[:10]):
        # Evidence present; membership still REVIEW
        status = AdapterStatus.REVIEW.value

    return AdapterResult(
        adapter="Safety",
        status=status,
        objects=devices,
        facts=facts,
        diagnostics=diagnostics + [{"kind": "REVIEW_ITEMS", "count": len(review_items)}],
        counts={
            "estopDevices": len(devices),
            "facts": len(facts),
            "reviewItems": len(review_items),
            "validationTargetsFound": sum(
                1 for v in found.values() if v["presentInCp3Identities"]
            ),
        },
        proofs={"validationTargets": found, "reviewItemsSample": review_items[:20]},
        notes=[
            "Safety Evidence Adapter ≠ Site Forge SafetyModel",
            "Unknown zone membership remains UNKNOWN/REVIEW — never permissive",
        ],
    )


def _slot(edge: dict[str, Any] | None) -> dict[str, Any]:
    if not edge:
        return {"raw": None, "targetIdentity": None, "status": FactStatus.UNKNOWN.value}
    return {
        "raw": edge.get("sourceRawValue"),
        "targetIdentity": edge.get("targetIdentity"),
        "targetMenu": edge.get("targetMenu"),
        "status": FactStatus.PROVEN.value
        if edge.get("status") == "RESOLVED"
        else FactStatus.UNKNOWN.value,
    }

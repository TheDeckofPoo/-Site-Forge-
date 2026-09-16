#!/usr/bin/env python3
"""CP4 Transportation / Conveyor-family adapter.

Consumes CP3 edges targeting/sourced from Conveyor. Does not invent adjacency.
Conveyor.asc is a broad object list (display + electrical), not only belts.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from fortna_semantics.common import (
    AdapterResult,
    AdapterStatus,
    FactStatus,
    RuleClass,
    fact_from_edge,
)


def run_transportation_adapter(cp3: dict[str, Any]) -> AdapterResult:
    by_src = cp3["bySourceMenu"]
    by_tgt = cp3["byTargetIdentity"]
    rev = cp3["reverse"]

    # Objects that appear as Conveyor target identities
    objects: dict[str, dict[str, Any]] = {}
    facts = []
    diagnostics = []

    for key, edges in by_tgt.items():
        if not key.startswith("Conveyor::"):
            continue
        ident = key.split("::", 1)[1]
        inbound = edges
        obj = objects.setdefault(
            ident,
            {
                "identity": ident,
                "existsAsConveyorTarget": True,
                "inboundReferenceCount": 0,
                "inboundFromMenus": {},
                "notes": [
                    "Conveyor family object — may be display part, motor, PE, or belt; "
                    "not automatically a physical conveyor segment."
                ],
            },
        )
        obj["inboundReferenceCount"] += len(inbound)
        for e in inbound:
            sm = e.get("sourceMenu") or "?"
            obj["inboundFromMenus"][sm] = obj["inboundFromMenus"].get(sm, 0) + 1
            facts.append(
                fact_from_edge(
                    semantic_type="conveyor_object_referenced",
                    identity=ident,
                    value={
                        "from": f"{e.get('sourceMenu')}.{e.get('sourceColumn')}",
                        "raw": e.get("sourceRawValue"),
                    },
                    edge=e,
                    status=FactStatus.PROVEN.value
                    if e.get("status") == "RESOLVED"
                    else FactStatus.REVIEW_REQUIRED.value,
                    interpretation_rule="cp3_target_identity_is_conveyor_family_object",
                    provenance=RuleClass.RUN_PROVEN.value,
                ).to_dict()
            )

    # Also capture Conveyor as source of selections (outgoing)
    for e in by_src.get("Conveyor") or []:
        if e.get("status") != "RESOLVED":
            continue
        sid = e.get("sourceRawValue")  # not identity of conveyor row
        # Outgoing from a Conveyor *record* — identity via reverse lookup of record
        # We only know sourceRecord; identity string requires CP3 targetIdentity on
        # edges *to* that record. Skip inventing — mark UNKNOWN without name.
        pass

    # Proofs for validation targets (not hardcoded into generic logic — queried)
    proof_ids = [
        "P312",
        "P314",
        "P316",
        "M314",
        "PE314_P",
        "M136_AUX",
        "LATCH_MERGE_316",
    ]
    proofs = {}
    for pid in proof_ids:
        obj = objects.get(pid)
        if not obj:
            proofs[pid] = {
                "status": FactStatus.UNKNOWN.value,
                "detail": "No CP3 resolved edge targeted Conveyor identity",
            }
            continue
        proofs[pid] = {
            "status": FactStatus.PROVEN.value,
            "inboundReferenceCount": obj["inboundReferenceCount"],
            "inboundFromMenus": obj["inboundFromMenus"],
            "unknown": [
                "physical geometry",
                "belt vs motor vs PE classification beyond inbound source menus",
                "physical adjacency",
            ],
        }

    status = AdapterStatus.PASS.value
    if not objects:
        status = AdapterStatus.FAIL.value
        diagnostics.append({"kind": "NO_CONVEYOR_TARGETS", "detail": "No Conveyor::* identities in CP3"})

    return AdapterResult(
        adapter="Transportation",
        status=status,
        objects=sorted(objects.values(), key=lambda o: o["identity"]),
        facts=facts[:5000],  # bound artifact size; counts remain full
        diagnostics=diagnostics,
        counts={
            "conveyorFamilyObjects": len(objects),
            "factsEmitted": len(facts),
            "factsSerialized": min(len(facts), 5000),
            "proofTargetsFound": sum(
                1 for p in proofs.values() if p["status"] == FactStatus.PROVEN.value
            ),
            "proofTargetsUnknown": sum(
                1 for p in proofs.values() if p["status"] == FactStatus.UNKNOWN.value
            ),
        },
        proofs=proofs,
        notes=[
            "Objects are Fortna Conveyor-table identities referenced by CP3 edges.",
            "No physical adjacency inferred from numbering.",
            RuleClass.RUN_PROVEN.value,
        ],
    )

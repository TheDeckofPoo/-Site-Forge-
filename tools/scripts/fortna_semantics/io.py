#!/usr/bin/env python3
"""CP4 I/O Evidence Adapter — Fortna-proven associations only.

Does not replace Site Forge HardwareIOModel. No endpoint guessing.
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

# Tables that often carry I/O-ish selections in Fortna schemas (discovered via CP3 menus present)
IO_SOURCE_MENUS = (
    "Configio",
    "Inpoints",
    "Outpoints",
    "AnalogOutputs",
    "EIPModules",
    "EIPAdapters",
)


def run_io_adapter(cp3: dict[str, Any]) -> AdapterResult:
    objects = []
    facts = []
    diagnostics = []
    menus_exercised = []

    for menu in IO_SOURCE_MENUS:
        edges = cp3["bySourceMenu"].get(menu) or []
        if not edges:
            continue
        menus_exercised.append(menu)
        by_rec = group_edges_by_record(edges)
        for rec_i, cols in sorted(by_rec.items()):
            # Collect Conveyor / Machine associations only from resolved edges
            conveyor_refs = []
            machine_refs = []
            other_refs = []
            for cname, e in cols.items():
                if e.get("status") != "RESOLVED":
                    continue
                slot = {
                    "column": cname,
                    "raw": e.get("sourceRawValue"),
                    "targetMenu": e.get("targetMenu"),
                    "targetIdentity": e.get("targetIdentity"),
                    "cp3Edge": {
                        "sourceMenu": e.get("sourceMenu"),
                        "sourceRecord": e.get("sourceRecord"),
                        "sourceColumn": e.get("sourceColumn"),
                    },
                }
                if e.get("targetMenu") == "Conveyor":
                    conveyor_refs.append(slot)
                elif e.get("targetMenu") == "Machine":
                    machine_refs.append(slot)
                else:
                    other_refs.append(slot)
                facts.append(
                    fact_from_edge(
                        semantic_type="io.selection_ref",
                        identity=f"{menu}#{rec_i}",
                        value=e.get("targetIdentity"),
                        edge=e,
                        status=FactStatus.PROVEN.value,
                        interpretation_rule="io_table_selection_is_fortna_association",
                        provenance=RuleClass.RUN_PROVEN.value,
                    ).to_dict()
                )
            objects.append(
                {
                    "sourceMenu": menu,
                    "sourceRecord": rec_i,
                    "conveyorAssociations": conveyor_refs,
                    "machineAssociations": machine_refs,
                    "otherAssociations": other_refs[:20],
                    "physicalAddress": None,
                    "physicalAddressStatus": FactStatus.UNKNOWN.value,
                    "engineerAlias": None,
                    "notes": [
                        "Physical endpoint address not invented.",
                        "Engineer alias distinct from Fortna identity when unknown.",
                    ],
                }
            )

    # Also: Conveyor objects that look I/O-ish only as UNKNOWN classification
    # (no name-based guessing of ownership)

    status = AdapterStatus.PASS.value if menus_exercised else AdapterStatus.REVIEW.value
    if not menus_exercised:
        diagnostics.append(
            {
                "kind": "NO_IO_SOURCE_MENUS_IN_CP3",
                "detail": "None of Configio/Inpoints/Outpoints/... produced CP3 record edges",
            }
        )
        status = AdapterStatus.REVIEW.value

    # If associations exist but addresses unknown → REVIEW is acceptable
    if objects and all(o.get("physicalAddressStatus") == FactStatus.UNKNOWN.value for o in objects):
        status = AdapterStatus.REVIEW.value

    return AdapterResult(
        adapter="IO",
        status=status,
        objects=objects[:500],
        facts=facts[:3000],
        diagnostics=diagnostics,
        counts={
            "ioSourceMenusExercised": len(menus_exercised),
            "menus": menus_exercised,
            "recordsTouched": len(objects),
            "facts": len(facts),
            "conveyorAssociations": sum(
                len(o.get("conveyorAssociations") or []) for o in objects
            ),
        },
        proofs={
            "menusExercised": menus_exercised,
            "sample": objects[:5],
        },
        notes=[
            "I/O Evidence Adapter ≠ HardwareIOModel",
            "No duplicate ownership invention",
        ],
    )

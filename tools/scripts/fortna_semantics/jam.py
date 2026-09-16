#!/usr/bin/env python3
"""CP4 Jam adapter — Jamcheck/Jamzones evidence via CP3 only."""
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

JAM_COLS = {
    "Sensor_Name",
    "Timer_Name",
    "Error_Name",
    "Conveyor_Name",
    "Zone",
    "Jam_Owner",
    "Motor Under Jam Eye",
    "ClearJamSignal",
    "L2_ClearJamSignal",
}


def run_jam_adapter(cp3: dict[str, Any]) -> AdapterResult:
    edges = cp3["bySourceMenu"].get("Jamcheck") or []
    by_rec = group_edges_by_record(edges)
    objects = []
    facts = []
    diagnostics = []
    complete = 0

    for rec_i, cols in sorted(by_rec.items()):
        entry = {
            "sourceRecord": rec_i,
            "sensor": _slot(cols.get("Sensor_Name")),
            "timer": _slot(cols.get("Timer_Name")),
            "error": _slot(cols.get("Error_Name")),
            "conveyorObject": _slot(cols.get("Conveyor_Name")),
            "zone": _slot(cols.get("Zone")),
            "machine": _slot(cols.get("Jam_Owner")),
            "motorUnderJamEye": _slot(cols.get("Motor Under Jam Eye")),
            "clearJamSignal": _slot(cols.get("ClearJamSignal")),
            "l2ClearJamSignal": _slot(cols.get("L2_ClearJamSignal")),
            "notes": ["No physical sensor placement inferred."],
        }
        populated = [
            k
            for k, v in entry.items()
            if isinstance(v, dict) and v.get("status") == FactStatus.PROVEN.value
        ]
        entry["provenFieldCount"] = len(populated)
        if len(populated) >= 5:
            complete += 1
        objects.append(entry)
        for cname, edge in cols.items():
            if cname not in JAM_COLS:
                continue
            facts.append(
                fact_from_edge(
                    semantic_type=f"jam.{cname}",
                    identity=f"Jamcheck#{rec_i}",
                    value=edge.get("targetIdentity"),
                    edge=edge,
                    status=FactStatus.PROVEN.value
                    if edge.get("status") == "RESOLVED"
                    else FactStatus.UNKNOWN.value,
                    interpretation_rule="jamcheck_selection_is_fortna_jam_ref",
                ).to_dict()
            )

    # Zones seen as targets
    zones = sorted(
        {
            k.split("::", 1)[1]
            for k in cp3["byTargetIdentity"]
            if k.startswith("Jamzones::")
        }
    )

    proofs = {
        "completeRecordsSample": [
            o
            for o in objects
            if o.get("provenFieldCount", 0) >= 5
        ][:5],
        "completeRecordCount": complete,
        "jamzonesIdentitiesSample": zones[:20],
        "jamzonesIdentityCount": len(zones),
    }

    status = AdapterStatus.PASS.value if complete >= 3 else AdapterStatus.REVIEW.value
    if not objects:
        status = AdapterStatus.FAIL.value
        diagnostics.append({"kind": "NO_JAMCHECK_EDGES"})

    return AdapterResult(
        adapter="Jam",
        status=status,
        objects=objects[:200],  # bound size; counts full
        facts=facts[:3000],
        diagnostics=diagnostics,
        counts={
            "jamcheckRecordsTouched": len(objects),
            "completeRecords": complete,
            "jamzonesIdentities": len(zones),
            "facts": len(facts),
        },
        proofs=proofs,
        notes=["Jam adapter isolates jam semantics from Merge/Transportation."],
    )


def _slot(edge: dict[str, Any] | None) -> dict[str, Any]:
    if not edge:
        return {"raw": None, "targetIdentity": None, "status": FactStatus.UNKNOWN.value}
    st = FactStatus.PROVEN.value if edge.get("status") == "RESOLVED" else FactStatus.UNKNOWN.value
    if (edge.get("sourceRawValue") or "").strip().upper() in {"INVALID", "", "N/A", "NONE"}:
        st = FactStatus.UNKNOWN.value
    return {
        "raw": edge.get("sourceRawValue"),
        "targetIdentity": edge.get("targetIdentity"),
        "targetMenu": edge.get("targetMenu"),
        "status": st,
    }

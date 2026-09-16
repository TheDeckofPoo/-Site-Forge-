#!/usr/bin/env python3
"""CP4 Mtrchain adapter — startup/display relationships, not physical topology."""
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


# Columns interpreted as Mtrchain relationships (schema names from RUN/CP3)
MTR_REL_COLS = {
    "Motor_Ndx",
    "Motor_Chained1",
    "Motor_Chained2",
    "Motor_Chained3",
    "Motor_Chained4",
    "Motor_Chained5",
    "Motor_Chained6",
    "Motor_Chained7",
    "Motor_Chained8",
    "Motor_Chained9",
    "Motor_Chained10",
    "Motor_Aux",
    "Enabled",
    "GoUntil",
}


def run_mtrchain_adapter(cp3: dict[str, Any]) -> AdapterResult:
    edges = cp3["bySourceMenu"].get("Mtrchain") or []
    by_rec = group_edges_by_record(edges)
    objects = []
    facts = []
    diagnostics = []

    for rec_i, cols in sorted(by_rec.items()):
        # Prefer Motor_Ndx identity when present; else first resolved target as soft id
        motor_ndx = cols.get("Motor_Ndx")
        identity = None
        if motor_ndx and motor_ndx.get("sourceRawValue"):
            identity = str(motor_ndx.get("sourceRawValue"))
        if not identity:
            identity = f"Mtrchain#{rec_i}"

        entry = {
            "identity": identity,
            "sourceRecord": rec_i,
            "motorNdx": _slot(cols.get("Motor_Ndx")),
            "chained": [],
            "motorAux": _slot(cols.get("Motor_Aux")),
            "enabled": _slot(cols.get("Enabled")),
            "goUntil": _slot(cols.get("GoUntil")),
            "semanticNotes": [
                "SOURCE_PROVEN Fortna meaning: motor relationships / startup sequence "
                "and display P-part coloring — not automatically physical conveyor topology."
            ],
        }
        for i in range(1, 11):
            cname = f"Motor_Chained{i}"
            if cname in cols:
                entry["chained"].append(_slot(cols[cname]) | {"slot": i})

        # Facts
        for cname, edge in cols.items():
            if cname not in MTR_REL_COLS:
                continue
            raw = edge.get("sourceRawValue")
            st = FactStatus.PROVEN.value
            diags = []
            if edge.get("status") != "RESOLVED":
                if (raw or "").strip().upper() in {"", "INVALID", "N/A", "NONE"}:
                    st = FactStatus.UNKNOWN.value
                    diags.append("empty_or_invalid_selection")
                else:
                    st = FactStatus.REVIEW_REQUIRED.value
            facts.append(
                fact_from_edge(
                    semantic_type=f"mtrchain.{cname}",
                    identity=identity,
                    value=edge.get("targetIdentity"),
                    edge=edge,
                    status=st,
                    interpretation_rule="mtrchain_column_is_fortna_control_or_display_ref",
                    provenance=RuleClass.SOURCE_PROVEN.value
                    if st == FactStatus.PROVEN.value
                    else RuleClass.RUN_PROVEN.value,
                    diagnostics=diags,
                ).to_dict()
            )
        objects.append(entry)

    # PLC2 validation target M314 (query, not hard-coded into resolution)
    m314 = next((o for o in objects if o["identity"] == "M314"), None)
    proofs = {"M314": _proof_m314(m314)}

    status = AdapterStatus.PASS.value if objects else AdapterStatus.FAIL.value
    if not m314:
        diagnostics.append(
            {
                "kind": "VALIDATION_TARGET_MISSING",
                "identity": "M314",
                "detail": "No Mtrchain entry with Motor_Ndx/identity M314 in CP3 edges",
            }
        )
        # Don't fail whole adapter if other entries exist — REVIEW for missing validation target
        if objects:
            status = AdapterStatus.REVIEW.value

    # If M314 present but proof incomplete → REVIEW
    if m314 and proofs["M314"]["status"] != FactStatus.PROVEN.value:
        status = AdapterStatus.REVIEW.value

    return AdapterResult(
        adapter="Mtrchain",
        status=status,
        objects=objects,
        facts=facts,
        diagnostics=diagnostics,
        counts={
            "entries": len(objects),
            "facts": len(facts),
            "chainedSlotsPopulated": sum(
                1 for o in objects for c in o["chained"] if c.get("raw") not in (None, "", "INVALID")
            ),
        },
        proofs=proofs,
        notes=[
            "Separates Fortna startup/control refs from physical topology.",
            "GoUntil INVALID remains UNKNOWN, not fabricated.",
        ],
    )


def _slot(edge: dict[str, Any] | None) -> dict[str, Any]:
    if not edge:
        return {"raw": None, "targetIdentity": None, "status": FactStatus.UNKNOWN.value, "cp3EdgeKey": None}
    raw = edge.get("sourceRawValue")
    st = FactStatus.PROVEN.value if edge.get("status") == "RESOLVED" else FactStatus.UNKNOWN.value
    if (raw or "").strip().upper() in {"INVALID", "N/A", "NONE", ""}:
        st = FactStatus.UNKNOWN.value
    return {
        "raw": raw,
        "targetIdentity": edge.get("targetIdentity"),
        "targetRecord": edge.get("targetRecord"),
        "status": st,
        "cp3EdgeKey": f"{edge.get('sourceMenu')}#{edge.get('sourceRecord')}.{edge.get('sourceColumn')}",
        "resolutionMode": edge.get("resolutionMode"),
    }


def _proof_m314(entry: dict[str, Any] | None) -> dict[str, Any]:
    if not entry:
        return {"status": FactStatus.UNKNOWN.value, "detail": "entry_missing"}
    need = {
        "Motor_Ndx": entry["motorNdx"],
        "Motor_Chained1": next((c for c in entry["chained"] if c.get("slot") == 1), {}),
        "Motor_Aux": entry["motorAux"],
        "Enabled": entry["enabled"],
        "GoUntil": entry["goUntil"],
    }
    expect = {
        "Motor_Ndx": "M314",
        "Motor_Chained1": "P314",
        "Motor_Aux": "LATCH_MERGE_316",
        "Enabled": "M136_AUX",
    }
    checks = {}
    ok = True
    for k, exp in expect.items():
        got = (need.get(k) or {}).get("raw")
        checks[k] = {"expected": exp, "got": got, "pass": got == exp}
        ok = ok and got == exp
    gu = (need.get("GoUntil") or {}).get("raw")
    checks["GoUntil"] = {
        "expected": "INVALID_or_empty",
        "got": gu,
        "pass": (gu or "").strip().upper() in {"INVALID", "", "N/A", "NONE"},
    }
    return {
        "status": FactStatus.PROVEN.value if ok else FactStatus.REVIEW_REQUIRED.value,
        "sourceRecord": entry.get("sourceRecord"),
        "checks": checks,
    }

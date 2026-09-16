#!/usr/bin/env python3
"""CP4 Merge adapter — independent of Transportation/Mtrchain internals.

Consumes CP3 MergeBoss / MergeInputs edges. Logical lane ≠ release conveyor.
"""
from __future__ import annotations

import re
from typing import Any

from fortna_semantics.common import (
    AdapterResult,
    AdapterStatus,
    FactStatus,
    RuleClass,
    fact_from_edge,
    group_edges_by_record,
)


def _merge_class(name: str) -> str:
    u = name.upper()
    if "SPUR" in u:
        return "SPUR"
    if "3-1" in u or "3_1" in u or "3TO1" in u:
        return "3-1"
    if "2-1" in u or "2_1" in u or "2TO1" in u:
        return "2-1"
    return "UNKNOWN"


def _logical_lane_from_name(lane_name: str | None) -> str | None:
    """Deterministic parse of Fortna MergeInputs Name tokens like LANE1_P136.

    DETERMINISTIC_DERIVATION from observed Fortna naming — not topology.
    """
    if not lane_name:
        return None
    m = re.search(r"(P\d+(?:_[A-Z0-9]+)?)", lane_name.upper().replace("LANE1_", "").replace("LANE2_", "").replace("LANE3_", ""))
    # Prefer explicit P### after LANE#_
    m2 = re.search(r"LANE\d+_(P\d+(?:_[A-Z0-9]+)?)", lane_name.upper())
    if m2:
        return m2.group(1)
    if m:
        return m.group(1)
    return None


def run_merge_adapter(cp3: dict[str, Any], *, mtrchain_public: dict[str, Any] | None = None) -> AdapterResult:
    """mtrchain_public is optional immutable AdapterResult.to_dict() for derived chains."""
    mi_edges = cp3["bySourceMenu"].get("MergeInputs") or []
    mb_edges = cp3["bySourceMenu"].get("MergeBoss") or []
    by_rec = group_edges_by_record(mi_edges)

    # Discover MergeBoss identities from resolved MergeInputs.MergeBoss edges
    bosses: dict[str, dict[str, Any]] = {}
    facts: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    for rec_i, cols in sorted(by_rec.items()):
        boss_e = cols.get("MergeBoss")
        if not boss_e:
            continue
        boss_id = boss_e.get("sourceRawValue") or boss_e.get("targetIdentity")
        if not boss_id:
            continue
        boss = bosses.setdefault(
            str(boss_id),
            {
                "identity": str(boss_id),
                "mergeClass": _merge_class(str(boss_id)),
                "lanes": [],
                "evidence": [],
            },
        )
        # Lane name is not always a CP3 selection edge — often STRING on MergeInputs.
        # Without re-parsing ASC, we only know lane via MergeRoute selection if present,
        # or via reverse: we cannot invent Name. Use MergeRoute targetIdentity as lane label
        # when available; else MergeInputs#record.
        route = cols.get("MergeRoute")
        lane_label = None
        if route and route.get("sourceRawValue"):
            lane_label = str(route.get("sourceRawValue"))
        lane_id = _logical_lane_from_name(lane_label) if lane_label else None
        if not lane_id and lane_label and lane_label.upper().startswith("LANE"):
            lane_id = _logical_lane_from_name(lane_label)
        presence = cols.get("Presense") or cols.get("Presence")
        release = cols.get("ReleaseIO")

        lane = {
            "sourceRecord": rec_i,
            "laneLabel": lane_label,
            "logicalIdentity": lane_id,
            "logicalIdentityStatus": FactStatus.DERIVED.value
            if lane_id
            else FactStatus.UNKNOWN.value,
            "presence": _ref(presence),
            "releaseIO": _ref(release),
            "mergeBoss": _ref(boss_e),
            "criticalDistinction": "logical_lane_identity_ne_physical_release_conveyor",
        }

        # Optional derived chain ReleaseIO → Mtrchain → display P (public mtrchain only)
        if (
            mtrchain_public
            and release
            and release.get("status") == "RESOLVED"
            and release.get("targetIdentity")
        ):
            mid = release.get("targetIdentity")
            mtr_objs = {
                o.get("identity"): o for o in (mtrchain_public.get("objects") or [])
            }
            mtr = mtr_objs.get(mid)
            if mtr:
                chained1 = None
                for c in mtr.get("chained") or []:
                    if c.get("slot") == 1:
                        chained1 = c
                        break
                lane["derivedReleaseChain"] = {
                    "status": FactStatus.DERIVED.value,
                    "rule": "MergeInputs.ReleaseIO -> motor identity -> Mtrchain.Motor_Chained1",
                    "releaseIO": mid,
                    "mtrchainIdentity": mid,
                    "motorChained1": (chained1 or {}).get("raw"),
                    "meaning": (
                        "Fortna Mtrchain startup/display relationship — "
                        "NOT automatically physical conveyor topology"
                    ),
                    "provenance": RuleClass.DETERMINISTIC_DERIVATION.value,
                }

        boss["lanes"].append(lane)
        for e in (boss_e, presence, release, route):
            if not e:
                continue
            facts.append(
                fact_from_edge(
                    semantic_type="merge.lane_field",
                    identity=str(boss_id),
                    value=e.get("targetIdentity"),
                    edge=e,
                    status=FactStatus.PROVEN.value
                    if e.get("status") == "RESOLVED"
                    else FactStatus.REVIEW_REQUIRED.value,
                    interpretation_rule="mergeinputs_selection_is_fortna_merge_ref",
                ).to_dict()
            )

    # Also list MergeBoss table identities seen as targets
    for key, edges in cp3["byTargetIdentity"].items():
        if key.startswith("MergeBoss::"):
            ident = key.split("::", 1)[1]
            bosses.setdefault(
                ident,
                {
                    "identity": ident,
                    "mergeClass": _merge_class(ident),
                    "lanes": [],
                    "evidence": ["seen_as_cp3_target_only"],
                },
            )

    objects = sorted(bosses.values(), key=lambda o: o["identity"])

    # Proofs (validation queries)
    proofs = {
        "MERGE_316_SPUR": _proof_spur(bosses.get("MERGE_316_SPUR"), expect=[
            ("P136", "EZPE136_P1", "SSVEZPE136_P1"),
            ("P312", "PE314_P", "M314"),
        ]),
        "MERGE_324_SPUR": _proof_spur(bosses.get("MERGE_324_SPUR"), expect=None),
        "MERGE_406_3-1": {
            "present": "MERGE_406_3-1" in bosses,
            "mergeClass": (bosses.get("MERGE_406_3-1") or {}).get("mergeClass"),
            "laneCount": len((bosses.get("MERGE_406_3-1") or {}).get("lanes") or []),
        },
        "MERGE_400_2-1": {
            "present": "MERGE_400_2-1" in bosses,
            "mergeClass": (bosses.get("MERGE_400_2-1") or {}).get("mergeClass"),
            "laneCount": len((bosses.get("MERGE_400_2-1") or {}).get("lanes") or []),
        },
    }

    status = AdapterStatus.PASS.value
    if not objects:
        status = AdapterStatus.FAIL.value
        diagnostics.append({"kind": "NO_MERGE_OBJECTS"})
    else:
        p316 = proofs["MERGE_316_SPUR"]
        if p316.get("status") == FactStatus.REVIEW_REQUIRED.value:
            status = AdapterStatus.REVIEW.value
        if p316.get("status") == FactStatus.UNKNOWN.value and "MERGE_316_SPUR" not in bosses:
            # Site without this boss — not a FAIL for generic adapter
            pass

    return AdapterResult(
        adapter="Merge",
        status=status,
        objects=objects,
        facts=facts,
        diagnostics=diagnostics,
        counts={
            "mergeBossObjects": len(objects),
            "lanes": sum(len(o.get("lanes") or []) for o in objects),
            "byClass": {
                c: sum(1 for o in objects if o.get("mergeClass") == c)
                for c in ("SPUR", "2-1", "3-1", "UNKNOWN")
            },
        },
        proofs=proofs,
        notes=[
            "logical lane identity != physical release conveyor",
            "Mtrchain chain on ReleaseIO is DERIVED evidence only when provided",
        ],
    )


def _ref(edge: dict[str, Any] | None) -> dict[str, Any] | None:
    if not edge:
        return None
    return {
        "raw": edge.get("sourceRawValue"),
        "targetIdentity": edge.get("targetIdentity"),
        "targetRecord": edge.get("targetRecord"),
        "status": FactStatus.PROVEN.value
        if edge.get("status") == "RESOLVED"
        else FactStatus.REVIEW_REQUIRED.value,
        "cp3": {
            "sourceMenu": edge.get("sourceMenu"),
            "sourceRecord": edge.get("sourceRecord"),
            "sourceColumn": edge.get("sourceColumn"),
        },
    }


def _proof_spur(boss: dict[str, Any] | None, expect: list[tuple[str, str, str]] | None) -> dict[str, Any]:
    if not boss:
        return {"status": FactStatus.UNKNOWN.value, "detail": "boss_not_present"}
    lanes = boss.get("lanes") or []
    out = {"status": FactStatus.PROVEN.value, "mergeClass": boss.get("mergeClass"), "lanes": lanes}
    if expect is None:
        out["status"] = FactStatus.PROVEN.value if lanes else FactStatus.REVIEW_REQUIRED.value
        return out
    # Prefer logical-id match; fall back to presence+release pair match (CP3-proven fields)
    by_logic = {ln.get("logicalIdentity"): ln for ln in lanes}
    by_pr = {
        (
            (ln.get("presence") or {}).get("raw"),
            (ln.get("releaseIO") or {}).get("raw"),
        ): ln
        for ln in lanes
    }
    checks = []
    ok = True
    for logic, pres, rel in expect:
        ln = by_logic.get(logic) or by_pr.get((pres, rel))
        if not ln:
            checks.append({"logical": logic, "pass": False, "detail": "lane_missing"})
            ok = False
            continue
        got_p = (ln.get("presence") or {}).get("raw")
        got_r = (ln.get("releaseIO") or {}).get("raw")
        good = got_p == pres and got_r == rel
        # Logical id is DERIVED when present; proof can still PASS on presence/release alone
        checks.append(
            {
                "logicalExpected": logic,
                "logicalGot": ln.get("logicalIdentity"),
                "pass": good,
                "presence": got_p,
                "releaseIO": got_r,
                "expectedPresence": pres,
                "expectedReleaseIO": rel,
            }
        )
        ok = ok and good
    out["checks"] = checks
    out["status"] = FactStatus.PROVEN.value if ok else FactStatus.REVIEW_REQUIRED.value
    return out

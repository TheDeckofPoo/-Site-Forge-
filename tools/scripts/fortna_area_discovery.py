#!/usr/bin/env python3
"""Evidence-based Engineering Area candidate discovery.

Never copies finished-PLC Area names into generation.
Weak candidates stay ENGINEER_REQUIRED / suggested — never silently applied.

Confidence:
  CONFIRMED | HIGH_CONFIDENCE | CANDIDATE | ENGINEER_REQUIRED
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from fortna_site_model import (
    INCLUDED,
    PROV_ENGINEER,
    PROV_RUN_EXPLICIT,
    _clean,
    merge_table_rows,
    normalize_name,
)

CONFIRMED = "CONFIRMED"
HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
CANDIDATE = "CANDIDATE"
ENGINEER_REQUIRED = "ENGINEER_REQUIRED"


def _blank(v: Any) -> bool:
    s = _clean(v)
    return not s or s.upper() in {"N/A", "INVALID", "NONE", "NA"}


def discover_area_candidates(
    run_dir,
    machine: str,
    site: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build AreaCandidate list from RUN + SiteModel evidence only."""
    from pathlib import Path

    run_dir = Path(run_dir)
    fortna = run_dir / "FORTNA"
    site = site or {}
    candidates: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    # Always emit provisional controller-scoped placeholder (not a plant Area).
    candidates.append(
        {
            "id": f"area_candidate:{machine}_Area",
            "proposed_name": f"{machine}_Area",
            "confidence": ENGINEER_REQUIRED,
            "proposed_membership": [
                e.get("raw_name") or e.get("normalized_name")
                for e in (site.get("equipment") or [])
                if e.get("inclusion") == INCLUDED
            ],
            "evidence": [
                {
                    "kind": "controller_scope_provisional",
                    "detail": f"MACHINENAME={machine}; not a plant Engineering Area",
                    "provenance": PROV_RUN_EXPLICIT,
                }
            ],
            "conflicts": [],
            "engineer_required": True,
            "suggested": True,
            "auto_apply": False,
            "note": "Prefer Suggested Areas UI; engineer must rename/split",
        }
    )

    # StartStop zones → grouping hints (not Areas)
    for z in (site.get("operational_groups") or {}).get("startstop_zones") or []:
        name = z.get("raw_name") or z.get("normalized_name")
        if _blank(name):
            continue
        candidates.append(
            {
                "id": f"area_hint:startstop:{normalize_name(name)}",
                "proposed_name": str(name),
                "confidence": CANDIDATE,
                "proposed_membership": [],
                "evidence": [
                    {
                        "kind": "startstop_zone_hint",
                        "table": "StartStopZones.asc",
                        "detail": "Start/Stop zone ≠ Engineering Area",
                        "provenance": PROV_RUN_EXPLICIT,
                    }
                ],
                "conflicts": ["must_not_auto_promote_zone_to_area"],
                "engineer_required": True,
                "suggested": True,
                "auto_apply": False,
                "group_type": "StartStopZone",
            }
        )

    # Jamzones Zone Owner → ownership hints
    owner_members: dict[str, list[str]] = defaultdict(list)
    if fortna.is_dir() and list(fortna.glob("Jamzones.asc*")):
        merged = merge_table_rows(fortna, "Jamzones.asc", machine)
        for item in merged.get("rows") or []:
            row = item.get("row") or {}
            owner = _clean(row.get("Zone Owner") or row.get("Zone Owner ") or row.get("ZoneOwner"))
            zone = _clean(row.get("Zone Name") or row.get("Name"))
            if _blank(owner) or _blank(zone):
                continue
            owner_members[owner].append(zone)
        for owner, zones in sorted(owner_members.items()):
            candidates.append(
                {
                    "id": f"area_hint:jam_owner:{normalize_name(owner)}",
                    "proposed_name": owner,
                    "confidence": CANDIDATE,
                    "proposed_membership": [],
                    "evidence": [
                        {
                            "kind": "jamzone_owner_hint",
                            "table": "Jamzones.asc",
                            "zones": zones[:20],
                            "count": len(zones),
                            "detail": "May indicate process ownership, not Engineering Area",
                            "provenance": PROV_RUN_EXPLICIT,
                        }
                    ],
                    "conflicts": [],
                    "engineer_required": True,
                    "suggested": True,
                    "auto_apply": False,
                    "group_type": "ProcessOwnerHint",
                }
            )

    # Mtrchain Stop Zone hints
    stop_zones: Counter[str] = Counter()
    if fortna.is_dir() and list(fortna.glob("Mtrchain.asc*")):
        merged = merge_table_rows(fortna, "Mtrchain.asc", machine)
        for item in merged.get("rows") or []:
            row = item.get("row") or {}
            sz = _clean(row.get("Stop Zone") or row.get("StopZone"))
            if not _blank(sz):
                stop_zones[sz] += 1
        for sz, n in stop_zones.most_common(15):
            candidates.append(
                {
                    "id": f"area_hint:mtrchain_stop:{normalize_name(sz)}",
                    "proposed_name": sz,
                    "confidence": CANDIDATE,
                    "proposed_membership": [],
                    "evidence": [
                        {
                            "kind": "mtrchain_stop_zone_hint",
                            "table": "Mtrchain.asc",
                            "count": n,
                            "detail": "Stop Zone may align with StartStop; not auto Area",
                            "provenance": PROV_RUN_EXPLICIT,
                        }
                    ],
                    "conflicts": [],
                    "engineer_required": True,
                    "suggested": True,
                    "auto_apply": False,
                    "group_type": "MotorStopZoneHint",
                }
            )

    # Sorter entity names as grouping hints only
    for s in site.get("sorters") or []:
        name = s.get("raw_name") or s.get("normalized_name")
        if _blank(name):
            continue
        candidates.append(
            {
                "id": f"area_hint:sorter:{normalize_name(name)}",
                "proposed_name": f"SorterGroup_{name}",
                "confidence": CANDIDATE,
                "proposed_membership": [],
                "evidence": [
                    {
                        "kind": "sorter_grouping_hint",
                        "table": "Sorters.asc",
                        "sorter": name,
                        "detail": "Sorter entity is not an Engineering Area",
                        "provenance": s.get("provenance") or PROV_RUN_EXPLICIT,
                    }
                ],
                "conflicts": [],
                "engineer_required": True,
                "suggested": True,
                "auto_apply": False,
                "group_type": "SorterHint",
            }
        )

    # Detect name collisions between provisional Area and zone hints
    names = Counter(c.get("proposed_name") for c in candidates)
    for c in candidates:
        n = c.get("proposed_name")
        if names[n] > 1:
            c.setdefault("conflicts", []).append("duplicate_candidate_name")
            conflicts.append({"name": n, "count": names[n]})

    confirmed = [c for c in candidates if c["confidence"] == CONFIRMED]
    high = [c for c in candidates if c["confidence"] == HIGH_CONFIDENCE]
    cand = [c for c in candidates if c["confidence"] == CANDIDATE]
    eng = [c for c in candidates if c["confidence"] == ENGINEER_REQUIRED]

    return {
        "machine": machine,
        "policy": [
            "Do not copy finished-PLC Area names into generation",
            "Never silently turn a weak candidate into an Area",
            "Prefer Suggested Areas for engineer review",
            "N/A alone is not Area evidence",
        ],
        "counts": {
            "CONFIRMED": len(confirmed),
            "HIGH_CONFIDENCE": len(high),
            "CANDIDATE": len(cand),
            "ENGINEER_REQUIRED": len(eng),
            "suggested": sum(1 for c in candidates if c.get("suggested")),
        },
        "candidates": candidates,
        "conflicts": conflicts,
        "inferred_high_confidence": len(confirmed) + len(high),
        "suggested": len(cand) + sum(1 for c in eng if c.get("suggested")),
        "engineer_required": len(eng),
    }


def apply_confirmed_areas_only(
    site: dict[str, Any],
    discovery: dict[str, Any],
) -> dict[str, Any]:
    """Only CONFIRMED candidates may auto-write area_id. Others stay suggested."""
    applied = []
    for c in discovery.get("candidates") or []:
        if c.get("confidence") != CONFIRMED or not c.get("auto_apply"):
            continue
        name = c.get("proposed_name")
        for mem in c.get("proposed_membership") or []:
            nn = normalize_name(mem)
            for eq in site.get("equipment") or []:
                if normalize_name(eq.get("normalized_name") or "") == nn:
                    eq["area_id"] = name
                    eq.setdefault("evidence", []).append(
                        {"kind": "area_confirmed_applied", "area": name}
                    )
                    applied.append(nn)
    return {"applied_membership": applied, "count": len(applied)}

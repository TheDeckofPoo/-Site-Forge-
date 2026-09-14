#!/usr/bin/env python3
"""Regression: Apply-to-Autogen must not wipe engineer Transport Areas.

Simulates:
  Auto Build seed → engineer creates TEST_A / TEST_B → assigns conveyors
  → Apply to workbook → Areas and assignments survive.

Does NOT clear siteforge.transportBuild.* (JS-side); this tests the Python
apply_graph_to_workbook path that previously restored rows too aggressively.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_transport_graph import apply_graph_to_workbook  # noqa: E402


def _hash_areas(wb: dict) -> str:
    areas = sorted(
        [
            {
                "name": str(a.get("name") or "").strip(),
                "count": int(a.get("conveyor_count") or 0),
            }
            for a in (wb.get("areas") or [])
            if str(a.get("name") or "").strip()
        ],
        key=lambda x: x["name"],
    )
    conv = sorted(
        [
            {
                "tag": str(r.get("conveyor") or "").strip().upper(),
                "area": str(r.get("main_area") or "").strip(),
            }
            for r in (wb.get("conveyors") or [])
            if str(r.get("conveyor") or "").strip()
        ],
        key=lambda x: x["tag"],
    )
    raw = json.dumps({"areas": areas, "conv": conv}, sort_keys=True)
    return f"{len(areas)}:{len(conv)}:{hash(raw)}"


def test_engineer_areas_survive_apply():
    # Seed workbook as if from RUN Autogen scan
    wb = {
        "machine": "ORNCCP4",
        "project_name": "OReillyGreensboro_ORNCCP4",
        "conveyors": [
            {
                "conveyor": "P100",
                "main_area": "ORNCCP4_Area",
                "safety_zone": "ORNCCP4_ESZone1",
                "source": "run",
                "include": True,
            },
            {
                "conveyor": "P102",
                "main_area": "ORNCCP4_Area",
                "safety_zone": "ORNCCP4_ESZone1",
                "source": "run",
                "include": True,
            },
            {
                "conveyor": "P106",
                "main_area": "ORNCCP4_Area",
                "safety_zone": "ORNCCP4_ESZone1",
                "source": "run",
                "include": True,
            },
        ],
        "areas": [
            {"name": "ORNCCP4_Area", "safety_zone": "ORNCCP4_ESZone1", "conveyor_count": 3}
        ],
        "options": {"areas": ["ORNCCP4_Area"], "safety_zones": ["ORNCCP4_ESZone1"]},
        "merges_2to1": [],
    }

    # Engineer graph: two new Areas with conveyors reassigned + one new stub
    graph = {
        "version": 1,
        "applyMode": "canonical",
        "areas": [
            {
                "id": "area_a",
                "name": "TEST_A",
                "nodes": [
                    {
                        "id": "n1",
                        "kind": "conv_straight",
                        "conveyorTag": "P100",
                        "downstream": "P102",
                        "plcOwned": True,
                    },
                    {
                        "id": "n2",
                        "kind": "conv_straight",
                        "conveyorTag": "P102",
                        "downstream": "",
                        "terminal": True,
                        "plcOwned": True,
                    },
                ],
                "wires": [{"id": "w1", "from": "n1", "to": "n2", "toPort": "in"}],
            },
            {
                "id": "area_b",
                "name": "TEST_B",
                "nodes": [
                    {
                        "id": "n3",
                        "kind": "conv_straight",
                        "conveyorTag": "P106",
                        "downstream": "",
                        "terminal": True,
                        "plcOwned": True,
                    },
                    {
                        "id": "n4",
                        "kind": "conv_straight",
                        "conveyorTag": "P999",
                        "downstream": "",
                        "terminal": True,
                        "plcOwned": True,
                        "placeholderTag": True,
                    },
                ],
                "wires": [],
            },
            {
                "id": "area_empty",
                "name": "TEST_EMPTY",
                "nodes": [],
                "wires": [],
            },
        ],
        "activeAreaId": "area_a",
    }

    before = copy_area_snapshot(wb)
    out = apply_graph_to_workbook(graph, copy.deepcopy(wb))
    assert out["ok"], out
    wb2 = out["workbook"]

    area_names = {str(a.get("name") or "").strip() for a in (wb2.get("areas") or [])}
    assert "TEST_A" in area_names, f"TEST_A missing from workbook areas: {area_names}"
    assert "TEST_B" in area_names, f"TEST_B missing from workbook areas: {area_names}"
    assert "TEST_EMPTY" in area_names, f"TEST_EMPTY missing (0-conveyor engineer area): {area_names}"

    by = {
        str(r.get("conveyor") or "").strip().upper(): str(r.get("main_area") or "").strip()
        for r in (wb2.get("conveyors") or [])
    }
    assert by.get("P100") == "TEST_A", by
    assert by.get("P102") == "TEST_A", by
    assert by.get("P106") == "TEST_B", by
    assert by.get("P999") == "TEST_B", by

    # Tags still in workbook that were NOT in this Apply must NOT be yanked
    # solely because their main_area matched a graph area name.
    # (Simulated by a RUN row already in TEST_A that was not in the graph —
    #  with the old bug it would be restored; with the fix it is kept as-is
    #  only if it was not marked transport_build. Add such a row:)
    wb_extra = copy.deepcopy(wb)
    wb_extra["conveyors"].append(
        {
            "conveyor": "P200",
            "main_area": "TEST_A",  # same name as engineer area, but RUN-sourced
            "safety_zone": "TEST_A_ESZone1",
            "source": "run",
            "include": True,
            # NOT transport_build
        }
    )
    out2 = apply_graph_to_workbook(graph, wb_extra)
    by2 = {
        str(r.get("conveyor") or "").strip().upper(): str(r.get("main_area") or "").strip()
        for r in (out2["workbook"].get("conveyors") or [])
    }
    # P200 was never in the Apply graph and was never transport_build —
    # must keep its main_area (not restored to ORNCCP4_Area).
    assert by2.get("P200") == "TEST_A", (
        f"P200 should keep TEST_A (not restored); got {by2.get('P200')}; "
        f"restored={out2.get('conveyors_restored')}"
    )

    # Graph area names must appear in areas_applied
    applied = set(out.get("areas_applied") or [])
    assert "TEST_A" in applied and "TEST_B" in applied, applied

    print("PASS test_engineer_areas_survive_apply")
    print("before_areas", before)
    print("after_areas", sorted(area_names))
    print("hash_style", _hash(wb2))
    return True


def copy_area_snapshot(wb: dict) -> list:
    return sorted(
        str(a.get("name") or "").strip()
        for a in (wb.get("areas") or [])
        if str(a.get("name") or "").strip()
    )


def _hash(wb: dict) -> str:
    areas = sorted(
        str(a.get("name") or "").strip()
        for a in (wb.get("areas") or [])
        if str(a.get("name") or "").strip()
    )
    conv = sorted(
        f"{str(r.get('conveyor') or '').strip().upper()}={str(r.get('main_area') or '').strip()}"
        for r in (wb.get("conveyors") or [])
        if str(r.get("conveyor") or "").strip()
    )
    return f"{len(areas)}:{len(conv)}:" + "|".join(areas + conv)


import copy  # noqa: E402  — used by test


if __name__ == "__main__":
    test_engineer_areas_survive_apply()
    print("ALL PASS")

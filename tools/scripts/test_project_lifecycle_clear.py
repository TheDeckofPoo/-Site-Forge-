#!/usr/bin/env python3
"""Project lifecycle clear — _default_main_area must stay controller-scoped.

Guards:
  - Fake MSCRENOSHIP workbook documents the foreign-site leak source
  - apply_graph_to_workbook default area for ORNCCP2 must NOT return MSCRENOSHIP_Area
  - Resulting areas contain zero MSCRENO tokens for an ORNCCP2 workbook
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_transport_graph import apply_graph_to_workbook  # noqa: E402


def _mscreon_workbook() -> dict:
    """Foreign-site workbook that historically leaked into ORNCCP2 defaults."""
    return {
        "version": 1,
        "kind": "fortna_autogen_workbook",
        "machine": "MSCRENOSHIP",
        "project_name": "Reno_MSCRENOSHIP",
        "site": "Reno",
        "conveyors": [
            {
                "number": 1,
                "include": True,
                "conveyor": "P10",
                "main_area": "MSCRENOSHIP_Area",
                "safety_zone": "MSCRENOSHIP_ESZone1",
                "type": "Transport with MS",
                "source": "run",
            },
            {
                "number": 2,
                "include": True,
                "conveyor": "P20",
                "main_area": "MSCRENOSHIP_Area",
                "safety_zone": "MSCRENOSHIP_ESZone1",
                "type": "Transport with MS",
                "source": "run",
            },
        ],
        "areas": [
            {
                "name": "MSCRENOSHIP_Area",
                "safety_zone": "MSCRENOSHIP_ESZone1",
                "conveyor_count": 2,
            }
        ],
        "options": {
            "areas": ["MSCRENOSHIP_Area"],
            "safety_zones": ["MSCRENOSHIP_ESZone1"],
        },
    }


def _ornccp2_workbook_forcing_machine_fallback() -> dict:
    """ORNCCP2 workbook where the only prior area is the graph area itself.

    That forces _default_main_area past counts/areas into the machine token path
    (ORNCCP2_Area) — never a hardcoded MSCRENOSHIP_Area.
    """
    return {
        "version": 1,
        "kind": "fortna_autogen_workbook",
        "machine": "ORNCCP2",
        "project_name": "OReillyGreensboro_ORNCCP2",
        "site": "OReillyGreensboro",
        "conveyors": [
            {
                "number": 1,
                "include": True,
                "conveyor": "P100",
                # Same name as the graph area → excluded from default counts/areas
                "main_area": "ModuleA",
                "safety_zone": "ModuleA_ESZone1",
                "type": "Transport with MS",
                "source": "run",
                "transport_build": True,
            }
        ],
        "areas": [
            {
                "name": "ModuleA",
                "safety_zone": "ModuleA_ESZone1",
                "conveyor_count": 1,
            }
        ],
        "options": {"areas": ["ModuleA"], "safety_zones": ["ModuleA_ESZone1"]},
    }


def _minimal_graph_module_a() -> dict:
    """Graph owns P300 on ModuleA only — P100 must restore via machine default."""
    return {
        "version": 1,
        "areas": [
            {
                "id": "area_a",
                "name": "ModuleA",
                "nodes": [
                    {
                        "id": "n_p300",
                        "kind": "conv_straight",
                        "label": "P300",
                        "conveyorTag": "P300",
                        "downstream": "",
                        "x": 40,
                        "y": 100,
                        "devices": [],
                    }
                ],
                "wires": [],
            }
        ],
    }


def _areas_blob(wb: dict) -> str:
    parts: list[str] = []
    for a in wb.get("areas") or []:
        if isinstance(a, dict):
            parts.append(str(a.get("name") or ""))
            parts.append(str(a.get("safety_zone") or ""))
        else:
            parts.append(str(a))
    for r in wb.get("conveyors") or []:
        parts.append(str(r.get("main_area") or ""))
        parts.append(str(r.get("safety_zone") or ""))
    for a in (wb.get("options") or {}).get("areas") or []:
        parts.append(str(a))
    for s in (wb.get("options") or {}).get("safety_zones") or []:
        parts.append(str(s))
    return " ".join(parts).upper()


def main() -> int:
    print("=== test_project_lifecycle_clear ===")
    failures = 0

    # 1) Foreign MSCRENOSHIP fixture (documents the leak source)
    foreign = _mscreon_workbook()
    foreign_blob = _areas_blob(foreign)
    if "MSCRENOSHIP_AREA" not in foreign_blob:
        print("FAIL: fixture missing MSCRENOSHIP_Area")
        failures += 1
    else:
        print("PASS: MSCRENOSHIP fixture has MSCRENOSHIP_Area rows")

    # 2) ORNCCP2 apply — machine fallback must be ORNCCP2_Area, never MSCRENO*
    wb = _ornccp2_workbook_forcing_machine_fallback()
    graph = _minimal_graph_module_a()
    result = apply_graph_to_workbook(graph, wb)
    if not result.get("ok"):
        print(f"FAIL: apply_graph_to_workbook not ok: {result}")
        return 1
    out = result.get("workbook") or {}
    blob = _areas_blob(out)
    if "MSCRENO" in blob:
        print("FAIL: MSCRENO token leaked into ORNCCP2 workbook areas")
        print(
            json.dumps(
                {"areas": out.get("areas"), "conveyors": out.get("conveyors")},
                indent=2,
            )[:2000]
        )
        failures += 1
    else:
        print("PASS: zero MSCRENO in resulting ORNCCP2 areas")

    p100 = next(
        (
            r
            for r in (out.get("conveyors") or [])
            if str(r.get("conveyor") or "").upper() == "P100"
        ),
        None,
    )
    if not p100:
        print("FAIL: P100 missing after apply")
        failures += 1
    else:
        area = str(p100.get("main_area") or "")
        if area.upper() == "ORNCCP2_AREA":
            print("PASS: P100 restored to ORNCCP2_Area via machine fallback")
        elif "MSCRENO" in area.upper():
            print(f"FAIL: P100 defaulted to MSCRENO area: {area!r}")
            failures += 1
        else:
            print(
                f"FAIL: expected P100 main_area=ORNCCP2_Area (machine fallback), got {area!r}"
            )
            failures += 1

    # 3) Empty-ish ORNCCP2 workbook (no areas list) still must not invent MSCRENO
    empty_orn = {
        "machine": "ORNCCP2",
        "project_name": "OReillyGreensboro_ORNCCP2",
        "conveyors": [
            {
                "conveyor": "P50",
                "main_area": "ModuleA",
                "safety_zone": "ModuleA_ESZone1",
                "source": "run",
                "transport_build": True,
                "include": True,
                "type": "Transport with MS",
            }
        ],
        "areas": [],
    }
    r2 = apply_graph_to_workbook(_minimal_graph_module_a(), empty_orn)
    out2 = r2.get("workbook") or {}
    blob2 = _areas_blob(out2)
    if "MSCRENO" in blob2:
        print("FAIL: empty ORNCCP2 path leaked MSCRENO")
        failures += 1
    else:
        print("PASS: empty ORNCCP2 path has zero MSCRENO")

    p50 = next(
        (
            r
            for r in (out2.get("conveyors") or [])
            if str(r.get("conveyor") or "").upper() == "P50"
        ),
        None,
    )
    if p50 and str(p50.get("main_area") or "").upper() == "ORNCCP2_AREA":
        print("PASS: P50 restored to ORNCCP2_Area via machine fallback")
    elif p50 and "MSCRENO" in str(p50.get("main_area") or "").upper():
        print(f"FAIL: P50 MSCRENO default {p50.get('main_area')!r}")
        failures += 1
    elif p50:
        print(
            f"FAIL: expected P50 main_area=ORNCCP2_Area, got {p50.get('main_area')!r}"
        )
        failures += 1
    else:
        print("FAIL: P50 missing after apply")
        failures += 1

    if failures:
        print(f"=== FAILED ({failures}) ===")
        return 1
    print("=== ALL PASS ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

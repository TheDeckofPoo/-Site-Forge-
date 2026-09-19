#!/usr/bin/env python3
"""Canonical workbook merge: Transport + Safety + Sorter survive sequential Apply.

Documents the one-workbook merge contract used by Apply Safety / generate /
Apply Sorter (fortna-plus.js + safety-build.js).
"""
from __future__ import annotations
# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys
_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / 'tools' / 'scripts'
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
# Prefer canonical names used by existing tests:
SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO
REPO_ROOT = _SF_REPO
# --- end bootstrap ---


import unittest


def merge_workbook(
    disk: dict,
    mem: dict,
    *,
    safety=None,
    sorter=None,
    conveyors=None,
    sawtooth=None,
    control=None,
) -> dict:
    """Mirrors live Sorter/Safety Apply merge: never hollow Transport or sibling builds.

    Residual duplication: dashboard fortna-plus.js Apply Sorter inlines this pattern
    separately from safety-build.js / transport Apply — centralize later (Gate N).
    """
    out = {**disk, **mem}
    out["conveyors"] = (
        conveyors
        if conveyors is not None
        else (
            disk.get("conveyors")
            if isinstance(disk.get("conveyors"), list) and disk.get("conveyors")
            else mem.get("conveyors") or disk.get("conveyors") or []
        )
    )
    if safety is not None:
        out["safety_build"] = safety
    else:
        out["safety_build"] = mem.get("safety_build") or disk.get("safety_build")
    if sawtooth is not None:
        out["sawtooth_build"] = sawtooth
    else:
        out["sawtooth_build"] = mem.get("sawtooth_build") or disk.get("sawtooth_build")
    if sorter is not None:
        out["sorter_build"] = sorter
    elif mem.get("sorter_build"):
        out["sorter_build"] = mem["sorter_build"]
    elif disk.get("sorter_build"):
        out["sorter_build"] = disk["sorter_build"]
    if control is not None:
        out["control_build"] = control
    else:
        out["control_build"] = mem.get("control_build") or disk.get("control_build")
    return out


class TestCanonicalSubsystemMerge(unittest.TestCase):
    def test_sequential_apply_survives(self) -> None:
        disk: dict = {}
        # Apply Transport
        disk = merge_workbook(
            disk,
            {},
            conveyors=[{"conveyor": "P400", "main_area": "ZZ_A", "include": True}],
        )
        self.assertEqual(disk["conveyors"][0]["main_area"], "ZZ_A")
        # Apply Safety (must not wipe conveyors)
        disk = merge_workbook(
            disk,
            {"conveyors": []},  # hollow memory
            safety={
                "zones": [{"name": "ZZ_A_ESZone1", "members": ["4ES"], "area": "ZZ_A"}],
                "appliedAt": "t1",
            },
        )
        self.assertTrue(disk["conveyors"])
        self.assertEqual(disk["safety_build"]["zones"][0]["members"], ["4ES"])
        # Apply Sorter
        disk = merge_workbook(
            disk,
            {},
            sorter={"sorters": [{"name": "504_BELT"}], "appliedAt": "t2"},
        )
        # Apply/reconcile StartStop/Jam control model
        disk = merge_workbook(
            disk,
            {},
            control={
                "version": 1,
                "startstop": {"zone_count": 2, "zones": [{"name": "AREA_A"}]},
                "jam": {"zone_count": 1},
                "logical_signals": {"signal_count": 3, "referenced_count": 2},
            },
        )
        # Modify Transport again
        disk = merge_workbook(
            disk,
            {},
            conveyors=[
                {"conveyor": "P400", "main_area": "ZZ_A", "include": True},
                {"conveyor": "P402", "main_area": "ZZ_A", "include": True},
            ],
        )
        # Apply Safety again + reload shape
        disk = merge_workbook(
            disk,
            {"conveyors": []},
            safety={
                "zones": [{"name": "ZZ_A_ESZone1", "members": ["4ES", "5ES"], "area": "ZZ_A"}],
                "appliedAt": "t3",
            },
        )
        self.assertEqual(len(disk["conveyors"]), 2)
        self.assertEqual(disk["safety_build"]["zones"][0]["members"], ["4ES", "5ES"])
        self.assertEqual(disk["sorter_build"]["sorters"][0]["name"], "504_BELT")
        self.assertEqual(disk["control_build"]["startstop"]["zone_count"], 2)
        self.assertEqual(disk["control_build"]["logical_signals"]["referenced_count"], 2)

    def test_sorter_apply_does_not_drop_safety_when_mem_hollow(self) -> None:
        disk = {
            "conveyors": [{"conveyor": "P400", "include": True}],
            "safety_build": {"zones": [{"name": "A_ES", "members": ["4ES"]}]},
            "sawtooth_build": {"collector_conveyor": "P414"},
        }
        # Sorter Apply with empty mem conveyors must keep Transport/Safety/Sawtooth.
        out = merge_workbook(
            disk,
            {"conveyors": []},
            sorter={"known_sorters": [{"name": "X"}], "plc_generation": "NOT_STARTED"},
        )
        self.assertTrue(out["conveyors"])
        self.assertEqual(out["safety_build"]["zones"][0]["name"], "A_ES")
        self.assertEqual(out["sawtooth_build"]["collector_conveyor"], "P414")
        self.assertEqual(out["sorter_build"]["plc_generation"], "NOT_STARTED")


if __name__ == "__main__":
    unittest.main(verbosity=2)

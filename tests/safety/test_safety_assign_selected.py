#!/usr/bin/env python3
"""Safety Assign Selected — state-transition contract (Gate M).

Mirrors dashboard/safety-build.js assignCheckedToSelectedZone:
check devices → assign to selected zone → reassign removes from other zones
→ Apply payload retains members.
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


def assign_selected(zones: list[dict], dest: str, names: list[str]) -> None:
    for oz in zones:
        if oz["name"] == dest:
            continue
        oz["members"] = [
            m
            for m in oz.get("members") or []
            if not any(str(n).upper() == str(m).upper() for n in names)
        ]
    live = next(z for z in zones if z["name"] == dest)
    s = set(live.get("members") or [])
    for n in names:
        s.add(n)
    live["members"] = list(s)
    live["membersOrigin"] = "ENGINEER_ASSIGNED"
    live["engineerEdited"] = True


class TestSafetyAssignSelected(unittest.TestCase):
    def test_assign_and_reassign(self) -> None:
        zones = [
            {"name": "ZoneA", "members": []},
            {"name": "ZoneB", "members": ["ES100"]},
        ]
        assign_selected(zones, "ZoneA", ["ES500", "ES406"])
        a = next(z for z in zones if z["name"] == "ZoneA")
        self.assertEqual(set(a["members"]), {"ES500", "ES406"})
        # move ES500 to ZoneB
        assign_selected(zones, "ZoneB", ["ES500"])
        a = next(z for z in zones if z["name"] == "ZoneA")
        b = next(z for z in zones if z["name"] == "ZoneB")
        self.assertNotIn("ES500", a["members"])
        self.assertIn("ES500", b["members"])
        self.assertIn("ES100", b["members"])

    def test_apply_payload_shape(self) -> None:
        zones = [{"name": "testt111_ESZone1", "members": [], "area": "testt111"}]
        assign_selected(zones, "testt111_ESZone1", ["4ES", "5ES", "ES422"])
        payload = {
            "safety_build": {
                "zones": zones,
                "appliedAt": "2026-09-18T00:00:00Z",
            }
        }
        self.assertEqual(len(payload["safety_build"]["zones"][0]["members"]), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)

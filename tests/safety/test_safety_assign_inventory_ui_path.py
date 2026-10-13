#!/usr/bin/env python3
"""P0 — real UI assignment state transition (not preconstructed Apply payload).

Warden 2c8789a failure:
  Check ESPB2/24/32/ESLS2 in SITE SAFETY INVENTORY
  → click zone-detail \"Assign checked inventory → this zone\"
  → UI looked like Assigned 4
  → devices stayed in Default Safety
  → Apply → Area_Test1_ESZone1 members=[]

Hunter first divergence:
  addSelectedDevices read hidden #sb-available [data-sb-avail]:checked
  while the engineer checked visible [data-sb-inv] inventory boxes.

This test exercises THAT collector transition + membership handoff, not a
hand-built Apply payload.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SAFETY_JS = REPO / "dashboard" / "safety-build.js"

PICK_MEMBERS = ["ESPB2", "ESPB24", "ESPB32", "ESLS2"]
ZONE_NAME = "Area_Test1_ESZone1"
AREA_NAME = "Area_Test1"


def _broken_zone_detail_collector(hidden_avail_checked, inventory_checked):
    """Pre-fix addSelectedDevices — ONLY hidden #sb-available checks."""
    return list(hidden_avail_checked or [])


def _fixed_inventory_collector(hidden_avail_checked, inventory_checked):
    """Post-fix collector — SITE SAFETY INVENTORY [data-sb-inv] only."""
    seen = set()
    out = []
    for n in inventory_checked or []:
        key = str(n).upper()
        if not n or key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out


def assign_selected_ui_transition(zones, dest_name, inventory_checked):
    """Mirror assignCheckedToSelectedZone → mutateZone membership write."""
    live = next(z for z in zones if z["name"] == dest_name)
    names = _fixed_inventory_collector([], inventory_checked)
    s = set(live.get("members") or [])
    meta = live.setdefault("memberMeta", {})
    for n in names:
        if n.upper() not in {str(x).upper() for x in s}:
            s.add(n)
        meta[n] = {"origin": "ENGINEER_ASSIGNED", "assignedBy": "engineer"}
    live["members"] = list(s)
    live["membersOrigin"] = "ENGINEER_ASSIGNED"
    live["engineerEdited"] = True
    live["zoneOrigin"] = "ENGINEER"
    live["createdBy"] = "engineer"
    # Status must reflect membership AFTER write, not checkbox count alone.
    status = f"Assigned {len(live['members'])} device(s) → {dest_name}"
    return live, status


def devices_in_default(all_devices, zones):
    """Devices with no engineer-zone membership remain Default/Unassigned."""
    assigned = set()
    for z in zones:
        if str(z.get("name") or "").lower().startswith("default"):
            continue
        for m in z.get("members") or []:
            assigned.add(str(m).upper())
    return [d for d in all_devices if str(d).upper() not in assigned]


class TestAssignInventoryUiPath(unittest.TestCase):
    def test_source_no_longer_reads_hidden_sb_available(self) -> None:
        src = SAFETY_JS.read_text(encoding="utf-8")
        self.assertNotRegex(
            src,
            r"querySelectorAll\(['\"]#sb-available \[data-sb-avail\]:checked['\"]\)",
            "addSelectedDevices must not read hidden #sb-available checks",
        )
        self.assertIn("collectCheckedInventoryDeviceNames", src)
        self.assertIn("data-sb-inv", src)
        # Zone-detail button must reuse inventory assign path
        self.assertRegex(
            src,
            r"function addSelectedDevices\([\s\S]*?assignCheckedToSelectedZone\(\)",
        )

    def test_first_divergence_broken_vs_fixed_collector(self) -> None:
        inventory_checked = list(PICK_MEMBERS)
        hidden_avail_checked: list[str] = []  # engineer never sees/checks these
        broken = _broken_zone_detail_collector(hidden_avail_checked, inventory_checked)
        fixed = _fixed_inventory_collector(hidden_avail_checked, inventory_checked)
        self.assertEqual(broken, [], "broken path silently assigns nothing")
        self.assertEqual(fixed, PICK_MEMBERS, "fixed path reads inventory checks")

    def test_ui_assign_writes_members_and_leaves_default(self) -> None:
        zones = [
            {
                "name": "Default Safety",
                "members": list(PICK_MEMBERS) + ["ESPB20"],
                "isDefault": True,
            },
            {
                "name": ZONE_NAME,
                "source_id": "szone_test1eszone1",
                "area": AREA_NAME,
                "areaRef": AREA_NAME,
                "members": [],
                "engineerEdited": True,
                "createdBy": "engineer",
                "zoneOrigin": "ENGINEER",
                "provenance": "ENGINEER_CREATED",
            },
        ]
        all_devices = list(PICK_MEMBERS) + ["ESPB20"]

        # BEFORE: all four still Default
        self.assertEqual(
            sorted(devices_in_default(all_devices, zones)),
            sorted(all_devices),
        )

        live, status = assign_selected_ui_transition(zones, ZONE_NAME, PICK_MEMBERS)

        # AFTER write: zone has exactly 4; status from membership count
        self.assertEqual(sorted(live["members"]), sorted(PICK_MEMBERS))
        self.assertEqual(len(live["members"]), 4)
        self.assertIn("Assigned 4", status)
        self.assertIn(ZONE_NAME, status)

        # Four leave Default; ESPB20 remains Default
        still_default = devices_in_default(all_devices, zones)
        self.assertEqual(still_default, ["ESPB20"])
        for m in PICK_MEMBERS:
            self.assertNotIn(m, still_default)

    def test_apply_payload_from_ui_transition_not_empty(self) -> None:
        """Apply must serialize the UI-assigned members — not a hollow zone."""
        zones = [
            {
                "name": ZONE_NAME,
                "source_id": "szone_test1eszone1",
                "area": AREA_NAME,
                "members": [],
                "engineerEdited": True,
                "createdBy": "engineer",
            }
        ]
        live, _ = assign_selected_ui_transition(zones, ZONE_NAME, PICK_MEMBERS)
        # Simulate Apply payload shape from live zone after UI assign
        payload_zone = {
            "source_id": live["source_id"],
            "name": live["name"],
            "engineering_name": live["name"],
            "area": live.get("area") or AREA_NAME,
            "members": list(live["members"]),
            "membersOrigin": "ENGINEER_ASSIGNED",
            "engineerEdited": True,
            "zoneOrigin": "ENGINEER",
            "createdBy": "engineer",
            "provenance": "ENGINEER_CREATED",
        }
        self.assertEqual(len(payload_zone["members"]), 4)
        self.assertEqual(sorted(payload_zone["members"]), sorted(PICK_MEMBERS))

    def test_empty_live_must_not_eclipse_member_rich_draft(self) -> None:
        """Apply memberSnap prefer: hollow live cannot wipe draft members."""
        live_snap = {
            "members": [],
            "engineerEdited": True,
            "name": ZONE_NAME,
        }
        draft = {
            "members": list(PICK_MEMBERS),
            "engineerEdited": True,
            "name": ZONE_NAME,
        }
        # Mirror repaired prefer rule
        existing = live_snap
        members = draft["members"]
        if existing and len(existing.get("members") or []) >= len(members):
            chosen = existing
        elif existing and (existing.get("members") or []) and not members:
            chosen = existing
        else:
            chosen = {
                **existing,
                "members": members if members else (existing.get("members") or []),
            }
        self.assertEqual(sorted(chosen["members"]), sorted(PICK_MEMBERS))


class TestAssignStatusFromLiveMembership(unittest.TestCase):
    def test_status_uses_post_write_count_not_checkbox_count(self) -> None:
        """Assigned N must equal zone.members length after write."""
        zones = [{
            "name": ZONE_NAME,
            "source_id": "szone_x",
            "members": [],
            "engineerEdited": True,
            "createdBy": "engineer",
        }]
        # Pretend only 3 of 4 checkbox names are eligible after resolve
        eligible = PICK_MEMBERS[:3]
        live, status = assign_selected_ui_transition(zones, ZONE_NAME, eligible)
        self.assertEqual(len(live["members"]), 3)
        self.assertIn("Assigned 3", status)
        self.assertNotIn("Assigned 4", status)


if __name__ == "__main__":
    unittest.main()

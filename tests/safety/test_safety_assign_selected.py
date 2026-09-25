#!/usr/bin/env python3
"""Safety Assign Selected — many-to-many membership contract.

Mirrors dashboard/safety-build.js assignCheckedToSelectedZone:
check devices → ADD to selected zone (never strip from other zones).
A shared MCR may participate in ZoneA + ZoneB without duplication.
"""
from __future__ import annotations
# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys
_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / 'tools' / 'scripts'
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO
REPO_ROOT = _SF_REPO
# --- end bootstrap ---

import unittest

from fortna_default_ownership import assign_safety_members, delete_safety_zone_return_to_default
from fortna_es_compiler import build_safety_zone_irs, emit_es_program


def assign_selected(zones: list[dict], dest: str, names: list[str]) -> None:
    """UI-faithful many-to-many ADD (no exclusive move)."""
    live = next(z for z in zones if z["name"] == dest)
    s = set(live.get("members") or [])
    meta = live.setdefault("memberMeta", {})
    for n in names:
        if n not in s and n.upper() not in {str(x).upper() for x in s}:
            s.add(n)
        meta[n] = {"origin": "ENGINEER_ASSIGNED", "assignedBy": "engineer"}
    live["members"] = list(s)
    live["membersOrigin"] = "ENGINEER_ASSIGNED"
    live["engineerEdited"] = True


def _rung_xml(num, text, comment=""):
    c = f"<Comment><![CDATA[{comment}]]></Comment>" if comment else ""
    return f'<Rung Number="{num}" Type="N">{c}<Text><![CDATA[{text}]]></Text></Rung>'


def _routine(name, rungs):
    return (
        f'<Routine Name="{name}" Type="RLL"><RLLContent>'
        + "".join(rungs)
        + "</RLLContent></Routine>"
    )


def _extract_tag_block(_lib, _tag):
    return None


class TestSafetyAssignSelected(unittest.TestCase):
    def test_assign_adds_without_removing_from_others(self) -> None:
        zones = [
            {"name": "ZoneA", "members": []},
            {"name": "ZoneB", "members": ["ES100"]},
        ]
        assign_selected(zones, "ZoneA", ["ES500", "ES406"])
        a = next(z for z in zones if z["name"] == "ZoneA")
        self.assertEqual(set(a["members"]), {"ES500", "ES406"})
        # ADD ES500 to ZoneB — must remain in ZoneA (many-to-many)
        assign_selected(zones, "ZoneB", ["ES500"])
        a = next(z for z in zones if z["name"] == "ZoneA")
        b = next(z for z in zones if z["name"] == "ZoneB")
        self.assertIn("ES500", a["members"])
        self.assertIn("ES500", b["members"])
        self.assertIn("ES100", b["members"])
        self.assertEqual(a["memberMeta"]["ES500"]["origin"], "ENGINEER_ASSIGNED")

    def test_shared_mcr_two_zones_no_duplication(self) -> None:
        """Regression: 2MCR1_AUX in ZoneA + ZoneB; delete ZoneA keeps ZoneB."""
        zones = [
            {
                "name": "Trash_ESZone1",
                "source_id": "szone_trash",
                "members": [],
                "area": "Trash",
                "engineerEdited": True,
            },
            {
                "name": "Infeed_ESZone1",
                "source_id": "szone_infeed",
                "members": [],
                "area": "Infeed",
                "engineerEdited": True,
            },
        ]
        zones = assign_safety_members(zones, ["ES406", "2MCR1_AUX"], "Trash_ESZone1")
        zones = assign_safety_members(zones, ["2MCR1_AUX"], "Infeed_ESZone1")
        trash = next(z for z in zones if z["name"] == "Trash_ESZone1")
        infeed = next(z for z in zones if z["name"] == "Infeed_ESZone1")
        self.assertEqual(set(trash["members"]), {"ES406", "2MCR1_AUX"})
        self.assertEqual(set(infeed["members"]), {"2MCR1_AUX"})
        # Canonical device appears once per zone — no duplicate copies
        self.assertEqual(trash["members"].count("2MCR1_AUX"), 1)
        self.assertEqual(infeed["members"].count("2MCR1_AUX"), 1)

        # Persist / reopen shape
        payload = {
            "safety_build": {
                "zones": zones,
                "appliedAt": "2026-09-25T00:00:00Z",
            }
        }
        restored = payload["safety_build"]["zones"]
        self.assertIn("2MCR1_AUX", next(z for z in restored if z["name"] == "Trash_ESZone1")["members"])
        self.assertIn("2MCR1_AUX", next(z for z in restored if z["name"] == "Infeed_ESZone1")["members"])

        # Delete Trash → ES406 unassigned; 2MCR1_AUX still Infeed
        zones = delete_safety_zone_return_to_default(zones, "Trash_ESZone1")
        names = {str(z.get("name") or z.get("engineering_name") or "") for z in zones}
        self.assertNotIn("Trash_ESZone1", names)
        infeed2 = next(
            z for z in zones
            if str(z.get("name") or z.get("engineering_name") or "") == "Infeed_ESZone1"
        )
        self.assertEqual(set(infeed2["members"]), {"2MCR1_AUX"})

        # Compiler consumes many-to-many: shared AUX emits in remaining zone
        irs = build_safety_zone_irs(
            engineer_zones=[
                {
                    "name": "Infeed_ESZone1",
                    "area": "Infeed_Area",
                    "members": list(infeed2["members"]),
                    "conveyors": ["P100"],
                }
            ],
            default_area="Infeed_Area",
        )
        pack = emit_es_program(
            irs,
            _rung_xml=_rung_xml,
            routine=_routine,
            extract_tag_block=_extract_tag_block,
            library_text="",
        )
        xml = pack["program_xml"]
        self.assertIn("T_2MCR1_AUX", "".join(pack["zones"][0]["members"]) or xml)
        self.assertIn("ES_SIL1_Cat1(T_2MCR1_AUX_AOI,T_2MCR1_AUX,", xml)

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
        self.assertEqual(
            payload["safety_build"]["zones"][0]["memberMeta"]["4ES"]["origin"],
            "ENGINEER_ASSIGNED",
        )

    def test_engineer_membership_not_upgraded_to_proven(self) -> None:
        zones = [
            {
                "name": "ZoneA",
                "source_id": "szone_a",
                "members": ["ES406"],
                "memberMeta": {
                    "ES406": {"origin": "ENGINEER_ASSIGNED", "assignedBy": "engineer"},
                },
                "engineerEdited": True,
            }
        ]
        # Re-assign must not rewrite ENGINEER → PROVEN
        zones = assign_safety_members(zones, ["ES406"], "ZoneA")
        meta = zones[0]["memberMeta"]["ES406"]
        self.assertEqual(meta["origin"], "ENGINEER_ASSIGNED")


if __name__ == "__main__":
    unittest.main(verbosity=2)

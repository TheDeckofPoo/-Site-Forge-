#!/usr/bin/env python3
"""Gate I — Safety zone rename preserves source_id.

engineering_name is editable; source_id (RUN identity) is immutable.
Rename must not duplicate the zone or drop members.
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


import re
import sys
import unittest
from pathlib import Path

SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from fortna_safety_model import (  # noqa: E402
    ORIGIN_ENGINEER,
    _merge_engineer_zone,
    build_safety_model,
    safety_build_workbook_payload,
)

SAFETY_JS = ROOT / "dashboard" / "safety-build.js"
LOGIX_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class TestSafetyZoneRename(unittest.TestCase):
    def test_js_has_source_id_and_engineering_name(self) -> None:
        js = SAFETY_JS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("source_id", js)
        self.assertIn("engineering_name", js)
        self.assertIn("function renameSafetyZone", js)
        self.assertIn("function validateLogixIdent", js)
        self.assertIn("LOGIX_IDENT_RE", js)
        self.assertIn("Gate I", js)

    def test_logix_ident_rules_in_js(self) -> None:
        js = SAFETY_JS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("LOGIX_IDENT_RE", js)
        self.assertIn("[A-Za-z_][A-Za-z0-9_]*", js)
        # Valid / invalid examples via the shared regex used in tests
        self.assertTrue(LOGIX_RE.match("HAHAHA_ESZone1"))
        self.assertTrue(LOGIX_RE.match("Zone_A"))
        self.assertFalse(LOGIX_RE.match("1Bad"))
        self.assertFalse(LOGIX_RE.match("has space"))
        self.assertFalse(LOGIX_RE.match("bad-name"))

    def test_merge_preserves_source_id_on_rename(self) -> None:
        auto = {
            "id": "RUN_ESZone1",
            "source_id": "RUN_ESZone1",
            "name": "RUN_ESZone1",
            "engineering_name": "RUN_ESZone1",
            "areaRef": "Main",
            "members": ["ES400", "ES406"],
            "membersOrigin": "ENGINEER_ASSIGNED",
            "conveyorRefs": ["P404"],
        }
        eng = {
            "source_id": "RUN_ESZone1",
            "engineering_name": "Staging_ESZone1",
            "name": "Staging_ESZone1",
            "members": ["ES400", "ES406", "CP2_ES"],
            "membersOrigin": ORIGIN_ENGINEER,
            "engineerEdited": True,
            "areaRef": "Main",
        }
        merged = _merge_engineer_zone(auto, eng)
        self.assertEqual(merged["source_id"], "RUN_ESZone1")
        self.assertEqual(merged["engineering_name"], "Staging_ESZone1")
        self.assertEqual(merged["name"], "Staging_ESZone1")
        self.assertEqual(len(merged["members"]), 3)
        self.assertIn("CP2_ES", merged["members"])

    def test_payload_persists_both_fields(self) -> None:
        model = {
            "zones": [
                {
                    "source_id": "Alpha_ESZone1",
                    "id": "Alpha_ESZone1",
                    "engineering_name": "Beta_ESZone1",
                    "name": "Beta_ESZone1",
                    "areaRef": "Alpha",
                    "conveyorRefs": ["P100"],
                    "members": ["2ES"],
                    "membersOrigin": ORIGIN_ENGINEER,
                    "engineerEdited": True,
                    "status": "READY",
                    "fields": {},
                }
            ],
            "devices": [],
            "unassignedDevices": [],
            "inventoryByKind": {},
            "counts": {},
            "readiness": {},
        }
        payload = safety_build_workbook_payload(model)
        z = payload["zones"][0]
        self.assertEqual(z["source_id"], "Alpha_ESZone1")
        self.assertEqual(z["engineering_name"], "Beta_ESZone1")
        self.assertEqual(z["name"], "Beta_ESZone1")
        self.assertEqual(z["members"], ["2ES"])

    def test_build_model_rename_does_not_duplicate(self) -> None:
        model = build_safety_model(
            run_dir=None,
            machine="SYNTH",
            transport_zones=[
                {
                    "name": "Alpha_ESZone1",
                    "area": "Alpha",
                    "conveyors": ["P100", "P102"],
                    "members": [],
                }
            ],
            areas=["Alpha"],
            area_conveyors={"Alpha": ["P100", "P102"]},
            engineer_safety_build={
                "zones": [
                    {
                        "source_id": "Alpha_ESZone1",
                        "engineering_name": "Staging_ESZone1",
                        "name": "Staging_ESZone1",
                        "areaRef": "Alpha",
                        "members": ["ES100"],
                        "membersOrigin": ORIGIN_ENGINEER,
                        "engineerEdited": True,
                    }
                ]
            },
        )
        names = [z.get("name") for z in model["zones"]]
        source_ids = [z.get("source_id") for z in model["zones"]]
        # One zone identity — rename must not create a second shell
        self.assertEqual(source_ids.count("Alpha_ESZone1"), 1)
        hit = next(z for z in model["zones"] if z.get("source_id") == "Alpha_ESZone1")
        self.assertEqual(hit["engineering_name"], "Staging_ESZone1")
        self.assertEqual(hit["name"], "Staging_ESZone1")
        self.assertEqual(hit["members"], ["ES100"])
        self.assertNotIn("Alpha_ESZone1", names)  # display name is engineering_name


if __name__ == "__main__":
    unittest.main(verbosity=2)

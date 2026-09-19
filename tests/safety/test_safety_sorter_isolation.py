#!/usr/bin/env python3
"""Sorter Apply must not hollow Safety Apply membership (field 1027 regression)."""
from __future__ import annotations

# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys

_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
ROOT = _SF_REPO
# --- end bootstrap ---

import json
import unittest
from pathlib import Path


class TestPreferSafetyBuildLogic(unittest.TestCase):
    """Mirror dashboard preferSafetyBuild / unionSafetyBuild semantics in Python."""

    @staticmethod
    def _union(a, b):
        if not a and not b:
            return None
        if not a:
            return b
        if not b:
            return a
        by = {}
        for z in list(a.get("zones") or []) + list(b.get("zones") or []):
            sid = str(z.get("source_id") or z.get("id") or z.get("name") or "").strip()
            if not sid:
                continue
            prev = by.get(sid)
            if not prev:
                by[sid] = dict(z)
                continue
            next_z = {**prev, **z}
            prev_n = len(prev.get("members") or [])
            z_n = len(z.get("members") or [])
            if prev_n and not z_n:
                next_z["members"] = prev["members"]
                next_z["membersOrigin"] = prev.get("membersOrigin") or next_z.get("membersOrigin")
            elif z_n >= prev_n:
                next_z["members"] = z.get("members")
            else:
                next_z["members"] = prev.get("members")
            by[sid] = next_z
        base = b if b.get("appliedAt") and not a.get("appliedAt") else a
        if b.get("appliedAt") and a.get("appliedAt"):
            base = b
        return {**base, "zones": list(by.values())}

    def test_hollow_transport_does_not_beat_applied_safety(self):
        disk = {
            "source": "safety_build",
            "appliedAt": "2026-09-19T13:00:00Z",
            "zones": [
                {
                    "source_id": "Zone_Area1_ESZone1",
                    "id": "Zone_Area1_ESZone1",
                    "name": "Zone_Area1_ESZone1",
                    "members": [f"ES{i}" for i in range(12)],
                    "membersOrigin": "ENGINEER_ASSIGNED",
                }
            ],
        }
        mem = {
            "source": "transport_engineer",
            "zones": [
                {
                    "source_id": "AREA_TEST_ESZone1",
                    "name": "AREA_TEST_ESZone1",
                    "members": [],
                }
            ],
        }
        # Simulate prefer: score disk higher → union keeps engineer members
        merged = self._union(mem, disk)
        self.assertIsNotNone(merged)
        zones = {z["source_id"]: z for z in merged["zones"]}
        self.assertIn("Zone_Area1_ESZone1", zones)
        self.assertEqual(len(zones["Zone_Area1_ESZone1"]["members"]), 12)
        # Transport hollow zone may coexist but must not erase engineer zone
        if "AREA_TEST_ESZone1" in zones:
            self.assertEqual(len(zones["AREA_TEST_ESZone1"].get("members") or []), 0)

    def test_same_source_id_preserves_members_when_hollow_overwrites(self):
        disk = {
            "appliedAt": "t1",
            "zones": [
                {
                    "source_id": "Z1",
                    "name": "Zone_Area1_ESZone1",
                    "members": ["A", "B", "C"],
                    "membersOrigin": "ENGINEER_ASSIGNED",
                }
            ],
        }
        mem = {
            "source": "transport_engineer",
            "zones": [
                {
                    "source_id": "Z1",
                    "name": "Zone_Area1_ESZone1",
                    "members": [],
                }
            ],
        }
        merged = self._union(mem, disk)
        z = merged["zones"][0]
        self.assertEqual(z["members"], ["A", "B", "C"])


class TestTransportDoesNotReplaceAppliedSafety(unittest.TestCase):
    def test_apply_graph_preserves_members(self):
        from fortna_transport_graph import apply_graph_to_workbook

        wb = {
            "conveyors": [],
            "areas": [{"name": "AREA_TEST"}],
            "safety_build": {
                "source": "safety_build",
                "appliedAt": "2026-09-19T13:00:00Z",
                "zones": [
                    {
                        "source_id": "Zone_Area1_ESZone1",
                        "id": "Zone_Area1_ESZone1",
                        "name": "Zone_Area1_ESZone1",
                        "members": ["ES1", "ES2"],
                        "membersOrigin": "ENGINEER_ASSIGNED",
                        "conveyors": ["P600"],
                    }
                ],
            },
        }
        graph = {
            "areas": [{"name": "AREA_TEST", "nodes": []}],
            "safetyBuild": {
                "source": "transport_engineer",
                "zones": [
                    {
                        "source_id": "Zone_Area1_ESZone1",
                        "name": "Zone_Area1_ESZone1",
                        "members": [],
                        "conveyors": ["P600", "P610"],
                    }
                ],
            },
        }
        out = apply_graph_to_workbook(graph, wb)
        sb = out["workbook"]["safety_build"]
        self.assertTrue(sb.get("appliedAt"), msg=f"appliedAt lost: {sb}")
        z = next(
            x for x in sb["zones"] if (x.get("source_id") or x.get("id")) == "Zone_Area1_ESZone1"
        )
        self.assertEqual(z["members"], ["ES1", "ES2"])
        # Conveyor enrichment allowed
        convs = z.get("conveyors") or []
        self.assertIn("P610", convs)


class TestFinalArtifactPackOrphans(unittest.TestCase):
    def test_detects_p506_orphans(self):
        from fortna_final_artifact_closure import validate_final_artifact

        fake = '''
        <Tag Name="P610_Divert1" DataType="Track_Divert_UDT"/>
        <Tag Name="P506_Divert1" DataType="Track_Divert_UDT"/>
        <Tag Name="Default_Area_ESZone1" DataType="ES_UDT"/>
        '''
        r = validate_final_artifact(l5x_text=fake, machine="ORINDYAC6", allowed_divert_hosts=["P610"])
        self.assertEqual(r["status"], "FAIL")
        self.assertTrue(any("PACK_TEMPLATE" in e for e in r["errors"]))
        self.assertTrue(any("DEFAULT_SAFETY" in e for e in r["errors"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)

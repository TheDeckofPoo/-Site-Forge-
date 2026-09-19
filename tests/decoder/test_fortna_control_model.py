#!/usr/bin/env python3
"""FortnaPlus control model regressions — Gates D–G / N."""
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
import unittest
from pathlib import Path

SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
import sys

sys.path.insert(0, str(SCRIPTS))

from fortna_control_model import (  # noqa: E402
    build_control_models,
    classify_conveyor_row,
    merge_control_into_workbook,
)

CP5_RUN = ROOT / "workspace" / "cp5-run" / "RUN"
PLC2_RUN = ROOT / "workspace" / "_plc2_run_peek" / "RUN"
PROD = SCRIPTS / "fortna_control_model.py"


class TestClassifyConveyorRow(unittest.TestCase):
    def test_type_invalid_named_is_logical_not_discard(self) -> None:
        cls = classify_conveyor_row(
            {
                "IO_Name": "ENABLE_SAWTOOTH",
                "Type": "INVALID",
                "IO_Module_Type": "N/A",
                "IO_Address_Word": "450",
                "IO_Address_Bit": "13",
            }
        )
        self.assertEqual(cls["semanticClass"], "LOGICAL_SIGNAL")
        self.assertIsNone(cls["physicalEndpoint"])
        self.assertFalse(cls["discard"])

    def test_field_invalid_identity_absent(self) -> None:
        cls = classify_conveyor_row({"IO_Name": "INVALID", "Type": "INVALID"})
        self.assertEqual(cls["semanticClass"], "ABSENT_REFERENCE")
        self.assertTrue(cls["discard"])

    def test_physical_motor_not_logical(self) -> None:
        cls = classify_conveyor_row(
            {"IO_Name": "M116", "Type": "MOTOR", "IO_Address_Word": "402", "IO_Address_Bit": "0"}
        )
        self.assertEqual(cls["semanticClass"], "PHYSICAL_EQUIPMENT")
        self.assertNotEqual(cls["physicalEndpoint"], None)

    def test_no_name_pattern_authority(self) -> None:
        # Same Type=INVALID classification regardless of MEM_/ENABLE_/LATCH_ prefix
        a = classify_conveyor_row({"IO_Name": "FOO_BAR_XYZ", "Type": "INVALID", "IO_Module_Type": "N/A"})
        b = classify_conveyor_row({"IO_Name": "MEM_CP4_8_START", "Type": "INVALID", "IO_Module_Type": "N/A"})
        self.assertEqual(a["semanticClass"], b["semanticClass"])


@unittest.skipUnless(CP5_RUN.is_dir(), "CP5 RUN missing")
class TestControlModelCp5(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = build_control_models(CP5_RUN, "ORNCCP5")

    def test_startstop_decode(self) -> None:
        ss = self.model["startstop"]
        self.assertGreaterEqual(ss["zone_count"], 1)
        names = {z["name"] for z in ss["zones"]}
        self.assertNotIn("INVALID", names)
        # generic fields present
        z = ss["zones"][0]
        for k in ("startReqFlag", "stopReqFlag", "state", "startOwnerCtl", "stopOwnerCtl"):
            self.assertIn(k, z)

    def test_jam_decode_and_refs(self) -> None:
        jam = self.model["jam"]
        self.assertGreaterEqual(jam["zone_count"], 1)
        z = next(x for x in jam["zones"] if x["name"] != "INVALID")
        refs = z["references"]
        self.assertIn("Enable Bit", refs)
        self.assertIn("Start Stop Timer", refs)
        self.assertIn("StartStopZone", refs)
        # timer → timemenu class
        timer = refs["Start Stop Timer"]
        if timer["status"] == "RESOLVED":
            self.assertEqual(timer["semanticClass"], "TIMER")
            self.assertEqual(timer["targetMenu"], "timemenu")

    def test_logical_referenced_survives(self) -> None:
        ls = self.model["logical_signals"]
        self.assertGreaterEqual(ls["referenced_count"], 1)
        by = {s["name"]: s for s in ls["signals"]}
        # Proven referenced logicals from Jamzones (generic Type=INVALID path)
        for name in ("ENABLE_SAWTOOTH", "LATCH_TAKEAWAY", "MEM_CP4_8_START"):
            if name not in by:
                continue
            s = by[name]
            self.assertEqual(s["semanticClass"], "LOGICAL_SIGNAL")
            self.assertIsNone(s["physicalEndpoint"])
            self.assertTrue(s["referenced"])

    def test_logical_not_physical_io(self) -> None:
        for s in self.model["logical_signals"]["signals"]:
            self.assertIsNone(s["physicalEndpoint"])

    def test_absent_field_stays_absent(self) -> None:
        found_absent = False
        for z in self.model["jam"]["zones"]:
            for slot in (z.get("references") or {}).values():
                if slot.get("status") == "ABSENT":
                    found_absent = True
                    self.assertEqual(slot["semanticClass"], "ABSENT_REFERENCE")
                    self.assertIsNone(slot["targetIdentity"])
        self.assertTrue(found_absent)

    def test_jam_to_startstop_edge(self) -> None:
        edges = self.model["control_graph"]["edges"]
        ss_edges = [e for e in edges if e.get("type") == "belongs_to_startstop_zone"]
        self.assertGreaterEqual(len(ss_edges), 1)

    def test_no_site_hardcodes_in_production(self) -> None:
        text = PROD.read_text(encoding="utf-8", errors="replace")
        self.assertNotRegex(text, r"""machine\s*==\s*['\"]ORNCCP""")
        self.assertNotIn("ENABLE_SAWTOOTH", text)
        self.assertNotIn("MEM_CP4_8_START", text)
        self.assertNotIn("LATCH_TAKEAWAY", text)
        self.assertNotIn("Greensboro", text)
        # no CR#### / *_MEM pattern classifiers
        self.assertIsNone(re.search(r"endswith\(['\"]_MEM['\"]\)|startswith\(['\"]CR", text))


class TestCanonicalControlMerge(unittest.TestCase):
    def test_control_survives_sibling_applies(self) -> None:
        disk: dict = {}
        disk = merge_control_into_workbook(
            disk,
            {},
            control={"version": 1, "startstop": {"zone_count": 2}},
        )
        # Apply Safety hollow mem
        disk = merge_control_into_workbook(
            disk,
            {"conveyors": [], "safety_build": {"zones": [{"name": "A_ES"}]}},
        )
        self.assertEqual(disk["control_build"]["startstop"]["zone_count"], 2)
        self.assertEqual(disk["safety_build"]["zones"][0]["name"], "A_ES")
        # Apply Transport again
        disk = merge_control_into_workbook(
            disk,
            {"conveyors": [{"conveyor": "P1"}]},
        )
        self.assertEqual(disk["conveyors"][0]["conveyor"], "P1")
        self.assertEqual(disk["control_build"]["startstop"]["zone_count"], 2)
        # Apply Sorter
        disk = merge_control_into_workbook(
            disk,
            {"sorter_build": {"plc_generation": "NOT_STARTED"}},
        )
        self.assertEqual(disk["sorter_build"]["plc_generation"], "NOT_STARTED")
        self.assertEqual(disk["control_build"]["startstop"]["zone_count"], 2)


@unittest.skipUnless(PLC2_RUN.is_dir(), "PLC2 RUN missing")
class TestControlModelPlc2Blind(unittest.TestCase):
    def test_builds_without_site_branch(self) -> None:
        m = build_control_models(PLC2_RUN, "ORNCCP2")
        self.assertIn("startstop", m)
        self.assertIn("jam", m)
        self.assertIn("logical_signals", m)
        self.assertEqual(m["plc_generation"], "NOT_STARTED")


if __name__ == "__main__":
    unittest.main(verbosity=2)

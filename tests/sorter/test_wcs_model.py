#!/usr/bin/env python3
"""WCSModel discovery — ORINDYAC6 virgin RUN evidence; no sorter auto-enable."""
from __future__ import annotations
# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys
_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO
REPO_ROOT = _SF_REPO
# --- end bootstrap ---

import unittest
from pathlib import Path

from fortna_wcs_compiler import compile_wcs_pack, should_emit_wcs
from fortna_wcs_model import (
    ENGINEER_ASSIGNED,
    PROVEN,
    REVIEW_REQUIRED,
    build_wcs_model,
    discover,
    discover_wcs_evidence,
)

ORINDY_RUN = ROOT / "workspace" / "_virgin_orindy" / "RUN"
GREENSBORO_NAMES = (
    "P504_Induct_Decision_Request_Helix",
    "P506_Divert1",
    "DP1_L1_DivertedLane_str",
    "ORLY_Greensboro_NC_PLC5",
)


class TestOrindyWcsDiscovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not ORINDY_RUN.is_dir():
            raise unittest.SkipTest(f"ORINDY virgin RUN missing: {ORINDY_RUN}")
        if not (ORINDY_RUN / "FORTNA" / "WCSEvents.asc").is_file():
            raise unittest.SkipTest("ORINDY WCSEvents.asc missing")

    def test_evidence_fields_present(self) -> None:
        ev = discover_wcs_evidence(ORINDY_RUN, "ORINDYAC6")
        counts = ev["counts"]
        self.assertGreater(counts["msgwcs_active"], 0)
        self.assertGreater(counts["wcs_events_enabled"], 0)
        self.assertGreaterEqual(counts["msgmap_wcs_rows"], 1)
        self.assertGreaterEqual(counts["wcs_machine_peers"], 1)
        self.assertIn("MsgWCS", ev["tables"])
        self.assertIn("WCSEvents", ev["tables"])
        self.assertTrue(ev["tables"]["MsgWCS"]["exists"])
        self.assertEqual(ev["tables"]["MsgWCS"]["authority"], PROVEN)

    def test_enabled_false_until_engineer_or_proven(self) -> None:
        model = build_wcs_model(
            ORINDY_RUN,
            "ORINDYAC6",
            sorter_present=True,
        )
        self.assertFalse(model["enabled"])
        self.assertTrue(model["sorter_does_not_enable_wcs"])
        self.assertTrue(model["sorter_present"])
        enable = model["enable"]
        self.assertFalse(enable["value"])
        self.assertEqual(enable["authority"], REVIEW_REQUIRED)
        # Evidence still populated
        self.assertGreater(model["evidence"]["msgwcs_active"]["value"], 0)
        self.assertGreater(model["evidence"]["wcs_events_enabled"]["value"], 0)

    def test_engineer_enable_turns_on(self) -> None:
        model = build_wcs_model(
            ORINDY_RUN,
            "ORINDYAC6",
            wcs_build={"enabled": True, "tcp_endpoint": {"host": "10.0.0.5", "port": "44818"}},
            sorter_present=False,
        )
        self.assertTrue(model["enabled"])
        self.assertEqual(model["enable"]["authority"], ENGINEER_ASSIGNED)

    def test_no_greensboro_tag_names_invented(self) -> None:
        bundle = discover(ORINDY_RUN, "ORINDYAC6")
        blob = str(bundle)
        for name in GREENSBORO_NAMES:
            self.assertNotIn(name, blob, msg=f"must not invent {name}")
        # Lane strings empty / REVIEW — not copied from gold
        lanes = bundle["model"]["lane_strings"]
        self.assertEqual(lanes["value"], [])
        self.assertEqual(lanes["authority"], REVIEW_REQUIRED)


class TestWcsCompilerGate(unittest.TestCase):
    def test_sorter_alone_does_not_emit(self) -> None:
        self.assertFalse(should_emit_wcs(None, {"enabled": False}, sorter_present=True))
        compiled = compile_wcs_pack(sorter_present=True, wcs_model={"enabled": False})
        self.assertFalse(compiled["emitted"])

    def test_engineer_emit_includes_pack_and_task(self) -> None:
        pack = ROOT / "tools" / "libraries" / "programs" / "WCS_Interface_TCP_IP_Program.L5X"
        if not pack.is_file():
            raise unittest.SkipTest("WCS library pack missing")
        compiled = compile_wcs_pack(
            wcs_build={"enabled": True, "divert_host_conveyor": "P610"},
            site_stem="ORINDYAC6",
            divert_host="P610",
            sorter_present=True,
        )
        self.assertTrue(compiled["emitted"])
        self.assertIn("WCS_Interface_TCP_IP", compiled["program_xml"])
        self.assertEqual(compiled["task"]["name"], "P03_WCS_10ms")
        # Remap should not leave Greensboro controller name when site_stem set
        self.assertNotIn("ORLY_Greensboro_NC_PLC5", compiled["program_xml"])


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Program-pack + logical-signal contract integrity (Gates F–I / N)."""
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


import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKS = ROOT / "config" / "program_packs"
EVID = ROOT / "docs" / "evidence"


class TestProgramPackContracts(unittest.TestCase):
    def test_sorter_track_contract(self) -> None:
        p = PACKS / "sorter_track_contract.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data.get("pack_definition_version"), 1)
        self.assertIn(data.get("status"), {"READY_TO_IMPLEMENT", "PHASE1_ACTIVE"})
        self.assertEqual(data.get("phase1_scope"), "hot_emit")
        routines = {r["name"] for r in data.get("routines") or []}
        for need in (
            "Main",
            "Encoder",
            "Track_Induct_Package",
            "Track_Divert_Package",
            "Track_Divert_Confirm",
            "Scanner",
            "RT_Virtual_Enc",
            "Gridlock_Prevention",
        ):
            self.assertIn(need, routines)
        by_name = {r["name"]: r for r in data.get("routines") or []}
        self.assertEqual(by_name["Main"].get("emit_class"), "REQUIRED_STANDARD")
        self.assertEqual(by_name["Gridlock_Prevention"].get("emit_class"), "CONDITIONAL_STANDARD")
        self.assertEqual(by_name["RT_Virtual_Enc"].get("emit_class"), "CONDITIONAL_STANDARD")
        self.assertIn("divert_instances", data.get("expansion_points") or {})
        self.assertIn(
            data.get("compiler_implementation"),
            {"NOT_STARTED", "PHASE1_GENERATED", "PHASE1_ACTIVE"},
        )
        # anti hollow-complete
        self.assertNotEqual(data.get("status"), "COMPLETE")
        self.assertTrue(data.get("gaps_remaining"))

    def test_plc4_plc5_sorter_pack_diff(self) -> None:
        p = PACKS / "plc4_plc5_sorter_pack_diff.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data.get("pack_diff_version"), 1)
        routines = data.get("routines") or {}
        self.assertIn("Gridlock_Prevention", routines.get("PLC5_only") or [])
        self.assertIn("RT_Virtual_Enc", routines.get("PLC5_only") or [])
        self.assertEqual(routines.get("PLC4_only") or [], [])
        rules = {r.get("id") for r in data.get("gate_c_rules") or []}
        self.assertIn("expand_diverts", rules)
        self.assertTrue((EVID / "PLC4_PLC5_SORTER_PROGRAM_PACK_DIFF.md").is_file())

    def test_wcs_contract(self) -> None:
        p = PACKS / "wcs_interface_contract.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data.get("status"), "MORE_EVIDENCE_REQUIRED")
        presence = data.get("presence") or {}
        self.assertTrue(presence.get("PLC5") is True or data.get("plc5_present"))
        self.assertTrue(presence.get("PLC4") is True or data.get("plc4_present"))
        # sorter is not mandatory WCS
        self.assertIs(presence.get("sorter_mandatory", False), False)
        iface = data.get("sorter_wcs_interface") or {}
        if isinstance(iface, dict):
            self.assertGreaterEqual(int(iface.get("proven_shared_controller_tag_count") or 0), 1)
        else:
            self.assertGreaterEqual(len(iface), 1)
        self.assertEqual(data.get("compiler_implementation"), "NOT_STARTED")

    def test_logical_signal_model(self) -> None:
        p = PACKS / "logical_signal_model.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        text = json.dumps(data)
        self.assertIn("Jamzones", text)
        self.assertIn("Mtrchain", text)
        self.assertIn("Conveyor", text)
        self.assertIn("timemenu", text)
        self.assertIn("INVALID", text)
        # must not use name-pattern rules as authority
        self.assertNotIn("if name.endswith('_MEM')", text)

    def test_evidence_docs_exist(self) -> None:
        for name in (
            "SORTER_TRACK_PROGRAM_PACK.md",
            "WCS_PROGRAM_PACK.md",
            "LOGICAL_SIGNAL_MODEL.md",
            "PLC4_PLC5_SORTER_PROGRAM_PACK_DIFF.md",
        ):
            self.assertTrue((EVID / name).is_file(), msg=name)
        self.assertTrue((ROOT / "docs" / "PLC_PROGRAM_PACK_ARCHITECTURE.md").is_file())

    def test_no_site_decision_in_contracts(self) -> None:
        for path in PACKS.glob("*.json"):
            text = path.read_text(encoding="utf-8")
            # Examples may mention oracle paths; forbid decision conditionals
            self.assertNotRegex(text, r"if\s+site\s*==|machine\s*==\s*['\"]ORNCCP5['\"]")


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Program-pack + logical-signal contract integrity (Gates F–I / N)."""
from __future__ import annotations

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
        self.assertEqual(data.get("status"), "MORE_EVIDENCE_REQUIRED")
        routines = {r["name"] for r in data.get("routines") or []}
        for need in (
            "Main",
            "Encoder",
            "Track_Induct_Package",
            "Track_Divert_Package",
            "Track_Divert_Confirm",
            "Scanner",
            "RT_Virtual_Enc",
        ):
            self.assertIn(need, routines)
        self.assertEqual(data.get("compiler_implementation"), "NOT_STARTED")
        # anti hollow-complete
        self.assertNotEqual(data.get("status"), "COMPLETE")
        self.assertNotEqual(data.get("status"), "READY_TO_IMPLEMENT")

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

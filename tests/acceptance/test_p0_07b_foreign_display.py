#!/usr/bin/env python3
"""P0-07b — FOREIGN_CONTROLLER canonical ownership must win over blank fields.

Known Ship devices in gold escalation:
  ESLS1, ESLS13P7-1, ESLS13P7-2, ESLS13P9-1 → FOREIGN_CONTROLLER — MSCRENOSHIP

Must never render as REVIEW_REQUIRED · UNKNOWN_OWNER merely because Safety
model left machine/controller blank.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLD_ESC = (
    ROOT
    / "exports"
    / "diagnostics"
    / "gold_repro_7c08e71_20261013-160513"
    / "workspace"
    / "io_canonical_escalation_snapshot.json"
)
GOLD_SM = (
    ROOT
    / "exports"
    / "diagnostics"
    / "gold_repro_7c08e71_20261013-160513"
    / "plc2-safety"
    / "safety_model_MSCRENOPICK.json"
)
FOREIGN = ["ESLS1", "ESLS13P7-1", "ESLS13P7-2", "ESLS13P9-1"]


class TestP007bForeignDisplay(unittest.TestCase):
    def test_gold_escalation_foreign_controller(self) -> None:
        self.assertTrue(GOLD_ESC.is_file())
        snap = json.loads(GOLD_ESC.read_text(encoding="utf-8"))
        by = {
            (d.get("canonical_name") or d.get("name")): d
            for d in (snap.get("devices") or [])
        }
        for n in FOREIGN:
            self.assertIn(n, by, n)
            d = by[n]
            self.assertEqual(d.get("final_status"), "FOREIGN_CONTROLLER", n)
            self.assertEqual(d.get("evidence_class"), "FOREIGN_CONTROLLER", n)
            ctrl = (
                d.get("controller")
                or (d.get("peer_controllers") or [None])[0]
                or d.get("peer_controller")
            )
            self.assertEqual(ctrl, "MSCRENOSHIP", n)

    def test_gold_safety_model_blank_machine_is_the_defect_fixture(self) -> None:
        """Preserve the disagreement: SM stamped UNKNOWN while ledger is FOREIGN."""
        self.assertTrue(GOLD_SM.is_file())
        sm = json.loads(GOLD_SM.read_text(encoding="utf-8"))
        devices = sm.get("devices") or sm.get("safetyDevices") or []
        by = {(d.get("name") or d.get("id")): d for d in devices if isinstance(d, dict)}
        # At least one foreign candidate lost machine in the gold SM
        lost = [
            n
            for n in FOREIGN
            if n in by and not str(by[n].get("machine") or by[n].get("controller") or "").strip()
        ]
        self.assertTrue(
            lost,
            "gold SM should show blank machine on foreign rows (repro of UI downgrade)",
        )

    def test_ui_join_contract_js(self) -> None:
        gate = ROOT / "tests" / "ui" / "test_safety_foreign_canonical_join.js"
        self.assertTrue(gate.is_file())
        r = subprocess.run(
            ["node", str(gate)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()

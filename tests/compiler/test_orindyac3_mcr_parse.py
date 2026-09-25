#!/usr/bin/env python3
"""ORINDYAC3 MCR trigger parse — GATE A (bare ~IF + multi-word FIRE)."""
from __future__ import annotations
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_run_logic_triggers import mcr_command_writers_from_run, parse_logic_asc

AC3 = ROOT / "workspace" / "_orindyac3_run" / "RUN"


@unittest.skipUnless(AC3.is_dir(), "ORINDYAC3 RUN not extracted")
class TestOrindyAc3McrParse(unittest.TestCase):
    def test_trigger_27_preserves_ps210(self) -> None:
        """Bare ~IF (no AND) must not drop PS210."""
        t27 = next(t for t in parse_logic_asc(AC3) if t["trigger"] == 27)
        ios = [c["io"] for c in t27["conditions"]]
        self.assertEqual(ios, ["3ESR1AUX", "PS210"])
        w = next(x for x in mcr_command_writers_from_run(AC3) if x.get("coil") == "3MCR1")
        self.assertEqual(w.get("status"), "PROVEN")
        self.assertEqual(w.get("condition_count"), 2)
        self.assertIn("PS210", w.get("rung") or "")
        self.assertIn("3ESR1AUX", "".join(c.get("io") or "" for c in w.get("conditions") or []))

    def test_trigger_5_does_not_invent_fire_bool(self) -> None:
        """FIRE ALARM ACTIVE must not truncate to invented FIRE BOOL as PROVEN."""
        t5 = next(t for t in parse_logic_asc(AC3) if t["trigger"] == 5)
        ios = [c["io"] for c in t5["conditions"]]
        self.assertEqual(len(ios), 3)
        self.assertIn("4ESR1AUX", ios)
        self.assertIn("PS202", ios)
        self.assertNotIn("FIRE", ios)  # truncated form forbidden
        self.assertTrue(
            any("FIRE_ALARM" in (c.get("io") or "") for c in t5["conditions"]),
            msg=f"expected FIRE_ALARM_* identity, got {ios}",
        )
        w = next(x for x in mcr_command_writers_from_run(AC3) if x.get("coil") == "4MCR1")
        # Unbound multi-word → REVIEW, never PROVEN with invented FIRE
        self.assertEqual(w.get("status"), "REVIEW_REQUIRED")
        self.assertEqual(len(w.get("conditions") or []), 3)
        self.assertNotIn("XIC(FIRE)", w.get("rung") or "")


if __name__ == "__main__":
    unittest.main(verbosity=2)

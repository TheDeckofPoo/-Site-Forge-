#!/usr/bin/env python3
"""MSCRENOPICK Safety inventory — current-machine ESPB eligible, foreign excluded."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

_SF_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SF_REPO / "tools" / "scripts"))

RUN = (
    _SF_REPO
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
    / "RUN"
)


@unittest.skipUnless((RUN / "project.cfg").is_file(), "MSCRENOPICK RUN missing")
class TestMscrenoPickSafetyInventory(unittest.TestCase):
    def test_current_site_espb_eligible(self) -> None:
        from fortna_safety_model import discover_safety_devices, build_safety_model

        names = {str(d.get("name") or "").upper() for d in discover_safety_devices(RUN, "MSCRENOPICK")}
        for n in ("ESPB24", "ESPB2", "ESLS2", "ESPB32"):
            self.assertIn(n, names, f"{n} must be available on virgin MSCRENOPICK")
        # Foreign pack pushbuttons must not appear
        for n in ("ESPB27", "ESPB3", "ESPB4", "ESPB6"):
            self.assertNotIn(n, names)

        model = build_safety_model(
            run_dir=RUN,
            machine="MSCRENOPICK",
            engineer_safety_build={"zones": [{"name": "pick_one_ESZone1", "members": []}]},
        )
        unassigned = {str(x).upper() for x in (model.get("unassignedDevices") or [])}
        self.assertTrue(unassigned, "Safety eligible list must be non-empty")
        for n in ("ESPB24", "ESPB2", "ESPB32"):
            self.assertIn(n, unassigned)


if __name__ == "__main__":
    unittest.main(verbosity=2)

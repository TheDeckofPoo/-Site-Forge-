#!/usr/bin/env python3
"""Atlanta: deterministic I/O claim ledger must surface ESR/MCR into Safety inventory.

Candidates appear as UNASSIGNED — never invisible, never auto-zoned.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_safety_model import build_safety_model, discover_safety_devices  # noqa: E402

ATL_RUN = _SF_REPO / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN"
MACHINE = "MSCATL_CP3"

REQUIRED = {
    "T_3MCR1_AUX": "MCR",
    "T_3ESR1": "ESR",
    "T_3ESR2": "ESR",
    "T_3ESR3": "ESR",
}


class TestAtlantaIoSafetyBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not (ATL_RUN / "FORTNA").is_dir():
            raise unittest.SkipTest("Atlanta RUN peek missing")

    def test_discover_surfaces_mcr_esr(self) -> None:
        devs = discover_safety_devices(ATL_RUN, MACHINE)
        by_name = {d.get("name"): d for d in devs}
        for name, kind in REQUIRED.items():
            self.assertIn(name, by_name, f"missing Safety inventory candidate {name}")
            self.assertEqual(by_name[name].get("kind"), kind)

    def test_model_keeps_candidates_unassigned(self) -> None:
        model = build_safety_model(run_dir=ATL_RUN, machine=MACHINE)
        inv = {d.get("name"): d for d in (model.get("devices") or [])}
        for name in REQUIRED:
            self.assertIn(name, inv)
            # Must not be silently omitted; zone membership unknown → UNASSIGNED
            # (Default Safety ownership bucket is OK — not an engineer ES zone).
            d = inv[name]
            zone = d.get("zone") or d.get("safetyZoneRef") or d.get("zoneName") or ""
            status = str(d.get("status") or "").upper()
            self.assertEqual(status, "UNASSIGNED", f"{name} status={status!r}")
            zu = str(zone).upper()
            self.assertTrue(
                zu in {"", "UNASSIGNED", "DEFAULT", "DEFAULT SAFETY"}
                or bool(d.get("defaultSafety")),
                f"{name} unexpectedly in engineer zone: zone={zone!r}",
            )
        counts = model.get("counts") or {}
        self.assertGreaterEqual(int(counts.get("esr") or 0), 3)
        self.assertGreaterEqual(int(counts.get("mcr") or 0), 1)
        self.assertGreaterEqual(int(counts.get("unassigned") or 0), 4)


if __name__ == "__main__":
    unittest.main()

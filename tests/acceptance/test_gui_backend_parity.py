#!/usr/bin/env python3
"""GUI contract vs backend canonical models — Safety + Hardware parity."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

_SF_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SF_REPO / "tools" / "scripts"))

from fortna_visual_qualification import build_gui_backend_parity  # noqa: E402

RUN = (
    _SF_REPO
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
    / "RUN"
)


@unittest.skipUnless((RUN / "project.cfg").is_file(), "MSCRENOPICK RUN missing")
class TestGuiBackendParity(unittest.TestCase):
    def test_safety_and_hardware_parity_contracts(self) -> None:
        r = build_gui_backend_parity(RUN, "MSCRENOPICK")
        self.assertTrue(r.get("ok"), r.get("failures"))
        s = r["safety"]
        self.assertEqual(s["devices_found"], s["unassigned"] + s["automatically_resolved"] + s["engineer_assigned"])
        self.assertEqual(s["unassigned"], s["gui_available_count"])
        adapters = r["hardware"]["adapters"]
        names = {str(a.get("rio_name") or "").upper() for a in adapters}
        # Canonical RUN identities for this machine (not AENTR13 concatenation)
        self.assertTrue({"AENTR1", "AENTR2", "AENTR3"} <= names)
        self.assertNotIn("AENTR13", names)
        states = r["hardware"]["owner_states"]
        self.assertIn("ASSIGNED", states)
        self.assertIn("UNRESOLVED_OWNER", states)
        # Must not pretend every channel is assigned
        self.assertGreaterEqual(int(states.get("ASSIGNED") or 0), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

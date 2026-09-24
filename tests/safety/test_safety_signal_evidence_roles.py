"""Related-signal classification under a canonical SafetyDevice (not aliases)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "tools" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fortna_safety_model import reconcile_safety_devices  # noqa: E402


class TestMcrMultiPhysicalSignals(unittest.TestCase):
    def test_two_physical_one_naming_variant_one_device(self):
        signals = [
            {
                "name": "3MCR1",
                "kind": "MCR",
                "physicalEndpoint": "AENTR:I.Data[1].0",
                "sources": ["HW"],
                "evidence": [],
            },
            {
                "name": "3MCR1_AUX",
                "kind": "MCR",
                "physicalEndpoint": "AENTR:I.Data[1].1",
                "sources": ["HW"],
                "evidence": [],
            },
            {
                "name": "T_3MCR1",
                "kind": "MCR",
                "physicalEndpoint": "",
                "sources": ["RUN"],
                "evidence": [],
            },
        ]
        recon = reconcile_safety_devices(signals)
        devices = recon.get("devices") or []
        self.assertEqual(len(devices), 1, devices)
        d = devices[0]
        sigs = d.get("signals") or []
        self.assertEqual(len(sigs), 3)
        phys = [
            s for s in sigs
            if str(s.get("physicalEndpoint") or "").strip()
        ]
        nonphys = [
            s for s in sigs
            if not str(s.get("physicalEndpoint") or "").strip()
        ]
        self.assertEqual(len(phys), 2)
        self.assertEqual(len(nonphys), 1)
        endpoints = {str(s.get("physicalEndpoint")) for s in phys}
        self.assertEqual(endpoints, {"AENTR:I.Data[1].0", "AENTR:I.Data[1].1"})
        # Must not invent a second canonical device for AUX
        self.assertEqual(len(devices), 1)


class TestUiTerminology(unittest.TestCase):
    def test_js_uses_related_signals_not_aliases(self):
        src = (REPO / "dashboard" / "safety-build.js").read_text(encoding="utf-8")
        self.assertIn("related signal", src)
        self.assertIn("classifyRelatedSafetySignal", src)
        self.assertNotIn("alias(es)", src)


if __name__ == "__main__":
    unittest.main()

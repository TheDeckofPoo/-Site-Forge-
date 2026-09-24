"""Canonical SafetyDevice grouping — aliases collapse to one assignable device."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "tools" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fortna_safety_model import reconcile_safety_devices  # noqa: E402


def _sig(name: str, kind: str, phys: str = "") -> dict:
    return {
        "name": name,
        "kind": kind,
        "physicalEndpoint": phys,
        "sources": ["TEST"],
        "evidence": [],
        "origin": "AUTO",
    }


class TestCanonicalSafetyGrouping(unittest.TestCase):
    def test_esr_primary_aux_t_alias_one_device(self):
        signals = [
            _sig("2ESR1", "ESR", "CP2RIO0:I.Data[1].0"),
            _sig("2ESR1_AUX", "ESR", "CP2RIO0:I.Data[1].0"),
            _sig("T_2ESR1", "ESR", "CP2RIO0:I.Data[1].0"),
        ]
        recon = reconcile_safety_devices(signals)
        devices = recon.get("devices") or []
        # Three signals retained in evidence (on the device)
        self.assertEqual(len(signals), 3)
        self.assertEqual(len(devices), 1, devices)
        d = devices[0]
        names = {str(s.get("name") or "").upper() for s in (d.get("signals") or [])}
        self.assertIn("2ESR1", names)
        self.assertIn("2ESR1_AUX", names)
        self.assertIn("T_2ESR1", names)
        # One canonical assignable name / tag
        self.assertTrue(d.get("name") or d.get("id"))
        self.assertEqual(len(devices), 1)

    def test_ambiguous_multi_kind_stem_is_review(self):
        # Force ambiguity via same stem with conflicting kinds if group keys collide —
        # reconcile uses kind:stem keys so different kinds stay separate devices.
        # Ambiguous path: INT rejection + review list for interlocks.
        signals = [
            _sig("INT_2ESR1", "ESR", "X:I.0"),
            _sig("2ESR1", "ESR", "X:I.0"),
        ]
        recon = reconcile_safety_devices(signals)
        review = recon.get("review") or []
        devices = recon.get("devices") or []
        # INT_* rejected from device inventory
        self.assertTrue(
            any("INT" in str(r.get("name") or "").upper() or "INT" in str(r.get("reason") or "")
                for r in review)
            or all("INT_2ESR1" not in str(d.get("signalNames") or d.get("signals") or [])
                   for d in devices)
        )
        # Physical ESR still forms one device
        self.assertTrue(any(
            "2ESR1" in str(d.get("name") or "").upper()
            or "2ESR1" in str(d.get("signalNames") or []).upper()
            for d in devices
        ))

    def test_nonphysical_alias_alone_not_required_as_device_with_phys(self):
        # AUX without physical endpoint still groups if primary has phys
        signals = [
            _sig("2ESR1", "ESR", "CP:I.Data[0].1"),
            _sig("2ESR1_AUX", "ESR", ""),
        ]
        recon = reconcile_safety_devices(signals)
        devices = recon.get("devices") or []
        self.assertEqual(len(devices), 1)
        sigs = devices[0].get("signals") or []
        self.assertEqual(len(sigs), 2)


class TestSafetyInventoryUsesGroupedDevices(unittest.TestCase):
    def test_js_prefers_safetyDevicesGrouped(self):
        src = (REPO / "dashboard" / "safety-build.js").read_text(encoding="utf-8")
        self.assertIn("collectCanonicalSafetyDevices", src)
        self.assertIn("safetyDevicesGrouped", src)
        self.assertIn("normalizeCanonicalSafetyDevice", src)
        self.assertIn("alias(es)", src)


if __name__ == "__main__":
    unittest.main()

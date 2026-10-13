#!/usr/bin/env python3
"""P0-16 / P0-16u — one canonical Safety device classifier across layers.

ESPB2 / ESPB24 / ESPB32 → ESTOP
ESLS2 → ESLS

Python model, shared JS module, and Hub diagnostics must agree.
Gold Area_Test1_ESZone1: E-Stops=3, ESLS=1.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_safety_model import _classify_device  # noqa: E402

GOLD = (
    ROOT
    / "exports"
    / "diagnostics"
    / "gold_repro_7c08e71_20261013-160513"
    / "workspace"
    / "autogen_workbook.json"
)


class TestP016SafetyRoleClassifier(unittest.TestCase):
    def test_python_classifier_espb_esls(self) -> None:
        self.assertEqual(_classify_device("ESPB2"), "ESTOP")
        self.assertEqual(_classify_device("ESPB24"), "ESTOP")
        self.assertEqual(_classify_device("ESPB32"), "ESTOP")
        self.assertEqual(_classify_device("ESLS2"), "ESLS")

    def test_gold_zone_role_arrays(self) -> None:
        self.assertTrue(GOLD.is_file(), f"missing gold fixture {GOLD}")
        wb = json.loads(GOLD.read_text(encoding="utf-8"))
        z = (wb.get("safety_build") or {}).get("zones") or []
        self.assertEqual(len(z), 1)
        zone = z[0]
        self.assertEqual(zone.get("eStops"), ["ESPB2", "ESPB24", "ESPB32"])
        self.assertEqual(zone.get("eslsDevices"), ["ESLS2"])
        # Classifier agrees with persisted roles
        for n in zone["eStops"]:
            self.assertEqual(_classify_device(n), "ESTOP", n)
        for n in zone["eslsDevices"]:
            self.assertEqual(_classify_device(n), "ESLS", n)

    def test_shared_js_module_parity(self) -> None:
        js = ROOT / "dashboard" / "safety-device-classify.js"
        self.assertTrue(js.is_file())
        script = f"""
const api = require({json.dumps(str(js))});
const cases = [
  ['ESPB2','ESTOP'],['ESPB24','ESTOP'],['ESPB32','ESTOP'],['ESLS2','ESLS']
];
for (const [n,k] of cases) {{
  const got = api.classifySafetyDeviceKind(n);
  if (got !== k) {{ console.error('FAIL', n, got, 'expected', k); process.exit(2); }}
}}
console.log('OK');
"""
        r = subprocess.run(
            ["node", "-e", script],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OK", r.stdout)


class TestP016uHubDiagnosticsConsumeRoles(unittest.TestCase):
    def test_compile_hub_diagnostics_js_gate(self) -> None:
        gate = ROOT / "tests" / "ui" / "test_compile_hub_safety_diagnostics.js"
        self.assertTrue(gate.is_file())
        r = subprocess.run(
            ["node", str(gate)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("[PASS]", r.stdout)
        # Shared classifier must be loaded by dashboard
        html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
        self.assertIn("safety-device-classify.js", html)
        fp = (ROOT / "dashboard" / "fortna-plus.js").read_text(encoding="utf-8")
        self.assertIn("classifySafetyDeviceKind", fp)


if __name__ == "__main__":
    unittest.main()

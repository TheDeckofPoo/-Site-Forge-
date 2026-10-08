#!/usr/bin/env python3
"""Regression: defect artifact filenames must be Windows-safe."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_l5x_acceptance_auditor import write_generator_defect_case  # noqa: E402
from fortna_run_io_source_ledger import audit_device_resolution  # noqa: E402
from fortna_windows_safe_path import (  # noqa: E402
    WINDOWS_INVALID_CHARS,
    sanitize_windows_filename,
    stable_defect_filename,
)


class TestSanitize(unittest.TestCase):
    def test_strips_comparison_and_reserved(self) -> None:
        raw = "GENERATOR_DEFECT_IO_DEVICE_RESOLUTION_BELOW_THRESHOLD_26.92<85.0.json"
        safe = sanitize_windows_filename(raw)
        for ch in WINDOWS_INVALID_CHARS:
            self.assertNotIn(ch, safe)
        self.assertTrue(safe.endswith(".json"))

    def test_endpoint_colons_and_slashes(self) -> None:
        raw = "AENTR1:I.Data[3].2/path\\bit?.json"
        safe = sanitize_windows_filename(raw)
        for ch in '<>:"/\\|?*':
            self.assertNotIn(ch, safe)

    def test_stable_prefers_code_not_dynamic(self) -> None:
        fname = stable_defect_filename(
            failure_code="IO_DEVICE_RESOLUTION_BELOW_THRESHOLD",
            signature="IO:DEVICE_RESOLUTION_BELOW_THRESHOLD:26.92<85.0",
        )
        self.assertEqual(fname, "GENERATOR_DEFECT_IO_DEVICE_RESOLUTION_BELOW_THRESHOLD.json")
        self.assertNotIn("<", fname)
        self.assertNotIn("26.92", fname)


class TestAuditSignatureStable(unittest.TestCase):
    def test_resolution_failure_signature_has_no_angle_bracket(self) -> None:
        canon = {
            "device_resolution_coverage_pct": 26.92,
            "PHYSICAL_DEVICE_RESOLUTION_PCT": 26.92,
            "critical_unresolved": [],
        }
        fails = audit_device_resolution(canon, threshold_pct=85.0)
        self.assertTrue(fails)
        sig = fails[0]["signature"]
        self.assertNotIn("<", sig)
        self.assertEqual(sig, "IO:DEVICE_RESOLUTION_BELOW_THRESHOLD")
        self.assertEqual(fails[0]["actual"], 26.92)
        self.assertEqual(fails[0]["required"], 85.0)
        self.assertEqual(fails[0]["detail"]["actual"], 26.92)
        self.assertEqual(fails[0]["detail"]["required"], 85.0)


class TestWriteGeneratorDefectCase(unittest.TestCase):
    def test_writes_windows_safe_stable_name_with_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            # Legacy-style signature that previously crashed Windows
            legacy_sig = "IO:DEVICE_RESOLUTION_BELOW_THRESHOLD:26.92<85.0"
            path = write_generator_defect_case(
                out,
                manifest={"machine": "MSCRENOPICK"},
                signature=legacy_sig,
                tickets=[
                    {
                        "code": "IO_DEVICE_RESOLUTION_BELOW_THRESHOLD",
                        "signature": "IO:DEVICE_RESOLUTION_BELOW_THRESHOLD",
                        "detail": {"actual": 26.92, "required": 85.0},
                    }
                ],
                attempts=[],
                l5x_paths=[],
                ai_responses=[],
                relay_responses=[],
                failure_code="IO_DEVICE_RESOLUTION_BELOW_THRESHOLD",
                actual=26.92,
                required=85.0,
                detail={"actual": 26.92, "required": 85.0, "gate": "ENGINEERING_RESOLUTION_FAIL"},
            )
            self.assertTrue(path.is_file())
            self.assertEqual(
                path.name,
                "GENERATOR_DEFECT_IO_DEVICE_RESOLUTION_BELOW_THRESHOLD.json",
            )
            for ch in WINDOWS_INVALID_CHARS:
                self.assertNotIn(ch, path.name)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["actual"], 26.92)
            self.assertEqual(data["required"], 85.0)
            self.assertIn("signature", data)
            # Signature preserved in report (may be legacy or stable)
            self.assertTrue(str(data["signature"]).startswith("IO:DEVICE_RESOLUTION_BELOW_THRESHOLD"))


if __name__ == "__main__":
    unittest.main()

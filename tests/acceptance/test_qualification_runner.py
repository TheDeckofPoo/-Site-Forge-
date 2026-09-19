#!/usr/bin/env python3
"""Acceptance tests for Site Forge Qualification Runner."""
from __future__ import annotations

# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys

_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO
REPO_ROOT = _SF_REPO
# --- end bootstrap ---

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(SCRIPTS))

from fortna_qualification_runner import (  # noqa: E402
    CROSS_SUBSYSTEM_STATE_REGRESSION,
    run_compare,
    run_qualify,
)

VIRGIN = ROOT / "workspace" / "_virgin_orindy" / "RUN"
MACHINE = "ORINDYAC6"

REQUIRED_REPORT_FILES = (
    "qualification_report.md",
    "qualification_report.json",
    "handoff_snapshots.json",
    "generation_manifest.json",
    "active_tables.json",
    "machine_closure.json",
    "final_artifact_validation.json",
)


class TestQualificationVirginOrindy(unittest.TestCase):
    @unittest.skipUnless(VIRGIN.is_dir(), "workspace/_virgin_orindy/RUN not present")
    def test_virgin_orindy_produces_report_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "qual"
            report = run_qualify(
                run_dir=VIRGIN,
                machine=MACHINE,
                mode="virgin",
                out_dir=out,
                skip_generate=True,
                sanitized=True,
            )
            self.assertIn(report.get("overall"), {"PASS", "REVIEW", "FAIL"})
            self.assertEqual(report.get("mode"), "virgin")
            self.assertFalse(report.get("reference_used_in_discovery"))
            for name in REQUIRED_REPORT_FILES:
                path = out / name
                self.assertTrue(path.is_file(), f"missing {name}")
            dash = report.get("dashboard") or {}
            self.assertIn("table_resolution_machine_closure", dash)
            self.assertIn("safety", dash)
            self.assertIn("sorter", dash)
            # Virgin must not invent Safety members
            snaps = json.loads((out / "handoff_snapshots.json").read_text(encoding="utf-8"))
            before = (snaps.get("snapshots") or {}).get("safety_before_apply") or {}
            self.assertEqual(int(before.get("operational_member_count") or 0), 0)


class TestQualificationCompareRegression(unittest.TestCase):
    def test_compare_detects_safety_member_regression(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = root / "qual_a"
            b = root / "qual_b"
            a.mkdir()
            b.mkdir()
            # A: healthy Apply with members that reach Autogen
            _write(
                a / "handoff_snapshots.json",
                {
                    "snapshots": {
                        "safety_after_apply": {
                            "operational_member_count": 12,
                            "member_count": 12,
                        },
                        "autogen_input_summary": {
                            "safety_build_members": {"operational_member_count": 12}
                        },
                    }
                },
            )
            _write(
                a / "qualification_report.json",
                {"dashboard": {"safety": "PASS"}, "overall": "PASS"},
            )
            # B: Apply had members, Autogen saw zero → CROSS_SUBSYSTEM_STATE_REGRESSION
            _write(
                b / "handoff_snapshots.json",
                {
                    "snapshots": {
                        "safety_after_apply": {
                            "operational_member_count": 12,
                            "member_count": 12,
                        },
                        "autogen_input_summary": {
                            "safety_build_members": {"operational_member_count": 0}
                        },
                    }
                },
            )
            _write(
                b / "qualification_report.json",
                {"dashboard": {"safety": "FAIL"}, "overall": "FAIL"},
            )
            out = root / "compare"
            result = run_compare(a=a, b=b, out_dir=out)
            self.assertFalse(result.get("ok"))
            self.assertEqual(result.get("overall"), "FAIL")
            codes = [r.get("code") for r in (result.get("regressions") or [])]
            self.assertIn(CROSS_SUBSYSTEM_STATE_REGRESSION, codes)
            self.assertTrue((out / "compare_report.json").is_file())
            self.assertTrue((out / "compare_report.md").is_file())


class TestReferenceNotReadDuringDiscovery(unittest.TestCase):
    @unittest.skipUnless(VIRGIN.is_dir(), "workspace/_virgin_orindy/RUN not present")
    def test_reference_l5x_not_read_during_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ref = root / "FINISHED_ORACLE.L5X"
            sentinel = "REFERENCE_ORACLE_SENTINEL_DO_NOT_READ_IN_DISCOVERY"
            ref.write_text(
                f'<RSLogix5000Content>{sentinel}</RSLogix5000Content>\n',
                encoding="utf-8",
            )
            out = root / "qual"
            reads: list[str] = []

            real_read_text = Path.read_text

            def spy_read_text(self: Path, *args: object, **kwargs: object) -> str:
                reads.append(str(self.resolve()))
                return real_read_text(self, *args, **kwargs)

            with mock.patch.object(Path, "read_text", spy_read_text):
                report = run_qualify(
                    run_dir=VIRGIN,
                    machine=MACHINE,
                    mode="virgin",
                    reference_l5x=ref,
                    out_dir=out,
                    skip_generate=True,
                )

            self.assertFalse(report.get("reference_used_in_discovery"))
            ref_resolved = str(ref.resolve())
            self.assertFalse(
                any(r == ref_resolved or r.endswith("FINISHED_ORACLE.L5X") for r in reads),
                f"reference L5X was read during qualify/discovery: {reads}",
            )
            # Content never ingested
            joined = "\n".join(Path(p).read_text(encoding="utf-8", errors="replace") for p in out.glob("*.json"))
            self.assertNotIn(sentinel, joined)


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(unittest.main(verbosity=2))

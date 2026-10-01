"""Unit tests for Site Forge BUILD ISSUES manifest (fortna_build_issues)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))

from fortna_build_issues import (  # noqa: E402
    SECTION_ORDER,
    build_issues_manifest,
    classify_build_status,
    render_build_issues_txt,
    write_build_issues,
)


class TestUnresolvedIoSection(unittest.TestCase):
    def test_planted_unresolved_io_appears(self) -> None:
        report = {
            "unresolved_io": [
                {
                    "object": "EZPE99_F",
                    "subsystem": "io",
                    "status": "UNRESOLVED",
                    "reason": "No proven physical endpoint",
                }
            ]
        }
        manifest = build_issues_manifest(report, site="TESTSITE")
        items = manifest["UNRESOLVED I/O"]
        self.assertTrue(items)
        objs = {i.get("object/device") for i in items}
        self.assertIn("EZPE99_F", objs)
        txt = render_build_issues_txt(manifest)
        self.assertIn("UNRESOLVED I/O", txt)
        self.assertIn("EZPE99_F", txt)


class TestWithheldMerges(unittest.TestCase):
    def test_withheld_merges_appear(self) -> None:
        report = {
            "merges_withheld_review": ["P2-P18", "P15-P72"],
            "merges_withheld_count": 2,
        }
        manifest = build_issues_manifest(report, site="TESTSITE")
        withheld = manifest["WITHHELD FROM L5X"]
        names = {i.get("object/device") for i in withheld}
        self.assertIn("P2-P18", names)
        self.assertIn("P15-P72", names)
        self.assertEqual(
            classify_build_status(report, structural_ok=True, promoted=False),
            "PARTIAL",
        )


class TestBuildStatusClassification(unittest.TestCase):
    def test_blocked_when_build_failed(self) -> None:
        report = {"build_failed": True, "error": "generation hard fail"}
        self.assertEqual(
            classify_build_status(report, structural_ok=False, promoted=False),
            "BLOCKED",
        )
        manifest = build_issues_manifest(
            report,
            site="TESTSITE",
            l5x_generated=False,
            l5x_promoted=False,
        )
        self.assertEqual(manifest["BUILD STATUS"], "BLOCKED")
        self.assertTrue(manifest["BLOCKERS"])

    def test_partial_when_structurally_ok_with_withheld_merges(self) -> None:
        report = {
            "ok": True,
            "build_failed": False,
            "generation_assertions": {"ok": True, "failures": []},
            "merges_withheld_review": ["P1001-P105A"],
            "symbol_closure": {"ok": True, "failures": [], "failure_count": 0},
            "studio_preflight": {"ok": True, "issues": []},
        }
        self.assertEqual(
            classify_build_status(report, structural_ok=True, promoted=False),
            "PARTIAL",
        )
        manifest = build_issues_manifest(
            report,
            site="TESTSITE",
            l5x_generated=True,
            l5x_promoted=False,
        )
        self.assertEqual(manifest["BUILD STATUS"], "PARTIAL")
        self.assertFalse(manifest["BLOCKERS"])
        self.assertTrue(manifest["WITHHELD FROM L5X"])


class TestTxtRendering(unittest.TestCase):
    def test_txt_contains_required_header_fields(self) -> None:
        report: dict = {}
        manifest = build_issues_manifest(
            report,
            site="ACME_CTRL1",
            git_sha="abc1234",
            tar_hash="deadbeef",
            build_id="20261001-120000",
            timestamp="2026-10-01 12:00:00",
            l5x_generated=True,
            l5x_promoted=False,
            commissioning_ready="NO",
            build_status="PARTIAL",
        )
        txt = render_build_issues_txt(manifest)
        self.assertIn("SITE FORGE BUILD ISSUES", txt)
        self.assertIn("Site/controller:", txt)
        self.assertIn("ACME_CTRL1", txt)
        self.assertIn("Git SHA:", txt)
        self.assertIn("abc1234", txt)
        self.assertIn("TAR/source hash:", txt)
        self.assertIn("deadbeef", txt)
        self.assertIn("Build ID/timestamp:", txt)
        self.assertIn("BUILD STATUS:", txt)
        self.assertIn("PARTIAL", txt)
        self.assertIn("COMMISSIONING READY:", txt)
        self.assertIn("L5X GENERATED:", txt)
        self.assertIn("YES", txt)
        self.assertIn("L5X PROMOTED TO CURRENT:", txt)

    def test_empty_sections_render_none(self) -> None:
        manifest = build_issues_manifest({}, site="EMPTYSITE", build_status="SUCCESS")
        txt = render_build_issues_txt(manifest)
        for section in SECTION_ORDER:
            self.assertIn(section, txt)
        # Every empty section body is the literal "None"
        for section in SECTION_ORDER:
            self.assertEqual(manifest[section], [])
        # Spot-check a few sections render "None" on the following line
        lines = txt.splitlines()
        for section in ("BLOCKERS", "UNRESOLVED I/O", "WITHHELD FROM L5X", "SAFETY"):
            idx = lines.index(section)
            self.assertEqual(lines[idx + 1], "None")


class TestWriteArtifacts(unittest.TestCase):
    def test_write_creates_txt_and_json(self) -> None:
        report = {
            "merges_withheld_review": ["P1-P2"],
            "unresolved_io": [{"device": "DEV_A", "status": "UNKNOWN"}],
        }
        manifest = build_issues_manifest(
            report,
            site="WRITESITE",
            git_sha="fff",
            l5x_generated=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            txt_path, json_path = write_build_issues(manifest, out, site="WRITESITE")
            self.assertEqual(txt_path.name, "WRITESITE_BUILD_ISSUES.txt")
            self.assertEqual(json_path.name, "WRITESITE_BUILD_ISSUES.json")
            self.assertTrue(txt_path.is_file())
            self.assertTrue(json_path.is_file())
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["site"], "WRITESITE")
            self.assertTrue(loaded["WITHHELD FROM L5X"])
            self.assertTrue(loaded["UNRESOLVED I/O"])


if __name__ == "__main__":
    unittest.main()

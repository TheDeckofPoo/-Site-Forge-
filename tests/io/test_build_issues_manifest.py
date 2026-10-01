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
        self.assertIn("TAR SHA256:", txt)
        self.assertIn("deadbeef", txt)
        self.assertIn("RUN fingerprint:", txt)
        self.assertIn("Build ID:", txt)
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


class TestOri103Completeness(unittest.TestCase):
    def test_named_unresolved_io_not_count_only(self) -> None:
        report = {
            "stage0": {"CLAIMS_UNRESOLVED": 2},
            "unresolved_io_names": ["EZSSV15", "EZSSV18"],
            "symbol_closure": {"ok": True, "failures": [], "failure_count": 0},
        }
        manifest = build_issues_manifest(report, site="MSCRENOPICK", build_status="PARTIAL")
        objs = {i.get("object/device") for i in manifest["UNRESOLVED I/O"]}
        self.assertIn("EZSSV15", objs)
        self.assertIn("EZSSV18", objs)
        txt = render_build_issues_txt(manifest)
        self.assertIn("EZSSV15", txt)
        self.assertIn("EZSSV18", txt)
        self.assertNotIn("names unavailable", txt)

    def test_false_omitted_not_emitted(self) -> None:
        report = {
            "es_program": {
                "status": "READY",
                "omitted": False,
                "omitted_zones": [],
                "zones": [{"name": "MSCRENOPICK_ESZone1", "members": ["ESPB2"]}],
                "report_matches_artifact": True,
            },
            "symbol_closure": {"ok": True, "failures": [], "failure_count": 0},
        }
        manifest = build_issues_manifest(report, site="MSCRENOPICK", build_status="PARTIAL")
        txt = render_build_issues_txt(manifest)
        self.assertNotIn("False [OMITTED]", txt)
        objs = {i.get("object/device") for i in manifest["SAFETY"]}
        self.assertNotIn("False", objs)

    def test_cl17_non_structural_when_artifact_valid(self) -> None:
        report = {
            "writer_coverage": {"by_class": {"DEFECT": ["CL17"]}},
            "symbol_closure": {"ok": True, "failures": [], "failure_count": 0},
            "studio_preflight": {"ok": True, "issues": []},
        }
        manifest = build_issues_manifest(report, site="MSCRENOPICK")
        self.assertFalse(manifest["BLOCKERS"])
        writers = manifest["WRITER / OUTPUT ISSUES"]
        cl = next(i for i in writers if i.get("object/device") == "CL17")
        self.assertEqual(cl.get("severity/classification"), "UNSUPPORTED / REVIEW")
        self.assertEqual(cl.get("effect"), "COMMISSIONING")
        self.assertIn("WITHHELD", str(cl.get("what Site Forge did") or ""))

    def test_p105a_explicit_and_ori090(self) -> None:
        report = {
            "merges_withheld_review": ["P1001-P105A"],
            "eip_interface_ip": "192.168.1.9",
            "eip_adapter_ips": ["192.168.1.52", "192.168.1.63"],
            "symbol_closure": {"ok": True, "failures": [], "failure_count": 0},
        }
        manifest = build_issues_manifest(report, site="MSCRENOPICK", build_status="PARTIAL")
        withheld_objs = {i.get("object/device") for i in manifest["WITHHELD FROM L5X"]}
        self.assertIn("P105A", withheld_objs)
        hygiene = render_build_issues_txt(manifest)
        self.assertIn("ORI-090", hygiene)

    def test_tar_sha_not_substituted_by_run_fingerprint(self) -> None:
        manifest = build_issues_manifest(
            {},
            site="MSCRENOPICK",
            git_sha="abc",
            tar_hash="",
            run_fingerprint="shortfp123",
            build_id="bid",
            build_status="PARTIAL",
        )
        self.assertEqual(manifest.get("RUN fingerprint"), "shortfp123")
        self.assertEqual(manifest.get("TAR SHA256"), "")
        txt = render_build_issues_txt(manifest)
        self.assertIn("RUN fingerprint: shortfp123", txt)
        self.assertIn("TAR SHA256:", txt)


if __name__ == "__main__":
    unittest.main()

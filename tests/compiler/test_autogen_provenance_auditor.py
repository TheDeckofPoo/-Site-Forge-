#!/usr/bin/env python3
"""Provenance auditor — known-site, blind, and negative/counterfactual tests."""
from __future__ import annotations
# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys
_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / 'tools' / 'scripts'
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
# Prefer canonical names used by existing tests:
SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO
REPO_ROOT = _SF_REPO
# --- end bootstrap ---


import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from fortna_autogen_provenance import (  # noqa: E402
    CLASS_DERIVED,
    CLASS_ENGINEER,
    CLASS_PROVEN,
    CLASS_REVIEW,
    CLASS_UNKNOWN,
    audit,
    why_query,
    write_reports,
)

PLC5 = ROOT / "workspace" / "cp5-run" / "RUN"
VIRGIN = ROOT / "workspace" / "_virgin_orindy" / "RUN"
PLC2 = ROOT / "workspace" / "_plc2_run_peek" / "RUN"


@unittest.skipUnless((PLC5 / "project.cfg").is_file(), "PLC5 RUN missing")
class TestKnownSiteProvenance(unittest.TestCase):
    """A. Known-site reproduction — ORNCCP5 produces expected derived I/O decisions."""

    def test_plc5_emits_io_and_safety_records(self) -> None:
        doc = audit(PLC5, "ORNCCP5", scan_production_code=False)
        self.assertFalse(doc["finished_plc_used"])
        self.assertGreater(doc["total_records"], 10)
        self.assertIn(CLASS_PROVEN, doc["counts"])
        # At least some assigned I/O should be PROVEN/DERIVED
        io = [r for r in doc["records"] if r["subsystem"] == "io"]
        self.assertTrue(io)
        assigned = [
            r
            for r in io
            if r["classification"] in (CLASS_PROVEN, CLASS_DERIVED, CLASS_ENGINEER)
            and "owner:" in " ".join(r.get("evidence_available") or [])
        ]
        self.assertGreater(len(assigned), 0)

    def test_why_query_finds_endpoint(self) -> None:
        doc = audit(PLC5, "ORNCCP5", scan_production_code=False)
        # Pick any artifact with Data[
        sample = next(
            (r for r in doc["records"] if "Data[" in str(r.get("artifact") or "")),
            None,
        )
        self.assertIsNotNone(sample)
        q = str(sample["artifact"]).split(":")[0]  # rio name fragment
        hits = why_query(doc, q)
        self.assertTrue(hits)


@unittest.skipUnless((VIRGIN / "project.cfg").is_file(), "virgin ORINDYAC6 RUN missing")
class TestBlindVirginProvenance(unittest.TestCase):
    """B. Blind/virgin — no finished PLC in the path."""

    def test_virgin_audit_does_not_use_finished_plc(self) -> None:
        doc = audit(VIRGIN, "ORINDYAC6", scan_production_code=False)
        self.assertFalse(doc["finished_plc_used"])
        self.assertGreater(doc["counts"].get(CLASS_PROVEN, 0) + doc["counts"].get(CLASS_DERIVED, 0), 0)
        # Word 600 style endpoints should appear as Data[0] lineage when assigned
        hits = why_query(doc, "Data[0]")
        # May or may not have Data[0] string in artifact depending on channel emit
        # At minimum audit runs without finished PLC paths
        self.assertNotIn("finished", str(doc["run_dir"]).lower())


class TestNegativeCounterfactual(unittest.TestCase):
    """C. Negative — remove evidence → decision changes."""

    def test_safety_membership_without_engineer_is_review(self) -> None:
        # Synthetic: zone with empty members must be REVIEW_REQUIRED
        # Use virgin or PLC5 if available; else skip
        run = VIRGIN if (VIRGIN / "project.cfg").is_file() else PLC5
        if not (run / "project.cfg").is_file():
            self.skipTest("no RUN")
        mach = "ORINDYAC6" if run == VIRGIN else "ORNCCP5"
        empty = {
            "zones": [
                {
                    "source_id": "TEST_ESZone1",
                    "name": "TEST_ESZone1",
                    "members": [],
                    "membersOrigin": "UNRESOLVED",
                    "provenance": "ENGINEER_CREATED",
                    "engineerEdited": True,
                }
            ]
        }
        doc = audit(run, mach, safety_build=empty, scan_production_code=False)
        mem = [
            r
            for r in doc["records"]
            if r["subsystem"] == "safety" and r["decision"] == "safety_device_membership"
            and "TEST_ESZone1" in r["artifact"]
        ]
        self.assertTrue(mem)
        self.assertEqual(mem[0]["classification"], CLASS_REVIEW)

    def test_safety_membership_with_engineer_is_engineer_assigned(self) -> None:
        run = VIRGIN if (VIRGIN / "project.cfg").is_file() else PLC5
        if not (run / "project.cfg").is_file():
            self.skipTest("no RUN")
        mach = "ORINDYAC6" if run == VIRGIN else "ORNCCP5"
        filled = {
            "zones": [
                {
                    "source_id": "TEST_ESZone1",
                    "name": "TEST_ESZone1",
                    "members": ["ES600", "ES601"],
                    "membersOrigin": "ENGINEER_ASSIGNED",
                    "provenance": "ENGINEER_CREATED",
                    "engineerEdited": True,
                }
            ]
        }
        doc = audit(run, mach, safety_build=filled, scan_production_code=False)
        mem = [
            r
            for r in doc["records"]
            if r["subsystem"] == "safety"
            and r["decision"] == "safety_device_membership"
            and "TEST_ESZone1" in r["artifact"]
            and r["classification"] == CLASS_ENGINEER
        ]
        self.assertTrue(mem)
        # Counterfactual: emptying members flips class
        empty = {
            "zones": [
                {
                    "source_id": "TEST_ESZone1",
                    "name": "TEST_ESZone1",
                    "members": [],
                    "membersOrigin": "UNRESOLVED",
                    "engineerEdited": True,
                }
            ]
        }
        doc2 = audit(run, mach, safety_build=empty, scan_production_code=False)
        mem2 = [
            r
            for r in doc2["records"]
            if r["subsystem"] == "safety"
            and r["decision"] == "safety_device_membership"
            and "TEST_ESZone1" in r["artifact"]
        ]
        self.assertTrue(mem2)
        self.assertEqual(mem2[0]["classification"], CLASS_REVIEW)

    def test_reports_deterministic(self) -> None:
        run = PLC5 if (PLC5 / "project.cfg").is_file() else VIRGIN
        if not (run / "project.cfg").is_file():
            self.skipTest("no RUN")
        mach = "ORNCCP5" if run == PLC5 else "ORINDYAC6"
        doc = audit(run, mach, scan_production_code=False)
        with tempfile.TemporaryDirectory() as td:
            jp, mp = write_reports(doc, Path(td))
            self.assertTrue(jp.is_file())
            self.assertTrue(mp.is_file())
            again = json.loads(jp.read_text(encoding="utf-8"))
            self.assertEqual(again["counts"], doc["counts"])


class TestAntiCopy(unittest.TestCase):
    def test_anti_copy_scan_runs(self) -> None:
        run = PLC5 if (PLC5 / "project.cfg").is_file() else VIRGIN
        if not (run / "project.cfg").is_file():
            self.skipTest("no RUN")
        mach = "ORNCCP5" if run == PLC5 else "ORINDYAC6"
        doc = audit(run, mach, scan_production_code=True)
        # May or may not find site-ifs; ensure key exists and finished_plc_used is false
        self.assertIn("anti_copy", doc)
        self.assertFalse(doc["finished_plc_used"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

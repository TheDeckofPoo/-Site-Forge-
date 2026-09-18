#!/usr/bin/env python3
"""GATE 3 Confirm-PE + GATE 4 PhysicalDivert model tests.

- No physical_diverts = lanes/2 hardcode in production paths
- Confirm PE not promoted from FullClearTimer name similarity alone
- Accept/Change preserves provenance (ENGINEER_ACCEPTED; never falsify PROVEN)
- Relationship artifact counts + STRONGLY_SUPPORTED classification
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
PLUS = ROOT / "dashboard" / "fortna-plus.js"
INDEX = ROOT / "dashboard" / "index.html"
REL_JSON = ROOT / "exports" / "stabilization" / "plc5_lane_divert_relationship.json"
AUDIT_JSON = ROOT / "exports" / "stabilization" / "plc5_divert_confirm_pe_audit.json"
DOC = ROOT / "docs" / "evidence" / "SORTER_LANE_PHYSICAL_DIVERT_MODEL.md"
RUN = ROOT / "workspace" / "cp5-run" / "RUN"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fortna_sorter_lane_divert_model import (  # noqa: E402
    build_from_run,
    build_confirm_pe_audit,
    build_lane_divert_relationship,
)
from fortna_sorter_review_lifecycle import (  # noqa: E402
    bulk_accept_derived_divert_pe,
    bulk_apply_value,
)


class TestSorterLaneDivertModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not (RUN / "FORTNA").is_dir():
            raise unittest.SkipTest(f"PLC5 RUN not present at {RUN}")
        cls.audit, cls.rel = build_from_run(RUN, "ORNCCP5")

    def test_gate4_counts_from_run_not_half(self) -> None:
        c = self.rel["counts"]
        self.assertEqual(c["destination_lane_records"], 32)
        self.assertEqual(c["unique_physical_outputs"], 32)
        self.assertEqual(c["unique_physical_divert_mechanisms"], 16)
        self.assertEqual(c["lanes_per_physical_divert"], 2)
        self.assertEqual(c["unresolved_mappings"], 0)
        # Must be derived from shared FullClearTimer / SSV family — not hardcoded /2
        self.assertIn("shared_FullClearTimer", [g["key"] for g in self.rel["grouping_evidence"]])
        self.assertIn(self.rel["classification"], ("STRONGLY_SUPPORTED", "STRONGLY_SUPPORTED_WITH_GAPS"))
        self.assertIn("do not hardcode", self.rel["not"].lower())
        self.assertIn("32", self.rel["phase1_action"])

    def test_gate4_no_slash2_in_production_scripts(self) -> None:
        banned = re.compile(
            r"physical_divert[s]?\s*=\s*.*/\s*2|divert_count\s*/\s*2|lanes\s*/\s*2",
            re.I,
        )
        for rel in (
            "fortna_sorter_discovery.py",
            "fortna_sorter_build.py",
            "fortna_sorter_pack_compiler.py",
            "fortna_sorter_lane_divert_model.py",
            "fortna_sorter_review_lifecycle.py",
        ):
            text = (SCRIPTS / rel).read_text(encoding="utf-8", errors="replace")
            # Allow documentary mentions of the ban, not assignment hardcodes
            for m in banned.finditer(text):
                window = text[max(0, m.start() - 80) : m.end() + 40]
                self.assertTrue(
                    "hardcode" in window.lower() or "do not" in window.lower() or "not" in window.lower(),
                    msg=f"Suspicious /2 hardcode in {rel}: {window!r}",
                )

    def test_gate3_confirm_pe_not_from_timer_name_alone(self) -> None:
        s = self.audit["plc5_audit_summary"]
        self.assertEqual(s["destination_lanes_reviewed"], 32)
        self.assertEqual(s["proven_confirm_pe"], 0)
        self.assertEqual(s["derived_confirm_pe"], 0)
        self.assertEqual(s["no_confirm_pe_candidate"], 32)
        # Hints may exist in Conveyor but must not become candidates
        self.assertGreater(s.get("full_clear_timer_pe_hint_present", 0), 0)
        for row in self.audit["divert_rows_requiring_review"]:
            self.assertIsNone(row["candidate_confirmation_pe"])
            self.assertEqual(row["engineer_action"], "SELECTION_REQUIRED")
            self.assertIn(row["evidence_class"], ("REVIEW_REQUIRED", "ENGINEER_REQUIRED"))

    def test_gate3_semantic_primary_is_verify_io(self) -> None:
        sem = self.audit["confirm_pe_semantic_conclusion"]
        self.assertIn("Verify I/O Name", sem["primary_run_field"])
        self.assertTrue(any("FullClearTimer" in x for x in sem["not_confirm_pe"]))

    def test_accept_change_preserves_provenance(self) -> None:
        rows = [
            {"name": "A", "divert_pe": "PE_A", "authority": {"divert_pe": "DERIVED"}},
            {"name": "B", "divert_pe": "PE_B", "authority": {"divert_pe": "PROVEN"}},
            {"name": "C", "divert_pe": "", "authority": {"divert_pe": "REVIEW_REQUIRED"}},
            {"name": "D", "divert_pe": "", "authority": {"divert_pe": "UNKNOWN"}},
        ]
        accepted = bulk_accept_derived_divert_pe(rows)
        self.assertEqual(accepted[0]["authority"]["divert_pe"], "DERIVED")
        self.assertEqual(accepted[0]["divert_pe_acceptance"], "ENGINEER_ACCEPTED")
        self.assertEqual(accepted[1]["authority"]["divert_pe"], "PROVEN")  # untouched by derived-accept
        self.assertNotEqual(accepted[3]["authority"]["divert_pe"], "PROVEN")

        changed = bulk_apply_value(rows, [2], "PE_ENG")
        self.assertEqual(changed[2]["divert_pe"], "PE_ENG")
        self.assertEqual(changed[2]["divert_pe_acceptance"], "ENGINEER_ACCEPTED")
        self.assertNotEqual(changed[2]["authority"]["divert_pe"], "PROVEN")

        # Changing a PROVEN row via apply must not falsify PROVEN
        changed_p = bulk_apply_value(rows, [1], "PE_OTHER")
        # bulk_apply_value sets ENGINEER_REQUIRED only when not PROVEN — verify helper contract
        from fortna_sorter_review_lifecycle import normalize_status

        auth = normalize_status((changed_p[1].get("authority") or {}).get("divert_pe"))
        self.assertEqual(auth, "PROVEN")

    def test_ui_derived_accept_change_contract(self) -> None:
        js = PLUS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("sorter-divert-pe-accept", js)
        self.assertIn("sorter-divert-pe-change", js)
        self.assertIn("Derived:", js)
        self.assertIn("ENGINEER_ACCEPTED", js)
        self.assertIn("never falsify PROVEN", js)
        self.assertIn("Confirm PE…", js)
        # empty Select only when no candidate
        self.assertIn("hasCandidate", js)
        html = INDEX.read_text(encoding="utf-8", errors="replace")
        self.assertIn("btn-divert-accept-derived", html)

    def test_artifacts_and_doc_written(self) -> None:
        self.assertTrue(REL_JSON.is_file(), "plc5_lane_divert_relationship.json missing")
        self.assertTrue(AUDIT_JSON.is_file(), "plc5_divert_confirm_pe_audit.json missing")
        self.assertTrue(DOC.is_file(), "SORTER_LANE_PHYSICAL_DIVERT_MODEL.md missing")
        rel = json.loads(REL_JSON.read_text(encoding="utf-8"))
        audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
        self.assertEqual(rel["counts"]["destination_lane_records"], 32)
        self.assertEqual(rel["counts"]["unique_physical_divert_mechanisms"], 16)
        self.assertEqual(len(audit["divert_rows_requiring_review"]), 32)
        doc = DOC.read_text(encoding="utf-8")
        self.assertIn("Confirm PE", doc)
        self.assertIn("PhysicalDivert", doc)
        # Documentary ban is required; production must not assign via /2
        self.assertRegex(doc, re.compile(r"do not hardcode physical_diverts\s*=\s*lanes\s*/\s*2", re.I))


if __name__ == "__main__":
    unittest.main()

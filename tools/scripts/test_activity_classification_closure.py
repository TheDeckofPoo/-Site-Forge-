#!/usr/bin/env python3
"""Activity classification closure — N/A must not deactivate."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_activity_classify import (  # noqa: E402
    AVAILABLE,
    EXCLUDED,
    INCLUDED,
    classify_object,
    classify_site_model,
)
from fortna_site_model import (  # noqa: E402
    ACTIVE_CONFIRMED,
    ACTIVE_LIKELY,
    HISTORICAL_OR_STALE,
    INACTIVE_CONFIRMED,
)


class TestNoNADeactivation(unittest.TestCase):
    def test_machine_name_na_does_not_exclude_with_io_evidence(self):
        obj = {
            "kind": "equipment",
            "raw_name": "P9001",
            "normalized_name": "P9001",
            "Machine_Name": "N/A",
            "io_address_word": "100",
            "evidence": [{"kind": "controller_io"}, {"kind": "motor_link"}],
            "source_scope": "base_only",
        }
        classify_object(obj, machine="ALPHASITE", related_links={"P9001"}, in_machine_scope=None)
        self.assertNotEqual(obj["inclusion"], EXCLUDED)
        self.assertIn(obj["active_state"], {ACTIVE_CONFIRMED, ACTIVE_LIKELY})
        self.assertTrue(any(e.get("kind") == "ambiguous_ownership" for e in obj["evidence"]))
        self.assertNotEqual(obj.get("generation_reason"), "EXPLICIT_INACTIVE_DOCUMENTED_FIELD")
        notes = obj.get("source_evidence_notes") or []
        self.assertTrue(any(n.get("field") == "Machine_Name" for n in notes))
        # N/A alone must not be treated as inactivity signal
        self.assertTrue(obj.get("inclusion") in {INCLUDED, AVAILABLE})

    def test_blank_enable_is_not_inactive(self):
        obj = {
            "kind": "equipment",
            "raw_name": "P9002",
            "normalized_name": "P9002",
            "enable": "N/A",
            "evidence": [{"kind": "controller_io"}, {"kind": "mtrchain"}],
            "source_scope": "controller_overlay",
        }
        classify_object(obj, machine="ALPHASITE", related_links={"P9002"})
        self.assertNotEqual(obj["active_state"], INACTIVE_CONFIRMED)
        self.assertNotEqual(obj["inclusion"], EXCLUDED)

    def test_explicit_offline_yes_still_inactive(self):
        obj = {
            "kind": "equipment",
            "raw_name": "P9003",
            "normalized_name": "P9003",
            "Offline": "Y",
            "evidence": [{"kind": "controller_io"}],
        }
        classify_object(obj, machine="ALPHASITE", related_links=set())
        self.assertEqual(obj["active_state"], INACTIVE_CONFIRMED)
        self.assertEqual(obj["inclusion"], EXCLUDED)

    def test_decision_records_evidence_lists(self):
        obj = {
            "kind": "equipment",
            "raw_name": "P9004",
            "normalized_name": "P9004",
            "evidence": [{"kind": "jam_link"}, {"kind": "controller_io"}],
            "source_table": "Conveyor.asc",
            "source_scope": "base_only",
            "Machine_Name": "ALPHASITE",
        }
        classify_object(obj, machine="ALPHASITE", related_links={"P9004"})
        self.assertIn("evidence_for", obj)
        self.assertIn("evidence_against", obj)
        self.assertIn("generation_reason", obj)
        self.assertTrue(obj["evidence_for"])

    def test_site_model_policy_flag(self):
        model = {
            "equipment": [
                {
                    "kind": "equipment",
                    "raw_name": "P1",
                    "normalized_name": "P1",
                    "Machine_Name": "N/A",
                    "evidence": [{"kind": "controller_io"}],
                    "source_scope": "base_only",
                }
            ],
            "relationships": [],
        }
        report = classify_site_model(model, "X")
        self.assertFalse(report["policy"]["single_field_na_deactivation"])


class TestHistoricalStillExcluded(unittest.TestCase):
    def test_historical_scope_excluded(self):
        obj = {
            "kind": "equipment",
            "raw_name": "POLD",
            "normalized_name": "POLD",
            "source_scope": "historical",
            "evidence": [],
        }
        classify_object(obj, machine="X", related_links=set())
        self.assertEqual(obj["active_state"], HISTORICAL_OR_STALE)
        self.assertEqual(obj["inclusion"], EXCLUDED)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""ORI-111 regression: never manufacture controller ownership to green a PLC.

When the TAR label says controller A but Conveyor.asc Machine_Name evidence is
N/A or belongs to controller B, Site Forge must not invent ownership merely to
produce a green build.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from fortna_build_escalation import (  # noqa: E402
    validate_machine_identity_proposal,
)


CASE = (
    ROOT
    / "exports"
    / "delivery_gate_20261002"
    / "ordencp1_proven_empty_case.json"
)


class TestNoInventOwnership(unittest.TestCase):
    def test_rejects_invented_machine_not_in_evidence(self) -> None:
        ev = {
            "claimed_machine": "ORDENCP1",
            "project_cfg_machine": "ORDENCP1",
            "exclusive_machine_names": {"ORDENCP4": 469},
        }
        v = validate_machine_identity_proposal(
            {"resolved_machine": "FAKE_OWNED_PLC", "treat_na_rows_as_resolved_machine": True},
            ev,
        )
        self.assertFalse(v["ok"])

    def test_ordencp1_case_file_records_proven_empty(self) -> None:
        self.assertTrue(CASE.is_file(), "ORDENCP1 proven-empty case missing")
        j = json.loads(CASE.read_text(encoding="utf-8"))
        self.assertEqual(j.get("classification"), "PROVEN_INPUT_SCOPE_LIMITATION")
        self.assertFalse(j.get("engineer_complete"))
        self.assertFalse(j.get("ori111_end_to_end_success"))
        self.assertEqual(j.get("resulting_owned_conveyor_count"), 0)
        self.assertEqual(j.get("resulting_mapped_io_count"), 0)
        self.assertFalse(
            (j.get("validator_result") or {}).get("accepted_treat_na"),
            "case must preserve AI/Relay refusal to assign N/A rows",
        )
        lesson = str(j.get("lesson") or "").lower()
        self.assertIn("must not manufacture ownership", lesson)

    def test_treat_na_false_is_valid_resolution(self) -> None:
        """Accepting ORDENCP1 without inventing N/A ownership is allowed."""
        ev = {
            "claimed_machine": "ORDENCP1",
            "project_cfg_machine": "ORDENCP1",
            "exclusive_machine_names": {"ORDENCP4": 469},
        }
        v = validate_machine_identity_proposal(
            {
                "resolved_machine": "ORDENCP1",
                "treat_na_rows_as_resolved_machine": False,
                "confidence": "DERIVED",
            },
            ev,
        )
        self.assertTrue(v["ok"], v)
        self.assertFalse(v.get("treat_na_rows_as_resolved_machine"))


if __name__ == "__main__":
    unittest.main()

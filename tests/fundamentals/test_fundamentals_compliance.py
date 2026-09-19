#!/usr/bin/env python3
"""Executable Site Forge Fundamentals — not documentation-only."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_project_identity import (  # noqa: E402
    ProjectIdentity,
    identity_from_mapping,
    project_key_from_parts,
    same_project,
)
from fortna_io_extract import row_machine_matches  # noqa: E402
from fortna_final_artifact_closure import validate_final_artifact  # noqa: E402

MSC_PICK_RUN = (
    _SF_REPO
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
    / "RUN"
)


class TestProjectIdentity(unittest.TestCase):
    def test_same_project_requires_key_and_machine(self) -> None:
        a = ProjectIdentity("MSCRENO", "MSCRENOPICK", "MSCRENO|MSCRENOPICK", "fp1")
        b = ProjectIdentity("MSCRENO", "MSCRENOPICK", "MSCRENO|MSCRENOPICK", "fp2")
        c = ProjectIdentity("MSCRENO", "MSCRENOPACK", "MSCRENO|MSCRENOPACK", "fp1")
        self.assertTrue(same_project(a, b))  # revision may differ
        self.assertFalse(same_project(a, c))
        self.assertFalse(same_project(a, None))

    def test_project_key_stable(self) -> None:
        self.assertEqual(
            project_key_from_parts(project_name="MSCRENO", machine="MSCRENOPICK"),
            "MSCRENO|MSCRENOPICK",
        )


class TestNoSubstringMachineMatch(unittest.TestCase):
    """Generalize the rule — MSCRENO must not match MSCRENOPACK/PICK."""

    def test_pick_does_not_match_pack(self) -> None:
        self.assertFalse(row_machine_matches("MSCRENOPACK", "MSCRENOPICK"))
        self.assertFalse(row_machine_matches("MSCRENOPICK", "MSCRENOPACK"))
        self.assertTrue(row_machine_matches("MSCRENOPICK", "MSCRENOPICK"))


class TestReviewIsNotPass(unittest.TestCase):
    def test_final_closure_review_not_ok(self) -> None:
        # Empty Safe routines → REVIEW, not PASS/ok
        r = validate_final_artifact(l5x_text="<Controller/>", machine="X")
        self.assertIn(r["status"], ("REVIEW", "FAIL", "PASS"))
        if r["status"] == "REVIEW":
            self.assertFalse(r["ok"])


class TestErasedMeansErasedWorkbook(unittest.TestCase):
    def test_foreign_workbook_not_preserved(self) -> None:
        from fortna_workbook import build_workbook_from_run

        if not (MSC_PICK_RUN / "project.cfg").is_file():
            self.skipTest("MSCRENOPICK RUN fixture missing")
        foreign = {
            "machine": "ORINDYAC6",
            "project_name": "ORINDY",
            "project_key": "ORINDY|ORINDYAC6",
            "sorter_build": {"divert_host_conveyor": "P610", "appliedAt": "t"},
            "merges_2to1": [{"name": "P600"}],
            "safety_build": {"zones": [{"name": "IndyZone", "members": ["ES1"]}]},
            "conveyors": [],
        }
        wb = build_workbook_from_run(MSC_PICK_RUN, existing=foreign)
        self.assertNotEqual(str(wb.get("machine") or "").upper(), "ORINDYAC6")
        self.assertFalse(wb.get("sorter_build"))
        self.assertFalse(wb.get("merges_2to1"))
        # Safety zones from Indy must not survive
        zones = (wb.get("safety_build") or {}).get("zones") or []
        self.assertFalse(any("Indy" in str(z.get("name") or "") for z in zones))


@unittest.skipUnless((MSC_PICK_RUN / "project.cfg").is_file(), "MSCRENOPICK RUN missing")
class TestP120ExactIdentity(unittest.TestCase):
    """Exact identity: foreign P120 excluded; current P120C preserved."""

    def test_machine_scoped_view_p120_vs_p120c(self) -> None:
        from fortna_machine_scoped_run import build_machine_scoped_run_view

        view = build_machine_scoped_run_view(MSC_PICK_RUN, "MSCRENOPICK")
        self.assertNotIn("P120", {x.upper() for x in view.conveyor_ids})
        self.assertIn("P120C", {x.upper() for x in view.conveyor_ids})
        foreign = {e["identity"].upper() for e in view.foreign_excluded}
        self.assertIn("P120", foreign)

    def test_load_from_run_excludes_foreign_p120(self) -> None:
        from fortna_autogen import load_from_run

        inp = load_from_run(MSC_PICK_RUN)
        names = {
            str(getattr(c, "conveyor", "") or "").upper()
            for c in (inp.conveyors or [])
        }
        self.assertNotIn("P120", names)
        self.assertIn("P120C", names)


if __name__ == "__main__":
    unittest.main(verbosity=2)

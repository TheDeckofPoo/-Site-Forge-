#!/usr/bin/env python3
"""GATE 9 — MachineClosure provenance, why-query paths, orphan detection."""
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


import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from fortna_autogen_provenance import (  # noqa: E402
    CLASS_PROVEN,
    CLASS_REVIEW,
    audit,
    collect_machine_closure_provenance,
    collect_native_merge_provenance,
    collect_orphan_closure_checks,
    why_query,
)

VIRGIN = ROOT / "workspace" / "_virgin_orindy" / "RUN"
MACHINE = "ORINDYAC6"


def _write_mini_run(td: Path, machine: str = "TESTMACH") -> Path:
    run = td / "RUN"
    fortna = run / "FORTNA"
    fortna.mkdir(parents=True)
    (run / "project.cfg").write_text("Site=TEST\n", encoding="utf-8")
    (fortna / "Machine.asc").write_text(
        '"Machine_Name"~"Desc"\n'
        f"{machine}~Test\n",
        encoding="utf-8",
    )
    (fortna / "Conveyor.asc").write_text(
        '"IO_Name"~"Machine_Name"~"General_Description"\n'
        f"P600~{machine}~merge outfeed\n"
        f"P628~{machine}~main lane\n"
        f"ES600~{machine}~estop\n",
        encoding="utf-8",
    )
    (fortna / "MergeBoss.asc").write_text(
        '"Name"~"Owner"~"Desc"\n'
        f"RECIRC SPUR~{machine}~recirc\n",
        encoding="utf-8",
    )
    (fortna / "MergeInputs.asc").write_text(
        '"Name"~"MergeBoss"~"Desc"\n'
        "LANE P628 RECIRC~RECIRC SPUR~lane\n",
        encoding="utf-8",
    )
    (fortna / "MergeRoute.asc").write_text(
        '"Name"~"MergeInputs"~"Desc"\n'
        "LANE P628~LANE P628 RECIRC~route\n",
        encoding="utf-8",
    )
    (fortna / "EStop.asc").write_text(
        '"Desc"~"Part"~"Error"\n'
        "ES600~ES600~ES600\n",
        encoding="utf-8",
    )
    (fortna / "SawLane.asc").write_text(
        '"Name"~"PhotoEyeIO"~"Desc"\n',
        encoding="utf-8",
    )
    return run


class TestMachineClosureProvenanceSynthetic(unittest.TestCase):
    def test_why_p600_merge_returns_relationship_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run = _write_mini_run(Path(td), "TESTMACH")
            doc = audit(run, "TESTMACH", scan_production_code=False)
            closure = [
                r
                for r in doc["records"]
                if r["subsystem"] == "machine_closure"
            ]
            self.assertTrue(closure)
            # P600 conveyor member should carry relationship_path
            p600 = next(
                (
                    r
                    for r in closure
                    if str(r.get("artifact") or "").upper() == "P600"
                    or str((r.get("extras") or {}).get("identity") or "").upper()
                    == "P600"
                ),
                None,
            )
            self.assertIsNotNone(p600, "P600 should be in MachineClosure provenance")
            assert p600 is not None
            path = (p600.get("extras") or {}).get("relationship_path") or []
            self.assertTrue(path)
            self.assertEqual(p600["classification"], CLASS_PROVEN)

            hits = why_query(doc, "P600_Merge")
            self.assertTrue(hits, "why P600_Merge should hit Fortna relationship paths")
            top = hits[0]
            extras = top.get("extras") or {}
            self.assertTrue(
                extras.get("relationship_path")
                or top.get("subsystem") == "machine_closure"
                or "P600" in str(top.get("artifact") or "").upper()
            )

    def test_orphan_site_specific_artifact_detected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run = _write_mini_run(Path(td), "TESTMACH")
            # P406_Merge is site-specific and NOT in this machine's closure
            report = {
                "merges": [
                    {"name": "P406_Merge", "merge_tag": "P406_Merge"},
                    {"name": "P600_Merge", "merge_tag": "P600_Merge"},
                ],
                "tags": ["NO_Conv", "Merge_2to1", "P506_Divert1"],
            }
            doc = audit(
                run,
                "TESTMACH",
                autogen_report=report,
                scan_production_code=False,
            )
            self.assertIn("orphan_generation_count", doc)
            orphans = [
                r
                for r in doc["records"]
                if r.get("decision") == "orphan_site_specific_artifact"
            ]
            names = {r["artifact"] for r in orphans}
            self.assertIn("P406_Merge", names)
            self.assertIn("P506_Divert1", names)
            # P600 is in MachineClosure → not an orphan
            self.assertNotIn("P600_Merge", names)
            # Library / NO_* exempt
            self.assertNotIn("NO_Conv", names)
            self.assertNotIn("Merge_2to1", names)
            self.assertGreaterEqual(doc["orphan_generation_count"], 2)
            for r in orphans:
                self.assertEqual(r["classification"], CLASS_REVIEW)
                self.assertEqual(r["severity"], "error")

    def test_engineer_assigned_not_orphan(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run = _write_mini_run(Path(td), "TESTMACH")
            report = {
                "merges": [
                    {
                        "name": "P406_Merge",
                        "engineer_assigned": True,
                    }
                ]
            }
            orphans = collect_orphan_closure_checks(
                run,
                "TESTMACH",
                autogen_report=report,
            )
            self.assertEqual(orphans, [])


@unittest.skipUnless((VIRGIN / "project.cfg").is_file(), "virgin ORINDYAC6 RUN missing")
class TestMachineClosureProvenanceLive(unittest.TestCase):
    def test_orindyac6_closure_provenance_and_why(self) -> None:
        recs = collect_machine_closure_provenance(VIRGIN, MACHINE)
        self.assertTrue(recs)
        tables = {str((r.extras or {}).get("source_table") or "") for r in recs}
        self.assertTrue({"Conveyor", "EStop"} & tables)
        # relationship_path present on focus members
        with_path = [r for r in recs if (r.extras or {}).get("relationship_path")]
        self.assertTrue(with_path)

        doc = audit(VIRGIN, MACHINE, scan_production_code=False)
        self.assertEqual(doc.get("orphan_generation_count", 0), 0)
        # MergeInputs / MergeRoute path searchable via lane P-token
        hits = why_query(doc, "P628")
        self.assertTrue(
            any(
                r.get("subsystem") == "machine_closure"
                and (r.get("extras") or {}).get("relationship_path")
                for r in hits
            ),
            "why P628 should return MachineClosure relationship paths",
        )

    def test_orindyac6_why_p600_merge_native_path(self) -> None:
        """P600 may lack Conveyor.Machine_Name; MergeBoss graph still owns the merge."""
        native = collect_native_merge_provenance(VIRGIN, MACHINE)
        self.assertTrue(
            any(
                str(r.artifact).upper() == "P600_MERGE"
                or str((r.extras or {}).get("downstream") or "").upper() == "P600"
                for r in native
            ),
            "native merge provenance must include P600 discharge",
        )
        doc = audit(VIRGIN, MACHINE, scan_production_code=False)
        hits = why_query(doc, "P600_Merge")
        self.assertTrue(hits, "why P600_Merge must resolve via native MergeBoss path")
        top = hits[0]
        self.assertEqual(top.get("subsystem"), "native_merge")
        path = (top.get("extras") or {}).get("relationship_path") or top.get("transform") or []
        self.assertTrue(any("MergeBoss" in str(p) for p in path))
        blob = " ".join(str(p) for p in path).upper()
        self.assertIn("P600", blob.upper() + str(top.get("artifact") or "").upper())
        # Contaminants remain orphans; P600_Merge linked via native merge is not
        report = {
            "merges_2to1": [
                {"name": "P600", "discharge": "P600", "discovery_name": "2-1 SERVO"},
                {"name": "P406_Merge"},
                {"name": "P506_Divert1"},
            ]
        }
        doc2 = audit(
            VIRGIN, MACHINE, autogen_report=report, scan_production_code=False
        )
        orphan_names = {r["artifact"] for r in doc2.get("orphans") or []}
        self.assertNotIn("P600_Merge", orphan_names)
        self.assertIn("P406_Merge", orphan_names)
        self.assertIn("P506_Divert1", orphan_names)


if __name__ == "__main__":
    unittest.main(verbosity=2)

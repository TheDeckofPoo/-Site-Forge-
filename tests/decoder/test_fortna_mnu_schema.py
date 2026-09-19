#!/usr/bin/env python3
"""Tests for FortnaPlus .mnu schema archaeology decoder."""
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

from fortna_mnu_schema import (  # noqa: E402
    combine_schemas,
    diff_schemas,
    extract_references,
    parse_mnu_file,
    resolve_asc_path,
    schema_to_dict,
)

PLC2_FORTNA = ROOT / "workspace/_plc2_run_peek/RUN/FORTNA/fortna.mnu"
PLC2_PROJECT = ROOT / "workspace/_plc2_run_peek/RUN/PROJECT/project.mnu"
RENO_FORTNA = ROOT / (
    "workspace/_reno_peek/20260813-1132-MSCRENO-MSCRENOPACK-RUN/RUN/FORTNA/fortna.mnu"
)


def _require(path: Path) -> None:
    if not path.is_file():
        raise unittest.SkipTest(f"missing corpus file: {path}")


class TestMnuParse(unittest.TestCase):
    def test_all_workspace_mnu_parse(self) -> None:
        paths = sorted(ROOT.glob("workspace/**/*.mnu"))
        if not paths:
            self.skipTest("no workspace .mnu files")
        for p in paths:
            with self.subTest(path=str(p.relative_to(ROOT))):
                sch = parse_mnu_file(p)
                self.assertGreater(sch.stats["definitions"], 0)
                self.assertGreater(sch.stats["fields"], 0)
                self.assertIn("***", sch.headerLine)
                # No silent drop: every definition has provenance
                for d in sch.definitions[:20]:
                    self.assertTrue(d.provenance.get("sourceFile"))
                    self.assertTrue(d.provenance.get("line"))

    def test_deterministic_repeated_parse(self) -> None:
        _require(PLC2_FORTNA)
        a = schema_to_dict(parse_mnu_file(PLC2_FORTNA))
        b = schema_to_dict(parse_mnu_file(PLC2_FORTNA))
        self.assertEqual(
            json.dumps(a, sort_keys=True),
            json.dumps(b, sort_keys=True),
        )

    def test_definitions_and_fields_not_silently_dropped(self) -> None:
        _require(PLC2_FORTNA)
        _require(PLC2_PROJECT)
        fortna = parse_mnu_file(PLC2_FORTNA)
        project = parse_mnu_file(PLC2_PROJECT)
        fortna_names = {d.name for d in fortna.definitions}
        project_names = {d.name for d in project.definitions}
        for must in ("Conveyor", "Mtrchain", "EStop", "Jamzones", "MergeBoss"):
            self.assertIn(must, fortna_names)
        # HeightWidth is defined in authentic project.mnu (not fortna.mnu)
        self.assertIn("HeightWidth", project_names)
        conv = next(d for d in fortna.definitions if d.name == "Conveyor")
        # Conveyor has many columns in authentic file
        self.assertGreaterEqual(len(conv.fields), 20)
        field_names = {f.name for f in conv.fields}
        self.assertIn("IO_Name", field_names)
        self.assertIn("IO_Address_Word", field_names)

    def test_explicit_references_resolve_when_target_exists(self) -> None:
        _require(PLC2_FORTNA)
        _require(PLC2_PROJECT)
        fortna = parse_mnu_file(PLC2_FORTNA)
        project = parse_mnu_file(PLC2_PROJECT)
        rel = extract_references(fortna, project)
        self.assertGreater(rel["referenceCount"], 0)
        self.assertGreater(rel["resolvedCount"], 0)
        # HeightWidth lives in project.mnu; BoxDetectIn DLIST names Conveyor
        hw = rel["forward"].get("HeightWidth") or []
        targets = {(r["sourceField"], r["targetDefinition"], r["resolved"]) for r in hw}
        self.assertIn(("BoxDetectIn", "Conveyor", True), targets)
        # Mtrchain.Motor_Ndx -> Conveyor (fortna.mnu)
        mc = rel["forward"].get("Mtrchain") or []
        self.assertTrue(
            any(
                r["sourceField"] == "Motor_Ndx"
                and r["targetDefinition"] == "Conveyor"
                and r["resolved"]
                for r in mc
            )
        )

    def test_unresolved_references_remain_visible(self) -> None:
        _require(PLC2_FORTNA)
        sch = parse_mnu_file(PLC2_FORTNA)
        rel = extract_references(sch)
        # Even if zero unresolved in this corpus, the key must exist and be a list
        self.assertIsInstance(rel["unresolved"], list)
        self.assertEqual(rel["unresolvedCount"], len(rel["unresolved"]))
        for u in rel["unresolved"]:
            self.assertFalse(u["resolved"])
            self.assertTrue(u["targetDefinition"])

    def test_fortna_project_provenance_survives_combine(self) -> None:
        _require(PLC2_FORTNA)
        _require(PLC2_PROJECT)
        f = parse_mnu_file(PLC2_FORTNA, origin="FORTNA")
        p = parse_mnu_file(PLC2_PROJECT, origin="PROJECT")
        combined = combine_schemas([f, p])
        self.assertEqual(combined["precedencePolicy"], "NONE_APPLIED_REPORT_ONLY")
        # Every retained copy keeps origin (ownership index)
        ownership = combined["ownershipIndex"]
        self.assertGreater(len(ownership), 0)
        for name, copies in list(ownership.items())[:50]:
            for c in copies:
                self.assertIn(c["origin"], {"FORTNA", "PROJECT"})
                self.assertTrue(c["sourceFile"])
        # Collisions are reported rather than silently chosen
        self.assertIsInstance(combined["collisions"], list)
        self.assertEqual(combined["collisionCount"], len(combined["collisions"]))

    def test_semantic_version_diff_detects_real_changes(self) -> None:
        _require(PLC2_FORTNA)
        _require(RENO_FORTNA)
        a = parse_mnu_file(PLC2_FORTNA)
        b = parse_mnu_file(RENO_FORTNA)
        diff = diff_schemas(
            [
                ("plc2", a),
                ("reno_pack", b),
            ]
        )
        summary = diff["summary"]
        self.assertGreater(summary["definitionsUnion"], 0)
        # Reno pack introduces definitions not in plc2 peek (probe saw 9 names)
        self.assertGreaterEqual(summary["addedOrRemovedDefinitions"], 1)
        # Identical count should be reported
        self.assertGreaterEqual(summary["identicalDefinitions"], 0)
        tags = {t for d in diff["details"] for t in d.get("changeTags") or []}
        self.assertTrue(tags & {"IDENTICAL", "DEFINITION_ADDED", "DEFINITION_REMOVED", "FIELD_ADDED", "FIELD_REMOVED", "FIELD_DEFINITION_CHANGED", "METADATA_ONLY_CHANGED", "CAPACITY/LIMIT_CHANGED", "REFERENCE_ADDED", "REFERENCE_REMOVED", "UNKNOWN_CHANGE"})

    def test_machine_specific_asc_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "Conveyor.asc").write_text("generic\n", encoding="utf-8")
            (d / "Conveyor.asc.ORNCCP2").write_text("machine\n", encoding="utf-8")
            (d / "Mtrchain.asc").write_text("generic-mtr\n", encoding="utf-8")

            hit = resolve_asc_path("Conveyor", directory=d, ac_name="ORNCCP2")
            self.assertEqual(hit["chosenKind"], "MACHINE_SPECIFIC")
            self.assertTrue(str(hit["chosen"]).endswith("Conveyor.asc.ORNCCP2"))

            miss_specific = resolve_asc_path("Mtrchain", directory=d, ac_name="ORNCCP2")
            self.assertEqual(miss_specific["chosenKind"], "GENERIC")
            self.assertTrue(str(miss_specific["chosen"]).endswith("Mtrchain.asc"))

            missing = resolve_asc_path("NoSuchTable", directory=d, ac_name="ORNCCP2")
            self.assertEqual(missing["chosenKind"], "MISSING")
            self.assertIsNone(missing["chosen"])


if __name__ == "__main__":
    unittest.main()

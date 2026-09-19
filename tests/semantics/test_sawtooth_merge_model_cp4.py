#!/usr/bin/env python3
"""CP4 regression: SawtoothMergeModel auto-build from RUN (no finished PLC)."""
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
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_sawtooth_merge_model import build_sawtooth_merge_model, model_to_editor_shape  # noqa: E402

RUN = ROOT / "workspace" / "cp4-run" / "RUN"
MACHINE = "ORNCCP4"


@unittest.skipUnless((RUN / "project.cfg").is_file() or (RUN / "FORTNA").is_dir(), "CP4 RUN missing")
class TestSawtoothMergeModelCp4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = build_sawtooth_merge_model(RUN, MACHINE)
        cls.editor = model_to_editor_shape(cls.model)

    def test_one_merge_five_lanes(self):
        self.assertTrue(self.model["detected"])
        self.assertEqual(self.model["merge_count"], 1)
        self.assertEqual(self.model["lane_count"], 5)

    def test_lanes_have_conveyor_pe_drive(self):
        merge = self.model["merges"][0]
        self.assertEqual(merge["name"], "SAWTOOTH_MERGE")
        for ln in merge["lanes"]:
            self.assertTrue(ln["conveyor"]["value"], ln)
            self.assertEqual(ln["conveyor"]["provenance"], "RUN_EXPLICIT")
            self.assertTrue(ln["product_pe"]["value"], ln)
            self.assertTrue(str(ln["drive"]["value"] or "").upper().startswith("VFD"), ln)

    def test_vfd_and_encoder_preserved(self):
        self.assertEqual(self.model["vfd_summary"]["unique_bases"], 13)
        enc = (merge := self.model["merges"][0])["merge_encoder"]["value"]
        self.assertTrue(enc, merge)
        self.assertTrue(str(enc).upper().startswith("ENC"), enc)

    def test_collector_derived(self):
        coll = self.model["merges"][0]["collector_conveyor"]
        self.assertEqual(coll["value"], "P414")
        self.assertEqual(coll["provenance"], "RUN_DERIVED")

    def test_discharge_from_mtrchain(self):
        disc = self.model["merges"][0]["discharge_conveyor"]
        self.assertEqual(disc["value"], "P416")
        self.assertEqual(disc["provenance"], "RUN_DERIVED")
        self.assertEqual(self.editor["merges"][0]["downstream_conveyor"], "P416")

    def test_slice_reserve_from_run(self):
        lanes = self.model["merges"][0]["lanes"]
        self.assertTrue(any(ln["slice_seconds"]["value"] is not None for ln in lanes))
        self.assertTrue(any(ln["reserve_seconds"]["value"] is not None for ln in lanes))

    def test_editor_shape(self):
        self.assertTrue(self.editor["detected"])
        self.assertEqual(len(self.editor["merges"][0]["lanes"]), 5)

    def test_no_finished_plc_read(self):
        blob = str(self.model)
        self.assertNotIn("Finished", blob)
        self.assertIn("finished PLC4 never read", self.model["source_of_truth"])


if __name__ == "__main__":
    unittest.main()

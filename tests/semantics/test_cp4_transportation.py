#!/usr/bin/env python3
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
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fortna_semantics.evidence import load_or_build_cp3_index
from fortna_semantics.transportation import run_transportation_adapter

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "artifacts/fortna-reference-graph-plc2.json"


class TestCp4Transportation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not GRAPH.is_file():
            raise unittest.SkipTest("plc2 cp3 graph missing")
        cls.cp3 = load_or_build_cp3_index(graph_path=GRAPH)
        cls.res = run_transportation_adapter(cls.cp3)

    def test_pass_and_objects(self):
        self.assertEqual(self.res.status, "PASS")
        self.assertGreater(self.res.counts["conveyorFamilyObjects"], 10)

    def test_proof_targets(self):
        for pid in ("P314", "M314", "PE314_P", "LATCH_MERGE_316", "M136_AUX"):
            self.assertEqual(self.res.proofs[pid]["status"], "PROVEN", pid)

    def test_no_invented_edges(self):
        # Every fact must carry cp3EdgeKey
        for f in self.res.facts[:50]:
            self.assertTrue(f.get("cp3EdgeKey"))


if __name__ == "__main__":
    unittest.main()

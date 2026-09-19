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


import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fortna_semantics.evidence import load_or_build_cp3_index
from fortna_semantics.merge import run_merge_adapter
from fortna_semantics.mtrchain import run_mtrchain_adapter

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "artifacts/fortna-reference-graph-plc2.json"


class TestCp4Merge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not GRAPH.is_file():
            raise unittest.SkipTest("plc2 cp3 graph missing")
        cls.cp3 = load_or_build_cp3_index(graph_path=GRAPH)
        cls.mtr = run_mtrchain_adapter(cls.cp3)
        cls.res = run_merge_adapter(cls.cp3, mtrchain_public=cls.mtr.to_dict())

    def test_merge316_proof(self):
        p = self.res.proofs["MERGE_316_SPUR"]
        self.assertEqual(p["status"], "PROVEN", p)
        self.assertTrue(all(c["pass"] for c in p["checks"]))

    def test_lane_ne_release(self):
        boss = next(o for o in self.res.objects if o["identity"] == "MERGE_316_SPUR")
        for ln in boss["lanes"]:
            # When both known, they must not be silently collapsed in the model
            self.assertIn("criticalDistinction", ln)

    def test_classes(self):
        self.assertIn(self.res.counts["byClass"]["SPUR"], range(0, 100))


if __name__ == "__main__":
    unittest.main()

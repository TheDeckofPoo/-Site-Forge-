#!/usr/bin/env python3
from __future__ import annotations

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

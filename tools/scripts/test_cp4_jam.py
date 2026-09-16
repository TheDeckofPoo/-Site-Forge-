#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fortna_semantics.evidence import load_or_build_cp3_index
from fortna_semantics.jam import run_jam_adapter

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "artifacts/fortna-reference-graph-plc2.json"


class TestCp4Jam(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not GRAPH.is_file():
            raise unittest.SkipTest("plc2 cp3 graph missing")
        cls.res = run_jam_adapter(load_or_build_cp3_index(graph_path=GRAPH))

    def test_complete_records(self):
        self.assertGreaterEqual(self.res.counts["completeRecords"], 3)
        self.assertEqual(self.res.status, "PASS")
        self.assertGreaterEqual(len(self.res.proofs["completeRecordsSample"]), 3)


if __name__ == "__main__":
    unittest.main()

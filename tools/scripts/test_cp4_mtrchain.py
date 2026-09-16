#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fortna_semantics.evidence import load_or_build_cp3_index
from fortna_semantics.mtrchain import run_mtrchain_adapter

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "artifacts/fortna-reference-graph-plc2.json"


class TestCp4Mtrchain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not GRAPH.is_file():
            raise unittest.SkipTest("plc2 cp3 graph missing")
        cls.res = run_mtrchain_adapter(load_or_build_cp3_index(graph_path=GRAPH))

    def test_m314_proof(self):
        p = self.res.proofs["M314"]
        self.assertEqual(p["status"], "PROVEN", p)
        self.assertTrue(all(c["pass"] for k, c in p["checks"].items() if k != "GoUntil"))

    def test_isolation_status(self):
        self.assertIn(self.res.status, {"PASS", "REVIEW"})
        self.assertGreater(self.res.counts["entries"], 0)


if __name__ == "__main__":
    unittest.main()

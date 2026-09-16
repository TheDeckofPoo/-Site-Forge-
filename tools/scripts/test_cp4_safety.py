#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fortna_semantics.evidence import load_or_build_cp3_index
from fortna_semantics.safety import run_safety_adapter

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "artifacts/fortna-reference-graph-plc2.json"


class TestCp4Safety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not GRAPH.is_file():
            raise unittest.SkipTest("plc2 cp3 graph missing")
        cls.res = run_safety_adapter(load_or_build_cp3_index(graph_path=GRAPH))

    def test_review_not_permissive(self):
        self.assertEqual(self.res.status, "REVIEW")
        for o in self.res.objects[:20]:
            self.assertIsNone(o["safetyZoneRef"])
            self.assertEqual(o["safetyZoneStatus"], "UNKNOWN")

    def test_estop_evidence(self):
        self.assertGreater(self.res.counts["estopDevices"], 0)


if __name__ == "__main__":
    unittest.main()

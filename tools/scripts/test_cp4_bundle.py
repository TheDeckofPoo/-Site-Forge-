#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fortna_semantics.bundle import run_cp4_bundle

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "artifacts/fortna-reference-graph-plc2.json"


class TestCp4Bundle(unittest.TestCase):
    def test_bundle_isolation_and_artifacts(self):
        if not GRAPH.is_file():
            self.skipTest("plc2 cp3 graph missing")
        with tempfile.TemporaryDirectory() as td:
            b = run_cp4_bundle(
                site="plc2",
                graph_path=GRAPH,
                ac_name="ORNCCP2",
                out_dir=Path(td),
            )
            self.assertIn(b["status"], {"PASS", "REVIEW", "FAIL"})
            for name in ("Transportation", "Mtrchain", "Merge", "Jam", "Safety", "IO"):
                self.assertIn(name, b["adapters"])
                self.assertIn(b["adapters"][name]["status"], {"PASS", "REVIEW", "FAIL"})
            # Independent statuses preserved
            self.assertEqual(
                b["adapters"]["Safety"]["status"],
                b["adapterResults"]["Safety"]["status"],
            )
            for fname in (
                "cp4-transportation-plc2.json",
                "cp4-mtrchain-plc2.json",
                "cp4-merge-plc2.json",
                "cp4-jam-plc2.json",
                "cp4-safety-evidence-plc2.json",
                "cp4-io-evidence-plc2.json",
                "cp4-semantic-bundle-plc2.json",
            ):
                p = Path(td) / fname
                self.assertTrue(p.is_file(), fname)
                json.loads(p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

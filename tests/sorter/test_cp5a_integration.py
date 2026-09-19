#!/usr/bin/env python3
"""CP5A integration tests — production orchestrator + Transportation mapper."""
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

from fortna_cp5a_orchestrator import run_decoder_stack  # noqa: E402
from fortna_cp5a_transport_mapper import map_cp4_to_transport_graph  # noqa: E402

PLC2 = ROOT / "workspace/_plc2_run_peek/RUN"


class TestCp5aIntegration(unittest.TestCase):
    def test_decoder_to_transport_mapper_plc2(self):
        if not (PLC2 / "FORTNA" / "fortna.mnu").is_file():
            self.skipTest("PLC2 fixture missing")
        with tempfile.TemporaryDirectory() as td:
            dec = run_decoder_stack(
                run_dir=PLC2, ac_name="ORNCCP2", out_dir=Path(td) / "decoder"
            )
            self.assertTrue(dec.get("ok"), dec)
            self.assertEqual(dec.get("adapters", {}).get("Transportation", {}).get("status"), "PASS")
            self.assertEqual(dec.get("adapters", {}).get("Mtrchain", {}).get("status"), "PASS")
            graph = map_cp4_to_transport_graph(
                run_dir=PLC2, machine="ORNCCP2", decoder_dir=Path(td) / "decoder"
            )
            self.assertTrue(graph.get("ok"))
            self.assertTrue(graph.get("areas"))
            cp5a = (graph.get("metrics") or {}).get("cp5a") or {}
            self.assertEqual(cp5a.get("cp4ConveyorFamilyObjects"), 1012)
            self.assertEqual(cp5a.get("cp4MtrchainEntries"), 176)
            self.assertGreater(cp5a.get("placedNodes") or 0, 0)
            # Required proof objects found in CP4 catalog
            proofs = ((graph.get("cp5a") or {}).get("proofs") or {}).get("transportation") or {}
            for t in ("P314", "M314", "PE314_P", "LATCH_MERGE_316"):
                self.assertEqual((proofs.get(t) or {}).get("status"), "PROVEN", t)
            m314 = ((graph.get("cp5a") or {}).get("proofs") or {}).get("mtrchain", {}).get("M314")
            self.assertEqual((m314 or {}).get("status"), "PROVEN")
            # Geometry policy explicit
            self.assertIn("no adjacency invented", (cp5a.get("geometryPolicy") or "").lower())

    def test_mapper_without_decoder_falls_back_contract(self):
        # Mapper requires decoder dir summary; missing → still callable only with summary
        with tempfile.TemporaryDirectory() as td:
            # empty decoder dir → transport adapter empty but physical layout still builds
            Path(td).mkdir(exist_ok=True)
            if not (PLC2 / "FORTNA" / "fortna.mnu").is_file():
                self.skipTest("PLC2 fixture missing")
            # Write minimal empty summary so mapper proceeds
            (Path(td) / "cp5a-decoder-summary.json").write_text(
                '{"ok": true, "transportation": {"status": "PASS", "objects": [], "proofs": {}}, '
                '"mtrchain": {"status": "PASS", "objects": [], "proofs": {}}}',
                encoding="utf-8",
            )
            graph = map_cp4_to_transport_graph(
                run_dir=PLC2, machine="ORNCCP2", decoder_dir=Path(td)
            )
            self.assertTrue(graph.get("ok"))
            self.assertTrue(graph.get("areas"))


if __name__ == "__main__":
    unittest.main()

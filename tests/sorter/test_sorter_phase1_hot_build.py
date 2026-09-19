#!/usr/bin/env python3
"""Sorter Phase 1 hot generation — Gates P/R/S/U.

PLC5: emit Sorter_Track from RUN SorterModel (not finished-PLC discovery).
PLC4: same compiler path when RUN available.
PLC2: must NOT emit Sorter_Track (0 active sorters).
"""
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


import re
import unittest
from pathlib import Path

SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
import sys

sys.path.insert(0, str(SCRIPTS))

from fortna_sorter_discovery import build_canonical_sorter_model  # noqa: E402
from fortna_sorter_pack_compiler import (  # noqa: E402
    compile_sorter_track_pack,
    should_emit_sorter,
    sorter_model_to_build_config,
    write_generation_report,
)
from fortna_sorter_build import SORTER_TRACK_PACK  # noqa: E402

CP5_RUN = ROOT / "workspace" / "cp5-run" / "RUN"
CP4_RUN = ROOT / "workspace" / "cp4-run" / "RUN"
PLC2_RUN = ROOT / "workspace" / "_plc2_run_peek" / "RUN"
OUT = ROOT / "exports" / "stabilization"


class TestSorterPhase1AntiCheat(unittest.TestCase):
    def test_no_site_decision_in_compiler(self) -> None:
        for name in (
            "fortna_sorter_pack_compiler.py",
            "fortna_sorter_build.py",
        ):
            text = (SCRIPTS / name).read_text(encoding="utf-8", errors="replace")
            self.assertNotRegex(text, r"""machine\s*==\s*['\"]ORNCCP""")
            self.assertNotIn("if PLC5", text)
            self.assertNotIn("if PLC4", text)
            self.assertNotIn("506_SHIP_SORTER", text)
            self.assertNotIn("Greensboro", text)
            # Must not invent ENC from P suffix
            self.assertNotRegex(
                text,
                r"""ENC\{?m\.group|f[\"']ENC\{""",
            )


@unittest.skipUnless(CP5_RUN.is_dir() and SORTER_TRACK_PACK.is_file(), "CP5 RUN or pack missing")
class TestPlc5HotSorterGeneration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = build_canonical_sorter_model(CP5_RUN, "ORNCCP5")
        cls.result = compile_sorter_track_pack(sorter_model=cls.model, library_text="")
        write_generation_report(cls.result, OUT)

    def test_emits_sorter_track(self) -> None:
        self.assertTrue(self.result["ok"])
        self.assertTrue(self.result["emitted"])
        self.assertIn("PHASE1", self.result["plc_generation"])
        xml = self.result.get("program_xml") or ""
        self.assertIn('Name="Sorter_Track"', xml)
        self.assertIn('Name="Main"', xml)

    def test_not_not_started(self) -> None:
        self.assertNotEqual(self.result["plc_generation"], "NOT_STARTED")
        self.assertNotEqual(self.model.get("plc_generation"), "NOT_STARTED")
        self.assertIn("PHASE1", str(self.model.get("plc_generation")))

    def test_encoder_multiplicity_from_model(self) -> None:
        rep = self.result["report"]
        self.assertGreaterEqual(int(rep.get("encoder_count") or 0), 1)
        # Model has 5 encoders for CP5
        self.assertEqual(self.model.get("encoder_count") or self.model.get("sorter_count"), 5)

    def test_divert_multiplicity_from_model(self) -> None:
        n = int(self.model.get("divert_count") or len(self.model.get("divert_rows") or []))
        self.assertEqual(n, 32)
        rep = self.result["report"]
        kept = rep.get("wave_rungs_kept")
        # Phase 1 expands pack template slots to model N (MODEL_EXPANDED clones)
        self.assertEqual(int(kept), 32)
        self.assertGreaterEqual(int(rep.get("wave_rungs_in_pack") or 0), 1)

    def test_routines_populated(self) -> None:
        routines = set(self.result["report"].get("routines") or [])
        for need in (
            "Main",
            "Encoder",
            "Track_Induct_Package",
            "Track_Divert_Package",
            "Wave_Divert",
            "Scanner",
        ):
            self.assertIn(need, routines)
        # Must not be NOP-only Main
        xml = self.result["program_xml"]
        main = re.search(
            r'<Routine Name="Main"[^>]*>.*?</Routine>', xml, re.S
        )
        self.assertIsNotNone(main)
        self.assertIn("JSR(", main.group(0))

    def test_severity_optional_does_not_fatal(self) -> None:
        sev = self.result.get("severity") or {}
        self.assertTrue(sev.get("can_emit"))
        self.assertEqual(sev.get("FATAL_ERROR") or [], [])


@unittest.skipUnless(PLC2_RUN.is_dir(), "PLC2 RUN missing")
class TestPlc2NoSorterNegative(unittest.TestCase):
    def test_plc2_does_not_emit(self) -> None:
        model = build_canonical_sorter_model(PLC2_RUN, "ORNCCP2")
        self.assertEqual(model.get("sorter_count") or 0, 0)
        self.assertFalse(should_emit_sorter(None, model))
        cfg = sorter_model_to_build_config(model)
        # Empty known/tracking → assess may fatal; compiler should not emit
        result = compile_sorter_track_pack(sorter_model=model, library_text="")
        # Either blocked or not emitted
        self.assertFalse(result.get("emitted"))


@unittest.skipUnless(
    (ROOT / "workspace" / "cp4-run" / "RUN").is_dir() and SORTER_TRACK_PACK.is_file(),
    "CP4 RUN missing",
)
class TestPlc4BlindSorterGeneration(unittest.TestCase):
    def test_plc4_uses_same_compiler(self) -> None:
        model = build_canonical_sorter_model(CP4_RUN, "ORNCCP4")
        if int(model.get("sorter_count") or 0) == 0:
            self.skipTest("PLC4 RUN has 0 active sorters in this fixture")
        result = compile_sorter_track_pack(sorter_model=model, library_text="")
        self.assertTrue(result.get("emitted"))
        self.assertIn('Name="Sorter_Track"', result.get("program_xml") or "")
        # Divert count must equal model, not hard-coded 32
        n = int(model.get("divert_count") or len(model.get("divert_rows") or []))
        kept = (result.get("report") or {}).get("wave_rungs_kept")
        if kept is not None and int(kept) >= 0 and n > 0:
            self.assertEqual(int(kept), n)


class TestNDivertExpansion(unittest.TestCase):
    @unittest.skipUnless(SORTER_TRACK_PACK.is_file(), "pack missing")
    def test_n_diverts_keeps_n_wave_rungs(self) -> None:
        fake = {
            "sorter_count": 1,
            "sorters": [{"name": {"value": "TEST_SORTER"}, "encoder_io": {"value": "ENC_TEST"}}],
            "divert_count": 3,
            "divert_rows": [{"lane": f"L{i}"} for i in range(3)],
            "tracking_path": [
                {"encoder_tag": {"value": "ENC_TEST"}, "conveyor": {"value": "P100"}}
            ],
            "induct": {
                "encoder": {"value": "ENC_TEST"},
                "conveyor": {"value": "P100"},
                "photoeye": {"value": "PE100"},
            },
        }
        result = compile_sorter_track_pack(sorter_model=fake, library_text="")
        self.assertTrue(result["emitted"])
        self.assertEqual(int(result["report"].get("wave_rungs_kept") or 0), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""ORI-077 — CURRENT RUN MergeBoss/MergeInputs 2→1 fidelity (synthetic).

Covers:
  - real 2-to-1 merge orientation from lanes / presence PE / release IO / owner
  - ambiguous merge → REVIEW_REQUIRED (no HMI geometry inference)
  - no site-specific merge names hardcoded
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_plc2_merge_discovery import (  # noqa: E402
    _boss_number,
    discover_plc2_merges,
    discovery_to_autogen_merges_2to1,
)
from fortna_transport_graph import _seed_proven_blind_merges  # noqa: E402

MSCRENO_RUN = (
    _SF_REPO
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
    / "RUN"
)


def _write_asc(path: Path, header: str, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([header] + rows) + "\n", encoding="utf-8")


def _minimal_run(td: Path, machine: str = "SYNTHPLC") -> Path:
    run = td / "RUN"
    fortna = run / "FORTNA"
    fortna.mkdir(parents=True)
    (run / "project.cfg").write_text(f"MACHINENAME = {machine}\n", encoding="utf-8")
    for stem in (
        "Mtrchain",
        "Jamcheck",
        "Conveyor",
        "Fulljam",
        "Fullline",
        "Configio",
        "FORTNADT",
        "Stop",
        "MergeRoute",
        "MergeRunOutputs",
    ):
        _write_asc(fortna / f"{stem}.asc", '"Name"', ["N/A~"])
    return run


class TestBossNumberLanePair(unittest.TestCase):
    def test_lane_pair_boss_has_no_numeric_discharge_guess(self) -> None:
        self.assertIsNone(_boss_number("P2-P18"))
        self.assertIsNone(_boss_number("P1001-P105A"))
        self.assertIsNone(_boss_number("P15-P72"))
        self.assertEqual(_boss_number("MERGE_400_2-1"), "400")


class TestSyntheticTwoToOneOrientation(unittest.TestCase):
    """Lanes + presence + release + owner → oriented 2→1; no geometry."""

    def test_explicit_lanes_and_discharge(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run = _minimal_run(Path(td), "SYNTHPLC")
            fortna = run / "FORTNA"
            _write_asc(
                fortna / "MergeBoss.asc",
                '"Name"~"Process"~"Owner"~"CurrInput"~"NumInputs"~"OperableInput"~"Valid"',
                [
                    "N/A~N/A~N/A~0~0~INVALID~N~",
                    "MERGE_900_2-1~CTRL~SYNTHPLC~0~2~M900_AUX~Y~",
                ],
            )
            _write_asc(
                fortna / "MergeInputs.asc",
                '"Name"~"MergeBoss"~"Valid"~"Index"~"Presense"~"ReleaseIO"'
                '~"FullClearTimerName"~"ClrTimerName"~"RunTimerName"~"LnClrTimerName"',
                [
                    "N/A~N/A~N~0~INVALID~INVALID~N/A~N/A~N/A~N/A~",
                    "P910~MERGE_900_2-1~Y~0~PE910_P~M910~tmPE910_F~tmPE910_CLR~tmM910RUN~tmPE910_LN~",
                    "P920~MERGE_900_2-1~Y~1~PE920_P~M920~tmPE920_F~tmPE920_CLR~tmM920RUN~tmPE920_LN~",
                ],
            )
            _write_asc(
                fortna / "Mtrchain.asc",
                '"Motor_Name"~"Motor_Chained1"~"Motor_Chained2"~"Timer_Name"~"Motor_Aux"',
                [
                    "N/A~N/A~N/A~N/A~N/A~",
                    "M910~P910~P900~tmM910~N/A~",
                    "M920~P920~P900~tmM920~N/A~",
                    "M900~P900~N/A~LATCH_MERGE_900~M900_AUX~",
                ],
            )
            _write_asc(
                fortna / "Conveyor.asc",
                '"IO_Name"~"Type"~"Machine_Name"',
                [
                    "N/A~N/A~N/A~",
                    "P910~STRAIGHT~SYNTHPLC~",
                    "P920~STRAIGHT~SYNTHPLC~",
                    "P900~STRAIGHT~SYNTHPLC~",
                ],
            )
            _write_asc(
                fortna / "Jamcheck.asc",
                '"Zone"~"Conveyor_Name"~"Sensor_Name"~"Jam_Owner"',
                [
                    "N/A~N/A~N/A~N/A~",
                    "900 Merge~P900~PE900_J~SYNTHPLC~",
                ],
            )
            report = discover_plc2_merges(run, "SYNTHPLC")
            by = {m.get("name"): m for m in (report.get("merges") or [])}
            m = by.get("MERGE_900_2-1")
            self.assertIsNotNone(m, list(by))
            self.assertEqual(m.get("mainLane"), "P910")
            self.assertEqual(m.get("inductLane"), "P920")
            self.assertEqual(m.get("downstream"), "P900")
            self.assertEqual(m.get("classification"), "PROVEN")
            # Orientation is merge (2→1), not diverge
            self.assertNotEqual(m.get("downstream"), m.get("mainLane"))
            rows = discovery_to_autogen_merges_2to1(report)
            self.assertTrue(any(r.get("discharge") == "P900" for r in rows))


class TestAmbiguousMergeReview(unittest.TestCase):
    def test_lanes_without_discharge_are_review_required(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run = _minimal_run(Path(td), "SYNTHPLC")
            fortna = run / "FORTNA"
            _write_asc(
                fortna / "MergeBoss.asc",
                '"Name"~"Process"~"Owner"~"CurrInput"~"NumInputs"~"OperableInput"~"Valid"',
                [
                    "N/A~N/A~N/A~0~0~INVALID~N~",
                    "P2-P18~CTRL~SYNTHPLC~0~2~MEM_OK~Y~",
                ],
            )
            _write_asc(
                fortna / "MergeInputs.asc",
                '"Name"~"MergeBoss"~"Valid"~"Index"~"Presense"~"ReleaseIO"',
                [
                    "N/A~N/A~N~0~INVALID~INVALID~",
                    "P2~P2-P18~Y~0~EZPE53_P~EZSSV4~",
                    "P18~P2-P18~Y~1~EZPE52_P~EZSSV5~",
                ],
            )
            _write_asc(
                fortna / "Conveyor.asc",
                '"IO_Name"~"Type"~"Machine_Name"',
                [
                    "N/A~N/A~N/A~",
                    "P2~STRAIGHT~SYNTHPLC~",
                    "P18~STRAIGHT~SYNTHPLC~",
                ],
            )
            report = discover_plc2_merges(run, "SYNTHPLC")
            by = {m.get("name"): m for m in (report.get("merges") or [])}
            m = by.get("P2-P18")
            self.assertIsNotNone(m, list(by))
            # Logical lanes from MergeInputs.Name — not PE digits (EZPE53 → P53)
            self.assertEqual(m.get("mainLane"), "P2")
            self.assertEqual(m.get("inductLane"), "P18")
            self.assertIsNone(m.get("downstream"))
            self.assertEqual(m.get("classification"), "REVIEW_REQUIRED")
            rows = discovery_to_autogen_merges_2to1(report, include_review=True)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].get("status"), "REVIEW_REQUIRED")
            self.assertEqual(rows[0].get("lane_a"), "P2")
            self.assertEqual(rows[0].get("lane_b"), "P18")
            self.assertEqual(rows[0].get("control_object"), "P2-P18")
            self.assertFalse(rows[0].get("discharge"))

            wb = {"machine": "SYNTHPLC", "run_dir": str(run), "merges_2to1": []}
            seeded = _seed_proven_blind_merges(wb)
            self.assertTrue(seeded)
            self.assertEqual(len(wb["merges_2to1"]), 1)
            self.assertEqual(wb["merges_2to1"][0].get("status"), "REVIEW_REQUIRED")


class TestMscrenoPickLiveWhenPresent(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not (MSCRENO_RUN / "FORTNA").is_dir():
            raise unittest.SkipTest(f"MSCRENOPICK RUN missing at {MSCRENO_RUN}")

    def test_three_merges_modeled_with_lane_names(self) -> None:
        report = discover_plc2_merges(MSCRENO_RUN, "MSCRENOPICK")
        by = {m.get("name"): m for m in (report.get("merges") or [])}
        for boss, lane_a, lane_b in (
            ("P2-P18", "P2", "P18"),
            ("P15-P72", "P15", "P72"),
            ("P1001-P105A", "P1001", "P105A"),
        ):
            m = by.get(boss)
            self.assertIsNotNone(m, f"missing {boss}; have {list(by)}")
            self.assertEqual(m.get("mainLane"), lane_a, m)
            self.assertEqual(m.get("inductLane"), lane_b, m)
            self.assertIn(
                m.get("classification"),
                {"PROVEN", "REVIEW_REQUIRED", "CANDIDATE"},
                m,
            )
        rows = discovery_to_autogen_merges_2to1(report, include_review=True)
        self.assertGreaterEqual(len(rows), 3)
        names = {r.get("discovery_name") or r.get("control_object") for r in rows}
        self.assertTrue({"P2-P18", "P15-P72", "P1001-P105A"} <= names)


if __name__ == "__main__":
    unittest.main()

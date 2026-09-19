#!/usr/bin/env python3
"""GATE 6 — Native 2→1 merge discovery via MergeBoss / MergeInputs / MergeRoute.

Tests:
  - positive native merge (ORINDYAC6 2-1 SERVO → P600)
  - no-merge negative (empty overlay / invalid-only bosses)
  - other-machine exclusion (ORNCCP2 merges not attributed to ORINDYAC6)
  - base-vs-overlay contamination (base empty + overlay wins; frozen PLC2
    blind_report must not seed into a different workbook machine)
  - GATE 7: ordinary MergeBoss path never includes Sawtooth_Merge
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from fortna_plc2_merge_discovery import (  # noqa: E402
    discover_plc2_merges,
    discovery_to_autogen_merges_2to1,
)
from fortna_transport_graph import _seed_proven_blind_merges  # noqa: E402

ORINDY_RUN = ROOT / "workspace" / "_virgin_orindy" / "RUN"
PLC2_RUN = ROOT / "workspace" / "_plc2_run_peek" / "RUN"


def _write_asc(path: Path, header: str, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join([header] + rows) + "\n"
    path.write_text(body, encoding="utf-8")


class TestNativeMergePositiveOrindy(unittest.TestCase):
    """Positive: ORINDYAC6 MergeBoss 2-1 SERVO → P600 from RUN only."""

    @classmethod
    def setUpClass(cls) -> None:
        if not (ORINDY_RUN / "FORTNA").is_dir():
            raise unittest.SkipTest(f"ORINDYAC6 RUN missing at {ORINDY_RUN}")

    def test_p600_2to1_from_native_tables(self) -> None:
        report = discover_plc2_merges(ORINDY_RUN, "ORINDYAC6")
        by_name = {m.get("name"): m for m in (report.get("merges") or [])}
        m600 = by_name.get("2-1 SERVO")
        self.assertIsNotNone(m600, f"missing 2-1 SERVO; have {list(by_name)}")
        self.assertEqual(m600.get("classification"), "PROVEN", m600)
        self.assertEqual(m600.get("mainLane"), "P542")
        self.assertEqual(m600.get("inductLane"), "P644")
        self.assertEqual(m600.get("downstream"), "P600")
        self.assertEqual(m600.get("sourceClassification"), "2-1")
        self.assertEqual(m600.get("bossNumber"), "600")
        # Firewall: finished PLC not read
        self.assertFalse(report.get("firewall", {}).get("finished_l5x_read"))

        rows = discovery_to_autogen_merges_2to1(report)
        discharges = {r.get("discharge") for r in rows}
        self.assertIn("P600", discharges)
        p600 = next(r for r in rows if r.get("discharge") == "P600")
        self.assertEqual(p600.get("lane_a"), "P542")
        self.assertEqual(p600.get("lane_b"), "P644")
        self.assertEqual(p600.get("source"), "native_merge_discovery")
        self.assertEqual(p600.get("discovery_machine"), "ORINDYAC6")


class TestNativeMergeNoMergeNegative(unittest.TestCase):
    """Negative: Valid=N / empty overlay → no merges."""

    def test_invalid_only_bosses_yield_no_merges(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run = Path(td) / "RUN"
            fortna = run / "FORTNA"
            fortna.mkdir(parents=True)
            (run / "project.cfg").write_text(
                "MACHINENAME = EMPTYPLC\n", encoding="utf-8"
            )
            _write_asc(
                fortna / "MergeBoss.asc",
                '"Name"~"Process"~"Owner"~"CurrInput"~"NumInputs"~"OperableInput"~"Valid"',
                [
                    "N/A~N/A~N/A~0~0~INVALID~N~",
                    " ~N/A~N/A~1~0~INVALID~N~",
                ],
            )
            _write_asc(
                fortna / "MergeInputs.asc",
                '"Name"~"MergeBoss"~"Valid"~"Index"~"Presense"~"ReleaseIO"',
                ["N/A~N/A~N~0~INVALID~INVALID~"],
            )
            _write_asc(
                fortna / "MergeRoute.asc",
                '"Name"~"MergeInputs"',
                ["N/A~N/A~"],
            )
            # Minimal stubs so discovery can open tables
            for stem in (
                "Mtrchain",
                "Jamcheck",
                "Conveyor",
                "Fulljam",
                "Fullline",
                "Configio",
                "FORTNADT",
                "Stop",
                "MergeRunOutputs",
            ):
                _write_asc(fortna / f"{stem}.asc", '"Name"', ["N/A~"])

            report = discover_plc2_merges(run, "EMPTYPLC")
            self.assertEqual(report.get("counts", {}).get("total"), 0)
            self.assertEqual(discovery_to_autogen_merges_2to1(report), [])


class TestNativeMergeOtherMachineExclusion(unittest.TestCase):
    """ORNCCP2 MergeBoss rows must not appear under ORINDYAC6 discovery."""

    @classmethod
    def setUpClass(cls) -> None:
        if not (ORINDY_RUN / "FORTNA").is_dir():
            raise unittest.SkipTest(f"ORINDYAC6 RUN missing at {ORINDY_RUN}")
        if not (PLC2_RUN / "FORTNA").is_dir():
            raise unittest.SkipTest(f"PLC2 RUN missing at {PLC2_RUN}")

    def test_orindy_excludes_greensboro_boss_names(self) -> None:
        orindy = discover_plc2_merges(ORINDY_RUN, "ORINDYAC6")
        names = {m.get("name") for m in (orindy.get("merges") or [])}
        for banned in (
            "MERGE_316_SPUR",
            "MERGE_400_2-1",
            "MERGE_324_SPUR",
            "MERGE_406_3-1",
        ):
            self.assertNotIn(banned, names)

        plc2 = discover_plc2_merges(PLC2_RUN, "ORNCCP2")
        plc2_names = {m.get("name") for m in (plc2.get("merges") or [])}
        self.assertTrue({"MERGE_316_SPUR", "MERGE_400_2-1"} & plc2_names)

        # Shared Mtrchain may contain CP2 latch rows — discharges must stay scoped
        orindy_down = {
            m.get("downstream") for m in (orindy.get("merges") or []) if m.get("downstream")
        }
        self.assertNotIn("P406", orindy_down)
        self.assertNotIn("P400", orindy_down)
        self.assertIn("P600", orindy_down)


class TestBaseVsOverlayContamination(unittest.TestCase):
    """Overlay MergeBoss wins; frozen PLC2 report must not seed other machines."""

    @classmethod
    def setUpClass(cls) -> None:
        if not (ORINDY_RUN / "FORTNA").is_dir():
            raise unittest.SkipTest(f"ORINDYAC6 RUN missing at {ORINDY_RUN}")

    def test_base_empty_overlay_provides_orindy_bosses(self) -> None:
        report = discover_plc2_merges(ORINDY_RUN, "ORINDYAC6")
        names = {m.get("name") for m in (report.get("merges") or [])}
        # Base MergeBoss.asc is all-invalid; overlay supplies these
        self.assertIn("2-1 SERVO", names)
        self.assertIn("RECIRC SPUR", names)

    def test_frozen_plc2_blind_report_does_not_seed_orindy_workbook(self) -> None:
        # Ensure frozen PLC2 report exists (written by PLC2 discovery regression)
        frozen = ROOT / "exports" / "plc2-merge-discovery" / "blind_report.json"
        if not frozen.is_file():
            raise unittest.SkipTest("plc2 blind_report.json missing")
        data = json.loads(frozen.read_text(encoding="utf-8"))
        self.assertEqual(str(data.get("machine") or "").upper(), "ORNCCP2")

        wb = {
            "machine": "ORINDYAC6",
            "merges_2to1": [],
            # Force frozen-report path: no matching run_dir MACHINENAME probe by
            # pointing at a non-existent path and clearing live discovery.
            "run_dir": str(ROOT / "workspace" / "_does_not_exist_run"),
        }
        seeded = _seed_proven_blind_merges(wb)
        self.assertEqual(seeded, [])
        self.assertEqual(wb.get("merges_2to1"), [])

    def test_seed_live_orindy_when_run_dir_matches(self) -> None:
        wb = {
            "machine": "ORINDYAC6",
            "run_dir": str(ORINDY_RUN),
            "merges_2to1": [],
        }
        seeded = _seed_proven_blind_merges(wb)
        self.assertIn("P600", seeded)
        discharges = {m.get("discharge") for m in wb.get("merges_2to1") or []}
        self.assertIn("P600", discharges)
        for m in wb.get("merges_2to1") or []:
            self.assertNotIn(
                m.get("discovery_name"),
                {"MERGE_316_SPUR", "MERGE_400_2-1", "MERGE_324_SPUR", "MERGE_406_3-1"},
            )


class TestSawtoothStaysSeparate(unittest.TestCase):
    """GATE 7 — ordinary MergeBoss discovery never implies Sawtooth_Merge."""

    def test_discovery_rows_are_merge_2to1_not_sawtooth(self) -> None:
        if not (ORINDY_RUN / "FORTNA").is_dir():
            raise unittest.SkipTest("ORINDYAC6 RUN missing")
        report = discover_plc2_merges(ORINDY_RUN, "ORINDYAC6")
        rows = discovery_to_autogen_merges_2to1(report)
        self.assertTrue(rows, "expected proven native merges")
        for r in rows:
            self.assertEqual(r.get("suggested_aoi"), "Merge_2to1")
            self.assertNotIn("Sawtooth", str(r.get("discovery_name") or ""))
            self.assertNotEqual(r.get("suggested_aoi"), "Sawtooth_Merge")

    def test_inclusion_gate_still_strips_sawtooth_for_ordinary_merge(self) -> None:
        from fortna_autogen import (  # noqa: WPS433
            AutogenInput,
            ConveyorRow,
            apply_sawtooth_merge_inclusion_gate,
        )

        inp = AutogenInput(
            project_name="ORINDYAC6_Shipping",
            machine="ORINDYAC6",
            conveyors=[
                ConveyorRow(number=1, conveyor="P600", main_area="A", type="Transport"),
                ConveyorRow(number=2, conveyor="P542", main_area="A", type="Transport"),
                ConveyorRow(number=3, conveyor="P644", main_area="A", type="Transport"),
            ],
            include_programs=["Devices_Comm", "Sawtooth_Merge"],
            merges_2to1=[
                {
                    "name": "P600",
                    "lane_a": "P542",
                    "lane_b": "P644",
                    "discharge": "P600",
                    "suggested_aoi": "Merge_2to1",
                    "source": "native_merge_discovery",
                }
            ],
            sawtooth_build={},
        )
        decision = apply_sawtooth_merge_inclusion_gate(inp)
        self.assertFalse(decision["allowed"], decision)
        self.assertNotIn("Sawtooth_Merge", inp.include_programs)


class TestPlc2RegressionUnbroken(unittest.TestCase):
    """Native-table path must not break PLC2 proven merges."""

    def test_plc2_four_proven(self) -> None:
        if not (PLC2_RUN / "FORTNA").is_dir():
            raise unittest.SkipTest("PLC2 RUN missing")
        report = discover_plc2_merges(PLC2_RUN, "ORNCCP2")
        proven = [
            m for m in (report.get("merges") or []) if m.get("classification") == "PROVEN"
        ]
        self.assertGreaterEqual(len(proven), 4)
        by = {m.get("name"): m for m in proven}
        self.assertEqual(by["MERGE_400_2-1"].get("downstream"), "P400")
        self.assertEqual(by["MERGE_316_SPUR"].get("mainLane"), "P136_P1")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Critical I/O source conservation gate.

Proves:
1. Upstream RUN ledger is the I/O completeness denominator (not physical_io_map.csv).
2. Removing a real upstream PB/Safety from canonical discovery MUST FAIL even when
   every remaining physical_io_map.csv row is perfectly self-accounted.
3. Coverage is NOT_PROVEN when the ledger is incomplete — never fake 100%.
"""
from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from fortna_run_io_source_ledger import (  # noqa: E402
    STATUS_MAPPED,
    STATUS_REVIEW,
    STATUS_SILENT,
    audit_source_conservation,
    build_run_io_source_ledger,
    reconcile_ledger,
)


def _write_map(path: Path, rows: list[tuple[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "fortna_name",
                "device_type",
                "direction",
                "fortna_bank",
                "fortna_bit",
                "module_data_ref",
                "mapped",
                "notes",
            ]
        )
        for name, mapped in rows:
            w.writerow([name, "io", "I", "1001", "0", "AENTR1:I.Data[0].0", mapped, ""])


class TestCsvSelfAccountingIsInsufficient(unittest.TestCase):
    def test_perfect_csv_still_fails_when_upstream_missing(self) -> None:
        """Critical regression: CSV-only 100% must not mask a dropped RUN device."""
        ledger = {
            "machine": "MSCRENOPICK",
            "ledger_complete": True,
            "candidates": [
                {
                    "source_signal": "ESPB2",
                    "source_file": "FORTNA/Conveyor.asc",
                    "source_type": "conveyor_named_claim",
                    "machine": "MSCRENOPICK",
                    "ownership_hint": "OWN",
                    "word": "1006",
                    "bit": "14",
                    "highlight": "ESPB",
                },
                {
                    "source_signal": "PB6_JR",
                    "source_file": "FORTNA/Conveyor.asc",
                    "source_type": "conveyor_named_claim",
                    "machine": "N/A",
                    "ownership_hint": "WILDCARD",
                    "word": "1101",
                    "bit": "1",
                    "highlight": "PUSHBUTTON_CONTROL",
                },
                {
                    "source_signal": "3PBSTART",
                    "source_file": "FORTNA/Conveyor.asc",
                    "source_type": "conveyor_named_claim",
                    "machine": "MSCRENOPACK",
                    "ownership_hint": "FOREIGN",
                    "word": "1017",
                    "bit": "15",
                    "highlight": "PUSHBUTTON_CONTROL",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            # CSV perfectly accounts for ESPB2 only — classic false 100% pattern
            map_csv = tdir / "physical_io_map.csv"
            _write_map(map_csv, [("ESPB2", "Y")])

            # Canonical discovery deliberately DROPS PB6_JR (the regression)
            canon = {"ESPB2"}
            recon = reconcile_ledger(
                ledger,
                physical_io_map_csv=map_csv,
                l5x_path=None,
                machine="MSCRENOPICK",
                canonical_device_names=canon,
            )
            # CSV self-consistency would look fine (1 mapped / 1 row)
            self.assertEqual(recon["mapped"], 1)
            self.assertEqual(recon["foreign"], 1)  # 3PBSTART
            self.assertGreaterEqual(recon["silently_missing"], 1)
            self.assertIn("PB6_JR", recon["silently_missing_devices"])
            self.assertFalse(recon["conservation_ok"])
            fails = audit_source_conservation(recon)
            self.assertTrue(fails)
            self.assertTrue(
                any("PB6_JR" in str(f.get("signature") or "") for f in fails),
                fails,
            )

    def test_coverage_not_proven_when_ledger_incomplete(self) -> None:
        ledger = {
            "machine": "X",
            "ledger_complete": False,
            "candidates": [],
        }
        recon = reconcile_ledger(ledger, machine="X", canonical_device_names=set())
        self.assertEqual(recon["coverage_status"], "NOT_PROVEN")
        self.assertIsNone(recon["coverage_pct"])
        self.assertFalse(recon["conservation_ok"])


class TestHappyPathConservation(unittest.TestCase):
    def test_all_candidates_accounted(self) -> None:
        ledger = {
            "machine": "MSCRENOPICK",
            "ledger_complete": True,
            "candidates": [
                {
                    "source_signal": "ESPB2",
                    "source_file": "FORTNA/Conveyor.asc",
                    "source_type": "conveyor_named_claim",
                    "machine": "MSCRENOPICK",
                    "ownership_hint": "OWN",
                    "highlight": "ESPB",
                },
                {
                    "source_signal": "PB6_JR",
                    "source_file": "FORTNA/Conveyor.asc",
                    "source_type": "conveyor_named_claim",
                    "machine": "N/A",
                    "ownership_hint": "WILDCARD",
                    "highlight": "PUSHBUTTON_CONTROL",
                },
                {
                    "source_signal": "3PBSTART",
                    "source_file": "FORTNA/Conveyor.asc",
                    "source_type": "conveyor_named_claim",
                    "machine": "MSCRENOPACK",
                    "ownership_hint": "FOREIGN",
                    "highlight": "PUSHBUTTON_CONTROL",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            map_csv = Path(td) / "physical_io_map.csv"
            _write_map(map_csv, [("ESPB2", "Y"), ("PB6_JR", "N")])
            recon = reconcile_ledger(
                ledger,
                physical_io_map_csv=map_csv,
                machine="MSCRENOPICK",
                canonical_device_names={"ESPB2", "PB6_JR"},
            )
            self.assertEqual(recon["silently_missing"], 0)
            self.assertTrue(recon["conservation_ok"])
            self.assertEqual(recon["mapped"], 1)
            self.assertEqual(recon["review"], 1)
            self.assertEqual(recon["foreign"], 1)
            self.assertEqual(recon["coverage_status"], "PROVEN")
            self.assertEqual(
                recon["accounted"], recon["source_physical_candidates"]
            )


class TestAuditorRejectsSilentMissing(unittest.TestCase):
    def test_audit_l5x_source_conservation_failure(self) -> None:
        from fortna_l5x_acceptance_auditor import audit_l5x

        # Minimal L5X with IO_MAP present
        l5x = (
            '<?xml version="1.0"?>\n'
            "<RSLogix5000Content>"
            '<Controller Name="MSCRENOPICK">'
            '<Programs>'
            '<Program Name="IO_MAP"><Routines>'
            '<Routine Name="Main_Routine"><RLLContent>'
            "<Rung><Text><![CDATA[XIC(ESPB2);]]></Text></Rung>"
            "</RLLContent></Routine></Routines></Program>"
            '<Program Name="ES"><Routines>'
            '<Routine Name="Main_Routine"><RLLContent>'
            "<Rung><Text><![CDATA[JSR(Z_Safe_Logic);]]></Text></Rung>"
            "</RLLContent></Routine>"
            '<Routine Name="Z_Safe_Logic"><RLLContent>'
            "<Rung><Text><![CDATA[XIC(ESPB2);]]></Text></Rung>"
            "</RLLContent></Routine>"
            '<Routine Name="Z_Safe_PI"><RLLContent>'
            "<Rung><Text><![CDATA[OTE(PI_OK);]]></Text></Rung>"
            "</RLLContent></Routine>"
            "</Routines></Program>"
            "</Programs></Controller></RSLogix5000Content>"
        )
        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            l5x_path = tdir / "t.L5X"
            l5x_path.write_text(l5x, encoding="utf-8")
            reconciled = {
                "conservation_ok": False,
                "ledger_complete": True,
                "silently_missing": 1,
                "source_physical_candidates": 2,
                "failures": [
                    {
                        "code": "IO_SOURCE_CONSERVATION_FAILURE",
                        "signature": "IO:SOURCE_CONSERVATION_FAILURE:PB6_JR",
                        "device": "PB6_JR",
                    }
                ],
            }
            manifest = {
                "machine": "MSCRENOPICK",
                "transportation": {"required": False},
                "io": {
                    "required": True,
                    "program": "IO_MAP",
                    "source_conservation": {
                        "enforce": True,
                        "reconciled": reconciled,
                    },
                },
                "safety": {"required": False},
                "foreign_site_forbid": [],
            }
            result = audit_l5x(l5x_path, manifest)
            self.assertFalse(result.get("ok"))
            sigs = [f.get("signature") for f in (result.get("failures") or [])]
            self.assertTrue(
                any("SOURCE_CONSERVATION_FAILURE" in str(s) for s in sigs),
                sigs,
            )


class TestLiveMscrenopickLedgerBuilds(unittest.TestCase):
    @unittest.skipUnless(
        (
            ROOT
            / "workspace"
            / "_reno_peek"
            / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
            / "RUN"
            / "project.cfg"
        ).is_file()
        or (
            ROOT / "workspace" / "inbox" / "20260813-1132-MSCRENO-MSCRENOPICK-RUN.tar.gz"
        ).is_file(),
        "MSCRENOPICK RUN not available",
    )
    def test_ledger_finds_safety_and_pb_candidates(self) -> None:
        run = (
            ROOT
            / "workspace"
            / "_reno_peek"
            / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
            / "RUN"
        )
        if not (run / "project.cfg").is_file():
            self.skipTest("peek RUN missing")
        ledger = build_run_io_source_ledger(run, "MSCRENOPICK")
        self.assertTrue(ledger.get("ledger_complete"))
        self.assertGreater(ledger.get("source_physical_candidates") or 0, 0)
        names = {str(c.get("source_signal") or "").upper() for c in ledger.get("candidates") or []}
        # Known Safety on this fixture
        self.assertTrue({"ESPB2", "ESPB24", "ESPB32"} & names, names)
        # Pushbutton / control evidence exists in RUN (may be FOREIGN or WILDCARD)
        pb = [
            c
            for c in (ledger.get("candidates") or [])
            if str(c.get("highlight") or "").upper().startswith("PUSHBUTTON")
        ]
        self.assertGreater(len(pb), 0, "expected PB/control candidates in RUN ledger")


if __name__ == "__main__":
    unittest.main()

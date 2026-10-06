#!/usr/bin/env python3
"""Unique canonical device ledger + resolution metrics + engineer confirm."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_io_engineer_confirm import (  # noqa: E402
    CONFIRM_FOREIGN,
    CONFIRM_LOCAL,
    confirm_physical_device,
    load_confirmations,
)
from fortna_run_io_source_ledger import (  # noqa: E402
    STATUS_FOREIGN,
    STATUS_MAPPED,
    STATUS_REVIEW,
    STATUS_SPARE,
    audit_device_resolution,
    build_canonical_device_ledger,
)


def _evidence_ledger() -> dict:
    return {
        "machine": "MSCRENOPICK",
        "ledger_complete": True,
        "candidates": [
            {
                "id": "c1",
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
                "id": "c2",
                "source_signal": "ESPB2",
                "source_file": "FORTNA/EStop.asc",
                "source_type": "estop_table",
                "machine": "",
                "word": "1006",
                "bit": "14",
                "highlight": "ESPB",
            },
            {
                "id": "c3",
                "source_signal": "ESPB2",
                "source_file": "safety_model/evidence_union",
                "source_type": "safety_evidence",
                "machine": "MSCRENOPICK",
                "word": "1006",
                "bit": "14",
                "highlight": "ESPB",
                "canonical_hint": "ESPB2",
            },
            {
                "id": "c4",
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
                "id": "c5",
                "source_signal": "3PBSTART",
                "source_file": "FORTNA/Conveyor.asc",
                "source_type": "conveyor_named_claim",
                "machine": "MSCRENOPACK",
                "ownership_hint": "FOREIGN",
                "word": "1017",
                "bit": "15",
                "highlight": "PUSHBUTTON_CONTROL",
            },
            {
                "id": "c6",
                "source_signal": "AENTR1:I.Data[1].0",
                "source_file": "eipcfg+configio",
                "source_type": "physical_word_map",
                "machine": "MSCRENOPICK",
                "word": "1001",
                "bit": "0",
                "endpoint": "AENTR1:I.Data[1].0",
                "highlight": "PHYSICAL_CHANNEL",
            },
        ],
    }


class TestCanonicalCollapse(unittest.TestCase):
    def test_three_evidence_rows_become_one_device(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            map_csv = Path(td) / "physical_io_map.csv"
            map_csv.write_text(
                "fortna_name,device_type,direction,fortna_bank,fortna_bit,module_data_ref,mapped,notes\n"
                '"ESPB2","estop","I","1006","14","AENTR3:4:I.Data.4",Y,""\n',
                encoding="utf-8",
            )
            led = _evidence_ledger()
            names = {c["source_signal"].upper() for c in led["candidates"]}
            canon = build_canonical_device_ledger(
                led,
                machine="MSCRENOPICK",
                physical_io_map_csv=map_csv,
                canonical_device_names=names,
                apply_engineer_confirmations=False,
            )
            espb = [d for d in canon["devices"] if d["canonical_name"] == "ESPB2"]
            self.assertEqual(len(espb), 1, canon.get("devices"))
            self.assertEqual(espb[0]["source_evidence_count"], 3)
            self.assertEqual(espb[0]["final_status"], STATUS_MAPPED)
            self.assertEqual(canon["source_evidence_rows"], 6)
            self.assertLess(canon["unique_physical_candidates"], canon["source_evidence_rows"])
            foreign = [d for d in canon["devices"] if d["canonical_name"] == "3PBSTART"]
            self.assertEqual(foreign[0]["final_status"], STATUS_FOREIGN)
            # Foreign excluded from local denominator
            local_names = [
                d["canonical_name"]
                for d in canon["devices"]
                if d.get("ownership") != "FOREIGN" and d.get("final_status") != STATUS_FOREIGN
            ]
            self.assertNotIn("3PBSTART", local_names)
            self.assertEqual(canon["unique_foreign"], 1)


class TestResolutionMetrics(unittest.TestCase):
    def test_review_is_not_resolved_and_blocks_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            map_csv = Path(td) / "physical_io_map.csv"
            map_csv.write_text(
                "fortna_name,device_type,direction,fortna_bank,fortna_bit,module_data_ref,mapped,notes\n"
                '"ESPB2","estop","I","1006","14","AENTR3:4:I.Data.4",Y,""\n',
                encoding="utf-8",
            )
            led = _evidence_ledger()
            names = {c["source_signal"].upper() for c in led["candidates"]}
            canon = build_canonical_device_ledger(
                led,
                machine="MSCRENOPICK",
                physical_io_map_csv=map_csv,
                canonical_device_names=names,
                apply_engineer_confirmations=False,
            )
            pb = next(d for d in canon["devices"] if d["canonical_name"] == "PB6_JR")
            self.assertEqual(pb["final_status"], STATUS_REVIEW)
            self.assertGreaterEqual(canon["critical_unresolved_count"], 1)
            self.assertFalse(canon["engineering_resolution_ok"])
            fails = audit_device_resolution(canon, threshold_pct=85.0)
            self.assertTrue(any("PB6_JR" in str(f.get("signature")) for f in fails), fails)

    def test_conservation_ok_does_not_imply_resolution_ok(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            map_csv = Path(td) / "physical_io_map.csv"
            map_csv.write_text(
                "fortna_name,device_type,direction,fortna_bank,fortna_bit,module_data_ref,mapped,notes\n"
                '"ESPB2","estop","I","1006","14","AENTR3:4:I.Data.4",Y,""\n',
                encoding="utf-8",
            )
            led = _evidence_ledger()
            names = {c["source_signal"].upper() for c in led["candidates"]}
            canon = build_canonical_device_ledger(
                led,
                machine="MSCRENOPICK",
                physical_io_map_csv=map_csv,
                canonical_device_names=names,
                apply_engineer_confirmations=False,
            )
            self.assertTrue(canon["source_conservation_ok"])
            self.assertFalse(canon["engineering_resolution_ok"])


class TestEngineerConfirm(unittest.TestCase):
    def test_confirm_local_durable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "engineer_io_confirmations.json"
            r = confirm_physical_device(
                canonical_device="PB6_JR",
                classification=CONFIRM_LOCAL,
                controller="MSCRENOPICK",
                physical_endpoint="UNKNOWN_PENDING",
                reason="fixture confirm",
                store_path=store,
            )
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["status"], "ENGINEER_CONFIRMED")
            loaded = load_confirmations(store)
            self.assertIn("PB6_JR", loaded["confirmations"])

    def test_conflict_requires_ack(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "engineer_io_confirmations.json"
            r = confirm_physical_device(
                canonical_device="ESPB2",
                classification=CONFIRM_LOCAL,
                controller="MSCRENOPICK",
                proven_foreign=True,
                conflict_acknowledged=False,
                store_path=store,
            )
            self.assertFalse(r["ok"])
            self.assertEqual(r.get("code"), "CONFLICT_FOREIGN")


if __name__ == "__main__":
    unittest.main()

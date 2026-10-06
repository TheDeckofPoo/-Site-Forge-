#!/usr/bin/env python3
"""Physical-world-first I/O: no fake spare inflation; three separate metrics."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_io_equipment_classifier import classify_equipment  # noqa: E402
from fortna_run_io_source_ledger import (  # noqa: E402
    STATUS_SPARE,
    build_canonical_device_ledger,
)


def _ledger_with_channels() -> dict:
    return {
        "machine": "MSCRENOPICK",
        "ledger_complete": True,
        "candidates": [
            {
                "id": "pb1",
                "source_signal": "PB6_JR",
                "source_file": "FORTNA/Conveyor.asc",
                "source_type": "conveyor_named_claim",
                "machine": "N/A",
                "word": "1101",
                "bit": "1",
                "highlight": "PUSHBUTTON_CONTROL",
            },
            {
                "id": "mem1",
                "source_signal": "MEM_ENABLE_FLAG",
                "source_file": "FORTNA/Logic.asc",
                "source_type": "conveyor_named_claim",
                "machine": "MSCRENOPICK",
                "word": "2000",
                "bit": "0",
                "highlight": "IO",
            },
            {
                "id": "ch1",
                "source_signal": "AENTR1:I.Data[1].0",
                "source_file": "eipcfg+configio",
                "source_type": "physical_word_map",
                "machine": "MSCRENOPICK",
                "word": "1001",
                "bit": "0",
                "endpoint": "AENTR1:I.Data[1].0",
                "highlight": "PHYSICAL_CHANNEL",
            },
            {
                "id": "sp1",
                "source_signal": "SPARE",
                "source_file": "eipcfg+configio",
                "source_type": "physical_word_map",
                "machine": "MSCRENOPICK",
                "word": "1001",
                "bit": "1",
                "endpoint": "AENTR1:I.Data[1].1",
                "highlight": "PHYSICAL_CHANNEL",
            },
        ],
    }


class TestClassifier(unittest.TestCase):
    def test_nomenclature_and_internal(self) -> None:
        pb = classify_equipment("PBSTART")
        self.assertEqual(pb["equipment_class"], "CONTROL_STATION_START_PB")
        self.assertEqual(pb["evidence_class"], "PHYSICAL_FIELD_DEVICE")
        self.assertIn("Start_PB", pb.get("fortna_plus_hint") or "")
        mem = classify_equipment("MEM_FOO")
        self.assertEqual(mem["evidence_class"], "INTERNAL_LOGICAL")
        pe = classify_equipment("PE12")
        self.assertEqual(pe["equipment_class"], "PHOTOEYE")


class TestProvenSpareOnly(unittest.TestCase):
    def test_endpoint_channel_is_not_fake_spare(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            map_csv = Path(td) / "physical_io_map.csv"
            map_csv.write_text(
                "fortna_name,device_type,direction,fortna_bank,fortna_bit,module_data_ref,mapped,notes\n",
                encoding="utf-8",
            )
            led = _ledger_with_channels()
            names = {c["source_signal"].upper() for c in led["candidates"]}
            canon = build_canonical_device_ledger(
                led,
                machine="MSCRENOPICK",
                physical_io_map_csv=map_csv,
                canonical_device_names=names,
                apply_engineer_confirmations=False,
            )
            # Unoccupied endpoint-shaped channel must NOT inflate spare/resolution
            self.assertEqual(canon.get("unproven_channel_occupancy"), 1)
            spares = [
                d
                for d in canon["devices"]
                if d.get("final_status") == STATUS_SPARE
            ]
            self.assertEqual(len(spares), 1, spares)
            self.assertEqual(spares[0]["canonical_name"].upper(), "SPARE")
            # Internal logical excluded from physical denom
            self.assertGreaterEqual(int(canon.get("unique_internal_logical") or 0), 1)
            # Three metrics present and separate
            self.assertIn("SOURCE_CONSERVATION_PCT", canon)
            self.assertIn("PHYSICAL_DEVICE_RESOLUTION_PCT", canon)
            self.assertIn("GENERATED_PHYSICAL_IO_PCT", canon)
            # PB remains visible as physical field device
            pb = next(d for d in canon["devices"] if d["canonical_name"] == "PB6_JR")
            self.assertEqual(pb.get("evidence_class"), "PHYSICAL_FIELD_DEVICE")
            # Fake 85% from mass spare is impossible here (1 physical PB + maybe 1 spare)
            self.assertLess(canon["unique_physical_devices"], 10)


if __name__ == "__main__":
    unittest.main()

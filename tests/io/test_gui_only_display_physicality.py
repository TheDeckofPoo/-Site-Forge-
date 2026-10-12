#!/usr/bin/env python3
"""GUI_ONLY physicality: EStop/Errors display evidence never establishes physicality."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))

from fortna_io_equipment_classifier import classify_equipment  # noqa: E402
from fortna_run_io_source_ledger import (  # noqa: E402
    STATUS_FOREIGN,
    STATUS_GUI_ONLY,
    STATUS_INTERNAL,
    STATUS_MAPPED,
    build_canonical_device_ledger,
    build_run_io_source_ledger,
)
from fortna_safety_inventory_scope import (  # noqa: E402
    LOCAL_PHYSICAL,
    UNRELATED_FOREIGN,
    classify_safety_device_scope,
    partition_safety_inventory,
)

MSC_PICK_RUN = (
    REPO
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
    / "RUN"
)
PHYS_MAP = Path(
    r"C:\dev\worktree\FortnaPlus-transport-active\exports\delivery_gate_20261002"
    r"\active_control_gen\ori111_repair_1\physical_io_map.csv"
)
if not PHYS_MAP.is_file():
    PHYS_MAP = None


@unittest.skipUnless((MSC_PICK_RUN / "project.cfg").is_file(), "MSCRENOPICK RUN missing")
class TestGuiOnlyDisplayPhysicality(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        led = build_run_io_source_ledger(MSC_PICK_RUN, "MSCRENOPICK")
        cls.canon = build_canonical_device_ledger(
            led,
            machine="MSCRENOPICK",
            run_dir=MSC_PICK_RUN,
            physical_io_map_csv=PHYS_MAP,
            apply_engineer_confirmations=False,
        )
        cls.by = {d["canonical_name"].upper(): d for d in cls.canon["devices"]}

    def test_espb1o_gui_only(self) -> None:
        d = self.by["ESPB1O"]
        self.assertEqual(d.get("final_status"), STATUS_GUI_ONLY, d)
        self.assertEqual(d.get("evidence_class"), "GUI_ONLY")
        self.assertFalse(d.get("critical"))

    def test_esstop1_gui_only(self) -> None:
        d = self.by["ESSTOP1"]
        self.assertEqual(d.get("final_status"), STATUS_GUI_ONLY, d)
        self.assertEqual(d.get("evidence_class"), "GUI_ONLY")
        self.assertFalse(d.get("critical"))

    def test_espb20_foreign(self) -> None:
        d = self.by["ESPB20"]
        self.assertEqual(d.get("final_status"), STATUS_FOREIGN, d)
        self.assertEqual(d.get("ownership"), "FOREIGN")

    def test_picking_enable_internal_logical(self) -> None:
        # Classifier path (name is software-state nomenclature).
        r = classify_equipment("PICKING_ENABLE")
        self.assertEqual(r.get("evidence_class"), "INTERNAL_LOGICAL")
        self.assertEqual(r.get("equipment_class"), "INTERNAL_LOGICAL")
        # Synthetic ledger: display-only + Logic.asc operational reference → INTERNAL.
        led = {
            "machine": "MSCRENOPICK",
            "ledger_complete": True,
            "candidates": [
                {
                    "id": "pe1",
                    "source_signal": "PICKING_ENABLE",
                    "source_file": "FORTNA/EStop.asc",
                    "source_type": "estop_display",
                    "machine": "N/A",
                    "word": "",
                    "bit": "",
                    "highlight": "IO",
                }
            ],
        }
        # Ensure Logic.asc contains the token in the MSCRENOPICK RUN fixture.
        logic = (MSC_PICK_RUN / "FORTNA" / "Logic.asc").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("PICKING_ENABLE", logic.upper())
        with tempfile.TemporaryDirectory() as td:
            map_csv = Path(td) / "physical_io_map.csv"
            map_csv.write_text(
                "fortna_name,device_type,direction,fortna_bank,fortna_bit,"
                "module_data_ref,mapped,notes\n",
                encoding="utf-8",
            )
            canon = build_canonical_device_ledger(
                led,
                machine="MSCRENOPICK",
                run_dir=MSC_PICK_RUN,
                physical_io_map_csv=map_csv,
                canonical_device_names={"PICKING_ENABLE"},
                apply_engineer_confirmations=False,
            )
        d = next(x for x in canon["devices"] if x["canonical_name"] == "PICKING_ENABLE")
        self.assertEqual(d.get("final_status"), STATUS_INTERNAL, d)

    def test_local_physical_members_intact(self) -> None:
        for name in ("ESPB2", "ESPB24", "ESPB32", "ESLS2"):
            d = self.by[name]
            self.assertEqual(d.get("ownership"), "LOCAL", d)
            self.assertIn(d.get("final_status"), {STATUS_MAPPED, "REVIEW_REQUIRED"}, d)
            self.assertEqual(d.get("evidence_class"), "PHYSICAL_FIELD_DEVICE", d)

    def test_ship_esls_remain_foreign(self) -> None:
        for name in ("ESLS1", "ESLS13P7-1", "ESLS13P7-2", "ESLS13P9-1"):
            d = self.by[name]
            self.assertEqual(d.get("final_status"), STATUS_FOREIGN, d)

    def test_denominator_four_mapped_when_phys_map_present(self) -> None:
        if PHYS_MAP is None or not PHYS_MAP.is_file():
            self.skipTest("physical_io_map.csv missing")
        self.assertEqual(self.canon.get("unique_physical_devices"), 4)
        self.assertEqual(self.canon.get("unique_mapped"), 4)
        self.assertEqual(self.canon.get("PHYSICAL_DEVICE_RESOLUTION_PCT"), 100.0)
        self.assertEqual(self.canon.get("critical_unresolved_count"), 0)
        self.assertGreaterEqual(int(self.canon.get("unique_gui_only") or 0), 2)
        self.assertEqual(self.canon.get("SOURCE_CONSERVATION_PCT"), 100.0)

    def test_gui_only_not_in_safety_assignable(self) -> None:
        part = partition_safety_inventory(
            [
                {
                    "name": "ESPB1O",
                    "final_status": STATUS_GUI_ONLY,
                    "evidence_class": "GUI_ONLY",
                    "device_type": "GUI_ONLY",
                },
                {
                    "name": "ESPB24",
                    "controller": "MSCRENOPICK",
                    "ownership": "LOCAL",
                    "final_status": STATUS_MAPPED,
                    "evidence_class": "PHYSICAL_FIELD_DEVICE",
                },
            ],
            active_machine="MSCRENOPICK",
        )
        names = {d["name"].upper() for d in part["assignable"]}
        self.assertNotIn("ESPB1O", names)
        self.assertIn("ESPB24", names)
        self.assertEqual(
            classify_safety_device_scope(
                {
                    "name": "ESPB1O",
                    "final_status": STATUS_GUI_ONLY,
                    "evidence_class": "GUI_ONLY",
                },
                active_machine="MSCRENOPICK",
            ),
            UNRELATED_FOREIGN,
        )
        self.assertEqual(
            classify_safety_device_scope(
                {
                    "name": "ESPB24",
                    "controller": "MSCRENOPICK",
                    "ownership": "LOCAL",
                },
                active_machine="MSCRENOPICK",
            ),
            LOCAL_PHYSICAL,
        )


if __name__ == "__main__":
    unittest.main()

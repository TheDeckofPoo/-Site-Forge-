#!/usr/bin/env python3
"""Two-Area synthetic controller: create/rename/split/move + L5X regenerate."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from fortna_site_model import SiteModel, make_object, make_relationship  # noqa: E402
from fortna_area_ops import (  # noqa: E402
    create_area,
    move_equipment,
    rename_area,
    generate_area_l5x_snippet,
    propagate_area_to_workbook_rows,
)


def _model() -> SiteModel:
    m = SiteModel(machine_scope="ALPHASITE", run_dir="synthetic")
    m.areas = [
        make_object("area", "Area_1", provenance="ENGINEER_CONFIGURED_REQUIRED", inclusion="INCLUDED").to_dict()
    ]
    for name in ("P9001", "P9002", "P9003", "P9004"):
        m.equipment.append(
            make_object(
                "equipment",
                name,
                inclusion="INCLUDED",
                area_id="Area_1",
                equipment_type="STRAIGHT",
            ).to_dict()
        )
    m.motors.append(
        make_object("motor", "M9001", inclusion="INCLUDED").to_dict()
    )
    m.relationships.append(
        make_relationship(
            source="M9001",
            target="P9001",
            kind="motor_link",
            provenance="RUN_EXPLICIT",
            confidence="HIGH",
            evidence=[{"kind": "motor_link"}],
            source_table="Conveyor.asc",
        )
    )
    # Jam zone must NOT rename with Area
    m.operational_groups = {
        "jam_zones": [
            make_object("jam_zone", "JAM_ALPHA", inclusion="INCLUDED").to_dict()
        ]
    }
    return m


class TestMultiAreaE2E(unittest.TestCase):
    def test_create_rename_split_move_regenerate(self):
        model = _model()
        create_area(model, "Shipping_Area")
        create_area(model, "Induct_Area")
        self.assertEqual(len(model.areas), 3)

        # Move two conveyors to Shipping (device only)
        move_equipment(model, ["P9003", "P9004"], "Shipping_Area", move_attached=False)
        self.assertEqual(
            {e["normalized_name"]: e.get("area_id") for e in model.equipment if e["normalized_name"] in {"P9003", "P9004"}},
            {"P9003": "Shipping_Area", "P9004": "Shipping_Area"},
        )

        # Move P9001 with attached motor
        move_equipment(model, ["P9001"], "Induct_Area", move_attached=True)
        motor = next(x for x in model.motors if x["normalized_name"] == "M9001")
        self.assertEqual(motor.get("area_id"), "Induct_Area")

        # Rename Area_1 remaining equipment's area after rename
        rename_area(model, "Area_1", "Residual_Area")
        jam = (model.operational_groups or {}).get("jam_zones") or []
        self.assertEqual(jam[0].get("raw_name") or jam[0].get("normalized_name"), "JAM_ALPHA")

        rows = propagate_area_to_workbook_rows(
            [e for e in model.equipment if e.get("area_id") == "Shipping_Area"],
            "Shipping_Area",
        )
        self.assertTrue(all(r.get("main_area") == "Shipping_Area" for r in rows))

        # L5X snippet regeneration from inline library fixture
        lib = (
            '<Tag Name="Main_Area" TagType="Base" DataType="Area_UDT"></Tag>\n'
            '<Program Name="Main_Area_Fast"><Routines><Routine Name="Main"/></Routines></Program>\n'
        )
        with tempfile.TemporaryDirectory() as td:
            lib_path = Path(td) / "lib.L5X"
            lib_path.write_text(lib, encoding="utf-8")
            snip = generate_area_l5x_snippet("Shipping_Area", lib_path)
        xml = snip.get("xml") if isinstance(snip, dict) else str(snip)
        self.assertIn("Shipping_Area", xml)
        self.assertNotIn('Name="Main_Area"', xml)
        self.assertTrue(
            "Shipping_Area_Fast" in xml or any("Shipping_Area" in p for p in (snip.get("program_names") or []))
        )
        self.assertTrue(snip.get("model_driven"))


if __name__ == "__main__":
    unittest.main()

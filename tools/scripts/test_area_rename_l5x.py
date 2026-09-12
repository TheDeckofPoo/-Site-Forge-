#!/usr/bin/env python3
"""Deterministic Area rename → L5X snippet test (model-driven, not finished-PLC rewrite).

Uses synthetic non-Greensboro names. Self-contained with an inline Area_UDT
library fixture; optionally exercises the real O'Reilly library when present.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from fortna_area_ops import (  # noqa: E402
    create_area,
    delete_area,
    generate_area_l5x_snippet,
    move_equipment,
    propagate_area_to_workbook_rows,
    rename_area,
)
from fortna_autogen import AutogenInput, ConveyorRow  # noqa: E402
from fortna_site_model import (  # noqa: E402
    DEFAULT_AREA_ID,
    INCLUDED,
    PROV_ENGINEER,
    PROV_RUN_EXPLICIT,
    SiteModel,
    make_object,
    make_relationship,
)

REAL_LIBRARY = ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X"

# Minimal inline library: Area_UDT template only (no finished PLC content).
INLINE_LIBRARY = """<?xml version="1.0" encoding="UTF-8"?>
<RSLogix5000Content SchemaRevision="1.0">
  <Controller>
    <Tags>
      <Tag Name="Main_Area" TagType="Base" DataType="Area_UDT" Constant="false"
           ExternalAccess="Read/Write">
        <Data Format="Decorated"><Structure DataType="Area_UDT"/></Data>
      </Tag>
    </Tags>
  </Controller>
</RSLogix5000Content>
"""


def _minimal_model() -> SiteModel:
    model = SiteModel(machine_scope="SYNTH_CTRL1", run_dir="synthetic")
    area = make_object(
        "area",
        DEFAULT_AREA_ID,
        provenance=PROV_ENGINEER,
        inclusion=INCLUDED,
        confidence="HIGH",
        area_id=DEFAULT_AREA_ID,
        default_area=True,
    ).to_dict()
    area["name"] = DEFAULT_AREA_ID
    model.areas = [area]
    # Keep a jam zone that must NOT be renamed with the area.
    model.operational_groups = {
        "jam_zones": [
            make_object(
                "jam_zone",
                "Staging_JamZone1",
                provenance=PROV_RUN_EXPLICIT,
                inclusion=INCLUDED,
            ).to_dict()
        ],
        "startstop_zones": [
            make_object(
                "startstop_zone",
                "Staging_SSZone1",
                provenance=PROV_RUN_EXPLICIT,
                inclusion=INCLUDED,
            ).to_dict()
        ],
    }
    model.estop_zones = [
        make_object(
            "estop_zone",
            "Staging_ESZone1",
            provenance=PROV_RUN_EXPLICIT,
            inclusion=INCLUDED,
        ).to_dict()
    ]
    eq = make_object(
        "equipment",
        "P501",
        provenance=PROV_RUN_EXPLICIT,
        inclusion=INCLUDED,
        confidence="HIGH",
        area_id=DEFAULT_AREA_ID,
        equipment_type="STRAIGHT",
    ).to_dict()
    model.equipment = [eq]
    motor = make_object(
        "motor",
        "M501",
        provenance=PROV_RUN_EXPLICIT,
        inclusion=INCLUDED,
        confidence="HIGH",
        area_id=DEFAULT_AREA_ID,
        linked_conveyor="P501",
    ).to_dict()
    model.motors = [motor]
    model.relationships = [
        make_relationship(
            source="M501",
            target="P501",
            kind="motor_link",
            provenance=PROV_RUN_EXPLICIT,
            confidence="HIGH",
            evidence=[{"kind": "motor_link", "detail": "P501"}],
            source_table="Conveyor.asc",
        )
    ]
    return model


class TestAreaOpsBasics(unittest.TestCase):
    def test_rename_does_not_touch_zones(self):
        model = _minimal_model()
        jam_before = model.operational_groups["jam_zones"][0]["raw_name"]
        ss_before = model.operational_groups["startstop_zones"][0]["raw_name"]
        es_before = model.estop_zones[0]["raw_name"]
        rename_area(model, DEFAULT_AREA_ID, "Shipping_Area")
        self.assertEqual(model.areas[0]["raw_name"], "Shipping_Area")
        self.assertEqual(model.equipment[0]["area_id"], "Shipping_Area")
        self.assertEqual(model.operational_groups["jam_zones"][0]["raw_name"], jam_before)
        self.assertEqual(model.operational_groups["startstop_zones"][0]["raw_name"], ss_before)
        self.assertEqual(model.estop_zones[0]["raw_name"], es_before)

    def test_delete_empty_only(self):
        model = _minimal_model()
        create_area(model, "Empty_Staging_Area")
        delete_area(model, "Empty_Staging_Area")
        self.assertFalse(any(a.get("raw_name") == "Empty_Staging_Area" for a in model.areas))
        with self.assertRaises(ValueError):
            delete_area(model, DEFAULT_AREA_ID)

    def test_move_attached_uses_relationships_not_tag_similarity(self):
        model = _minimal_model()
        # P502 shares a tag-number pattern with M502 but has NO relationship —
        # must not move when move_attached follows P501 only.
        decoy = make_object(
            "motor",
            "M502",
            provenance=PROV_RUN_EXPLICIT,
            inclusion=INCLUDED,
            area_id=DEFAULT_AREA_ID,
        ).to_dict()
        model.motors.append(decoy)
        create_area(model, "Outbound_Area")
        move_equipment(model, ["P501"], "Outbound_Area", move_attached=True)
        self.assertEqual(model.equipment[0]["area_id"], "Outbound_Area")
        m501 = next(m for m in model.motors if m["raw_name"] == "M501")
        m502 = next(m for m in model.motors if m["raw_name"] == "M502")
        self.assertEqual(m501["area_id"], "Outbound_Area")
        self.assertEqual(m502["area_id"], DEFAULT_AREA_ID)


class TestAreaRenameL5X(unittest.TestCase):
    def test_model_driven_rename_snippet_inline_library(self):
        model = _minimal_model()
        # 1) Workbook / Autogen rows start as Area_1
        rows = propagate_area_to_workbook_rows(model.equipment, DEFAULT_AREA_ID)
        self.assertTrue(rows)
        self.assertEqual(rows[0]["main_area"], DEFAULT_AREA_ID)
        inp = AutogenInput(
            project_name="Synthetic_Shipping_CTRL",
            processor="1756-L83E",
            areas=[DEFAULT_AREA_ID],
            safety_zones=["Staging_ESZone1"],
            conveyors=[
                ConveyorRow(
                    number=1,
                    conveyor="P501",
                    main_area=DEFAULT_AREA_ID,
                    safety_zone="Staging_ESZone1",
                    type="Transport with MS",
                    motor_starter="Yes",
                )
            ],
        )
        self.assertEqual(inp.conveyors[0].main_area, DEFAULT_AREA_ID)

        # 2) Rename via fortna_area_ops (model is source of truth)
        rename_area(model, DEFAULT_AREA_ID, "Shipping_Area")
        area_name = model.areas[0]["raw_name"]
        self.assertEqual(area_name, "Shipping_Area")

        # Propagate model area → workbook / AutogenInput (not finished PLC)
        rows2 = propagate_area_to_workbook_rows(
            [e for e in model.equipment if e.get("area_id") == area_name],
            area_name,
        )
        self.assertEqual(rows2[0]["main_area"], "Shipping_Area")
        inp.areas = [area_name]
        for c in inp.conveyors:
            c.main_area = area_name

        # 3) Build path: regenerate Area tag/program XML from library Main_Area
        #    using the model area name (autogen-style), never finished-PLC rewrite.
        snippet = generate_area_l5x_snippet(area_name, INLINE_LIBRARY)
        xml = snippet["xml"]
        self.assertTrue(snippet["model_driven"])
        self.assertEqual(snippet["area_name"], "Shipping_Area")
        self.assertIn('Tag Name="Shipping_Area"', xml)
        self.assertTrue(any(n.startswith("Shipping_Area") for n in snippet["program_names"]))
        self.assertIn("Shipping_Area", xml)

        # Area_1 must not remain as an area tag / program name after rename build.
        self.assertNotIn('Tag Name="Area_1"', xml)
        self.assertNotRegex(xml, r'Program Name="Area_1')
        self.assertNotIn("Area_1", snippet["program_names"])
        self.assertIsNone(re.search(r'Program Name="Area_1(_Area)?_(Slow|Fast|L\d)"', xml))

        # 4) Prove model-driven: snippet area equals model/workbook area, and
        #    generation used Main_Area template (not a finished PLC path).
        self.assertEqual(snippet["area_name"], model.areas[0]["raw_name"])
        self.assertEqual(snippet["area_name"], rows2[0]["main_area"])
        self.assertEqual(snippet["area_name"], inp.conveyors[0].main_area)
        self.assertIn(snippet["source"], {"library_Main_Area", "inline_minimal"})
        self.assertNotIn("Finished", snippet["source"])
        self.assertNotIn(".L5X", str(snippet.get("source")))

    def test_real_library_when_present(self):
        if not REAL_LIBRARY.is_file():
            self.skipTest(f"library missing: {REAL_LIBRARY}")
        model = _minimal_model()
        rename_area(model, DEFAULT_AREA_ID, "Shipping_Area")
        area_name = model.areas[0]["raw_name"]
        snippet = generate_area_l5x_snippet(area_name, REAL_LIBRARY)
        xml = snippet["xml"]
        self.assertEqual(snippet["source"], "library_Main_Area")
        self.assertIn('Tag Name="Shipping_Area"', xml)
        self.assertIn("DataType=\"Area_UDT\"", xml)
        self.assertNotIn('Tag Name="Area_1"', xml)
        self.assertNotRegex(xml, r'Program Name="Area_1')
        # Model name drove generation — AutogenInput mirrors workbook main_area.
        rows = propagate_area_to_workbook_rows(model.equipment, area_name)
        inp = AutogenInput(
            project_name="Synthetic_Shipping_CTRL",
            areas=[area_name],
            conveyors=[
                ConveyorRow(
                    number=1,
                    conveyor="P501",
                    main_area=rows[0]["main_area"],
                    type="Transport with MS",
                )
            ],
        )
        self.assertEqual(inp.conveyors[0].main_area, "Shipping_Area")
        self.assertEqual(snippet["area_name"], inp.conveyors[0].main_area)


class TestSiteModelV2Helpers(unittest.TestCase):
    def test_make_relationship_compat_keys(self):
        rel = make_relationship(
            source="M1",
            target="P1",
            kind="motor_link",
            provenance=PROV_RUN_EXPLICIT,
            confidence="HIGH",
        )
        self.assertEqual(rel["source"], "M1")
        self.assertEqual(rel["target"], "P1")
        self.assertEqual(rel["from"], "M1")
        self.assertEqual(rel["to"], "P1")
        self.assertEqual(rel["kind"], "motor_link")

    def test_counts_include_v2_buckets(self):
        model = SiteModel(machine_scope="X", run_dir="y")
        c = model.counts()
        for key in (
            "io_points",
            "drives",
            "motor_chains",
            "transport_paths",
            "merges",
            "scanners",
            "communications",
            "tracking",
            "decision_traces",
            "superseded_candidates",
        ):
            self.assertIn(key, c)
        d = model.to_dict()
        self.assertEqual(d.get("schema_version"), "2.0")


if __name__ == "__main__":
    unittest.main()

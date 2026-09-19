#!/usr/bin/env python3
"""GUI and Qualification must share the same workbook → AutogenInput overlay."""
from __future__ import annotations

# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys

_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
ROOT = _SF_REPO
# --- end bootstrap ---

import unittest
from pathlib import Path

from fortna_autogen import AutogenInput, ConveyorRow
from fortna_workbook import apply_workbook_to_input, build_effective_autogen_input


class TestWorkbookCompilerHandoff(unittest.TestCase):
    def test_sorter_build_and_include_programs_overlay(self) -> None:
        inp = AutogenInput(
            project_name="T",
            machine="ORINDYAC6",
            conveyors=[
                ConveyorRow(
                    number=1,
                    conveyor="P610",
                    main_area="ORINDYAC6_Area",
                    safety_zone="",
                    type="Transport with MS",
                )
            ],
            areas=["ORINDYAC6_Area"],
        )
        wb = {
            "conveyors": [
                {
                    "conveyor": "P610",
                    "main_area": "ShippingSorter",
                    "safety_zone": "Zone_Area1_ESZone1",
                    "include": True,
                }
            ],
            "sorter_build": {
                "appliedAt": "2026-09-19T12:00:00Z",
                "sorter_area_name": "ShippingSorter",
                "shipping_sorter_supported": True,
                "divert_count": 24,
                "divert_host_conveyor": "P610",
                "tracking": [{"conveyor": "P610", "encoder_tag": "ENC610", "has_encoder": "yes"}],
            },
            "merges_2to1": [
                {"name": "P600", "discharge": "P600", "lane_a": "P542", "lane_b": "P644"}
            ],
            "safety_build": {
                "appliedAt": "t",
                "zones": [
                    {
                        "source_id": "Zone_Area1_ESZone1",
                        "name": "Zone_Area1_ESZone1",
                        "members": ["ES1"],
                    }
                ],
            },
        }
        out = apply_workbook_to_input(inp, wb)
        self.assertTrue(out.sorter_build)
        self.assertEqual(out.sorter_build.get("divert_host_conveyor"), "P610")
        self.assertIn("Sorter_Track", out.include_programs)
        self.assertIn("ShippingSorter_Area_L3", out.include_programs)
        self.assertEqual(len(out.merges_2to1), 1)
        self.assertEqual(out.conveyors[0].main_area, "ShippingSorter")

    def test_does_not_invent_default_eszone_on_stub(self) -> None:
        inp = AutogenInput(project_name="T", machine="M", conveyors=[], areas=[])
        wb = {
            "conveyors": [
                {
                    "conveyor": "P999",
                    "main_area": "ShippingSorter",
                    "safety_zone": "Default_Area_ESZone1",
                    "include": True,
                    "type": "Transport with MS",
                }
            ]
        }
        out = apply_workbook_to_input(inp, wb)
        self.assertEqual(out.conveyors[0].safety_zone, "")


@unittest.skipUnless(
    (ROOT / "workspace" / "_virgin_orindy" / "RUN" / "project.cfg").is_file(),
    "virgin RUN missing",
)
class TestEffectiveHandoffLive(unittest.TestCase):
    def test_build_effective_loads_run(self) -> None:
        inp = build_effective_autogen_input(
            ROOT / "workspace" / "_virgin_orindy" / "RUN",
            {
                "sorter_build": {
                    "appliedAt": "t",
                    "divert_count": 2,
                    "sorter_area_name": "ShippingSorter",
                    "shipping_sorter_supported": True,
                }
            },
            machine="ORINDYAC6",
        )
        self.assertEqual(inp.machine, "ORINDYAC6")
        self.assertIn("Sorter_Track", inp.include_programs)


if __name__ == "__main__":
    unittest.main(verbosity=2)

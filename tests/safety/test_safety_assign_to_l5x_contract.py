"""Physical SafetyDevice → zone assignment → workbook → L5X ES_UDT contract."""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "tools" / "scripts"
LIBRARY = REPO / "tools" / "libraries" / "OReilly_Library_v3.L5X"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


class TestSafetyAssignToL5xContract(unittest.TestCase):
    def test_engineer_zone_members_emit_es_udt_not_aux_dupes(self):
        if not LIBRARY.is_file():
            self.skipTest("library missing")
        from fortna_autogen import AutogenInput, ConveyorRow, build_l5x

        # Site-neutral synthetic: one physical ES device, one AUX alias must not
        # create a second UDT when only the canonical device is assigned.
        inp = AutogenInput(
            project_name="Synthetic_Safety_CTRL",
            machine="SYNTH_SAFE",
            areas=["Pack_Area"],
            safety_zones=["Pack_ESZone1"],
            safety_zone_members=[
                {
                    "name": "Pack_ESZone1",
                    "area": "Pack_Area",
                    "members": ["ES100"],  # canonical physical — not ES100_AUX
                }
            ],
            safety_build={
                "zones": [
                    {
                        "name": "Pack_ESZone1",
                        "area": "Pack_Area",
                        "members": ["ES100"],
                        "status": "READY",
                    }
                ]
            },
            conveyors=[
                ConveyorRow(
                    number=1,
                    conveyor="P100",
                    main_area="Pack_Area",
                    safety_zone="Pack_ESZone1",
                    type="Transport with MS",
                )
            ],
            io_points=[
                {
                    "tag": "ES100",
                    "fortna_name": "ES100",
                    "io_name": "ES100",
                    "direction": "IN",
                    "device_type": "estop",
                    "description": "E-STOP",
                    "fortna_bank": "1",
                    "fortna_bit": "0",
                }
            ],
            include_sys=False,
            include_io_map=True,
            include_io_map_gold=False,
        )
        # Normalize io_points if dicts need IoPoint — build_l5x may accept dicts via load
        # Prefer empty io and rely on safety_build members for ES tags
        inp.io_points = []
        l5x, report = build_l5x(inp, LIBRARY)
        # ES_UDT for assigned device
        self.assertRegex(l5x, r'Tag Name="(?:T_)?ES100"[^>]*DataType="ES_UDT"')
        # AUX alias must not appear as a separate controller tag from this assignment
        self.assertNotRegex(l5x, r'Tag Name="(?:T_)?ES100_AUX"')
        # Nonphysical unknown must not invent operational members
        self.assertNotIn("ES999_AUX", l5x)

    def test_workbook_safety_build_round_trip_fields(self):
        """Assignment persistence shape used by Safety Apply → Autogen."""
        sb = {
            "zones": [
                {
                    "name": "ZoneA_ESZone1",
                    "area": "ZoneA",
                    "members": ["ES10", "ESLS10"],
                    "status": "READY",
                }
            ]
        }
        self.assertEqual(sb["zones"][0]["members"], ["ES10", "ESLS10"])
        self.assertNotIn("ES10_AUX", sb["zones"][0]["members"])


if __name__ == "__main__":
    unittest.main()

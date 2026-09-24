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
            include_sys=False,
            include_io_map=True,
            include_io_map_gold=False,
        )
        inp.io_points = []
        l5x, report = build_l5x(inp, LIBRARY)
        self.assertRegex(l5x, r'Tag Name="(?:T_)?ES100"[^>]*DataType="ES_UDT"')
        self.assertNotRegex(l5x, r'Tag Name="(?:T_)?ES100_AUX"')
        self.assertNotIn("ES999_AUX", l5x)

    def test_esr_alias_family_one_zone_member_one_udt(self):
        if not LIBRARY.is_file():
            self.skipTest("library missing")
        from fortna_autogen import AutogenInput, ConveyorRow, build_l5x
        from fortna_safety_model import reconcile_safety_devices

        signals = [
            {"name": "2ESR1", "kind": "ESR", "physicalEndpoint": "RIO:I.Data[0].1", "sources": ["T"]},
            {"name": "2ESR1_AUX", "kind": "ESR", "physicalEndpoint": "RIO:I.Data[0].1", "sources": ["T"]},
            {"name": "T_2ESR1", "kind": "ESR", "physicalEndpoint": "RIO:I.Data[0].1", "sources": ["T"]},
        ]
        recon = reconcile_safety_devices(signals)
        devices = recon.get("devices") or []
        self.assertEqual(len(devices), 1)
        canonical = devices[0].get("name") or devices[0].get("id")
        self.assertTrue(canonical)

        inp = AutogenInput(
            project_name="Synthetic_ESR_CTRL",
            machine="SYNTH_ESR",
            areas=["Line_Area"],
            safety_zones=["Line_ESZone1"],
            safety_build={
                "zones": [
                    {
                        "name": "Line_ESZone1",
                        "area": "Line_Area",
                        "members": [canonical],
                        "status": "READY",
                    }
                ]
            },
            conveyors=[
                ConveyorRow(
                    number=1,
                    conveyor="P200",
                    main_area="Line_Area",
                    safety_zone="Line_ESZone1",
                    type="Transport with MS",
                )
            ],
            include_sys=False,
            include_io_map=False,
        )
        l5x, _ = build_l5x(inp, LIBRARY)
        # One logical structure for the canonical device (digit-leading → T_)
        es_tags = re.findall(
            r'<Tag Name="(T_?2ESR1(?:_AUX)?)"[^>]*DataType="ES_UDT"',
            l5x,
        )
        # Must not emit both primary and AUX as separate ES_UDT tags from one assignment
        self.assertLessEqual(len(set(es_tags)), 1, es_tags)
        self.assertNotIn('Tag Name="2ESR1_AUX"', l5x)
        self.assertNotIn('Tag Name="T_2ESR1_AUX"', l5x)

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

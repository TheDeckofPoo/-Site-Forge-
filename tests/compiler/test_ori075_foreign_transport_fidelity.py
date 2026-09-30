#!/usr/bin/env python3
"""ORI-075 CURRENT-RUN fidelity — foreign transport retained as evidence, not Pick.

Synthetic multi-controller plant ASC (no MSC Reno name hardcodes as the rule):
  SITEAPICK  = active controller under test
  SITEAPACK  = foreign Pack transport owner
  SITEASHIP  = foreign Ship transport owner

Covers:
  - RAW_EVIDENCE_ROW / LOCAL_ACTIVE / FOREIGN / UNKNOWN_OWNER / TEMPLATE_GRAPHICAL_ONLY
  - Foreign Pack/Ship rows retained (not deleted) with include=False
  - Foreign rows do NOT enter Pick Area / program plan / generation membership
  - HMI TITLE/IMAGE is graphical-only, not active equipment
  - Transport Apply restore must not park foreign evidence into Pick default Area
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_asc import write_asc  # noqa: E402
from fortna_run_equipment_fidelity import (  # noqa: E402
    FOREIGN_EQUIPMENT,
    LOCAL_ACTIVE_EQUIPMENT,
    TEMPLATE_GRAPHICAL_ONLY,
    UNKNOWN_OWNER,
    annotate_workbook_conveyors,
    classify_run_equipment_fidelity,
    may_generate,
)
from fortna_transport_graph import apply_graph_to_workbook  # noqa: E402

CONV_HEADERS = [
    "IO_Name",
    "General_Description",
    "IO_Address_Word",
    "IO_Address_Bit",
    "Device_Description",
    "Part_Number",
    "IO_Module_Type",
    "Type",
    "Machine_Name",
    "Motor",
    "Drive",
    "X_cord",
    "Y_cord",
    "Length",
    "Angle",
    "Width",
]

MERGE_HEADERS = [
    "Name",
    "Process",
    "Owner",
    "CurrInput",
    "NumInputs",
    "OperableInput",
    "Valid",
    "SwitchDelayTimer",
    "SwitchDelayTimerPreset",
    "IsSwitchDelay",
    "pStatus",
]


def _conv(
    name: str,
    *,
    typ: str = "STRAIGHT",
    machine: str = "N/A",
    motor: str = " ",
) -> dict[str, str]:
    return {
        "IO_Name": name,
        "General_Description": name,
        "IO_Address_Word": "0",
        "IO_Address_Bit": "0",
        "Device_Description": "N/A",
        "Part_Number": "N/A",
        "IO_Module_Type": "N/A",
        "Type": typ,
        "Machine_Name": machine,
        "Motor": motor,
        "Drive": " ",
        "X_cord": "0.000",
        "Y_cord": "0.000",
        "Length": "10.000",
        "Angle": "0",
        "Width": "30.000",
    }


def _write_synthetic_run(root: Path) -> Path:
    run = root / "RUN"
    fortna = run / "FORTNA"
    project = run / "PROJECT"
    fortna.mkdir(parents=True)
    project.mkdir(parents=True)
    (run / "project.cfg").write_text(
        "\n".join(
            [
                "[DATA_CONFIG]",
                "FORTNADIR  = ./FORTNA",
                "PROJECTDIR = ./PROJECT",
                "MACHINENAME = SITEAPICK",
                "PROJECTNAME = SITEA",
                "",
            ]
        ),
        encoding="utf-8",
    )
    rows = [
        # Local active — explicit Pick ownership
        _conv("P10", typ="STRAIGHT", machine="SITEAPICK", motor="M10"),
        _conv("M10", typ="MOTOR", machine="SITEAPICK"),
        # Local active via device linkage (conveyor N/A, motor owned by Pick)
        _conv("P11", typ="ZEROPRESSURE", machine="N/A"),
        _conv("M11", typ="MOTOR", machine="SITEAPICK"),
        # Foreign Pack / Ship transport
        _conv("P20", typ="STRAIGHT", machine="SITEAPACK"),
        _conv("P21", typ="BELT", machine="SITEAPACK"),
        _conv("P30", typ="CURVE", machine="SITEASHIP"),
        # HMI graphical only
        _conv("LANE1", typ="TITLE", machine="N/A"),
        _conv("LOGO", typ="IMAGE", machine="N/A"),
        # Unknown owner mechanical (no Machine_Name, no linked local device)
        _conv("P99", typ="STRAIGHT", machine="N/A"),
        # MergeBoss-linked local (Name encodes P12; Owner=SITEAPICK)
        _conv("P12", typ="STRAIGHT", machine="N/A"),
    ]
    write_asc(fortna / "Conveyor.asc", CONV_HEADERS, rows)
    write_asc(
        fortna / "MergeBoss.asc.SITEAPICK",
        MERGE_HEADERS,
        [
            {
                "Name": "P10-P12",
                "Process": "CTRL",
                "Owner": "SITEAPICK",
                "CurrInput": "2",
                "NumInputs": "2",
                "OperableInput": "M10_AUX",
                "Valid": "Y",
                "SwitchDelayTimer": "N/A",
                "SwitchDelayTimerPreset": "0.000",
                "IsSwitchDelay": "0",
                "pStatus": "Init Okay",
            }
        ],
    )
    return run


class TestOri075FidelityClasses(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory(prefix="ori075_")
        self.run_dir = _write_synthetic_run(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_classes_distinguish_foreign_graphical_local(self) -> None:
        payload = classify_run_equipment_fidelity(self.run_dir, "SITEAPICK")
        by = {r["identity"].upper(): r for r in payload["rows"]}

        self.assertEqual(by["P10"]["fidelity_class"], LOCAL_ACTIVE_EQUIPMENT)
        self.assertTrue(may_generate(by["P10"]["fidelity_class"]))

        self.assertEqual(by["P11"]["fidelity_class"], LOCAL_ACTIVE_EQUIPMENT)
        self.assertEqual(by["P12"]["fidelity_class"], LOCAL_ACTIVE_EQUIPMENT)

        self.assertEqual(by["P20"]["fidelity_class"], FOREIGN_EQUIPMENT)
        self.assertEqual(by["P21"]["fidelity_class"], FOREIGN_EQUIPMENT)
        self.assertEqual(by["P30"]["fidelity_class"], FOREIGN_EQUIPMENT)
        self.assertFalse(may_generate(by["P20"]["fidelity_class"]))

        self.assertEqual(by["LANE1"]["fidelity_class"], TEMPLATE_GRAPHICAL_ONLY)
        self.assertEqual(by["LOGO"]["fidelity_class"], TEMPLATE_GRAPHICAL_ONLY)
        self.assertFalse(may_generate(by["LANE1"]["fidelity_class"]))

        self.assertEqual(by["P99"]["fidelity_class"], UNKNOWN_OWNER)
        self.assertFalse(may_generate(by["P99"]["fidelity_class"]))

        # Raw rows retained — foreign not deleted to clean counts
        self.assertGreaterEqual(payload["counts"][FOREIGN_EQUIPMENT], 3)
        self.assertGreaterEqual(payload["counts"][TEMPLATE_GRAPHICAL_ONLY], 2)
        self.assertGreaterEqual(payload["counts_total_retained"], 8)

    def test_equipment_plan_retains_foreign_evidence(self) -> None:
        from fortna_equipment_plan import inventory_and_plan

        out = inventory_and_plan(self.run_dir, machine_name="SITEAPICK")
        fid = out.get("equipment_fidelity") or {}
        foreign = set(fid.get("foreign_tags") or [])
        self.assertIn("P20", foreign)
        self.assertIn("P30", foreign)
        # Local plan must not treat Pack/Ship as Pick conveyors
        inv_convs = {str(x).upper() for x in (out.get("inventory") or {}).get("conveyors") or []}
        self.assertNotIn("P20", inv_convs)
        self.assertNotIn("P30", inv_convs)

    def test_transport_restore_keeps_foreign_out_of_pick_area(self) -> None:
        """Cleared Transport Apply must not park Pack/Ship into Pick default Area."""
        wb = {
            "machine": "SITEAPICK",
            "project_name": "SITEA_SITEAPICK",
            "run_dir": str(self.run_dir),
            "conveyors": [
                {
                    "conveyor": "P10",
                    "main_area": "Pick_Area",
                    "safety_zone": "Pick_ESZone1",
                    "source": "run",
                    "include": True,
                    "transport_build": True,
                },
                {
                    "conveyor": "P20",
                    "main_area": "Pick_Area",  # wrongly parked — must be demoted
                    "safety_zone": "Pick_ESZone1",
                    "source": "run",
                    "include": True,
                    "Machine_Name": "SITEAPACK",
                    "transport_build": True,
                },
                {
                    "conveyor": "LANE1",
                    "main_area": "Pick_Area",
                    "safety_zone": "Pick_ESZone1",
                    "source": "run",
                    "include": True,
                    "type": "TITLE",
                    "asc_type": "TITLE",
                    "transport_build": True,
                },
            ],
            "areas": [
                {"name": "Pick_Area", "safety_zone": "Pick_ESZone1", "conveyor_count": 3}
            ],
            "options": {"areas": ["Pick_Area"]},
            "merges_2to1": [],
        }
        # Empty graph areas with no bound tags → restore unbound transport rows
        graph = {
            "version": 1,
            "applyMode": "canonical",
            "areas": [
                {
                    "id": "a1",
                    "name": "Engineer_Area",
                    "nodes": [],
                    "wires": [],
                }
            ],
        }
        result = apply_graph_to_workbook(graph, wb)
        wb = result.get("workbook") or wb

        by = {
            str(r.get("conveyor") or "").upper(): r for r in (wb.get("conveyors") or [])
        }
        # Local RUN row may restore to site default and remain includable
        self.assertIn("P10", by)
        self.assertNotEqual(by["P10"].get("include"), False)

        # Foreign Pack retained as evidence — not Pick Area generation member
        self.assertIn("P20", by)
        self.assertEqual(by["P20"].get("fidelity_class"), FOREIGN_EQUIPMENT)
        self.assertFalse(
            by["P20"].get("include") not in (False, 0, "0", "false", "False")
        )
        self.assertEqual(by["P20"].get("generation_membership"), "EXCLUDED")
        self.assertEqual(str(by["P20"].get("main_area") or ""), "")

        # Graphical TITLE retained, not generated into Pick
        self.assertIn("LANE1", by)
        self.assertEqual(by["LANE1"].get("fidelity_class"), TEMPLATE_GRAPHICAL_ONLY)
        self.assertEqual(by["LANE1"].get("include"), False)
        self.assertEqual(str(by["LANE1"].get("main_area") or ""), "")

    def test_annotate_demotes_foreign_without_deleting(self) -> None:
        wb = {
            "machine": "SITEAPICK",
            "run_dir": str(self.run_dir),
            "conveyors": [
                {"conveyor": "P10", "include": True, "main_area": "Pick_Area"},
                {
                    "conveyor": "P20",
                    "include": True,
                    "main_area": "Pick_Area",
                    "Machine_Name": "SITEAPACK",
                },
            ],
        }
        annotate_workbook_conveyors(wb, run_dir=self.run_dir, machine="SITEAPICK")
        tags = [r["conveyor"] for r in wb["conveyors"]]
        self.assertEqual(len(tags), 2)  # not deleted
        foreign = next(r for r in wb["conveyors"] if r["conveyor"] == "P20")
        self.assertEqual(foreign["include"], False)
        self.assertEqual(foreign["fidelity_class"], FOREIGN_EQUIPMENT)


if __name__ == "__main__":
    unittest.main(verbosity=2)

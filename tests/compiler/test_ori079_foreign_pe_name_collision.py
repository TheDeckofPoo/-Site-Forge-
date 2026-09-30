#!/usr/bin/env python3
"""ORI-079: PE digit similarity must never promote foreign conveyors.

Synthetic plant (no site hardcodes as the rule):
  SITEPICK owns EZPE30_F (Machine_Name=SITEPICK)
  Fullline maps EZPE30_F → P38 (Pick conveyor)
  P30 exists as foreign Ship geometry (Machine_Name=N/A, no local proof)

Digit invention would wrongly mark P30 LOCAL; topology must mark P38 instead.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_asc import write_asc  # noqa: E402
from fortna_run_equipment_fidelity import (  # noqa: E402
    FOREIGN_EQUIPMENT,
    LOCAL_ACTIVE_EQUIPMENT,
    classify_run_equipment_fidelity,
    may_generate,
)

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

FULLLINE_HEADERS = [
    "Desc",
    "Sensor_Name",
    "Timer_Name",
    "Timer_Preset",
    "Clr_Timer_Name",
    "Clr_Timer_Preset",
    "Error_Name",
    "Conveyor_Name",
    "DontFireResponse",
    "Response IO",
    "Invert",
    "Go Until",
    "ReSound Horn",
    "NoGap",
    "Status",
    "Sent",
    "FullClearOutput",
    "FullClearACTION",
    "FullClearBIT",
]


def _conv(name: str, *, typ: str = "STRAIGHT", machine: str = "N/A") -> dict[str, str]:
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
        "Motor": " ",
        "Drive": " ",
        "X_cord": "0.000",
        "Y_cord": "0.000",
        "Length": "10.000",
        "Angle": "0",
        "Width": "30.000",
    }


def _fullline(sensor: str, conveyor: str) -> dict[str, str]:
    return {
        "Desc": sensor,
        "Sensor_Name": sensor,
        "Timer_Name": f"tm{sensor}",
        "Timer_Preset": "3.000",
        "Clr_Timer_Name": f"tmfc{sensor}",
        "Clr_Timer_Preset": "6.000",
        "Error_Name": sensor,
        "Conveyor_Name": conveyor,
        "DontFireResponse": "N",
        "Response IO": "INVALID",
        "Invert": "N",
        "Go Until": "INVALID",
        "ReSound Horn": "N/A",
        "NoGap": "N",
        "Status": "N",
        "Sent": "N",
        "FullClearOutput": "INVALID",
        "FullClearACTION": "N/A",
        "FullClearBIT": "0",
    }


class TestOri079ForeignPeNameCollision(unittest.TestCase):
    def test_matching_pe_number_foreign_ownership_not_generated(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run = Path(td) / "RUN"
            fortna = run / "FORTNA"
            fortna.mkdir(parents=True)
            (run / "project.cfg").write_text("Machine=SITEPICK\n", encoding="utf-8")
            write_asc(
                fortna / "Conveyor.asc",
                CONV_HEADERS,
                [
                    _conv("P30", typ="CURVE"),  # foreign Ship geometry, N/A owner
                    _conv("P38", typ="STRAIGHT"),  # true Fullline owner
                    _conv("P61", typ="STRAIGHT", machine="SITEPACK"),  # explicit foreign
                    _conv("EZPE30_F", typ="PHOTOEYE", machine="SITEPICK"),
                    _conv("EZPE61_F", typ="PHOTOEYE", machine="SITEPICK"),
                    _conv("TITLE1", typ="TITLE"),
                ],
            )
            write_asc(
                fortna / "Fullline.asc",
                FULLLINE_HEADERS,
                [
                    _fullline("EZPE30_F", "P38"),
                    _fullline("EZPE61_F", "P119"),  # PE61 serves P119, not P61
                ],
            )
            # Minimal MergeBoss so loader does not fail soft paths
            write_asc(
                fortna / "MergeBoss.asc",
                ["Name", "Owner", "NumInputs"],
                [],
            )

            model = classify_run_equipment_fidelity(run, "SITEPICK")
            by_id = {r["identity"]: r for r in model["rows"] if r.get("identity")}

            self.assertEqual(by_id["P38"]["fidelity_class"], LOCAL_ACTIVE_EQUIPMENT)
            self.assertTrue(may_generate(by_id["P38"]["fidelity_class"]))
            # Digit collision P30 must NOT become local/generate-eligible
            self.assertNotEqual(by_id["P30"]["fidelity_class"], LOCAL_ACTIVE_EQUIPMENT)
            self.assertFalse(may_generate(by_id["P30"]["fidelity_class"]))
            # Explicit foreign stays foreign even if a local PE shares digits
            self.assertEqual(by_id["P61"]["fidelity_class"], FOREIGN_EQUIPMENT)
            self.assertFalse(may_generate(by_id["P61"]["fidelity_class"]))


if __name__ == "__main__":
    unittest.main()

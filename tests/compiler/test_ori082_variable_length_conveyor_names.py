#!/usr/bin/env python3
"""ORI-082: conveyor / motor / PE identities are not fixed digit-width."""
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
    LOCAL_ACTIVE_EQUIPMENT,
    P_TAG_RE,
    _p_from_device,
    classify_run_equipment_fidelity,
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


def _row(name: str, *, typ: str = "STRAIGHT", machine: str = "N/A") -> dict[str, str]:
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


class TestOri082VariableLengthNames(unittest.TestCase):
    def test_p_tag_regex_accepts_1_to_4_digits(self) -> None:
        for name in ("P1", "P12", "P123", "P1001", "P1A", "P105A"):
            self.assertTrue(P_TAG_RE.match(name), name)
        self.assertFalse(P_TAG_RE.match("PX"))
        self.assertFalse(P_TAG_RE.match("P12345"))  # 5 digits out of policy

    def test_motor_device_to_p_one_digit(self) -> None:
        self.assertEqual(_p_from_device("M1"), "P1")
        self.assertEqual(_p_from_device("M12"), "P12")
        self.assertEqual(_p_from_device("M1001"), "P1001")

    def test_short_motors_promote_matching_conveyors(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run = Path(td) / "RUN"
            fortna = run / "FORTNA"
            fortna.mkdir(parents=True)
            (run / "project.cfg").write_text("Machine=SITEPICK\n", encoding="utf-8")
            write_asc(
                fortna / "Conveyor.asc",
                CONV_HEADERS,
                [
                    _row("P1", typ="ZEROPRESSURE"),
                    _row("P12", typ="STRAIGHT"),
                    _row("P123", typ="STRAIGHT"),
                    _row("P1001", typ="STRAIGHT"),
                    _row("M1", typ="MOTOR", machine="SITEPICK"),
                    _row("M12", typ="MOTOR", machine="SITEPICK"),
                    _row("M123", typ="MOTOR", machine="SITEPICK"),
                    _row("M1001", typ="MOTOR", machine="SITEPICK"),
                ],
            )
            write_asc(fortna / "Fullline.asc", ["Sensor_Name", "Conveyor_Name"], [])
            write_asc(fortna / "MergeBoss.asc", ["Name", "Owner"], [])
            model = classify_run_equipment_fidelity(run, "SITEPICK")
            by = {r["identity"]: r["fidelity_class"] for r in model["rows"]}
            for tag in ("P1", "P12", "P123", "P1001"):
                self.assertEqual(by[tag], LOCAL_ACTIVE_EQUIPMENT, tag)


if __name__ == "__main__":
    unittest.main()

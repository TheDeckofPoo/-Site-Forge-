"""Equipment-aware I/O V1 — motor / power / air binding (raw names immutable)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "tools" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fortna_equipment_binding import (  # noqa: E402
    CLASS_AIR_PRESSURE,
    CLASS_MOTOR_STARTER,
    CLASS_POWER_SUPPLY,
    UDT_AIR,
    UDT_MOTOR_STARTER,
    UDT_PS,
    build_equipment_bindings,
    build_motor_starter_devices,
    choose_motor_logix_tag,
    classify_power_or_air,
    parse_motor_starter_name,
)


class TestMotorCanonicalization(unittest.TestCase):
    def test_m77_to_p77(self):
        p = parse_motor_starter_name("M77")
        assert p is not None
        self.assertEqual(p["canonical_id"], "P77")
        self.assertEqual(p["role"], "RUN_COMMAND")

    def test_m77_aux_same_stem(self):
        p = parse_motor_starter_name("M77_AUX")
        assert p is not None
        self.assertEqual(p["canonical_id"], "P77")
        self.assertEqual(p["role"], "AUXILIARY_FORWARD")

    def test_m7a_lettered(self):
        p = parse_motor_starter_name("M7A")
        assert p is not None
        self.assertEqual(p["canonical_id"], "P7A")
        p2 = parse_motor_starter_name("M7A_AUX")
        assert p2 is not None
        self.assertEqual(p2["canonical_id"], "P7A")

    def test_mdr_not_transformed(self):
        self.assertIsNone(parse_motor_starter_name("MDR118"))
        self.assertIsNone(parse_motor_starter_name("MDR410A"))

    def test_vfd_not_transformed(self):
        self.assertIsNone(parse_motor_starter_name("VFD200"))
        self.assertIsNone(parse_motor_starter_name("VFD200_AUX"))

    def test_mtrans_not_transformed(self):
        self.assertIsNone(parse_motor_starter_name("MTRANS"))

    def test_aggregate_pair_and_driven_conveyor(self):
        rows = [
            {
                "IO_Name": "M77",
                "Type": "MOTOR",
                "General_Description": "D77 MOTOR STARTER FOR CONVEYOR MP106",
            },
            {
                "IO_Name": "M77_AUX",
                "Type": "MOTOR",
                "General_Description": "D77 MOTOR RUN INPUT FOR CONV MP106",
            },
            {"IO_Name": "MDR118", "Type": "MOTOR", "General_Description": "MDR"},
            {"IO_Name": "VFD200", "Type": "MOTOR", "General_Description": "VFD"},
        ]
        devices = build_motor_starter_devices(rows, machine="MSCRENOPACK")
        self.assertEqual(len(devices), 1)
        d = devices[0]
        self.assertEqual(d.canonical_id, "P77")
        self.assertEqual(d.logix_tag, "P77")
        self.assertEqual(d.equipment_class, CLASS_MOTOR_STARTER)
        self.assertEqual(d.datatype, UDT_MOTOR_STARTER)
        self.assertEqual(d.driven_conveyor, "MP106")
        self.assertNotEqual(d.driven_conveyor, "P77")
        self.assertEqual(d.member_path("RUN_COMMAND"), "P77.O.Run")
        self.assertEqual(d.member_path("AUXILIARY_FORWARD"), "P77.I.Auxiliary_Forward")
        self.assertEqual(d.signals["RUN_COMMAND"].raw_name, "M77")
        self.assertEqual(d.signals["AUXILIARY_FORWARD"].raw_name, "M77_AUX")
        self.assertEqual(d.confidence, "PROVEN")

    def test_collision_uses_ms_suffix(self):
        rows = [
            {"IO_Name": "M77", "Type": "MOTOR", "General_Description": "starter"},
            {"IO_Name": "M77_AUX", "Type": "MOTOR", "General_Description": "aux"},
            {"IO_Name": "P77", "Type": "STRAIGHT", "General_Description": "conveyor"},
        ]
        devices = build_motor_starter_devices(rows)
        self.assertEqual(devices[0].logix_tag, "P77_MS")
        self.assertEqual(devices[0].member_path("RUN_COMMAND"), "P77_MS.O.Run")

    def test_choose_logix_tag_helper(self):
        self.assertEqual(choose_motor_logix_tag("P77"), "P77")
        self.assertEqual(choose_motor_logix_tag("P77", reserved_bare_tags=["P77"]), "P77_MS")

    def test_unpaired_aux_review(self):
        rows = [
            {
                "IO_Name": "M100_AUX",
                "Type": "MOTOR",
                "General_Description": "AUX only",
            }
        ]
        devices = build_motor_starter_devices(rows)
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].confidence, "REVIEW_REQUIRED")
        self.assertIn("AUX", devices[0].review_reason)


class TestPowerAirClassification(unittest.TestCase):
    def test_pws_is_power_supply(self):
        info = classify_power_or_air("PWS112", "POWER SUPPLY ON P112 IS ON")
        assert info is not None
        self.assertEqual(info["equipment_class"], CLASS_POWER_SUPPLY)
        self.assertEqual(info["datatype"], UDT_PS)
        self.assertEqual(info["member"], "I.PS_OK")

    def test_ezpws_is_power_supply(self):
        info = classify_power_or_air("EZPWS53", "EZ POWER PEZ-53")
        assert info is not None
        self.assertEqual(info["equipment_class"], CLASS_POWER_SUPPLY)

    def test_ps208a_is_air_not_power(self):
        info = classify_power_or_air("PS208A", "AIR PRESSURE ON P208A IS ADEQUATE")
        assert info is not None
        self.assertEqual(info["equipment_class"], CLASS_AIR_PRESSURE)
        self.assertEqual(info["datatype"], UDT_AIR)
        self.assertEqual(info["member"], "I.Pressure_OK")

    def test_ambiguous_ps_review(self):
        info = classify_power_or_air("PS999", "SOME SENSOR")
        assert info is not None
        self.assertEqual(info["confidence"], "REVIEW_REQUIRED")


class TestBindingsIndex(unittest.TestCase):
    def test_by_raw_index(self):
        rows = [
            {
                "IO_Name": "M77",
                "Type": "MOTOR",
                "General_Description": "STARTER FOR CONVEYOR MP106",
            },
            {
                "IO_Name": "M77_AUX",
                "Type": "MOTOR",
                "General_Description": "RUN INPUT FOR CONV MP106",
            },
            {
                "IO_Name": "PWS112",
                "Type": "STRAIGHT",
                "General_Description": "POWER SUPPLY ON P112 IS ON",
            },
            {
                "IO_Name": "PS208A",
                "Type": "STRAIGHT",
                "General_Description": "AIR PRESSURE ON P208A IS ADEQUATE",
            },
        ]
        bundle = build_equipment_bindings(rows, machine="X")
        by = bundle["by_raw"]
        self.assertEqual(by["M77"]["member_path"], "P77.O.Run")
        self.assertEqual(by["M77_AUX"]["member_path"], "P77.I.Auxiliary_Forward")
        self.assertEqual(by["M77"]["driven_conveyor"], "MP106")
        self.assertEqual(by["PWS112"]["equipment_class"], CLASS_POWER_SUPPLY)
        self.assertEqual(by["PS208A"]["equipment_class"], CLASS_AIR_PRESSURE)
        self.assertEqual(bundle["counts"]["motor_starters"], 1)


if __name__ == "__main__":
    unittest.main()

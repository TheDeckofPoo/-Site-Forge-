"""Equipment-aware I/O V1 — motor / power / air / ES / PE binding (raw immutable)."""
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
    CLASS_CONVEYOR,
    CLASS_ESTOP,
    CLASS_MOTOR_STARTER,
    CLASS_PHOTOEYE,
    CLASS_POWER_SUPPLY,
    UDT_AIR,
    UDT_CONV,
    UDT_ES,
    UDT_MOTOR_STARTER,
    UDT_PE,
    UDT_PS,
    build_equipment_bindings,
    build_motor_related_devices,
    choose_motor_ms_tag,
    classify_estop,
    classify_photoeye,
    classify_power_or_air,
    parse_motor_starter_name,
)


class TestMotorCanonicalization(unittest.TestCase):
    def test_m77_parse(self):
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

    def test_mdr_vfd_not_transformed(self):
        self.assertIsNone(parse_motor_starter_name("MDR118"))
        self.assertIsNone(parse_motor_starter_name("VFD200"))
        self.assertIsNone(parse_motor_starter_name("MTRANS"))

    def test_ms_tag_always_suffix(self):
        self.assertEqual(choose_motor_ms_tag("P77"), "P77_MS")
        self.assertEqual(choose_motor_ms_tag("P77_MS"), "P77_MS")

    def test_aux_to_ms_udt_not_bare_p(self):
        rows = [
            {
                "IO_Name": "M124",
                "Type": "MOTOR",
                "General_Description": "STARTER FOR CONVEYOR P124",
            },
            {
                "IO_Name": "M124_AUX",
                "Type": "MOTOR",
                "General_Description": "RUN INPUT FOR CONV P124",
            },
            {"IO_Name": "P124", "Type": "STRAIGHT", "General_Description": "conv"},
        ]
        devices = build_motor_related_devices(rows, machine="X")
        ms = [d for d in devices if d.equipment_class == CLASS_MOTOR_STARTER]
        conv = [d for d in devices if d.equipment_class == CLASS_CONVEYOR]
        self.assertEqual(len(ms), 1)
        self.assertEqual(ms[0].logix_tag, "P124_MS")
        self.assertEqual(ms[0].datatype, UDT_MOTOR_STARTER)
        self.assertEqual(ms[0].member_path("AUXILIARY_FORWARD"), "P124_MS.I.Auxiliary_Forward")
        self.assertEqual(ms[0].signals["AUXILIARY_FORWARD"].raw_name, "M124_AUX")
        # Physical OUT → Conv_UDT.O.Run — NOT MS.O.Run
        self.assertEqual(len(conv), 1)
        self.assertEqual(conv[0].datatype, UDT_CONV)
        self.assertEqual(conv[0].logix_tag, "P124_Conv")
        self.assertEqual(conv[0].member_path("CONVEYOR_RUN"), "P124_Conv.O.Run")
        self.assertEqual(conv[0].signals["CONVEYOR_RUN"].raw_name, "M124")
        self.assertNotIn("O.Run", ms[0].member_path("AUXILIARY_FORWARD"))

    def test_motor_out_without_lineage_is_review(self):
        rows = [
            {
                "IO_Name": "M77",
                "Type": "MOTOR",
                "General_Description": "STARTER FOR CONVEYOR MP106",
            },
            {
                "IO_Name": "M77_AUX",
                "Type": "MOTOR",
                "General_Description": "AUX FOR MP106",
            },
        ]
        devices = build_motor_related_devices(rows)
        conv = [d for d in devices if d.equipment_class == CLASS_CONVEYOR][0]
        self.assertEqual(conv.confidence, "REVIEW_REQUIRED")
        self.assertIn("LINEAGE", conv.review_reason)
        ms = [d for d in devices if d.equipment_class == CLASS_MOTOR_STARTER][0]
        self.assertEqual(ms.logix_tag, "P77_MS")
        self.assertEqual(ms.driven_conveyor, "MP106")

    def test_unpaired_aux_review(self):
        rows = [{"IO_Name": "M100_AUX", "Type": "MOTOR", "General_Description": "AUX"}]
        devices = build_motor_related_devices(rows)
        ms = [d for d in devices if d.equipment_class == CLASS_MOTOR_STARTER]
        self.assertEqual(ms[0].confidence, "REVIEW_REQUIRED")


class TestPowerAirEsPe(unittest.TestCase):
    def test_pws_and_air(self):
        self.assertEqual(
            classify_power_or_air("PWS112", "POWER SUPPLY ON P112 IS ON")["datatype"],
            UDT_PS,
        )
        self.assertEqual(
            classify_power_or_air("PS208A", "AIR PRESSURE ON P208A IS ADEQUATE")[
                "equipment_class"
            ],
            CLASS_AIR_PRESSURE,
        )
        self.assertEqual(
            classify_power_or_air("PS999", "SOME SENSOR")["confidence"],
            "REVIEW_REQUIRED",
        )

    def test_es_input(self):
        info = classify_estop("ES406", direction="IN")
        assert info is not None
        self.assertEqual(info["datatype"], UDT_ES)
        self.assertEqual(info["member"], "I.ES_OK")

    def test_pe_input(self):
        info = classify_photoeye("EZPE136_P1", direction="IN", device_type="PHOTOCELL")
        assert info is not None
        self.assertEqual(info["datatype"], UDT_PE)
        self.assertEqual(info["member"], "I.PE_Clear")


class TestBindingsIndex(unittest.TestCase):
    def test_by_raw_motor_split(self):
        rows = [
            {
                "IO_Name": "M124",
                "Type": "MOTOR",
                "General_Description": "STARTER FOR CONVEYOR P124",
            },
            {
                "IO_Name": "M124_AUX",
                "Type": "MOTOR",
                "General_Description": "AUX P124",
            },
            {"IO_Name": "P124", "Type": "STRAIGHT"},
            {
                "IO_Name": "EZPWS136",
                "Type": "STRAIGHT",
                "General_Description": "POWER SUPPLY",
            },
            {
                "IO_Name": "PS312",
                "Type": "STRAIGHT",
                "General_Description": "AIR PRESSURE ADEQUATE",
            },
            {"IO_Name": "ES406", "Type": "BEACON", "General_Description": "E-STOP"},
            {"IO_Name": "PE126_JF", "Type": "PHOTOCELL"},
        ]
        bundle = build_equipment_bindings(rows, machine="X")
        by = bundle["by_raw"]
        self.assertEqual(by["M124_AUX"]["member_path"], "P124_MS.I.Auxiliary_Forward")
        self.assertEqual(by["M124_AUX"]["datatype"], UDT_MOTOR_STARTER)
        self.assertEqual(by["M124"]["member_path"], "P124_Conv.O.Run")
        self.assertEqual(by["M124"]["datatype"], UDT_CONV)
        self.assertEqual(by["EZPWS136"]["member_path"], "EZPWS136.I.PS_OK")
        self.assertEqual(by["PS312"]["datatype"], UDT_AIR)
        self.assertEqual(by["ES406"]["datatype"], UDT_ES)
        self.assertEqual(by["PE126_JF"]["member_path"], "PE126_JF.I.PE_Clear")
        # Never Motor_Starter.O.Run for physical out
        self.assertFalse(by["M124"]["member_path"].endswith("MS.O.Run"))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Operand fidelity — TIMER/AOI/module path families (Gate C/E)."""
from __future__ import annotations

import unittest

from fortna_operand_validator import validate_operand


class TestOperandFidelity(unittest.TestCase):
    def test_timer_dn_is_valid(self) -> None:
        res = validate_operand(
            "P504_AtSpeedExtraTimer.DN",
            tags={"P504_AtSpeedExtraTimer": "TIMER"},
            datatypes={},
        )
        self.assertTrue(res.get("ok"), msg=res)
        # .DN resolves to BOOL member of TIMER
        self.assertEqual(res.get("resolved_type"), "BOOL")
        self.assertEqual(res.get("datatype"), "TIMER")

    def test_timer_nested_in_udt(self) -> None:
        res = validate_operand(
            "Track_Group_SCN504.ResetTrkOffsets_UnlatchTmr.DN",
            tags={"Track_Group_SCN504": "Track_Group_UDT"},
            datatypes={
                "Track_Group_UDT": {"ResetTrkOffsets_UnlatchTmr": "TIMER", "ID": "DINT"},
            },
        )
        self.assertTrue(res.get("ok"), msg=res)

    def test_sealed_aoi_nested_accepted(self) -> None:
        res = validate_operand(
            "P506_Divert1_AOI.Divert_PackageDetect.O_Token_Found_Ack",
            tags={"P506_Divert1_AOI": "Track_Divert_AOI"},
            datatypes={
                "Track_Divert_AOI": {
                    "Divert_PackageDetect": "TRK_SearchToken_VirtualLocation",
                },
            },
            aoi_names={"TRK_SearchToken_VirtualLocation", "Track_Divert_AOI"},
        )
        self.assertTrue(res.get("ok"), msg=res)
        self.assertTrue(res.get("external"))

    def test_comm_udt_flt_commloss(self) -> None:
        res = validate_operand(
            "CP5RIO2_2.Flt.CommLoss",
            tags={"CP5RIO2_2": "Comm_UDT"},
            datatypes={
                "Comm_UDT": {"Flt": "Comm_Flt", "Comm_Code": "DINT"},
                "Comm_Flt": {"CommLoss": "BIT", "UpStrmCommLoss": "BIT"},
            },
        )
        self.assertTrue(res.get("ok"), msg=res)

    def test_missing_comm_tag_still_fails(self) -> None:
        res = validate_operand(
            "CP5RIO2_2.Flt.CommLoss",
            tags={},
            datatypes={},
        )
        self.assertFalse(res.get("ok"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

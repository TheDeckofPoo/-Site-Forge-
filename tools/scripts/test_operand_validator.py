#!/usr/bin/env python3
"""Gate I — operand member-path validator unit tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fortna_operand_validator import validate_l5x_operands, validate_operand  # noqa: E402


class TestOperandValidator(unittest.TestCase):
    def test_valid_nested_member(self) -> None:
        tags = {"P220A_MS": "Motor_Starter_UDT"}
        dts = {"Motor_Starter_UDT": {"I": "Motor_Starter_I", "O": "Motor_Starter_O"},
               "Motor_Starter_I": {"Auxiliary_Forward": "BOOL", "Auxiliary_Reverse": "BOOL"}}
        r = validate_operand("P220A_MS.I.Auxiliary_Forward", tags=tags, datatypes=dts)
        self.assertTrue(r["ok"], r)

    def test_invalid_member(self) -> None:
        tags = {"P220A_MS": "Motor_Starter_UDT"}
        dts = {"Motor_Starter_UDT": {"I": "Motor_Starter_I"},
               "Motor_Starter_I": {"Auxiliary_Forward": "BOOL"}}
        r = validate_operand("P220A_MS.I.BadMember", tags=tags, datatypes=dts)
        self.assertFalse(r["ok"])
        self.assertIn(r["kind"], ("MEMBER_NOT_FOUND", "NESTED_MEMBER_NOT_FOUND"))
        self.assertEqual(r.get("failed_segment") or r.get("failed_member_segment"), "BadMember")

    def test_tag_not_found(self) -> None:
        r = validate_operand("NoSuchTag.I.X", tags={}, datatypes={})
        self.assertFalse(r["ok"])
        self.assertEqual(r["kind"], "TAG_NOT_FOUND")

    def test_l5x_scan_finds_bad_member(self) -> None:
        l5x = """<?xml version="1.0"?>
<RSLogix5000Content>
  <Controller>
    <DataTypes>
      <DataType Name="Motor_Starter_UDT">
        <Members>
          <Member Name="I" DataType="Motor_Starter_I"/>
        </Members>
      </DataType>
      <DataType Name="Motor_Starter_I">
        <Members>
          <Member Name="Auxiliary_Forward" DataType="BOOL"/>
        </Members>
      </DataType>
    </DataTypes>
    <Tags>
      <Tag Name="P220A_MS" DataType="Motor_Starter_UDT"/>
    </Tags>
    <Programs>
      <Program Name="IO_MAP">
        <Routines>
          <Routine Name="CP_I" Type="RLL">
            <RLLContent>
              <Rung Number="6" Type="N">
                <Text><![CDATA[XIC(P220A_MS.I.Auxiliary_Forward)OTE(Dummy);]]></Text>
              </Rung>
              <Rung Number="46" Type="N">
                <Text><![CDATA[XIC(P220A_MS.I.BadMember)OTE(Dummy2);]]></Text>
              </Rung>
            </RLLContent>
          </Routine>
        </Routines>
      </Program>
    </Programs>
  </Controller>
</RSLogix5000Content>
"""
        rep = validate_l5x_operands(l5x)
        self.assertEqual(rep["operands_checked"], 4)  # 2 XIC + 2 OTE
        self.assertGreaterEqual(rep["invalid_count"], 1)
        kinds = {i.get("operand") for i in rep["invalid"]}
        self.assertTrue(any("BadMember" in (o or "") for o in kinds), rep["invalid"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

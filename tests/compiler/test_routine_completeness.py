#!/usr/bin/env python3
"""Routine completeness contract — placeholder vs complete vs missing."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SF_REPO / "tools" / "scripts"))

from fortna_routine_completeness import (  # noqa: E402
    STATUS_COMPLETE,
    STATUS_MISSING_EXPECTED,
    STATUS_PLACEHOLDER,
    analyze_routine_coverage,
)


def _l5x(programs: str) -> str:
    return f"""<?xml version="1.0"?>
<RSLogix5000Content>
<Controller Name="TESTSITE">
<Tags/>
<Programs>
{programs}
</Programs>
</Controller>
</RSLogix5000Content>
"""


class TestRoutineCompleteness(unittest.TestCase):
    def test_stacklight_placeholder(self) -> None:
        programs = """
<Program Name="TESTSITE_Area_Slow">
<Routines>
<Routine Name="Main_Routine" Type="RLL">
<RLLContent>
<Rung Number="0" Type="N"><Text><![CDATA[JSR(Area_Logic,0);]]></Text></Rung>
<Rung Number="6" Type="N"><Text><![CDATA[JSR(Stacklight,0);]]></Text></Rung>
</RLLContent>
</Routine>
<Routine Name="Area_Logic" Type="RLL">
<RLLContent>
<Rung Number="0" Type="N"><Text><![CDATA[XIC(AlwaysOn)OTE(Area.Run);]]></Text></Rung>
</RLLContent>
</Routine>
<Routine Name="Stacklight" Type="RLL">
<RLLContent>
<Rung Number="0" Type="N"><Text><![CDATA[NOP();]]></Text></Rung>
</RLLContent>
</Routine>
</Routines>
</Program>
"""
        cov = analyze_routine_coverage(_l5x(programs), report={})
        by = {(r.program, r.routine): r for r in cov.rows}
        self.assertEqual(by[("TESTSITE_Area_Slow", "Area_Logic")].status, STATUS_COMPLETE)
        self.assertEqual(by[("TESTSITE_Area_Slow", "Stacklight")].status, STATUS_PLACEHOLDER)
        self.assertTrue(any(i.get("ROUTINE") == "Stacklight" for i in cov.issues))

    def test_ori107_timing_routines_in_l2_not_missing_on_l1(self) -> None:
        """ORI-107: Conv_Speed/FullTime/PETime in Area_L2 must not be MISSING on L1."""
        programs = """
<Program Name="TESTSITE_Area_L1">
<Routines>
<Routine Name="Main_Routine" Type="RLL">
<RLLContent>
<Rung Number="0" Type="N"><Text><![CDATA[JSR(Area,0);]]></Text></Rung>
</RLLContent>
</Routine>
<Routine Name="Area" Type="RLL">
<RLLContent>
<Rung Number="0" Type="N"><Text><![CDATA[NOP();]]></Text></Rung>
</RLLContent>
</Routine>
</Routines>
</Program>
<Program Name="TESTSITE_Area_L2">
<Routines>
<Routine Name="Main_Routine" Type="RLL">
<RLLContent>
<Rung Number="0" Type="N"><Text><![CDATA[JSR(Conv_Speed,0);]]></Text></Rung>
<Rung Number="1" Type="N"><Text><![CDATA[JSR(FullTime,0);]]></Text></Rung>
<Rung Number="2" Type="N"><Text><![CDATA[JSR(PETime,0);]]></Text></Rung>
</RLLContent>
</Routine>
<Routine Name="Conv_Speed" Type="RLL">
<RLLContent>
<Rung Number="0" Type="N"><Text><![CDATA[XIC(AlwaysOn)OTE(Init.Done);]]></Text></Rung>
</RLLContent>
</Routine>
<Routine Name="FullTime" Type="RLL">
<RLLContent>
<Rung Number="0" Type="N"><Text><![CDATA[XIC(AlwaysOn)OTE(Init.Done);]]></Text></Rung>
</RLLContent>
</Routine>
<Routine Name="PETime" Type="RLL">
<RLLContent>
<Rung Number="0" Type="N"><Text><![CDATA[XIC(AlwaysOn)OTE(Init.Done);]]></Text></Rung>
</RLLContent>
</Routine>
</Routines>
</Program>
"""
        cov = analyze_routine_coverage(_l5x(programs), report={})
        by = {(r.program, r.routine): r for r in cov.rows}
        self.assertNotIn(("TESTSITE_Area_L1", "Conv_Speed"), by)
        self.assertNotIn(("TESTSITE_Area_L1", "FullTime"), by)
        self.assertNotIn(("TESTSITE_Area_L1", "PETime"), by)
        self.assertEqual(by[("TESTSITE_Area_L2", "Conv_Speed")].status, STATUS_COMPLETE)
        self.assertEqual(by[("TESTSITE_Area_L2", "FullTime")].status, STATUS_COMPLETE)
        self.assertEqual(by[("TESTSITE_Area_L2", "PETime")].status, STATUS_COMPLETE)
        missing = [
            i for i in cov.issues
            if i.get("ROUTINE") in {"Conv_Speed", "FullTime", "PETime"}
            and str(i.get("severity/classification") or i.get("status") or "").upper()
            == STATUS_MISSING_EXPECTED
        ]
        self.assertEqual(missing, [])

    def test_missing_expected_when_jsr_target_absent(self) -> None:
        programs = """
<Program Name="TESTSITE_Area_Slow">
<Routines>
<Routine Name="Main_Routine" Type="RLL">
<RLLContent>
<Rung Number="0" Type="N"><Text><![CDATA[JSR(Stacklight,0);]]></Text></Rung>
</RLLContent>
</Routine>
</Routines>
</Program>
"""
        cov = analyze_routine_coverage(_l5x(programs), report={})
        stack = next(r for r in cov.rows if r.routine == "Stacklight")
        self.assertEqual(stack.status, STATUS_MISSING_EXPECTED)
        self.assertFalse(stack.present)
        self.assertTrue(stack.scheduled)


if __name__ == "__main__":
    unittest.main()

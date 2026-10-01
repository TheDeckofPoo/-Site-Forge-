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

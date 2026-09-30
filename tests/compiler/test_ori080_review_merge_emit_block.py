#!/usr/bin/env python3
"""ORI-080: REVIEW_REQUIRED merges must not emit Merge_2to1 PLC logic.

Also: undeclared merge operands must fail symbol closure (no false PASS).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_plc2_merge_discovery import (  # noqa: E402
    CLASS_PROVEN,
    CLASS_REVIEW,
    discovery_to_autogen_merges_2to1,
)
from fortna_symbol_closure import check_symbol_closure  # noqa: E402


class TestOri080ReviewMergeEmitBlock(unittest.TestCase):
    def test_review_merge_may_generate_false(self) -> None:
        report = {
            "machine": "SITEPICK",
            "merges": [
                {
                    "name": "P2-P18",
                    "classification": CLASS_REVIEW,
                    "sourceClassification": "UNKNOWN",
                    "mainLane": "P2",
                    "inductLane": "P18",
                    "downstream": None,
                    "numInputs": 2,
                    "PEs": {"main": "EZPE53_P", "induct": "EZPE52_P", "jam": ""},
                    "evidence": [{"kind": "mergeboss", "owner": "SITEPICK"}],
                    "unresolved": ["downstream:missing_for_proven"],
                },
                {
                    "name": "P100-P200",
                    "classification": CLASS_PROVEN,
                    "sourceClassification": "MERGEROUTE",
                    "mainLane": "P100",
                    "inductLane": "P200",
                    "downstream": "P300",
                    "numInputs": 2,
                    "PEs": {"main": "PE100_P", "induct": "PE200_P", "jam": ""},
                    "evidence": [{"kind": "mergeboss", "owner": "SITEPICK"}],
                    "unresolved": [],
                },
            ],
        }
        rows = discovery_to_autogen_merges_2to1(report, include_review=True)
        by_name = {r["discovery_name"]: r for r in rows}
        self.assertIn("P2-P18", by_name)
        self.assertFalse(by_name["P2-P18"].get("may_generate"))
        self.assertEqual(by_name["P2-P18"].get("status"), "REVIEW_REQUIRED")
        self.assertTrue(by_name["P100-P200"].get("may_generate"))
        self.assertEqual(by_name["P100-P200"].get("discharge"), "P300")

    def test_undeclared_merge_tag_fails_symbol_closure(self) -> None:
        # Minimal L5X fragment: Conv_Merge references undeclared P2_Conv.
        l5x = """<?xml version="1.0" encoding="UTF-8"?>
<RSLogix5000Content>
<Controller Name="SITEPICK">
<Tags>
<Tag Name="P15_Conv" TagType="Base" DataType="P3000_Conv"/>
<Tag Name="AlwaysOn" TagType="Base" DataType="BOOL"/>
</Tags>
<Programs>
<Program Name="SITEPICK_Area_Fast">
<Tags/>
<Routines>
<Routine Name="Conv_Merge" Type="RLL">
<RLLContent>
<Rung Number="0" Type="N">
<Text><![CDATA[XIC(AlwaysOn)OTE(P2_Conv.O.Run);]]></Text>
</Rung>
</RLLContent>
</Routine>
</Routines>
</Program>
</Programs>
</Controller>
</RSLogix5000Content>
"""
        report = check_symbol_closure(l5x)
        self.assertFalse(report.ok)
        roots = {f.root.upper() for f in report.failures}
        self.assertIn("P2_CONV", roots)


if __name__ == "__main__":
    unittest.main()

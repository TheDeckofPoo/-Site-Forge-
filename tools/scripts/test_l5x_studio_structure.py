#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_l5x_studio_structure import (  # noqa: E402
    sanitize_l5x_studio_structure,
    validate_routine_language_containers,
    validate_l5x_studio_structure,
)
from fortna_sorter_build import _limit_wave_divert_rungs, _append_build_config_routine  # noqa: E402
from fortna_l5x_structured_data import emit_merge_2to1_tag  # noqa: E402


class TestRoutineContainers(unittest.TestCase):
    def test_detect_raw_rung(self) -> None:
        xml = '<Routine Name="Wave_Divert" Type="RLL"><Rung Number="0" Type="N"><Text><![CDATA[NOP();]]></Text></Rung></Routine>'
        errs = validate_routine_language_containers(xml)
        self.assertTrue(any(e["kind"] == "RLL_RUNG_OUTSIDE_RLLCONTENT" for e in errs))

    def test_wave_divert_rewrite_wraps_rllcontent(self) -> None:
        prog = (
            '<Routines><Routine Name="Wave_Divert" Type="RLL"><RLLContent>'
            '<Rung Number="0" Type="N"><Text><![CDATA[TRK_Divert_WaveFunction(P506_Divert1_Wave,x,y,z);]]></Text></Rung>'
            '<Rung Number="1" Type="N"><Text><![CDATA[TRK_Divert_WaveFunction(P506_Divert2_Wave,x,y,z);]]></Text></Rung>'
            "</RLLContent></Routine></Routines>"
        )
        out, kept, pack = _limit_wave_divert_rungs(prog, 2)
        self.assertIn("<RLLContent>", out)
        self.assertNotRegex(out, r'Type="RLL">\s*<Rung')
        self.assertEqual(kept, 2)

    def test_build_config_uses_stcontent(self) -> None:
        prog = '<Routines><Routine Name="Main" Type="RLL"><RLLContent></RLLContent></Routine></Routines>'
        out = _append_build_config_routine(prog, {"induct_conveyor": "P1", "divert_count": 1}, [])
        self.assertIn("<STContent>", out)
        self.assertNotIn("<STLines>", out)
        errs = validate_routine_language_containers(out)
        self.assertFalse(any(e["routine"] == "Build_Config" for e in errs))

    def test_build_config_st_line_has_no_nested_text(self) -> None:
        prog = '<Routines><Routine Name="Main" Type="RLL"><RLLContent></RLLContent></Routine></Routines>'
        out = _append_build_config_routine(prog, {"induct_conveyor": "P1", "divert_count": 1}, [])
        self.assertRegex(out, r'<Line Number="0"><!\[CDATA\[')
        self.assertNotRegex(out, r"<Line\b[^>]*>\s*<Text\b")
        errs = validate_routine_language_containers(out)
        self.assertFalse(any(e["kind"] == "ST_LINE_NESTED_TEXT" for e in errs))

    def test_validator_fails_on_st_line_nested_text(self) -> None:
        xml = (
            '<Routine Name="Build_Config" Type="ST"><STContent>'
            '<Line Number="0"><Text><![CDATA[// bad]]></Text></Line>'
            "</STContent></Routine>"
        )
        errs = validate_routine_language_containers(xml)
        self.assertTrue(any(e["kind"] == "ST_LINE_NESTED_TEXT" for e in errs))

    def test_sanitize_rewrites_st_line_nested_text(self) -> None:
        xml = (
            '<Routine Name="Build_Config" Type="ST"><STContent>'
            '<Line Number="0"><Text><![CDATA[// snap]]></Text></Line>'
            "</STContent></Routine>"
        )
        out = sanitize_l5x_studio_structure(xml)
        self.assertIn('<Line Number="0"><![CDATA[// snap]]></Line>', out)
        self.assertNotRegex(out, r"<Line\b[^>]*>\s*<Text\b")
        errs = validate_routine_language_containers(out)
        self.assertFalse(any(e["kind"] == "ST_LINE_NESTED_TEXT" for e in errs))

    def test_merge_2to1_has_full_decorated(self) -> None:
        tag = emit_merge_2to1_tag("P406_Merge")
        self.assertIn('Name="EnableIn"', tag)
        self.assertIn('Name="M_InductLane_In_Hold"', tag)
        self.assertGreater(tag.count("DataValueMember"), 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)

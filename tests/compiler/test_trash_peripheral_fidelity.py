"""Peripheral Area Fast/Slow scheduling invariants (site-free).

Generated-output regressions for:
  - Fast owns Conv_PE when PE_Logic exists (exactly one JSR + routine)
  - Slow must NOT schedule Conv_PE / PE_Logic (no dual-rate execution)
  - Fast Full/Merge JSR+routine at most once each
  - Fast_Conv jam PE must not become exit/add
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "tools" / "scripts"
LIBRARY = REPO / "tools" / "libraries" / "OReilly_Library_v3.L5X"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fortna_autogen import (  # noqa: E402
    AutogenInput,
    ConveyorRow,
    _conv_udt_type_code,
    _pe_wiring_for_conv,
    build_l5x,
    clone_template_for_conveyor,
)
from fortna_conveyor_section_model import classify_conv_type  # noqa: E402


def _program_xml(l5x: str, program_name: str) -> str:
    m = re.search(
        rf'<Program Name="{re.escape(program_name)}"[^>]*>(.*?)</Program>',
        l5x,
        re.S,
    )
    return m.group(1) if m else ""


def _routine_xml(program_body: str, routine_name: str) -> str:
    m = re.search(
        rf'<Routine Name="{re.escape(routine_name)}"[^>]*>(.*?)</Routine>',
        program_body,
        re.S,
    )
    return m.group(1) if m else ""


def _jsr_targets(main_routine_body: str) -> list[str]:
    return re.findall(r"JSR\(([^,)]+)", main_routine_body or "")


def _count(seq: list[str], name: str) -> int:
    return sum(1 for x in seq if x == name)


class TestFastConvPeRoles(unittest.TestCase):
    def test_jam_only_does_not_fill_fast_exit(self):
        rows = [
            {
                "fortna_name": "PE1006_J",
                "io_name": "PE1006_J",
                "description": "JAM PE FOR P1006",
            }
        ]
        w = _pe_wiring_for_conv(rows)
        self.assertEqual(w["exit_pe_tag"], "")
        self.assertEqual(w["add_pe_tag"], "")
        self.assertIn("PE1006_J", w["jam_pe_tags"])

    def test_product_pe_fills_fast_exit(self):
        rows = [
            {
                "fortna_name": "PE1008_P",
                "io_name": "PE1008_P",
                "description": "PRODUCT PE",
            },
            {
                "fortna_name": "PE1008_J",
                "io_name": "PE1008_J",
                "description": "JAM",
            },
        ]
        w = _pe_wiring_for_conv(rows)
        self.assertEqual(w["exit_pe_tag"], "PE1008_P")
        self.assertNotEqual(w["exit_pe_tag"], "PE1008_J")
        self.assertIn("PE1008_J", w["jam_pe_tags"])

    def test_clone_fast_conv_uses_no_pe_when_no_product(self):
        if not LIBRARY.is_file():
            self.skipTest(f"library missing: {LIBRARY}")
        lib = LIBRARY.read_text(encoding="utf-8", errors="replace")
        item = clone_template_for_conveyor(
            lib,
            "P3000_Conv",
            "P1006",
            "Test_Area",
            "Test_Area_Safe",
            "",
            exit_pe_tag="",
            add_pe_tag="",
            jam_pe_tags=["PE1006_J"],
        )
        fast = next(r for r in item["rungs"] if r["label"] == "Fast")
        self.assertIn("NO_PE,NO_PE", fast["text"].replace(" ", ""))
        self.assertNotIn("PE1006_J", fast["text"])


class TestConvTypeLibraryAligned(unittest.TestCase):
    def test_straight_ms_is_type_3(self):
        c = classify_conv_type("STRAIGHT", False)
        self.assertEqual(c["type_code"], 3)
        self.assertEqual(_conv_udt_type_code("Transport with MS"), 3)

    def test_zeropressure_ms_is_type_2(self):
        c = classify_conv_type("ZEROPRESSURE", False)
        self.assertEqual(c["type_code"], 2)


class TestPiAreaModel(unittest.TestCase):
    def test_conveyor_row_has_pi_area_fields(self):
        row = ConveyorRow(conveyor="P1006", number="1006", main_area="Test_Area")
        self.assertTrue(hasattr(row, "pi_area"))
        self.assertTrue(hasattr(row, "pi_area_confidence"))
        self.assertEqual(row.pi_area, "")


class TestGeneratedFastSlowScheduling(unittest.TestCase):
    """Generated L5X invariants — not source-string checks."""

    @classmethod
    def setUpClass(cls):
        if not LIBRARY.is_file():
            raise unittest.SkipTest(f"library missing: {LIBRARY}")
        # Generic synthetic area: PE_Logic (product), Full_PE, and a 2:1 merge.
        cls.inp = AutogenInput(
            project_name="Synthetic_Peripheral_CTRL",
            machine="SYNTH_CTRL",
            areas=["Test_Area"],
            safety_zones=["Test_Area_ESZone1"],
            conveyors=[
                ConveyorRow(
                    number=1,
                    conveyor="P501",
                    main_area="Test_Area",
                    safety_zone="Test_Area_ESZone1",
                    type="Transport with MS",
                    motor_starter="Yes",
                    exit_pe_tag="PE501_P",
                    jam_pe_tags=["PE501_J"],
                    product_pe_tags=["PE501_P"],
                    full_pe_tags=["PE501_F"],
                    all_pe_tags=["PE501_P", "PE501_J", "PE501_F"],
                ),
                ConveyorRow(
                    number=2,
                    conveyor="P502",
                    main_area="Test_Area",
                    safety_zone="Test_Area_ESZone1",
                    type="Transport with MS",
                    motor_starter="Yes",
                    exit_pe_tag="",
                    jam_pe_tags=["PE502_J"],
                    product_pe_tags=[],
                    full_pe_tags=[],
                    all_pe_tags=["PE502_J"],
                ),
                ConveyorRow(
                    number=3,
                    conveyor="P503",
                    main_area="Test_Area",
                    safety_zone="Test_Area_ESZone1",
                    type="Transport with MS",
                    motor_starter="Yes",
                ),
            ],
            merges_2to1=[
                {
                    "name": "P503",
                    "area": "Test_Area",
                    "lanes": 2,
                    "lane_a": "P501",
                    "lane_b": "P502",
                    "discharge": "P503",
                    "pe_a": "NO_PE",
                    "pe_b": "NO_PE",
                    "jam_pe": "NO_PE",
                }
            ],
            include_sys=False,
            include_io_map=False,
            include_io_map_gold=False,
        )
        cls.l5x, cls.report = build_l5x(cls.inp, LIBRARY)
        cls.fast = _program_xml(cls.l5x, "Test_Area_Area_Fast")
        cls.slow = _program_xml(cls.l5x, "Test_Area_Area_Slow")
        if not cls.fast:
            # Some emitters use Test_Area_Fast when area already ends with _Area
            cls.fast = _program_xml(cls.l5x, "Test_Area_Fast")
        if not cls.slow:
            cls.slow = _program_xml(cls.l5x, "Test_Area_Slow")
        cls.fast_main = _routine_xml(cls.fast, "Main_Routine")
        cls.slow_main = _routine_xml(cls.slow, "Main_Routine")
        cls.fast_jsrs = _jsr_targets(cls.fast_main)
        cls.slow_jsrs = _jsr_targets(cls.slow_main)

    def test_programs_emitted(self):
        self.assertTrue(self.fast, "Fast program missing from L5X")
        self.assertTrue(self.slow, "Slow program missing from L5X")
        self.assertTrue(self.fast_main, "Fast Main_Routine missing")
        self.assertTrue(self.slow_main, "Slow Main_Routine missing")

    def test_fast_has_exactly_one_conv_fast_jsr(self):
        self.assertEqual(_count(self.fast_jsrs, "Conv_Fast"), 1)

    def test_fast_owns_conv_pe_exactly_once(self):
        self.assertEqual(_count(self.fast_jsrs, "Conv_PE"), 1)
        self.assertEqual(len(re.findall(r'Routine Name="Conv_PE"', self.fast)), 1)
        pe_body = _routine_xml(self.fast, "Conv_PE")
        self.assertIn("PE_Logic(", pe_body)

    def test_slow_has_no_conv_pe(self):
        self.assertEqual(_count(self.slow_jsrs, "Conv_PE"), 0)
        self.assertNotIn('Routine Name="Conv_PE"', self.slow)
        self.assertNotIn("PE_Logic(", self.slow)

    def test_fast_full_scheduled_exactly_once(self):
        self.assertEqual(_count(self.fast_jsrs, "Conv_Full"), 1)
        self.assertEqual(len(re.findall(r'Routine Name="Conv_Full"', self.fast)), 1)

    def test_fast_merge_scheduled_exactly_once(self):
        self.assertEqual(_count(self.fast_jsrs, "Conv_Merge"), 1)
        self.assertEqual(len(re.findall(r'Routine Name="Conv_Merge"', self.fast)), 1)

    def test_no_dual_rate_pe_logic(self):
        """Every PE_Logic call must live under Fast Conv_PE — never Slow."""
        pe_calls = len(re.findall(r"PE_Logic\(", self.l5x))
        fast_pe = _routine_xml(self.fast, "Conv_PE")
        fast_pe_calls = len(re.findall(r"PE_Logic\(", fast_pe or ""))
        self.assertGreater(pe_calls, 0)
        self.assertEqual(pe_calls, fast_pe_calls)

    def test_fast_jsrs_only_call_emitted_routines(self):
        """Compiler invariant: every Fast Main JSR target must exist as a routine."""
        for target in self.fast_jsrs:
            self.assertIn(
                f'Routine Name="{target}"',
                self.fast,
                f"Fast Main_Routine JSR({target}) but routine missing",
            )


class TestAreaWithoutPeHasNoConvPe(unittest.TestCase):
    """Area with zero real PE rungs must not emit orphan Conv_PE / JSR."""

    @classmethod
    def setUpClass(cls):
        if not LIBRARY.is_file():
            raise unittest.SkipTest(f"library missing: {LIBRARY}")
        cls.inp = AutogenInput(
            project_name="Synthetic_NoPE_CTRL",
            machine="SYNTH_NOPE",
            areas=["Bare_Area"],
            safety_zones=["Bare_Area_ESZone1"],
            conveyors=[
                ConveyorRow(
                    number=1,
                    conveyor="P601",
                    main_area="Bare_Area",
                    safety_zone="Bare_Area_ESZone1",
                    type="Transport with MS",
                    motor_starter="Yes",
                ),
            ],
            include_sys=False,
            include_io_map=False,
            include_io_map_gold=False,
        )
        cls.l5x, _ = build_l5x(cls.inp, LIBRARY)
        cls.fast = _program_xml(cls.l5x, "Bare_Area_Fast") or _program_xml(
            cls.l5x, "Bare_Area_Area_Fast"
        )
        cls.slow = _program_xml(cls.l5x, "Bare_Area_Slow") or _program_xml(
            cls.l5x, "Bare_Area_Area_Slow"
        )
        cls.fast_jsrs = _jsr_targets(_routine_xml(cls.fast, "Main_Routine"))
        cls.slow_jsrs = _jsr_targets(_routine_xml(cls.slow, "Main_Routine"))

    def test_no_conv_pe_anywhere(self):
        self.assertEqual(_count(self.fast_jsrs, "Conv_PE"), 0)
        self.assertEqual(_count(self.slow_jsrs, "Conv_PE"), 0)
        self.assertNotIn('Routine Name="Conv_PE"', self.fast)
        self.assertNotIn('Routine Name="Conv_PE"', self.slow)
        self.assertNotIn("PE_Logic(", self.l5x)


class TestTrashAreaWithPeUsesFastConvPe(unittest.TestCase):
    """Trash-named Area with PE follows the same Fast Conv_PE contract."""

    @classmethod
    def setUpClass(cls):
        if not LIBRARY.is_file():
            raise unittest.SkipTest(f"library missing: {LIBRARY}")
        cls.inp = AutogenInput(
            project_name="Synthetic_Trash_CTRL",
            machine="SYNTH_TRASH",
            areas=["Trash_Area"],
            safety_zones=["Trash_Area_ESZone1"],
            conveyors=[
                ConveyorRow(
                    number=1,
                    conveyor="P701",
                    main_area="Trash_Area",
                    safety_zone="Trash_Area_ESZone1",
                    type="Transport with MS",
                    motor_starter="Yes",
                    exit_pe_tag="PE701_P",
                    jam_pe_tags=["PE701_J"],
                    product_pe_tags=["PE701_P"],
                    all_pe_tags=["PE701_P", "PE701_J"],
                ),
            ],
            include_sys=False,
            include_io_map=False,
            include_io_map_gold=False,
        )
        cls.l5x, _ = build_l5x(cls.inp, LIBRARY)
        cls.fast = _program_xml(cls.l5x, "Trash_Area_Fast") or _program_xml(
            cls.l5x, "Trash_Area_Area_Fast"
        )
        cls.slow = _program_xml(cls.l5x, "Trash_Area_Slow") or _program_xml(
            cls.l5x, "Trash_Area_Area_Slow"
        )
        cls.fast_jsrs = _jsr_targets(_routine_xml(cls.fast, "Main_Routine"))
        cls.slow_jsrs = _jsr_targets(_routine_xml(cls.slow, "Main_Routine"))

    def test_trash_fast_owns_pe(self):
        self.assertEqual(_count(self.fast_jsrs, "Conv_PE"), 1)
        pe_body = _routine_xml(self.fast, "Conv_PE")
        self.assertIn("PE_Logic(", pe_body)
        self.assertIn("PE701", pe_body)

    def test_trash_slow_has_no_pe(self):
        self.assertEqual(_count(self.slow_jsrs, "Conv_PE"), 0)
        self.assertNotIn('Routine Name="Conv_PE"', self.slow)


class TestMultiAreaPeIsolation(unittest.TestCase):
    """PE rungs must not leak between Areas."""

    @classmethod
    def setUpClass(cls):
        if not LIBRARY.is_file():
            raise unittest.SkipTest(f"library missing: {LIBRARY}")
        cls.inp = AutogenInput(
            project_name="Synthetic_Multi_CTRL",
            machine="SYNTH_MULTI",
            areas=["Area_A", "Area_B"],
            safety_zones=["Area_A_ESZone1", "Area_B_ESZone1"],
            conveyors=[
                ConveyorRow(
                    number=1,
                    conveyor="P801",
                    main_area="Area_A",
                    safety_zone="Area_A_ESZone1",
                    type="Transport with MS",
                    motor_starter="Yes",
                    exit_pe_tag="PE801_P",
                    jam_pe_tags=["PE801_J"],
                    product_pe_tags=["PE801_P"],
                    all_pe_tags=["PE801_P", "PE801_J"],
                ),
                ConveyorRow(
                    number=2,
                    conveyor="P901",
                    main_area="Area_B",
                    safety_zone="Area_B_ESZone1",
                    type="Transport with MS",
                    motor_starter="Yes",
                    exit_pe_tag="PE901_P",
                    jam_pe_tags=["PE901_J"],
                    product_pe_tags=["PE901_P"],
                    all_pe_tags=["PE901_P", "PE901_J"],
                ),
            ],
            include_sys=False,
            include_io_map=False,
            include_io_map_gold=False,
        )
        cls.l5x, _ = build_l5x(cls.inp, LIBRARY)
        cls.fast_a = _program_xml(cls.l5x, "Area_A_Fast") or _program_xml(
            cls.l5x, "Area_A_Area_Fast"
        )
        cls.fast_b = _program_xml(cls.l5x, "Area_B_Fast") or _program_xml(
            cls.l5x, "Area_B_Area_Fast"
        )

    def test_pe_devices_stay_in_own_area(self):
        pe_a = _routine_xml(self.fast_a, "Conv_PE")
        pe_b = _routine_xml(self.fast_b, "Conv_PE")
        self.assertIn("PE801", pe_a)
        self.assertNotIn("PE901", pe_a)
        self.assertIn("PE901", pe_b)
        self.assertNotIn("PE801", pe_b)


class TestAreaTimerContract(unittest.TestCase):
    def test_l1_area_emits_library_timer_set(self):
        src = (SCRIPTS / "fortna_autogen.py").read_text(encoding="utf-8", errors="replace")
        for member in (
            "StartTime",
            "RstTime",
            "SilTime",
            "AutoSilTime",
            "JamRstTime",
            "FltRstTime",
            "EngMgmtTime",
        ):
            self.assertIn(f".{member} :=", src)


class TestMpsInvestigationNote(unittest.TestCase):
    def test_mps_is_library_template_not_production_emit(self):
        lib = LIBRARY.read_text(encoding="utf-8", errors="replace")
        self.assertIn("MPS3000", lib)
        bind = (SCRIPTS / "fortna_equipment_binding.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("P{stem}_MS", bind)
        self.assertNotIn('return f"MPS', bind)


if __name__ == "__main__":
    unittest.main()

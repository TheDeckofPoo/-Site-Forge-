"""ORNCCP2 Trash Area peripheral-fidelity regressions (no topology scoring).

Covers:
  - Fast_Conv PE roles (jam must not become exit/add)
  - PE_Logic not double-scheduled in Slow and Fast
  - Area_UDT library timer initialization
  - pi_area field exists and Conv_PI can exclude non-matching pi_area
  - Conv.Type remains library+RUN aligned (Transport+MS → 3)
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "tools" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fortna_autogen import (  # noqa: E402
    ConveyorRow,
    _conv_udt_type_code,
    _pe_wiring_for_conv,
    clone_template_for_conveyor,
)
from fortna_conveyor_section_model import classify_conv_type  # noqa: E402


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
        lib = (REPO / "tools" / "libraries" / "OReilly_Library_v3.L5X").read_text(
            encoding="utf-8", errors="replace"
        )
        item = clone_template_for_conveyor(
            lib,
            "P3000_Conv",
            "P1006",
            "Trash_Zone",
            "Trash_Zone_Safe",
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
        row = ConveyorRow(conveyor="P1006", number="1006", main_area="Trash_Zone")
        self.assertTrue(hasattr(row, "pi_area"))
        self.assertTrue(hasattr(row, "pi_area_confidence"))
        self.assertEqual(row.pi_area, "")


class TestPeNotDoubleScheduled(unittest.TestCase):
    """Static contract: build_l5x must not attach the same PE_Logic list to Fast."""

    def test_autogen_source_omits_fast_conv_pe_duplicate(self):
        src = (SCRIPTS / "fortna_autogen.py").read_text(encoding="utf-8", errors="replace")
        # After the peripheral pass, Fast must not get routine("Conv_PE", rungs_pe)
        # while Slow still may.
        # Find the Fast program assembly block after "--- Fast"
        m = re.search(
            r"# --- Fast:.*?programs_xml\.append\(\s*f'<Program Name=\"\{prog_fast\}\"",
            src,
            re.S,
        )
        self.assertIsNotNone(m, "Fast program assembly block not found")
        fast_block = m.group(0)
        self.assertNotIn(
            'routine("Conv_PE", rungs_pe)',
            fast_block,
            "PE_Logic must not be duplicated into Fast Conv_PE",
        )
        self.assertIn(
            'routine("Conv_PE", rungs_pe)',
            src,
            "Slow Conv_PE should still exist",
        )


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
        """MPS#### appears in library samples; production emit uses P####_MS."""
        lib = (REPO / "tools" / "libraries" / "OReilly_Library_v3.L5X").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("MPS3000", lib)
        bind = (SCRIPTS / "fortna_equipment_binding.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("P{stem}_MS", bind)
        self.assertNotIn('return f"MPS', bind)


if __name__ == "__main__":
    unittest.main()

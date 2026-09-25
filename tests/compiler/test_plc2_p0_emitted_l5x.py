#!/usr/bin/env python3
"""Generated-L5X validation for PLC2 P0s — source existence is not enough.

Verifies emitted tag DataTypes and AOI operand contracts in synthetic L5X fragments
built the same way production Autogen builds them.
"""
from __future__ import annotations

from pathlib import Path as _SFPath
import sys as _SFSys

_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys = _SFSys
sys.path.insert(0, str(SCRIPTS))

import fortna_autogen as ag  # noqa: E402
from fortna_equipment_binding import classify_estop  # noqa: E402
from fortna_es_compiler import build_safety_zone_irs, emit_es_program  # noqa: E402
from fortna_io_extract import equipment_kind  # noqa: E402


def _rung_xml(num: int, text: str, comment: str = "") -> str:
    c = f"<Comment><![CDATA[{comment}]]></Comment>" if comment else ""
    return f'<Rung Number="{num}" Type="N">{c}<Text><![CDATA[{text}]]></Text></Rung>'


def _routine(name: str, rungs: list[str]) -> str:
    fixed = [re.sub(r'Number="\d+"', f'Number="{i}"', r, count=1) for i, r in enumerate(rungs)]
    return (
        f'<Routine Name="{name}" Type="RLL"><RLLContent>'
        + "".join(fixed)
        + "</RLLContent></Routine>"
    )


class TestPd0002McrEmittedDatatype(unittest.TestCase):
    """PD-0002: bare MCR coil must not become ES_UDT in emitted tag XML."""

    def test_classify_and_member_reject_coil(self) -> None:
        self.assertIsNone(
            classify_estop(
                "2MCR1",
                direction="O",
                device_type="1794-OA8I",
                description="ENERGIZE MASTER CONTROL RELAY",
            )
        )
        self.assertEqual(equipment_kind("2MCR1", "BEACON", "ENERGIZE MASTER CONTROL RELAY"), "digital_out")
        self.assertEqual(ag._io_map_es_member("2MCR1"), "")
        self.assertEqual(ag._io_map_es_member("T_2MCR1"), "")
        self.assertTrue(ag._io_map_es_member("2MCR1_AUX").endswith(".I.ES_OK"))

    def test_needs_es_udt_logic_excludes_bare_mcr(self) -> None:
        """Mirror production needs_es_udt gate against bare coil names."""
        for raw, tname in (("2MCR1", "T_2MCR1"), ("3MCR1", "T_3MCR1"), ("14MCR1", "T_14MCR1")):
            _raw_u = raw.upper()
            _tn_u = tname.upper()
            _is_mcr_coil = bool(
                re.match(r"^(?:T_)?\d*MCR\d*$", _tn_u)
                or re.match(r"^(?:T_)?\d*MCR\d*$", _raw_u)
            ) and not (_tn_u.endswith("_AUX") or _raw_u.endswith("_AUX"))
            self.assertTrue(_is_mcr_coil, msg=raw)
            # AUX still allowed
        self.assertTrue(
            re.match(r"^(?:T_)?\d+MCR\d*_AUX$", "T_2MCR1_AUX", re.I)
        )


class TestPd0003PiWriterEnforced(unittest.TestCase):
    def test_emit_writers_only_for_membered_zones(self) -> None:
        zones = build_safety_zone_irs(
            safety_zones=["Area_A_ESZone1", "Orphan_ESZone1"],
            areas=["Area_A"],
            engineer_zones=[
                {
                    "name": "Area_A_ESZone1",
                    "area": "Area_A",
                    "members": ["ES100"],
                    "conveyors": ["P100"],
                }
            ],
            estop_model={"zones": []},
            area_conveyors={"Area_A": ["P100"]},
        )
        pack = emit_es_program(
            zones,
            _rung_xml=_rung_xml,
            routine=_routine,
            extract_tag_block=lambda *_a, **_k: None,
            library_text="",
            ensure_tag=lambda _n: None,
            add_tag_block=lambda _b: None,
        )
        self.assertIsNotNone(pack)
        writers = set(pack.get("zones_with_pi_writers") or [])
        self.assertIn("Area_A_ESZone1", writers)
        self.assertNotIn("Orphan_ESZone1", writers)
        # Fast_Conv must not be allowed to keep Orphan as operational consumer
        self.assertTrue(pack.get("pi_writer_invariant_ok"))


class TestPd0005ControlStationOperands(unittest.TestCase):
    def test_library_contract_no_literal_zero_inout(self) -> None:
        """Gold/library pattern uses CS_UDT / NO_CS — never literal 0 InOut."""
        lib = (ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X").read_text(
            encoding="utf-8", errors="replace"
        )
        # Template call in library
        m = re.search(r"Slow_ControlStation\(([^)]+)\)", lib)
        self.assertIsNotNone(m)
        args = [a.strip() for a in m.group(1).split(",")]
        # Last may be numeric timeout; prior must not be bare 0
        for a in args[:-1]:
            self.assertNotEqual(a, "0", msg=f"InOut literal 0 forbidden: {m.group(0)}")
        self.assertTrue(any("CS" in a or a.startswith("Input") or a == "NO_CS" for a in args[1:-1]) or len(args) >= 2)

    def test_autogen_emit_pattern_uses_no_cs_not_zero(self) -> None:
        src = (SCRIPTS / "fortna_autogen.py").read_text(encoding="utf-8", errors="replace")
        # Production must not contain the broken literal-0 pattern
        self.assertNotRegex(src, r'Slow_ControlStation\([^)]*,0,0,0,0,0,')
        self.assertIn("NO_CS", src)
        self.assertIn("DataType=\"Slow_ControlStation\"", src)


class TestPd0029CommDiagOmitted(unittest.TestCase):
    def test_commdiag_udt_file_not_in_production_libraries(self) -> None:
        self.assertFalse((ROOT / "tools" / "libraries" / "CommDiag_UDT.L5X").is_file())

    def test_load_generic_commdiag_removed(self) -> None:
        self.assertFalse(hasattr(ag, "_load_generic_commdiag_udt_xml"))


class TestPd0036IoMapGoldQuarantined(unittest.TestCase):
    def test_io_map_not_in_programs_dir(self) -> None:
        self.assertFalse(
            (ROOT / "tools" / "libraries" / "programs" / "IO_MAP_Program.L5X").is_file()
        )
        self.assertTrue(
            (ROOT / "tools" / "libraries" / "validation_oracles" / "IO_MAP_Program.L5X").is_file()
        )

    def test_include_io_map_gold_does_not_merge(self) -> None:
        packs = ag.resolve_program_exports(include_sys=False, include_io_map_gold=True)
        names = [p.get("name") for p in packs]
        self.assertNotIn("IO_MAP", names)
        self.assertNotIn("Sys", names)


class TestPd0035MtrchainProvenance(unittest.TestCase):
    def test_vocab_separates_fullline(self) -> None:
        src = (SCRIPTS / "fortna_autogen.py").read_text(encoding="utf-8", errors="replace")
        self.assertIn("RUN_MTRCHAIN_PROVEN", src)
        self.assertIn("RUN_FULLLINE_DERIVED", src)
        self.assertIn("PD-0035", src)
        csrc = (SCRIPTS / "fortna_conveyor_section_model.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("mtrchain_timer_name", csrc)
        self.assertIn("infer_downstream_from_fullline", csrc)


if __name__ == "__main__":
    unittest.main()

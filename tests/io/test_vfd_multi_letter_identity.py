#!/usr/bin/env python3
"""VFD identity parsing: multi-letter equipment suffixes (13RB) + conveyor lineage."""
from __future__ import annotations

import re
import unittest
from types import SimpleNamespace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_vfd_device_model import _vfd_base_and_suffix, _plc_num  # noqa: E402


def _vfd_parse(tname: str) -> tuple[str, str] | None:
    """Mirror fortna_autogen._vfd_parse (keep tests free of full generate() scope)."""
    m = (
        re.match(r"^VFD(\d+[A-Z]*)(?:_(.+))?$", tname, re.I)
        or re.match(r"^T_VFD(\d+[A-Z]*)(?:_(.+))?$", tname, re.I)
    )
    if not m:
        return None
    identity = (m.group(1) or "").upper()
    if not identity or not re.match(r"^\d+[A-Z]*$", identity):
        return None
    return identity, (m.group(2) or "").upper()


def _vfd_has_conveyor_lineage(identity: str, known: set[str]) -> bool:
    ident = (identity or "").upper()
    if not ident or not known:
        return False
    candidates = {f"P{ident}"}
    m = re.match(r"^(\d+)([A-Z]+)$", ident)
    if m:
        candidates.add(f"P{m.group(1)}-{m.group(2)}")
        candidates.add(f"P{m.group(1)}_{m.group(2)}")
    if candidates & known:
        return True
    want = f"P{ident}"
    for c in known:
        if re.sub(r"[-_]", "", c) == want:
            return True
    return False


def _vfd_ms_member_for_test(tname: str, direction: str, known: set[str]) -> str | None:
    parsed = _vfd_parse(tname)
    if not parsed:
        return None
    num, suffix = parsed
    if not _vfd_has_conveyor_lineage(num, known):
        return None
    base = f"P{num}_VFD"
    d = (direction or "").upper()
    if suffix in ("AUX", "AUXILIARY", "AUX_FWD", "AF", "FB", "FEEDBACK"):
        return f"{base}.I.Auxiliary_Forward"
    if not suffix:
        if d in ("O", "OUT", "OUTPUT"):
            return f"{base}.O.Run"
        return f"{base}.I.Auxiliary_Forward"
    return None


class TestVfdMultiLetterIdentity(unittest.TestCase):
    def test_parse_single_and_multi_letter(self) -> None:
        self.assertEqual(_vfd_parse("VFD13"), ("13", ""))
        self.assertEqual(_vfd_parse("VFD13A"), ("13A", ""))
        self.assertEqual(_vfd_parse("VFD13RB"), ("13RB", ""))
        self.assertEqual(_vfd_parse("VFD13RB_AUX"), ("13RB", "AUX"))
        self.assertEqual(_vfd_parse("T_VFD13RB_AUX"), ("13RB", "AUX"))
        self.assertIsNone(_vfd_parse("PE13RB_F"))

    def test_device_model_parse_parity(self) -> None:
        self.assertEqual(_vfd_base_and_suffix("VFD13RB_AUX"), ("VFD13RB", "AUX"))
        self.assertEqual(_plc_num("VFD13RB"), "13RB")
        self.assertEqual(_plc_num("VFD13A"), "13A")
        self.assertEqual(_plc_num("VFD13"), "13")

    def test_lineage_hyphen_insensitive(self) -> None:
        known = {"P13-RB", "P100", "P13A"}
        self.assertTrue(_vfd_has_conveyor_lineage("13RB", known))
        self.assertTrue(_vfd_has_conveyor_lineage("13A", known))
        self.assertTrue(_vfd_has_conveyor_lineage("100", known))
        self.assertFalse(_vfd_has_conveyor_lineage("13", known))  # no bare P13
        self.assertFalse(_vfd_has_conveyor_lineage("99Z", known))

    def test_members_with_lineage(self) -> None:
        known = {"P13-RB", "P13", "P13A"}
        self.assertEqual(
            _vfd_ms_member_for_test("VFD13RB_AUX", "I", known),
            "P13RB_VFD.I.Auxiliary_Forward",
        )
        self.assertEqual(
            _vfd_ms_member_for_test("VFD13RB", "O", known),
            "P13RB_VFD.O.Run",
        )
        self.assertEqual(
            _vfd_ms_member_for_test("VFD13A", "O", known),
            "P13A_VFD.O.Run",
        )
        self.assertEqual(
            _vfd_ms_member_for_test("VFD13", "O", known),
            "P13_VFD.O.Run",
        )

    def test_no_lineage_stays_unresolved(self) -> None:
        known = {"P100"}  # no P13RB / P13-RB
        self.assertIsNone(_vfd_ms_member_for_test("VFD13RB", "O", known))
        self.assertIsNone(_vfd_ms_member_for_test("VFD13RB_AUX", "I", known))

    def test_autogen_source_uses_multi_letter_regex(self) -> None:
        src = (ROOT / "tools" / "scripts" / "fortna_autogen.py").read_text(encoding="utf-8")
        self.assertIn(r"VFD(\d+[A-Z]*)", src)
        self.assertIn("_vfd_has_conveyor_lineage", src)
        # Old single-letter-only pattern must not be the only parse path
        self.assertNotRegex(
            src,
            r'def _vfd_parse\(tname: str\).*?VFD\(\\d\+\[A-Z\]\?\)',
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

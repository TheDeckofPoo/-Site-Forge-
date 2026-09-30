#!/usr/bin/env python3
"""ORI-081: E-stop FEEDBACK must OTE BOOL member, never ES_UDT root."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_autogen import _io_map_es_member  # noqa: E402


def _find_udt_root_otes(l5x_text: str, udt_tag_names: set[str]) -> list[str]:
    """Return OTE operands whose target is a bare UDT root (no member)."""
    bad: list[str] = []
    for m in re.finditer(r"\bOTE\(([^)]+)\)", l5x_text, flags=re.I):
        op = m.group(1).strip()
        if "." in op:
            continue
        root = op.split("[", 1)[0].strip()
        if root.upper() in {n.upper() for n in udt_tag_names}:
            bad.append(op)
    return bad


class TestOri081EspbUdtOte(unittest.TestCase):
    def test_espb_maps_to_es_ok_member(self) -> None:
        self.assertEqual(_io_map_es_member("ESPB24"), "ESPB24.I.ES_OK")
        self.assertEqual(_io_map_es_member("ESPB2"), "ESPB2.I.ES_OK")
        self.assertEqual(_io_map_es_member("ESPB32"), "ESPB32.I.ES_OK")
        self.assertEqual(_io_map_es_member("ESLS2"), "ESLS2.I.ES_OK")

    def test_udt_root_ote_rejected(self) -> None:
        l5x = """
        <Tag Name="ESPB24" DataType="ES_UDT"/>
        <Tag Name="ESLS2" DataType="ES_UDT"/>
        <Text><![CDATA[XIC(AENTR1:I.Data[3].7)OTE(ESPB24);]]></Text>
        <Text><![CDATA[XIC(AENTR2:I.Data[2].3)OTE(ESLS2.I.ES_OK);]]></Text>
        """
        bad = _find_udt_root_otes(l5x, {"ESPB24", "ESLS2"})
        self.assertEqual(bad, ["ESPB24"])


if __name__ == "__main__":
    unittest.main()

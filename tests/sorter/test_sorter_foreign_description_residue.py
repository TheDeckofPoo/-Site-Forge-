#!/usr/bin/env python3
"""Part J: sorter pack Divert descriptions must not retain foreign SSV50x names."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_sorter_build import (  # noqa: E402
    SORTER_TRACK_PACK,
    _neutralize_divert_tag_descriptions,
    _neutralize_foreign_description_cdata,
    build_sorter_track,
)


class TestSorterForeignDescriptionResidue(unittest.TestCase):
    def test_neutralize_divert_descriptions(self) -> None:
        block = (
            '<Tag Name="PS1_Divert3" DataType="Track_Divert_UDT">'
            "<Description><![CDATA[Divert 3:\nSSV506E1 &\nSSV506E2]]></Description>"
            "</Tag>"
        )
        out, n = _neutralize_divert_tag_descriptions([block])
        self.assertEqual(n, 1)
        self.assertIn("Divert 3", out[0])
        self.assertNotRegex(out[0], r"SSV50")

    def test_neutralize_foreign_cdata(self) -> None:
        xml = (
            "<Comment><![CDATA[ORLY_Greensboro_NC_PLC5 residue]]></Comment>"
            "<Description><![CDATA[clean local note]]></Description>"
        )
        out, n = _neutralize_foreign_description_cdata(xml)
        self.assertGreaterEqual(n, 1)
        self.assertNotIn("ORLY_Greensboro", out)
        self.assertIn("clean local note", out)

    @unittest.skipUnless(SORTER_TRACK_PACK.is_file(), "Sorter_Track pack not installed")
    def test_configured_pack_emit_has_no_ssv50x_descriptions(self) -> None:
        sorter = {
            "divert_count": 16,
            "divert_host_conveyor": "PS1",
            "induct_conveyor": "PS1",
            "induct_pe": "PE60_I",
            "encoders": [{"name": "SHIP SORT", "io": "ENC_SHIP", "include": True}],
        }
        compiled = build_sorter_track(sorter, library_text="")
        self.assertEqual(compiled.get("report", {}).get("mode"), "configured_pack")
        blob = "\n".join(
            [
                compiled.get("program_xml") or "",
                "\n".join(compiled.get("tags") or []),
                "\n".join(compiled.get("program_local_tags") or []),
            ]
        )
        # Descriptions/comments must not carry Greensboro divert solenoids
        for m in re.finditer(
            r"<(?:Description|Comment)>\s*<!\[CDATA\[(.*?)\]\]>",
            blob,
            re.S,
        ):
            body = m.group(1)
            self.assertNotRegex(
                body,
                r"(?i)SSV50[0-9]|Greensboro|Brownsburg|ORLY_",
                msg=f"foreign residue in description/comment: {body[:80]!r}",
            )
        self.assertGreaterEqual(
            int((compiled.get("report") or {}).get("foreign_description_scrubbed") or 0),
            1,
        )


if __name__ == "__main__":
    unittest.main()

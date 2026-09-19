#!/usr/bin/env python3
"""Unmapped pack-template slots must be pruned — never remapped to divert_host."""
from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_sorter_build import (  # noqa: E402
    PACK_TEMPLATE_ENC_SLOTS,
    _mapped_template_slots,
    _unmapped_template_slots,
    build_configured_sorter_track,
)
from fortna_final_artifact_closure import validate_final_artifact  # noqa: E402

LIB = _SF_REPO / "tools" / "libraries" / "OReilly_Library_v3.L5X"


class TestTemplateSlotMapping(unittest.TestCase):
    def test_two_tracking_rows_map_first_two_slots_only(self) -> None:
        sorter = {
            "divert_host_conveyor": "P610",
            "induct_conveyor": "P606",
            "divert_count": 4,
            "tracking": [
                {"conveyor": "P606", "encoder_tag": "ENC606", "has_encoder": "yes"},
                {"conveyor": "P610", "encoder_tag": "ENC610", "has_encoder": "yes"},
            ],
        }
        mapped = _mapped_template_slots(sorter)
        self.assertEqual(mapped.get("P504"), "P606")
        self.assertEqual(mapped.get("P506"), "P610")
        unmapped = _unmapped_template_slots(sorter)
        self.assertIn("P508", unmapped)
        self.assertIn("P509", unmapped)
        self.assertIn("P510", unmapped)
        self.assertNotIn("P504", unmapped)
        self.assertNotIn("P506", unmapped)


@unittest.skipUnless(LIB.is_file(), "library L5X missing")
class TestConfiguredPackPrunesUnmapped(unittest.TestCase):
    def test_unmapped_slots_not_emitted_as_live_equipment(self) -> None:
        sorter = {
            "divert_host_conveyor": "P610",
            "induct_conveyor": "P606",
            "divert_count": 4,
            "tracking_count": 2,
            "tracking": [
                {"conveyor": "P606", "encoder_tag": "ENC606", "has_encoder": "yes", "pe": "PE606_I"},
                {"conveyor": "P610", "encoder_tag": "ENC610", "has_encoder": "yes", "pe": "PE610_I"},
            ],
            "induct_has_encoder": "yes",
            "induct_encoder_tag": "ENC606",
        }
        lib = LIB.read_text(encoding="utf-8", errors="replace")
        live = build_configured_sorter_track(sorter, lib)
        blob = (live.get("program_xml") or "") + "\n" + "\n".join(live.get("tags") or [])
        rep = live.get("report") or {}

        self.assertEqual(rep.get("mapped_template_slots", {}).get("P504"), "P606")
        self.assertIn("P508", rep.get("unmapped_template_slots") or [])

        # Unmapped template hosts must not survive as Tag declarations.
        for slot in ("P508", "P509", "P510"):
            tag_hits = re.findall(rf'Tag Name="{slot}(?:_[^"]*)?"', blob)
            self.assertEqual(tag_hits, [], f"unmapped {slot} tags still emitted: {tag_hits[:8]}")

        # Divert family must land on proven divert_host, not leftover template hosts.
        self.assertRegex(blob, r"P610_Divert")
        self.assertNotRegex(blob, r"P506_Divert\d")
        self.assertNotRegex(blob, r"P508_Divert\d")

        # Must NOT solve unmapped slots by dumping them onto divert_host wholesale.
        # P610_Conv_Track is OK (mapped from P506); P610_* from P508/P509/P510 is not.
        # Presence of P508 tokens anywhere (including live operands) is a fail.
        live_ops = re.findall(r"\bP508_[A-Za-z0-9_]+\b", blob)
        # Allow only inside DISABLED comments if any slipped; prefer zero.
        self.assertEqual(live_ops, [], f"unmapped P508 operands survived: {live_ops[:12]}")


class TestFinalClosureTemplateEquipment(unittest.TestCase):
    def test_template_equipment_without_lineage_fails(self) -> None:
        fake = (
            '<Tag Name="P506_Conv_Track"/>'
            '<Tag Name="P610_Divert1"/>'
            '<Tag Name="P508_Enc"/>'
        )
        r = validate_final_artifact(
            l5x_text=fake,
            machine="ORINDYAC6",
            allowed_divert_hosts=["P610"],
            allowed_template_hosts=["P610"],
        )
        self.assertEqual(r["status"], "FAIL")
        joined = " ".join(r.get("errors") or [])
        self.assertIn("PACK_TEMPLATE_EQUIPMENT_NO_LINEAGE", joined)


if __name__ == "__main__":
    unittest.main(verbosity=2)

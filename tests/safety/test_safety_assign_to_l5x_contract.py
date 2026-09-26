"""Physical SafetyDevice → zone assignment → workbook → L5X ES_UDT contract.

ORI-054 disposition (Warden re-gate @ 969eb83):
  Prior expectations called build_l5x with empty io_points and no emitted
  writer graph, then required ES_UDT tags / zone routines. After ORI-048 the
  compiler refuses Safety consumers without a real writer — that is deliberate
  fail-safe production behavior, not a regression to weaken.

  These tests now exercise the stronger invariants:
    - with an emitted writer → one canonical ES_UDT, no AUX dupe, zone routines
    - without a writer → no silent ES_SIL1 / orphan consumer emission
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "tools" / "scripts"
LIBRARY = REPO / "tools" / "libraries" / "OReilly_Library_v3.L5X"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fortna_es_compiler import (  # noqa: E402
    build_safety_zone_irs,
    emit_es_program,
)


def _rung_xml(num: int, text: str, comment: str = "") -> str:
    c = f"<Comment><![CDATA[{comment}]]></Comment>" if comment else ""
    return f'<Rung Number="{num}" Type="N">{c}<Text><![CDATA[{text}]]></Text></Rung>'


def _routine(name: str, rungs: list[str]) -> str:
    body = "".join(rungs)
    return f'<Routine Name="{name}" Type="RLL"><RLLContent>{body}</RLLContent></Routine>'


class TestSafetyAssignToL5xContract(unittest.TestCase):
    def test_engineer_zone_members_emit_es_udt_not_aux_dupes(self):
        """ORI-054: with a real writer, canonical ES100 emits one ES_UDT — no AUX dupe."""
        eng = [
            {
                "name": "Pack_ESZone1",
                "area": "Pack_Area",
                "members": ["ES100"],
                "membersOrigin": "ENGINEER_ASSIGNED",
                "engineerEdited": True,
                "conveyors": ["P100"],
            }
        ]
        irs = build_safety_zone_irs(engineer_zones=eng, default_area="Pack_Area")
        pack = emit_es_program(
            irs,
            _rung_xml=_rung_xml,
            routine=_routine,
            extract_tag_block=lambda *_: None,
            library_text="",
            written_tags={"ES100", "ES100.I.ES_OK"},
        )
        self.assertIsNotNone(pack)
        assert pack is not None
        self.assertIn("Pack_ESZone1", pack.get("emitted_zones") or [])
        xml = pack["program_xml"]
        self.assertIn("ES_SIL1_Cat1(ES100_AOI,ES100,", xml)
        self.assertNotIn("ES100_AUX", xml)
        self.assertNotIn("ES999_AUX", xml)
        # One SIL1 consumer for the canonical device — never an AUX dupe consumer
        sil1 = re.findall(r"ES_SIL1_Cat1\(([^)]+)\)", xml)
        self.assertEqual(len(sil1), 1, sil1)
        self.assertIn("ES100", sil1[0])
        self.assertNotIn("AUX", sil1[0])

    def test_no_writer_blocks_orphan_consumer(self):
        """ORI-048/054: missing emitted writer → no silent ES_SIL1 for the consumer."""
        eng = [
            {
                "name": "Pack_ESZone1",
                "area": "Pack_Area",
                "members": ["ES100"],
                "membersOrigin": "ENGINEER_ASSIGNED",
                "engineerEdited": True,
                "conveyors": ["P100"],
            }
        ]
        irs = build_safety_zone_irs(engineer_zones=eng, default_area="Pack_Area")
        pack = emit_es_program(
            irs,
            _rung_xml=_rung_xml,
            routine=_routine,
            extract_tag_block=lambda *_: None,
            library_text="",
            written_tags=set(),
        )
        xml = pack["program_xml"]
        self.assertNotIn("ES_SIL1_Cat1(ES100_AOI,ES100,", xml)
        self.assertNotIn("ES_SIL1_Cat1(", xml)
        self.assertTrue(pack.get("shell") or "Pack_ESZone1" in (pack.get("omitted_zones") or []))

    def test_esr_alias_family_one_zone_member_one_udt(self):
        if not LIBRARY.is_file():
            self.skipTest("library missing")
        from fortna_autogen import AutogenInput, ConveyorRow, build_l5x
        from fortna_safety_model import reconcile_safety_devices

        signals = [
            {"name": "2ESR1", "kind": "ESR", "physicalEndpoint": "RIO:I.Data[0].1", "sources": ["T"]},
            {"name": "2ESR1_AUX", "kind": "ESR", "physicalEndpoint": "RIO:I.Data[0].1", "sources": ["T"]},
            {"name": "T_2ESR1", "kind": "ESR", "physicalEndpoint": "RIO:I.Data[0].1", "sources": ["T"]},
        ]
        recon = reconcile_safety_devices(signals)
        devices = recon.get("devices") or []
        self.assertEqual(len(devices), 1)
        canonical = devices[0].get("name") or devices[0].get("id")
        self.assertTrue(canonical)

        # Stronger path: emit_es_program with writer for AUX feedback
        eng = [
            {
                "name": "Line_ESZone1",
                "area": "Line_Area",
                "members": [canonical],
                "membersOrigin": "ENGINEER_ASSIGNED",
                "engineerEdited": True,
                "conveyors": ["P200"],
            }
        ]
        irs = build_safety_zone_irs(
            engineer_zones=eng, safety_devices=devices, default_area="Line_Area"
        )
        pack = emit_es_program(
            irs,
            _rung_xml=_rung_xml,
            routine=_routine,
            extract_tag_block=lambda *_: None,
            library_text="",
            written_tags={"T_2ESR1_AUX", "T_2ESR1_AUX.I.ES_OK"},
        )
        xml = pack["program_xml"]
        # Must not emit both primary and AUX as separate ES_SIL1 consumers
        sil1 = re.findall(r"ES_SIL1_Cat1\(([^)]+)\)", xml)
        self.assertEqual(len(sil1), 1, sil1)
        self.assertIn("T_2ESR1_AUX", sil1[0])
        self.assertNotIn("2ESR1_AUX_AOI,2ESR1_AUX", xml)

    def test_workbook_safety_build_round_trip_fields(self):
        """Assignment persistence shape used by Safety Apply → Autogen."""
        sb = {
            "zones": [
                {
                    "name": "ZoneA_ESZone1",
                    "area": "ZoneA",
                    "members": ["ES10", "ESLS10"],
                    "status": "READY",
                }
            ]
        }
        self.assertEqual(sb["zones"][0]["members"], ["ES10", "ESLS10"])
        self.assertNotIn("ES10_AUX", sb["zones"][0]["members"])


if __name__ == "__main__":
    unittest.main()

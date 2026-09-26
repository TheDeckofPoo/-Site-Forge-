#!/usr/bin/env python3
"""ORI-042 — canonical SafetyDevice resolves to proven AUX feedback operand."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_es_compiler import (  # noqa: E402
    build_safety_zone_irs,
    emit_es_program,
    resolve_safety_feedback_operand,
)


def _rung_xml(num: int, text: str, comment: str = "") -> str:
    c = f"<Comment><![CDATA[{comment}]]></Comment>" if comment else ""
    return f'<Rung Number="{num}" Type="N">{c}<Text><![CDATA[{text}]]></Text></Rung>'


def _routine(name: str, rungs: list[str]) -> str:
    return (
        f'<Routine Name="{name}" Type="RLL"><RLLContent>'
        f'{"".join(rungs)}</RLLContent></Routine>'
    )


class TestFeedbackOperandResolve(unittest.TestCase):
    def test_esr_aux_with_phys(self) -> None:
        ev = {
            "6ESR1": {
                "name": "6ESR1",
                "signals": [
                    {
                        "name": "6ESR1_AUX",
                        "role": "AUX",
                        "physicalEndpoint": "603.1",
                    },
                    {"name": "T_6ESR1_AUX", "role": "AUX", "physicalEndpoint": "603.1"},
                ],
            }
        }
        fo = resolve_safety_feedback_operand("6ESR1", device_evidence=ev)
        self.assertEqual(fo.status, "RESOLVED")
        self.assertEqual(fo.operand, "T_6ESR1_AUX")

    def test_mcr_aux_plain_no_t_sibling(self) -> None:
        ev = {
            "1MCR1": {
                "name": "1MCR1",
                "signals": [
                    {"name": "1MCR1_AUX", "role": "AUX", "physicalEndpoint": "10.1"},
                ],
            }
        }
        fo = resolve_safety_feedback_operand("1MCR1", device_evidence=ev)
        self.assertEqual(fo.status, "RESOLVED")
        self.assertEqual(fo.operand, "T_1MCR1_AUX")

    def test_t_alias_present(self) -> None:
        ev = {
            "1MCR1": {
                "name": "1MCR1",
                "signals": [
                    {"name": "T_1MCR1", "role": "PRIMARY"},
                    {"name": "T_1MCR1_AUX", "role": "AUX", "physicalEndpoint": "1.2"},
                ],
            }
        }
        fo = resolve_safety_feedback_operand("1MCR1", device_evidence=ev)
        self.assertEqual(fo.operand, "T_1MCR1_AUX")

    def test_member_already_aux(self) -> None:
        fo = resolve_safety_feedback_operand("6ESR1_AUX", device_evidence={})
        self.assertEqual(fo.status, "RESOLVED")
        self.assertEqual(fo.operand, "T_6ESR1_AUX")

    def test_missing_feedback_review_not_invented(self) -> None:
        fo = resolve_safety_feedback_operand("6ESR1", device_evidence={})
        self.assertEqual(fo.status, "REVIEW_REQUIRED")
        self.assertEqual(fo.operand, "")
        fo2 = resolve_safety_feedback_operand("1MCR1", device_evidence={})
        self.assertEqual(fo2.status, "REVIEW_REQUIRED")
        self.assertEqual(fo2.operand, "")

    def test_emit_uses_feedback_not_bare_canonical(self) -> None:
        devs = [
            {
                "name": "6ESR1",
                "signals": [
                    {"name": "6ESR1_AUX", "role": "AUX", "physicalEndpoint": "603.1"},
                ],
            }
        ]
        eng = [
            {
                "name": "Zone1",
                "area": "Area1",
                "members": ["6ESR1"],
                "membersOrigin": "ENGINEER_ASSIGNED",
                "engineerEdited": True,
                "conveyors": ["P100"],
            }
        ]
        irs = build_safety_zone_irs(
            engineer_zones=eng, safety_devices=devs, default_area="Area1"
        )
        self.assertEqual(irs[0].members, ["T_6ESR1"])  # canonical preserved
        pack = emit_es_program(
            irs,
            _rung_xml=_rung_xml,
            routine=_routine,
            extract_tag_block=lambda *_: None,
            library_text="",
        )
        xml = pack["program_xml"]
        self.assertIn("T_6ESR1_AUX", xml)
        self.assertNotIn("ES_SIL1_Cat1(T_6ESR1_AOI,T_6ESR1,", xml)


class TestCanonicalMcrMembershipPreserved(unittest.TestCase):
    def test_bare_mcr_not_silently_dropped(self) -> None:
        eng = [
            {
                "name": "Zone1",
                "area": "Area1",
                "members": ["CP2_MCR1", "T_2MCR1", "4ES"],
                "membersOrigin": "ENGINEER_ASSIGNED",
                "engineerEdited": True,
                "conveyors": ["P1"],
            }
        ]
        # No feedback evidence → members preserved, emit uses only ESTOP
        irs = build_safety_zone_irs(engineer_zones=eng, default_area="Area1")
        names = set(irs[0].members)
        self.assertIn("CP2_MCR1", names)
        self.assertIn("T_2MCR1", names)
        self.assertIn("T_4ES", names)
        self.assertEqual(len(irs[0].members), 3)

    def test_mcr_with_aux_evidence_emits_feedback(self) -> None:
        eng = [
            {
                "name": "Zone1",
                "area": "Area1",
                "members": ["CP2_MCR1"],
                "membersOrigin": "ENGINEER_ASSIGNED",
                "engineerEdited": True,
                "conveyors": ["P1"],
            }
        ]
        devs = [
            {
                "name": "CP2_MCR1",
                "signals": [
                    {"name": "CP2_MCR1_AUX", "role": "AUX", "physicalEndpoint": "9.1"},
                ],
            }
        ]
        irs = build_safety_zone_irs(
            engineer_zones=eng, safety_devices=devs, default_area="Area1"
        )
        self.assertIn("CP2_MCR1", irs[0].members)
        self.assertEqual(irs[0].emit_ready_operands(), ["CP2_MCR1_AUX"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

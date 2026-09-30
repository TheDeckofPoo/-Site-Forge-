#!/usr/bin/env python3
"""ORI-092: report writer coverage and function disclosure match the L5X artifact."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_autogen import (  # noqa: E402
    _classify_mapped_output_writers,
    _derive_function_disclosure_from_l5x,
    propose_generic_safety_zone_candidate,
)
from fortna_equipment_binding import (  # noqa: E402
    choose_conveyor_run_tag,
    resolve_motor_section_owner,
)


class TestOri092ReportArtifactTruth(unittest.TestCase):
    def test_withheld_fast_conv_not_valid_writer(self) -> None:
        l5x = """
        <Program Name="Area_Fast"><Routines>
        <Routine Name="Conv_Fast"><RLLContent>
        <Comment><![CDATA[PARTIAL BUILD — Fast_Conv withheld (PD-0003): Safety Zone unresolved]]></Comment>
        <Text><![CDATA[NOP();]]></Text>
        </RLLContent></Routine>
        <Routine Name="Conv_Jam"><RLLContent>
        <Text><![CDATA[Slow_Jam(P1_Conv_AOI.Jam,P1_Conv,Area,NO_PE,NO_PE,NO_PE,NO_PE,NO_PE);]]></Text>
        </RLLContent></Routine>
        </Routines></Program>
        """
        cov = _classify_mapped_output_writers(
            mapped_output_tags=["P1_Conv", "M120"],
            l5x_text=l5x,
        )
        self.assertEqual(cov["by_class"]["VALID_WRITER"], [])
        self.assertIn("P1_Conv", cov["by_class"]["INTENTIONALLY_UNDRIVEN_REVIEW"])
        self.assertTrue(cov["fast_conv_withheld"])
        self.assertEqual(cov["outputs_with_valid_writers"], 0)

        disc = _derive_function_disclosure_from_l5x(
            l5x,
            {
                "slow_flt_status": "REVIEW_REQUIRED",
                "slow_flt_provenance": "FINISHED_SITE_DERIVED_SUSPECT",
            },
        )
        self.assertEqual(disc["Fast_Conv"]["status"], "REVIEW_WITHHELD")
        self.assertEqual(disc["Conv_PI"]["status"], "REVIEW_WITHHELD")
        self.assertEqual(disc["Slow_Flt"]["status"], "UNSUPPORTED_BETA_FUNCTION")

    def test_live_fast_conv_counts_as_writer(self) -> None:
        l5x = """
        <Text><![CDATA[Fast_Conv(P1_Conv,NO_PE,NO_PE,Zone1);]]></Text>
        """
        cov = _classify_mapped_output_writers(
            mapped_output_tags=["P1_Conv"],
            l5x_text=l5x,
        )
        self.assertEqual(cov["by_class"]["VALID_WRITER"], ["P1_Conv"])
        self.assertTrue(cov["fast_conv_live"])

    def test_m120_unique_proven_run_owner(self) -> None:
        sm = {
            "sections": {
                "P120A": {
                    "motor": "M120",
                    "confidence": "PROVEN_CROSS_TABLE",
                    "provenance": [{"kind": "mtrchain_p", "motor": "M120"}],
                },
                "P120C": {
                    "motor": "M120",
                    "confidence": "PROVEN_RUN",
                    "provenance": [
                        {"kind": "conveyor_asc", "confidence": "PROVEN_RUN"},
                        {"kind": "mtrchain_p", "motor": "M120"},
                    ],
                },
            }
        }
        owner, conf, reason = resolve_motor_section_owner(
            motor_name="M120",
            stem="120",
            known_convs={"P120A", "P120C"},
            section_model=sm,
        )
        self.assertEqual(owner, "P120C")
        self.assertEqual(conf, "PROVEN")
        self.assertIn("P120C", reason)
        tag, tconf, _ = choose_conveyor_run_tag(
            "120",
            known_convs={"P120A", "P120C"},
            section_model=sm,
            motor_name="M120",
        )
        self.assertEqual(tag, "P120C_Conv")
        self.assertEqual(tconf, "PROVEN")

    def test_ambiguous_motor_review(self) -> None:
        sm = {
            "sections": {
                "P120A": {
                    "motor": "M120",
                    "confidence": "PROVEN_RUN",
                    "provenance": [{"kind": "conveyor_asc", "motor": "M120"}],
                },
                "P120C": {
                    "motor": "M120",
                    "confidence": "PROVEN_RUN",
                    "provenance": [{"kind": "conveyor_asc", "motor": "M120"}],
                },
            }
        }
        owner, conf, reason = resolve_motor_section_owner(
            motor_name="M120",
            known_convs={"P120A", "P120C"},
            section_model=sm,
        )
        self.assertEqual(owner, "")
        self.assertEqual(conf, "REVIEW_REQUIRED")
        self.assertIn("AMBIGUOUS", reason)

    def test_safety_candidate_requires_confirm(self) -> None:
        cand = propose_generic_safety_zone_candidate(
            machine="MSCRENOPICK",
            safety_devices=[
                {
                    "name": "ESPB2",
                    "machine": "MSCRENOPICK",
                    "assignable": True,
                    "physicalEndpoint": "AENTR3:I.Data[4].6",
                    "safety_role": "FEEDBACK",
                    "sources": ["ESTOP_TABLE"],
                    "confidence": "REVIEW_REQUIRED",
                    "inventory_scope": "LOCAL_PHYSICAL",
                },
                {
                    "name": "FOREIGN_ES",
                    "machine": "OTHER",
                    "assignable": True,
                    "physicalEndpoint": "1.1",
                    "safety_role": "FEEDBACK",
                    "sources": ["ESTOP_TABLE"],
                },
            ],
            areas=["MSCRENOPICK_Area"],
            conveyors=[{"conveyor": "P1"}],
            engineer_zones=[],
        )
        self.assertEqual(cand["status"], "CANDIDATE")
        self.assertTrue(cand["engineer_confirmation_required"])
        self.assertFalse(cand.get("auto_confirm"))
        self.assertEqual(cand["candidate"]["name"], "MSCRENOPICK_ESZone1")
        self.assertEqual(cand["candidate"]["members"], ["ESPB2"])
        self.assertEqual(cand["candidate"]["membership_count"], 1)

    def test_enable_chain_includes_non_assignable_peer(self) -> None:
        """PICKING_ENABLE Logic.asc peers stay in candidate even if WORD_ONLY."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            fortna = Path(td) / "FORTNA"
            fortna.mkdir()
            (fortna / "Logic.asc").write_text(
                'IF part named ESPB2 E-STOP IS OFF ~AND  IF part named ESPB32 IS OFF '
                '~AND  IF part named ESLS2 PULL CORD IS OFF ~AND  IF part named ESPB24 '
                'IS OFF ~THEN ~TURN ON part named PICKING_ENABLE   at I/O address 151/10\n',
                encoding="utf-8",
            )
            cand = propose_generic_safety_zone_candidate(
                machine="MSCRENOPICK",
                run_dir=td,
                safety_devices=[
                    {
                        "name": n,
                        "machine": "MSCRENOPICK",
                        "assignable": n != "ESLS2",
                        "physicalEndpoint": "1142.13" if n == "ESLS2" else "AENTR1:I.Data[0].0",
                        "safety_role": "FEEDBACK",
                        "sources": ["ESTOP_TABLE", "LOGIC"],
                        "confidence": "REVIEW_REQUIRED",
                        "inventory_scope": "LOCAL_PHYSICAL",
                        "review_reason": "WORD_ONLY_EVIDENCE" if n == "ESLS2" else None,
                        "kind": "ESLS" if n == "ESLS2" else "ESTOP",
                    }
                    for n in ("ESPB2", "ESPB24", "ESPB32", "ESLS2")
                ],
                areas=["MSCRENOPICK_Area"],
                conveyors=[{"conveyor": "P1"}],
                engineer_zones=[],
            )
        self.assertEqual(cand["status"], "CANDIDATE")
        self.assertEqual(cand["candidate"]["membership_count"], 4)
        self.assertEqual(
            set(cand["candidate"]["members"]),
            {"ESPB2", "ESPB24", "ESPB32", "ESLS2"},
        )
        blocked = {
            x["device"] for x in cand["candidate"]["assignment_blocked_members"]
        }
        self.assertEqual(blocked, {"ESLS2"})
        self.assertIn("ESLS2", cand["candidate"]["members"])


if __name__ == "__main__":
    unittest.main()

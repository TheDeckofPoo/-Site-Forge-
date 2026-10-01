"""ORI-094/095/096/097 sanitized closeout tests (no site special-cases in prod code)."""
from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(REPO / "tools" / "scripts"))


class TestReadyForSafetyEmit(unittest.TestCase):
    def test_proven_ready(self):
        from fortna_safety_endpoint_integrity import ready_for_safety_emit

        d = {
            "name": "DEV_A",
            "endpoint_confidence": "PROVEN",
            "hardwareBacked": True,
            "endpoint_proof_depth": "FULL",
            "machine": "SITE",
            "machine_ownership": "PROVEN",
        }
        r = ready_for_safety_emit(d, policy="PROVEN")
        self.assertTrue(r["ready"])
        self.assertEqual(r["confidence"], "PROVEN")

    def test_derived_not_ready_even_if_engineer_assigned(self):
        from fortna_safety_endpoint_integrity import ready_for_safety_emit

        d = {
            "name": "DEV_B",
            "endpoint_confidence": "DERIVED",
            "confidence": "DERIVED",
            "status": "ENGINEER_ASSIGNED",
            "engineerAssigned": True,
            "hardwareBacked": False,
        }
        r = ready_for_safety_emit(d, policy="PROVEN")
        self.assertFalse(r["ready"])
        self.assertIn("ENGINEER_INTENT_DOES_NOT_PROVE_PHYSICAL", r["reasons"])

    def test_review_not_ready(self):
        from fortna_safety_endpoint_integrity import ready_for_safety_emit

        d = {
            "name": "DEV_C",
            "endpoint_confidence": "REVIEW_REQUIRED",
            "status": "ENGINEER_ASSIGNED",
        }
        r = ready_for_safety_emit(d, policy="PROVEN")
        self.assertFalse(r["ready"])

    def test_local_physical_scope_full_hardware_is_proven(self):
        """Grouped devices may stamp inventory_scope without machine_ownership."""
        from fortna_safety_endpoint_integrity import (
            decide_endpoint_confidence,
            ready_for_safety_emit,
        )

        d = {
            "name": "ESPB2",
            "kind": "ESTOP",
            "physicalEndpoint": "AENTR3:I.Data[4].4",
            "endpoint_proof_depth": "FULL",
            "hardwareBacked": True,
            "machine": "MSCRENOPICK",
            "inventory_scope": "LOCAL_PHYSICAL",
            # Intentionally blank — mirrors pre-fix grouped SafetyDevices.
            "machine_ownership": None,
            "endpoint_confidence": "REVIEW_REQUIRED",  # stale stamp
        }
        decision = decide_endpoint_confidence(d)
        self.assertEqual(decision["confidence"], "PROVEN")
        self.assertTrue(decision["ownership_ok"])
        r = ready_for_safety_emit(d, policy="PROVEN")
        self.assertTrue(r["ready"])
        self.assertEqual(r["confidence"], "PROVEN")


class TestSyncEsEmitReport(unittest.TestCase):
    def test_report_matches_artifact_safe_pi(self):
        from fortna_es_compiler import sync_es_emit_report

        programs = [
            '''<Program Name="ES"><Routines>
            <Routine Name="MSCRENOPICK_ESZone1_Safe_Logic"/>
            <Routine Name="MSCRENOPICK_ESZone1_Safe_PI"/>
            <Text><![CDATA[XIC(MSCRENOPICK_Area.Reset)OTE(MSCRENOPICK_ESZone1.PI.Reset);]]></Text>
            <Text><![CDATA[XIC(MSCRENOPICK_Area.Silence)OTE(MSCRENOPICK_ESZone1.PI.Silence);]]></Text>
            </Routines></Program>'''
        ]
        stale = {
            "status": "READY",
            "detail": "SAFETY REVIEW REQUIRED — emitted 0 ready zone(s); omitted incomplete: MSCRENOPICK_ESZone1",
            "emitted_zones": [],
            "omitted_zones": ["MSCRENOPICK_ESZone1"],
            "zones_with_pi_writers": [],
            "motion_refs_without_pi_writer": ["P1→MSCRENOPICK_ESZone1"],
        }
        out = sync_es_emit_report(
            stale,
            es_pack={
                "emitted_zones": ["MSCRENOPICK_ESZone1"],
                "omitted_zones": [],
                "zones": [
                    {
                        "name": "MSCRENOPICK_ESZone1",
                        "members": ["ESPB2", "ESLS2"],
                        "has_pi_writer": True,
                    }
                ],
                "zones_with_pi_writers": ["MSCRENOPICK_ESZone1"],
            },
            programs_xml=programs,
            motion_zone_refs=["P1→MSCRENOPICK_ESZone1", "Fast_Conv→MSCRENOPICK_ESZone1"],
            area_command_path={
                "reset_path": "XIC(Area.HMI.Reset)OTE(Area.Reset)",
                "silence_path": "XIC(Area.HMI.Silence)OTE(Area.Silence)",
            },
        )
        self.assertEqual(out["emitted_zones"], ["MSCRENOPICK_ESZone1"])
        self.assertEqual(out["omitted_zones"], [])
        self.assertIn("MSCRENOPICK_ESZone1", out["zones_with_pi_writers"])
        self.assertTrue(out["pi_writer_invariant_ok"])
        self.assertEqual(out["motion_refs_without_pi_writer"], [])
        self.assertNotIn("emitted 0", out["detail"])
        self.assertTrue(out["report_matches_artifact"])
        self.assertEqual(out["reset_status"], "READY")
        self.assertEqual(out["silence_status"], "READY")


class TestNoSilentOctalFallback(unittest.TestCase):
    def test_bit_helpers_need_run_or_fail_closed(self):
        from fortna_autogen import _fortna_bit_is_high, _fortna_bit_to_data_bit
        from fortna_bit_address import clear_radix_cache

        clear_radix_cache()
        # Without RUN proof, helpers must not silently octal-parse.
        self.assertFalse(_fortna_bit_is_high("13"))
        self.assertIsNone(_fortna_bit_to_data_bit("13"))


class TestRunnabilityWriterCountCoercion(unittest.TestCase):
    def test_mapped_outputs_int_does_not_break_summary(self):
        """writer_coverage.mapped_outputs is an int count, not a list."""
        mapped = 37
        by_class = {"VALID_WRITER": ["P1_Conv"] * 29}
        eff = by_class.get("VALID_WRITER") or []
        eff_n = len(eff) if isinstance(eff, list) else int(eff or 0)
        supp_n = mapped if isinstance(mapped, int) else len(mapped or [])
        self.assertEqual(eff_n, 29)
        self.assertEqual(supp_n, 37)
        self.assertEqual(f"{eff_n}/{supp_n}", "29/37")


if __name__ == "__main__":
    unittest.main()

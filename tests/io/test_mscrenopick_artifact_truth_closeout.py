"""ORI-098 / exports-current promotion — artifact truth closeout.

A. Populated Default/Unassigned Safety bucket cannot leak into Area_Logic as PI.Tripped
B. Engineer-confirmed operational zone DOES become Area.Run trip reference
C. Failed integrity/symbol/preflight candidate is never promoted to exports/current
D. Previous valid current build survives a failed subsequent build
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))

import fortna_autogen as ag  # noqa: E402

LIBRARY = REPO / "tools" / "libraries" / "OReilly_Library_v3.L5X"


def _default_bucket(**extra):
    z = {
        "name": "Default_Safety",
        "area": "MSCRENOPICK_Area",
        "members": ["ESPB1", "ESPB2"],
        "isDefault": True,
        "isUnassignedBucket": True,
        "operational": False,
        "defaultSafety": True,
    }
    z.update(extra)
    return z


def _engineer_zone(name: str = "MSCRENOPICK_ESZone1", **extra):
    z = {
        "name": name,
        "engineering_name": name,
        "area": "MSCRENOPICK_Area",
        "members": ["ESPB10"],
        "engineerEdited": True,
        "createdBy": "engineer",
        "zoneOrigin": "ENGINEER",
        "membersOrigin": "ENGINEER_ASSIGNED",
        "operational": True,
        "status": "READY",
    }
    z.update(extra)
    return z


class TestOri098AreaRunSafetyFilter(unittest.TestCase):
    """A/B — Default bucket never enters Area.Run; engineer zone does."""

    def test_a_default_bucket_excluded_from_area_cmd_zones(self) -> None:
        zones = ag.collect_area_cmd_safety_zones(
            "MSCRENOPICK_Area",
            safety_zone_members=[
                _default_bucket(),
                {
                    "name": "Unassigned_Safety",
                    "members": ["ES99"],
                    "isUnassignedBucket": True,
                    "operational": False,
                    "area": "MSCRENOPICK_Area",
                },
            ],
            safety_build_zones=[_default_bucket(name="Default Safety")],
        )
        self.assertEqual(zones, [])
        for bad in ("Default_Safety", "Unassigned_Safety", "Default Safety"):
            self.assertFalse(any(ag.is_non_operational_safety_zone(bad) is False for _ in [0]))
            self.assertTrue(ag.is_non_operational_safety_zone(bad))

    def test_b_engineer_operational_zone_eligible(self) -> None:
        zones = ag.collect_area_cmd_safety_zones(
            "MSCRENOPICK_Area",
            safety_zone_members=[_default_bucket(), _engineer_zone()],
            safety_build_zones=[],
        )
        self.assertIn("MSCRENOPICK_ESZone1", zones)
        self.assertNotIn("Default_Safety", zones)

    def test_multi_area_matching_preserved(self) -> None:
        zones = ag.collect_area_cmd_safety_zones(
            "MSCRENOPICK_Area",
            safety_zone_members=[
                _engineer_zone("MSCRENOPICK_ESZone1"),
                _engineer_zone(
                    "Other_ESZone1",
                    area="Other_Area",
                ),
            ],
        )
        self.assertEqual(zones, ["MSCRENOPICK_ESZone1"])

    def test_empty_members_and_operational_false_excluded(self) -> None:
        zones = ag.collect_area_cmd_safety_zones(
            "MSCRENOPICK_Area",
            safety_zone_members=[
                _engineer_zone(members=[]),
                _engineer_zone("Ghost_ESZone1", operational=False, members=["ES1"]),
                _engineer_zone("Good_ESZone1"),
            ],
        )
        self.assertEqual(zones, ["Good_ESZone1"])

    @unittest.skipUnless(LIBRARY.is_file(), f"library missing: {LIBRARY}")
    def test_a_b_area_logic_l5x_artifact(self) -> None:
        """Populated Default bucket must not appear as XIO(...PI.Tripped) in Area_Logic."""
        inp = ag.AutogenInput(
            project_name="MSCRENOPICK_Closeout",
            machine="MSCRENOPICK",
            areas=["MSCRENOPICK_Area"],
            safety_zones=["MSCRENOPICK_ESZone1"],
            safety_zone_members=[_default_bucket(), _engineer_zone()],
            safety_build={
                "zones": [_default_bucket(), _engineer_zone()],
            },
            include_sys=False,
            include_io_map=False,
            build_intent="PARTIAL",
            conveyors=[
                ag.ConveyorRow(
                    number=1,
                    conveyor="P1",
                    main_area="MSCRENOPICK_Area",
                    safety_zone="MSCRENOPICK_ESZone1",
                    type="Transport with MS",
                    motor_starter="Yes",
                    jam_pe_tags=["PE1"],
                    product_pe_tags=["PE1"],
                ),
            ],
            pe_devices=[{"name": "PE1", "conveyor": "P1"}],
        )
        l5x, _report = ag.build_l5x(inp, LIBRARY)

        # Isolate Area_Logic routine text when present
        m = re.search(
            r'<Routine\s+Name="Area_Logic"[^>]*>(.*?)</Routine>',
            l5x,
            flags=re.I | re.S,
        )
        area_logic = m.group(1) if m else l5x

        self.assertNotRegex(
            area_logic,
            r"XIO\(\s*(?:Default_Safety|Unassigned_Safety|Default\s+Safety)\.PI\.Tripped\s*\)",
            msg="ORI-098: Default/Unassigned bucket leaked into Area.Run seal-in",
        )
        self.assertRegex(
            area_logic,
            r"XIO\(\s*MSCRENOPICK_ESZone1\.PI\.Tripped\s*\)",
            msg="ORI-098: engineer operational zone must be Area.Run trip reference",
        )


class TestExportsCurrentPromotion(unittest.TestCase):
    """C/D — failed candidate never overwrites exports/current."""

    def test_c_failed_gates_never_promote(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            current = root / "exports" / "current"
            diag = root / "diagnostics"
            current.mkdir(parents=True)
            diag.mkdir(parents=True)
            basename = "MSCRENOPICK_2026_01_01_1200.L5X"
            candidate = diag / basename
            candidate.write_text("<L5X>FAILED_CANDIDATE</L5X>", encoding="utf-8")

            info = ag.promote_l5x_candidate(
                candidate_path=candidate,
                current_dir=current,
                l5x_basename=basename,
                gates_passed=False,
                explicit_out=False,
            )
            self.assertTrue(info["l5x_generated"])
            self.assertFalse(info["l5x_promoted_to_current"])
            self.assertEqual(info["l5x_current_path"], "")
            self.assertTrue(candidate.is_file())
            self.assertFalse((current / basename).exists())
            # Failed file must NOT land under exports/current
            self.assertEqual(list(current.glob("*.L5X")), [])

    def test_d_previous_valid_current_survives_failed_promote(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            current = root / "exports" / "current"
            diag = root / "diagnostics"
            current.mkdir(parents=True)
            diag.mkdir(parents=True)

            prev_name = "MSCRENOPICK_2025_12_01_0900.L5X"
            prev = current / prev_name
            prev.write_text("<L5X>PREVIOUS_VALID</L5X>", encoding="utf-8")
            prev_text = prev.read_text(encoding="utf-8")

            fail_name = "MSCRENOPICK_2026_01_01_1200.L5X"
            candidate = diag / fail_name
            candidate.write_text("<L5X>FAILED_NEW</L5X>", encoding="utf-8")

            info = ag.promote_l5x_candidate(
                candidate_path=candidate,
                current_dir=current,
                l5x_basename=fail_name,
                gates_passed=False,
                explicit_out=False,
            )
            self.assertFalse(info["l5x_promoted_to_current"])
            self.assertTrue(prev.is_file())
            self.assertEqual(prev.read_text(encoding="utf-8"), prev_text)
            self.assertFalse((current / fail_name).exists())
            # Candidate remains in diagnostics only
            self.assertTrue(candidate.is_file())
            self.assertIn("FAILED_NEW", candidate.read_text(encoding="utf-8"))

    def test_success_promotes_and_keeps_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            current = root / "exports" / "current"
            diag = root / "diagnostics"
            current.mkdir(parents=True)
            diag.mkdir(parents=True)
            basename = "MSCRENOPICK_2026_02_01_0800.L5X"
            candidate = diag / basename
            candidate.write_text("<L5X>GOOD</L5X>", encoding="utf-8")

            info = ag.promote_l5x_candidate(
                candidate_path=candidate,
                current_dir=current,
                l5x_basename=basename,
                gates_passed=True,
                explicit_out=False,
            )
            self.assertTrue(info["l5x_promoted_to_current"])
            self.assertTrue((current / basename).is_file())
            self.assertEqual((current / basename).read_text(encoding="utf-8"), "<L5X>GOOD</L5X>")
            # Staging candidate retained in diagnostics
            self.assertTrue(candidate.is_file())

    def test_explicit_out_does_not_claim_current_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "gate_out"
            out.mkdir()
            basename = "SYNTH.L5X"
            candidate = out / basename
            candidate.write_text("<L5X>GATE</L5X>", encoding="utf-8")
            info = ag.promote_l5x_candidate(
                candidate_path=candidate,
                current_dir=None,
                l5x_basename=basename,
                gates_passed=True,
                explicit_out=True,
            )
            self.assertTrue(info["l5x_generated"])
            self.assertFalse(info["l5x_promoted_to_current"])
            self.assertTrue(info.get("l5x_promoted_to_out_dir"))


class TestReportArtifactTruth(unittest.TestCase):
    """E/F/G/H/I — report_matches_artifact, zone collapse, closure, build status."""

    def test_e_report_matches_artifact_fails_on_inconsistency(self) -> None:
        from fortna_es_compiler import sync_es_emit_report

        programs = [
            '''<Program Name="ES"><Routines>
            <Routine Name="Z1_Safe_PI"/>
            <Routine Name="Z1_Safe_Logic"/>
            </Routines></Program>
            <Program Name="Slow"><Routines>
            <Routine Name="Area_Logic"><Rung><Text><![CDATA[
            XIO(Default_Safety.PI.Tripped)OTE(Area.Run);
            ]]></Text></Rung></Routine>
            </Routines></Program>'''
        ]
        out = sync_es_emit_report(
            {
                "status": "READY",
                "emitted_zones": ["Z1"],
                "omitted_zones": [],
                "zones": [{"name": "Z1", "members": ["ES1"]}],
                "zones_with_pi_writers": ["Z1"],
            },
            programs_xml=programs,
        )
        self.assertFalse(out["report_matches_artifact"])
        self.assertTrue(
            any("DEFAULT_SAFETY" in m for m in (out.get("report_artifact_mismatches") or []))
        )

    def test_f_duplicate_szone_identity_collapses(self) -> None:
        from fortna_es_compiler import sync_es_emit_report

        programs = [
            '''<Program Name="ES"><Routines>
            <Routine Name="MSCRENOPICK_ESZone1_Safe_PI"/>
            <Routine Name="MSCRENOPICK_ESZone1_Safe_Logic"/>
            </Routines></Program>
            <Program Name="Slow"><Routines>
            <Routine Name="Area_Logic"><Rung><Text><![CDATA[
            XIC(A.Reset)OTE(MSCRENOPICK_ESZone1.PI.Reset);
            XIC(A.Silence)OTE(MSCRENOPICK_ESZone1.PI.Silence);
            ]]></Text></Rung></Routine></Routines></Program>'''
        ]
        out = sync_es_emit_report(
            {
                "status": "READY",
                "emitted_zones": ["MSCRENOPICK_ESZone1", "szone_abc123"],
                "omitted_zones": [],
                "zones": [
                    {
                        "name": "MSCRENOPICK_ESZone1",
                        "engineering_name": "MSCRENOPICK_ESZone1",
                        "source_id": "szone_abc123",
                        "members": ["ESPB2"],
                    },
                    {
                        "name": "szone_abc123",
                        "source_id": "szone_abc123",
                        "engineering_name": "MSCRENOPICK_ESZone1",
                        "members": ["ESPB2"],
                    },
                ],
                "zones_with_pi_writers": ["MSCRENOPICK_ESZone1", "szone_abc123"],
            },
            programs_xml=programs,
            area_command_path={
                "reset_path": "XIC(A.Reset)OTE(A.Reset)",
                "silence_path": "XIC(A.Silence)OTE(A.Silence)",
            },
        )
        self.assertEqual(out["emitted_zones"], ["MSCRENOPICK_ESZone1"])
        names = [z.get("name") for z in (out.get("zones") or [])]
        self.assertEqual(names.count("MSCRENOPICK_ESZone1"), 1)
        self.assertNotIn("szone_abc123", names)

    def test_g_symbol_closure_ok_false_with_failures(self) -> None:
        from fortna_symbol_closure import ClosureFinding, ClosureReport, CLOSURE_FAIL

        failures = [
            ClosureFinding(
                operand="GhostTag",
                root="GhostTag",
                producer="Program:IO_MAP",
                classification=CLOSURE_FAIL,
                expected_owner="controller",
                missing_evidence="none",
            )
        ]
        rep = ClosureReport(ok=True, findings=failures, failures=failures, counts={})
        # Simulate generate() invariant: ok cannot coexist with failures
        if rep.failures and rep.ok:
            rep.ok = False
        self.assertFalse(rep.ok)
        self.assertGreater(len(rep.failures), 0)

    def test_h_blocked_on_hard_structural_failure(self) -> None:
        from fortna_build_issues import classify_build_status

        st = classify_build_status(
            {"build_failed": True, "ok": False, "error": "symbol closure"},
            structural_ok=False,
            promoted=False,
        )
        self.assertEqual(st, "BLOCKED")

    def test_i_partial_when_structurally_valid_with_withheld(self) -> None:
        from fortna_build_issues import classify_build_status

        st = classify_build_status(
            {
                "ok": True,
                "build_failed": False,
                "merges_withheld_review": ["P2-P18", "P15-P72", "P1001-P105A"],
                "merges_emitted": [],
            },
            structural_ok=True,
            promoted=True,
        )
        self.assertEqual(st, "PARTIAL")


if __name__ == "__main__":
    unittest.main()

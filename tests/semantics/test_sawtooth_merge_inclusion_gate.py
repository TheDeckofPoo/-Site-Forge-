#!/usr/bin/env python3
"""GATE C — Sawtooth_Merge inclusion requires target-machine lineage.

Positive: Sawtooth evidence / engineer config on target equipment → included
Negative: ordinary 2→1 merge only → NOT included
Scope: Sawtooth elsewhere in site (outside target machine) → NOT included

Also guards PLC4-class properly configured builds remain allowed.
"""
from __future__ import annotations
# --- siteforge test path bootstrap (cleanup) ---
from pathlib import Path as _SFPath
import sys as _SFSys
_SF_REPO = _SFPath(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / 'tools' / 'scripts'
if str(_SF_SCRIPTS) not in _SFSys.path:
    _SFSys.path.insert(0, str(_SF_SCRIPTS))
# Prefer canonical names used by existing tests:
SCRIPTS = _SF_SCRIPTS
ROOT = _SF_REPO
REPO_ROOT = _SF_REPO
# --- end bootstrap ---


import sys
import unittest
from pathlib import Path

SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from fortna_autogen import (  # noqa: E402
    AutogenInput,
    ConveyorRow,
    apply_sawtooth_merge_inclusion_gate,
    evaluate_sawtooth_merge_inclusion,
    ptag_from_sawtooth_token,
    resolve_program_exports,
    sawtooth_build_is_configured,
    sawtooth_equipment_refs_from_build,
    target_machine_equipment_ptags,
)


def _conv(tag: str, area: str = "Area1") -> ConveyorRow:
    return ConveyorRow(number=1, conveyor=tag, main_area=area, type="Transport with MS")


class TestPtagFromSawtoothToken(unittest.TestCase):
    def test_tokens(self) -> None:
        self.assertEqual(ptag_from_sawtooth_token("P414"), "P414")
        self.assertEqual(ptag_from_sawtooth_token("VFD520_AUX"), "P520")
        self.assertEqual(ptag_from_sawtooth_token("PE516_P"), "P516")
        self.assertEqual(ptag_from_sawtooth_token("LANE_0_P219"), "P219")
        self.assertEqual(ptag_from_sawtooth_token("INVALID"), "")


class TestSawtoothInclusionPositive(unittest.TestCase):
    """actual Sawtooth evidence for target machine → included"""

    def test_engineer_build_scoped_to_target_allows_pack(self) -> None:
        inp = AutogenInput(
            project_name="Test_PLC4like",
            machine="TESTPLC4",
            conveyors=[_conv("P414"), _conv("P219"), _conv("P116")],
            include_programs=["Devices_Comm", "Sawtooth_Merge"],
            sawtooth_build={
                "collector_conveyor": "P414",
                "lanes": [
                    {"conveyor": "P219", "pe": "PE219_P"},
                    {"conveyor": "P116", "pe": "PE116_P"},
                ],
            },
        )
        self.assertTrue(sawtooth_build_is_configured(inp.sawtooth_build))
        decision = apply_sawtooth_merge_inclusion_gate(inp)
        self.assertTrue(decision["allowed"], decision)
        self.assertFalse(decision["stripped"], decision)
        self.assertIn("Sawtooth_Merge", inp.include_programs)
        self.assertEqual(decision["reason"], "engineer_sawtooth_build_scoped_to_target")
        gold = resolve_program_exports(inp.include_programs, include_sys=False)
        self.assertIn("Sawtooth_Merge", [g["name"] for g in gold])


class TestSawtoothInclusionNegative(unittest.TestCase):
    """ordinary 2→1 merge only → NOT included"""

    def test_ordinary_merge_topology_does_not_include_sawtooth(self) -> None:
        inp = AutogenInput(
            project_name="Test_Shipping",
            machine="TESTSHIP",
            conveyors=[_conv("P406"), _conv("P404"), _conv("P138")],
            include_programs=["Devices_Comm", "Sawtooth_Merge"],
            merges_2to1=[
                {
                    "name": "P406",
                    "lane_a": "P404",
                    "lane_b": "P138",
                    "discharge": "P406",
                    "suggested_aoi": "Merge_2to1",
                    "source": "transport_build_graph",
                }
            ],
            sawtooth_build={},
        )
        decision = apply_sawtooth_merge_inclusion_gate(inp)
        self.assertFalse(decision["allowed"], decision)
        self.assertTrue(decision["stripped"], decision)
        self.assertNotIn("Sawtooth_Merge", inp.include_programs)
        self.assertEqual(decision["reason"], "ordinary_merge_topology_is_not_sawtooth")
        gold = resolve_program_exports(inp.include_programs, include_sys=False)
        self.assertNotIn("Sawtooth_Merge", [g["name"] for g in gold])


class TestSawtoothInclusionScope(unittest.TestCase):
    """Sawtooth elsewhere in site outside target machine → NOT included"""

    def test_out_of_scope_collector_does_not_include_pack(self) -> None:
        # Target owns shipping conveyors; workbook still carries CP5-area sawtooth
        inp = AutogenInput(
            project_name="Test_CP6_Shipping",
            machine="TESTCP6",
            conveyors=[_conv("P600"), _conv("P602"), _conv("P704A")],
            include_programs=["Devices_Comm", "System", "Sawtooth_Merge", "Sorter_Track"],
            sawtooth_build={
                "collector_conveyor": "P520",
                "downstream_conveyor": "P522",
                "lanes": [
                    {"conveyor": "", "pe": "PE516_P", "drive": "VFD516_EN", "motor": "VFD520_AUX"},
                    {"conveyor": "", "pe": "PE140_P", "drive": "VFD140_EN", "motor": "VFD520_AUX"},
                ],
                "discovery_source": "site_model",
            },
            merges_2to1=[
                {
                    "name": "P602",
                    "lane_a": "P600",
                    "lane_b": "P704A",
                    "discharge": "P602",
                    "suggested_aoi": "Merge_2to1",
                }
            ],
        )
        equip = target_machine_equipment_ptags(inp)
        self.assertIn("P600", equip)
        self.assertNotIn("P520", equip)
        refs = sawtooth_equipment_refs_from_build(inp.sawtooth_build)
        self.assertIn("P520", refs)
        self.assertTrue(sawtooth_build_is_configured(inp.sawtooth_build))

        decision = apply_sawtooth_merge_inclusion_gate(inp)
        self.assertFalse(decision["allowed"], decision)
        self.assertTrue(decision["stripped"], decision)
        self.assertEqual(decision["reason"], "sawtooth_equipment_outside_target_machine")
        self.assertNotIn("Sawtooth_Merge", inp.include_programs)
        # Sorter_Track must not be collateral damage
        self.assertIn("Sorter_Track", inp.include_programs)
        gold = resolve_program_exports(inp.include_programs, include_sys=False)
        self.assertNotIn("Sawtooth_Merge", [g["name"] for g in gold])


class TestSawtoothInclusionPlc4Guard(unittest.TestCase):
    """Do not break PLC4 Sawtooth when properly configured."""

    @unittest.skipUnless(
        (ROOT / "workspace" / "cp4-run" / "RUN" / "project.cfg").is_file(),
        "CP4 RUN missing",
    )
    def test_plc4_run_evidence_intersects_target(self) -> None:
        from fortna_autogen import load_from_run
        from fortna_cp4_discovery import discover_sawtooth
        from fortna_autogen import (
            sawtooth_equipment_refs_from_discovery,
            sawtooth_refs_intersect_target,
        )

        run = ROOT / "workspace" / "cp4-run" / "RUN"
        inp = load_from_run(run, processor="1756-L83E")
        saw = discover_sawtooth(run, "ORNCCP4")
        refs = sawtooth_equipment_refs_from_discovery(saw)
        hits = sawtooth_refs_intersect_target(refs, target_machine_equipment_ptags(inp))
        self.assertTrue(hits, f"PLC4 must have in-scope sawtooth refs; refs={refs}")

        inp.include_programs = ["Sawtooth_Merge"]
        inp.sawtooth_build = {
            "collector_conveyor": "P414",
            "lanes": [{"conveyor": "P219"}, {"conveyor": "P116"}],
        }
        decision = evaluate_sawtooth_merge_inclusion(inp)
        self.assertTrue(decision["allowed"], decision)
        gated = apply_sawtooth_merge_inclusion_gate(inp)
        self.assertIn("Sawtooth_Merge", inp.include_programs)
        self.assertTrue(gated["allowed"], gated)


class TestSawtoothProvenanceWhy(unittest.TestCase):
    def test_why_sawtooth_merge_review_without_lineage(self) -> None:
        from fortna_autogen_provenance import (
            CLASS_REVIEW,
            collect_sawtooth_pack_provenance,
            why_query,
        )

        # Synthetic audit doc using collector directly (no RUN required)
        recs = collect_sawtooth_pack_provenance(
            ROOT / "workspace" / "_virgin_orindy" / "RUN",
            "ORINDYAC6",
            autogen_report={
                "programs": ["Sys", "Sawtooth_Merge"],
                "sawtooth_inclusion": {
                    "allowed": False,
                    "reason": "sawtooth_equipment_outside_target_machine",
                    "classification": CLASS_REVIEW,
                    "build_configured": True,
                    "build_refs": ["P520", "P516"],
                    "build_hits": [],
                    "discovery_refs": ["P520"],
                    "discovery_hits": [],
                    "want_include": True,
                },
            },
        )
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].artifact, "Sawtooth_Merge")
        self.assertEqual(recs[0].classification, CLASS_REVIEW)
        self.assertFalse(recs[0].included)
        doc = {"records": [r.__dict__ if hasattr(r, "__dict__") else r for r in (
            # asdict-compatible
            __import__("dataclasses").asdict(recs[0]),
        )]}
        hits = why_query(doc, "Sawtooth_Merge")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["artifact"], "Sawtooth_Merge")
        self.assertEqual(hits[0]["classification"], CLASS_REVIEW)


if __name__ == "__main__":
    unittest.main()

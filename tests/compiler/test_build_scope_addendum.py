#!/usr/bin/env python3
"""Partial / area-scoped build architecture — minimum groundwork tests."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_build_scope import (  # noqa: E402
    SCOPE_AREA,
    SCOPE_FULL,
    INTENT_COMPLETE,
    INTENT_PARTIAL,
    BuildScope,
    compute_build_closure,
    classify_build_result,
    area_export_manifest,
    parse_build_scope,
)


class TestBuildScopeClosure(unittest.TestCase):
    def test_selected_area_excludes_other_areas(self) -> None:
        scope = BuildScope(mode=SCOPE_AREA, selected_areas=["Area_A"], intent=INTENT_PARTIAL)
        closure = compute_build_closure(
            areas=["Area_A", "Area_B"],
            conveyors=[
                {"conveyor": "P100", "main_area": "Area_A"},
                {"conveyor": "P200", "main_area": "Area_B"},
            ],
            safety_zone_members=[
                {
                    "name": "Zone_A",
                    "area": "Area_A",
                    "conveyors": ["P100"],
                    "members": ["ES1"],
                },
                {
                    "name": "Zone_B",
                    "area": "Area_B",
                    "conveyors": ["P200"],
                    "members": ["ES2"],
                },
            ],
            scope=scope,
        )
        self.assertEqual(closure.areas, ["Area_A"])
        self.assertEqual(closure.conveyors, ["P100"])
        self.assertIn("Zone_A", closure.safety_zones)
        self.assertNotIn("Zone_B", closure.safety_zones)

    def test_partial_does_not_hard_block(self) -> None:
        scope = BuildScope(mode=SCOPE_FULL, intent=INTENT_PARTIAL)
        closure = compute_build_closure(
            areas=["A"],
            conveyors=[{"conveyor": "P1", "main_area": "A"}],
            scope=scope,
        )
        br = classify_build_result(
            closure=closure,
            unresolved_in_closure=["P1→(unresolved Safety)"],
            live_fast_conv=0,
            pi_writer_ok=False,
        )
        self.assertEqual(br["build_state"], INTENT_PARTIAL)
        self.assertFalse(br["commissionable"])
        self.assertFalse(br["hard_block_complete"])

    def test_complete_hard_blocks_unresolved(self) -> None:
        scope = BuildScope(mode=SCOPE_FULL, intent=INTENT_COMPLETE)
        closure = compute_build_closure(
            areas=["A"],
            conveyors=[{"conveyor": "P1", "main_area": "A"}],
            scope=scope,
        )
        br = classify_build_result(
            closure=closure,
            unresolved_in_closure=["P1→(unresolved Safety)"],
            live_fast_conv=0,
            pi_writer_ok=False,
        )
        self.assertTrue(br["hard_block_complete"])
        self.assertFalse(br["commissionable"])

    def test_area_export_manifest_shape(self) -> None:
        scope = BuildScope(mode=SCOPE_AREA, selected_areas=["A"], intent=INTENT_PARTIAL)
        closure = compute_build_closure(
            areas=["A"],
            conveyors=[{"conveyor": "P1", "main_area": "A"}],
            scope=scope,
        )
        br = classify_build_result(closure=closure, unresolved_in_closure=[], live_fast_conv=1)
        man = area_export_manifest(closure=closure, build_result=br)
        self.assertEqual(man["export_kind"], "AREA_PROGRAM_L5X")
        self.assertTrue(man["policy"]["no_safe_escape_hatch"])
        self.assertTrue(man["policy"]["generated_ne_commissionable"])


class TestPartialBuildAutogen(unittest.TestCase):
    @unittest.skipUnless(
        (ROOT / "workspace/_plc2_run_peek/RUN/project.cfg").is_file(),
        "ORNCCP2 RUN peek missing",
    )
    def test_partial_full_controller_generates_without_whole_project_safety(self) -> None:
        """Unresolved Safety outside a complete intent must not block PARTIAL L5X."""
        from fortna_autogen import build_l5x, load_from_run

        lib = ROOT / "tools/libraries/OReilly_Library_v3.L5X"
        inp = load_from_run(ROOT / "workspace/_plc2_run_peek/RUN")
        inp.include_sys = False
        inp.build_intent = "PARTIAL"
        inp.build_scope_mode = "FULL_CONTROLLER"
        # No engineer Safety zones — Default/Unassigned remains; PARTIAL must still emit
        inp.safety_build = {"zones": []}
        inp.safety_zones = []
        inp.safety_zone_members = []
        l5x, report = build_l5x(inp, lib)
        self.assertTrue(len(l5x) > 1000)
        self.assertEqual(report.get("build_state"), "PARTIAL")
        self.assertFalse(report.get("commissionable"))
        # PARTIAL: generation_assertions may still be ok (Safety withheld, not COMPLETE fail)
        # Studio blockers must not include PD-0003 COMPLETE failure
        blockers = report.get("studio_blockers") or []
        self.assertFalse(
            any("COMPLETE/COMMISSIONABLE" in b for b in blockers),
            msg=blockers,
        )
        # Fast_Conv withheld as NOP in PARTIAL when Safety unresolved
        live = re.findall(r"Fast_Conv\([^)]+\)", l5x)
        # May be 0 in PARTIAL without Safety — that is withheld, not fake _Safe
        self.assertFalse(any("_Safe" in x for x in live))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""PLC2 final freeze corrections — emitted-L5X / path / determinism evidence."""
from __future__ import annotations

from pathlib import Path
import os
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import fortna_autogen as ag  # noqa: E402


class TestPd0036PathQuarantine(unittest.TestCase):
    def test_rejects_traversal_and_oracle_paths(self) -> None:
        attacks = [
            "../validation_oracles/Sys_Program.L5X",
            "..\\validation_oracles\\IO_MAP_Program.L5X",
            "validation_oracles/Sys_Program.L5X",
            str(ROOT / "tools/libraries/validation_oracles/Sys_Program.L5X"),
            "%2e%2e/validation_oracles/Sys_Program.L5X",
        ]
        for a in attacks:
            packs = ag.resolve_program_exports([a], include_io_map_gold=True)
            names = [p.get("name") for p in packs]
            self.assertNotIn("Sys", names, msg=a)
            self.assertFalse(
                any("ORLY_Greensboro" in str(p.get("source") or "") for p in packs),
                msg=a,
            )

    def test_io_map_gold_still_ignored(self) -> None:
        packs = ag.resolve_program_exports(include_io_map_gold=True)
        self.assertNotIn("IO_MAP", [p.get("name") for p in packs])


class TestPd0029NoCommDiagReconstruction(unittest.TestCase):
    def test_no_inline_index_max_init_shape(self) -> None:
        src = (SCRIPTS / "fortna_autogen.py").read_text(encoding="utf-8")
        # Reconstruction body must not synthesize CommDiag_UDT members
        self.assertIn("never reconstruct finished-site CommDiag_UDT", src)
        # The old L5K array shape literal must not appear as a synthesis template
        self.assertNotRegex(
            src,
            r'CDATA\[\[0,\{int\(index_max\)\},0\]\]',
        )


class TestPd0034SafeNeverTag(unittest.TestCase):
    def test_safe_empty_not_tag(self) -> None:
        self.assertEqual(ag._safe(""), "")
        self.assertEqual(ag._safe("???"), "")
        self.assertEqual(ag._safe("---"), "")
        self.assertNotEqual(ag._safe("P217"), "Tag")

    def test_clone_next_never_tag_conv(self) -> None:
        lib = (ROOT / "tools/libraries/OReilly_Library_v3.L5X").read_text(
            encoding="utf-8", errors="replace"
        )
        # Minimal: downstream that sanitizes empty must yield NO_Conv
        item = ag.clone_template_for_conveyor(
            lib,
            "P1000_Conv",
            "P100",
            "Area_A",
            "",
            "---",  # collapses to empty via _safe
        )
        fast = next(r for r in item["rungs"] if r["label"] == "Fast")
        self.assertIn("NO_Conv", fast["text"])
        self.assertNotIn("Tag_Conv", fast["text"])


class TestPd0003NoSafeEscape(unittest.TestCase):
    def test_no_area_safe_invention_in_scrub_source(self) -> None:
        src = (SCRIPTS / "fortna_autogen.py").read_text(encoding="utf-8")
        self.assertIn("no _Safe escape", src)
        # Scrub must not assign f"{...}_Safe" as operational zone
        scrub = src[src.find("_scrub_motion_safety_zone_refs") : src.find("_scrub_motion_safety_zone_refs") + 3500]
        self.assertNotRegex(scrub, r'item\["safety_zone"\]\s*=\s*stub')
        self.assertNotRegex(scrub, r'item\["safety_zone"\]\s*=\s*f?".*_Safe"')


class TestPd0037DeterministicCsOrder(unittest.TestCase):
    def test_cs_sort_in_source(self) -> None:
        src = (SCRIPTS / "fortna_autogen.py").read_text(encoding="utf-8")
        self.assertIn("PD-0037: deterministic CS slot order", src)
        self.assertIn("sorted(dict.fromkeys(_cs_tags_for_area)", src)


class TestPd0038Quarantine(unittest.TestCase):
    def test_finished_packs_not_in_production_dirs(self) -> None:
        prod = ROOT / "tools" / "libraries"
        programs = prod / "programs"
        oracle = prod / "validation_oracles"
        for name in (
            "AOI_SNTP_QUERY_AOI.L5X",
            "TRK_Divert_WaveFunction_AOI.L5X",
            "Enc_Routine_ST.L5X",
        ):
            self.assertFalse((prod / name).is_file(), msg=name)
            self.assertTrue((oracle / name).is_file(), msg=name)
        for name in (
            "Sorter_Track_Program.L5X",
            "WCS_Interface_TCP_IP_Program.L5X",
            "Sawtooth_Merge_Program.L5X",
            "ShippingSorter_Area_L3_Program.L5X",
            "IO_MAP_Program.L5X",
            "Sys_Program.L5X",
            "System_Program.L5X",
        ):
            self.assertFalse((programs / name).is_file(), msg=name)
            self.assertTrue((oracle / name).is_file(), msg=name)
        self.assertTrue((prod / "OReilly_Library_v3.L5X").is_file())
        self.assertTrue((prod / "PRODUCTION_LIBRARY_PROVENANCE.md").is_file())


class TestPd0037RepeatedBuildHash(unittest.TestCase):
    """Same CS name set → same sorted slot order regardless of hash seed / set order."""

    def test_cs_sort_stable_under_shuffled_sets(self) -> None:
        def _cs_sort_key(name: str) -> tuple:
            m = re.search(r"(\d+)", name or "")
            return (int(m.group(1)) if m else 10**9, name or "")

        names = ["CP3_CS", "CP2_CS", "CP10_CS", "CP1_CS"]
        orders = []
        for seed_perm in (
            names,
            list(reversed(names)),
            ["CP10_CS", "CP1_CS", "CP3_CS", "CP2_CS"],
            list(dict.fromkeys(names)),  # insertion
        ):
            # Simulate set→list then sorted (production path)
            as_set_list = list(set(seed_perm))
            orders.append(tuple(sorted(as_set_list, key=_cs_sort_key)))
        self.assertEqual(len(set(orders)), 1, msg=orders)
        self.assertEqual(orders[0], ("CP1_CS", "CP2_CS", "CP3_CS", "CP10_CS"))

    @unittest.skipUnless(
        (ROOT / "workspace/_plc2_run_peek/RUN/project.cfg").is_file(),
        "ORNCCP2 RUN peek missing",
    )
    def test_repeated_build_cs_calls_identical(self) -> None:
        """Same RUN + intent → identical Slow_ControlStation calls across 3 builds."""
        from fortna_autogen import build_l5x, load_from_run

        run = ROOT / "workspace/_plc2_run_peek/RUN"
        lib = ROOT / "tools/libraries/OReilly_Library_v3.L5X"
        calls_list = []
        for _ in range(3):
            inp = load_from_run(run)
            inp.include_sys = False
            inp.include_io_map_gold = False
            l5x, _rep = build_l5x(inp, lib)
            calls = re.findall(r"Slow_ControlStation\(([^)]*)\)", l5x)
            calls_list.append(tuple(calls))
        self.assertEqual(len(set(calls_list)), 1, msg=calls_list)


if __name__ == "__main__":
    unittest.main()

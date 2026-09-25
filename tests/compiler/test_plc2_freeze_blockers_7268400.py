#!/usr/bin/env python3
"""Freeze blocker corrections against audited SHA 7268400 findings."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))

RUN = ROOT / "workspace" / "_plc2_run_peek" / "RUN"
LIB = ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X"


class TestRunLogicTriggers(unittest.TestCase):
    @unittest.skipUnless((RUN / "FORTNA" / "Logic.asc").is_file(), "RUN Logic.asc missing")
    def test_mcr_apress_triggers_3_and_4(self) -> None:
        from fortna_run_logic_triggers import mcr_command_writers_from_run

        writers = mcr_command_writers_from_run(RUN)
        by_coil = {w["coil"]: w for w in writers if w.get("status") == "PROVEN"}
        self.assertIn("2MCR1", by_coil)
        self.assertEqual(by_coil["2MCR1"]["condition_io"], "PS312")
        self.assertEqual(by_coil["2MCR1"]["trigger"], 3)
        self.assertIn("3MCR1", by_coil)
        self.assertEqual(by_coil["3MCR1"]["condition_io"], "PS320")
        self.assertEqual(by_coil["3MCR1"]["trigger"], 4)
        # Must NOT invent Start/Stop
        for w in writers:
            self.assertNotIn("Start_PB", str(w.get("rung") or ""))

    @unittest.skipUnless((RUN / "FORTNA" / "horns.asc").is_file(), "horns.asc missing")
    def test_horns_asc_cp2_wh310(self) -> None:
        from fortna_run_logic_triggers import parse_horns_asc, horn_fire_triggers_from_run

        horns = {h["cp"]: h for h in parse_horns_asc(RUN) if h.get("cp")}
        self.assertEqual(horns["CP2"]["hornio"], "2WH")
        self.assertEqual(horns["CP2"]["companion_wh"], "WH310")
        self.assertEqual(horns["CP3"]["hornio"], "3WH")
        fires = {f["dest"]: f for f in horn_fire_triggers_from_run(RUN)}
        self.assertEqual(fires["WH310"]["source"], "2WH")
        self.assertEqual(fires["WH310"]["trigger"], 87)
        self.assertEqual(fires["WH318"]["source"], "3WH")


class TestPd0002EmittedMcr(unittest.TestCase):
    @unittest.skipUnless(RUN.is_dir() and LIB.is_file(), "RUN/library missing")
    def test_emitted_mcr_uses_apress_not_cs_start_stop(self) -> None:
        from fortna_autogen import build_l5x, load_from_run

        inp = load_from_run(RUN)
        inp.include_sys = False
        area0 = (inp.areas or ["ORNCCP2_Area"])[0]
        if isinstance(area0, dict):
            area0 = area0.get("name") or "ORNCCP2_Area"
        inp.safety_build = {
            "version": 1,
            "zones": [
                {
                    "name": "ModuleB_ESZone1",
                    "area": area0,
                    "conveyors": [getattr(c, "conveyor", "") for c in (inp.conveyors or [])[:8]],
                    "members": ["T_2ES", "T_3ES", "T_2MCR1_AUX", "T_3MCR1_AUX"],
                    "membersOrigin": "ENGINEER_ASSIGNED",
                }
            ],
        }
        inp.safety_zones = ["ModuleB_ESZone1"]
        inp.safety_zone_members = inp.safety_build["zones"]
        for c in inp.conveyors or []:
            c.safety_zone = "ModuleB_ESZone1"
            c.main_area = c.main_area or area0
        l5x, report = build_l5x(inp, LIB)
        self.assertNotRegex(l5x, r"Start_PB\)XIO\([^)]*Stop_PB\)OTE\(T_\d*MCR")
        self.assertRegex(l5x, r"XIC\(PS312\.I\.Pressure_OK\)OTE\(T_2MCR1\)")
        self.assertRegex(l5x, r"XIC\(PS320\.I\.Pressure_OK\)OTE\(T_3MCR1\)")
        self.assertEqual(
            re.search(r'<Tag[^>]*Name="T_2MCR1"[^>]*DataType="([^"]+)"', l5x).group(1),
            "BOOL",
        )


class TestPd0003LiveFastConv(unittest.TestCase):
    @unittest.skipUnless(RUN.is_dir() and LIB.is_file(), "RUN/library missing")
    def test_live_fast_conv_when_engineer_zone_has_members(self) -> None:
        from fortna_autogen import build_l5x, load_from_run

        inp = load_from_run(RUN)
        inp.include_sys = False
        area0 = (inp.areas or ["ORNCCP2_Area"])[0]
        if isinstance(area0, dict):
            area0 = str(area0.get("name") or "ORNCCP2_Area")
        convs = [getattr(c, "conveyor", "") for c in (inp.conveyors or []) if getattr(c, "conveyor", "")]
        self.assertGreater(len(convs), 5)
        inp.safety_build = {
            "version": 1,
            "zones": [
                {
                    "name": "ModuleB_ESZone1",
                    "area": area0,
                    "conveyors": convs,
                    "members": ["T_2ES", "T_3ES", "ES400"],
                    "membersOrigin": "ENGINEER_ASSIGNED",
                }
            ],
        }
        inp.safety_zones = ["ModuleB_ESZone1"]
        inp.safety_zone_members = inp.safety_build["zones"]
        for c in inp.conveyors or []:
            c.safety_zone = "ModuleB_ESZone1"
            c.main_area = area0
        l5x, report = build_l5x(inp, LIB)
        live = re.findall(r"Fast_Conv\([^)]+\)", l5x)
        self.assertGreater(len(live), 0, msg="PD-0042: live Fast_Conv required")
        self.assertTrue(all("ModuleB_ESZone1" in x for x in live))
        self.assertFalse(any("_Safe" in x for x in live))
        # Adversarial: made-up zone without members must not invent writers
        inp2 = load_from_run(RUN)
        inp2.include_sys = False
        inp2.safety_build = {
            "zones": [{"name": "FakeZone", "area": area0, "conveyors": convs[:3], "members": []}]
        }
        inp2.safety_zones = ["FakeZone"]
        inp2.safety_zone_members = inp2.safety_build["zones"]
        for c in inp2.conveyors or []:
            c.safety_zone = "FakeZone"
        l5x2, rep2 = build_l5x(inp2, LIB)
        blockers = rep2.get("studio_blockers") or []
        self.assertTrue(
            any("PD-0003" in b or "PI writer" in b for b in blockers)
            or not (rep2.get("generation_assertions") or {}).get("ok"),
            msg=str(blockers),
        )
        # Must not invent ES_SIL1 for empty FakeZone
        self.assertNotIn("FakeZone_Safe_Logic", l5x2)


class TestPd0041LibrarySeal(unittest.TestCase):
    def test_rejects_warden_attack_classes(self) -> None:
        from fortna_autogen import resolve_production_library, DEFAULT_LIBRARY

        attacks = [
            str(ROOT / "tools/libraries/validation_oracles/System_Program.L5X"),
            "../validation_oracles/Sys_Program.L5X",
            "..\\validation_oracles\\IO_MAP_Program.L5X",
            str(ROOT / "workspace/validation/ORLY_GreensboroPLC2_NC_Finished.L5X"),
            "%2e%2e/tools/libraries/validation_oracles/Sys_Program.L5X",
            str(ROOT / "tools/libraries/validation_oracles/Slow_Flt_AOI.L5X"),
        ]
        for a in attacks:
            with self.assertRaises(ValueError, msg=a):
                resolve_production_library(a)
        ok = resolve_production_library("OReilly_Library_v3.L5X")
        self.assertEqual(ok.resolve(), DEFAULT_LIBRARY.resolve())


class TestSafetyModelAreasDict(unittest.TestCase):
    @unittest.skipUnless(RUN.is_dir(), "RUN missing")
    def test_build_safety_model_accepts_dict_areas(self) -> None:
        from fortna_safety_model import build_safety_model

        # Reproduce Warden crash: areas as dict objects
        model = build_safety_model(
            run_dir=RUN,
            machine="ORNCCP2",
            areas=[{"name": "ORNCCP2_Area", "id": "a1"}, {"name": "Trash_Area"}],
            engineer_safety_build={
                "zones": [
                    {
                        "name": "Trash_Zone",
                        "source_id": "szone_test",
                        "engineering_name": "Trash_Zone",
                        "area": "Trash_Area",
                        "members": [],
                        "provenance": "ENGINEER_CREATED",
                    }
                ]
            },
        )
        self.assertIsInstance(model, dict)
        self.assertIn("zones", model)


class TestPd0005HornEmit(unittest.TestCase):
    @unittest.skipUnless(RUN.is_dir() and LIB.is_file(), "RUN/library missing")
    def test_horn_chain_from_run_not_digits(self) -> None:
        from fortna_autogen import build_l5x, load_from_run

        inp = load_from_run(RUN)
        inp.include_sys = False
        l5x, _ = build_l5x(inp, LIB)
        has_cs_to_hornio = bool(re.search(r"XIC\(CP2_CS\.O\.Horn\)OTE\((?:T_)?2WH\)", l5x))
        has_fire = bool(re.search(r"XIC\((?:T_)?2WH\)OTE\((?:T_)?WH310\)", l5x))
        self.assertTrue(
            has_cs_to_hornio or has_fire,
            msg=f"missing proven horn chain cs={has_cs_to_hornio} fire={has_fire}",
        )
        # Digit-match invention without RUN evidence must not be the only path
        self.assertNotIn("RUN panel ", l5x)  # old digit-match comment removed


if __name__ == "__main__":
    unittest.main()

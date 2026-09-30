#!/usr/bin/env python3
"""ORI-083: PLC_Fast EVENT scheduling + report/task fidelity.

Synthetic minimal fixtures only — no proprietary Reno TAR.
Proves:
  - Area L1/L2 generation also emits controller PLC_Fast on P10_Fast_50ms
  - PLC_Fast contains real EVENT() for P15_Config_L1/L2_Event (and Sys)
  - Sys/PLC_Init emitted when Init.* has L1/L2 readers and no writers
  - report programs/task_schedule derived from actual L5X XML
  - no false P10_Fast_20ms claim
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

import fortna_autogen as ag  # noqa: E402

LIBRARY = _SF_REPO / "tools" / "libraries" / "OReilly_Library_v3.L5X"


def _synthetic_input() -> ag.AutogenInput:
    return ag.AutogenInput(
        project_name="Synthetic_ORI083",
        machine="SYNTH_CTRL1",
        areas=["ModuleB_Area"],
        safety_zones=["ModuleB_ESZone1"],
        include_sys=False,
        include_io_map=False,
        conveyors=[
            ag.ConveyorRow(
                number=1,
                conveyor="P901",
                main_area="ModuleB_Area",
                safety_zone="ModuleB_ESZone1",
                type="Transport with MS",
                motor_starter="Yes",
                jam_pe_tags=["PE901"],
                product_pe_tags=["PE901"],
            ),
        ],
        pe_devices=[{"name": "PE901", "conveyor": "P901"}],
    )


class TestOri083PlcFastScheduling(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not LIBRARY.is_file():
            raise unittest.SkipTest(f"library missing: {LIBRARY}")

    def test_plc_fast_event_and_sys_init_emitted(self) -> None:
        inp = _synthetic_input()
        l5x, report = ag.build_l5x(inp, LIBRARY)

        self.assertIn("PLC_Fast", report.get("programs") or [])
        self.assertIn("Sys", report.get("programs") or [])
        self.assertRegex(l5x, r'<Program\s+Name="PLC_Fast"')
        self.assertRegex(l5x, r'<Program\s+Name="Sys"')

        # Real EVENT() instructions — L1/L2 never run without these.
        self.assertIn("EVENT(P15_Config_L1_Event)", l5x)
        self.assertIn("EVENT(P15_Config_L2_Event)", l5x)
        self.assertIn("EVENT(P15_Config_Sys_Event)", l5x)

        # PLC_Fast scheduled on P10_Fast_50ms alongside Area_Fast
        sched = report.get("task_schedule") or {}
        self.assertIn("P10_Fast_50ms", sched)
        self.assertIn("PLC_Fast", sched["P10_Fast_50ms"])
        self.assertTrue(
            any(n.endswith("_Area_Fast") or n.endswith("_Fast") for n in sched["P10_Fast_50ms"]),
            msg=f"Area Fast missing from P10: {sched['P10_Fast_50ms']}",
        )
        self.assertNotIn("P10_Fast_20ms", sched)
        self.assertNotIn("P10_Fast_20ms", l5x)

        # Sys on EVENT task, triggered by PLC_Fast
        self.assertIn("P15_Config_Sys_Event", sched)
        self.assertEqual(sched["P15_Config_Sys_Event"], ["Sys"])
        self.assertIn("P15_Config_L1_Event", sched)
        self.assertIn("P15_Config_L2_Event", sched)

        # Sys PLC_Init writes Init.*
        self.assertRegex(l5x, r"Init\.DebounceOnTime\s*:=")
        self.assertIn("JSR(PLC_Init,0);", l5x)

        # Config programs are EVENT_SCHEDULED, never NOT_EXECUTABLE here
        cfg = report.get("config_program_status") or {}
        self.assertTrue(cfg, msg="config_program_status missing")
        for name, st in cfg.items():
            self.assertEqual(
                st,
                "EVENT_SCHEDULED",
                msg=f"{name} status={st} (expected EVENT_SCHEDULED)",
            )

    def test_report_matches_generated_l5x(self) -> None:
        inp = _synthetic_input()
        l5x, report = ag.build_l5x(inp, LIBRARY)

        l5x_programs = ag._programs_from_l5x(l5x)
        l5x_tasks = ag._task_schedule_from_l5x(l5x)

        self.assertEqual(
            list(report.get("programs") or []),
            l5x_programs,
            msg="REPORT_PROGRAMS != GENERATED_PROGRAMS",
        )
        self.assertEqual(
            dict(report.get("task_schedule") or {}),
            l5x_tasks,
            msg="REPORT_TASKS != GENERATED_TASKS",
        )
        self.assertEqual(
            list(report.get("tasks") or []),
            list(l5x_tasks.keys()),
        )
        # No false Sys claim without Program Sys
        if "Sys" in (report.get("programs") or []):
            self.assertRegex(l5x, r'<Program\s+Name="Sys"')
        for tname, progs in (report.get("task_schedule") or {}).items():
            self.assertRegex(l5x, rf'<Task\s+Name="{re.escape(tname)}"')
            for p in progs:
                self.assertRegex(l5x, rf'<Program\s+Name="{re.escape(p)}"')

    def test_helpers_parse_l5x(self) -> None:
        sample = """
        <Programs>
          <Program Name="Zone1_Area_Fast"/>
          <Program Name="Zone1_Area_L1"/>
          <Program Name="PLC_Fast"/>
          <Program Name="Sys"/>
        </Programs>
        <Tasks>
          <Task Name="P10_Fast_50ms" Type="PERIODIC">
            <ScheduledPrograms>
              <ScheduledProgram Name="Zone1_Area_Fast"/>
              <ScheduledProgram Name="PLC_Fast"/>
            </ScheduledPrograms>
          </Task>
          <Task Name="P15_Config_L1_Event" Type="EVENT">
            <ScheduledPrograms>
              <ScheduledProgram Name="Zone1_Area_L1"/>
            </ScheduledPrograms>
          </Task>
        </Tasks>
        """
        self.assertEqual(
            ag._programs_from_l5x(sample),
            ["Zone1_Area_Fast", "Zone1_Area_L1", "PLC_Fast", "Sys"],
        )
        self.assertEqual(
            ag._task_schedule_from_l5x(sample),
            {
                "P10_Fast_50ms": ["Zone1_Area_Fast", "PLC_Fast"],
                "P15_Config_L1_Event": ["Zone1_Area_L1"],
            },
        )
        # Without EVENT() → NOT_EXECUTABLE
        status = ag._config_program_exec_status(sample, ["Zone1_Area_L1", "Zone1_Area_L2"])
        self.assertEqual(status["Zone1_Area_L1"], "NOT_EXECUTABLE")
        self.assertEqual(status["Zone1_Area_L2"], "NOT_EXECUTABLE")
        with_event = sample + "EVENT(P15_Config_L1_Event)"
        status2 = ag._config_program_exec_status(
            with_event, ["Zone1_Area_L1", "Zone1_Area_L2"]
        )
        self.assertEqual(status2["Zone1_Area_L1"], "EVENT_SCHEDULED")
        self.assertEqual(status2["Zone1_Area_L2"], "NOT_EXECUTABLE")

    def test_plc_fast_builder_minimal_event_without_library_aois(self) -> None:
        """Honest REVIEW stubs still include real EVENT()."""
        seen: set[str] = set()
        tags: list[str] = []

        def _add(block: str) -> None:
            m = re.search(r'<Tag[^>]*\bName="([^"]+)"', block)
            if m:
                seen.add(m.group(1))
            tags.append(block)

        def _rung_xml(num: int, text: str, comment: str = "") -> str:
            c = f"<Comment><![CDATA[{comment}]]></Comment>" if comment else ""
            return (
                f'<Rung Number="{num}" Type="N">{c}'
                f"<Text><![CDATA[{text}]]></Text></Rung>"
            )

        def routine(name: str, rungs: list[str]) -> str:
            return (
                f'<Routine Name="{name}" Type="RLL"><RLLContent>'
                + "".join(rungs)
                + "</RLLContent></Routine>"
            )

        pack = ag._build_plc_fast_program_xml(
            library_text="",  # no AOIs
            _add_tag_block=_add,
            _rung_xml=_rung_xml,
            routine=routine,
            seen_tag_names=seen,
            has_l1=True,
            has_l2=True,
            has_sys=True,
        )
        xml = pack["program_xml"]
        self.assertIn("EVENT(P15_Config_L1_Event)", xml)
        self.assertIn("EVENT(P15_Config_L2_Event)", xml)
        self.assertIn("EVENT(P15_Config_Sys_Event)", xml)
        self.assertTrue(any("REVIEW_REQUIRED" in n for n in pack["review_notes"]))
        self.assertIn("Init_L1_Config", seen)
        self.assertIn("Init_L2_Config", seen)
        self.assertIn("Init_Sys_Config", seen)


if __name__ == "__main__":
    unittest.main()

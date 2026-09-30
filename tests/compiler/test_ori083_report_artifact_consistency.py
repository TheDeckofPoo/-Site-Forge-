#!/usr/bin/env python3
"""ORI-083: report programs/tasks must derive from L5X helpers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_autogen import (  # noqa: E402
    _programs_from_l5x,
    _task_schedule_from_l5x,
    _config_program_exec_status,
)


class TestOri083ReportArtifactConsistency(unittest.TestCase):
    def test_helpers_match_l5x(self) -> None:
        l5x = """
        <Programs>
          <Program Name="PLC_Fast"/>
          <Program Name="Sys"/>
          <Program Name="SITE_L1"/>
          <Program Name="SITE_L2"/>
        </Programs>
        <Tasks>
          <Task Name="P10_Fast_20ms">
            <ScheduledPrograms>
              <ScheduledProgram Name="PLC_Fast"/>
              <ScheduledProgram Name="Sys"/>
            </ScheduledPrograms>
          </Task>
          <Task Name="P15_Config_L1_Event">
            <ScheduledPrograms>
              <ScheduledProgram Name="SITE_L1"/>
            </ScheduledPrograms>
          </Task>
          <Task Name="P15_Config_L2_Event">
            <ScheduledPrograms>
              <ScheduledProgram Name="SITE_L2"/>
            </ScheduledPrograms>
          </Task>
        </Tasks>
        EVENT(P15_Config_L1_Event);
        EVENT(P15_Config_L2_Event);
        """
        progs = _programs_from_l5x(l5x)
        tasks = _task_schedule_from_l5x(l5x)
        self.assertEqual(progs, ["PLC_Fast", "Sys", "SITE_L1", "SITE_L2"])
        self.assertIn("PLC_Fast", tasks.get("P10_Fast_20ms", []))
        status = _config_program_exec_status(l5x, progs)
        self.assertEqual(status.get("SITE_L1"), "EVENT_SCHEDULED")
        self.assertEqual(status.get("SITE_L2"), "EVENT_SCHEDULED")


if __name__ == "__main__":
    unittest.main()

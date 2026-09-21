#!/usr/bin/env python3
"""Hard final-artifact gate: LOST CLAIMS must block successful generation.

A 256→67 mapping loss must never produce PASS again.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_autogen import _generation_assertion_failures  # noqa: E402


class TestIoMapLostClaimsGate(unittest.TestCase):
    def _inp(self, **kw):
        base = {
            "include_io_map": True,
            "pe_devices": [],
            "conveyors": [],
            "include_programs": [],
            "sawtooth_build": {},
        }
        base.update(kw)
        return SimpleNamespace(**base)

    def test_lost_claims_blocks_build(self) -> None:
        report = {
            "io_map_mapped": 67,
            "io_map_lost_claims_count": 189,
            "io_map_lost_claims_sample": [
                {"tname": "SOME_INPUT", "channel": "T_1794_AENT_2:I.Data[0].0"},
            ],
            "io_map_source": "run_tar_gz_banks_eip",
            "pe_logic_rungs": 0,
            "conveyor_count": 0,
        }
        failures = _generation_assertion_failures(
            self._inp(),
            report,
            mappable_io_count=256,
        )
        lost = [f for f in failures if "LOST CLAIMS=" in f]
        self.assertEqual(len(lost), 1, failures)
        self.assertIn("LOST CLAIMS=189", lost[0])
        self.assertIn("SOME_INPUT", lost[0])

    def test_zero_lost_claims_does_not_trip_gate(self) -> None:
        report = {
            "io_map_mapped": 255,
            "io_map_lost_claims_count": 0,
            "io_map_lost_claims_sample": [],
            "io_map_source": "run_tar_gz_banks_eip",
            "pe_logic_rungs": 0,
            "conveyor_count": 0,
        }
        failures = _generation_assertion_failures(
            self._inp(),
            report,
            mappable_io_count=256,
        )
        self.assertFalse(any("LOST CLAIMS=" in f for f in failures), failures)

    def test_gold_io_map_skips_lost_gate(self) -> None:
        report = {
            "io_map_mapped": 10,
            "io_map_lost_claims_count": 5,
            "io_map_lost_claims_sample": [{"tname": "X"}],
            "io_map_source": "gold_program_excel",
            "pe_logic_rungs": 0,
            "conveyor_count": 0,
        }
        failures = _generation_assertion_failures(
            self._inp(),
            report,
            mappable_io_count=50,
        )
        self.assertFalse(any("LOST CLAIMS=" in f for f in failures), failures)


if __name__ == "__main__":
    unittest.main()

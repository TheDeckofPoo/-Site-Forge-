#!/usr/bin/env python3
"""Regression: Hardware I/O engineer name + Generate/mute overrides."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_hardware_io_overrides import (  # noqa: E402
    apply_overrides_to_hardware_model,
    clear_overrides,
    effective_name,
    empty_overrides,
    load_overrides,
    overrides_for_iomap,
    save_overrides,
    upsert_channel_override,
    validate_logical_name,
)


class TestHardwareIoOverrides(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "overrides.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_validate_logical_name(self) -> None:
        ok, _ = validate_logical_name("P402_Conv.O.Run")
        self.assertTrue(ok)
        ok, err = validate_logical_name("bad name")
        self.assertFalse(ok)
        self.assertIn("Invalid", err)
        ok, _ = validate_logical_name("Fan_Starter")
        self.assertTrue(ok)
        ok, _ = validate_logical_name("")
        self.assertTrue(ok)
        print("  [PASS] logical name validation")

    def test_upsert_and_effective(self) -> None:
        ov = empty_overrides()
        upsert_channel_override(
            ov,
            physical_address="CP2RIO0:O.Data[6].6",
            source_name="M402",
            engineer_name="P402_Conv.O.Run",
            generate=True,
        )
        save_overrides(ov, self.path)
        loaded = load_overrides(self.path)
        ch = (loaded.get("channels") or {})["CP2RIO0:O.Data[6].6"]
        self.assertEqual(ch["sourceName"], "M402")
        self.assertEqual(ch["engineerName"], "P402_Conv.O.Run")
        self.assertTrue(ch["generate"])
        self.assertEqual(effective_name("M402", "P402_Conv.O.Run"), "P402_Conv.O.Run")
        print("  [PASS] upsert preserves source + engineer")

    def test_mute_excludes_from_iomap_map(self) -> None:
        ov = empty_overrides()
        upsert_channel_override(
            ov,
            physical_address="CP2RIO0:O.Data[6].6",
            source_name="M402",
            engineer_name="P402_Conv.O.Run",
            generate=False,
        )
        upsert_channel_override(
            ov,
            physical_address="CP2RIO0:O.Data[6].7",
            source_name="M404",
            generate=True,
        )
        m = overrides_for_iomap(ov)
        self.assertFalse(m["CP2RIO0:O.Data[6].6"]["generate"])
        self.assertTrue(m["CP2RIO0:O.Data[6].7"]["generate"])
        print("  [PASS] mute → generate=False in iomap map")

    def test_apply_to_model(self) -> None:
        model = {
            "ok": True,
            "adapters": [
                {
                    "rio_name": "CP2RIO0",
                    "modules": [
                        {
                            "channels": [
                                {
                                    "physical_address": "CP2RIO0:O.Data[6].6",
                                    "logical_endpoint": {"name": "M402"},
                                }
                            ]
                        }
                    ],
                }
            ],
        }
        ov = empty_overrides()
        upsert_channel_override(
            ov,
            physical_address="CP2RIO0:O.Data[6].6",
            source_name="M402",
            engineer_name="Fan_Starter",
            generate=True,
        )
        apply_overrides_to_hardware_model(model, ov)
        ch = model["adapters"][0]["modules"][0]["channels"][0]
        self.assertEqual(ch["sourceName"], "M402")
        self.assertEqual(ch["engineerName"], "Fan_Starter")
        self.assertEqual(ch["effectiveName"], "Fan_Starter")
        self.assertTrue(ch["generate"])
        print("  [PASS] model merge keeps RUN source + engineer effective")


def main() -> int:
    print("=== test_hardware_io_overrides ===")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestHardwareIoOverrides)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("ALL PASS" if result.wasSuccessful() else "FAIL")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

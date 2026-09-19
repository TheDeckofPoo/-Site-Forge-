#!/usr/bin/env python3
"""Regression: Hardware I/O engineer name + Generate/mute overrides."""
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


import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
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
            engineer_name="Fan_Starter",
            generate=True,
        )
        m = overrides_for_iomap(ov)
        self.assertFalse(m["CP2RIO0:O.Data[6].6"]["generate"])
        self.assertTrue(m["CP2RIO0:O.Data[6].7"]["generate"])
        self.assertEqual(m["CP2RIO0:O.Data[6].7"]["engineerName"], "Fan_Starter")
        print("  [PASS] mute → generate=False in iomap map")

    def test_apply_to_model(self) -> None:
        model = {
            "ok": True,
            "adapters": [
                {
                    "rio_name": "CP2RIO0",
                    "modules": [
                        {
                            "direction": "O",
                            "data_index": 6,
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

    def test_spare_engineer_name_survives_rebuild(self) -> None:
        """SPARE bit with no RUN channel must keep engineerName after model apply."""
        model = {
            "ok": True,
            "adapters": [
                {
                    "rio_name": "CP2RIO0",
                    "modules": [
                        {
                            "direction": "I",
                            "data_index": 7,
                            "is_adapter_card": False,
                            "channels": [],  # spare — no RUN points
                        }
                    ],
                }
            ],
        }
        ov = empty_overrides()
        upsert_channel_override(
            ov,
            physical_address="CP2RIO0:I.Data[7].15",
            source_name="",
            engineer_name="TEST_INPUT",
            generate=True,
        )
        apply_overrides_to_hardware_model(model, ov)
        chs = model["adapters"][0]["modules"][0]["channels"]
        self.assertTrue(chs, "expected synthesized spare channel")
        ch = next(c for c in chs if c["physical_address"] == "CP2RIO0:I.Data[7].15")
        self.assertEqual(ch["engineerName"], "TEST_INPUT")
        self.assertEqual(ch["effectiveName"], "TEST_INPUT")
        # Re-apply as if refreshHardwareIo rebuilt the model
        model2 = {
            "ok": True,
            "adapters": [
                {
                    "rio_name": "CP2RIO0",
                    "modules": [
                        {"direction": "I", "data_index": 7, "is_adapter_card": False, "channels": []}
                    ],
                }
            ],
        }
        apply_overrides_to_hardware_model(model2, ov)
        ch2 = model2["adapters"][0]["modules"][0]["channels"][0]
        self.assertEqual(ch2["effectiveName"], "TEST_INPUT")
        print("  [PASS] spare engineer name survives model rebuild")

    def test_rename_then_revert_purges_stale_name(self) -> None:
        """SPARE → TEST_OUTPUT → SPARE must leave ZERO active TEST_OUTPUT mapping."""
        from fortna_hardware_io_overrides import (
            is_clear_sentinel,
            prune_inactive_overrides,
            should_clear_engineer,
        )

        self.assertTrue(should_clear_engineer("SPARE", ""))
        self.assertTrue(should_clear_engineer("M402", "M402"))
        self.assertTrue(is_clear_sentinel(""))

        ov = empty_overrides()
        addr = "CP2RIO0:O.Data[6].6"
        upsert_channel_override(
            ov,
            physical_address=addr,
            source_name="",
            engineer_name="TEST_OUTPUT",
            generate=True,
        )
        self.assertEqual(
            (ov["channels"][addr].get("engineerName")),
            "TEST_OUTPUT",
        )
        # Revert to SPARE
        upsert_channel_override(
            ov,
            physical_address=addr,
            source_name="",
            engineer_name="SPARE",
            clear_engineer=False,  # should auto-clear via sentinel
        )
        prune_inactive_overrides(ov)
        self.assertNotIn(addr, ov.get("channels") or {})
        iomap = overrides_for_iomap(ov)
        self.assertNotIn(addr, iomap)
        blob = json.dumps(ov) + json.dumps(iomap)
        self.assertNotIn("TEST_OUTPUT", blob)
        print("  [PASS] rename→revert purges TEST_OUTPUT from overrides/iomap")

    def test_restore_source_name_clears_override(self) -> None:
        from fortna_hardware_io_overrides import prune_inactive_overrides

        ov = empty_overrides()
        addr = "CP2RIO0:O.Data[6].6"
        upsert_channel_override(
            ov,
            physical_address=addr,
            source_name="M402",
            engineer_name="Me_Likey_Butts",
            generate=True,
        )
        upsert_channel_override(
            ov,
            physical_address=addr,
            source_name="M402",
            engineer_name="M402",  # restore original
        )
        prune_inactive_overrides(ov)
        self.assertNotIn(addr, ov.get("channels") or {})
        self.assertNotIn("Me_Likey_Butts", json.dumps(overrides_for_iomap(ov)))
        print("  [PASS] restore source name clears Me_Likey_Butts")


def main() -> int:
    print("=== test_hardware_io_overrides ===")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestHardwareIoOverrides)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("ALL PASS" if result.wasSuccessful() else "FAIL")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""VFDDeviceModel builder — known-site discrete path + SpdControl NOT_CONFIGURED."""
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_vfd_device_model import (  # noqa: E402
    BINDING_DISCRETE,
    build_vfd_device_model,
    ethernet_optional_command_member,
    is_ethernet_optional_command_suffix,
)


class TestVfdDeviceModel(unittest.TestCase):
    def test_cp5_discrete_devices(self):
        run = ROOT / "workspace" / "cp5-run"
        if not (run / "RUN" / "FORTNA" / "Conveyor.asc").is_file():
            self.skipTest("CP5 RUN missing")
        model = build_vfd_device_model(run, "ORNCCP5")
        self.assertGreaterEqual(model["device_count"], 1)
        self.assertTrue(all(d["binding"] == BINDING_DISCRETE for d in model["devices"]))
        self.assertTrue(all(d["plc_datatype"] == "Motor_Starter_UDT" for d in model["devices"]))
        # SpdControl ethernet hooks unconfigured on known sites
        for st in model["spdcontrol"]["field_states"].values():
            self.assertIn(st, {"INVALID_OR_EMPTY", "ASC_MISSING", "N/A"})
        # Representative signal roles
        roles = {s["role"] for d in model["devices"] for s in d["signals"]}
        self.assertIn("START_ENABLE_CMD", roles)
        self.assertIn("RUNNING_FEEDBACK", roles)

    def test_cp2_no_vfds(self):
        run = ROOT / "workspace" / "_plc2_run_peek"
        if not (run / "RUN" / "FORTNA" / "Conveyor.asc").is_file():
            self.skipTest("PLC2 RUN peek missing")
        model = build_vfd_device_model(run, "ORNCCP2")
        self.assertEqual(model["device_count"], 0)

    def test_ethernet_optional_suffixes_gated(self):
        self.assertTrue(is_ethernet_optional_command_suffix("JOG"))
        self.assertTrue(is_ethernet_optional_command_suffix("CLR_FLT"))
        self.assertTrue(is_ethernet_optional_command_suffix("LOC_CTRL"))
        self.assertTrue(is_ethernet_optional_command_suffix("MOP_INC"))
        self.assertTrue(is_ethernet_optional_command_suffix("ACC_BIT0"))
        self.assertFalse(is_ethernet_optional_command_suffix("EN"))
        self.assertFalse(is_ethernet_optional_command_suffix("AUX"))
        self.assertEqual(ethernet_optional_command_member("JOG"), "VFDOut.Jog")
        self.assertEqual(
            ethernet_optional_command_member("CLR_FLT"), "VFDOut.ClearFaults"
        )


if __name__ == "__main__":
    unittest.main()

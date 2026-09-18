#!/usr/bin/env python3
"""VFDDeviceModel builder — known-site discrete path + SpdControl NOT_CONFIGURED."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_vfd_device_model import (  # noqa: E402
    BINDING_DISCRETE,
    build_vfd_device_model,
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


if __name__ == "__main__":
    unittest.main()

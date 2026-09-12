#!/usr/bin/env python3
"""Area_1 and EStop_Zone_1 engineer default workflow."""
from __future__ import annotations

import sys
import unittest

from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_site_model import (  # noqa: E402
    SiteModel,
    ensure_default_area,
    ensure_default_estop_zone,
    make_object,
)
from fortna_area_ops import rename_area, create_area, move_equipment  # noqa: E402


class TestEngineerDefaults(unittest.TestCase):
    def test_area_1_assigns_included_equipment(self):
        m = SiteModel(machine_scope="ALPHASITE", run_dir="synthetic")
        m.equipment = [
            make_object("equipment", "P9001", inclusion="INCLUDED").to_dict(),
            make_object("equipment", "P9002", inclusion="AVAILABLE").to_dict(),
        ]
        ensure_default_area(m)
        self.assertTrue(any(a.get("raw_name") == "Area_1" for a in m.areas))
        p9001 = next(e for e in m.equipment if e["normalized_name"] == "P9001")
        p9002 = next(e for e in m.equipment if e["normalized_name"] == "P9002")
        self.assertEqual(p9001.get("area_id"), "Area_1")
        self.assertNotEqual(p9002.get("area_id"), "Area_1")  # AVAILABLE not auto-assigned

    def test_estop_zone_1_holds_devices(self):
        m = SiteModel(machine_scope="ALPHASITE", run_dir="synthetic")
        m.estop_zones = [
            make_object("estop_zone", "ES900", inclusion="AVAILABLE").to_dict(),
            make_object("estop_zone", "ES901", inclusion="AVAILABLE").to_dict(),
        ]
        ensure_default_estop_zone(m)
        zones = (m.operational_groups or {}).get("estop_zones_operational") or m.estop_zones
        self.assertTrue(any((z.get("raw_name") or z.get("name")) == "EStop_Zone_1" for z in zones))
        devices = (m.operational_groups or {}).get("estop_devices") or []
        self.assertGreaterEqual(len(devices), 2)
        self.assertTrue(all(d.get("estop_zone_id") == "EStop_Zone_1" for d in devices))

    def test_rename_area_still_works_after_default(self):
        m = SiteModel(machine_scope="ALPHASITE", run_dir="synthetic")
        m.equipment = [make_object("equipment", "P1", inclusion="INCLUDED").to_dict()]
        ensure_default_area(m)
        rename_area(m, "Area_1", "Shipping_Area")
        self.assertEqual(m.equipment[0].get("area_id"), "Shipping_Area")


if __name__ == "__main__":
    unittest.main()

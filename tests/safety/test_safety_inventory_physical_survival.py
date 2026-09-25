#!/usr/bin/env python3
"""Safety inventory: alias suppression must not erase canonical physical devices.

ORI-010 family — raw signals > 0 with valid controller-owned evidence must not
collapse to zero engineer-facing physical devices.
"""
from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_safety_model import (  # noqa: E402
    build_safety_evidence_union,
    build_safety_model,
)
from fortna_safety_inventory_scope import (  # noqa: E402
    LOCAL_PHYSICAL,
    UNRELATED_FOREIGN,
    classify_safety_device_scope,
    partition_safety_inventory,
)


def _lift_phys(g: dict) -> str:
    pe = str(g.get("physicalEndpoint") or "").strip()
    if pe:
        return pe
    for s in g.get("signals") or []:
        if isinstance(s, dict) and s.get("physicalEndpoint"):
            return str(s["physicalEndpoint"])
    return ""


class TestGroupedDeviceCarriesPhysicalEndpoint(unittest.TestCase):
    def test_grouped_devices_have_device_level_phys(self) -> None:
        run = ROOT / "workspace" / "_orindyac3_run" / "RUN"
        if not run.is_dir():
            self.skipTest("ORINDYAC3 RUN missing")
        eu = build_safety_evidence_union(run, "ORINDYAC3")
        devices = eu.get("devices") or []
        self.assertGreater(len(devices), 0)
        missing = [d.get("name") for d in devices if not d.get("physicalEndpoint")]
        self.assertEqual(
            missing,
            [],
            msg=f"canonical devices missing physicalEndpoint: {missing[:10]}",
        )

    def test_raw_signals_do_not_collapse_to_zero_physical(self) -> None:
        run = ROOT / "workspace" / "_orindyac3_run" / "RUN"
        if not run.is_dir():
            self.skipTest("ORINDYAC3 RUN missing")
        model = build_safety_model(
            run_dir=run,
            machine="ORINDYAC3",
            transport_zones=[],
            areas=[],
            engineer_safety_build={},
        )
        flat = model.get("devices") or []
        grouped = model.get("safetyDevices") or []
        raw = len(flat)
        phys = sum(1 for d in grouped if d.get("physicalEndpoint") or _lift_phys(d))
        self.assertGreater(raw, 0)
        self.assertGreater(
            phys,
            0,
            msg=f"INVARIANT VIOLATED: raw_safety_signals={raw} but canonical_physical=0",
        )


class TestAliasSuppressionSurvivesCanonical(unittest.TestCase):
    def test_multi_alias_one_physical(self) -> None:
        """Synthetic: multiple signal aliases → one grouped device with phys."""
        # Use real AC3 ESLS which may share stems; assert grouping count ≤ signal count
        run = ROOT / "workspace" / "_orindyac3_run" / "RUN"
        if not run.is_dir():
            self.skipTest("ORINDYAC3 RUN missing")
        eu = build_safety_evidence_union(run, "ORINDYAC3")
        counts = eu.get("counts") or {}
        signals = int(counts.get("signals") or 0)
        devices = int(counts.get("devices") or 0)
        self.assertGreater(signals, 0)
        self.assertGreater(devices, 0)
        self.assertLessEqual(devices, signals)
        for d in eu.get("devices") or []:
            self.assertTrue(
                d.get("physicalEndpoint") or _lift_phys(d),
                msg=f"{d.get('name')} lost physical after grouping",
            )


class TestCategoryPopulation(unittest.TestCase):
    def test_families_populate(self) -> None:
        run = ROOT / "workspace" / "_orindyac3_run" / "RUN"
        if not run.is_dir():
            self.skipTest("ORINDYAC3 RUN missing")
        model = build_safety_model(
            run_dir=run,
            machine="ORINDYAC3",
            transport_zones=[],
            areas=[],
            engineer_safety_build={},
        )
        c = model.get("counts") or {}
        self.assertGreater(c.get("estops", 0), 0)
        self.assertGreater(c.get("esr", 0), 0)
        self.assertGreater(c.get("esls", 0), 0)
        # Categories reconcile to site_devices
        total = (
            c.get("estops", 0)
            + c.get("esr", 0)
            + c.get("mcr", 0)
            + c.get("cs", 0)
            + c.get("esls", 0)
            + c.get("other_safety", 0)
        )
        self.assertEqual(total, c.get("site_devices") or c.get("devices"))


class TestControllerScoping(unittest.TestCase):
    def test_foreign_excluded_from_assignable(self) -> None:
        devices = [
            {"name": "3ES", "machine": "ORINDYAC3", "physicalEndpoint": "300.7"},
            {"name": "6ES", "machine": "ORINDYAC6", "physicalEndpoint": "600.7"},
            {
                "name": "SHARED_ES",
                "machine": "ORINDYAC6",
                "physicalEndpoint": "1.1",
                "crossControllerDependency": True,
            },
        ]
        part = partition_safety_inventory(devices, active_machine="ORINDYAC3")
        self.assertEqual(part["counts"][LOCAL_PHYSICAL], 1)
        self.assertEqual(part["counts"][UNRELATED_FOREIGN], 1)
        self.assertEqual(len(part["assignable"]), 1)
        self.assertEqual(part["assignable"][0]["name"], "3ES")
        self.assertEqual(len(part["remote_dependency"]), 1)

    def test_classify_blank_machine_is_local(self) -> None:
        self.assertEqual(
            classify_safety_device_scope(
                {"name": "ES100", "machine": ""},
                active_machine="ORINDYAC3",
            ),
            LOCAL_PHYSICAL,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

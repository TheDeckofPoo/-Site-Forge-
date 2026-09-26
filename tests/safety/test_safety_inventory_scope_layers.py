#!/usr/bin/env python3
"""ORI-033/030/041 — foreign exclusion, nonphysical, logical ESR."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_safety_inventory_scope import (  # noqa: E402
    LOCAL_PHYSICAL,
    UNRELATED_FOREIGN,
    partition_safety_inventory,
)
from fortna_safety_model import _classify_device  # noqa: E402

SAFETY_JS = ROOT / "dashboard" / "safety-build.js"


class TestForeignFlatAndDefaultExclusion(unittest.TestCase):
    def test_ab_partition_zero_cross_leak(self) -> None:
        devices = [
            {"name": "1ES1", "machine": "MACHINE_A", "physicalEndpoint": "1.1", "kind": "ESTOP"},
            {"name": "1ESLS1", "machine": "MACHINE_A", "physicalEndpoint": "1.2", "kind": "ESLS"},
            {"name": "7ES1", "machine": "MACHINE_B", "physicalEndpoint": "7.1", "kind": "ESTOP"},
            {"name": "7MCR1", "machine": "MACHINE_B", "physicalEndpoint": "7.4", "kind": "MCR"},
        ]
        part_a = partition_safety_inventory(devices, active_machine="MACHINE_A")
        names_a = {d["name"] for d in part_a["assignable"]}
        self.assertEqual(names_a, {"1ES1", "1ESLS1"})
        self.assertEqual(part_a["counts"][UNRELATED_FOREIGN], 2)
        # Flat/Default engineer layers must use the same assignable set
        flat_a = part_a["local_physical"]
        self.assertTrue(all(d["name"].startswith("1") for d in flat_a))
        part_b = partition_safety_inventory(devices, active_machine="MACHINE_B")
        names_b = {d["name"] for d in part_b["assignable"]}
        self.assertEqual(names_b, {"7ES1", "7MCR1"})
        self.assertEqual(names_a & names_b, set())

    def test_js_filters_active_machine_layers(self) -> None:
        src = SAFETY_JS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("filterDevicesToActiveMachine", src)
        self.assertIn("UNRELATED_FOREIGN", src)
        self.assertIn("ORI-033", src)


class TestNonphysicalNotAssignable(unittest.TestCase):
    def test_js_requires_physical_claim(self) -> None:
        src = SAFETY_JS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("deviceHasPhysicalClaim", src)
        self.assertIn("ORI-030", src)
        # Last-resort name-only promotion must be gone
        self.assertNotIn("Last-resort recovery: promote Safety-family rows", src)

    def test_name_only_estop_not_classified_enough(self) -> None:
        # Classifier may still label ESTOP, but assignable gate is JS phys claim
        self.assertEqual(_classify_device("ES1900BLA"), "ESTOP")
        self.assertEqual(_classify_device("ES532"), "ESTOP")


class TestLogicalEsrRejected(unittest.TestCase):
    def test_esr_not_ok_not_device(self) -> None:
        self.assertEqual(_classify_device("6ESR_NOT_OK"), "")
        self.assertEqual(_classify_device("1ESR_NOT_OK"), "")
        self.assertEqual(_classify_device("8ESR_NOT_OK"), "")

    def test_legitimate_esr_still_classifies(self) -> None:
        self.assertEqual(_classify_device("6ESR1"), "ESR")
        self.assertEqual(_classify_device("6ESR1_AUX"), "ESR")
        self.assertEqual(_classify_device("T_6ESR1_AUX"), "ESR")
        self.assertEqual(_classify_device("CP2_ESR1"), "ESR")

    def test_no_hardcoded_rialto_name(self) -> None:
        src = (ROOT / "tools" / "scripts" / "fortna_safety_model.py").read_text(
            encoding="utf-8", errors="replace"
        )
        # Generic MEM / _NOT_OK evidence gate — no site-specific if name == ...
        self.assertIn("_NOT_OK", src)
        self.assertNotIn('if name == "6ESR_NOT_OK"', src)
        self.assertNotIn("if name == '6ESR_NOT_OK'", src)


class TestDiscoveryInProgressGate(unittest.TestCase):
    def test_js_blocks_assign_while_loading(self) -> None:
        src = SAFETY_JS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("SAFETY_DISCOVERY_IN_PROGRESS", src)
        self.assertIn("safetyDiscoveryBlocking", src)
        self.assertIn("safetyDiscoveryInProgress", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)

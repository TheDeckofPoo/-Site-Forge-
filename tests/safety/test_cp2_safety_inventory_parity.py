#!/usr/bin/env python3
"""MSCATL_CP2 Safety inventory parity — proven I/O surfaced, INT interlock not ESR."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SF_REPO = Path(__file__).resolve().parents[2]
_SF_SCRIPTS = _SF_REPO / "tools" / "scripts"
if str(_SF_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SF_SCRIPTS))

from fortna_safety_model import (  # noqa: E402
    _classify_device,
    discover_safety_devices,
    safety_inventory_parity,
)

CP2_RUN = _SF_REPO / "workspace" / "_mscatl_peek" / "MSCATL_CP2" / "RUN"
MACHINE = "MSCATL_CP2"

REQUIRED = ("2ESR1", "2MCR1_AUX", "2ES", "ES1130", "ESLS1300")


@unittest.skipUnless((CP2_RUN / "FORTNA").is_dir(), "MSCATL_CP2 RUN peek missing")
class TestCp2SafetyInventoryParity(unittest.TestCase):
    def test_discover_includes_proven_io(self) -> None:
        by = {str(d.get("name") or ""): d for d in discover_safety_devices(CP2_RUN, MACHINE)}
        for name in REQUIRED:
            self.assertIn(name, by, f"missing {name}")
        self.assertEqual(by["2ESR1"].get("kind"), "ESR")
        self.assertEqual(by["2MCR1_AUX"].get("kind"), "MCR")
        self.assertEqual(by["2ES"].get("kind"), "ESTOP")
        self.assertEqual(by["ESLS1300"].get("kind"), "ESLS")

    def test_int_interlock_excluded_as_esr(self) -> None:
        self.assertEqual(_classify_device("INT-2ES2-1ESR1"), "")
        by = {str(d.get("name") or ""): d for d in discover_safety_devices(CP2_RUN, MACHINE)}
        self.assertNotIn("INT-2ES2-1ESR1", by)
        self.assertNotIn("INT_2ES2_1ESR1", by)
        for name, d in by.items():
            self.assertFalse(
                str(name).upper().startswith("INT"),
                f"interlock {name} must not be Safety inventory",
            )
            if "ESR" in str(name).upper() and d.get("kind") == "ESR":
                self.assertTrue(
                    re_is_real_esr(name),
                    f"{name} classified ESR but is not a real ESR device form",
                )

    def test_parity_foreign_stale_zero(self) -> None:
        report = safety_inventory_parity(CP2_RUN, MACHINE)
        counts = report.get("counts") or {}
        self.assertEqual(
            counts.get("foreign_stale"),
            0,
            f"foreign/stale={report.get('foreign_stale')}",
        )
        inv = {n.upper() for n in (report.get("surfaced_inventory") or [])}
        for name in REQUIRED:
            self.assertIn(name.upper(), inv)
        classified = {n.upper() for n in (report.get("safety_classified_io") or [])}
        self.assertNotIn("INT-2ES2-1ESR1", classified)
        self.assertNotIn("INT_2ES2_1ESR1", classified)
        print(
            f"CP2 parity: classified={counts.get('classified')} "
            f"inventory={counts.get('inventory')} "
            f"missing={counts.get('missing')} "
            f"foreign_stale={counts.get('foreign_stale')}"
        )


def re_is_real_esr(name: str) -> bool:
    import re

    u = str(name or "").strip().upper().replace("-", "_")
    return bool(
        re.match(r"^T_\d+ESR\d*", u)
        or re.match(r"^CP\d+_ESR\d*", u)
        or re.match(r"^\d+ESR\d*", u)
        or re.match(r"^ESR\d*", u)
        or re.search(r"(?:^|_)ESR\d*", u)
    )


if __name__ == "__main__":
    unittest.main(verbosity=2)

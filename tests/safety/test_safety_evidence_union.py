#!/usr/bin/env python3
"""Safety evidence UNION + SafetyDevice/SafetySignal grouping."""
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
    build_safety_evidence_union,
    discover_safety_devices,
    reconcile_safety_devices,
    safety_inventory_parity,
)

SHIP_RUN = (
    _SF_REPO
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOSHIP-RUN"
    / "RUN"
)
SHIP_MACHINE = "MSCRENOSHIP"

CP2_RUN = _SF_REPO / "workspace" / "_mscatl_peek" / "MSCATL_CP2" / "RUN"
CP2_MACHINE = "MSCATL_CP2"


class TestSafetyDeviceSignalGrouping(unittest.TestCase):
    def test_mcr_aux_t_alias_one_device(self) -> None:
        signals = [
            {"name": "2MCR1", "kind": "MCR"},
            {"name": "2MCR1_AUX", "kind": "MCR"},
            {"name": "T_2MCR1", "kind": "MCR"},
            {"name": "T_2MCR1_AUX", "kind": "MCR"},
        ]
        recon = reconcile_safety_devices(signals)
        self.assertEqual(recon["counts"]["devices"], 1)
        self.assertEqual(recon["counts"]["review_required"], 0)
        dev = recon["devices"][0]
        self.assertEqual(dev["kind"], "MCR")
        self.assertEqual(dev["stem"], "2MCR1")
        names = {str(s.get("name")) for s in (dev.get("signals") or [])}
        self.assertEqual(names, {"2MCR1", "2MCR1_AUX", "T_2MCR1", "T_2MCR1_AUX"})
        roles = {s["name"]: s["role"] for s in dev["signals"]}
        self.assertEqual(roles["2MCR1"], "PRIMARY")
        self.assertEqual(roles["2MCR1_AUX"], "AUX")
        self.assertEqual(roles["T_2MCR1"], "PRIMARY")
        self.assertEqual(roles["T_2MCR1_AUX"], "AUX")

    def test_similar_names_alone_do_not_group(self) -> None:
        # Different stems — must stay separate devices
        recon = reconcile_safety_devices(
            [
                {"name": "2MCR1", "kind": "MCR"},
                {"name": "3MCR1", "kind": "MCR"},
                {"name": "2MCR1_AUX", "kind": "MCR"},
            ]
        )
        stems = {d["stem"] for d in recon["devices"]}
        self.assertEqual(stems, {"2MCR1", "3MCR1"})
        by = {d["stem"]: d for d in recon["devices"]}
        self.assertEqual(len(by["2MCR1"]["signals"]), 2)
        self.assertEqual(len(by["3MCR1"]["signals"]), 1)

    def test_int_never_device(self) -> None:
        self.assertEqual(_classify_device("INT-2ES2-1ESR1"), "")
        self.assertEqual(_classify_device("INT_2ES2_1ESR1"), "")
        recon = reconcile_safety_devices(
            [
                {"name": "INT-2ES2-1ESR1", "kind": "ESR"},
                {"name": "2ESR1", "kind": "ESR"},
            ]
        )
        names = {d["name"] for d in recon["devices"]}
        self.assertIn("2ESR1", names)
        self.assertNotIn("INT-2ES2-1ESR1", names)
        self.assertTrue(
            any(
                r.get("disposition") == "REJECTED_INT_INTERLOCK"
                for r in recon["review_required"]
            )
        )


@unittest.skipUnless((SHIP_RUN / "project.cfg").is_file(), "MSCRENOSHIP RUN missing")
class TestMscrenoshipEvidenceUnion(unittest.TestCase):
    def test_foreign_session_rejection_parity_zero(self) -> None:
        report = safety_inventory_parity(SHIP_RUN, SHIP_MACHINE)
        counts = report.get("counts") or {}
        self.assertEqual(
            counts.get("foreign_stale"),
            0,
            f"foreign_stale={report.get('foreign_stale')}",
        )
        # PACK-owned MCR/ESR must not surface on SHIP
        inv = {n.upper() for n in (report.get("surfaced_inventory") or [])}
        for foreign in (
            "13MCR1",
            "13MCR1_AUX",
            "14MCR1",
            "T_13MCR1",
            "13ESR1_AUX",
        ):
            self.assertNotIn(foreign, inv)

    def test_union_sources_not_first_wins(self) -> None:
        union = build_safety_evidence_union(SHIP_RUN, SHIP_MACHINE)
        src = union.get("source_counts") or {}
        # Multiple sources contribute; inventory is the UNION of signals
        self.assertGreater(int(src.get("estop") or 0), 0)
        self.assertGreater(int(src.get("conveyor") or 0), 0)
        self.assertEqual(int((union.get("counts") or {}).get("mcr") or 0), 0)
        self.assertEqual(int((union.get("counts") or {}).get("esr") or 0), 0)
        flat = discover_safety_devices(SHIP_RUN, SHIP_MACHINE)
        self.assertEqual(len(flat), int((union.get("counts") or {}).get("signals") or 0))
        for d in flat:
            self.assertFalse(
                str(d.get("name") or "").upper().startswith("INT"),
                f"INT must never be inventory: {d.get('name')}",
            )


@unittest.skipUnless((CP2_RUN / "FORTNA").is_dir(), "MSCATL_CP2 RUN peek missing")
class TestCp2UnionSurfacesMcr(unittest.TestCase):
    def test_cp2_mcr_grouped(self) -> None:
        union = build_safety_evidence_union(CP2_RUN, CP2_MACHINE)
        self.assertGreaterEqual(int((union.get("counts") or {}).get("mcr") or 0), 1)
        # Prefer grouping 2MCR1 + AUX (+ T_) when present
        mcr_devs = [d for d in (union.get("devices") or []) if d.get("kind") == "MCR"]
        self.assertTrue(mcr_devs)
        stems = {d.get("stem") for d in mcr_devs}
        if "2MCR1" in stems:
            d = next(x for x in mcr_devs if x.get("stem") == "2MCR1")
            sigs = {str(s.get("name") or "").upper() for s in (d.get("signals") or [])}
            self.assertTrue(
                any("2MCR1" in s for s in sigs),
                f"expected 2MCR1 family in {sigs}",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)

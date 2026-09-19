#!/usr/bin/env python3
"""GATE 8 — EStop.Part→Conveyor proves machine ownership, not ES zone membership."""
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
import tempfile
import unittest
from pathlib import Path

SCRIPTS = _SF_SCRIPTS  # was: SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from fortna_estop_model import (  # noqa: E402
    OWN_PROVEN,
    OWN_REVIEW,
    OWN_UNKNOWN,
    build_estop_model,
)

VIRGIN = ROOT / "workspace" / "_virgin_orindy" / "RUN"
MACHINE = "ORINDYAC6"


def _write_mini_run(td: Path, machine: str = "TESTMACH") -> Path:
    """Synthetic RUN: EStop.Part → Conveyor.Machine_Name ownership only."""
    run = td / "RUN"
    fortna = run / "FORTNA"
    fortna.mkdir(parents=True)
    (run / "project.cfg").write_text("Site=TEST\n", encoding="utf-8")
    # Minimal Machine row so MachineClosure can seed
    (fortna / "Machine.asc").write_text(
        '"Machine_Name"~"Desc"\n'
        f"{machine}~Test machine\n",
        encoding="utf-8",
    )
    (fortna / "Conveyor.asc").write_text(
        '"IO_Name"~"Machine_Name"~"General_Description"\n'
        f"ES100~{machine}~E-stop device on target\n"
        "ES200~OTHERMACH~E-stop device on other controller\n"
        f"P100~{machine}~belt\n",
        encoding="utf-8",
    )
    (fortna / "EStop.asc").write_text(
        '"Desc"~"Part"~"Error"\n'
        "ES100~ES100~ES100\n"
        "ES200~ES200~ES200\n"
        "N/A~ES100~ES100\n"  # Desc blank-ish → name falls back to Part
        "MysteryZone~P100~MysteryZone\n"  # ZONE in name → candidate zone shell only
        "OrphanES~MISSINGPART~OrphanES\n",
        encoding="utf-8",
    )
    return run


class TestEstopPartOwnershipSynthetic(unittest.TestCase):
    def test_part_conveyor_machine_ownership_not_zone(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run = _write_mini_run(Path(td), "TESTMACH")
            model = build_estop_model(run, "TESTMACH")

            by_name = {d["name"]: d for d in model["devices"]}
            self.assertIn("ES100", by_name)
            d100 = by_name["ES100"]
            self.assertEqual(d100["part"], "ES100")
            self.assertEqual(d100["part_conveyor"], "ES100")
            self.assertEqual(d100["machine_ownership"], OWN_PROVEN)
            self.assertEqual(d100["zone_membership"], OWN_REVIEW)

            self.assertIn("ES200", by_name)
            d200 = by_name["ES200"]
            self.assertEqual(d200["part_conveyor"], "ES200")
            self.assertEqual(d200["machine_ownership"], OWN_REVIEW)
            self.assertEqual(d200["zone_membership"], OWN_REVIEW)

            # Desc=N/A falls back to Part for device name; still PROVEN via Part
            self.assertTrue(
                any(
                    d.get("part") == "ES100" and d.get("machine_ownership") == OWN_PROVEN
                    for d in model["devices"]
                )
            )

            orphan = by_name.get("OrphanES")
            self.assertIsNotNone(orphan)
            assert orphan is not None
            self.assertEqual(orphan["machine_ownership"], OWN_UNKNOWN)
            self.assertIsNone(orphan["part_conveyor"])
            self.assertEqual(orphan["zone_membership"], OWN_REVIEW)

            # No auto-minted {machine}_ESZone1 operational placeholder
            zone_names = {z["name"] for z in model["zones"]}
            self.assertNotIn("TESTMACH_ESZone1", zone_names)
            self.assertNotIn("TESTMACH_Area_ESZone1", zone_names)
            # Named ZONE row may appear as candidate shell, never generation_allowed
            for z in model["zones"]:
                self.assertFalse(z.get("generation_allowed"))
                self.assertEqual(z.get("membership"), [])

            self.assertIn(
                "Jamzones / Areas are not automatic ES zones",
                model.get("policy") or [],
            )
            self.assertTrue(
                any("Default Safety" in p for p in (model.get("policy") or []))
            )
            self.assertFalse(model["safety_generation_gate"]["allowed"])
            self.assertGreaterEqual(model["counts"]["machine_ownership_proven"], 1)


@unittest.skipUnless((VIRGIN / "project.cfg").is_file(), "virgin ORINDYAC6 RUN missing")
class TestEstopPartOwnershipLive(unittest.TestCase):
    def test_orindyac6_part_ownership_smoke(self) -> None:
        model = build_estop_model(VIRGIN, MACHINE)
        self.assertEqual(model["zones"], [])
        proven = [
            d
            for d in model["devices"]
            if d.get("machine_ownership") == OWN_PROVEN
        ]
        self.assertGreater(len(proven), 0)
        for d in proven:
            self.assertEqual(d.get("zone_membership"), OWN_REVIEW)
            self.assertTrue(d.get("part"))
            self.assertTrue(d.get("part_conveyor"))
        # Spot-check ES600 if present
        es600 = next((d for d in proven if d.get("name") == "ES600"), None)
        if es600 is not None:
            self.assertEqual(es600["part"], "ES600")
            self.assertEqual(es600["part_conveyor"], "ES600")
            self.assertEqual(es600["machine_ownership"], OWN_PROVEN)
            self.assertEqual(es600["zone_membership"], OWN_REVIEW)
        self.assertNotIn(
            f"{MACHINE}_ESZone1",
            {z["name"] for z in model["zones"]},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

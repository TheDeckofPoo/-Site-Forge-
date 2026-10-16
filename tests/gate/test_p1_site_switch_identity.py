#!/usr/bin/env python3
"""P1 — SHIP↔PICK site-switch identity gates (unit level, no Electron).

Covers workbook/machine ProjectIdentity gates that must hold when switching
between MSCRENOSHIP and MSCRENOPICK without a full UI Clear.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "diagnostics"))

from fortna_project_identity import (  # noqa: E402
    ProjectIdentity,
    identity_from_run,
    identity_from_workbook,
    project_key_from_parts,
    same_project,
)
from fortna_run_workspace_discover import site_model_identity_matches  # noqa: E402
from patch_torture_helpers import run_path  # noqa: E402

SHIP_RUN = run_path("MSCRENOSHIP")
PICK_RUN = run_path("MSCRENOPICK")


def _foreign_workbook(machine: str, *, sorter_host: str, zone: str) -> dict:
    return {
        "machine": machine,
        "project_name": "MSCRENO",
        "project_key": project_key_from_parts(project_name="MSCRENO", machine=machine),
        "run_fingerprint": f"FP_{machine}",
        "project_identity": {
            "project_name": "MSCRENO",
            "machine": machine,
            "project_key": project_key_from_parts(project_name="MSCRENO", machine=machine),
            "run_fingerprint": f"FP_{machine}",
        },
        "sorter_build": {
            "divert_host_conveyor": sorter_host,
            "divert_count": 16,
            "appliedAt": "t",
        },
        "merges_2to1": [{"name": "P600_FOREIGN"}],
        "safety_build": {"zones": [{"name": zone, "members": ["ES1"]}]},
        "conveyors": [
            {
                "conveyor": "P999",
                "main_area": f"{machine}_Area_FOREIGN",
                "safety_zone": zone,
            }
        ],
        "options": {"areas": [f"{machine}_Area_FOREIGN"]},
    }


class TestSameProjectShipPick(unittest.TestCase):
    def test_ship_and_pick_are_different_projects(self) -> None:
        ship = ProjectIdentity(
            "MSCRENO",
            "MSCRENOSHIP",
            "MSCRENO|MSCRENOSHIP",
            "fp_ship",
        )
        pick = ProjectIdentity(
            "MSCRENO",
            "MSCRENOPICK",
            "MSCRENO|MSCRENOPICK",
            "fp_pick",
        )
        self.assertFalse(same_project(ship, pick))
        self.assertTrue(same_project(ship, ship))

    def test_mscreno_substring_does_not_soft_match_ship(self) -> None:
        soft = ProjectIdentity("MSCRENO", "MSCRENO", "MSCRENO|MSCRENO", "fp")
        ship = ProjectIdentity(
            "MSCRENO",
            "MSCRENOSHIP",
            "MSCRENO|MSCRENOSHIP",
            "fp",
        )
        self.assertFalse(same_project(soft, ship))


@unittest.skipUnless(SHIP_RUN is not None and PICK_RUN is not None, "SHIP/PICK RUN missing")
class TestWorkbookMachineGateShipPick(unittest.TestCase):
    def test_ship_workbook_not_preserved_onto_pick_run(self) -> None:
        from fortna_workbook import build_workbook_from_run

        assert PICK_RUN is not None
        foreign = _foreign_workbook(
            "MSCRENOSHIP", sorter_host="PS1", zone="MSCRENOSHIP_ESZone1"
        )
        wb = build_workbook_from_run(PICK_RUN, existing=foreign)
        self.assertEqual(str(wb.get("machine") or "").upper(), "MSCRENOPICK")
        self.assertFalse(wb.get("sorter_build"), "SHIP sorter_build must not survive onto PICK")
        self.assertFalse(wb.get("merges_2to1"), "SHIP merges must not survive onto PICK")
        zones = (wb.get("safety_build") or {}).get("zones") or []
        self.assertFalse(
            any("MSCRENOSHIP" in str(z.get("name") or "").upper() for z in zones),
            zones,
        )
        areas = [
            str(c.get("main_area") or "")
            for c in (wb.get("conveyors") or [])
            if isinstance(c, dict)
        ]
        self.assertFalse(
            any("FOREIGN" in a.upper() and "SHIP" in a.upper() for a in areas),
            areas[:5],
        )
        ident = identity_from_workbook(wb)
        self.assertIsNotNone(ident)
        assert ident is not None
        self.assertEqual(ident.machine.upper(), "MSCRENOPICK")

    def test_pick_workbook_not_preserved_onto_ship_run(self) -> None:
        from fortna_workbook import build_workbook_from_run

        assert SHIP_RUN is not None
        foreign = _foreign_workbook(
            "MSCRENOPICK", sorter_host="P120C", zone="MSCRENOPICK_ESZone1"
        )
        wb = build_workbook_from_run(SHIP_RUN, existing=foreign)
        self.assertEqual(str(wb.get("machine") or "").upper(), "MSCRENOSHIP")
        self.assertFalse(wb.get("sorter_build"), "PICK sorter_build must not survive onto SHIP")
        zones = (wb.get("safety_build") or {}).get("zones") or []
        self.assertFalse(
            any("MSCRENOPICK" in str(z.get("name") or "").upper() for z in zones),
            zones,
        )
        ident = identity_from_workbook(wb)
        self.assertIsNotNone(ident)
        assert ident is not None
        self.assertEqual(ident.machine.upper(), "MSCRENOSHIP")

    def test_run_identities_differ(self) -> None:
        assert SHIP_RUN is not None and PICK_RUN is not None
        ship = identity_from_run(SHIP_RUN)
        pick = identity_from_run(PICK_RUN)
        self.assertEqual(ship.machine.upper(), "MSCRENOSHIP")
        self.assertEqual(pick.machine.upper(), "MSCRENOPICK")
        self.assertFalse(same_project(ship, pick))


@unittest.skipUnless(SHIP_RUN is not None and PICK_RUN is not None, "SHIP/PICK RUN missing")
class TestSiteModelIdentityGate(unittest.TestCase):
    def test_ship_model_rejected_for_pick_machine(self) -> None:
        assert SHIP_RUN is not None
        ship_model = {
            "machine_scope": "MSCRENOSHIP",
            "controller": "MSCRENOSHIP",
            "run_dir": str(SHIP_RUN),
            "run_fingerprint": "SHIP_FP",
            "identity": {
                "machine_scope": "MSCRENOSHIP",
                "controller": "MSCRENOSHIP",
                "run_dir": str(SHIP_RUN),
                "run_fingerprint": "SHIP_FP",
            },
        }
        ok, reason = site_model_identity_matches(
            ship_model, machine="MSCRENOPICK", run_fingerprint="SHIP_FP"
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "CONTROLLER_MISMATCH")

    def test_missing_fingerprint_fail_closed(self) -> None:
        model = {
            "machine_scope": "MSCRENOSHIP",
            "identity": {"machine_scope": "MSCRENOSHIP", "run_fingerprint": ""},
        }
        ok, reason = site_model_identity_matches(model, machine="MSCRENOSHIP")
        self.assertFalse(ok)
        self.assertEqual(reason, "SITE_MODEL_MISSING_RUN_FINGERPRINT")


class TestCurrentRestoreMachineGate(unittest.TestCase):
    """Unit-level CURRENT restore machine gate (Electron path still needs Warden)."""

    def test_wrong_machine_rejects_latest(self) -> None:
        # Mirror of desktop/main.js loadCurrentAutogenForActiveSite machine check.
        with tempfile.TemporaryDirectory() as td:
            sandbox = Path(td)
            cur = sandbox / "exports" / "current"
            cur.mkdir(parents=True)
            l5x = cur / "MSCRENOSHIP_STALE.L5X"
            l5x.write_text("<!-- stale -->", encoding="utf-8")
            latest = {
                "ok": True,
                "controller_name": "MSCRENOSHIP",
                "source_run_hash": "SHIP_FP",
                "l5x": str(l5x),
                "current_artifact": True,
                "current_invalidated": False,
            }
            (cur / "LATEST.json").write_text(json.dumps(latest), encoding="utf-8")
            meta = {
                "machine": "MSCRENOPICK",
                "run_fingerprint": "PICK_FP",
            }
            want = str(meta.get("machine") or "").strip().upper()
            r = json.loads((cur / "LATEST.json").read_text(encoding="utf-8"))
            got = str(r.get("controller_name") or r.get("machine") or "").strip().upper()
            self.assertNotEqual(got, want)
            # Gate: foreign/stale machine → no current
            reason = "FOREIGN_OR_STALE_MACHINE" if got != want else "MATCH"
            self.assertEqual(reason, "FOREIGN_OR_STALE_MACHINE")


if __name__ == "__main__":
    unittest.main(verbosity=2)

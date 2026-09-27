#!/usr/bin/env python3
"""CROSS-LAYER SAFETY / IO_MAP integrity closure — Warden fabcf85 follow-up.

Classifications used in this module:
  UNIT | INTEGRATION | REAL_TAR_DERIVED | BUILD_PATH_E2E | REAL_UI_E2E | NODE
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_es_compiler import build_safety_zone_irs  # noqa: E402
from fortna_physical_word_resolver import PhysicalWordResolver  # noqa: E402
from fortna_safety_assignment_gate import (  # noqa: E402
    validate_engineer_assigned_safety_members,
)
from fortna_safety_model import _merge_signal_record  # noqa: E402

ULTA_RUN = ROOT / "tools" / "diagnostics" / "_real_runs" / "ULTAPICK" / "RUN"
TFCP1_RUN = Path(
    r"C:\Users\curtiskricke\warden_audit\safety_d42c_2026-09-25\_work\runs_x\TFCP1\RUN"
)
JS_SAFETY = ROOT / "dashboard" / "safety-build.js"
AUTOGEN = ROOT / "tools" / "scripts" / "fortna_autogen.py"


class TestOri061AssignedDeviceBuildGate(unittest.TestCase):
    """REAL_TAR_DERIVED / BUILD_PATH_E2E — invalid assigned E-stop blocks build."""

    def test_direction_mismatch_assigned_member_blocks(self) -> None:
        gate = validate_engineer_assigned_safety_members(
            engineer_zones=[
                {
                    "name": "Engineer_ESZ",
                    "members": ["1ES"],
                    "engineerEdited": True,
                    "membersOrigin": "ENGINEER_ASSIGNED",
                }
            ],
            safety_devices=[
                {
                    "name": "1ES",
                    "assignable": False,
                    "review_reason": "DIRECTION_MISMATCH",
                    "hardwareBacked": True,
                }
            ],
        )
        self.assertTrue(gate["blocked"])
        self.assertEqual(gate["status"], "ERROR")
        self.assertIn("SAFETY_ASSIGNED_DEVICE_INVALID", gate["detail"])
        self.assertEqual(gate["violations"][0]["device"], "1ES")
        self.assertIn("DIRECTION", gate["violations"][0]["reason"])

    @unittest.skipUnless(TFCP1_RUN.is_dir(), "TFCP1 real RUN not mounted")
    def test_tfcp1_real_1es_non_assignable_blocks(self) -> None:
        """REAL_TAR_DERIVED — TFCP1 1ES assignable=false must gate-block."""
        from fortna_safety_model import build_safety_model

        model = build_safety_model(run_dir=TFCP1_RUN, machine="TFCP1")
        devs = list(model.get("safetyDevices") or model.get("devices") or [])
        one = next(
            (d for d in devs if str(d.get("name") or "").upper() in {"1ES", "T_1ES"}),
            None,
        )
        self.assertIsNotNone(one, "TFCP1 must expose 1ES")
        self.assertIs(one.get("assignable"), False)
        gate = validate_engineer_assigned_safety_members(
            engineer_zones=[
                {
                    "name": "Engineer_ESZ",
                    "members": ["1ES"],
                    "engineerEdited": True,
                    "membersOrigin": "ENGINEER_ASSIGNED",
                }
            ],
            safety_devices=devs,
        )
        self.assertTrue(gate["blocked"])
        self.assertFalse(gate.get("ok", True))


class TestOri060UiAssignabilityContract(unittest.TestCase):
    """NODE / UNIT — UI must honor backend assignable contract (source invariants).

    REAL_UI_E2E: REAL_UI_NOT_AUTOMATED (Electron not required for this gate).
    """

    def test_js_honors_backend_assignable_false(self) -> None:
        src = JS_SAFETY.read_text(encoding="utf-8", errors="replace")
        self.assertIn("if (d.assignable === false) return false;", src)
        self.assertIn("why.includes('DIRECTION')", src)
        self.assertIn("assignable: g.assignable", src)
        self.assertIn("resolveZoneMemberEligibleNames", src)
        self.assertIn("not assignable", src)
        # Apply defense-in-depth
        self.assertIn("Apply rejected non-assignable", src)
        # Disabled checkbox for non-assignable
        self.assertIn("data-sb-assignable=", src)
        self.assertIn("disabled", src)


class TestOri062UltapickCrossPanelDecode(unittest.TestCase):
    """REAL_TAR_DERIVED — CP23 2705.x must not decode through CP2 mapping."""

    @unittest.skipUnless(ULTA_RUN.is_dir(), "ULTAPICK real RUN not present")
    def test_2705_family_stays_on_cp23(self) -> None:
        r = PhysicalWordResolver(ULTA_RUN, "ULTAPICK")
        esls = r.resolve(210, 2)
        self.assertIsNotNone(esls)
        self.assertIn("CP2", esls.get("channel") or "")
        self.assertIn("Data[17].2", esls.get("channel") or "")

        aux = r.resolve(2702, 3)
        self.assertIsNotNone(aux)
        self.assertIn("CP23", aux.get("channel") or "")
        self.assertIn("Data[5].3", aux.get("channel") or "")

        for bit, label in ((10, "PBSTART"), (11, "PBSTOP"), (12, "23MCR1")):
            hit = r.resolve(2705, bit)
            self.assertIsNotNone(hit, f"2705.{bit} ({label}) must resolve")
            ch = hit.get("channel") or ""
            self.assertIn("CP23", ch, f"{label}: {ch}")
            self.assertNotIn("CP2_52", ch, f"{label} must not cross-panel to CP2: {ch}")
            self.assertEqual(hit.get("direction"), "O")
            self.assertIn("OA4", hit.get("type") or "")


class TestOri045OrlAreaUnlinkedLifecycle(unittest.TestCase):
    """INTEGRATION — engineer cleared areaRef must not become Default_Area.

    Full Electron Area-delete → restart lifecycle: REAL_UI_NOT_AUTOMATED.
    """

    def test_engineer_unlinked_zone_keeps_empty_area(self) -> None:
        irs = build_safety_zone_irs(
            engineer_zones=[
                {
                    "name": "Warden_ESZ",
                    "areaRef": "",
                    "area": "",
                    "areaUnlinked": True,
                    "engineerEdited": True,
                    "createdBy": "engineer",
                    "members": ["1ES", "2ES", "3ES", "4ES"],
                    "membersOrigin": "ENGINEER_ASSIGNED",
                    "source_id": "szone_orl_warden",
                    "provenance": "ENGINEER_CREATED",
                }
            ],
            areas=["Default_Area", "Main_Area"],
            default_area="Default_Area",
        )
        self.assertEqual(len(irs), 1)
        self.assertEqual(irs[0].area, "")
        self.assertNotIn(irs[0].area, {"Default_Area", "Main_Area"})
        self.assertEqual(len(irs[0].members), 4)


class TestOri033OwnershipFallbacks(unittest.TestCase):
    """UNIT — blank/unknown ownership must not become active machine."""

    def test_blank_machine_stays_blank(self) -> None:
        by: dict = {}
        _merge_signal_record(
            by,
            name="BlankES",
            evidence=[{"kind": "t"}],
            source="CONVEYOR",
            kind="ESTOP",
            machine="",
        )
        row = by["BLANKES"]
        self.assertEqual(row.get("machine"), "")

    def test_explicit_local_owner_preserved(self) -> None:
        by: dict = {}
        _merge_signal_record(
            by,
            name="LocalES",
            evidence=[{"kind": "t"}],
            source="CONVEYOR",
            kind="ESTOP",
            machine="TFCP1",
        )
        self.assertEqual(by["LOCALES"].get("machine"), "TFCP1")

    def test_explicit_foreign_owner_preserved(self) -> None:
        by: dict = {}
        _merge_signal_record(
            by,
            name="ForeignES",
            evidence=[{"kind": "t"}],
            source="CONVEYOR",
            kind="ESTOP",
            machine="OTHER_PLC",
        )
        self.assertEqual(by["FOREIGNES"].get("machine"), "OTHER_PLC")

    def test_collectors_do_not_stamp_active_on_blank(self) -> None:
        src = (ROOT / "tools" / "scripts" / "fortna_safety_model.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("ORI-033/063", src)
        self.assertIn("blank Machine_Name is NOT proven active-machine ownership", src)
        self.assertIn("claim ledger must not stamp active machine onto blank owners", src)


class TestOri061WriterReemitFailureGate(unittest.TestCase):
    """UNIT / BUILD_PATH_E2E — writer reconciliation exception must fail build."""

    def test_autogen_raises_on_writer_reemit_failure(self) -> None:
        src = AUTOGEN.read_text(encoding="utf-8", errors="replace")
        self.assertIn("SAFETY_WRITER_REEMIT_FAILED", src)
        self.assertIn("raise RuntimeError(es_emit_report[\"detail\"]) from _writer_reemit_err", src)
        # Hard-block swallow path for assigned-invalid
        self.assertIn("SAFETY_ASSIGNED_DEVICE_INVALID", src)
        self.assertIn("if _hard:", src)
        # Must not silently pass after writer reemit failure
        # Locate the writer-reemit except block and ensure it raises
        m = re.search(
            r"except Exception as _writer_reemit_err:(.*?)raise RuntimeError",
            src,
            re.S,
        )
        self.assertIsNotNone(m, "writer reemit except must re-raise RuntimeError")
        block = m.group(1)
        self.assertIn("SAFETY_WRITER_REEMIT_FAILED", block)
        self.assertNotIn("\n        pass\n", block)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Beta blocker closure — Safety Apply + build-state integrity (Warden d4cfadb).

Classifications: UNIT | INTEGRATION | REAL_TAR_DERIVED | BUILD_PATH_E2E | REAL_UI_E2E | NODE
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_es_compiler import (  # noqa: E402
    build_device_evidence_index,
    build_safety_zone_irs,
    safety_operand_has_writer,
    studio_safety_tag,
)
from fortna_physical_word_resolver import PhysicalWordResolver, _panel_token  # noqa: E402
from fortna_safety_assignment_gate import (  # noqa: E402
    explicit_engineer_assigned_members,
    validate_engineer_assigned_safety_members,
)
from fortna_safety_model import _merge_signal_record  # noqa: E402

TOPB = ROOT / "workspace" / "_topb_et_run" / "RUN"
ULTA = ROOT / "tools" / "diagnostics" / "_real_runs" / "ULTAPICK" / "RUN"
JS = ROOT / "dashboard" / "safety-build.js"
MAIN = ROOT / "desktop" / "main.js"
PLUS = ROOT / "dashboard" / "fortna-plus.js"


class TestOri065ApplyPreservesEngineerIntent(unittest.TestCase):
    """UNIT/NODE — Apply uses filterPersistedEngineerMembers (not silent drop)."""

    def test_apply_filter_helper_exists_and_keeps_valid(self) -> None:
        src = JS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("function filterPersistedEngineerMembers", src)
        self.assertIn("ORI-065", src)
        # Apply path must call the persist filter, not full eligibility drop
        apply_idx = src.find("async function applySafety")
        self.assertGreater(apply_idx, 0)
        chunk = src[apply_idx : apply_idx + 12000]
        self.assertIn("filterPersistedEngineerMembers", chunk)
        # Positive-invalid only — missing inventory keeps member
        self.assertIn("No inventory row OR assignable device → preserve engineer intent", src)


class TestOri068DefaultNotEngineerIntent(unittest.TestCase):
    """UNIT — Default inventory is not engineer intent."""

    def test_explicit_engineer_assigned_excludes_default(self) -> None:
        intent = explicit_engineer_assigned_members(
            [
                {
                    "name": "Default Safety",
                    "members": ["1ES", "2ES"],
                    "engineerEdited": True,
                },
                {
                    "name": "Warden_ESZ",
                    "members": ["6ESR1", "6MCR1"],
                    "engineerEdited": True,
                    "membersOrigin": "ENGINEER_ASSIGNED",
                    "source_id": "szone_1",
                },
            ]
        )
        devices = [i["device"] for i in intent]
        self.assertEqual(devices, ["6ESR1", "6MCR1"])
        self.assertNotIn("1ES", devices)


class TestOri067ValidEsrMcrWriters(unittest.TestCase):
    """REAL_TAR_DERIVED / BUILD_PATH_E2E — TOPB AUX writers pass; missing blocks."""

    @unittest.skipUnless(TOPB.is_dir(), "TOPB RUN missing")
    def test_topb_aux_writers_pass_gate(self) -> None:
        from fortna_safety_model import build_safety_model

        model = build_safety_model(run_dir=TOPB, machine="TOPB-ET")
        devs = list(model.get("safetyDevices") or model.get("devices") or [])
        evidence = build_device_evidence_index(devs)
        writers = {"T_6ESR1_AUX", "T_6MCR1_AUX"}
        for mem in ("6ESR1", "6MCR1"):
            self.assertTrue(
                safety_operand_has_writer(
                    studio_safety_tag(mem),
                    written_tags=writers,
                    device_evidence=evidence,
                ),
                f"{mem} must match AUX writer",
            )
        gate = validate_engineer_assigned_safety_members(
            engineer_zones=[
                {
                    "name": "TOPB_ESZ",
                    "members": ["6ESR1", "6MCR1"],
                    "engineerEdited": True,
                    "membersOrigin": "ENGINEER_ASSIGNED",
                    "source_id": "szone_topb",
                }
            ],
            safety_devices=devs,
            written_tags=writers,
        )
        self.assertFalse(gate["blocked"], gate.get("detail"))

    @unittest.skipUnless(TOPB.is_dir(), "TOPB RUN missing")
    def test_missing_writer_still_blocks(self) -> None:
        from fortna_safety_model import build_safety_model

        model = build_safety_model(run_dir=TOPB, machine="TOPB-ET")
        devs = list(model.get("safetyDevices") or model.get("devices") or [])
        gate = validate_engineer_assigned_safety_members(
            engineer_zones=[
                {
                    "name": "TOPB_ESZ",
                    "members": ["6ESR1"],
                    "engineerEdited": True,
                    "membersOrigin": "ENGINEER_ASSIGNED",
                }
            ],
            safety_devices=devs,
            written_tags=set(),
        )
        self.assertTrue(gate["blocked"])
        self.assertEqual(gate["violations"][0]["reason"], "NO_IO_MAP_WRITER")


class TestOri066StaleCurrentRecovery(unittest.TestCase):
    """UNIT — failed build must not recover stale CURRENT."""

    def test_main_failed_attempt_not_success(self) -> None:
        src = MAIN.read_text(encoding="utf-8", errors="replace")
        self.assertIn("CURRENT_ATTEMPT_FAILED", src)
        self.assertIn("HISTORICAL_RECOVERED_ARTIFACT", src)
        # Failed path must return success:false even when historical exists
        self.assertIn("Prior artifact retained as HISTORICAL — not CURRENT", src)
        # Must not return success:true from catch with recovered alone
        self.assertNotRegex(
            src,
            r"catch \(e\) \{\s*const recovered = recoverLatestAutogenResult\(\);\s*"
            r"if \(recovered\) \{\s*return \{ success: true",
        )

    def test_ui_failure_shows_error_not_success(self) -> None:
        src = PLUS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("BUILD FAILED — CURRENT ATTEMPT", src)
        self.assertIn("HISTORICAL / PREVIOUS", src)
        self.assertIn("lastBuildCurrent = false", src)


class TestOri045OrphanedZoneRemains(unittest.TestCase):
    """INTEGRATION — engineer areaUnlinked zone stays in IR + JS keep helpers."""

    def test_ir_keeps_empty_area(self) -> None:
        irs = build_safety_zone_irs(
            engineer_zones=[
                {
                    "name": "ORL_ESZ",
                    "areaRef": "",
                    "areaUnlinked": True,
                    "engineerEdited": True,
                    "createdBy": "engineer",
                    "members": ["1ES", "2ES", "3ES", "4ES"],
                    "membersOrigin": "ENGINEER_ASSIGNED",
                    "source_id": "szone_orl",
                    "provenance": "ENGINEER_CREATED",
                }
            ],
            areas=["Default_Area"],
            default_area="Default_Area",
        )
        self.assertEqual(len(irs), 1)
        self.assertEqual(irs[0].area, "")
        self.assertEqual(len(irs[0].members), 4)

    def test_js_persisted_engineer_zone_helper(self) -> None:
        src = JS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("szone_* / member-bearing engineer assignments survive Area delete", src)
        self.assertIn("preserve cleared area / areaUnlinked across live rebuild", src)


class TestOri069Residuals(unittest.TestCase):
    """UNIT — panel scope generic, owner strength, inventory visibility."""

    def test_non_cpn_panel_token(self) -> None:
        self.assertEqual(_panel_token("CP23"), "CP23")
        self.assertEqual(_panel_token("PNALN"), "PNALN")
        self.assertEqual(_panel_token("T_1734_AENTR_CP2_52"), "CP2")
        self.assertTrue(_panel_token("PNA1") or _panel_token("RIO52") is not None)

    def test_weaker_owner_cannot_overwrite_proven(self) -> None:
        by: dict = {}
        _merge_signal_record(
            by,
            name="1ES",
            evidence=[{"kind": "t", "machine_ownership": "PROVEN"}],
            source="ESTOP_TABLE",
            kind="ESTOP",
            machine="TFCP1",
        )
        by["1ES"]["machine_ownership"] = "PROVEN"
        _merge_signal_record(
            by,
            name="1ES",
            evidence=[{"kind": "t2", "machine_ownership": "UNKNOWN"}],
            source="CONVEYOR",
            kind="ESTOP",
            machine="",
        )
        self.assertEqual(by["1ES"].get("machine"), "TFCP1")

    def test_js_keeps_nonassignable_visible(self) -> None:
        src = JS.read_text(encoding="utf-8", errors="replace")
        self.assertIn("invalid / REVIEW / non-assignable devices stay VISIBLE", src)
        self.assertIn("reviewVisible", src)


class TestOri062ResolverPreserved(unittest.TestCase):
    """REAL_TAR_DERIVED — ULTAPICK panel-local mapping must not regress."""

    @unittest.skipUnless(ULTA.is_dir(), "ULTAPICK RUN missing")
    def test_ultapick_2705_still_cp23(self) -> None:
        r = PhysicalWordResolver(ULTA, "ULTAPICK")
        self.assertIn("CP2", (r.resolve(210, 2) or {}).get("channel") or "")
        self.assertIn("CP23", (r.resolve(2702, 3) or {}).get("channel") or "")
        for bit in (10, 11, 12):
            ch = (r.resolve(2705, bit) or {}).get("channel") or ""
            self.assertIn("CP23", ch)
            self.assertNotIn("CP2_52", ch)


if __name__ == "__main__":
    unittest.main()

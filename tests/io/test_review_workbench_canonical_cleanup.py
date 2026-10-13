#!/usr/bin/env python3
"""P0 Review Workbench / Safety canonical-state cleanup.

1. Proven LOCAL_PHYSICAL Pick Safety devices are NOT unresolved Workbench items
2. FOREIGN / GUI_ONLY / INTERNAL are not local critical review
3. Engineer confirmations compose (CONFIRM_LOCAL then CONFIRM_SAFETY keeps endpoint)
4. Safety Build consumes engineer-confirmed LOCAL+Safety+endpoint
5. Source conservation / physical resolution remain truthful
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))

from fortna_io_engineer_confirm import (  # noqa: E402
    CONFIRM_LOCAL,
    CONFIRM_SAFETY,
    apply_confirmations_to_safety_devices,
    confirm_physical_device,
    load_confirmations,
)
from fortna_io_review_workbench import (  # noqa: E402
    _needs_local_engineer_review,
    build_workbench,
)
from fortna_run_io_source_ledger import (  # noqa: E402
    STATUS_FOREIGN,
    STATUS_GUI_ONLY,
    STATUS_MAPPED,
    build_canonical_device_ledger,
    build_source_evidence_ledger,
)
from fortna_safety_inventory_scope import (  # noqa: E402
    LOCAL_PHYSICAL,
    UNRELATED_FOREIGN,
    classify_safety_device_scope,
)

MSC_PICK_RUN = (
    REPO
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
    / "RUN"
)
MSC_SHIP_RUN = (
    REPO
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOSHIP-RUN"
    / "RUN"
)
MSC_PACK_RUN = (
    REPO
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOPACK-RUN"
    / "RUN"
)
PHYS_MAP = Path(
    r"C:\dev\worktree\FortnaPlus-transport-active\exports\delivery_gate_20261002"
    r"\active_control_gen\ori111_repair_1\physical_io_map.csv"
)
if not PHYS_MAP.is_file():
    PHYS_MAP = None

PICK_LOCAL = ("ESPB2", "ESPB24", "ESPB32", "ESLS2")


@unittest.skipUnless((MSC_PICK_RUN / "project.cfg").is_file(), "MSCRENOPICK RUN missing")
class TestReviewWorkbenchExceptionTruth(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        led = build_source_evidence_ledger(MSC_PICK_RUN, "MSCRENOPICK")
        cls.canon_no_map = build_canonical_device_ledger(
            led,
            machine="MSCRENOPICK",
            run_dir=MSC_PICK_RUN,
            physical_io_map_csv=None,
            apply_engineer_confirmations=False,
        )
        cls.canon_map = build_canonical_device_ledger(
            led,
            machine="MSCRENOPICK",
            run_dir=MSC_PICK_RUN,
            physical_io_map_csv=PHYS_MAP,
            apply_engineer_confirmations=False,
        )
        cls.by_no_map = {
            d["canonical_name"].upper(): d for d in cls.canon_no_map["devices"]
        }
        cls.by_map = {d["canonical_name"].upper(): d for d in cls.canon_map["devices"]}

    def test_pick_locals_have_endpoints(self) -> None:
        for name in PICK_LOCAL:
            d = self.by_no_map[name]
            self.assertTrue(d.get("physical_endpoint"), name)
            self.assertEqual(d.get("ownership"), "LOCAL", name)

    def test_pick_locals_not_workbench_exceptions_even_without_map(self) -> None:
        """Map-CSV lag must not keep LOCAL+endpoint as critical unresolved review."""
        for name in PICK_LOCAL:
            d = self.by_no_map[name]
            self.assertEqual(d.get("final_status"), "REVIEW_REQUIRED", name)
            self.assertFalse(_needs_local_engineer_review(d), name)

    def test_pick_locals_mapped_when_map_present(self) -> None:
        if PHYS_MAP is None:
            self.skipTest("physical_io_map.csv unavailable")
        for name in PICK_LOCAL:
            d = self.by_map[name]
            self.assertEqual(d.get("final_status"), STATUS_MAPPED, d)
            self.assertFalse(_needs_local_engineer_review(d), name)

    def test_workbench_excludes_pick_locals(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            empty = Path(td) / "engineer_io_confirmations.json"
            empty.write_text(json.dumps({"version": 1, "confirmations": {}}))
            wb = build_workbench(
                machine="MSCRENOPICK",
                run_dir=MSC_PICK_RUN,
                physical_io_map_csv=None,
                confirmations_path=empty,
            )
            self.assertTrue(wb.get("ok"), wb)
            names = {
                str(i.get("canonical_name") or "").upper()
                for i in (wb.get("items") or [])
            }
            for name in PICK_LOCAL:
                self.assertNotIn(name, names, f"{name} must not be unresolved review")
            self.assertEqual(wb.get("critical_review_count"), 0)

    def test_foreign_ship_not_local_critical_review(self) -> None:
        d = self.by_no_map["ESPB20"]
        self.assertEqual(d.get("final_status"), STATUS_FOREIGN, d)
        self.assertFalse(_needs_local_engineer_review(d))
        self.assertEqual(
            classify_safety_device_scope(d, active_machine="MSCRENOPICK"),
            UNRELATED_FOREIGN,
        )

    def test_gui_only_not_local_critical_review(self) -> None:
        d = self.by_no_map["ESPB1O"]
        self.assertEqual(d.get("final_status"), STATUS_GUI_ONLY, d)
        self.assertFalse(_needs_local_engineer_review(d))

    def test_source_conservation_100(self) -> None:
        if PHYS_MAP is None:
            self.skipTest("physical_io_map.csv unavailable")
        self.assertEqual(self.canon_map.get("SOURCE_CONSERVATION_PCT"), 100.0)
        self.assertTrue(self.canon_map.get("source_conservation_ok"))
        self.assertEqual(self.canon_map.get("PHYSICAL_DEVICE_RESOLUTION_PCT"), 100.0)
        self.assertEqual(self.canon_map.get("critical_unresolved_count"), 0)
        # Four known local Pick Safety devices remain physically mapped.
        mapped = {
            d["canonical_name"].upper()
            for d in self.canon_map["devices"]
            if d.get("final_status") == STATUS_MAPPED
        }
        for name in PICK_LOCAL:
            self.assertIn(name, mapped, name)


class TestEngineerDecisionCompose(unittest.TestCase):
    def test_confirm_local_then_safety_preserves_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "engineer_io_confirmations.json"
            r1 = confirm_physical_device(
                canonical_device="SYNTH_ESPB99",
                classification=CONFIRM_LOCAL,
                controller="MSCRENOPICK",
                physical_endpoint="AENTR9:I.DATA[1].1",
                device_type="ESPB",
                reason="fixture local",
                store_path=store,
            )
            self.assertTrue(r1["ok"], r1)
            r2 = confirm_physical_device(
                canonical_device="SYNTH_ESPB99",
                classification=CONFIRM_SAFETY,
                controller="MSCRENOPICK",
                physical_endpoint="",
                safety_classification="ESPB",
                safety_zone="ESZone_TEST",
                reason="fixture safety",
                store_path=store,
            )
            self.assertTrue(r2["ok"], r2)
            # Scoped key: site|controller|device (MSCRENO|MSCRENOPICK|SYNTH_ESPB99)
            confs = load_confirmations(store)["confirmations"]
            self.assertIn("MSCRENO|MSCRENOPICK|SYNTH_ESPB99", confs)
            row = confs["MSCRENO|MSCRENOPICK|SYNTH_ESPB99"]
            self.assertEqual(row["physical_endpoint"], "AENTR9:I.DATA[1].1")
            self.assertEqual(row["device_type"], "ESPB")
            self.assertEqual(row["safety_classification"], "ESPB")
            self.assertEqual(row["safety_zone"], "ESZone_TEST")
            self.assertEqual(row["final_status"], "ENGINEER_CONFIRMED")
            self.assertEqual(row["site"], "MSCRENO")
            self.assertEqual(row["controller"], "MSCRENOPICK")
            self.assertTrue(row.get("classification_history"))
            self.assertTrue(row.get("evidence_fingerprint"))

    def test_safety_build_consumes_engineer_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "engineer_io_confirmations.json"
            confirm_physical_device(
                canonical_device="SYNTH_ESPB99",
                classification=CONFIRM_LOCAL,
                controller="MSCRENOPICK",
                physical_endpoint="AENTR9:I.DATA[1].1",
                device_type="ESPB",
                store_path=store,
            )
            confirm_physical_device(
                canonical_device="SYNTH_ESPB99",
                classification=CONFIRM_SAFETY,
                controller="MSCRENOPICK",
                safety_classification="ESPB",
                safety_zone="ESZone_TEST",
                store_path=store,
            )
            devices: list = []
            stats = apply_confirmations_to_safety_devices(
                devices,
                store_path=store,
                inject_missing=True,
                active_machine="MSCRENOPICK",
            )
            self.assertEqual(stats["injected"], 1)
            self.assertEqual(len(devices), 1)
            d = devices[0]
            self.assertTrue(d["assignable"])
            self.assertEqual(d["physicalEndpoint"], "AENTR9:I.DATA[1].1")
            self.assertEqual(d["inventory_scope"], LOCAL_PHYSICAL)
            self.assertEqual(
                classify_safety_device_scope(d, active_machine="MSCRENOPICK"),
                LOCAL_PHYSICAL,
            )

    def test_foreign_confirmation_not_assignable_same_controller(self) -> None:
        """Same-controller FOREIGN inject is REVIEW_REQUIRED / non-assignable."""
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "engineer_io_confirmations.json"
            confirm_physical_device(
                canonical_device="ESPB_FOREIGN_SYNTH",
                classification="CONFIRM_FOREIGN",
                controller="MSCRENOPICK",
                device_type="ESPB",
                reason="peer owned",
                store_path=store,
            )
            devices: list = []
            stats = apply_confirmations_to_safety_devices(
                devices,
                store_path=store,
                inject_missing=True,
                active_machine="MSCRENOPICK",
            )
            self.assertEqual(stats["injected"], 1)
            self.assertEqual(len(devices), 1)
            self.assertFalse(devices[0]["assignable"])
            self.assertIn("FOREIGN", devices[0]["review_reason"] or "")

    def test_cross_controller_foreign_does_not_inject(self) -> None:
        """Ship FOREIGN confirmation must not inject into Pick inventory."""
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "engineer_io_confirmations.json"
            confirm_physical_device(
                canonical_device="ESPB_FOREIGN_SYNTH",
                classification="CONFIRM_FOREIGN",
                controller="MSCRENOSHIP",
                device_type="ESPB",
                reason="peer owned",
                store_path=store,
            )
            devices: list = []
            stats = apply_confirmations_to_safety_devices(
                devices,
                store_path=store,
                inject_missing=True,
                active_machine="MSCRENOPICK",
            )
            self.assertEqual(stats["injected"], 0)
            self.assertEqual(len(devices), 0)
            self.assertGreaterEqual(stats["skipped_cross_controller"], 1)


@unittest.skipUnless((MSC_SHIP_RUN / "project.cfg").is_file(), "MSCRENOSHIP RUN missing")
class TestShipRegressionWorkbench(unittest.TestCase):
    def test_ship_workbench_builds_and_foreign_rules_intact(self) -> None:
        """Unrelated regression site: workbench builds; no crash on exception filter."""
        with tempfile.TemporaryDirectory() as td:
            empty = Path(td) / "engineer_io_confirmations.json"
            empty.write_text(json.dumps({"version": 1, "confirmations": {}}))
            wb = build_workbench(
                machine="MSCRENOSHIP",
                run_dir=MSC_SHIP_RUN,
                confirmations_path=empty,
            )
            self.assertTrue(wb.get("ok"), wb)
            # Proven foreign-to-Pick devices must not appear as SHIP local critical
            # solely due to stale review logic; filter uses canonical authority.
            for it in wb.get("items") or []:
                own = str(it.get("controller_ownership") or "").upper()
                self.assertNotEqual(own, "FOREIGN")


@unittest.skipUnless((MSC_PACK_RUN / "project.cfg").is_file(), "MSCRENOPACK RUN missing")
class TestPackRegressionWorkbench(unittest.TestCase):
    def test_pack_workbench_builds(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            empty = Path(td) / "engineer_io_confirmations.json"
            empty.write_text(json.dumps({"version": 1, "confirmations": {}}))
            wb = build_workbench(
                machine="MSCRENOPACK",
                run_dir=MSC_PACK_RUN,
                confirmations_path=empty,
            )
            self.assertTrue(wb.get("ok"), wb)
            led = build_source_evidence_ledger(MSC_PACK_RUN, "MSCRENOPACK")
            canon = build_canonical_device_ledger(
                led,
                machine="MSCRENOPACK",
                run_dir=MSC_PACK_RUN,
                apply_engineer_confirmations=False,
            )
            # Regression: ledger still produces devices; GUI_ONLY/FOREIGN filter safe.
            self.assertGreater(len(canon.get("devices") or []), 0)


if __name__ == "__main__":
    unittest.main()

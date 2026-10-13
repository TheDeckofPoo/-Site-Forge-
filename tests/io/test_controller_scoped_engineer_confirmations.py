#!/usr/bin/env python3
"""P0: Controller-scoped engineer confirmations.

An engineer confirmation must never apply merely because the device name matches.

Acceptance:
  - Pick ESPB22 confirmation does not apply on Ship
  - Pick ESPB22 confirmation does not apply on Pack
  - Ship-local ESPB22 stays Ship-local
  - Pick SS13P9 FOREIGN does not apply on Ship
  - Different sites with same device name do not collide
  - Changed RUN/evidence marks confirmation stale
  - Legacy unscoped record does not auto-apply
  - inject_missing across controller = 0
  - Confirmation properties still compose instead of overwrite
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
    CONFIRM_FOREIGN,
    CONFIRM_LOCAL,
    CONFIRM_SAFETY,
    STATUS_ENGINEER_CONFIRMED,
    STATUS_FOREIGN,
    STATUS_STALE_EVIDENCE,
    STATUS_STALE_LEGACY,
    apply_confirmations_to_devices,
    apply_confirmations_to_safety_devices,
    build_evidence_fingerprint,
    confirm_physical_device,
    derive_site_from_controller,
    fingerprint_compatible,
    load_confirmations,
    lookup_confirmation,
    make_scope_key,
    migrate_store_to_scoped,
    save_confirmations,
)


class TestScopeKeyIdentity(unittest.TestCase):
    def test_scope_key_format(self) -> None:
        self.assertEqual(
            make_scope_key("MSCRENO", "MSCRENOPICK", "ESPB22"),
            "MSCRENO|MSCRENOPICK|ESPB22",
        )

    def test_derive_site_from_controller(self) -> None:
        self.assertEqual(derive_site_from_controller("MSCRENOPICK"), "MSCRENO")
        self.assertEqual(derive_site_from_controller("MSCRENOSHIP"), "MSCRENO")
        self.assertEqual(derive_site_from_controller("MSCRENOPACK"), "MSCRENO")
        self.assertEqual(derive_site_from_controller("ORINDYAC6"), "ORINDYAC6")
        self.assertEqual(
            derive_site_from_controller("MSCRENOPICK", site="CUSTOM"),
            "CUSTOM",
        )


class TestEspb22CrossControllerIsolation(unittest.TestCase):
    """ESPB22: Pick LOCAL confirmation must not contaminate Ship/Pack."""

    def _seed_pick_espb22(self, store: Path) -> dict:
        return confirm_physical_device(
            canonical_device="ESPB22",
            classification=CONFIRM_SAFETY,
            controller="MSCRENOPICK",
            device_type="ESPB",
            safety_classification="ESPB",
            safety_zone="ESZone_REVIEW",
            reason="fixture: Pick-scoped LOCAL confirmation",
            store_path=store,
            evidence_fingerprint=build_evidence_fingerprint(
                ownership="LOCAL",
                evidence_class="PHYSICAL_FIELD_DEVICE",
            ),
        )

    def test_pick_confirmation_does_not_apply_on_ship(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "engineer_io_confirmations.json"
            r = self._seed_pick_espb22(store)
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["scope_key"], "MSCRENO|MSCRENOPICK|ESPB22")

            # Ship device list containing ESPB22 as local physical evidence.
            devices = [
                {
                    "canonical_name": "ESPB22",
                    "ownership": "LOCAL",
                    "final_status": "REVIEW_REQUIRED",
                    "evidence_class": "PHYSICAL_FIELD_DEVICE",
                    "physical_endpoint": "AENTR_SHIP:I.DATA[1].0",
                }
            ]
            stats = apply_confirmations_to_devices(
                devices,
                store_path=store,
                active_machine="MSCRENOSHIP",
            )
            self.assertEqual(stats["applied"], 0)
            self.assertIsNone(devices[0].get("engineer_confirmation"))
            # Ship's own evidence remains — not overwritten to ENGINEER_CONFIRMED from Pick.
            self.assertNotEqual(
                devices[0].get("final_status"),
                STATUS_ENGINEER_CONFIRMED,
            )
            self.assertEqual(devices[0].get("ownership"), "LOCAL")
            # Peer history may be attached read-only.
            peers = devices[0].get("engineer_confirmation_peer_history") or []
            self.assertTrue(any(_norm_ctrl(p) == "MSCRENOPICK" for p in peers))

    def test_pick_confirmation_does_not_apply_on_pack(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "engineer_io_confirmations.json"
            self._seed_pick_espb22(store)
            devices = [
                {
                    "canonical_name": "ESPB22",
                    "ownership": "UNKNOWN",
                    "final_status": "REVIEW_REQUIRED",
                }
            ]
            stats = apply_confirmations_to_devices(
                devices,
                store_path=store,
                active_machine="MSCRENOPACK",
            )
            self.assertEqual(stats["applied"], 0)
            self.assertIsNone(devices[0].get("engineer_confirmation"))

    def test_ship_local_espb22_stays_ship_local(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "engineer_io_confirmations.json"
            self._seed_pick_espb22(store)
            # Ship confirms its own ESPB22 LOCAL independently.
            confirm_physical_device(
                canonical_device="ESPB22",
                classification=CONFIRM_LOCAL,
                controller="MSCRENOSHIP",
                physical_endpoint="AENTR_SHIP:I.DATA[1].0",
                device_type="ESPB",
                reason="fixture: Ship-scoped LOCAL",
                store_path=store,
            )
            devices = [
                {
                    "canonical_name": "ESPB22",
                    "ownership": "LOCAL",
                    "final_status": "REVIEW_REQUIRED",
                    "physical_endpoint": "AENTR_SHIP:I.DATA[1].0",
                }
            ]
            stats = apply_confirmations_to_devices(
                devices,
                store_path=store,
                active_machine="MSCRENOSHIP",
            )
            self.assertEqual(stats["applied"], 1)
            conf = devices[0]["engineer_confirmation"]
            self.assertEqual(conf["controller"], "MSCRENOSHIP")
            self.assertEqual(conf["ownership"], "LOCAL")
            self.assertEqual(conf["scope_key"], "MSCRENO|MSCRENOSHIP|ESPB22")
            # Pick row still present, isolated.
            loaded = load_confirmations(store)
            self.assertIn("MSCRENO|MSCRENOPICK|ESPB22", loaded["confirmations"])
            self.assertIn("MSCRENO|MSCRENOSHIP|ESPB22", loaded["confirmations"])

    def test_pick_espb22_does_not_become_local_from_old_confirmation_on_pick_when_foreign(
        self,
    ) -> None:
        """Current Pick evidence FOREIGN_CONTROLLER wins over applying LOCAL wrongly.

        When Pick evidence says FOREIGN (owned by Ship), a Pick-scoped LOCAL
        confirmation whose fingerprint ownership diverges becomes STALE and
        must not force ENGINEER_CONFIRMED LOCAL.
        """
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "engineer_io_confirmations.json"
            confirm_physical_device(
                canonical_device="ESPB22",
                classification=CONFIRM_SAFETY,
                controller="MSCRENOPICK",
                device_type="ESPB",
                reason="old Pick LOCAL",
                store_path=store,
                evidence_fingerprint=build_evidence_fingerprint(
                    ownership="LOCAL",
                    evidence_class="PHYSICAL_FIELD_DEVICE",
                ),
            )
            devices = [
                {
                    "canonical_name": "ESPB22",
                    "ownership": "FOREIGN",
                    "final_status": STATUS_FOREIGN,
                    "evidence_class": "FOREIGN_CONTROLLER",
                    "controller": "MSCRENOSHIP",
                }
            ]
            stats = apply_confirmations_to_devices(
                devices,
                store_path=store,
                active_machine="MSCRENOPICK",
            )
            # Fingerprint ownership LOCAL vs current FOREIGN → stale, not applied.
            self.assertEqual(stats["applied"], 0)
            self.assertGreaterEqual(stats["skipped_stale"], 1)
            self.assertEqual(devices[0].get("final_status"), STATUS_FOREIGN)
            self.assertEqual(devices[0].get("ownership"), "FOREIGN")
            self.assertIn("engineer_confirmation_stale", devices[0])

    def test_safety_inject_missing_cross_controller_is_zero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "engineer_io_confirmations.json"
            self._seed_pick_espb22(store)
            # Give the Pick confirmation an endpoint so same-controller would inject.
            confs = load_confirmations(store)
            confs["confirmations"]["MSCRENO|MSCRENOPICK|ESPB22"][
                "physical_endpoint"
            ] = "AENTR1:I.DATA[0].0"
            save_confirmations(confs, store)

            ship_devices: list = []
            stats = apply_confirmations_to_safety_devices(
                ship_devices,
                store_path=store,
                inject_missing=True,
                active_machine="MSCRENOSHIP",
            )
            self.assertEqual(stats["injected"], 0)
            self.assertEqual(len(ship_devices), 0)
            self.assertGreaterEqual(stats["skipped_cross_controller"], 1)

            pack_devices: list = []
            stats_p = apply_confirmations_to_safety_devices(
                pack_devices,
                store_path=store,
                inject_missing=True,
                active_machine="MSCRENOPACK",
            )
            self.assertEqual(stats_p["injected"], 0)


class TestSs13p9CrossControllerIsolation(unittest.TestCase):
    def test_pick_foreign_ss13p9_does_not_apply_on_ship(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "engineer_io_confirmations.json"
            confirm_physical_device(
                canonical_device="SS13P9",
                classification=CONFIRM_FOREIGN,
                controller="MSCRENOPICK",
                reason="Pick: word absent from active Configio",
                store_path=store,
            )
            # Ship has legitimate local SS13P9 evidence.
            devices = [
                {
                    "canonical_name": "SS13P9",
                    "ownership": "LOCAL",
                    "final_status": "REVIEW_REQUIRED",
                    "physical_endpoint": "AENTR_SHIP:I.DATA[9].3",
                    "evidence_class": "PHYSICAL_FIELD_DEVICE",
                }
            ]
            stats = apply_confirmations_to_devices(
                devices,
                store_path=store,
                active_machine="MSCRENOSHIP",
            )
            self.assertEqual(stats["applied"], 0)
            self.assertIsNone(devices[0].get("engineer_confirmation"))
            # Must not be forced FOREIGN by Pick confirmation.
            self.assertEqual(devices[0].get("ownership"), "LOCAL")
            self.assertNotEqual(devices[0].get("final_status"), STATUS_FOREIGN)


class TestSiteCollisionIsolation(unittest.TestCase):
    def test_different_sites_same_device_name_do_not_collide(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "engineer_io_confirmations.json"
            confirm_physical_device(
                canonical_device="ESPB1",
                classification=CONFIRM_LOCAL,
                controller="MSCRENOPICK",
                site="MSCRENO",
                physical_endpoint="A:I.DATA[0].0",
                store_path=store,
            )
            confirm_physical_device(
                canonical_device="ESPB1",
                classification=CONFIRM_FOREIGN,
                controller="ORINDYAC6",
                site="ORINDYAC6",
                store_path=store,
            )
            loaded = load_confirmations(store)
            self.assertIn("MSCRENO|MSCRENOPICK|ESPB1", loaded["confirmations"])
            self.assertIn("ORINDYAC6|ORINDYAC6|ESPB1", loaded["confirmations"])

            reno = [{"canonical_name": "ESPB1", "ownership": "LOCAL"}]
            apply_confirmations_to_devices(
                reno, store_path=store, active_machine="MSCRENOPICK", site="MSCRENO"
            )
            self.assertEqual(
                reno[0]["engineer_confirmation"]["ownership"], "LOCAL"
            )

            orindy = [{"canonical_name": "ESPB1", "ownership": "UNKNOWN"}]
            apply_confirmations_to_devices(
                orindy, store_path=store, active_machine="ORINDYAC6", site="ORINDYAC6"
            )
            self.assertEqual(
                orindy[0]["engineer_confirmation"]["final_status"], STATUS_FOREIGN
            )


class TestStaleEvidence(unittest.TestCase):
    def test_changed_run_marks_confirmation_stale(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "engineer_io_confirmations.json"
            confirm_physical_device(
                canonical_device="ESPB7",
                classification=CONFIRM_LOCAL,
                controller="MSCRENOPICK",
                physical_endpoint="AENTR1:I.DATA[1].1",
                store_path=store,
                evidence_fingerprint=build_evidence_fingerprint(
                    run_hash="RUN_AAA",
                    raw_word="1011",
                    raw_bit="3",
                    endpoint="AENTR1:I.DATA[1].1",
                    ownership="LOCAL",
                ),
            )
            devices = [
                {
                    "canonical_name": "ESPB7",
                    "ownership": "LOCAL",
                    "run_hash": "RUN_BBB",  # material change
                    "word": "1011",
                    "bit": "3",
                    "physical_endpoint": "AENTR1:I.DATA[1].1",
                }
            ]
            stats = apply_confirmations_to_devices(
                devices,
                store_path=store,
                active_machine="MSCRENOPICK",
            )
            self.assertEqual(stats["applied"], 0)
            self.assertGreaterEqual(stats["skipped_stale"], 1)
            stale = devices[0].get("engineer_confirmation_stale") or {}
            self.assertEqual(stale.get("scope_status"), STATUS_STALE_EVIDENCE)

    def test_fingerprint_compatible_same(self) -> None:
        a = build_evidence_fingerprint(run_hash="R1", raw_word="10", ownership="LOCAL")
        b = build_evidence_fingerprint(run_hash="R1", raw_word="10", ownership="LOCAL")
        self.assertTrue(fingerprint_compatible(a, b))

    def test_fingerprint_incompatible_word(self) -> None:
        a = build_evidence_fingerprint(raw_word="10", ownership="LOCAL")
        b = build_evidence_fingerprint(raw_word="99", ownership="LOCAL")
        self.assertFalse(fingerprint_compatible(a, b))


class TestLegacyUnscoped(unittest.TestCase):
    def test_legacy_unscoped_does_not_auto_apply(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "engineer_io_confirmations.json"
            # Write a v1 name-keyed store directly (pre-migration shape).
            store.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "confirmations": {
                            "ESPB22": {
                                "canonical_device": "ESPB22",
                                "classification": "CONFIRM_SAFETY",
                                "controller": "MSCRENOPICK",
                                "ownership": "LOCAL",
                                "final_status": "ENGINEER_CONFIRMED",
                                "physical_endpoint": "",
                                "device_type": "ESPB",
                                "evidence_snapshot": {},
                                "assignable": True,
                            },
                            "SS13P9": {
                                "canonical_device": "SS13P9",
                                "classification": "CONFIRM_FOREIGN",
                                "controller": "MSCRENOPICK",
                                "ownership": "FOREIGN",
                                "final_status": "FOREIGN_CONTROLLER",
                                "evidence_snapshot": {},
                                "assignable": False,
                            },
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            loaded = load_confirmations(store)
            # Migrated out of active confirmations.
            self.assertEqual(loaded["confirmations"], {})
            self.assertGreaterEqual(len(loaded["legacy_confirmations"]), 2)
            for row in loaded["legacy_confirmations"].values():
                self.assertEqual(row.get("scope_status"), STATUS_STALE_LEGACY)
                self.assertTrue(row.get("read_only"))

            # Ship must not receive Pick's legacy ESPB22.
            devices = [
                {
                    "canonical_name": "ESPB22",
                    "ownership": "LOCAL",
                    "final_status": "REVIEW_REQUIRED",
                }
            ]
            stats = apply_confirmations_to_devices(
                devices,
                store=loaded,
                active_machine="MSCRENOSHIP",
            )
            self.assertEqual(stats["applied"], 0)
            self.assertIsNone(devices[0].get("engineer_confirmation"))

            # Name-only lookup without controller returns None for apply.
            self.assertIsNone(lookup_confirmation(loaded, "ESPB22"))

            # Safety inject across controllers from legacy = 0.
            ship_safety: list = []
            sstats = apply_confirmations_to_safety_devices(
                ship_safety,
                store=loaded,
                inject_missing=True,
                active_machine="MSCRENOSHIP",
            )
            self.assertEqual(sstats["injected"], 0)
            self.assertEqual(sstats["applied"], 0)
            self.assertGreaterEqual(sstats["skipped_legacy"], 2)

    def test_migrate_does_not_guess_scope(self) -> None:
        store = {
            "version": 1,
            "confirmations": {
                "ESPB99": {
                    "canonical_device": "ESPB99",
                    "controller": "MSCRENOPICK",
                    "final_status": "ENGINEER_CONFIRMED",
                    "ownership": "LOCAL",
                }
            },
        }
        migrated = migrate_store_to_scoped(store)
        self.assertEqual(migrated["confirmations"], {})
        legacy = migrated["legacy_confirmations"]
        self.assertIn("legacy:ESPB99", legacy)
        self.assertEqual(legacy["legacy:ESPB99"]["scope_status"], STATUS_STALE_LEGACY)
        # Must NOT invent MSCRENO|MSCRENOPICK|ESPB99 as active.
        self.assertNotIn("MSCRENO|MSCRENOPICK|ESPB99", migrated["confirmations"])


class TestComposeStillWorks(unittest.TestCase):
    def test_compose_preserves_endpoint_under_scoped_key(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "engineer_io_confirmations.json"
            r1 = confirm_physical_device(
                canonical_device="SYNTH_ESPB99",
                classification=CONFIRM_LOCAL,
                controller="MSCRENOPICK",
                physical_endpoint="AENTR9:I.DATA[1].1",
                device_type="ESPB",
                store_path=store,
            )
            self.assertTrue(r1["ok"], r1)
            r2 = confirm_physical_device(
                canonical_device="SYNTH_ESPB99",
                classification=CONFIRM_SAFETY,
                controller="MSCRENOPICK",
                safety_classification="ESPB",
                safety_zone="ESZone_TEST",
                store_path=store,
            )
            self.assertTrue(r2["ok"], r2)
            row = load_confirmations(store)["confirmations"][
                "MSCRENO|MSCRENOPICK|SYNTH_ESPB99"
            ]
            self.assertEqual(row["physical_endpoint"], "AENTR9:I.DATA[1].1")
            self.assertEqual(row["device_type"], "ESPB")
            self.assertEqual(row["safety_zone"], "ESZone_TEST")
            self.assertTrue(row.get("classification_history"))


class TestNoActiveMachineRefusesApply(unittest.TestCase):
    def test_devices_apply_requires_active_machine(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "engineer_io_confirmations.json"
            confirm_physical_device(
                canonical_device="ESPB22",
                classification=CONFIRM_LOCAL,
                controller="MSCRENOPICK",
                store_path=store,
            )
            devices = [{"canonical_name": "ESPB22", "ownership": "LOCAL"}]
            stats = apply_confirmations_to_devices(devices, store_path=store)
            self.assertEqual(stats["applied"], 0)
            self.assertIn("active_machine required", stats.get("error") or "")


def _norm_ctrl(p: dict) -> str:
    return str(p.get("controller") or "").strip().upper()


if __name__ == "__main__":
    unittest.main()

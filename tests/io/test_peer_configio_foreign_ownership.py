#!/usr/bin/env python3
"""Peer Configio ownership: foreign controller words must not become local Safety.

Generic rule (no device-name special cases):
  active Configio lacks word + peer Configio.asc.<PEER> owns word
  ⇒ FOREIGN_CONTROLLER with peer provenance.

Also: UNSUPPORTED must not inflate PHYSICAL_DEVICE_RESOLUTION_PCT.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))

from fortna_run_io_source_ledger import (  # noqa: E402
    STATUS_FOREIGN,
    STATUS_MAPPED,
    STATUS_UNSUPPORTED,
    build_canonical_device_ledger,
    recompute_physical_io_metrics,
    resolve_ownership_deterministic,
)
from fortna_safety_inventory_scope import (  # noqa: E402
    LOCAL_PHYSICAL,
    UNRELATED_FOREIGN,
    classify_safety_device_scope,
    partition_safety_inventory,
)

MSC_PICK_RUN = (
    REPO
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
    / "RUN"
)


@unittest.skipUnless((MSC_PICK_RUN / "project.cfg").is_file(), "MSCRENOPICK RUN missing")
class TestPeerConfigioForeignOwnership(unittest.TestCase):
    def test_ship_words_are_foreign_without_name_special_case(self) -> None:
        # Word-level evidence only — never hard-code ESLS* names in production.
        cases = [
            ("1100", "17"),
            ("1132", "16"),
            ("1132", "15"),
            ("1133", "12"),
        ]
        for word, bit in cases:
            own = resolve_ownership_deterministic(
                machine="MSCRENOPICK",
                source_machine="N/A",
                word=word,
                bit=bit,
                run_dir=MSC_PICK_RUN,
            )
            self.assertEqual(
                own.get("ownership"),
                "FOREIGN",
                f"word {word}: {own}",
            )
            self.assertEqual(own.get("deterministic_code"), "PEER_CONFIGIO_OWNERSHIP")
            peers = [p.upper() for p in (own.get("peer_controllers") or [])]
            self.assertIn("MSCRENOSHIP", peers, own)
            self.assertFalse(own.get("word_in_active_configio"))

    def test_local_pick_word_remains_local(self) -> None:
        own = resolve_ownership_deterministic(
            machine="MSCRENOPICK",
            source_machine="N/A",
            word="1142",
            bit="13",
            run_dir=MSC_PICK_RUN,
        )
        self.assertEqual(own.get("ownership"), "LOCAL", own)
        self.assertEqual(own.get("deterministic_code"), "ENDPOINT_ON_ACTIVE_CONTROLLER")
        self.assertTrue(own.get("word_in_active_configio"))

    def test_canonical_ledger_marks_ship_esls_foreign(self) -> None:
        led = {
            "machine": "MSCRENOPICK",
            "ledger_complete": True,
            "candidates": [
                {
                    "id": "esls1",
                    "source_signal": "ESLS1",
                    "source_file": "FORTNA/Conveyor.asc",
                    "source_type": "conveyor_named_claim",
                    "machine": "N/A",
                    "word": "1100",
                    "bit": "17",
                    "highlight": "ESLS",
                },
                {
                    "id": "esls2",
                    "source_signal": "ESLS2",
                    "source_file": "FORTNA/Conveyor.asc",
                    "source_type": "conveyor_named_claim",
                    "machine": "MSCRENOPICK",
                    "word": "1142",
                    "bit": "13",
                    "highlight": "ESLS",
                },
                {
                    "id": "p7_1",
                    "source_signal": "ESLS13P7-1",
                    "source_file": "FORTNA/EStop.asc",
                    "source_type": "estop_named_claim",
                    "machine": "N/A",
                    "word": "1132",
                    "bit": "16",
                    "highlight": "ESLS",
                },
                {
                    "id": "p7_2",
                    "source_signal": "ESLS13P7-2",
                    "source_file": "FORTNA/EStop.asc",
                    "source_type": "estop_named_claim",
                    "machine": "N/A",
                    "word": "1132",
                    "bit": "15",
                    "highlight": "ESLS",
                },
                {
                    "id": "p9_1",
                    "source_signal": "ESLS13P9-1",
                    "source_file": "FORTNA/EStop.asc",
                    "source_type": "estop_named_claim",
                    "machine": "N/A",
                    "word": "1133",
                    "bit": "12",
                    "highlight": "ESLS",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            map_csv = Path(td) / "physical_io_map.csv"
            map_csv.write_text(
                "fortna_name,device_type,direction,fortna_bank,fortna_bit,"
                "module_data_ref,mapped,notes\n"
                "ESLS2,ESLS,I,1142,13,AENTR2:I.DATA[2].3,Y,local\n",
                encoding="utf-8",
            )
            names = {c["source_signal"].upper() for c in led["candidates"]}
            canon = build_canonical_device_ledger(
                led,
                machine="MSCRENOPICK",
                run_dir=MSC_PICK_RUN,
                physical_io_map_csv=map_csv,
                canonical_device_names=names,
                apply_engineer_confirmations=False,
            )
        by = {d["canonical_name"].upper(): d for d in canon["devices"]}
        for foreign_name in ("ESLS1", "ESLS13P7-1", "ESLS13P7-2", "ESLS13P9-1"):
            d = by[foreign_name]
            self.assertEqual(d.get("final_status"), STATUS_FOREIGN, d)
            self.assertEqual(d.get("ownership"), "FOREIGN", d)
            self.assertEqual(d.get("evidence_class"), "FOREIGN_CONTROLLER", d)
            ctrl = str(d.get("controller") or "").upper()
            self.assertEqual(ctrl, "MSCRENOSHIP", d)
            # Not Pick critical unresolved / not in local physical denom
            self.assertNotIn(
                foreign_name,
                {
                    (x.get("canonical_device") or "").upper()
                    for x in (canon.get("critical_unresolved") or [])
                },
            )

        local = by["ESLS2"]
        self.assertEqual(local.get("ownership"), "LOCAL")
        self.assertIn(local.get("final_status"), {STATUS_MAPPED, "REVIEW_REQUIRED"})

        # Safety inventory: foreign stamped devices are not assignable local
        part = partition_safety_inventory(
            [
                {
                    "name": d["canonical_name"],
                    "controller": d.get("controller"),
                    "ownership": d.get("ownership"),
                    "final_status": d.get("final_status"),
                    "evidence_class": d.get("evidence_class"),
                }
                for d in canon["devices"]
            ],
            active_machine="MSCRENOPICK",
        )
        assignable = {d["name"].upper() for d in part["assignable"]}
        self.assertNotIn("ESLS1", assignable)
        self.assertNotIn("ESLS13P7-1", assignable)
        self.assertIn("ESLS2", assignable)
        self.assertEqual(
            classify_safety_device_scope(
                {
                    "name": "ESLS1",
                    "ownership": "FOREIGN",
                    "controller": "MSCRENOSHIP",
                    "final_status": STATUS_FOREIGN,
                },
                active_machine="MSCRENOPICK",
            ),
            UNRELATED_FOREIGN,
        )


class TestUnsupportedDoesNotInflateResolution(unittest.TestCase):
    def test_unsupported_excluded_from_resolved_pct(self) -> None:
        canon = {
            "devices": [
                {
                    "canonical_name": "ESPB2",
                    "ownership": "LOCAL",
                    "final_status": STATUS_MAPPED,
                    "evidence_class": "PHYSICAL_FIELD_DEVICE",
                    "device_type": "ESPB",
                    "critical": True,
                },
                {
                    "canonical_name": "ESPB_PA3",
                    "ownership": "UNKNOWN",
                    "final_status": STATUS_UNSUPPORTED,
                    "evidence_class": "PHYSICAL_FIELD_DEVICE",
                    "device_type": "ESPB",
                    "critical": True,
                },
                {
                    "canonical_name": "ESLS_FOREIGN",
                    "ownership": "FOREIGN",
                    "final_status": STATUS_FOREIGN,
                    "evidence_class": "FOREIGN_CONTROLLER",
                    "device_type": "ESLS",
                    "controller": "OTHER",
                    "critical": True,
                },
            ],
            "source_evidence_rows": 3,
            "evidence_reconcile": {"conservation_ok": True, "silently_missing": 0},
        }
        metrics = recompute_physical_io_metrics(canon)
        # FOREIGN excluded from denom; UNSUPPORTED present but not resolved.
        # Denom = ESPB2 + ESPB_PA3 = 2; resolved = ESPB2 only → 50%.
        self.assertEqual(metrics["unique_physical_devices"], 2)
        self.assertEqual(metrics["mapped_physical_devices"], 1)
        self.assertEqual(metrics["unsupported_physical_devices"], 1)
        self.assertEqual(metrics["foreign_devices"], 1)
        self.assertEqual(metrics["PHYSICAL_DEVICE_RESOLUTION_PCT"], 50.0)
        self.assertEqual(
            classify_safety_device_scope(
                canon["devices"][2], active_machine="MSCRENOPICK"
            ),
            UNRELATED_FOREIGN,
        )
        self.assertEqual(
            classify_safety_device_scope(
                canon["devices"][0], active_machine="MSCRENOPICK"
            ),
            LOCAL_PHYSICAL,
        )


if __name__ == "__main__":
    unittest.main()

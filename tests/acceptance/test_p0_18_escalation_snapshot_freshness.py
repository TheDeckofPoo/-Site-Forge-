#!/usr/bin/env python3
"""P0-18 — stale escalation snapshots must not overwrite active project truth.

A snapshot is authoritative only when it matches active project identity:
  site/controller, run_fingerprint, archive / workbook revision.

Newest-file selection alone is forbidden.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_io_escalation_store import (  # noqa: E402
    load_escalation_snapshot,
    save_escalation_snapshot,
    snapshot_matches_active_project,
)


class TestP018SnapshotFreshness(unittest.TestCase):
    def test_fingerprint_mismatch_is_stale(self) -> None:
        snap = {
            "ori": "IO_CANONICAL_ESCALATION_SNAPSHOT",
            "machine": "MSCRENOPICK",
            "run_fingerprint": "aaaa",
            "archive": "old.tar.gz",
            "saved_at": "2026-10-12T21:00:00+00:00",
            "devices": [],
        }
        m = snapshot_matches_active_project(
            snap,
            machine="MSCRENOPICK",
            run_fingerprint="bbbb",
            archive="old.tar.gz",
        )
        self.assertFalse(m["ok"])
        self.assertTrue(m["stale"])
        self.assertIn("RUN_FINGERPRINT_MISMATCH", " ".join(m.get("details") or []))

    def test_machine_mismatch_is_stale(self) -> None:
        snap = {
            "ori": "IO_CANONICAL_ESCALATION_SNAPSHOT",
            "machine": "MSCRENOSHIP",
            "run_fingerprint": "same",
            "devices": [],
        }
        m = snapshot_matches_active_project(
            snap,
            machine="MSCRENOPICK",
            run_fingerprint="same",
        )
        self.assertFalse(m["ok"])
        self.assertTrue(m["stale"])

    def test_matching_identity_ok(self) -> None:
        snap = {
            "ori": "IO_CANONICAL_ESCALATION_SNAPSHOT",
            "machine": "MSCRENOPICK",
            "run_fingerprint": "f36bac385792506982fb186897dc8a2b2bf2f421",
            "archive": "20260813-1132-MSCRENO-MSCRENOPICK-RUN.tar.gz",
            "devices": [],
        }
        m = snapshot_matches_active_project(
            snap,
            machine="MSCRENOPICK",
            run_fingerprint="f36bac385792506982fb186897dc8a2b2bf2f421",
            archive="20260813-1132-MSCRENO-MSCRENOPICK-RUN.tar.gz",
        )
        self.assertTrue(m["ok"], m)
        self.assertFalse(m["stale"])

    def test_save_embeds_identity_and_load_rejects_stale(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = root / "workspace"
            ws.mkdir()
            (ws / "active").mkdir()
            meta = {
                "machine": "MSCRENOPICK",
                "run_fingerprint": "live-fp-1013",
                "archive": "live-run.tar.gz",
                "archive_name": "live-run.tar.gz",
                "imported": "2026-10-13T15:22:48",
            }
            (ws / "active-meta.json").write_text(json.dumps(meta), encoding="utf-8")

            # Write a STALE snapshot (10/12, wrong fingerprint) into workspace
            stale = {
                "ori": "IO_CANONICAL_ESCALATION_SNAPSHOT",
                "version": 1,
                "saved_at": "2026-10-12T21:18:18+00:00",
                "machine": "MSCRENOPICK",
                "run_fingerprint": "old-fp-1012",
                "archive": "old-run.tar.gz",
                "build_id": "20261012-171803",
                "metrics": {"unique_review": 0, "unique_physical_devices": 5},
                "devices": [{"canonical_name": "STALE_DEV", "final_status": "FOREIGN_CONTROLLER"}],
                "extra": {},
            }
            (ws / "io_canonical_escalation_snapshot.json").write_text(
                json.dumps(stale), encoding="utf-8"
            )

            load_escalation_snapshot.last_rejection = None  # type: ignore[attr-defined]
            loaded = load_escalation_snapshot(
                machine="MSCRENOPICK",
                repo=root,
                run_fingerprint="live-fp-1013",
                archive="live-run.tar.gz",
            )
            self.assertIsNone(loaded)
            rej = load_escalation_snapshot.last_rejection  # type: ignore[attr-defined]
            self.assertTrue(rej and rej.get("stale"))

            # Fresh save under active identity must load
            saved = save_escalation_snapshot(
                {
                    "unique_review": 0,
                    "unique_physical_devices": 115,
                    "devices": [{"canonical_name": "ESPB2", "final_status": "ENGINEER_CONFIRMED"}],
                    "run_fingerprint": "live-fp-1013",
                    "archive": "live-run.tar.gz",
                },
                machine="MSCRENOPICK",
                build_id="20261013-test",
                repo=root,
            )
            self.assertTrue(saved["ok"], saved)
            loaded2 = load_escalation_snapshot(
                machine="MSCRENOPICK",
                repo=root,
                run_fingerprint="live-fp-1013",
                archive="live-run.tar.gz",
            )
            self.assertIsNotNone(loaded2)
            self.assertEqual(loaded2.get("run_fingerprint"), "live-fp-1013")
            self.assertEqual((loaded2.get("metrics") or {}).get("unique_physical_devices"), 115)

    def test_date_only_stale_without_fingerprint_on_snapshot(self) -> None:
        """Warden case: 10/12 snapshot without fingerprint vs 10/13 import."""
        snap = {
            "ori": "IO_CANONICAL_ESCALATION_SNAPSHOT",
            "machine": "MSCRENOPICK",
            "saved_at": "2026-10-12T21:18:18+00:00",
            "build_id": "20261012-171803",
            "devices": [],
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = root / "workspace"
            ws.mkdir()
            (ws / "active-meta.json").write_text(
                json.dumps(
                    {
                        "machine": "MSCRENOPICK",
                        "run_fingerprint": "f36bac385792506982fb186897dc8a2b2bf2f421",
                        "imported": "2026-10-13T15:22:48",
                        "archive": "20260813-1132-MSCRENO-MSCRENOPICK-RUN.tar.gz",
                    }
                ),
                encoding="utf-8",
            )
            m = snapshot_matches_active_project(
                snap,
                machine="MSCRENOPICK",
                repo=root,
            )
            self.assertFalse(m["ok"], m)
            self.assertTrue(m["stale"])


if __name__ == "__main__":
    unittest.main()

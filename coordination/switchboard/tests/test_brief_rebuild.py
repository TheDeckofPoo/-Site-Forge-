"""Morning brief generation, handoffs, deterministic rebuild, CLI end-to-end."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import unittest

from coordination.switchboard.cli import main
from coordination.switchboard.reports import build_handoff, morning_brief
from coordination.switchboard.store import PACKAGE_DIR, Store
from coordination.switchboard.validator import validate

from .helpers import FIXTURES, SHA_A, SHA_B, SHA_C, SwitchboardCase, all_fixtures


def run_cli(*argv) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        rc = main(list(argv))
    return rc, buf.getvalue()


class MorningBrief(SwitchboardCase):
    def test_brief_after_failed_audit(self):
        self.post_upto("05")
        text = morning_brief(self.state(), "packets")
        self.assertTrue(text.startswith("BACKPLANE BANDITS — NIGHT SHIFT"))
        for needle in (f"Starting SHA: {SHA_A}", "Anton:  mission ANTON-ORI052-01", "Warden: audit WARDEN-ORI052-01",
                       "ORI-052 FAIL @ 969eb83", "Reopened:        ORI-052 (reproducer TPNA1",
                       "IMPLEMENTER_AUDITOR_CONFLICT ORI-052", "ORI-052 REOPENED (owner Anton)",
                       "Curtis decisions required:", "then Anton: Fix ORI-052",
                       "packets/0005-result-WARDEN-ORI052-01-Warden.json"):
            self.assertIn(needle, text)
        self.assertLessEqual(len(text.splitlines()), 25)

    def test_brief_after_full_replay(self):
        for _, pkt in all_fixtures():
            self.post(pkt)
        text = morning_brief(self.state(), "packets", subsystems=self.store.load_subsystems())
        self.assertIn(f"Starting SHA: {SHA_B}", text)
        self.assertIn(f"Ending SHA:   {SHA_C}", text)
        self.assertIn("Verified closed: ORI-052", text)
        self.assertIn("ORI-052 PASS @ c0de052", text)
        self.assertIn("Safety CANDIDATE_FOR_GRADUATION", text)
        self.assertLessEqual(len(text.splitlines()), 25)
        full = morning_brief(self.state(), "packets", all_history=True)
        self.assertIn("IMPLEMENTER_AUDITOR_CONFLICT ORI-052", full)

    def test_handoff_validates_and_suggests_mission(self):
        from coordination.switchboard.store import Store
        self.store = Store(self.make_root(self.tmp / "h", {"max_cycles": 5}))
        self.post_upto("05")
        h = build_handoff(self.state())
        self.assertEqual(validate(h, "handoff"), [])
        self.assertEqual(h["to"], "Anton")
        self.assertEqual(h["required_start_sha"], SHA_B)
        self.assertEqual(h["suggested_mission"]["ori_ids"], ["ORI-052"])


class DeterministicRebuild(SwitchboardCase):
    def test_rebuild_matches_incremental_and_is_repeatable(self):
        for _, pkt in all_fixtures():
            self.post(pkt)
        cur = (self.root / "state" / "current.json").read_text()
        sub = (self.root / "state" / "subsystem_status.json").read_text()
        shutil.rmtree(self.root / "state")
        self.store.rebuild()
        self.assertEqual((self.root / "state" / "current.json").read_text(), cur)
        self.assertEqual((self.root / "state" / "subsystem_status.json").read_text(), sub)
        self.store.rebuild()
        self.assertEqual((self.root / "state" / "current.json").read_text(), cur)
        # a second independent root replaying the same history yields identical state
        other = Store(self.make_root(self.tmp / "other"))
        for _, pkt in all_fixtures():
            other.post(pkt)
        self.assertEqual((other.root / "state" / "current.json").read_text(), cur)
        self.assertEqual(self.store.check(), [])

    def test_check_detects_drift(self):
        for _, pkt in all_fixtures()[:3]:
            self.post(pkt)
        p = self.root / "state" / "current.json"
        obj = json.loads(p.read_text())
        obj["defects"]["ORI-052"]["state"] = "WARDEN_VERIFIED"  # hand-edit = drift
        p.write_text(json.dumps(obj))
        self.assertEqual(len(self.store.check()), 1)
        rc, out = run_cli("--root", str(self.root), "rebuild", "--check")
        self.assertEqual(rc, 1)
        self.assertIn("STATE DRIFT", out)

    def test_committed_package_state_matches_committed_history(self):
        self.assertEqual(Store(PACKAGE_DIR).check(), [])

    def test_committed_example_run_matches_rebuild(self):
        ex = PACKAGE_DIR / "examples" / "replay_ori052"
        self.assertEqual(Store(ex).check(), [])
        self.assertEqual(len(Store(ex).packet_files()), len(all_fixtures()))


class CliEndToEnd(SwitchboardCase):
    def test_cli_replay_status_brief_handoff_new_mission(self):
        r = str(self.root)
        rc, out = run_cli("--root", r, "validate", *[str(p) for p in sorted(FIXTURES.glob("*.json"))])
        self.assertEqual(rc, 0, out)
        rc, out = run_cli("--root", r, "replay", str(FIXTURES), "--strict")
        self.assertEqual(rc, 0, out)
        self.assertIn("IMPLEMENTER_AUDITOR_CONFLICT", out)
        rc, out = run_cli("--root", r, "status")
        self.assertIn("ORI-052   WARDEN_VERIFIED", out)
        rc, out = run_cli("--root", r, "morning-brief")
        self.assertIn("Verified closed: ORI-052", out)
        rc, out = run_cli("--root", r, "rebuild", "--check")
        self.assertEqual(rc, 0, out)

    def test_cli_post_result_rejects_wrong_sha(self):
        r = str(self.root)
        for name in ("01", "02"):
            [p] = FIXTURES.glob(f"{name}-*.json")
            rc, out = run_cli("--root", r, "post-mission" if name == "02" else "post-defect", str(p))
            self.assertEqual(rc, 0, out)
        bad = json.loads(next(FIXTURES.glob("03-*.json")).read_text())
        bad["start_sha"] = SHA_C
        bp = self.tmp / "bad.json"
        bp.write_text(json.dumps(bad))
        rc, out = run_cli("--root", r, "post-result", str(bp))
        self.assertEqual(rc, 1)
        self.assertIn("SHA_MISMATCH", out)

    def test_cli_invalid_packet_validate_fails(self):
        bp = self.tmp / "m.json"
        m = json.loads(next(FIXTURES.glob("02-*.json")).read_text())
        del m["scope"]
        bp.write_text(json.dumps(m))
        rc, out = run_cli("--root", str(self.root), "validate", str(bp))
        self.assertEqual(rc, 1)
        self.assertIn("scope", out)

    def test_new_mission_from_handoff(self):
        from coordination.switchboard.store import Store
        self.root = self.make_root(self.tmp / "nm", {"max_cycles": 5})
        self.store = Store(self.root)
        self.post_upto("05")
        r = str(self.root)
        rc, out = run_cli("--root", r, "next-handoff")
        self.assertEqual(rc, 0)
        [hp] = (self.root / "handoffs").glob("HANDOFF-*.json")
        rc, out = run_cli("--root", r, "new-mission", "--from-handoff", str(hp), "--created-by", "Gilfoyle",
                          "--created-at", "2026-09-26T08:00:00-04:00", "--artifact",
                          "exports/diagnostics/safety_inventory_plc3_evidence.json")
        self.assertEqual(rc, 0, out)
        st = self.state()
        [(mid, m)] = [(k, v) for k, v in st["missions"].items() if v["status"] == "AWAITING_RESULT"]
        self.assertEqual(m["assigned_to"], "Anton")
        self.assertEqual(m["required_start_sha"], SHA_B)
        self.assertEqual(st["next_owner"], "Anton")

    def test_new_mission_flags(self):
        r = str(self.root)
        rc, out = run_cli("--root", r, "new-mission", "--id", "ANTON-X-01", "--title", "t", "--assigned-to", "Anton",
                          "--branch", "feature/x", "--start-sha", SHA_B, "--scope", "s", "--accept", "a",
                          "--created-at", "2026-09-26T08:00:00-04:00", "--dry-run")
        self.assertEqual(rc, 0, out)
        self.assertEqual(json.loads(out)["mission_id"], "ANTON-X-01")
        self.assertEqual(self.store.packet_files(), [])


if __name__ == "__main__":
    unittest.main()

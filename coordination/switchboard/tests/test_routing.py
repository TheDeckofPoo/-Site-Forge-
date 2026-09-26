"""Handoff engine routing rules and the CRITICAL LAW (claim != closure)."""
from __future__ import annotations

import copy
import json
import unittest

from .helpers import SHA_B, SHA_C, SwitchboardCase, all_fixtures, fixture


class AntonCannotSelfVerify(SwitchboardCase):
    def test_fixed_claim_only_reaches_claimed_fixed(self):
        self.post_upto("03")
        d = self.defect()
        self.assertEqual(d["state"], "CLAIMED_FIXED")
        self.assertEqual(d["current_owner"], "Warden")
        self.assertIsNone(d["warden_verification"])
        self.assertEqual(d["implementer_claim"]["sha"], SHA_B)
        # Anton's mission is complete; next work goes to Warden, never closure
        self.assertEqual(self.state()["next_owner"], "Warden")
        self.assertNotIn("CLOSED", json.dumps(self.state()))

    def test_implementer_pass_verdict_rejected(self):
        self.post_upto("02")
        r = fixture("03")
        r["ori_dispositions"] = [{"ori_id": "ORI-052", "disposition": "PASS", "verified_sha": SHA_B}]
        r["claimed_fixes"] = []
        res = self.post(r, expect_ok=False)
        self.assertIn("UNAUTHORIZED_VERIFICATION", self.codes(res))
        self.assertEqual(self.defect()["state"], "OPEN")
        st = self.state()
        self.assertEqual(st["next_owner"], "Curtis")
        self.assertEqual(st["night_shift"]["loop_status"], "HALTED")

    def test_implementer_cannot_verify_own_claim_later(self):
        self.post_upto("03")
        m = fixture("04")
        m["mission_id"], m["assigned_to"] = "ANTON-SELF-VERIFY", "Anton"
        self.post(m)
        r = fixture("05")
        r["mission_id"], r["agent"] = "ANTON-SELF-VERIFY", "Anton"
        r["ori_dispositions"][0]["disposition"] = "PASS"
        res = self.post(r, expect_ok=False)
        self.assertIn("UNAUTHORIZED_VERIFICATION", self.codes(res))
        self.assertEqual(self.defect()["state"], "CLAIMED_FIXED")

    def test_non_auditor_roles_cannot_verify(self):
        self.post_upto("03")
        for agent in ("Hunter", "Gilfoyle", "Curtis"):
            m = fixture("04")
            m["mission_id"], m["assigned_to"] = f"VERIFY-BY-{agent.upper()}", agent
            self.post(m)
            r = fixture("05")
            r["mission_id"], r["agent"] = m["mission_id"], agent
            r["ori_dispositions"][0]["disposition"] = "PASS"
            r["ori_dispositions"][0]["verified_sha"] = SHA_B
            res = self.post(r, expect_ok=False)
            self.assertIn("UNAUTHORIZED_VERIFICATION", self.codes(res), agent)
        self.assertEqual(self.defect()["state"], "CLAIMED_FIXED")


class WardenVerdicts(SwitchboardCase):
    night_shift = {"max_cycles": 5}

    def test_warden_fail_reopens_and_routes_to_anton(self):
        self.post_upto("05")
        d = self.defect()
        self.assertEqual(d["state"], "REOPENED")
        self.assertEqual(d["current_owner"], "Anton")
        self.assertIn("TPNA1", d["reproducer"])
        self.assertEqual(d["warden_verification"]["verdict"], "FAIL")
        st = self.state()
        self.assertEqual(st["next_owner"], "Anton")
        self.assertEqual(st["night_shift"]["loop_status"], "RUNNING")

    def test_warden_pass_verifies(self):
        for name, pkt in all_fixtures():
            self.post(pkt)
        d = self.defect()
        self.assertEqual(d["state"], "WARDEN_VERIFIED")
        self.assertEqual(d["warden_verification"]["verified_sha"], SHA_C)
        self.assertEqual(d["warden_verification"]["auditor"], "Warden")
        subs = self.store.load_subsystems()["subsystems"]
        self.assertEqual(subs["Safety"]["state"], "CANDIDATE_FOR_GRADUATION")

    def test_warden_new_ori_created_open_owner_anton(self):
        self.post_upto("04")
        r = fixture("05")
        r["new_oris"] = [{"ori_id": "ORI-061", "title": "MCR AUX feedback missing after Area delete",
                          "subsystem": "Safety", "reproducer": "TPNA2: delete Area with MCR",
                          "evidence": ["artifacts/warden/ORI-061.md"]}]
        res = self.post(r)
        new = self.defect("ORI-061")
        self.assertEqual(new["state"], "OPEN")
        self.assertEqual(new["current_owner"], "Anton")
        self.assertEqual(new["discovered_by"], "Warden")
        self.assertEqual(new["first_seen_sha"], SHA_B)
        self.assertEqual(self.state()["next_owner"], "Anton")
        self.assertTrue(res["accepted"])


class EngineerDecisionStops(SwitchboardCase):
    night_shift = {"max_cycles": 5}

    def test_engineer_decision_required_routes_to_curtis_and_halts(self):
        self.post_upto("04")
        r = fixture("05")
        r["stop_reason"] = "ENGINEER_DECISION_REQUIRED"
        r["engineer_decisions_required"] = [{"question": "Is REVIEW acceptable for bare MCR coil?", "ori_id": "ORI-052"}]
        self.post(r)
        st = self.state()
        self.assertEqual(st["next_owner"], "Curtis")
        self.assertEqual(st["night_shift"]["loop_status"], "HALTED")
        self.assertIn("ENGINEER_DECISION_REQUIRED", st["night_shift"]["halt_reasons"])
        self.assertTrue(st["recommended_after_review"].startswith("Anton"))
        self.assertEqual(len([e for e in st["engineer_decisions_required"] if not e["resolved"]]), 1)
        # a new mission does not restart routing
        m = fixture("07")
        res = self.post(m)
        self.assertIn("MISSION_WHILE_HALTED", self.codes(res))
        self.assertEqual(self.state()["next_owner"], "Curtis")
        # only the engineer may resume
        bad = fixture("06")
        bad["decision_id"], bad["decided_by"] = "GILFOYLE-RESUME", "Gilfoyle"
        res = self.post(bad, expect_ok=False)
        self.assertIn("UNAUTHORIZED_DECISION", self.codes(res))
        self.assertEqual(self.state()["next_owner"], "Curtis")
        self.post(fixture("06"))
        st = self.state()
        self.assertEqual(st["night_shift"]["loop_status"], "RUNNING")
        self.assertEqual(st["next_owner"], "Anton")  # pending mission ANTON-ORI052-02

    def test_disposition_marker_also_stops(self):
        self.post_upto("02")
        r = fixture("03")
        r["ori_dispositions"] = [{"ori_id": "ORI-052", "disposition": "PROPOSE_DEFER", "notes": "needs print"}]
        r["claimed_fixes"] = []
        self.post(r)
        st = self.state()
        self.assertEqual(st["next_owner"], "Curtis")
        self.assertEqual(self.defect()["state"], "OPEN")


class MaxCycles(SwitchboardCase):
    def test_default_one_cycle_stops_after_first_audit(self):
        self.assertEqual(self.store.config()["night_shift"]["max_cycles"], 1)
        self.post_upto("05")
        st = self.state()
        ns = st["night_shift"]
        self.assertEqual((ns["cycles_used"], ns["loop_status"]), (1, "HALTED"))
        self.assertIn("MAX_CYCLES (1/1)", ns["halt_reasons"])
        self.assertEqual(st["next_owner"], "Curtis")
        self.assertTrue(st["recommended_after_review"].startswith("Anton: Fix ORI-052 (REOPENED"))

    def test_two_cycles(self):
        root = self.make_root(self.tmp / "two", {"max_cycles": 2})
        from coordination.switchboard.store import Store
        self.store = Store(root)
        self.post_upto("05")
        self.assertEqual(self.state()["night_shift"]["loop_status"], "RUNNING")
        for name, pkt in all_fixtures():
            if name[:2] in ("07", "08", "09", "10"):
                self.post(pkt)
        ns = self.state()["night_shift"]
        self.assertEqual((ns["cycles_used"], ns["loop_status"]), (2, "HALTED"))

    def test_budget_limit_stops(self):
        root = self.make_root(self.tmp / "budget", {"max_cycles": 9, "budget_limit": 5})
        from coordination.switchboard.store import Store
        self.store = Store(root)
        self.post_upto("02")
        r = fixture("03")
        r["cost"] = 5
        self.post(r)
        st = self.state()
        self.assertEqual(st["next_owner"], "Curtis")
        self.assertTrue(any(h.startswith("BUDGET_EXHAUSTED") for h in st["night_shift"]["halt_reasons"]))


class Ori052Lifecycle(SwitchboardCase):
    def test_full_replay_transitions(self):
        for name, pkt in all_fixtures():
            self.post(pkt)
        hist = [(h["from"], h["to"], h["by"], h["owner"]) for h in self.defect()["history"]]
        self.assertEqual(hist, [
            (None, "OPEN", "Warden", "Anton"),
            ("OPEN", "CLAIMED_FIXED", "Anton", "Warden"),
            ("CLAIMED_FIXED", "REOPENED", "Warden", "Anton"),
            ("REOPENED", "CLAIMED_FIXED", "Anton", "Warden"),
            ("CLAIMED_FIXED", "WARDEN_VERIFIED", "Warden", "Curtis"),
        ])
        codes = [f["code"] for f in self.state()["flags"]]
        self.assertEqual(codes, ["IMPLEMENTER_AUDITOR_CONFLICT"])


class SubsystemLock(SwitchboardCase):
    night_shift = {"max_cycles": 9}

    def test_lock_then_regression(self):
        for name, pkt in all_fixtures():
            self.post(pkt)
        lock = {"packet_type": "decision", "decision_id": "CURTIS-LOCK-SAFETY", "decided_by": "Curtis",
                "decided_at": "2026-09-26T11:00:00-04:00", "summary": "Lock Safety",
                "subsystem_overrides": [{"subsystem": "Safety", "state": "LOCKED", "reason": "ORI-052 verified"}]}
        self.post(lock)
        self.assertEqual(self.defect()["state"], "LOCKED_REGRESSION")
        self.assertEqual(self.store.load_subsystems()["subsystems"]["Safety"]["state"], "LOCKED")
        m = copy.deepcopy(fixture("09"))
        m["mission_id"] = "WARDEN-REGRESSION-01"
        self.post(m)
        r = copy.deepcopy(fixture("10"))
        r["mission_id"] = "WARDEN-REGRESSION-01"
        r["ori_dispositions"][0]["disposition"] = "FAIL"
        res = self.post(r)
        self.assertIn("REGRESSION", self.codes(res))
        self.assertEqual(self.defect()["state"], "REOPENED")
        self.assertEqual(self.store.load_subsystems()["subsystems"]["Safety"]["state"], "REOPENED_BY_REGRESSION")

    def test_engineer_can_defer(self):
        self.post(fixture("01"))
        self.post({"packet_type": "decision", "decision_id": "CURTIS-DEFER", "decided_by": "Curtis",
                   "decided_at": "2026-09-26T11:00:00-04:00", "summary": "defer",
                   "defect_overrides": [{"ori_id": "ORI-052", "state": "DEFERRED", "reason": "needs site print"}]})
        self.assertEqual(self.defect()["state"], "DEFERRED")


if __name__ == "__main__":
    unittest.main()

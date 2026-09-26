"""Contradiction / integrity detection — one test per flag code."""
from __future__ import annotations

import unittest

from .helpers import SHA_A, SHA_C, SwitchboardCase, fixture


class Contradictions(SwitchboardCase):
    night_shift = {"max_cycles": 9}

    def assertFlag(self, res, code, severity):
        hits = [f for f in res["flags"] if f["code"] == code]
        self.assertTrue(hits, f"{code} not raised: {res['flags']}")
        self.assertEqual(hits[0]["severity"], severity)

    def test_implementer_auditor_conflict(self):
        self.post_upto("04")
        res = self.post(fixture("05"))
        self.assertFlag(res, "IMPLEMENTER_AUDITOR_CONFLICT", "WARN")
        self.assertEqual(self.defect()["state"], "REOPENED")

    def test_sha_mismatch_rejected_and_halts(self):
        self.post_upto("02")
        r = fixture("03")
        r["start_sha"] = SHA_C
        res = self.post(r, expect_ok=False)
        self.assertFlag(res, "SHA_MISMATCH", "REJECT")
        st = self.state()
        self.assertEqual(self.defect()["state"], "OPEN")
        self.assertEqual(st["next_owner"], "Curtis")
        self.assertTrue(any(h.startswith("SHA_MISMATCH") for h in st["night_shift"]["halt_reasons"]))
        # mission still awaits a correct result; rejected packet is kept for audit
        self.assertEqual(st["missions"]["ANTON-ORI052-01"]["status"], "AWAITING_RESULT")
        self.assertEqual(len(self.store.packet_files()), 3)

    def test_sha_mismatch_without_stop_switch_lets_agent_retry(self):
        from coordination.switchboard.store import Store
        self.store = Store(self.make_root(self.tmp / "nostop", {"stop_on_sha_mismatch": False}))
        self.post_upto("02")
        r = fixture("03")
        r["start_sha"] = SHA_C
        res = self.post(r, expect_ok=False)
        self.assertFlag(res, "SHA_MISMATCH", "REJECT")
        st = self.state()
        self.assertEqual(st["night_shift"]["loop_status"], "RUNNING")
        self.assertEqual(st["next_owner"], "Anton")
        self.post(fixture("03"))  # corrected result accepted
        self.assertEqual(self.defect()["state"], "CLAIMED_FIXED")

    def test_short_sha_accepted(self):
        self.post_upto("02")
        r = fixture("03")
        r["start_sha"] = SHA_A[:7]
        self.post(r)

    def test_branch_mismatch(self):
        self.post_upto("02")
        r = fixture("03")
        r["branch"] = "main"
        res = self.post(r, expect_ok=False)
        self.assertFlag(res, "BRANCH_MISMATCH", "REJECT")
        self.assertEqual(self.defect()["state"], "OPEN")

    def test_missing_artifact(self):
        self.post_upto("02")
        r = fixture("03")
        r["artifacts"] = []
        res = self.post(r)
        self.assertFlag(res, "MISSING_ARTIFACT", "WARN")

    def test_missing_tests(self):
        self.post_upto("02")
        r = fixture("03")
        r["tests_run"] = []
        res = self.post(r)
        self.assertFlag(res, "MISSING_TESTS", "WARN")
        self.assertEqual(self.defect()["state"], "CLAIMED_FIXED")  # still only a claim

    def test_unknown_mission(self):
        self.post_upto("02")
        r = fixture("03")
        r["mission_id"] = "ANTON-DOES-NOT-EXIST"
        res = self.post(r, expect_ok=False)
        self.assertFlag(res, "UNKNOWN_MISSION", "REJECT")
        self.assertEqual(self.defect()["state"], "OPEN")

    def test_wrong_mission_agent(self):
        self.post_upto("02")
        r = fixture("03")
        r["agent"] = "Hunter"
        res = self.post(r, expect_ok=False)
        self.assertFlag(res, "WRONG_MISSION_AGENT", "REJECT")

    def test_duplicate_result(self):
        self.post_upto("03")
        res = self.post(fixture("03"), expect_ok=False)
        self.assertFlag(res, "DUPLICATE_RESULT", "REJECT")

    def test_warden_verifies_different_sha_than_claim(self):
        self.post_upto("03")
        m = fixture("04")
        self.post(m)
        r = fixture("05")
        r["ori_dispositions"][0]["disposition"] = "PASS"
        r["ori_dispositions"][0]["verified_sha"] = SHA_A
        r["verified_sha"] = SHA_A
        res = self.post(r)
        self.assertFlag(res, "VERIFIED_SHA_MISMATCH", "BLOCK")
        self.assertEqual(self.defect()["state"], "CLAIMED_FIXED")  # verdict withheld
        st = self.state()
        self.assertEqual(st["next_owner"], "Curtis")
        self.assertEqual(st["night_shift"]["loop_status"], "HALTED")

    def test_auditor_claiming_fix_is_independence_violation(self):
        self.post_upto("04")
        r = fixture("05")
        r["ori_dispositions"][0]["disposition"] = "FIXED"
        res = self.post(r, expect_ok=False)
        self.assertFlag(res, "INDEPENDENCE_VIOLATION", "REJECT")

    def test_verdict_without_verified_sha(self):
        self.post_upto("04")
        r = fixture("05")
        del r["verified_sha"]
        del r["ori_dispositions"][0]["verified_sha"]
        res = self.post(r, expect_ok=False)
        self.assertFlag(res, "MISSING_VERIFIED_SHA", "REJECT")

    def test_pass_without_claim(self):
        self.post(fixture("01"))
        m = fixture("04")
        m["required_start_sha"] = SHA_A
        self.post(m)
        r = fixture("05")
        r["start_sha"] = r["final_sha"] = r["verified_sha"] = SHA_A
        r["ori_dispositions"][0].update(disposition="PASS", verified_sha=SHA_A)
        res = self.post(r)
        self.assertFlag(res, "VERIFY_WITHOUT_CLAIM", "BLOCK")
        self.assertEqual(self.defect()["state"], "OPEN")

    def test_dirty_tree(self):
        self.post_upto("02")
        r = fixture("03")
        r["working_tree_clean"] = False
        res = self.post(r)
        self.assertFlag(res, "DIRTY_TREE", "BLOCK")
        self.assertEqual(self.state()["next_owner"], "Curtis")

    def test_not_pushed_and_failing_tests(self):
        self.post_upto("02")
        r = fixture("03")
        r["pushed"] = False
        r["test_results"]["failed"] = 2
        res = self.post(r)
        self.assertFlag(res, "NOT_PUSHED", "WARN")
        self.assertFlag(res, "TESTS_FAILING", "WARN")

    def test_unknown_ori_claim(self):
        self.post_upto("02")
        r = fixture("03")
        r["claimed_fixes"] = ["ORI-052", "ORI-999"]
        res = self.post(r)
        self.assertFlag(res, "UNKNOWN_ORI", "BLOCK")
        self.assertFlag(res, "ORI_OUT_OF_SCOPE", "WARN")


if __name__ == "__main__":
    unittest.main()

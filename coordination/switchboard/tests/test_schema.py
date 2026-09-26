"""JSON schema validation + invalid packet rejection."""
from __future__ import annotations

import copy
import json
import unittest

from coordination.switchboard.store import PACKAGE_DIR, validate_packet
from coordination.switchboard.validator import SCHEMA_DIR, validate

from .helpers import SwitchboardCase, all_fixtures, fixture


class SchemaFiles(unittest.TestCase):
    def test_all_schema_files_present_and_declare_draft(self):
        for name in ("mission", "result", "defect", "handoff", "state", "decision"):
            s = json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
            self.assertTrue(s["$schema"].startswith("https://json-schema.org/draft/2020-12"), name)

    def test_all_replay_fixtures_validate(self):
        for name, pkt in all_fixtures():
            t, errs = validate_packet(pkt)
            self.assertEqual(errs, [], name)
            self.assertIn(t, ("mission", "result", "defect", "decision"))

    def test_committed_state_files_validate(self):
        for f in ("current.json", "subsystem_status.json"):
            obj = json.loads((PACKAGE_DIR / "state" / f).read_text(encoding="utf-8"))
            self.assertEqual(validate(obj, "state"), [], f)

    def test_validator_subset(self):
        schema = {"type": "object", "required": ["a"], "additionalProperties": False,
                  "properties": {"a": {"type": "string", "pattern": "^x"}, "b": {"enum": [1, 2]}}}
        from coordination.switchboard.validator import iter_errors
        self.assertEqual(list(iter_errors({"a": "xy"}, schema)), [])
        errs = list(iter_errors({"a": "y", "b": 3, "c": 1}, schema))
        self.assertEqual(len(errs), 3, errs)
        self.assertTrue(list(iter_errors({}, schema)))

    def test_warden_result_can_express_verdict_new_ori_and_engineer_decision(self):
        r = fixture("05")
        r = copy.deepcopy(r)
        r["new_oris"] = [{"ori_id": "ORI-060", "title": "t", "subsystem": "Safety", "reproducer": "TPNA2",
                          "evidence": ["artifacts/warden/x.md"]}]
        r["engineer_decisions_required"] = [{"question": "Accept REVIEW for bare MCR?"}]
        r["stop_reason"] = "ENGINEER_DECISION_REQUIRED"
        self.assertEqual(validate(r, "result"), [])


class InvalidMissionRejected(SwitchboardCase):
    def test_missing_required_field_rejected_and_not_stored(self):
        m = fixture("02")
        del m["required_start_sha"]
        res = self.store.post(m)
        self.assertFalse(res["accepted"])
        self.assertIsNone(res["stored"])
        self.assertTrue(any("required_start_sha" in e for e in res["errors"]))
        self.assertEqual(self.store.packet_files(), [])

    def test_bad_sha_and_empty_acceptance_rejected(self):
        m = fixture("02")
        m["required_start_sha"] = "not-a-sha"
        m["acceptance_criteria"] = []
        errs = validate(m, "mission")
        self.assertTrue(any("required_start_sha" in e for e in errs))
        self.assertTrue(any("acceptance_criteria" in e for e in errs))

    def test_unknown_field_and_bad_ori_rejected(self):
        m = fixture("02")
        m["surprise"] = 1
        m["ori_ids"] = ["ORI52"]
        errs = validate(m, "mission")
        self.assertTrue(any("surprise" in e for e in errs))
        self.assertTrue(any("ORI52" in e for e in errs))

    def test_mission_for_unknown_agent_rejected(self):
        self.post(fixture("01"))
        m = fixture("02")
        m["assigned_to"] = "Mallory"
        res = self.post(m, expect_ok=False)
        self.assertIn("UNKNOWN_AGENT", self.codes(res))

    def test_registration_must_be_open(self):
        d = fixture("01")
        d["state"] = "WARDEN_VERIFIED"
        res = self.post(d, expect_ok=False)
        self.assertIn("INVALID_REGISTRATION_STATE", self.codes(res))
        self.assertEqual(self.state()["defects"], {})


if __name__ == "__main__":
    unittest.main()

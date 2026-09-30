#!/usr/bin/env python3
"""ORI-076 + CD04/CD06/CD07/CD08/CD09 — CURRENT-RUN Safety/confidence fidelity.

Sanitized synthetic fixtures only — no proprietary MSC Reno TAR contents.
Preserves Day-1 ORI-045/068/072 contracts (see test_day1_*).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_es_compiler import build_safety_zone_irs  # noqa: E402
from fortna_safety_assignment_gate import (  # noqa: E402
    canonical_engineer_zones,
    dedupe_engineer_zones,
    engineer_assigned_member_count,
    explicit_engineer_assigned_members,
)
from fortna_safety_endpoint_integrity import (  # noqa: E402
    LIFECYCLE_FOUND,
    LIFECYCLE_GENERATED,
    LIFECYCLE_OWNED,
    LIFECYCLE_PHYSICALLY_BOUND,
    LIFECYCLE_ZONED,
    apply_canonical_endpoint_confidence,
    classify_safety_row_purpose,
    decide_endpoint_confidence,
    resolve_safety_signal_roles,
    _classify_safety_signal_role,
)


class TestOri076DuplicateZoneState(unittest.TestCase):
    """Duplicate Safety zone state / phantom engineer member counts."""

    def test_dedupe_three_shells_same_area(self) -> None:
        zones = [
            {
                "name": "Default Safety",
                "isDefault": True,
                "defaultSafety": True,
                "members": ["ESPB2", "ESPB24", "ESLS2"],
            },
            {
                "name": "PICK_ESZ",
                "engineering_name": "PICK_ESZ",
                "source_id": "PICK_ESZ",
                "areaRef": "PICK",
                "zoneOrigin": "ENGINEER",
                "engineerEdited": True,
                "createdBy": "engineer",
                "members": [],
                "conveyors": ["P56", "P57"],
            },
            {
                "name": "MSCRENOPICK_ESZone1",
                "source_id": "MSCRENOPICK_ESZone1",
                "areaRef": "PICK",
                "members": [],
                "conveyors": ["P56", "P57"],
            },
            {
                "name": "szone_zh22il0",
                "engineering_name": "PICK_ESZ",
                "source_id": "szone_zh22il0",
                "areaRef": "PICK",
                "zoneOrigin": "ENGINEER",
                "engineerEdited": True,
                "createdBy": "engineer",
                "members": [],
                "conveyors": ["P56", "P57"],
            },
        ]
        deduped = dedupe_engineer_zones(zones)
        eng = canonical_engineer_zones(deduped)
        self.assertEqual(len(eng), 1, eng)
        survivor = eng[0]
        self.assertTrue(
            str(survivor.get("source_id") or "").startswith("szone_")
            or survivor.get("zoneOrigin") == "ENGINEER",
            survivor,
        )
        self.assertEqual(
            str(survivor.get("engineering_name") or survivor.get("name")),
            "PICK_ESZ",
        )
        # Default stays separate
        defaults = [z for z in deduped if z.get("isDefault") or z.get("defaultSafety")]
        self.assertEqual(len(defaults), 1)
        self.assertEqual(engineer_assigned_member_count(deduped), 0)

    def test_default_members_not_engineer_count(self) -> None:
        zones = [
            {
                "name": "Default Safety",
                "isDefault": True,
                "defaultSafety": True,
                "members": [f"ES{i}" for i in range(46)],
            },
            {
                "name": "PICK_ESZ",
                "source_id": "szone_1",
                "zoneOrigin": "ENGINEER",
                "engineerEdited": True,
                "createdBy": "engineer",
                "members": [],
            },
        ]
        self.assertEqual(engineer_assigned_member_count(zones), 0)
        intent = explicit_engineer_assigned_members(zones)
        self.assertEqual(intent, [])

    def test_engineer_members_count_actual_devices(self) -> None:
        zones = [
            {
                "name": "Default Safety",
                "isDefault": True,
                "members": ["ESPB99"],
            },
            {
                "name": "Z1",
                "source_id": "szone_a",
                "zoneOrigin": "ENGINEER",
                "engineerEdited": True,
                "members": ["ESPB2", "ESPB24"],
                "membersOrigin": "ENGINEER_ASSIGNED",
            },
            {
                "name": "Z1",
                "source_id": "Z1",  # name-as-sid duplicate
                "zoneOrigin": "ENGINEER",
                "engineerEdited": True,
                "members": ["ESPB2", "ESLS2"],
                "membersOrigin": "ENGINEER_ASSIGNED",
            },
        ]
        self.assertEqual(engineer_assigned_member_count(zones), 3)
        eng = canonical_engineer_zones(zones)
        self.assertEqual(len(eng), 1)

    def test_es_ir_collapses_duplicate_shells(self) -> None:
        irs = build_safety_zone_irs(
            engineer_zones=[
                {
                    "name": "PICK_ESZ",
                    "engineering_name": "PICK_ESZ",
                    "source_id": "szone_x",
                    "areaRef": "PICK",
                    "zoneOrigin": "ENGINEER",
                    "engineerEdited": True,
                    "createdBy": "engineer",
                    "members": [],
                    "conveyors": ["P1", "P2"],
                },
                {
                    "name": "MSCRENOPICK_ESZone1",
                    "source_id": "MSCRENOPICK_ESZone1",
                    "areaRef": "PICK",
                    "members": [],
                    "conveyors": ["P1", "P2"],
                },
                {
                    "name": "szone_zh22il0",
                    "engineering_name": "PICK_ESZ",
                    "source_id": "szone_zh22il0",
                    "areaRef": "PICK",
                    "zoneOrigin": "ENGINEER",
                    "engineerEdited": True,
                    "members": [],
                    "conveyors": ["P1", "P2"],
                },
            ],
            areas=["PICK"],
            area_conveyors={"PICK": ["P1", "P2"]},
        )
        names = [z.name for z in irs]
        self.assertEqual(len(names), 1, names)
        self.assertEqual(names[0], "PICK_ESZ")


class TestCd04ConfidenceCoherence(unittest.TestCase):
    """PROVEN cannot also be unresolved across report paths."""

    def test_word_only_not_proven(self) -> None:
        d = {
            "name": "ESPB2",
            "kind": "ESTOP",
            "confidence": "PROVEN",  # incoherent prior stamp
            "physicalEndpoint": "1100.17",
            "endpoint_proof_depth": "WORD_ONLY",
            "hardwareBacked": False,
            "machine_ownership": "UNKNOWN",
            "review_reason": "WORD_ONLY_EVIDENCE",
            "status": "UNASSIGNED",
        }
        decision = decide_endpoint_confidence(d)
        self.assertNotEqual(decision["confidence"], "PROVEN")
        self.assertEqual(decision["confidence"], "REVIEW_REQUIRED")
        apply_canonical_endpoint_confidence([d])
        self.assertEqual(d["confidence"], "REVIEW_REQUIRED")
        self.assertEqual(d["endpoint_confidence"], "REVIEW_REQUIRED")
        self.assertTrue(d["found"])
        self.assertFalse(d["physically_bound"])
        self.assertFalse(d["generated"])

    def test_full_hardware_and_ownership_is_proven(self) -> None:
        d = {
            "name": "ESPB24",
            "kind": "ESTOP",
            "physicalEndpoint": "AENTR1:I.Data[2].0",
            "endpoint_proof_depth": "FULL",
            "hardwareBacked": True,
            "machine": "TESTPICK",
            "machine_ownership": "PROVEN",
        }
        decision = decide_endpoint_confidence(d)
        self.assertEqual(decision["confidence"], "PROVEN")
        self.assertTrue(decision["lifecycle"][LIFECYCLE_PHYSICALLY_BOUND])
        self.assertTrue(decision["lifecycle"][LIFECYCLE_OWNED])
        self.assertTrue(decision["lifecycle"][LIFECYCLE_FOUND])
        self.assertFalse(decision["lifecycle"][LIFECYCLE_GENERATED])


class TestCd06Cd07SafetyProvenRules(unittest.TestCase):
    """Machine naming alone insufficient; foreign ≠ local PROVEN; states separate."""

    def test_machine_name_only_not_proven(self) -> None:
        d = {
            "name": "ESPB32",
            "kind": "ESTOP",
            "machine": "TESTPICK",
            "Machine_Name": "TESTPICK",
            "machine_ownership": "PROVEN",  # naming stamp only
            "physicalEndpoint": "",
            "endpoint_proof_depth": "NONE",
            "hardwareBacked": False,
            "confidence": "PROVEN",
        }
        decision = decide_endpoint_confidence(d)
        self.assertNotEqual(decision["confidence"], "PROVEN")
        self.assertIn("MACHINE_NAME_ONLY", decision["reasons"])

    def test_foreign_estop_not_local_proven(self) -> None:
        d = {
            "name": "ESPB27",
            "kind": "ESTOP",
            "machine": "OTHERSITE",
            "machine_ownership": "FOREIGN",
            "inventory_scope": "UNRELATED_FOREIGN",
            "physicalEndpoint": "AENTR9:I.Data[1].0",
            "endpoint_proof_depth": "FULL",
            "hardwareBacked": True,
            "confidence": "PROVEN",
        }
        decision = decide_endpoint_confidence(d)
        self.assertEqual(decision["confidence"], "FOREIGN")
        self.assertFalse(decision["lifecycle"][LIFECYCLE_OWNED])
        apply_canonical_endpoint_confidence([d])
        self.assertEqual(d["confidence"], "FOREIGN")
        self.assertFalse(d["assignable"])

    def test_lifecycle_states_remain_separate(self) -> None:
        d = {
            "name": "ESLS2",
            "kind": "ESLS",
            "physicalEndpoint": "AENTR1:I.Data[3].1",
            "endpoint_proof_depth": "FULL",
            "hardwareBacked": True,
            "machine": "TESTPICK",
            "machine_ownership": "PROVEN",
            "status": "UNASSIGNED",
        }
        apply_canonical_endpoint_confidence([d])
        self.assertTrue(d["found"])
        self.assertTrue(d["owned"])
        self.assertTrue(d["physically_bound"])
        self.assertFalse(d["zoned"])  # not yet assigned
        self.assertFalse(d["generated"])
        # Keys must exist distinctly
        for k in (
            LIFECYCLE_FOUND,
            LIFECYCLE_OWNED,
            LIFECYCLE_PHYSICALLY_BOUND,
            LIFECYCLE_ZONED,
            LIFECYCLE_GENERATED,
        ):
            self.assertIn(k, d["lifecycle_states"])


class TestCd08EstopFeedbackNotCommand(unittest.TestCase):
    """E-stop monitoring inputs are FEEDBACK/MONITOR — never COMMAND."""

    def test_estop_role_not_command(self) -> None:
        self.assertEqual(
            _classify_safety_signal_role("ESPB24", kind="ESTOP"),
            "FEEDBACK",
        )
        self.assertEqual(
            _classify_safety_signal_role(
                "ESPB24", kind="ESTOP", existing_role="COMMAND"
            ),
            "FEEDBACK",
        )
        self.assertEqual(
            _classify_safety_signal_role(
                "ESPB24", kind="ESTOP", existing_role="MONITOR"
            ),
            "MONITOR",
        )

    def test_device_has_no_command_endpoint(self) -> None:
        devices = [
            {
                "name": "ESPB24",
                "kind": "ESTOP",
                "physicalEndpoint": "AENTR1:I.Data[2].0",
                "signals": [
                    {
                        "name": "ESPB24",
                        "kind": "ESTOP",
                        "physicalEndpoint": "AENTR1:I.Data[2].0",
                        "signalRole": "COMMAND",  # hostile prior
                    }
                ],
            }
        ]
        resolve_safety_signal_roles(devices)
        d = devices[0]
        self.assertNotIn("commandEndpoint", d)
        self.assertEqual(d.get("safetyFeedbackEndpoint"), "AENTR1:I.Data[2].0")
        role = (d.get("signals") or [{}])[0].get("safety_role")
        self.assertIn(role, {"FEEDBACK", "MONITOR"})


class TestCd09NonphysicalRows(unittest.TestCase):
    """Memory/nonphysical rows visible but NONPHYSICAL — not failed physical."""

    def test_memory_row_classified_nonphysical(self) -> None:
        row = {
            "name": "MEM_OK_TO_RUN",
            "Interface": "MEM",
            "physicalEndpoint": "",
        }
        self.assertEqual(classify_safety_row_purpose(row), "NONPHYSICAL")
        apply_canonical_endpoint_confidence([row])
        self.assertEqual(row["confidence"], "NONPHYSICAL")
        self.assertEqual(row["status"], "NONPHYSICAL")
        self.assertTrue(row.get("nonphysical"))
        self.assertFalse(row.get("assignable"))
        # Not a failed physical resolution path
        self.assertNotEqual(row.get("review_reason"), "NO_MODULE_CHANNEL_PROOF")
        self.assertEqual(row.get("review_reason"), "NONPHYSICAL_ROW")

    def test_explicit_purpose_nonphysical(self) -> None:
        row = {
            "name": "SW1",
            "purpose": "INTERNAL_MEMORY",
            "confidence": "PROVEN",
        }
        decision = decide_endpoint_confidence(row)
        self.assertEqual(decision["confidence"], "NONPHYSICAL")


class TestDay1ContractsStillPresent(unittest.TestCase):
    """Sanity — Day-1 ORI-045/068 helpers remain intact."""

    def test_ori045_zone_origin_preserved_on_dedupe(self) -> None:
        zones = [
            {
                "name": "Default Packaging EStops",
                "source_id": "szone_pack1",
                "zoneOrigin": "ENGINEER",
                "engineerEdited": True,
                "createdBy": "engineer",
                "members": ["1ES"],
                "membersOrigin": "ENGINEER_ASSIGNED",
            }
        ]
        out = dedupe_engineer_zones(zones)
        self.assertEqual(out[0]["zoneOrigin"], "ENGINEER")
        intent = explicit_engineer_assigned_members(out)
        self.assertEqual([i["device"] for i in intent], ["1ES"])

    def test_js_helpers_exported(self) -> None:
        js = (ROOT / "dashboard" / "fortna-plus.js").read_text(encoding="utf-8")
        self.assertIn("function dedupeSafetyBuildZones", js)
        self.assertIn("ORI-076: engineer assigned count", js)
        self.assertIn("window.dedupeSafetyBuildZones", js)
        sb = (ROOT / "dashboard" / "safety-build.js").read_text(encoding="utf-8")
        self.assertIn("dedupeCanonicalZones", sb)


if __name__ == "__main__":
    unittest.main(verbosity=2)

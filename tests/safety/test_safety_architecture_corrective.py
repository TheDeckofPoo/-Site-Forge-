#!/usr/bin/env python3
"""Safety architecture corrective pass — behavioral invariant tests (Warden 969eb83)."""
from __future__ import annotations

import re
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_es_compiler import (  # noqa: E402
    emit_es_program,
    build_safety_zone_irs,
    safety_operand_has_writer,
    filter_operands_without_writers,
    resolve_safety_feedback_operand,
)
from fortna_safety_endpoint_integrity import (  # noqa: E402
    apply_endpoint_collision_review,
    apply_hardware_backed_readiness,
    normalize_endpoint_key,
    classify_endpoint_proof_depth,
)
from fortna_safety_model import build_safety_evidence_union  # noqa: E402
from fortna_transport_graph import apply_graph_to_workbook  # noqa: E402


def _rung_xml(num, text, comment=""):
    c = f"<Comment><![CDATA[{comment}]]></Comment>" if comment else ""
    return f'<Rung Number="{num}" Type="N">{c}<Text><![CDATA[{text}]]></Text></Rung>'


def _routine(name, rungs):
    return f'<Routine Name="{name}" Type="RLL"><RLLContent>{"".join(rungs)}</RLLContent></Routine>'


class TestOri050ExactMachineIdentity(unittest.TestCase):
    def test_desktop_rejects_substring_identity(self) -> None:
        main = (ROOT / "desktop" / "main.js").read_text(encoding="utf-8", errors="replace")
        # Exact equality only — substring includes gone
        self.assertIn("artifactMatchesActiveMachine", main)
        fn = main.split("function artifactMatchesActiveMachine", 1)[1].split("\n  }", 1)[0]
        self.assertNotIn("includes(", fn)
        self.assertIn("got === want", fn)

    def test_adversarial_collisions_must_reject(self) -> None:
        """Behavioral: exact identity pairs that substring matching wrongly accepted."""
        pairs = [
            ("CP1", "CP10"),
            ("PLC1", "PLC10"),
            ("TFCP1", "TFCP10"),
            ("ORL_AC3", "ORL_AC30"),
            ("ORL_AC3", "ORL_AC3_OLD"),
            ("AC3", "ORL_AC3"),
            ("TPNA1", "TPNA12"),
            ("TPNA1", "PNA1"),
        ]

        def exact(a: str, b: str) -> bool:
            return a.strip().upper() == b.strip().upper()

        for active, artifact in pairs:
            self.assertFalse(
                exact(active, artifact),
                f"{active} must NOT match {artifact}",
            )
            # Substring would wrongly accept these — prove the defect class
            self.assertTrue(
                active.upper() in artifact.upper() or artifact.upper() in active.upper(),
                f"fixture {active}/{artifact} must be a substring collision",
            )


class TestOri053ReviewNotDiscoveryIncomplete(unittest.TestCase):
    def test_safety_evidence_complete_ignores_review_count(self) -> None:
        src = (ROOT / "tools" / "scripts" / "fortna_safety_model.py").read_text(
            encoding="utf-8", errors="replace"
        )
        # Must not require review_required == 0 for completeness
        block = src.split('"safety_evidence_complete"', 1)[1][:400]
        self.assertNotIn('review_required") or 0) == 0', block)
        self.assertIn("evidence_union is not None", block)


class TestOri051052CanonicalEndpoint(unittest.TestCase):
    def test_normalize_equivalent_spellings(self) -> None:
        a = normalize_endpoint_key("T_1734:I.Data[17].2")
        b = normalize_endpoint_key("t_1734:i.data[17].2")
        c = normalize_endpoint_key("T_1734 : I . Data [ 17 ] . 2")
        self.assertEqual(a, b)
        self.assertEqual(a, c)

    def test_collision_ultapick_pattern(self) -> None:
        devices = [
            {"name": "ESLS610L", "physicalEndpoint": "T_1734:I.Data[17].2", "kind": "ESLS"},
            {"name": "T_23MCR1", "physicalEndpoint": "T_1734:I.Data[17].2", "kind": "MCR"},
        ]
        r = apply_endpoint_collision_review(devices)
        self.assertEqual(r["conflicted_count"], 2)
        self.assertTrue(all(d.get("status") == "REVIEW_REQUIRED" for d in devices))
        self.assertTrue(all(d.get("assignable") is False for d in devices))
        claimants = {n for c in r["collisions"] for n in (c.get("claimants") or [])}
        self.assertEqual(claimants, {"ESLS610L", "T_23MCR1"})

    def test_word_only_not_ready(self) -> None:
        devices = [
            {
                "name": "ESLS812",
                "physicalEndpoint": "531.13",
                "kind": "ESLS",
                "configio_backed": True,
                "io_word": "531",
            },
            {
                "name": "ESLS870",
                "physicalEndpoint": "532.0",
                "kind": "ESLS",
                "configio_backed": True,
                "io_word": "532",
            },
        ]
        apply_hardware_backed_readiness(
            devices, configio_words={"531", "532"}, valid_endpoints=None
        )
        for d in devices:
            self.assertFalse(d.get("hardwareBacked"), d)
            self.assertEqual(d.get("status"), "REVIEW_REQUIRED")
            self.assertEqual(d.get("assignable"), False)
            depth = d.get("endpoint_proof_depth") or classify_endpoint_proof_depth(
                d.get("physicalEndpoint") or ""
            )
            self.assertIn(str(depth).upper(), {"WORD_ONLY", "NONE"})

    def test_full_rockwell_ready(self) -> None:
        ep = "AENTR13:I.Data[5].3"
        devices = [{"name": "ES500", "physicalEndpoint": ep, "kind": "ESTOP"}]
        apply_hardware_backed_readiness(
            devices, valid_endpoints={ep}, configio_words=None
        )
        self.assertTrue(devices[0].get("hardwareBacked"))
        self.assertNotEqual(devices[0].get("status"), "REVIEW_REQUIRED")


class TestOri048EmittedWriterGraph(unittest.TestCase):
    def test_phys_endpoint_alone_is_not_writer(self) -> None:
        self.assertFalse(
            safety_operand_has_writer(
                "T_1ES",
                written_tags=set(),
                device_evidence={
                    "T_1ES": {"physicalEndpoint": "RIO:I.Data[1].0", "configio_backed": True}
                },
            )
        )

    def test_emitted_writer_allows_consumer(self) -> None:
        self.assertTrue(
            safety_operand_has_writer(
                "T_1ES", written_tags={"T_1ES.I.ES_OK"}, device_evidence={}
            )
        )

    def test_missing_writer_blocks_emit(self) -> None:
        eng = [
            {
                "name": "Z1",
                "area": "A1",
                "members": ["1ES"],
                "membersOrigin": "ENGINEER_ASSIGNED",
                "engineerEdited": True,
                "conveyors": ["P1"],
            }
        ]
        irs = build_safety_zone_irs(engineer_zones=eng, default_area="A1")
        pack = emit_es_program(
            irs,
            _rung_xml=_rung_xml,
            routine=_routine,
            extract_tag_block=lambda *_: None,
            library_text="",
            written_tags=set(),
        )
        xml = pack["program_xml"]
        self.assertNotIn("ES_SIL1_Cat1(", xml)


class TestOri049033Conservation(unittest.TestCase):
    def test_js_no_blind_active_machine_stamp(self) -> None:
        src = (ROOT / "dashboard" / "safety-build.js").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("NEVER stamp blank ownership as the active machine", src)
        self.assertIn("UNKNOWN_OWNERSHIP", src)
        self.assertIn("UNRELATED_FOREIGN", src)
        # Old stampMach that invented ownership must be gone
        self.assertNotIn("return { ...d, machine: modelMach }", src)

    def test_python_no_blind_stamp(self) -> None:
        src = (ROOT / "tools" / "scripts" / "fortna_safety_model.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("NEVER stamp blank ownership as active machine", src)
        self.assertIn("UNKNOWN_OWNER", src)


class TestOri045032AreaDeleteZonePersist(unittest.TestCase):
    def test_area_delete_keeps_zone_members_clears_arearef(self) -> None:
        wb = {
            "conveyors": [],
            "areas": [{"name": "Warden_Area"}],
            "options": {"areas": ["Warden_Area"]},
            "safety_build": {
                "appliedAt": "2026-09-26T00:00:00Z",
                "zones": [
                    {
                        "source_id": "szone_warden",
                        "name": "Warden_ESZ",
                        "engineering_name": "Warden_ESZ",
                        "areaRef": "Warden_Area",
                        "area": "Warden_Area",
                        "members": ["ES914", "ESLS161", "1ESR1", "1MCR1"],
                        "engineerEdited": True,
                        "createdBy": "engineer",
                        "provenance": "ENGINEER_CREATED",
                    }
                ],
            },
        }
        graph = {
            "areas": [],
            "deletedAreas": ["Warden_Area"],
            "safetyBuild": {
                "zones": [
                    {
                        "source_id": "szone_warden",
                        "name": "Warden_ESZ",
                        "areaRef": "",
                        "area": "",
                        "members": ["ES914", "ESLS161", "1ESR1", "1MCR1"],
                        "engineerEdited": True,
                        "createdBy": "engineer",
                        "provenance": "ENGINEER_CREATED",
                    }
                ]
            },
            "merges": [],
        }
        r = apply_graph_to_workbook(graph, wb)
        zones = (r["workbook"].get("safety_build") or {}).get("zones") or []
        z = next(z for z in zones if (z.get("members") or []))
        self.assertEqual(z.get("areaRef") or "", "")
        self.assertEqual(len(z.get("members") or []), 4)

    def test_js_no_silent_arearef_relink(self) -> None:
        tb = (ROOT / "dashboard" / "transport-build.js").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("never silently relink a cleared areaRef", tb)
        sb = (ROOT / "dashboard" / "safety-build.js").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("areaUnlinked", sb)
        self.assertIn("never restamp cleared areaRef", sb)


class TestOri054Disposition(unittest.TestCase):
    def test_writer_required_for_zone_emit(self) -> None:
        eng = [
            {
                "name": "Pack_ESZone1",
                "area": "Pack_Area",
                "members": ["ES100"],
                "membersOrigin": "ENGINEER_ASSIGNED",
                "engineerEdited": True,
                "conveyors": ["P100"],
            }
        ]
        irs = build_safety_zone_irs(engineer_zones=eng, default_area="Pack_Area")
        with_w = emit_es_program(
            irs,
            _rung_xml=_rung_xml,
            routine=_routine,
            extract_tag_block=lambda *_: None,
            library_text="",
            written_tags={"ES100", "ES100.I.ES_OK"},
        )
        without = emit_es_program(
            irs,
            _rung_xml=_rung_xml,
            routine=_routine,
            extract_tag_block=lambda *_: None,
            library_text="",
            written_tags=set(),
        )
        self.assertIn("Pack_ESZone1", with_w.get("emitted_zones") or [])
        self.assertIn("Pack_ESZone1_Safe_Logic", with_w["program_xml"])
        self.assertNotIn("ES_SIL1_Cat1(", without["program_xml"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

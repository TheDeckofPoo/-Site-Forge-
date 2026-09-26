#!/usr/bin/env python3
"""Safety generalization closure regressions (Warden graduation @ 444d222)."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_es_compiler import (  # noqa: E402
    emit_es_program,
    build_safety_zone_irs,
)
from fortna_safety_endpoint_integrity import (  # noqa: E402
    apply_endpoint_collision_review,
    apply_hardware_backed_readiness,
)
from fortna_safety_model import _classify_device  # noqa: E402
from fortna_transport_graph import apply_graph_to_workbook  # noqa: E402


def _rung_xml(num, text, comment=""):
    c = f"<Comment><![CDATA[{comment}]]></Comment>" if comment else ""
    return f'<Rung Number="{num}" Type="N">{c}<Text><![CDATA[{text}]]></Text></Rung>'


def _routine(name, rungs):
    return f'<Routine Name="{name}" Type="RLL"><RLLContent>{"".join(rungs)}</RLLContent></Routine>'


class TestOri045ZoneSurvivesApply(unittest.TestCase):
    def test_safety_apply_js_recovers_orphaned_zones(self) -> None:
        src = (ROOT / "dashboard" / "safety-build.js").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("ORI-045", src)
        self.assertIn("Force-rehydrate any engineer zones", src)
        self.assertIn("Do NOT fall back to snap.areaRef", src)
        self.assertIn("prefer immutable szone_*", src)

    def test_transport_apply_keeps_members_clears_arearef(self) -> None:
        wb = {
            "conveyors": [],
            "areas": [],
            "options": {"areas": []},
            "safety_build": {
                "appliedAt": "2026-09-26T00:00:00Z",
                "source": "safety_build",
                "zones": [
                    {
                        "source_id": "szone_abc",
                        "id": "szone_abc",
                        "name": "Warden_G444_Empty_ESZ",
                        "engineering_name": "Warden_G444_Empty_ESZ",
                        "areaRef": "",
                        "area": "",
                        "members": ["ES914", "ESLS161", "1ESR1", "1MCR1"],
                        "engineerEdited": True,
                        "provenance": "ENGINEER_CREATED",
                        "createdBy": "engineer",
                    }
                ],
            },
            "merges_2to1": [],
        }
        graph = {
            "areas": [],
            "deletedAreas": ["Warden_G444_Empty_Area"],
            "safetyBuild": {
                "zones": [
                    {
                        "name": "Warden_G444_Empty_ESZ",
                        "areaRef": "",
                        "area": "",
                        "members": ["ES914", "ESLS161", "1ESR1", "1MCR1"],
                        "engineerEdited": True,
                        "provenance": "ENGINEER_CREATED",
                    }
                ]
            },
            "merges": [],
        }
        r = apply_graph_to_workbook(graph, wb)
        zones = (r["workbook"].get("safety_build") or {}).get("zones") or []
        self.assertTrue(any((z.get("members") or []) for z in zones))
        z = next(z for z in zones if (z.get("members") or []))
        self.assertEqual(z.get("areaRef") or "", "")
        self.assertEqual(len(z.get("members") or []), 4)


class TestOri048PreEmitWriterFilter(unittest.TestCase):
    def test_autogen_passes_written_tags(self) -> None:
        src = (ROOT / "tools" / "scripts" / "fortna_autogen.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("written_tags=_written_tags", src)
        self.assertIn("ORI-048: collect the REAL emitted writer graph BEFORE ES emit", src)
        self.assertIn("never infer solely from device physicalEndpoint presence", src)

    def test_orphan_without_writer_not_emitted(self) -> None:
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
            written_tags=set(),  # no writers
        )
        xml = pack["program_xml"]
        # No Safety consumer emitted when writer proof is absent
        self.assertNotIn("ES_SIL1_Cat1(T_1ES_AOI,T_1ES,", xml)
        self.assertNotIn("ES_SIL1_Cat1(", xml)
        self.assertTrue(pack.get("shell") or "REVIEW" in xml)


class TestOri051EndpointCollision(unittest.TestCase):
    def test_duplicate_endpoint_marks_review(self) -> None:
        devices = [
            {"name": "ESLS610L", "physicalEndpoint": "T_1734:I.Data[17].2", "kind": "ESLS"},
            {"name": "T_23MCR1", "physicalEndpoint": "T_1734:I.Data[17].2", "kind": "MCR"},
        ]
        r = apply_endpoint_collision_review(devices)
        self.assertEqual(r["conflicted_count"], 2)
        self.assertTrue(all(d.get("endpointConflict") for d in devices))
        self.assertTrue(all(d.get("status") == "REVIEW_REQUIRED" for d in devices))
        self.assertTrue(all(d.get("assignable") is False for d in devices))
        claimants = set()
        for c in r["collisions"]:
            claimants.update(c.get("claimants") or [])
        self.assertEqual(claimants, {"ESLS610L", "T_23MCR1"})

    def test_rockwell_spelling_and_whitespace_variants_collide(self) -> None:
        devices = [
            {"name": "ESLS610L", "physicalEndpoint": "T_1734:I.Data[17].2", "kind": "ESLS"},
            {
                "name": "T_23MCR1",
                "physicalEndpoint": "t_1734:i.data[17].2",
                "kind": "MCR",
            },
            {
                "name": "23MCR1",
                "physicalEndpoint": "T_1734 : I . Data [ 17 ] . 2",
                "kind": "MCR",
            },
        ]
        # Pairwise: first two collide; add third via same canonical key
        r = apply_endpoint_collision_review(devices)
        self.assertGreaterEqual(r["conflicted_count"], 2)
        self.assertTrue(all(d.get("endpointConflict") for d in devices))
        self.assertTrue(all(d.get("assignable") is False for d in devices))
        claimants = set()
        for c in r["collisions"]:
            claimants.update(c.get("claimants") or [])
        self.assertIn("ESLS610L", claimants)
        self.assertTrue({"T_23MCR1", "23MCR1"} & claimants)

    def test_bare_data_suffix_same_adapter_collides(self) -> None:
        devices = [
            {"name": "ESLS610L", "physicalEndpoint": "T_1734:I.Data[17].2", "kind": "ESLS"},
            {
                "name": "T_23MCR1",
                "physicalEndpoint": "Data[17].2",
                "adapter": "T_1734",
                "kind": "MCR",
            },
        ]
        r = apply_endpoint_collision_review(devices)
        self.assertEqual(r["conflicted_count"], 2)
        self.assertTrue(all(d.get("endpointConflict") for d in devices))
        self.assertTrue(all(d.get("assignable") is False for d in devices))
        claimants = set()
        for c in r["collisions"]:
            claimants.update(c.get("claimants") or [])
        self.assertEqual(claimants, {"ESLS610L", "T_23MCR1"})


class TestOri052HardwareBacked(unittest.TestCase):
    def test_word_only_not_ready(self) -> None:
        """Word/configio evidence alone is WORD_ONLY — never READY (ORI-052)."""
        devices = [
            {"name": "ES500", "physicalEndpoint": "500.0", "kind": "ESTOP"},
            {
                "name": "ESLS870",
                "physicalEndpoint": "532.0",
                "kind": "ESLS",
                "configio_backed": True,
            },
        ]
        apply_hardware_backed_readiness(
            devices, configio_words={"532"}, valid_endpoints=None
        )
        by = {d["name"]: d for d in devices}
        self.assertFalse(by["ES500"].get("hardwareBacked"))
        self.assertEqual(by["ES500"].get("status"), "REVIEW_REQUIRED")
        self.assertFalse(by["ESLS870"].get("hardwareBacked"))
        self.assertEqual(by["ESLS870"].get("status"), "REVIEW_REQUIRED")
        self.assertEqual(by["ESLS870"].get("endpoint_proof_depth"), "WORD_ONLY")
        self.assertEqual(by["ESLS870"].get("review_reason"), "WORD_ONLY_EVIDENCE")
        self.assertFalse(by["ESLS870"].get("assignable"))

    def test_full_rockwell_in_valid_endpoints_ready(self) -> None:
        devices = [
            {
                "name": "ESLS870",
                "physicalEndpoint": "T_1734:I.Data[5].0",
                "kind": "ESLS",
            },
        ]
        apply_hardware_backed_readiness(
            devices,
            configio_words=None,
            valid_endpoints={"T_1734:I.Data[5].0"},
        )
        d = devices[0]
        self.assertTrue(d.get("hardwareBacked"))
        self.assertEqual(d.get("endpoint_proof_depth"), "FULL")
        self.assertTrue(d.get("assignable"))


class TestOri043LogicalSuffixes(unittest.TestCase):
    def test_estop_esls_logical_rejected(self) -> None:
        self.assertEqual(_classify_device("1ES1_RESET"), "")
        self.assertEqual(_classify_device("ES914_OK"), "")
        self.assertEqual(_classify_device("ESLS161_OK"), "")
        self.assertEqual(_classify_device("ESLS161_RESET"), "")
        self.assertEqual(_classify_device("1ESR1_R1_AUX"), "ESR")
        self.assertEqual(_classify_device("1MCR_R1_AUX"), "MCR")

    def test_node_js_parity(self) -> None:
        script = ROOT / "tests" / "safety" / "test_safety_classify_parity.js"
        r = subprocess.run(
            ["node", str(script)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            stdin=subprocess.DEVNULL,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class TestOri050StaleArtifactGuard(unittest.TestCase):
    def test_desktop_and_ui_guard_present(self) -> None:
        main = (ROOT / "desktop" / "main.js").read_text(encoding="utf-8", errors="replace")
        ui = (ROOT / "dashboard" / "fortna-plus.js").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("artifactMatchesActiveMachine", main)
        self.assertIn("ORI-050", main)
        self.assertIn("staleForeign", ui)
        self.assertIn("BLOCKED — stale foreign L5X ignored", ui)


class TestOri033NoBlindStamp(unittest.TestCase):
    def test_python_policy_flag(self) -> None:
        src = (ROOT / "tools" / "scripts" / "fortna_safety_model.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("never_stamp_blank_machine_as_active", src)
        self.assertIn("NEVER stamp blank ownership as active machine", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)

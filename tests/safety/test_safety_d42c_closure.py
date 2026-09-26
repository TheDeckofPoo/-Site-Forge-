#!/usr/bin/env python3
"""ORI-044/045/046/047/048/049 + related closure regressions (Warden d42c)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_es_compiler import (  # noqa: E402
    build_safety_zone_irs,
    emit_es_program,
    filter_operands_without_writers,
    resolve_safety_feedback_operand,
    safety_operand_has_writer,
)
from fortna_safety_model import (  # noqa: E402
    _classify_device,
    _looks_like_unsupported_safety_name,
)
from fortna_transport_graph import apply_graph_to_workbook  # noqa: E402


def _rung_xml(num: int, text: str, comment: str = "") -> str:
    c = f"<Comment><![CDATA[{comment}]]></Comment>" if comment else ""
    return f'<Rung Number="{num}" Type="N">{c}<Text><![CDATA[{text}]]></Text></Rung>'


def _routine(name: str, rungs: list[str]) -> str:
    return f'<Routine Name="{name}" Type="RLL"><RLLContent>{"".join(rungs)}</RLLContent></Routine>'


class TestOri044AutogenHandoff(unittest.TestCase):
    def test_autogen_has_resolver_helper(self) -> None:
        src = (ROOT / "tools" / "scripts" / "fortna_autogen.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("_resolve_safety_devices_for_compiler", src)
        self.assertIn("ORI-044", src)
        self.assertIn("build_safety_model", src)

    def test_safety_apply_persists_safety_devices(self) -> None:
        src = (ROOT / "dashboard" / "safety-build.js").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("safetyDevices:", src)
        self.assertIn("devices_grouped:", src)


class TestOri046CanonicalMembership(unittest.TestCase):
    def test_js_keeps_canonical_mcr(self) -> None:
        src = (ROOT / "dashboard" / "safety-build.js").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("ORI-046", src)
        self.assertIn("Keep CANONICAL membership", src)
        # Old remap-to-AUX mutation must be gone
        self.assertNotIn("member = aux;", src)


class TestOri045AreaDeleteKeepsZone(unittest.TestCase):
    def test_js_clears_arearef_keeps_engineer_zone(self) -> None:
        src = (ROOT / "dashboard" / "safety-build.js").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("ORI-045", src)
        self.assertIn("NEVER destroy the Safety zone", src)

    def test_tombstone_override_on_recreate(self) -> None:
        src = (ROOT / "dashboard" / "transport-build.js").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("ORI-047", src)
        self.assertIn("overrides/removes obsolete Area tombstone", src)

    def test_apply_delete_keeps_zone_clears_ref(self) -> None:
        wb = {
            "conveyors": [],
            "areas": [
                {
                    "name": "Warden_D42_Empty_Area",
                    "provenance": "ENGINEER_CREATED",
                    "engineerCreated": True,
                }
            ],
            "options": {"areas": ["Warden_D42_Empty_Area"]},
            "safety_build": {
                "zones": [
                    {
                        "name": "Warden_D42_Empty_ESZ",
                        "areaRef": "Warden_D42_Empty_Area",
                        "area": "Warden_D42_Empty_Area",
                        "members": ["6ES1", "6ESR1"],
                        "engineerEdited": True,
                        "provenance": "ENGINEER_CREATED",
                    }
                ]
            },
            "merges_2to1": [],
        }
        graph = {
            "areas": [],
            "deletedAreas": ["Warden_D42_Empty_Area"],
            "safetyBuild": {
                "zones": [
                    {
                        "name": "Warden_D42_Empty_ESZ",
                        "areaRef": "",
                        "area": "",
                        "members": ["6ES1", "6ESR1"],
                        "engineerEdited": True,
                        "provenance": "ENGINEER_CREATED",
                    }
                ]
            },
            "merges": [],
        }
        result = apply_graph_to_workbook(graph, wb)
        names = {a["name"] for a in (result["workbook"].get("areas") or [])}
        self.assertNotIn("Warden_D42_Empty_Area", names)
        zones = (result["workbook"].get("safety_build") or {}).get("zones") or []
        z = next(x for x in zones if "Empty_ESZ" in str(x.get("name") or ""))
        self.assertEqual(z.get("areaRef") or "", "")
        self.assertEqual(sorted(z.get("members") or []), ["6ES1", "6ESR1"])


class TestOri043RealJsParity(unittest.TestCase):
    def test_node_runs_actual_js_classifier(self) -> None:
        script = ROOT / "tests" / "safety" / "test_safety_classify_parity.js"
        r = subprocess.run(
            ["node", str(script)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            stdin=subprocess.DEVNULL,
            shell=False,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PASS", r.stdout)

    def test_esr_r_suffix_not_estop(self) -> None:
        self.assertEqual(_classify_device("1ESR1_R1"), "ESR")
        self.assertEqual(_classify_device("6ESR_OK"), "")
        self.assertEqual(_classify_device("6ESR1_RESET"), "")


class TestOri048WriterConsumer(unittest.TestCase):
    def test_orphan_operand_review(self) -> None:
        fo = resolve_safety_feedback_operand("1ES", device_evidence={})
        self.assertEqual(fo.status, "RESOLVED")
        filtered = filter_operands_without_writers(
            [fo], written_tags=set(), device_evidence={}
        )
        self.assertEqual(filtered[0].status, "REVIEW_REQUIRED")
        self.assertEqual(filtered[0].reason, "safety_consumer_missing_writer")

    def test_writer_present_allows_operand(self) -> None:
        fo = resolve_safety_feedback_operand("1ES", device_evidence={})
        self.assertTrue(
            safety_operand_has_writer("T_1ES", written_tags={"T_1ES.I.ES_OK"})
        )
        filtered = filter_operands_without_writers(
            [fo], written_tags={"T_1ES.I.ES_OK"}, device_evidence={}
        )
        self.assertEqual(filtered[0].status, "RESOLVED")


class TestOri049UnsupportedConserved(unittest.TestCase):
    def test_escp2_is_unsupported_not_silent(self) -> None:
        self.assertEqual(_classify_device("ESCP2"), "")
        self.assertTrue(_looks_like_unsupported_safety_name("ESCP2"))
        self.assertTrue(_looks_like_unsupported_safety_name("MCRCP2"))
        self.assertTrue(_looks_like_unsupported_safety_name("MCRCP2AUX"))


class TestOri042TopbChainWithDevices(unittest.TestCase):
    def test_esr_resolves_when_devices_bridged(self) -> None:
        devs = [
            {
                "name": "6ESR1",
                "kind": "ESR",
                "machine": "TOPB-ET",
                "physicalEndpoint": "603.1",
                "signals": [
                    {
                        "name": "6ESR1_AUX",
                        "role": "AUX",
                        "physicalEndpoint": "603.1",
                    }
                ],
            }
        ]
        eng = [
            {
                "name": "Z1",
                "area": "A1",
                "members": ["6ESR1"],
                "membersOrigin": "ENGINEER_ASSIGNED",
                "engineerEdited": True,
                "conveyors": ["P1"],
            }
        ]
        irs = build_safety_zone_irs(
            engineer_zones=eng, safety_devices=devs, default_area="A1"
        )
        self.assertEqual(irs[0].members, ["T_6ESR1"])
        self.assertEqual(irs[0].emit_ready_operands(), ["T_6ESR1_AUX"])
        pack = emit_es_program(
            irs,
            _rung_xml=_rung_xml,
            routine=_routine,
            extract_tag_block=lambda *_: None,
            library_text="",
            written_tags={"T_6ESR1_AUX.I.ES_OK"},
        )
        xml = pack["program_xml"]
        self.assertIn("T_6ESR1_AUX", xml)
        self.assertNotIn("ES_SIL1_Cat1(T_6ESR1_AOI,T_6ESR1,", xml)


if __name__ == "__main__":
    unittest.main(verbosity=2)

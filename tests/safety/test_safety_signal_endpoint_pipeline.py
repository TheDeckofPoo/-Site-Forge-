#!/usr/bin/env python3
"""ORI-055/056/057/058/059 — Safety signal/endpoint pipeline behavioral tests.

Categories (do not merge):
  UNIT — pure helpers
  INTEGRATION — multi-module without full L5X
  E2E — build_l5x / real writer graph
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_es_compiler import (  # noqa: E402
    emit_es_program,
    build_safety_zone_irs,
    safety_operand_has_writer,
)
from fortna_safety_endpoint_integrity import (  # noqa: E402
    apply_endpoint_integrity_pipeline,
    apply_endpoint_collision_review,
    normalize_device_endpoints,
    resolve_safety_signal_roles,
    apply_direction_proof,
)
from fortna_safety_model import reconcile_safety_devices  # noqa: E402
from fortna_transport_graph import apply_graph_to_workbook  # noqa: E402


def _rung_xml(num, text, comment=""):
    return f'<Rung Number="{num}" Type="N"><Text><![CDATA[{text}]]></Text></Rung>'


def _routine(name, rungs):
    return f'<Routine Name="{name}" Type="RLL"><RLLContent>{"".join(rungs)}</RLLContent></Routine>'


# ---------------------------------------------------------------------------
# UNIT
# ---------------------------------------------------------------------------
class TestOri057NormalizeBeforeCollision(unittest.TestCase):
    """REAL failure form: word.bit vs Rockwell / bare I.Data — not two pre-normalized paths."""

    def test_ultapick_word_bit_vs_rockwell_path(self) -> None:
        devices = [
            {
                "name": "ESLS610L",
                "kind": "ESLS",
                "physicalEndpoint": "I.Data[17].2",
            },
            {
                "name": "T_23MCR1",
                "kind": "MCR",
                "physicalEndpoint": "2705.12",
            },
        ]
        word_map = {"2705.12": "T_1734:I.Data[17].2"}
        pipe = apply_endpoint_integrity_pipeline(
            devices,
            word_bit_to_endpoint=word_map,
            valid_endpoints={"T_1734:I.Data[17].2"},
            configio_words={"2705"},
        )
        self.assertGreaterEqual(int(pipe.get("conflicted_count") or 0), 2)
        self.assertTrue(all(d.get("endpointConflict") for d in devices))
        self.assertTrue(all(d.get("assignable") is False for d in devices))
        self.assertTrue(all(d.get("status") == "REVIEW_REQUIRED" for d in devices))
        claimants = {
            n
            for c in (pipe.get("collisions") or [])
            for n in (c.get("claimants") or [])
        }
        self.assertIn("ESLS610L", claimants)
        self.assertIn("T_23MCR1", claimants)

    def test_normalize_word_bit_alone(self) -> None:
        devices = [{"name": "A", "physicalEndpoint": "2705.12", "kind": "ESLS"}]
        normalize_device_endpoints(
            devices,
            {"2705.12": "T_1734:I.Data[17].2"},
            valid_endpoints={"T_1734:I.Data[17].2"},
        )
        self.assertEqual(
            devices[0]["physicalEndpoint"].upper(),
            "T_1734:I.DATA[17].2",
        )
        self.assertEqual(devices[0].get("endpoint_resolved_from"), "2705.12")


class TestOri056DirectionProof(unittest.TestCase):
    def test_estop_on_output_channel_not_ready(self) -> None:
        devices = [
            {
                "name": "1ES",
                "kind": "ESTOP",
                "physicalEndpoint": "AENTR1:O.Data[7].4",
            }
        ]
        resolve_safety_signal_roles(devices)
        apply_direction_proof(
            devices, valid_endpoints={"AENTR1:O.Data[7].4"}
        )
        self.assertEqual(devices[0].get("status"), "REVIEW_REQUIRED")
        self.assertFalse(devices[0].get("assignable"))
        self.assertIn("DIRECTION", str(devices[0].get("review_reason") or "").upper())


class TestOri055SignalRoles(unittest.TestCase):
    def test_mcr_prefers_aux_feedback_not_coil(self) -> None:
        devices = [
            {
                "name": "6MCR1",
                "kind": "MCR",
                "physicalEndpoint": "624.0",  # coil / command
                "signals": [
                    {
                        "name": "T_6MCR1_AUX",
                        "role": "AUX",
                        "physicalEndpoint": "RIO:I.Data[1].3",
                    },
                    {
                        "name": "6MCR1",
                        "role": "PRIMARY",
                        "physicalEndpoint": "624.0",
                    },
                ],
            }
        ]
        resolve_safety_signal_roles(devices)
        fb = devices[0].get("safetyFeedbackEndpoint") or ""
        self.assertIn("Data[1].3", fb.replace(" ", ""))
        self.assertNotEqual(fb, "624.0")


class TestOri058NoActiveMachineStamp(unittest.TestCase):
    def test_grouped_unknown_stays_unknown(self) -> None:
        signals = [
            {
                "name": "2ESR1",
                "kind": "ESR",
                "physicalEndpoint": "RIO:I.Data[0].1",
                # no machine field
            },
            {
                "name": "2ESR1_AUX",
                "kind": "ESR",
                "physicalEndpoint": "RIO:I.Data[0].1",
            },
        ]
        recon = reconcile_safety_devices(signals, machine="TFCP1")
        devices = recon.get("devices") or []
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].get("machine") or "", "")
        self.assertEqual(devices[0].get("inventory_scope"), "UNKNOWN_OWNERSHIP")
        self.assertEqual(devices[0].get("status"), "REVIEW_REQUIRED")
        self.assertFalse(devices[0].get("assignable"))


# ---------------------------------------------------------------------------
# INTEGRATION
# ---------------------------------------------------------------------------
class TestOri045TransportApplyPreservesEngineerZone(unittest.TestCase):
    def test_transport_apply_keeps_cleared_arearef_members(self) -> None:
        wb = {
            "conveyors": [],
            "areas": [],
            "options": {"areas": []},
            "safety_build": {
                "appliedAt": "2026-09-26T12:00:00Z",
                "zones": [
                    {
                        "source_id": "szone_orl",
                        "name": "Warden_ESZ",
                        "engineering_name": "Warden_ESZ",
                        "areaRef": "",
                        "area": "",
                        "areaUnlinked": True,
                        "members": ["ES914", "ESLS161", "1ESR1", "1MCR1"],
                        "engineerEdited": True,
                        "createdBy": "engineer",
                        "provenance": "ENGINEER_CREATED",
                    }
                ],
            },
        }
        # Transport Apply with hollow name-keyed zone (the real failure form)
        graph = {
            "areas": [],
            "deletedAreas": ["Warden_Area"],
            "safetyBuild": {
                "source": "transport_engineer",
                "zones": [
                    {
                        "name": "Warden_ESZ",
                        "areaRef": "",
                        "area": "",
                        "members": [],  # hollow transport seed
                    }
                ],
            },
            "merges": [],
        }
        r = apply_graph_to_workbook(graph, wb)
        zones = (r["workbook"].get("safety_build") or {}).get("zones") or []
        eng = [z for z in zones if (z.get("members") or [])]
        self.assertEqual(len(eng), 1, zones)
        self.assertEqual(len(eng[0].get("members") or []), 4)
        self.assertEqual(eng[0].get("areaRef") or "", "")
        # no duplicate by display name
        same = [
            z
            for z in zones
            if str(z.get("name") or "").upper() == "WARDEN_ESZ"
            or str(z.get("engineering_name") or "").upper() == "WARDEN_ESZ"
        ]
        self.assertEqual(len(same), 1)


class TestOri048PhysNotWriter(unittest.TestCase):
    def test_phys_endpoint_not_writer_without_iomap_row(self) -> None:
        self.assertFalse(
            safety_operand_has_writer(
                "T_1ES",
                written_tags=set(),
                device_evidence={
                    "T_1ES": {
                        "physicalEndpoint": "A:I.Data[1].0",
                        "configio_backed": True,
                    }
                },
            )
        )


# ---------------------------------------------------------------------------
# E2E (stronger ORI-054/059 — actual emit decision path)
# ---------------------------------------------------------------------------
class TestOri059E2EWriterGraph(unittest.TestCase):
    def test_emit_blocks_without_actual_writers(self) -> None:
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
            written_tags=set(),  # actual empty emission graph
        )
        self.assertNotIn("ES_SIL1_Cat1(", pack["program_xml"])

    def test_emit_allows_when_actual_writer_present(self) -> None:
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
        # Simulate actual IO_MAP resolved_rows writer set
        writers = {"T_1ES", "T_1ES.I.ES_OK"}
        pack = emit_es_program(
            irs,
            _rung_xml=_rung_xml,
            routine=_routine,
            extract_tag_block=lambda *_: None,
            library_text="",
            written_tags=writers,
        )
        self.assertIn("Z1", pack.get("emitted_zones") or [])
        self.assertIn("ES_SIL1_Cat1(", pack["program_xml"])


class TestOri050053Regression(unittest.TestCase):
    def test_exact_identity_still_present(self) -> None:
        main = (ROOT / "desktop" / "main.js").read_text(encoding="utf-8", errors="replace")
        fn = main.split("function artifactMatchesActiveMachine", 1)[1].split("\n  }", 1)[0]
        self.assertIn("got === want", fn)
        self.assertNotIn("includes(", fn)

    def test_review_not_discovery_incomplete(self) -> None:
        src = (ROOT / "tools" / "scripts" / "fortna_safety_model.py").read_text(
            encoding="utf-8", errors="replace"
        )
        block = src.split('"safety_evidence_complete"', 1)[1][:400]
        self.assertIn("evidence_union is not None", block)
        self.assertNotIn('review_required") or 0) == 0', block)


if __name__ == "__main__":
    unittest.main(verbosity=2)

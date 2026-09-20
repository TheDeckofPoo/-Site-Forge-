#!/usr/bin/env python3
"""AI I/O Resolver V1 — mocked unit tests (no API / no internet).

AI proposes. Site Forge validates. Deterministic path must work without AI.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from fortna_ai_io_resolver import (  # noqa: E402
    AI_IO_RESPONSE_SCHEMA,
    api_key_available,
    call_openai_resolver,
)
from fortna_ai_io_validate import validate_ai_response, validate_proposal  # noqa: E402
from fortna_ai_io_analyze import analyze  # noqa: E402


CLAIM_ID = "cl_test_pe600_j_001"


def _evidence() -> dict:
    return {
        "kind": "ai_io_evidence",
        "version": 1,
        "project": "ORINDYAC6",
        "machine": "ORINDYAC6",
        "run_dir": str(ROOT / "workspace" / "_virgin_orindy" / "RUN"),
        "eipcfg": {
            "adapters": [
                {
                    "rio_name": "T_1794_AENT_2",
                    "eipcfg_name": "T_1794_AENT_2",
                    "family": "1794_FLEX",
                    "modules": [
                        {
                            "slot": 1,
                            "catalog": "1794-IA16",
                            "type": "1794-IA16",
                            "input_bank": 28,
                            "direction": "I",
                            "data_index": 0,
                            "family": "1794_FLEX",
                        },
                        {
                            "slot": 2,
                            "catalog": "1794-IA16",
                            "type": "1794-IA16",
                            "input_bank": 29,
                            "direction": "I",
                            "data_index": 1,
                            "family": "1794_FLEX",
                        },
                    ],
                }
            ]
        },
        "configio": [
            {
                "row": 45,
                "Octal_Word": 611,
                "Bank": 29,
                "LoHi": "LO",
                "Desc": "AENT2 slot2",
                "Interface": "FLEX",
                "In_Out": "I",
            }
        ],
        "conveyor": [
            {
                "row": 123,
                "IO_Name": "PE600_J",
                "IO_Address_Word": "611",
                "IO_Address_Bit": "3",
                "Machine_Name": "ORINDYAC6",
                "Type": "PE",
                "description": "photoeye",
            }
        ],
        "raw_claims": [
            {
                "claim_id": CLAIM_ID,
                "source_table": "FORTNA/Conveyor.asc",
                "source_row": 123,
                "io_name": "PE600_J",
                "word": "611",
                "bit": "3",
                "machine": "ORINDYAC6",
                "device_type": "PE",
                "description": "photoeye",
            }
        ],
        "unresolved_points": [
            {
                "claim_id": CLAIM_ID,
                "claim_name": "PE600_J",
                "word": "611",
                "bit": "3",
                "disposition": "OWNER_CONFLICT",
            }
        ],
        "conflicts": {},
        "conservation_counts": {
            "raw_claims": 1,
            "deterministic_assigned": 0,
            "deterministic_unresolved": 0,
            "conflict_channels": 1,
        },
    }


def _valid_proposal(**overrides) -> dict:
    base = {
        "claim_id": CLAIM_ID,
        "logical_name": "PE600_J",
        "physical_endpoint": {
            "adapter": "T_1794_AENT_2",
            "family": "1794_FLEX",
            "slot": 2,
            "direction": "I",
            "data_index": 1,
            "bit": 3,
            "channel": "T_1794_AENT_2:I.Data[1].3",
        },
        "evidence": [
            {
                "source": "Conveyor.asc",
                "row": 123,
                "fact": "IO_Address_Word=611 IO_Address_Bit=3 PE600_J",
            },
            {
                "source": "Configio.asc",
                "row": 45,
                "fact": "Octal_Word=611 Bank=29 In_Out=I",
            },
        ],
        "proposal_status": "DERIVED",
        "ambiguity": [],
        "explanation": "Configio bank 29 maps word 611 to AENT_2 slot 2.",
    }
    base.update(overrides)
    return base


class TestApiKeyGate(unittest.TestCase):
    def test_no_api_key_reports_unavailable(self) -> None:
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            self.assertFalse(api_key_available())
            result = call_openai_resolver(_evidence())
            self.assertFalse(result["ok"])
            self.assertEqual(result["mode"], "unavailable")
            self.assertIn("OPENAI_API_KEY", result["error"])


class TestMockResolver(unittest.TestCase):
    def test_mock_response_path(self) -> None:
        payload = {
            "project": "ORINDYAC6",
            "machine": "ORINDYAC6",
            "claims": [_valid_proposal()],
            "unresolved": [],
            "warnings": [],
        }
        result = call_openai_resolver(_evidence(), mock_response=payload)
        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "mock")
        self.assertEqual(len(result["response"]["claims"]), 1)

    def test_schema_forbids_guessed(self) -> None:
        enum = AI_IO_RESPONSE_SCHEMA["properties"]["claims"]["items"]["properties"][
            "proposal_status"
        ]["enum"]
        self.assertNotIn("GUESSED", enum)
        self.assertEqual(
            set(enum), {"PROVEN", "DERIVED", "REVIEW_REQUIRED", "UNKNOWN"}
        )


class TestValidatorAcceptReject(unittest.TestCase):
    def setUp(self) -> None:
        self.evidence = _evidence()
        self.raw_by_id = {c["claim_id"]: c for c in self.evidence["raw_claims"]}
        self.run_dir = Path(self.evidence["run_dir"])

    def test_valid_proposal_accepted_as_derived(self) -> None:
        result = validate_proposal(
            _valid_proposal(),
            evidence=self.evidence,
            raw_by_id=self.raw_by_id,
            run_dir=self.run_dir,
        )
        self.assertTrue(result["accepted"], result)
        self.assertEqual(result["proposal_status"], "DERIVED")

    def test_invented_adapter_rejected(self) -> None:
        prop = _valid_proposal()
        prop["physical_endpoint"]["adapter"] = "T_FAKE_AENT_99"
        prop["physical_endpoint"]["channel"] = "T_FAKE_AENT_99:I.Data[1].3"
        result = validate_proposal(
            prop, evidence=self.evidence, raw_by_id=self.raw_by_id, run_dir=self.run_dir
        )
        self.assertFalse(result["accepted"])
        self.assertTrue(any("invented adapter" in r.lower() for r in result["reasons"]))

    def test_invented_source_row_rejected(self) -> None:
        prop = _valid_proposal()
        prop["evidence"] = [
            {"source": "Conveyor.asc", "row": 99999, "fact": "IO_Address_Word=611 PE600_J"},
            {"source": "Configio.asc", "row": 45, "fact": "Octal_Word=611 Bank=29"},
        ]
        result = validate_proposal(
            prop, evidence=self.evidence, raw_by_id=self.raw_by_id, run_dir=self.run_dir
        )
        self.assertFalse(result["accepted"])
        self.assertTrue(any("source row" in r.lower() for r in result["reasons"]))

    def test_foreign_machine_claim_rejected(self) -> None:
        prop = _valid_proposal()
        # Inject foreign machine on raw ledger entry
        foreign = dict(self.evidence)
        foreign["raw_claims"] = [
            {**self.evidence["raw_claims"][0], "machine": "MSCATL_CP3"}
        ]
        raw_by = {c["claim_id"]: c for c in foreign["raw_claims"]}
        result = validate_proposal(
            prop, evidence=foreign, raw_by_id=raw_by, run_dir=self.run_dir
        )
        self.assertFalse(result["accepted"])
        self.assertTrue(any("foreign-machine" in r.lower() for r in result["reasons"]))

    def test_bad_bit_channel_rejected(self) -> None:
        prop = _valid_proposal()
        prop["physical_endpoint"]["bit"] = 99
        prop["physical_endpoint"]["channel"] = "T_1794_AENT_2:I.Data[1].99"
        result = validate_proposal(
            prop, evidence=self.evidence, raw_by_id=self.raw_by_id, run_dir=self.run_dir
        )
        self.assertFalse(result["accepted"])
        self.assertTrue(
            any("capacity" in r.lower() or "bad" in r.lower() for r in result["reasons"])
        )

    def test_unknown_claim_id_rejected(self) -> None:
        prop = _valid_proposal(claim_id="cl_does_not_exist")
        result = validate_proposal(
            prop, evidence=self.evidence, raw_by_id=self.raw_by_id, run_dir=self.run_dir
        )
        self.assertFalse(result["accepted"])
        self.assertIn("raw ledger", " ".join(result["reasons"]).lower())

    def test_guessed_status_rejected(self) -> None:
        prop = _valid_proposal(proposal_status="GUESSED")
        result = validate_proposal(
            prop, evidence=self.evidence, raw_by_id=self.raw_by_id, run_dir=self.run_dir
        )
        self.assertFalse(result["accepted"])

    def test_incomplete_evidence_becomes_review(self) -> None:
        prop = _valid_proposal()
        # Only one valid cite → REVIEW_REQUIRED (not DERIVED)
        prop["evidence"] = [
            {
                "source": "Conveyor.asc",
                "row": 123,
                "fact": "IO_Address_Word=611 IO_Address_Bit=3 PE600_J",
            }
        ]
        result = validate_proposal(
            prop, evidence=self.evidence, raw_by_id=self.raw_by_id, run_dir=self.run_dir
        )
        self.assertFalse(result["accepted"])
        self.assertEqual(result["proposal_status"], "REVIEW_REQUIRED")

    def test_conservation_lost_claims_zero(self) -> None:
        payload = {
            "project": "ORINDYAC6",
            "machine": "ORINDYAC6",
            "claims": [_valid_proposal()],
            "unresolved": [],
            "warnings": [],
        }
        validated = validate_ai_response(payload, self.evidence, run_dir=self.run_dir)
        self.assertEqual(validated["lost_claims"], 0)
        self.assertEqual(validated["raw_claims"], 1)
        self.assertEqual(validated["ai_validator_accepted"], 1)

    def test_malformed_ai_response_safe_failure(self) -> None:
        validated = validate_ai_response(
            {"claims": ["not-a-dict", 42]},
            self.evidence,
            run_dir=self.run_dir,
        )
        self.assertTrue(validated["ok"])
        self.assertEqual(validated["ai_validator_accepted"], 0)
        self.assertGreaterEqual(validated["ai_validator_rejected"], 2)
        self.assertEqual(validated["lost_claims"], 0)


class TestAnalyzeOffline(unittest.TestCase):
    """API unavailable / mock path must not break deterministic analyze."""

    def test_api_unavailable_still_ok(self) -> None:
        orindy = ROOT / "workspace" / "_virgin_orindy" / "RUN"
        if not (orindy / "project.cfg").is_file():
            self.skipTest("ORINDYAC6 virgin RUN missing")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            with tempfile.TemporaryDirectory() as td:
                # Redirect evidence_out_dir via project name that lands under exports —
                # analyze writes to exports/ai-io; just assert it returns ok.
                result = analyze(orindy, "ORINDYAC6", project="TEST_AI_IO_OFFLINE")
        self.assertTrue(result["ok"])
        self.assertFalse(result["ai_ok"])
        self.assertIn("OPENAI_API_KEY", result.get("ai_error") or "")
        self.assertEqual(result["summary"]["lost"], 0)
        self.assertEqual(result["summary"]["conservation"], "PASS")

    def test_mock_analyze_accepts_valid(self) -> None:
        orindy = ROOT / "workspace" / "_virgin_orindy" / "RUN"
        if not (orindy / "project.cfg").is_file():
            self.skipTest("ORINDYAC6 virgin RUN missing")
        # Build mock from real evidence claim if present, else synthetic
        from fortna_ai_io_evidence import build_evidence_bundle

        ev = build_evidence_bundle(orindy, "ORINDYAC6", project="TEST_AI_IO_MOCK")
        raw = ev.get("raw_claims") or []
        if not raw:
            self.skipTest("no raw claims on ORINDYAC6")
        # Pick a claim that has matching adapter evidence if possible
        claim = raw[0]
        mock_payload = {
            "project": "TEST_AI_IO_MOCK",
            "machine": "ORINDYAC6",
            "claims": [
                {
                    "claim_id": claim["claim_id"],
                    "logical_name": claim["io_name"],
                    "physical_endpoint": {
                        "adapter": "INVENTED_ADAPTER",
                        "family": "1794_FLEX",
                        "slot": 1,
                        "direction": "I",
                        "data_index": 0,
                        "bit": int(claim["bit"]) if str(claim["bit"]).isdigit() else 0,
                        "channel": "INVENTED_ADAPTER:I.Data[0].0",
                    },
                    "evidence": [
                        {
                            "source": "Conveyor.asc",
                            "row": claim["source_row"],
                            "fact": f"IO_Name={claim['io_name']} IO_Address_Word={claim['word']}",
                        }
                    ],
                    "proposal_status": "DERIVED",
                    "ambiguity": [],
                    "explanation": "should be rejected — invented adapter",
                }
            ],
            "unresolved": [],
            "warnings": [],
        }
        result = analyze(
            orindy,
            "ORINDYAC6",
            project="TEST_AI_IO_MOCK",
            mock_response=mock_payload,
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["ai_ok"])
        # Invented adapter must not become DERIVED
        self.assertEqual(result["summary"]["ai_validated_derived"], 0)
        self.assertEqual(result["summary"]["lost"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""P0: Deterministic LOCAL+endpoint must not depend on AI availability."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_run_io_source_ledger import (  # noqa: E402
    STATUS_ENGINEER_REQUIRED,
    STATUS_MAPPED_PENDING_EMIT,
    STATUS_REVIEW,
    build_canonical_device_ledger,
)
from fortna_io_prebuild_escalation import (  # noqa: E402
    _validate_ownership_proposal,
    run_prebuild_io_escalation,
)

SHIP = ROOT / "workspace" / "_reno_peek" / "20260813-1132-MSCRENO-MSCRENOSHIP-RUN" / "RUN"


class TestDeterministicIoNoAi(unittest.TestCase):
    def test_mapped_pending_emit_constant(self) -> None:
        self.assertEqual(STATUS_MAPPED_PENDING_EMIT, "MAPPED_PENDING_EMIT")

    def test_ai_review_confidence_never_becomes_mapped(self) -> None:
        device = {
            "canonical_name": "ESLS1",
            "ownership": "LOCAL",
            "endpoint": "AENTR_1:I.Data[2].7",
            "physical_endpoint": "AENTR_1:I.Data[2].7",
            "word": "1101",
        }
        proposal = {
            "classification": "LOCAL",
            "confidence": "REVIEW_REQUIRED",
            "owner_controller": "MSCRENOSHIP",
            "reason": "AI soft claim",
        }
        val = _validate_ownership_proposal(
            proposal,
            device=device,
            machine="MSCRENOSHIP",
            active_words={"1101"},
        )
        self.assertTrue(val.get("ok"))
        self.assertEqual(val.get("final_status"), STATUS_ENGINEER_REQUIRED)
        self.assertTrue(val.get("engineer_required"))

    def test_ai_absent_keeps_deterministic_endpoint(self) -> None:
        canonical = {
            "devices": [
                {
                    "canonical_name": "ESLS1",
                    "device_type": "ESLS",
                    "ownership": "LOCAL",
                    "endpoint": "AENTR_1:I.Data[2].7",
                    "physical_endpoint": "AENTR_1:I.Data[2].7",
                    "deterministic_code": "ENDPOINT_ON_ACTIVE_CONTROLLER",
                    "final_status": STATUS_REVIEW,
                    "critical": True,
                    "word": "1101",
                    "bit": "7",
                }
            ],
            "active_configio_words": ["1101"],
        }
        # Health-down → AI unavailable short-circuit must retain deterministic proof.
        out = run_prebuild_io_escalation(
            canonical,
            machine="MSCRENOSHIP",
            health={
                "ai_api": {"available": False},
                "relay": {"available": False},
            },
            skip_noncritical=False,
        )
        devices = (out.get("devices") if isinstance(out, dict) else None) or canonical["devices"]
        by = {d["canonical_name"]: d for d in devices}
        d = by["ESLS1"]
        self.assertEqual(
            d.get("final_status"),
            STATUS_MAPPED_PENDING_EMIT,
            d,
        )
        self.assertNotEqual(d.get("final_status"), STATUS_ENGINEER_REQUIRED)


@unittest.skipUnless((SHIP / "project.cfg").is_file(), "MSCRENOSHIP RUN missing")
class TestShipEslsDeterministicNoAi(unittest.TestCase):
    def test_local_esls_are_mapped_pending_emit(self) -> None:
        from fortna_run_io_source_ledger import build_run_io_source_ledger

        led = build_run_io_source_ledger(SHIP, "MSCRENOSHIP")
        canon = build_canonical_device_ledger(
            led,
            machine="MSCRENOSHIP",
            run_dir=SHIP,
            physical_io_map_csv=None,
            apply_engineer_confirmations=False,
        )
        by = {d["canonical_name"].upper(): d for d in canon["devices"]}
        local_esls = [
            d
            for name, d in by.items()
            if name.startswith("ESLS")
            and d.get("ownership") == "LOCAL"
            and d.get("deterministic_code") == "ENDPOINT_ON_ACTIVE_CONTROLLER"
        ]
        self.assertTrue(local_esls, "expected at least one LOCAL proven ESLS")
        for d in local_esls:
            self.assertEqual(
                d.get("final_status"),
                STATUS_MAPPED_PENDING_EMIT,
                d,
            )
            self.assertTrue(d.get("assignable"), d)


if __name__ == "__main__":
    unittest.main(verbosity=2)

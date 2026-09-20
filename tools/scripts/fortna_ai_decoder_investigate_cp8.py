#!/usr/bin/env python3
"""One-shot CP8_ALPHA_DIALECT_REMAINING_R1 Decoder Investigator session.

Uses corrected neutral blind packet + ORNCCP4 RUN evidence.
Budget $0.50 / synthesis $0.40. No production rule promotion.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_ai_decoder_investigate import run_investigation  # noqa: E402

RUN = REPO / "exports/learning/_extract/ab56d6beb1b1ca87/RUN"
PACKET = (
    REPO
    / "exports/learning/investigations/CP8_ALPHA_DIALECT/blind_packet.json"
)
OUT = REPO / "exports/learning/investigations/CP8_ALPHA_DIALECT/R1"


def main() -> int:
    if not (RUN / "project.cfg").is_file():
        raise SystemExit(f"ORNCCP4 RUN missing: {RUN}")
    blind = json.loads(PACKET.read_text(encoding="utf-8"))
    # Ensure investigation metadata
    blind["investigation_id"] = "CP8_ALPHA_DIALECT_REMAINING_R1"
    blind["site_summary"] = {
        "machine": "ORNCCP4",
        "project": "OReillyGreensboro",
        "form": "PANEL_CATALOG_NUMERIC_ALPHA",
        "note": "High halves for IA16/IB16 have physical claims without direct EIPModules bank match; OA8I High halves have zero claims.",
    }
    blind["output_contract"] = {
        "type": "DecoderRuleCandidate",
        "status": ["CANDIDATE", "REVIEW_REQUIRED", "INSUFFICIENT_EVIDENCE"],
        "forbidden": ["physical_endpoint", "ai_derived", "READY", "Autogen", "PLC"],
    }
    result = run_investigation(
        run_dir=RUN,
        blind_packet=blind,
        out_dir=OUT,
        machine="ORNCCP4",
        project="OReillyGreensboro",
        investigation_id="CP8_ALPHA_DIALECT_REMAINING_R1",
    )
    summary = result.get("summary") or result
    (OUT / "session_return.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, default=str)[:5000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

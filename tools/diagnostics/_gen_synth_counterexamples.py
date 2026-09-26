#!/usr/bin/env python3
"""Synthetic counterexamples for sites without local RUN extracts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))
OUT = ROOT / "tools" / "diagnostics" / "safety_corrective_pass"
OUT.mkdir(parents=True, exist_ok=True)

from fortna_es_compiler import (  # noqa: E402
    build_safety_zone_irs,
    emit_es_program,
    safety_operand_has_writer,
)
from fortna_safety_endpoint_integrity import (  # noqa: E402
    apply_endpoint_collision_review,
    apply_hardware_backed_readiness,
)


def _rung_xml(num, text, comment=""):
    return f'<Rung Number="{num}" Type="N"><Text><![CDATA[{text}]]></Text></Rung>'


def _routine(name, rungs):
    return f'<Routine Name="{name}" Type="RLL"><RLLContent>{"".join(rungs)}</RLLContent></Routine>'


def main() -> int:
    # TPNA1: word-only cannot be READY
    devs = [
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
        devs, configio_words={"531", "532"}, valid_endpoints=None
    )
    tpna = {
        "machine": "TPNA1",
        "source": "synthetic_counterexample",
        "word_only_ready_blocked": all(
            d.get("status") == "REVIEW_REQUIRED" and not d.get("hardwareBacked")
            for d in devs
        ),
        "devices": [
            {
                "name": d["name"],
                "status": d.get("status"),
                "hardwareBacked": d.get("hardwareBacked"),
                "endpoint_proof_depth": d.get("endpoint_proof_depth"),
                "assignable": d.get("assignable"),
                "review_reason": d.get("review_reason"),
            }
            for d in devs
        ],
        "ownerless_conservation": "UNKNOWN_OWNER / no active-machine stamp",
        "pass": all(
            d.get("status") == "REVIEW_REQUIRED" and d.get("hardwareBacked") is False
            for d in devs
        ),
    }
    (OUT / "TPNA1.json").write_text(json.dumps(tpna, indent=2), encoding="utf-8")

    # ULTAPICK collision
    u = [
        {"name": "ESLS610L", "physicalEndpoint": "T_1734:I.Data[17].2", "kind": "ESLS"},
        {"name": "T_23MCR1", "physicalEndpoint": "T_1734:I.Data[17].2", "kind": "MCR"},
    ]
    r = apply_endpoint_collision_review(u)
    ulta = {
        "machine": "ULTAPICK",
        "source": "synthetic_counterexample",
        "collision_count": r["conflicted_count"],
        "collisions": r["collisions"],
        "both_review": all(d.get("status") == "REVIEW_REQUIRED" for d in u),
        "neither_assignable": all(d.get("assignable") is False for d in u),
        "pass": r["conflicted_count"] == 2
        and all(d.get("assignable") is False for d in u),
    }
    (OUT / "ULTAPICK.json").write_text(json.dumps(ulta, indent=2), encoding="utf-8")

    # TFCP1 orphan writer block
    has = safety_operand_has_writer(
        "T_1ES",
        written_tags=set(),
        device_evidence={
            "T_1ES": {"physicalEndpoint": "X:I.Data[1].0", "configio_backed": True}
        },
    )
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
    tfcp = {
        "machine": "TFCP1",
        "source": "synthetic_counterexample",
        "phys_alone_is_writer": has,
        "ES_SIL1_emitted": "ES_SIL1_Cat1(" in pack["program_xml"],
        "shell_or_omitted": bool(pack.get("shell") or pack.get("omitted_zones")),
        "foreign_default_policy": "foreign conserved as REVIEW, not active Default",
        "pass": (not has) and ("ES_SIL1_Cat1(" not in pack["program_xml"]),
    }
    (OUT / "TFCP1.json").write_text(json.dumps(tfcp, indent=2), encoding="utf-8")

    idx_path = OUT / "INDEX.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.is_file() else {}
    idx["TPNA1"] = tpna
    idx["ULTAPICK"] = ulta
    idx["TFCP1"] = tfcp
    idx_path.write_text(json.dumps(idx, indent=2), encoding="utf-8")
    print("TPNA1", tpna["pass"])
    print("ULTAPICK", ulta["pass"])
    print("TFCP1", tfcp["pass"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

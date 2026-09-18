#!/usr/bin/env python3
"""CP4 StartStopZones adapter — configuration islands via RUN ASC (not CP3-only).

Does not invent PLC emits. Does not modify Transportation/Mtrchain.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fortna_control_model import decode_startstop_zones
from fortna_semantics.common import AdapterResult, AdapterStatus


def run_startstop_adapter(
    *,
    run_dir: Path | str | None = None,
    machine: str | None = None,
    cp3: dict[str, Any] | None = None,
) -> AdapterResult:
    if not run_dir or not machine:
        return AdapterResult(
            adapter="StartStop",
            status=AdapterStatus.REVIEW.value,
            objects=[],
            facts=[],
            diagnostics=[{"kind": "MISSING_RUN_OR_MACHINE"}],
            counts={"zones": 0},
            proofs={},
            notes=["StartStop adapter requires run_dir + machine (ASC decode)."],
        )
    model = decode_startstop_zones(Path(run_dir), machine)
    # Optional: count CP3 identities targeting StartStopZones if provided
    cp3_ids = 0
    if cp3:
        by_tgt = cp3.get("byTargetIdentity") or {}
        cp3_ids = sum(1 for k in by_tgt if str(k).startswith("StartStopZones::"))
    status = AdapterStatus.PASS.value if model["zone_count"] else AdapterStatus.REVIEW.value
    return AdapterResult(
        adapter="StartStop",
        status=status,
        objects=model["zones"],
        facts=[],
        diagnostics=[],
        counts={"zones": model["zone_count"], "cp3StartStopIdentities": cp3_ids},
        proofs={"zoneNamesSample": [z["name"] for z in model["zones"][:10]]},
        notes=[
            "Decoded from StartStopZones.asc via merge_table_rows precedence",
            "Jamzones.StartStopZone → these names (belongs_to_startstop_zone)",
        ],
    )

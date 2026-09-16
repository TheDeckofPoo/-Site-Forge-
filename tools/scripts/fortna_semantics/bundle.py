#!/usr/bin/env python3
"""CP4 thin aggregator — no subsystem interpretation logic."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fortna_semantics.evidence import load_or_build_cp3_index, write_json
from fortna_semantics.io import run_io_adapter
from fortna_semantics.jam import run_jam_adapter
from fortna_semantics.merge import run_merge_adapter
from fortna_semantics.mtrchain import run_mtrchain_adapter
from fortna_semantics.safety import run_safety_adapter
from fortna_semantics.transportation import run_transportation_adapter


def run_cp4_bundle(
    *,
    site: str,
    graph_path: Path | None = None,
    run_dir: Path | None = None,
    ac_name: str | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    cp3 = load_or_build_cp3_index(
        graph_path=graph_path,
        run_dir=run_dir,
        ac_name=ac_name,
    )

    # Independent adapters — Merge may consume public Mtrchain result only
    transportation = run_transportation_adapter(cp3)
    mtrchain = run_mtrchain_adapter(cp3)
    merge = run_merge_adapter(cp3, mtrchain_public=mtrchain.to_dict())
    jam = run_jam_adapter(cp3)
    safety = run_safety_adapter(cp3)
    io = run_io_adapter(cp3)

    adapters = {
        "Transportation": transportation.to_dict(),
        "Mtrchain": mtrchain.to_dict(),
        "Merge": merge.to_dict(),
        "Jam": jam.to_dict(),
        "Safety": safety.to_dict(),
        "IO": io.to_dict(),
    }

    # Bundle status: FAIL if any FAIL; else REVIEW if any REVIEW; else PASS
    statuses = [a["status"] for a in adapters.values()]
    if "FAIL" in statuses:
        bundle_status = "FAIL"
    elif "REVIEW" in statuses:
        bundle_status = "REVIEW"
    else:
        bundle_status = "PASS"

    bundle = {
        "kind": "Cp4SemanticBundle",
        "version": 1,
        "site": site,
        "acName": cp3.get("acName"),
        "status": bundle_status,
        "adapters": {k: {"status": v["status"], "counts": v["counts"]} for k, v in adapters.items()},
        "adapterResults": adapters,
        "notes": [
            "Thin aggregator only — interpretation lives in isolated adapters.",
            "A REVIEW/FAIL adapter does not rewrite other adapters' results.",
        ],
    }

    if out_dir:
        out_dir = Path(out_dir)
        write_json(out_dir / f"cp4-transportation-{site}.json", adapters["Transportation"])
        write_json(out_dir / f"cp4-mtrchain-{site}.json", adapters["Mtrchain"])
        write_json(out_dir / f"cp4-merge-{site}.json", adapters["Merge"])
        write_json(out_dir / f"cp4-jam-{site}.json", adapters["Jam"])
        write_json(out_dir / f"cp4-safety-evidence-{site}.json", adapters["Safety"])
        write_json(out_dir / f"cp4-io-evidence-{site}.json", adapters["IO"])
        write_json(out_dir / f"cp4-semantic-bundle-{site}.json", bundle)

    return bundle

#!/usr/bin/env python3
"""CP5A Transportation mapper — CP4 Transport/Mtrchain → Site Forge transport graph.

Anti-corruption boundary: UI consumes Site Forge graph shape only.
Does not invent physical geometry/adjacency.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_run_physical_layout import build_transport_graph  # noqa: E402


def _classify_identity(ident: str) -> str:
    """Presentation hint only — NOT a physical-type claim."""
    u = (ident or "").strip().upper()
    if re.match(r"^P\d", u):
        return "conveyor_candidate"
    if re.match(r"^(M|VFD)\d", u):
        return "motor_candidate"
    if "PE" in u or u.startswith("EZ"):
        return "photoeye_candidate"
    if u.startswith("LATCH") or "LATCH" in u:
        return "latch_candidate"
    return "other_object"


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def map_cp4_to_transport_graph(
    *,
    run_dir: Path,
    machine: str,
    decoder_dir: Path,
    connect_threshold: float | None = None,
) -> dict[str, Any]:
    """Build transport graph from existing physical layout + CP4 annotations."""
    decoder_dir = Path(decoder_dir)
    summary = _load_json(decoder_dir / "cp5a-decoder-summary.json") or {}
    transport = _load_json(decoder_dir / "cp4-transportation-active.json") or summary.get(
        "transportation"
    ) or {}
    mtrchain = _load_json(decoder_dir / "cp4-mtrchain-active.json") or summary.get("mtrchain") or {}
    # Bundle may hold adapterResults
    bundle = _load_json(decoder_dir / "cp4-semantic-bundle.json") or {}
    if not transport:
        transport = (bundle.get("adapterResults") or {}).get("Transportation") or {}
    if not mtrchain:
        mtrchain = (bundle.get("adapterResults") or {}).get("Mtrchain") or {}

    # 1) Physical layout where RUN geometry exists (unchanged engine)
    ct = connect_threshold if connect_threshold is not None else "HIGH_CONFIDENCE"
    graph = build_transport_graph(Path(run_dir), machine or "", connect_threshold=str(ct))

    if not isinstance(graph, dict) or not isinstance(graph.get("areas"), list):
        return {
            "ok": False,
            "layer": "CP5",
            "error": "CP5 TRANSPORTATION MAPPING ERROR: physical layout produced no graph",
        }

    # Index placed tags
    placed: dict[str, dict[str, Any]] = {}
    for area in graph.get("areas") or []:
        for n in area.get("nodes") or []:
            tag = str(n.get("conveyorTag") or n.get("label") or "").strip()
            if tag:
                placed[tag.upper()] = n

    # Mtrchain index by identity
    mtr_by_id = {
        str(o.get("identity") or "").upper(): o for o in (mtrchain.get("objects") or [])
    }

    # Annotate placed nodes with decoder provenance
    annotated = 0
    for tag_u, n in placed.items():
        n.setdefault("decoder", {})
        n["decoder"]["geometryStatus"] = (
            "PROVEN" if n.get("physical") and n.get("sourceX") is not None else "UNKNOWN"
        )
        n["decoder"]["foundInCp4"] = False
        n["decoder"]["objectClassHint"] = _classify_identity(tag_u)
        # Attach mtrchain if this tag is a motor identity
        if tag_u in mtr_by_id:
            entry = mtr_by_id[tag_u]
            n["decoder"]["mtrchain"] = {
                "identity": entry.get("identity"),
                "motorNdx": entry.get("motorNdx"),
                "chained": entry.get("chained"),
                "motorAux": entry.get("motorAux"),
                "enabled": entry.get("enabled"),
                "goUntil": entry.get("goUntil"),
                "meaning": "Fortna startup/control + display relationship — not physical topology",
            }
            annotated += 1

    # CP4 conveyor-family objects
    cp4_objects = transport.get("objects") or []
    catalog = []
    unplaced_conveyor_candidates = []
    for obj in cp4_objects:
        ident = str(obj.get("identity") or "").strip()
        if not ident:
            continue
        cls = _classify_identity(ident)
        row = {
            "identity": ident,
            "classHint": cls,
            "foundStatus": "FOUND",
            "geometryStatus": "UNKNOWN",
            "activeStatus": "UNKNOWN",
            "includedStatus": "UNKNOWN",
            "inboundReferenceCount": obj.get("inboundReferenceCount") or 0,
            "inboundFromMenus": obj.get("inboundFromMenus") or {},
            "placed": ident.upper() in placed,
            "notes": obj.get("notes") or [],
        }
        if ident.upper() in placed:
            row["geometryStatus"] = placed[ident.upper()].get("decoder", {}).get(
                "geometryStatus", "PROVEN"
            )
            placed[ident.upper()]["decoder"]["foundInCp4"] = True
            placed[ident.upper()]["decoder"]["inboundReferenceCount"] = row[
                "inboundReferenceCount"
            ]
        catalog.append(row)
        if cls == "conveyor_candidate" and ident.upper() not in placed:
            unplaced_conveyor_candidates.append(ident)

    # Proofs from CP4
    proofs = {
        "transportation": transport.get("proofs") or {},
        "mtrchain": mtrchain.get("proofs") or {},
    }

    metrics = dict(graph.get("metrics") or {})
    metrics["cp5a"] = {
        "decoderOk": bool(summary.get("ok", True) if summary else True),
        "cp4TransportStatus": transport.get("status"),
        "cp4MtrchainStatus": mtrchain.get("status"),
        "cp4ConveyorFamilyObjects": len(cp4_objects),
        "cp4MtrchainEntries": len(mtrchain.get("objects") or []),
        "placedNodes": len(placed),
        "annotatedWithMtrchain": annotated,
        "unplacedConveyorCandidates": len(unplaced_conveyor_candidates),
        "catalogObjects": len(catalog),
        "geometryPolicy": "RUN physical layout only — no adjacency invented from Mtrchain/numbering",
    }

    graph["metrics"] = metrics
    graph["cp5a"] = {
        "version": 1,
        "source": "cp4_transportation_mtrchain",
        "catalog": catalog,
        "unplacedConveyorCandidates": unplaced_conveyor_candidates,
        "proofs": proofs,
        "decoderSummaryPath": str(decoder_dir / "cp5a-decoder-summary.json"),
    }
    # Ensure UI can surface unplaced tags via inventory merge
    graph["decoderInventoryTags"] = {
        "conveyorCandidates": sorted(
            {c["identity"] for c in catalog if c["classHint"] == "conveyor_candidate"}
        ),
        "motorCandidates": sorted(
            {c["identity"] for c in catalog if c["classHint"] == "motor_candidate"}
        ),
        "photoeyeCandidates": sorted(
            {c["identity"] for c in catalog if c["classHint"] == "photoeye_candidate"}
        ),
        "unplacedConveyorCandidates": sorted(unplaced_conveyor_candidates),
    }
    graph["ok"] = True
    return graph


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CP5A Transportation mapper")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--machine", default="")
    ap.add_argument("--decoder-dir", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--stdout-graph", action="store_true")
    args = ap.parse_args(argv)
    graph = map_cp4_to_transport_graph(
        run_dir=Path(args.run_dir),
        machine=args.machine,
        decoder_dir=Path(args.decoder_dir),
    )
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(
            json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    if args.stdout_graph:
        print(json.dumps(graph, ensure_ascii=False))
    elif not args.out:
        print(json.dumps({"ok": graph.get("ok"), "metrics": graph.get("metrics")}, indent=2))
    return 0 if graph.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

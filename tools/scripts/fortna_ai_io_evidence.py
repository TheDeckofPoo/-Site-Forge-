#!/usr/bin/env python3
"""Build a LOCAL current-machine I/O evidence bundle for the AI resolver sidecar.

Never includes finished/reference L5X.
Applies Fortna shadow semantics: Table.asc.<MACHINE> else Table.asc.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_asc import read_asc  # noqa: E402
from fortna_hardware_io_model import build_hardware_io_model  # noqa: E402
from fortna_io_claim_ledger import (  # noqa: E402
    _MACHINE_WILDCARD,
    _current_machine_row,
    _is_spare_token,
    build_claim_ledger,
    rack_conservation_invariant,
)
from fortna_physical_word_resolver import (  # noqa: E402
    PhysicalWordResolver,
    _find_eipcfg,
    _find_eipmodules,
    _load_configio_rows,
    _load_eipmodules_rows,
    build_physical_word_map,
    parse_eipcfg,
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_claim_id(
    *,
    machine: str,
    source_table: str,
    source_row: int,
    io_name: str,
    word: str,
    bit: str,
) -> str:
    raw = "|".join(
        [
            (machine or "").strip().upper(),
            source_table,
            str(source_row),
            (io_name or "").strip().upper(),
            str(word).strip(),
            str(bit).strip(),
        ]
    )
    return "cl_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def build_raw_claims(run_dir: Path, machine: str) -> list[dict[str, Any]]:
    """Preserve every current-machine named I/O claim with a stable claim_id."""
    conv = run_dir / "FORTNA" / "Conveyor.asc"
    if not conv.is_file():
        return []
    _, rows = read_asc(conv)
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        if not _current_machine_row(row, machine):
            continue
        name = str(row.get("IO_Name") or "").strip()
        if not name or _is_spare_token(name):
            continue
        typ = str(row.get("Type") or "").strip().upper()
        if typ == "SPARE":
            continue
        word = str(row.get("IO_Address_Word") or "").strip()
        bit = str(row.get("IO_Address_Bit") or "").strip()
        if not word or not bit:
            continue
        desc = str(
            row.get("General_Description")
            or row.get("Device_Description")
            or ""
        ).strip()
        claim_id = _stable_claim_id(
            machine=machine,
            source_table="FORTNA/Conveyor.asc",
            source_row=i,
            io_name=name,
            word=word,
            bit=bit,
        )
        out.append(
            {
                "claim_id": claim_id,
                "source_table": "FORTNA/Conveyor.asc",
                "source_row": i,
                "io_name": name,
                "word": word,
                "bit": bit,
                "machine": str(row.get("Machine_Name") or "").strip() or machine,
                "device_type": typ,
                "description": desc[:200],
            }
        )
    return out


def _safe_adapters(topo: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for ad in topo.get("adapters") or []:
        mods = []
        for m in ad.get("modules") or []:
            mods.append(
                {
                    "slot": m.get("slot"),
                    "catalog": m.get("type") or m.get("catalog"),
                    "name": m.get("name"),
                    "connection": m.get("connection"),
                    "input_bank": m.get("input_bank"),
                    "output_bank": m.get("output_bank"),
                    "data_index": m.get("data_index"),
                    "direction": m.get("direction"),
                    "family": m.get("family"),
                }
            )
        out.append(
            {
                "rio_name": ad.get("rio_name"),
                "eipcfg_name": ad.get("eipcfg_name") or ad.get("name"),
                "panel": ad.get("panel"),
                "targetip": ad.get("targetip") or ad.get("ip"),
                "node": ad.get("node"),
                "family": ad.get("family"),
                "input_address": ad.get("input_address"),
                "output_address": ad.get("output_address"),
                "modules": mods,
            }
        )
    return out


def build_evidence_bundle(
    run_dir: Path | str,
    machine: str,
    *,
    project: str = "",
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    machine = (machine or "").strip()
    topo = parse_eipcfg(run_dir, machine)
    configio = _load_configio_rows(run_dir, machine)
    eipmodules = _load_eipmodules_rows(run_dir, machine)
    pm = build_physical_word_map(run_dir, machine)
    model = build_hardware_io_model(run_dir, machine)
    ledger = build_claim_ledger(run_dir, machine)
    inv = rack_conservation_invariant(ledger)
    raw_claims = build_raw_claims(run_dir, machine)

    # Compact conveyor rows for AI context (current-machine only)
    conv_path = run_dir / "FORTNA" / "Conveyor.asc"
    conveyor_rows: list[dict[str, Any]] = []
    if conv_path.is_file():
        _, rows = read_asc(conv_path)
        for i, row in enumerate(rows):
            if not _current_machine_row(row, machine):
                continue
            name = str(row.get("IO_Name") or "").strip()
            if not name:
                continue
            conveyor_rows.append(
                {
                    "row": i,
                    "IO_Name": name,
                    "IO_Address_Word": str(row.get("IO_Address_Word") or "").strip(),
                    "IO_Address_Bit": str(row.get("IO_Address_Bit") or "").strip(),
                    "Machine_Name": str(row.get("Machine_Name") or "").strip(),
                    "Type": str(row.get("Type") or "").strip(),
                    "description": str(
                        row.get("General_Description")
                        or row.get("Device_Description")
                        or ""
                    ).strip()[:160],
                }
            )

    configio_out = []
    for r in configio:
        configio_out.append(
            {
                "row": r.get("row"),
                "Octal_Word": r.get("octal_word"),
                "Bank": r.get("bank"),
                "LoHi": r.get("lohi"),
                "Desc": r.get("desc"),
                "Interface": r.get("interface"),
                "In_Out": r.get("in_out"),
                "catalog_bank_parsed": r.get("catalog_bank_parsed"),
            }
        )

    eipmod_out = []
    for r in eipmodules[:500]:
        eipmod_out.append(
            {
                k: r.get(k)
                for k in (
                    "name",
                    "slot",
                    "type",
                    "catalog",
                    "input_bank",
                    "output_bank",
                    "adapter",
                    "rio_name",
                )
                if r.get(k) is not None
            }
        )

    # Deterministic unresolved / conflicts for AI focus
    unresolved = []
    for c in ledger.get("claims") or []:
        disp = c.get("disposition")
        if disp in ("physical_resolution_failure", "UNRESOLVED_OWNER", "OWNER_CONFLICT"):
            unresolved.append(
                {
                    "claim_name": c.get("name"),
                    "word": c.get("fortna_word"),
                    "bit": c.get("fortna_bit"),
                    "disposition": disp,
                    "physical_address": c.get("physical_address"),
                    "evidence": c.get("evidence"),
                }
            )

    # Attach claim_id onto unresolved by matching raw ledger
    by_key = {
        (c["io_name"].upper(), str(c["word"]), str(c["bit"])): c["claim_id"]
        for c in raw_claims
    }
    for u in unresolved:
        u["claim_id"] = by_key.get(
            (str(u.get("claim_name") or "").upper(), str(u.get("word")), str(u.get("bit")))
        )

    conflicts = model.get("owner_claim_conflicts") or {}

    site = project or ""
    if not site:
        # Derive from archive stem / path heuristics without inventing
        meta_path = run_dir.parent / "active-meta.json"
        if not meta_path.is_file():
            meta_path = REPO_ROOT / "workspace" / "active-meta.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            site = str(meta.get("archive_stem") or meta.get("export_name") or "")
        except Exception:
            site = machine

    return {
        "kind": "ai_io_evidence",
        "version": 1,
        "generated_at": _ts(),
        "project": site,
        "machine": machine,
        "run_dir": str(run_dir.resolve()),
        "shadow_semantics": "Table.asc.<MACHINE> if present else Table.asc",
        "eipcfg": {
            "path": str(_find_eipcfg(run_dir, machine) or ""),
            "adapters": _safe_adapters(topo),
        },
        "configio": configio_out,
        "conveyor": conveyor_rows,
        "eipmodules": {
            "path": str(_find_eipmodules(run_dir, machine) or ""),
            "rows": eipmod_out,
        },
        "deterministic_resolver": {
            "word_count": (pm.get("stats") or {}).get("word_count"),
            "unresolved_count": (pm.get("stats") or {}).get("unresolved_count"),
            "owner_states": (model.get("stats") or {}).get("owner_states") or {},
            "unresolved_words": list(pm.get("unresolved") or [])[:80],
        },
        "raw_claims": raw_claims,
        "unresolved_points": unresolved,
        "conflicts": conflicts,
        "conservation": inv,
        "conservation_counts": {
            "raw_claims": len(raw_claims),
            "deterministic_assigned": int(
                ((model.get("stats") or {}).get("owner_states") or {}).get("ASSIGNED") or 0
            ),
            "deterministic_unresolved": int(
                ((model.get("stats") or {}).get("owner_states") or {}).get("UNRESOLVED_OWNER") or 0
            ),
            "conflict_channels": len(conflicts),
            "ledger_phys_failures": int(inv.get("physical_resolution_failures") or 0),
        },
        "notes": [
            "Never includes finished/reference L5X.",
            "AI may only propose; Site Forge validates before DERIVED.",
        ],
    }


def evidence_out_dir(project: str, machine: str) -> Path:
    safe_p = re.sub(r"[^\w.\-]+", "_", (project or "project").strip())[:80] or "project"
    safe_m = re.sub(r"[^\w.\-]+", "_", (machine or "machine").strip())[:40] or "machine"
    return REPO_ROOT / "exports" / "ai-io" / f"{safe_p}_{safe_m}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build AI I/O evidence bundle")
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--machine", required=True)
    ap.add_argument("--project", default="")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    bundle = build_evidence_bundle(args.run_dir, args.machine, project=args.project)
    out = args.out
    if out is None:
        out = evidence_out_dir(bundle.get("project") or "", args.machine) / "evidence.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    # Also persist raw claims ledger next to evidence
    raw_path = out.parent / "raw_claims.json"
    raw_path.write_text(
        json.dumps(
            {
                "kind": "ai_io_raw_claims",
                "machine": args.machine,
                "count": len(bundle.get("raw_claims") or []),
                "claims": bundle.get("raw_claims") or [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(out),
                "raw_claims": len(bundle.get("raw_claims") or []),
                "unresolved_points": len(bundle.get("unresolved_points") or []),
                "conservation_ok": (bundle.get("conservation") or {}).get("ok"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

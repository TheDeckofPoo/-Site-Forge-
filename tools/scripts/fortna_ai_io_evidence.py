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
from fortna_ai_io_validate import (  # noqa: E402
    compute_claim_conservation,
    derive_evidence_status,
    enrich_conservation_with_readiness,
    needs_resolution_count,
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


def resolve_conveyor_asc(run_dir: Path, machine: str) -> Path | None:
    """Native Fortna shadow: Conveyor.asc.<MACHINE> if present else Conveyor.asc."""
    fortna = Path(run_dir) / "FORTNA"
    machine = (machine or "").strip()
    if machine:
        overlay = fortna / f"Conveyor.asc.{machine}"
        if overlay.is_file() and overlay.stat().st_size > 0:
            return overlay
    generic = fortna / "Conveyor.asc"
    if generic.is_file() and generic.stat().st_size > 0:
        return generic
    return None


def _parse_word(word: str) -> int | None:
    try:
        return int(float(str(word).strip()))
    except (TypeError, ValueError):
        return None


def _bit_parseable(bit: str) -> bool:
    """Accept decimal 0-15 or octal-ish 0-7/10-17 Conveyor bit encodings."""
    s = str(bit or "").strip()
    if not s:
        return False
    try:
        v = int(float(s))
    except (TypeError, ValueError):
        return False
    # Decimal channel or octal-ish nibble encodings used in Fortna tables
    return 0 <= v <= 17


def _configio_word_set(run_dir: Path, machine: str) -> set[int]:
    """Active Configio octal words for the current machine (physical I/O evidence)."""
    out: set[int] = set()
    for r in _load_configio_rows(run_dir, machine):
        try:
            out.add(int(r.get("octal_word")))
        except (TypeError, ValueError):
            continue
    return out


def _classify_claim_row(
    *,
    word: str,
    bit: str,
    configio_words: set[int],
) -> tuple[str, str]:
    """Return (class, reason). physical = Configio-backed word + parseable bit."""
    w = _parse_word(word)
    if w is None:
        return "nonphysical", "word_not_numeric"
    if not _bit_parseable(bit):
        return "nonphysical", "bit_not_parseable"
    # Virtual / catalog / foreign words (e.g. 6000, 5777) are not Configio-backed
    if not configio_words:
        return "nonphysical", "no_active_configio_words"
    if w not in configio_words:
        return "nonphysical", "word_not_in_active_configio"
    return "physical", "configio_word_present"


def build_raw_claims(
    run_dir: Path,
    machine: str,
    *,
    include_nonphysical: bool = False,
) -> list[dict[str, Any]]:
    """Physical I/O claim ledger for the current controller.

    Counts only current-machine named Conveyor claims whose word exists in
    active Configio (EIP-backed physical I/O). Virtual / special / catalog
    addresses (e.g. 6000) are excluded from the physical ledger.

    Set include_nonphysical=True only when the caller wants both classes;
    default returns physical claims only (AI raw ledger contract).
    """
    classified = classify_conveyor_claims(run_dir, machine)
    if include_nonphysical:
        return classified["physical"] + classified["nonphysical"]
    return classified["physical"]


def classify_conveyor_claims(run_dir: Path, machine: str) -> dict[str, Any]:
    """Split Conveyor named rows into physical vs nonphysical claim lists."""
    run_dir = Path(run_dir)
    machine = (machine or "").strip()
    conv = resolve_conveyor_asc(run_dir, machine)
    empty = {
        "conveyor_path": str(conv) if conv else "",
        "shadow": bool(conv and conv.name.endswith(f".{machine}")) if machine else False,
        "physical": [],
        "nonphysical": [],
        "configio_words": [],
    }
    if not conv:
        return empty

    configio_words = _configio_word_set(run_dir, machine)
    _, rows = read_asc(conv)
    # Prefer a stable relative source label
    try:
        source_table = str(conv.relative_to(run_dir)).replace("\\", "/")
    except ValueError:
        source_table = f"FORTNA/{conv.name}"

    physical: list[dict[str, Any]] = []
    nonphysical: list[dict[str, Any]] = []
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
            source_table=source_table,
            source_row=i,
            io_name=name,
            word=word,
            bit=bit,
        )
        klass, reason = _classify_claim_row(
            word=word, bit=bit, configio_words=configio_words
        )
        rec = {
            "claim_id": claim_id,
            "source_table": source_table,
            "source_row": i,
            "io_name": name,
            "word": word,
            "bit": bit,
            "machine": str(row.get("Machine_Name") or "").strip() or machine,
            "device_type": typ,
            "description": desc[:200],
            "claim_class": klass,
            "class_reason": reason,
        }
        if klass == "physical":
            physical.append(rec)
        else:
            nonphysical.append(rec)

    return {
        "conveyor_path": str(conv),
        "shadow": bool(machine and conv.name.endswith(f".{machine}")),
        "physical": physical,
        "nonphysical": nonphysical,
        "configio_words": sorted(configio_words),
    }


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
    classified = classify_conveyor_claims(run_dir, machine)
    raw_claims = classified["physical"]
    nonphysical_claims = classified["nonphysical"]

    # Deterministic dispositions for PHYSICAL claims only (match by name/word/bit)
    physical_words = {
        w
        for c in raw_claims
        if (w := _parse_word(str(c.get("word")))) is not None
    }
    ledger = build_claim_ledger(run_dir, machine, words=physical_words or None)
    inv = rack_conservation_invariant(ledger)

    # Index ledger dispositions onto physical claim_ids
    ledger_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for c in ledger.get("claims") or []:
        key = (
            str(c.get("name") or "").upper(),
            str(c.get("fortna_word") or "").strip(),
            str(c.get("fortna_bit") or "").strip(),
        )
        ledger_by_key[key] = c
    for rc in raw_claims:
        key = (
            str(rc.get("io_name") or "").upper(),
            str(rc.get("word") or "").strip(),
            str(rc.get("bit") or "").strip(),
        )
        traced = ledger_by_key.get(key)
        if traced:
            rc["deterministic_disposition"] = traced.get("disposition")
            rc["physical_address"] = traced.get("physical_address")
        else:
            rc["deterministic_disposition"] = "physical_resolution_failure"
            rc["physical_address"] = None
        # Diagnostic only — does not change disposition/outcome
        try:
            from fortna_bit_address import parse_fortna_bit_address
            from fortna_hardware_family import channel_capacity_for_catalog

            ba = parse_fortna_bit_address(
                rc.get("bit"),
                source_table=str(rc.get("source_table") or ""),
                source_row=rc.get("source_row"),
            )
            rc["fortna_bit_address"] = ba.to_dict()
            # Only when the word's resolved module is actually 4-channel
            wrec = (pm.get("words") or {}).get(str(rc.get("word"))) or {}
            cat = str(wrec.get("type") or wrec.get("catalog") or "")
            cap = channel_capacity_for_catalog(cat) if cat else 0
            if (
                rc.get("deterministic_disposition") == "physical_resolution_failure"
                and ba.half == "Low"
                and ba.module_bit is not None
                and cap == 4
                and ba.module_bit >= cap
            ):
                rc["resolution_diagnostic"] = "low_half_bit_exceeds_module_capacity"
        except Exception:
            pass

    # Compact conveyor rows for AI context — physical claims + surrounding evidence
    conveyor_rows: list[dict[str, Any]] = []
    for c in raw_claims:
        conveyor_rows.append(
            {
                "row": c.get("source_row"),
                "IO_Name": c.get("io_name"),
                "IO_Address_Word": c.get("word"),
                "IO_Address_Bit": c.get("bit"),
                "Machine_Name": c.get("machine"),
                "Type": c.get("device_type"),
                "description": c.get("description"),
                "claim_id": c.get("claim_id"),
                "claim_class": "physical",
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

    # Deterministic unresolved / conflicts for AI focus — physical claims only
    unresolved = []
    terminal_ok = {
        "ASSIGNED",
        "UNRESOLVED_OWNER",
        "OWNER_CONFLICT",
        "physical_resolution_failure",
    }
    disp_counts: dict[str, int] = {k: 0 for k in terminal_ok}
    for rc in raw_claims:
        disp = str(rc.get("deterministic_disposition") or "").strip()
        if disp == "UNRESOLVED":
            disp = "UNRESOLVED_OWNER"
        if disp not in terminal_ok:
            disp = "physical_resolution_failure"
        rc["deterministic_disposition"] = disp
        disp_counts[disp] += 1
        if disp in ("physical_resolution_failure", "UNRESOLVED_OWNER", "OWNER_CONFLICT"):
            unresolved.append(
                {
                    "claim_id": rc.get("claim_id"),
                    "claim_name": rc.get("io_name"),
                    "word": rc.get("word"),
                    "bit": rc.get("bit"),
                    "disposition": disp,
                    "physical_address": rc.get("physical_address"),
                }
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

    cons = enrich_conservation_with_readiness(
        compute_claim_conservation(
            {"raw_claims": raw_claims, "machine": machine, "project": site}
        ),
        configio_words=len(classified.get("configio_words") or []),
        nonphysical_excluded=len(nonphysical_claims),
    )
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
        "conveyor_path": classified.get("conveyor_path"),
        "conveyor_shadow": classified.get("shadow"),
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
        "nonphysical_claims_count": len(nonphysical_claims),
        "nonphysical_claims_sample": nonphysical_claims[:20],
        "unresolved_points": unresolved,
        "conflicts": conflicts,
        "ledger_invariant_physical_words": inv,
        "conservation": {
            "ok": cons["ok"],
            "status": cons["conservation"],
            "raw_physical_claims": cons["raw_physical_claims"],
            "accounted_claims": cons["accounted_claims"],
            "lost_claims": cons["lost_claims"],
            "duplicate_accounting": cons["duplicate_accounting"],
            "needs_resolution": cons["needs_resolution"],
            "counts": cons["counts"],
            "equation": cons["equation"],
        },
        "conservation_counts": {
            "raw_physical_claims": len(raw_claims),
            "raw_claims": len(raw_claims),
            "deterministic_assigned": disp_counts["ASSIGNED"],
            "deterministic_unresolved": disp_counts["UNRESOLVED_OWNER"],
            "deterministic_conflicts": disp_counts["OWNER_CONFLICT"],
            "physical_resolution_failures": disp_counts["physical_resolution_failure"],
            "needs_resolution": cons["needs_resolution"],
            "conflict_channels": len(conflicts),
            "nonphysical_excluded": len(nonphysical_claims),
            "configio_words": len(classified.get("configio_words") or []),
        },
        "evidence_status": cons["evidence_status"],
        "needs_resolution": cons["needs_resolution"],
        "notes": [
            "Never includes finished/reference L5X.",
            "raw_claims are PHYSICAL only (Configio-backed word + parseable bit).",
            "Virtual/special addresses (e.g. 6000) live in nonphysical_claims_sample.",
            "AI may only propose; Site Forge validates before DERIVED.",
            "conservation PASS ≠ I/O solved; see evidence_status.",
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
    cons = bundle.get("conservation") if isinstance(bundle.get("conservation"), dict) else {}
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(out),
                "raw_physical_claims": len(bundle.get("raw_claims") or []),
                "raw_claims": len(bundle.get("raw_claims") or []),
                "needs_resolution": bundle.get("needs_resolution"),
                "unresolved_points": len(bundle.get("unresolved_points") or []),
                "conservation_ok": cons.get("ok"),
                "conservation_status": cons.get("status"),
                "lost_claims": cons.get("lost_claims"),
                "duplicate_accounting": cons.get("duplicate_accounting"),
                "evidence_status": bundle.get("evidence_status"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

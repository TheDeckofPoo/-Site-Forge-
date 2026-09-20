#!/usr/bin/env python3
"""I/O claim conservation ledger — raw RUN named claims must never silently vanish.

Instrument:
  raw claim → resolver hit → physical address → HardwareIOModel owner_state → GUI state

Conservation (per rack or site):
  raw_named_claims
    = assigned
    + unresolved          (UNRESOLVED_OWNER / OWNER_CONFLICT)
    + physical_resolution_failures
    + (explicit spare with positive evidence only)

A named current-machine RUN claim may become:
  ASSIGNED | UNRESOLVED_OWNER | OWNER_CONFLICT | physical_resolution_failure

It must NEVER become UNUSED_MAPPED | PROVEN_SPARE | UNKNOWN without explicit evidence.

Does NOT read finished L5X. Does NOT special-case site names.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_asc import read_asc  # noqa: E402
from fortna_hardware_io_model import (  # noqa: E402
    OWNER_ASSIGNED,
    OWNER_ENGINEER_SPARE,
    OWNER_PROVEN_SPARE,
    OWNER_UNKNOWN,
    OWNER_UNRESOLVED,
    OWNER_UNUSED_MAPPED,
    build_hardware_io_model,
)
from fortna_physical_word_resolver import PhysicalWordResolver  # noqa: E402

FORBIDDEN_FOR_NAMED = frozenset(
    {OWNER_UNUSED_MAPPED, OWNER_PROVEN_SPARE, OWNER_UNKNOWN}
)
ALLOWED_FOR_NAMED = frozenset(
    {OWNER_ASSIGNED, OWNER_UNRESOLVED, "OWNER_CONFLICT", "physical_resolution_failure"}
)

_MACHINE_WILDCARD = frozenset(
    {"", "N/A", "NA", "NONE", "INVALID", "ALL", "0", "NULL"}
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_spare_token(name: str) -> bool:
    u = (name or "").strip().upper()
    return u in {"", "SPARE", "INVALID", "N/A", "NONE", "NULL", "—", "-", "(SPARE)"}


def _current_machine_row(row: dict[str, Any], machine: str) -> bool:
    rm = str(row.get("Machine_Name") or "").strip().upper()
    if not rm or rm in _MACHINE_WILDCARD:
        return True
    return rm == (machine or "").strip().upper()


def iter_raw_named_claims(
    run_dir: Path | str,
    machine: str,
    *,
    words: set[int] | None = None,
) -> list[dict[str, Any]]:
    """Enumerate named current-machine Conveyor.asc claims (conservation ledger birth)."""
    run_dir = Path(run_dir)
    conv = run_dir / "FORTNA" / "Conveyor.asc"
    if not conv.is_file():
        return []
    _, rows = read_asc(conv)
    out: list[dict[str, Any]] = []
    for row in rows:
        if not _current_machine_row(row, machine):
            continue
        name = str(row.get("IO_Name") or "").strip()
        if not name or _is_spare_token(name):
            continue
        typ = str(row.get("Type") or "").strip().upper()
        if typ == "SPARE":
            continue
        word_s = str(row.get("IO_Address_Word") or "").strip()
        bit_s = str(row.get("IO_Address_Bit") or "").strip()
        if not word_s or not bit_s:
            continue
        try:
            word_i = int(float(word_s))
        except (TypeError, ValueError):
            continue
        if words is not None and word_i not in words:
            continue
        out.append(
            {
                "name": name,
                "fortna_word": word_s,
                "fortna_bit": bit_s,
                "word": word_i,
                "type": typ,
                "machine_name": str(row.get("Machine_Name") or "").strip(),
                "source_table": "FORTNA/Conveyor.asc",
            }
        )
    return out


def _index_channels(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_addr: dict[str, dict[str, Any]] = {}
    for ad in model.get("adapters") or []:
        for mod in ad.get("modules") or []:
            for ch in mod.get("channels") or []:
                addr = (ch.get("physical_address") or "").strip()
                if addr:
                    by_addr[addr] = {
                        **ch,
                        "adapter_rio": ad.get("rio_name") or ad.get("eipcfg_name"),
                        "module_slot": mod.get("slot"),
                        "module_type": mod.get("type") or mod.get("catalog"),
                    }
    return by_addr


def trace_claim(
    claim: dict[str, Any],
    *,
    resolver: PhysicalWordResolver,
    channels_by_addr: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Instrument one claim through the pipeline."""
    name = claim["name"]
    word = claim["fortna_word"]
    bit = claim["fortna_bit"]
    row: dict[str, Any] = {
        **claim,
        "resolver_hit": False,
        "physical_address": None,
        "owner_state": None,
        "engineering_owner": None,
        "disposition": None,
        "gui_state": None,
        "forbidden": False,
        "evidence": None,
    }
    hit = resolver.resolve(word, bit)
    if not hit or not (hit.get("channel") or "").strip():
        row["disposition"] = "physical_resolution_failure"
        row["evidence"] = "resolver returned no channel"
        return row
    addr = str(hit.get("channel") or "").strip()
    row["resolver_hit"] = True
    row["physical_address"] = addr
    row["module_type"] = hit.get("type")
    row["rio_name"] = hit.get("rio_name")
    ch = channels_by_addr.get(addr)
    if not ch:
        row["disposition"] = "physical_resolution_failure"
        row["evidence"] = "resolved channel not present on HardwareIOModel modules"
        return row
    st = str(ch.get("owner_state") or OWNER_UNKNOWN)
    eng = str(ch.get("engineering_owner") or "").strip()
    row["owner_state"] = st
    row["engineering_owner"] = eng or None
    row["gui_state"] = st
    row["rejection_reason"] = ch.get("rejection_reason")
    # Conflict: channel has UNRESOLVED with OWNER_CONFLICT source
    src = str(ch.get("owner_source") or "").upper()
    if st == OWNER_UNRESOLVED and "CONFLICT" in src:
        row["disposition"] = "OWNER_CONFLICT"
    elif st == OWNER_ASSIGNED and eng == name:
        row["disposition"] = OWNER_ASSIGNED
    elif st == OWNER_ASSIGNED and eng and eng != name:
        # Another owner won the channel — still a named-claim disposition via conflict math
        row["disposition"] = "OWNER_CONFLICT"
        row["evidence"] = f"channel assigned to other owner {eng}"
    elif st == OWNER_UNRESOLVED:
        row["disposition"] = OWNER_UNRESOLVED
    elif st in FORBIDDEN_FOR_NAMED:
        row["disposition"] = st
        row["forbidden"] = True
        row["evidence"] = (
            f"named RUN claim became {st} without allowed disposition"
        )
    else:
        row["disposition"] = st
        if st not in ALLOWED_FOR_NAMED:
            row["forbidden"] = True
            row["evidence"] = f"unexpected disposition {st}"
    return row


def build_claim_ledger(
    run_dir: Path | str,
    machine: str,
    *,
    words: set[int] | None = None,
    rack_label: str = "",
) -> dict[str, Any]:
    """Build full claim ledger + conservation check."""
    run_dir = Path(run_dir)
    raw = iter_raw_named_claims(run_dir, machine, words=words)
    resolver = PhysicalWordResolver(run_dir, machine)
    model = build_hardware_io_model(run_dir, machine)
    channels = _index_channels(model)

    traced = [trace_claim(c, resolver=resolver, channels_by_addr=channels) for c in raw]
    counts = Counter(t.get("disposition") or "UNKNOWN" for t in traced)
    assigned = int(counts.get(OWNER_ASSIGNED) or 0)
    unresolved = int(counts.get(OWNER_UNRESOLVED) or 0)
    conflicts = int(counts.get("OWNER_CONFLICT") or 0)
    phys_fail = int(counts.get("physical_resolution_failure") or 0)
    forbidden = [t for t in traced if t.get("forbidden")]
    accounted = assigned + unresolved + conflicts + phys_fail
    raw_n = len(raw)
    conservation_ok = accounted == raw_n and not forbidden

    by_word: dict[str, int] = defaultdict(int)
    for t in traced:
        by_word[str(t.get("word"))] += 1

    return {
        "kind": "io_claim_ledger",
        "version": 1,
        "generated_at": _ts(),
        "machine": machine,
        "run_dir": str(run_dir),
        "rack_label": rack_label or "",
        "words": sorted(words) if words else None,
        "raw_named_claims": raw_n,
        "disposition_counts": dict(counts),
        "assigned": assigned,
        "unresolved": unresolved,
        "conflicts": conflicts,
        "physical_resolution_failures": phys_fail,
        "accounted": accounted,
        "conservation_ok": conservation_ok,
        "conservation_equation": (
            "raw_named_claims = assigned + unresolved + conflicts + physical_resolution_failures"
        ),
        "forbidden_named_dispositions": len(forbidden),
        "forbidden_samples": forbidden[:20],
        "claims_by_word": dict(sorted(by_word.items(), key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 0)),
        "model_owner_states": (model.get("stats") or {}).get("owner_states") or {},
        "claims": traced,
        "ok": conservation_ok,
    }


def rack_conservation_invariant(ledger: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the rack conservation invariant; FAIL if anything is missing."""
    raw_n = int(ledger.get("raw_named_claims") or 0)
    assigned = int(ledger.get("assigned") or 0)
    unresolved = int(ledger.get("unresolved") or 0)
    conflicts = int(ledger.get("conflicts") or 0)
    phys_fail = int(ledger.get("physical_resolution_failures") or 0)
    accounted = assigned + unresolved + conflicts + phys_fail
    forbidden = int(ledger.get("forbidden_named_dispositions") or 0)
    ok = accounted == raw_n and forbidden == 0
    return {
        "ok": ok,
        "raw_named_claims": raw_n,
        "assigned": assigned,
        "unresolved": unresolved,
        "conflicts": conflicts,
        "physical_resolution_failures": phys_fail,
        "accounted": accounted,
        "forbidden_named_dispositions": forbidden,
        "status": "PASS" if ok else "FAIL",
        "equation": ledger.get("conservation_equation"),
    }


def write_loss_report(ledger: dict[str, Any], out: Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    inv = rack_conservation_invariant(ledger)
    payload = {
        **{k: v for k, v in ledger.items() if k != "claims"},
        "invariant": inv,
        "loss_rows": [
            c
            for c in (ledger.get("claims") or [])
            if c.get("forbidden")
            or c.get("disposition") == "physical_resolution_failure"
        ],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="I/O claim conservation ledger")
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--machine", required=True)
    ap.add_argument("--words", type=str, default="", help="Comma list of Fortna words to scope")
    ap.add_argument("--rack-label", type=str, default="")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    words = None
    if args.words.strip():
        words = {int(x.strip()) for x in args.words.split(",") if x.strip()}
    ledger = build_claim_ledger(
        args.run_dir,
        args.machine,
        words=words,
        rack_label=args.rack_label,
    )
    inv = rack_conservation_invariant(ledger)
    print(json.dumps({"ok": inv["ok"], "invariant": inv, "disposition_counts": ledger["disposition_counts"]}, indent=2))
    if args.out:
        write_loss_report(ledger, args.out)
        print(f"wrote {args.out}")
    return 0 if inv["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

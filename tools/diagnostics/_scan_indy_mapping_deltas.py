#!/usr/bin/env python3
"""Scan ORINDY ASSIGNED claims for undirected→direction-aware channel deltas."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_ai_io_evidence import build_evidence_bundle  # noqa: E402
from fortna_physical_word_resolver import (  # noqa: E402
    PhysicalWordResolver,
    parse_eipcfg,
)


def undirected_old(adapter: dict, bank: int):
    """Pre-fix: first-by-slot among modules whose input_bank OR output_bank matches."""
    for mod in sorted(adapter.get("modules") or [], key=lambda m: int(m.get("slot") or 0)):
        if (mod.get("connection") or "").upper() == "HEADNODE":
            continue
        if "AENT" in (mod.get("type") or "").upper():
            continue
        try:
            ib = int(mod.get("input_bank")) if mod.get("input_bank") is not None else -1
        except (TypeError, ValueError):
            ib = -1
        try:
            ob = int(mod.get("output_bank")) if mod.get("output_bank") is not None else -1
        except (TypeError, ValueError):
            ob = -1
        if ib == bank and ib > 0:
            return mod, "I"
        if ob == bank:
            return mod, "O"
    return None


def main() -> int:
    run = ROOT / "workspace/_virgin_orindy/RUN"
    ev = build_evidence_bundle(run, "ORINDYAC6", project="ORINDYAC6")
    resolver = PhysicalWordResolver(run, "ORINDYAC6")
    topo = parse_eipcfg(run, "ORINDYAC6")
    adapters = topo.get("adapters") or []

    changed = []
    for c in ev.get("raw_claims") or []:
        if c.get("deterministic_disposition") != "ASSIGNED":
            continue
        hit = resolver.resolve(c.get("word"), c.get("bit")) or {}
        new_ch = hit.get("channel")
        half = hit.get("half_bank")
        if half is None or not new_ch:
            continue
        rio = hit.get("rio_name") or ""
        ad = next(
            (
                a
                for a in adapters
                if (a.get("rio_name") or "") == rio
                or (a.get("name") or "") == rio
                or rio in str(a.get("rio_name") or "")
            ),
            None,
        )
        if not ad:
            continue
        old = undirected_old(ad, int(half))
        if not old:
            continue
        omod, odir = old
        slot = int(omod.get("slot") or 0)
        di = slot - 1 if slot > 0 else 0
        old_ch = f"{ad.get('rio_name') or ad.get('name')}:{odir}.Data[{di}].{hit.get('bit')}"
        if old_ch != new_ch:
            changed.append(
                {
                    "claim": c.get("io_name"),
                    "word": c.get("word"),
                    "bit": c.get("bit"),
                    "old": old_ch,
                    "new": new_ch,
                    "type": hit.get("type"),
                    "dir": hit.get("direction"),
                }
            )

    print("changed_count", len(changed))
    print("by_name", Counter(x["claim"] for x in changed).most_common(30))
    flips = sorted({(x["old"], x["new"]) for x in changed})
    print("unique_flips", len(flips))
    for o, n in flips:
        print(f"{o} -> {n}")
    names = sorted({x["claim"] for x in changed})
    print("unique_claims", names)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

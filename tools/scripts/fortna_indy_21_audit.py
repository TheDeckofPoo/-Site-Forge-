#!/usr/bin/env python3
"""Audit all 21 ORINDY undirected→direction-aware corrections as one defect family.

No site-specific exceptions. Emits exports/ai-io/indy_21_defect_family_audit.json.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_ai_io_evidence import build_evidence_bundle  # noqa: E402
from fortna_configio_direction import resolve_configio_direction  # noqa: E402
from fortna_physical_word_resolver import (  # noqa: E402
    PhysicalWordResolver,
    _load_configio_rows,
    _load_eipmodules_rows,
    find_module_for_configio_bank,
    parse_eipcfg,
)
from fortna_rockwell_catalog import first_catalog  # noqa: E402

FOCUS_WORDS = ("614", "615", "616")


def _undirected_old(adapter: dict, bank: int):
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
    run = REPO / "workspace/_virgin_orindy/RUN"
    machine = "ORINDYAC6"
    ev = build_evidence_bundle(run, machine, project=machine)
    resolver = PhysicalWordResolver(run, machine)
    topo = parse_eipcfg(run, machine)
    cfg_rows = _load_configio_rows(run, machine)
    eip_rows = _load_eipmodules_rows(run, machine)

    # Collect undirected→directed deltas
    changes: list[dict[str, Any]] = []
    for c in ev.get("raw_claims") or []:
        if c.get("deterministic_disposition") != "ASSIGNED":
            continue
        hit = resolver.resolve(c.get("word"), c.get("bit")) or {}
        new_ch = hit.get("channel")
        half = hit.get("half_bank")
        if not new_ch or half is None:
            continue
        rio = hit.get("rio_name") or ""
        ad = next(
            (
                a
                for a in (topo.get("adapters") or [])
                if (a.get("rio_name") or "") == rio or (a.get("name") or "") == rio
            ),
            None,
        )
        if not ad:
            continue
        old = _undirected_old(ad, int(half))
        if not old:
            continue
        omod, odir = old
        slot = int(omod.get("slot") or 0)
        di = slot - 1 if slot > 0 else 0
        old_ch = f"{ad.get('rio_name') or ad.get('name')}:{odir}.Data[{di}].{hit.get('bit')}"
        if old_ch == new_ch:
            continue
        changes.append(
            {
                "claim": c.get("io_name"),
                "word": str(c.get("word")),
                "bit": str(c.get("bit")),
                "old_channel": old_ch,
                "new_channel": new_ch,
                "assign_how": hit.get("assign_how"),
                "type": hit.get("type"),
                "direction": hit.get("direction"),
                "bank": half,
                "adapter": rio,
                "slot": hit.get("eip_slot"),
                "data_index": hit.get("data_index"),
                "bank_join": hit.get("bank_join"),
                "binding_confidence": hit.get("binding_confidence"),
            }
        )

    by_word: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ch in changes:
        by_word[ch["word"]].append(ch)

    word_audits = []
    exceptions = []
    for word in sorted(by_word.keys(), key=lambda w: int(w)):
        cfg = [r for r in cfg_rows if str(r.get("octal_word")) == word]
        low = next((r for r in cfg if (r.get("lohi") or "").lower().startswith("l")), None)
        high = next((r for r in cfg if (r.get("lohi") or "").lower().startswith("h")), None)
        rows_info = []
        for side, row in (("Low", low), ("High", high)):
            if not row:
                continue
            desc = row.get("desc") or ""
            cat = first_catalog(desc, run_dir=run)
            cat_n = cat.catalog_number if cat else ""
            dinfo = resolve_configio_direction(catalog=cat_n, in_out=row.get("in_out"))
            bank = row.get("bank")
            # EIPModules candidates sharing numeric bank
            inputs = [
                {
                    "adapter": r.get("adapter"),
                    "type": r.get("type"),
                    "slot": r.get("slot"),
                    "input_bank": r.get("input_bank"),
                    "output_bank": r.get("output_bank"),
                }
                for r in eip_rows
                if int(r.get("input_bank") or -1) == int(bank or -999)
            ]
            outputs = [
                {
                    "adapter": r.get("adapter"),
                    "type": r.get("type"),
                    "slot": r.get("slot"),
                    "input_bank": r.get("input_bank"),
                    "output_bank": r.get("output_bank"),
                }
                for r in eip_rows
                if int(r.get("output_bank") or -999) == int(bank or -999)
            ]
            # Direction-aware selection
            exp_dir = dinfo.get("direction") or ""
            selected = None
            for ad in topo.get("adapters") or []:
                if not cat_n or exp_dir not in ("I", "O"):
                    continue
                result = find_module_for_configio_bank(
                    ad,
                    int(bank),
                    expected_direction=exp_dir,
                    expected_catalog=cat_n,
                )
                if result.get("ok"):
                    selected = {
                        "adapter": ad.get("name"),
                        "rio": ad.get("rio_name"),
                        "module": (result["module"] or {}).get("type"),
                        "slot": (result["module"] or {}).get("slot"),
                        "direction": result.get("direction"),
                        "reason": result.get("reason"),
                        "bank_join": (result["module"] or {}).get("bank_join"),
                    }
                    break
            rows_info.append(
                {
                    "side": side,
                    "desc": desc,
                    "catalog": cat_n,
                    "bank": bank,
                    "lohi": row.get("lohi"),
                    "in_out": row.get("in_out"),
                    "expected_direction": exp_dir,
                    "direction_status": dinfo.get("status"),
                    "input_candidates": inputs,
                    "output_candidates": outputs,
                    "selected": selected,
                    "collision": bool(inputs and outputs),
                }
            )

        claims = by_word[word]
        hows = {c.get("assign_how") for c in claims}
        dirs = {c.get("direction") for c in claims}
        same_class = hows <= {"configio_bank_match"} and dirs == {"O"}
        if not same_class:
            exceptions.append({"word": word, "hows": sorted(hows), "dirs": sorted(dirs)})
        word_audits.append(
            {
                "word": word,
                "configio": rows_info,
                "claims": claims,
                "same_generalized_logic": same_class,
                "defect_class": "shared_numeric_inputbank_outputbank_undirected_lookup",
            }
        )

    out = {
        "kind": "indy_21_defect_family_audit",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "machine": machine,
        "change_count": len(changes),
        "words": sorted(by_word.keys(), key=lambda w: int(w)),
        "all_same_generalized_logic": not exceptions,
        "exceptions": exceptions,
        "defect_family": (
            "A numeric EIP bank can be one module's InputBank and another's OutputBank. "
            "Undirected first-by-slot lookup selected INPUT; direction-aware catalog+bank "
            "selects OUTPUT. All 21 flips share this class."
        ),
        "word_audits": word_audits,
        "claim_list": changes,
    }
    path = REPO / "exports/ai-io/indy_21_defect_family_audit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "change_count": len(changes),
                "words": out["words"],
                "all_same_generalized_logic": out["all_same_generalized_logic"],
                "exceptions": exceptions,
                "path": str(path),
            },
            indent=2,
        )
    )
    return 0 if out["all_same_generalized_logic"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

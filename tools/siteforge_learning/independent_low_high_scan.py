#!/usr/bin/env python3
"""Independent Low/High structural scan — NO PhysicalWordResolver.

Uses only Configio, Conveyor, EIPModules, EIPModuleType, eipcfg raw tables.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))
from fortna_asc import read_asc  # noqa: E402


def _parse_bit(raw: Any) -> int:
    s = str(raw or "").strip()
    try:
        if s.isdigit() and int(s) <= 7:
            return int(s)
        return int(s, 8)  # Fortna High labels 10-17
    except Exception:
        return -1


def _load_module_types(run: Path) -> dict[str, dict]:
    paths = list((run / "PROJECT").glob("EIPModuleType.asc*")) if (run / "PROJECT").is_dir() else []
    out: dict[str, dict] = {}
    for p in paths:
        try:
            _, rows = read_asc(p)
        except Exception:
            continue
        for r in rows:
            name = (r.get("Name") or r.get("PartNum") or "").strip()
            if name:
                out[name] = {
                    k: r.get(k)
                    for k in (
                        "Name",
                        "PartNum",
                        "InputSize",
                        "InputSizeCard",
                        "InputBitSize",
                        "OutputSize",
                        "OutputSizeCard",
                        "OutputBitSize",
                        "NoInputBanks",
                        "NoOutputBanks",
                        "InpWordAlign",
                        "OutWordAlign",
                    )
                }
    return out


def _scan_run(run: Path, machine: str = "") -> dict[str, Any]:
    fortna = run / "FORTNA"
    proj = run / "PROJECT"
    cfg_paths = sorted(fortna.glob("Configio.asc*")) if fortna.is_dir() else []
    if machine:
        prefer = [p for p in cfg_paths if p.name.endswith("." + machine)]
        cfg_paths = prefer + [p for p in cfg_paths if p not in prefer]
    if not cfg_paths:
        return {"run": str(run), "ok": False, "reason": "no_configio"}
    try:
        _, cfg = read_asc(cfg_paths[0])
    except Exception as e:
        return {"run": str(run), "ok": False, "reason": str(e)}

    eip_paths = sorted(proj.glob("EIPModules.asc*")) if proj.is_dir() else []
    if machine:
        prefer = [p for p in eip_paths if p.name.endswith("." + machine)]
        eip_paths = prefer + [p for p in eip_paths if p not in prefer]
    eip = []
    if eip_paths:
        try:
            _, eip = read_asc(eip_paths[0])
        except Exception:
            eip = []

    conv = []
    cp = fortna / "Conveyor.asc"
    if cp.is_file():
        try:
            _, conv = read_asc(cp)
        except Exception:
            conv = []

    types = _load_module_types(run)

    def owners(bank: int) -> list[dict]:
        hits = []
        for r in eip:
            try:
                ib = int(float(r.get("InputBank") or 0))
            except Exception:
                ib = 0
            try:
                ob = int(float(r.get("OutputBank") or 0))
            except Exception:
                ob = 0
            if ib == bank and ib > 0:
                hits.append(
                    {
                        "dir": "I",
                        "type": r.get("Type"),
                        "slot": r.get("Slot"),
                        "adapter": r.get("Adapter"),
                        "ib": ib,
                        "ob": ob,
                    }
                )
            if ob == bank and ob > 0:
                hits.append(
                    {
                        "dir": "O",
                        "type": r.get("Type"),
                        "slot": r.get("Slot"),
                        "adapter": r.get("Adapter"),
                        "ib": ib,
                        "ob": ob,
                    }
                )
        return hits

    by_word: dict[int, dict] = defaultdict(dict)
    for r in cfg:
        try:
            w = int(float(r.get("Octal_Word") or 0))
        except Exception:
            continue
        if w <= 0:
            continue
        lohi = (r.get("LoHi") or "").strip().lower()
        try:
            b = int(float(r.get("Bank") or -1))
        except Exception:
            b = -1
        side = "Low" if lohi.startswith("l") else ("High" if lohi.startswith("h") else "")
        if not side:
            continue
        by_word[w][side] = {
            "bank": b,
            "desc": (r.get("Desc") or "").strip(),
            "interface": (r.get("Interface") or "").strip(),
        }

    claims: dict[int, list] = defaultdict(list)
    for r in conv:
        try:
            w = int(float(r.get("IO_Address_Word") or 0))
        except Exception:
            continue
        bit = _parse_bit(r.get("IO_Address_Bit"))
        if w > 0 and bit >= 0:
            claims[w].append(
                {"bit": bit, "name": r.get("IO_Name"), "raw_bit": r.get("IO_Address_Bit")}
            )

    pairs = []
    for w, sides in sorted(by_word.items()):
        if "Low" not in sides or "High" not in sides:
            continue
        lb, hb = sides["Low"]["bank"], sides["High"]["bank"]
        if hb != lb + 1:
            continue
        low_o, high_o = owners(lb), owners(hb)
        # Prefer unique owner; note collisions
        low_mod = low_o[0] if len(low_o) == 1 else None
        mt = (low_mod or {}).get("type") or ""
        tr = types.get(mt) or {}
        low_c = [c for c in claims.get(w, []) if 0 <= c["bit"] <= 7]
        high_c = [c for c in claims.get(w, []) if 8 <= c["bit"] <= 15]
        pairs.append(
            {
                "word": w,
                "low_bank": lb,
                "high_bank": hb,
                "desc_low": sides["Low"]["desc"],
                "desc_high": sides["High"]["desc"],
                "low_eip_owners": low_o,
                "high_eip_owners": high_o,
                "low_unique_module": low_mod,
                "module_type": mt,
                "slot": (low_mod or {}).get("slot"),
                "adapter": (low_mod or {}).get("adapter"),
                "direction": (low_mod or {}).get("dir"),
                "eipmoduletype": tr,
                "declared_input_size": tr.get("InputSize"),
                "declared_output_size": tr.get("OutputSize"),
                "low_claim_count": len(low_c),
                "high_claim_count": len(high_c),
                "pattern_low_match_high_miss": bool(low_o) and not high_o,
                "evidence_class": "INDEPENDENT_DERIVATION",
            }
        )

    return {
        "run": str(run),
        "ok": True,
        "machine": machine,
        "pair_count": len(pairs),
        "low_match_high_miss": sum(1 for p in pairs if p["pattern_low_match_high_miss"]),
        "high_claims_on_16ish_input": [
            p
            for p in pairs
            if p["pattern_low_match_high_miss"]
            and p["high_claim_count"] > 0
            and (p.get("direction") == "I")
        ],
        "high_claims_on_output": [
            p
            for p in pairs
            if p["pattern_low_match_high_miss"]
            and p["high_claim_count"] > 0
            and (p.get("direction") == "O")
        ],
        "oa8i_high_zero": [
            p
            for p in pairs
            if "OA8I" in (p.get("module_type") or "") and p["high_claim_count"] == 0
        ],
        "pairs": pairs,
        "eipmoduletype_catalogs": types,
    }


def main() -> int:
    roots = [
        ROOT / "exports/learning/_extract",
        ROOT / "workspace/_corpus_peek",
        ROOT / "workspace/_mscatl_peek",
        ROOT / "workspace/_virgin_orindy",
        ROOT / "workspace/_reno_peek",
        ROOT / "workspace/cp4-run",
    ]
    runs = []
    for root in roots:
        if not root.is_dir():
            continue
        for cfg in sorted(root.rglob("project.cfg")):
            runs.append(cfg.parent)

    reports = []
    for run in runs:
        # machine hint from path / project.cfg
        machine = ""
        try:
            text = (run / "project.cfg").read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                if "MACHINENAME" in line.upper() and "=" in line:
                    machine = line.split("=", 1)[1].strip()
                    break
        except Exception:
            pass
        rep = _scan_run(run, machine)
        if rep.get("ok") and rep.get("pair_count", 0) > 0:
            reports.append(rep)

    # Flatten independent examples of interest
    examples = []
    output_high = []
    for rep in reports:
        for p in rep.get("high_claims_on_16ish_input") or []:
            examples.append({**p, "machine": rep.get("machine"), "run": rep.get("run")})
        for p in rep.get("high_claims_on_output") or []:
            output_high.append({**p, "machine": rep.get("machine"), "run": rep.get("run")})

    out = {
        "kind": "independent_low_high_scan",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "physical_word_resolver_called": False,
        "runs_scanned": len(runs),
        "runs_with_pairs": len(reports),
        "independent_input_high_claim_examples": examples,
        "independent_output_high_claim_examples": output_high,
        "output_high_claim_count": len(output_high),
        "reports": [
            {
                "machine": r.get("machine"),
                "run": r.get("run"),
                "pair_count": r.get("pair_count"),
                "low_match_high_miss": r.get("low_match_high_miss"),
                "input_high_claim_pairs": len(r.get("high_claims_on_16ish_input") or []),
                "output_high_claim_pairs": len(r.get("high_claims_on_output") or []),
                "oa8i_high_zero": len(r.get("oa8i_high_zero") or []),
            }
            for r in reports
        ],
    }
    path = ROOT / "exports/learning/investigations/CP8_ALPHA_DIALECT/independent_low_high_scan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "runs_with_pairs": len(reports),
                "input_high_examples": len(examples),
                "output_high_examples": len(output_high),
                "path": str(path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

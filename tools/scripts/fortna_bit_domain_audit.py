#!/usr/bin/env python3
"""Cross-site Fortna bit-encoding domain audit (read-only, no live API).

Inventories Conveyor.IO_Address_Bit raw representations, 4-channel Low 4-7
patterns, by_word_bit alias conflicts, and failure clusters.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_ai_failure_cluster import cluster_unresolved_claims  # noqa: E402
from fortna_ai_io_evidence import build_evidence_bundle, build_raw_claims  # noqa: E402
from fortna_bit_address import parse_fortna_bit_address  # noqa: E402
from fortna_hardware_family import (  # noqa: E402
    channel_capacity_for_catalog,
    detect_family_from_catalog,
)
from fortna_physical_word_resolver import (  # noqa: E402
    PhysicalWordResolver,
    build_physical_word_map,
    _load_configio_rows,
)

SITES = [
    {
        "site": "ORINDYAC6",
        "machine": "ORINDYAC6",
        "run": REPO_ROOT / "workspace" / "_virgin_orindy" / "RUN",
    },
    {
        "site": "MSCATL_CP3",
        "machine": "MSCATL_CP3",
        "run": REPO_ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN",
    },
    {
        "site": "MSCRENOPICK",
        "machine": "MSCRENOPICK",
        "run": REPO_ROOT
        / "workspace"
        / "_reno_peek"
        / "20260813-1132-MSCRENO-MSCRENOPICK-RUN"
        / "RUN",
    },
    {
        "site": "ORDENCP3",
        "machine": "ORDENCP3",
        "run": REPO_ROOT / "workspace" / "_ordencp3_peek" / "ORDENCP3" / "RUN",
        "fixture_role": "alternate_evidence",
    },
]


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cfg_for_word(configio: list[dict], word: int) -> list[dict]:
    out = []
    for r in configio:
        try:
            if int(r.get("octal_word") if "octal_word" in r else r.get("Octal_Word")) == word:
                out.append(r)
        except (TypeError, ValueError):
            continue
    return out


def audit_site(site: dict[str, Any]) -> dict[str, Any]:
    run = Path(site["run"])
    machine = site["machine"]
    name = site["site"]
    if not (run / "project.cfg").is_file():
        return {
            "site": name,
            "run_available": False,
            "note": "RUN missing — not empty PASS",
        }

    evidence = build_evidence_bundle(run, machine, project=name)
    if site.get("fixture_role"):
        evidence["fixture_role"] = site["fixture_role"]
    raw = evidence.get("raw_claims") or []
    pm = build_physical_word_map(run, machine)
    resolver = PhysicalWordResolver(run, machine)
    configio = _load_configio_rows(run, machine)

    raw_bit_counts: Counter[str] = Counter()
    raw_bit_by_family: dict[str, Counter[str]] = defaultdict(Counter)
    encoding_counts: Counter[str] = Counter()
    rows_out: list[dict[str, Any]] = []
    low47_hits: list[dict[str, Any]] = []
    eight_nine: list[dict[str, Any]] = []

    # Index modules by bank for capacity
    bank_mod: dict[int, dict[str, Any]] = {}
    for ad in pm.get("adapters") or []:
        for m in ad.get("modules") or []:
            for bk in (m.get("input_bank"), m.get("output_bank")):
                try:
                    bank_mod[int(bk)] = {
                        **m,
                        "adapter": ad.get("rio_name"),
                        "family": m.get("family")
                        or detect_family_from_catalog(m.get("type") or m.get("catalog")),
                    }
                except (TypeError, ValueError):
                    continue

    for c in raw:
        raw_bit = str(c.get("bit") or "").strip()
        raw_bit_counts[raw_bit] += 1
        addr = parse_fortna_bit_address(
            raw_bit,
            source_table=str(c.get("source_table") or ""),
            source_row=c.get("source_row"),
        )
        encoding_counts[addr.encoding] += 1
        try:
            word_i = int(float(str(c.get("word"))))
        except (TypeError, ValueError):
            word_i = None

        cfg_rows = _cfg_for_word(configio, word_i) if word_i is not None else []
        lo = next((r for r in cfg_rows if str(r.get("lohi") or "").lower().startswith("lo")), None)
        hi = next((r for r in cfg_rows if str(r.get("lohi") or "").lower().startswith("hi")), None)
        half_row = lo if addr.half == "Low" else hi if addr.half == "High" else lo or hi
        bank = None
        try:
            bank = int((half_row or {}).get("bank"))
        except (TypeError, ValueError):
            bank = None
        mod = bank_mod.get(bank) if bank is not None else None
        catalog = str((mod or {}).get("type") or (mod or {}).get("catalog") or "")
        family = str((mod or {}).get("family") or detect_family_from_catalog(catalog) or "UNKNOWN")
        cap = channel_capacity_for_catalog(catalog) if catalog else 0
        raw_bit_by_family[family][raw_bit] += 1

        hit = resolver.resolve(c.get("word"), c.get("bit"))
        rec = {
            "site": name,
            "machine": machine,
            "io_name": c.get("io_name"),
            "claim_id": c.get("claim_id"),
            "word": c.get("word"),
            "raw_bit": raw_bit,
            "fortna_bit_address": addr.to_dict(),
            "configio_lohi": (half_row or {}).get("lohi"),
            "configio_bank": bank,
            "configio_interface": (half_row or {}).get("interface"),
            "configio_in_out": (half_row or {}).get("in_out"),
            "direction": (hit or {}).get("direction") or (mod or {}).get("direction"),
            "adapter": (hit or {}).get("rio_name") or (mod or {}).get("adapter"),
            "hardware_family": family,
            "module_catalog": catalog,
            "module_channel_capacity": cap,
            "deterministic_disposition": c.get("deterministic_disposition"),
            "physical_address": c.get("physical_address") or (hit or {}).get("channel"),
        }
        rows_out.append(rec)

        if raw_bit in {"8", "9"}:
            eight_nine.append(rec)

        # 4-channel Low bits beyond module capacity (OA4/IA4 only — not FLEX 16-pt)
        wrec = (pm.get("words") or {}).get(str(c.get("word"))) or {}
        wcat = str(wrec.get("type") or wrec.get("catalog") or catalog or "")
        wcap = channel_capacity_for_catalog(wcat) if wcat else cap
        is_4ch_low_overflow = (
            addr.half == "Low"
            and addr.module_bit is not None
            and wcap == 4
            and addr.module_bit >= 4
            and ("OA4" in wcat.upper() or "IA4" in wcat.upper() or "IB4" in wcat.upper() or "OB4" in wcat.upper())
        )
        if is_4ch_low_overflow:
            catalog = catalog or wcat
            family = "1734" if family == "UNKNOWN" else family
            cap = 4
            # Collision if remapped to High module_bit = module_bit-4
            remap_mb = addr.module_bit - 4
            high_logical = 8 + remap_mb
            collide = None
            for other in raw:
                if str(other.get("word")) != str(c.get("word")):
                    continue
                oa = parse_fortna_bit_address(other.get("bit"))
                if oa.logical_bit == high_logical and other.get("deterministic_disposition") == "ASSIGNED":
                    collide = {
                        "owner": other.get("io_name"),
                        "owner_bit": other.get("bit"),
                        "owner_addr": other.get("physical_address"),
                    }
                    break
            low47_hits.append(
                {
                    **{k: rec[k] for k in (
                        "site", "machine", "io_name", "claim_id", "word", "raw_bit",
                        "configio_bank", "module_catalog", "deterministic_disposition",
                        "physical_address",
                    )},
                    "low_bank": (lo or {}).get("bank"),
                    "high_bank": (hi or {}).get("bank"),
                    "module_bit": addr.module_bit,
                    "hypothetical_remap_module_bit": remap_mb,
                    "collision_if_remapped": collide,
                    "neighbors_proven": [
                        {
                            "io_name": o.get("io_name"),
                            "bit": o.get("bit"),
                            "addr": o.get("physical_address"),
                        }
                        for o in raw
                        if str(o.get("word")) == str(c.get("word"))
                        and o.get("deterministic_disposition") == "ASSIGNED"
                    ][:12],
                }
            )

    # by_word_bit integrity: no duplicate channels for different logical keys
    bwb = pm.get("by_word_bit") or {}
    channel_owners: dict[str, list[str]] = defaultdict(list)
    for k, v in bwb.items():
        if k.startswith("_"):
            continue
        ch = v.get("channel")
        if ch:
            channel_owners[ch].append(k)
    multi = {ch: keys for ch, keys in channel_owners.items() if len(keys) > 1}

    clustered = cluster_unresolved_claims(raw, evidence=evidence)
    cluster_summaries = []
    for cl in (clustered.get("clusters") or [])[:20]:
        dims = cl.get("dimensions") or {}
        cluster_summaries.append(
            {
                "cluster_id": cl.get("cluster_id"),
                "count": cl.get("count"),
                "family": dims.get("hardware_family"),
                "catalog": dims.get("module_catalog"),
                "direction": dims.get("direction"),
                "configio_interface": dims.get("configio_interface"),
                "configio_lohi": dims.get("configio_lohi"),
                "bit_pattern": dims.get("bit_encoding_class"),
                "failure_reason": dims.get("resolution_failure_reason"),
                "representative_claims": (cl.get("claims") or [])[:5],
            }
        )

    cc = evidence.get("conservation_counts") or {}
    return {
        "site": name,
        "run_available": True,
        "raw_physical_claims": len(raw),
        "needs_resolution": evidence.get("needs_resolution"),
        "evidence_status": evidence.get("evidence_status"),
        "raw_bit_counts": dict(sorted(raw_bit_counts.items(), key=lambda kv: kv[0])),
        "raw_bit_counts_by_family": {
            fam: dict(sorted(ctr.items())) for fam, ctr in raw_bit_by_family.items()
        },
        "encoding_counts": dict(encoding_counts),
        "raw_source_8_or_9_count": len(eight_nine),
        "raw_source_8_or_9_samples": eight_nine[:10],
        "four_channel_low_bits_4_7": low47_hits,
        "four_channel_low_bits_4_7_count": len(low47_hits),
        "by_word_bit_count": len(bwb),
        "by_word_bit_label_count": len(pm.get("by_word_bit_labels") or {}),
        "channels_with_multiple_logical_keys": multi,
        "failure_clusters": {
            "unresolved_input": clustered.get("input_claim_count"),
            "cluster_count": clustered.get("cluster_count"),
            "conservation": clustered.get("conservation"),
            "top_clusters": cluster_summaries,
        },
        "conservation_counts": cc,
    }


def audit_parse_matrix() -> list[dict[str, Any]]:
    """Document parse result for every raw label 0-17."""
    out = []
    for label in [str(i) for i in range(0, 18)]:
        addr = parse_fortna_bit_address(label)
        out.append(addr.to_dict())
    return out


def main() -> int:
    report = {
        "kind": "fortna_bit_domain_audit",
        "generated_at": _ts(),
        "live_api_called": False,
        "parse_matrix_0_17": audit_parse_matrix(),
        "fortnaplus_source_evidence": [
            {
                "file": "tools/scripts/fortna_autogen.py",
                "symbol": "_fortna_bit_is_high",
                "fact": "Prefer int(s, 8); octal 10-17 → High (v >= 8)",
            },
            {
                "file": "tools/scripts/fortna_autogen.py",
                "symbol": "_fortna_bit_to_data_bit",
                "fact": "Prefer PLC-5 octal (0-7, 10-17 → 0-15); POINT clamps to max_bit",
            },
            {
                "file": "tools/scripts/fortna_plc2_io_truth.py",
                "symbol": "_octal_bit_to_data_bit",
                "fact": "Decimal 10-17 remapped to 8+(n-10); else 0-15 decimal",
            },
            {
                "file": "tools/scripts/fortna_physical_word_resolver.py",
                "symbol": "parse_fortna_octal_bit / FortnaBitAddress",
                "fact": "[0-7]+ strings parsed as base-8 labels; High logical 8-15 → module_bit 0-7",
            },
            {
                "file": "tools/knowledge/fortnaplus_tables.json",
                "symbol": "Configio",
                "fact": "Octal_Word + LoHi + Bank + In_Out define word halves and direction masks",
            },
        ],
        "aliasing_fix": (
            "Prior by_word_bit inserted High keys both as logical 8+n AND as 10+n in the "
            "SAME dict. For OA4 (n=0..3) keys 10/11 were written twice (conflict). "
            "Fixed: logical keys only; Fortna labels live in by_word_bit_labels."
        ),
        "sites": [],
    }
    for site in SITES:
        print(f"=== {site['site']} ===", flush=True)
        s = audit_site(site)
        report["sites"].append(s)
        print(
            json.dumps(
                {
                    "site": s.get("site"),
                    "raw": s.get("raw_physical_claims"),
                    "needs_resolution": s.get("needs_resolution"),
                    "clusters": (s.get("failure_clusters") or {}).get("cluster_count"),
                    "raw_8_9": s.get("raw_source_8_or_9_count"),
                    "low47_4ch": s.get("four_channel_low_bits_4_7_count"),
                    "bit_keys": list((s.get("raw_bit_counts") or {}).keys())[:20],
                },
                indent=2,
            ),
            flush=True,
        )

    out = REPO_ROOT / "exports" / "ai-io" / "audits" / "bit_domain_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    # Drop per-claim rows from main report size — keep summaries; write detail sidecar
    slim = dict(report)
    detail = {}
    for s in slim["sites"]:
        if not s.get("run_available"):
            continue
        detail[s["site"]] = {
            "four_channel_low_bits_4_7": s.get("four_channel_low_bits_4_7"),
            "raw_source_8_or_9_samples": s.get("raw_source_8_or_9_samples"),
            "channels_with_multiple_logical_keys": s.get("channels_with_multiple_logical_keys"),
        }
        s.pop("four_channel_low_bits_4_7", None)
        s.pop("raw_source_8_or_9_samples", None)
    out.write_text(json.dumps(slim, indent=2), encoding="utf-8")
    detail_path = out.with_name("bit_domain_audit_detail.json")
    detail_path.write_text(json.dumps(detail, indent=2), encoding="utf-8")
    print(f"Wrote {out}", flush=True)
    print(f"Wrote {detail_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

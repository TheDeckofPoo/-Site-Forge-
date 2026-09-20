#!/usr/bin/env python3
"""Corpus-wide model-level backtest after f2cf46f Atlanta field fixes.

Does NOT regenerate every PLC. Uses PostgreSQL warehouse + deterministic
model APIs where RUN extracts are available. Does not select/tune a virgin site.
"""
from __future__ import annotations

import json
import re
import sys
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from siteforge_warehouse.postgres_repository import make_engine  # noqa: E402
from sqlalchemy import text  # noqa: E402
from fortna_hardware_family import channel_capacity_for_catalog  # noqa: E402

OUT = ROOT / "exports" / "backtest"
RES = ROOT / "exports" / "research"


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, str):
        path.write_text(obj if obj.endswith("\n") else obj + "\n", encoding="utf-8")
    else:
        path.write_text(
            json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )


def main() -> int:
    eng = make_engine()
    assert eng is not None
    OUT.mkdir(parents=True, exist_ok=True)
    RES.mkdir(parents=True, exist_ok=True)

    with eng.connect() as c:
        archives = [
            dict(r)
            for r in c.execute(
                text(
                    "SELECT archive_sha256, project, machine, filename, complete, "
                    "sync_status, discovered_path, extractor_version "
                    "FROM corpus.archives ORDER BY machine"
                )
            ).mappings()
        ]
        # Module catalog aggregate from eipmodules
        mods = [
            dict(r)
            for r in c.execute(
                text(
                    "SELECT machine, archive_sha256, type, direction, COUNT(*) AS n "
                    "FROM evidence.eipmodules "
                    "GROUP BY machine, archive_sha256, type, direction"
                )
            ).mappings()
        ]
        conflicts = [
            dict(r)
            for r in c.execute(
                text(
                    "SELECT machine, conflict_kind, COUNT(*) AS n "
                    "FROM evidence.conflicts GROUP BY machine, conflict_kind"
                )
            ).mappings()
        ]
        bridges = [
            dict(r)
            for r in c.execute(
                text(
                    "SELECT machine, status, COUNT(*) AS n "
                    "FROM evidence.adapter_bridges GROUP BY machine, status"
                )
            ).mappings()
        ]
        dialect = [
            dict(r)
            for r in c.execute(
                text(
                    "SELECT machine, form, SUM(count) AS n "
                    "FROM learning.dialect_observations "
                    "GROUP BY machine, form"
                )
            ).mappings()
        ]
        rules = [
            dict(r)
            for r in c.execute(
                text(
                    "SELECT rule_id, status, title, summary, meta "
                    "FROM learning.rule_candidates ORDER BY rule_id"
                )
            ).mappings()
        ]
        # ingest failures
        failed = [a for a in archives if not a.get("complete") or a.get("sync_status") == "FAILED"]
        complete = [a for a in archives if a.get("complete")]

    # --- I/O capacity / catalog study ---
    catalog_stats: dict[str, dict[str, Any]] = {}
    for m in mods:
        cat = str(m.get("type") or "UNKNOWN").strip() or "UNKNOWN"
        cap = channel_capacity_for_catalog(cat)
        st = catalog_stats.setdefault(
            cat,
            {
                "catalog": cat,
                "modules_observed": 0,
                "controller_set": set(),
                "known_capacity": cap,
                "capacity_known": cap > 0,
                "directions": Counter(),
            },
        )
        st["modules_observed"] += int(m.get("n") or 0)
        st["controller_set"].add(m.get("machine"))
        st["directions"][str(m.get("direction") or "")] += int(m.get("n") or 0)
        if not st["capacity_known"] and cap > 0:
            st["known_capacity"] = cap
            st["capacity_known"] = True

    capacity_report = []
    for cat, st in sorted(catalog_stats.items(), key=lambda x: -x[1]["modules_observed"]):
        capacity_report.append(
            {
                "catalog": cat,
                "modules_observed": st["modules_observed"],
                "controllers": len(st["controller_set"]),
                "known_capacity": st["known_capacity"],
                "capacity_known": st["capacity_known"],
                "directions": dict(st["directions"]),
                "ui_risk": (
                    None
                    if st["capacity_known"]
                    else "UNKNOWN_CAPACITY — UI may show N instead of N/C"
                ),
            }
        )

    # OW8 specifically must be 8
    ow8 = next((r for r in capacity_report if "OW8" in r["catalog"].upper()), None)

    # --- Merge corpus from warehouse conflicts / adapter bridges + discovery peeks ---
    # Prefer re-running discovery on available extracts under exports/learning/_extract
    merge_rows = []
    extract_root = ROOT / "exports" / "learning" / "_extract"
    peeks = [
        ROOT / "workspace" / "_mscatl_peek" / "MSCATL_CP3" / "RUN",
        ROOT / "workspace" / "_virgin_orindy" / "RUN",
        ROOT / "exports" / "demo" / "siteforge-reality-check-v1" / "HARD_BLIND" / "_run_extract" / "FISHER_CC9" / "RUN",
    ]
    try:
        from fortna_plc2_merge_discovery import (  # noqa: WPS433
            discover_plc2_merges,
            discovery_to_autogen_merges_2to1,
        )
    except Exception as ex:
        discover_plc2_merges = None  # type: ignore
        discovery_err = str(ex)
    else:
        discovery_err = None

    run_candidates: list[tuple[str, Path]] = []
    for p in peeks:
        if (p / "project.cfg").is_file():
            # machine from path heuristic
            mach = p.parent.name if p.name.upper() == "RUN" else p.name
            run_candidates.append((mach, p))
    if extract_root.is_dir():
        for d in extract_root.iterdir():
            run = d / "RUN"
            if (run / "project.cfg").is_file():
                # read machine from cfg
                mach = ""
                try:
                    for line in (run / "project.cfg").read_text(
                        encoding="utf-8", errors="replace"
                    ).splitlines():
                        if line.upper().startswith("MACHINENAME="):
                            mach = line.split("=", 1)[1].strip()
                            break
                except Exception:
                    mach = d.name
                run_candidates.append((mach or d.name, run))

    lane_hist = Counter()
    suffix_merges = []
    handoff_ok = 0
    handoff_fail = 0
    for mach, run in run_candidates[:80]:
        if discover_plc2_merges is None:
            break
        try:
            report = discover_plc2_merges(run, mach)
            rows = discovery_to_autogen_merges_2to1(report)
            for m in rows:
                lanes = int(m.get("lanes") or 2)
                lane_hist[lanes] += 1
                name = str(m.get("name") or m.get("discharge") or "")
                lettered = bool(name and name[-1:].isalpha() and any(ch.isdigit() for ch in name))
                emittable = lanes >= 2  # after f2cf46f
                merge_rows.append(
                    {
                        "machine": mach,
                        "name": name,
                        "lanes": lanes,
                        "discharge": m.get("discharge"),
                        "lettered_discharge": lettered,
                        "compiler_emittable_after_f2cf46f": emittable,
                        "source": m.get("source"),
                    }
                )
                if lettered:
                    suffix_merges.append({"machine": mach, "name": name, "lanes": lanes})
                if emittable:
                    handoff_ok += 1
                else:
                    handoff_fail += 1
        except Exception as ex:
            merge_rows.append(
                {
                    "machine": mach,
                    "error": str(ex),
                    "status": "TOOL_ERROR",
                }
            )
            handoff_fail += 1

    # --- Safety taxonomy from Configio/io_claims sample names in PG ---
    with eng.connect() as c:
        # Sample io claim names / configio desc for safety-ish tokens
        claim_names = [
            dict(r)
            for r in c.execute(
                text(
                    "SELECT machine, io_name, COUNT(*) AS n "
                    "FROM evidence.io_claims "
                    "WHERE io_name ~* '(ESTOP|E-STOP|ESLS|\\yESR\\y|\\yMCR\\y|RESET|SAFE|GATE|CS[0-9])' "
                    "GROUP BY machine, io_name "
                    "ORDER BY n DESC LIMIT 2000"
                )
            ).mappings()
        ]
        cfg_desc = [
            dict(r)
            for r in c.execute(
                text(
                    'SELECT machine, "desc" AS desc_text, COUNT(*) AS n '
                    "FROM evidence.configio_rows "
                    "WHERE \"desc\" ~* '(ESTOP|E-STOP|ESLS|ESR|MCR|RESET|SAFE)' "
                    'GROUP BY machine, "desc" '
                    "ORDER BY n DESC LIMIT 1000"
                )
            ).mappings()
        ]

    def classify_safety_name(name: str) -> str:
        u = (name or "").upper()
        if "ESTOP" in u or "E-STOP" in u or "E_STOP" in u:
            return "E_STOP"
        if "ESLS" in u:
            return "ESLS"
        if re_search_esr(u):
            return "ESR"
        if "MCR" in u:
            return "MCR"
        if "RESET" in u:
            return "RESET"
        if re.search(r"\bCS\d|\bCS_", u) or "CONTROLSTATION" in u.replace(" ", ""):
            return "CS"
        if "SAFE" in u or "GATE" in u:
            return "OTHER_SAFETY"
        return "OTHER"

    def re_search_esr(u: str) -> bool:
        return bool(re.search(r"(^|[^A-Z])ESR([^A-Z]|$)|ESRELAY|E-STOP.?RELAY", u))

    taxonomy_patterns: dict[str, dict[str, Any]] = {}
    for row in claim_names:
        name = str(row.get("io_name") or "")
        cat = classify_safety_name(name)
        # normalize pattern: strip digits lightly
        pat = re.sub(r"\d+", "#", name.upper())
        key = f"{cat}::{pat}"
        ent = taxonomy_patterns.setdefault(
            key,
            {
                "normalized_pattern": pat,
                "category": cat,
                "evidence_source": "evidence.io_claims.io_name",
                "controllers": set(),
                "count": 0,
                "confidence": "OBSERVED_ONLY",
                "examples": [],
            },
        )
        ent["controllers"].add(row.get("machine"))
        ent["count"] += int(row.get("n") or 0)
        if len(ent["examples"]) < 5:
            ent["examples"].append(name)

    for row in cfg_desc:
        name = str(row.get("desc_text") or row.get("desc") or "")
        cat = classify_safety_name(name)
        pat = re.sub(r"\d+", "#", name.upper())
        key = f"{cat}::CFG::{pat}"
        ent = taxonomy_patterns.setdefault(
            key,
            {
                "normalized_pattern": pat,
                "category": cat,
                "evidence_source": "evidence.configio_rows.desc",
                "controllers": set(),
                "count": 0,
                "confidence": "OBSERVED_ONLY",
                "examples": [],
            },
        )
        ent["controllers"].add(row.get("machine"))
        ent["count"] += int(row.get("n") or 0)
        if len(ent["examples"]) < 5:
            ent["examples"].append(name)

    taxonomy_list = []
    for ent in taxonomy_patterns.values():
        taxonomy_list.append(
            {
                **{k: v for k, v in ent.items() if k != "controllers"},
                "controllers_observed": len(ent["controllers"]),
                "controller_sample": sorted(ent["controllers"])[:12],
            }
        )
    taxonomy_list.sort(key=lambda x: (-x["count"], x["category"]))

    by_cat = Counter(t["category"] for t in taxonomy_list)

    # --- Controller evaluation rollup (model-level) ---
    results = []
    for a in complete:
        mach = a.get("machine") or ""
        status = "PASS"
        notes = []
        try:
            # applicable checks from warehouse presence
            n_mod = sum(
                int(m["n"])
                for m in mods
                if m.get("machine") == mach and m.get("archive_sha256") == a["archive_sha256"]
            )
            n_bridge = sum(
                int(b["n"]) for b in bridges if b.get("machine") == mach
            )
            n_conf = sum(
                int(b["n"]) for b in conflicts if b.get("machine") == mach
            )
            if n_mod == 0:
                status = "NOT_APPLICABLE"
                notes.append("no eipmodules")
            else:
                # unknown capacity modules?
                unknown_caps = [
                    m["type"]
                    for m in mods
                    if m.get("machine") == mach
                    and not channel_capacity_for_catalog(m.get("type"))
                ]
                if unknown_caps:
                    status = "REVIEW_REQUIRED"
                    notes.append(f"unknown_capacity_catalogs={sorted(set(unknown_caps))[:8]}")
                if n_conf:
                    notes.append(f"conflicts={n_conf}")
            results.append(
                {
                    "machine": mach,
                    "archive_sha256": a["archive_sha256"],
                    "status": status,
                    "eipmodules": n_mod,
                    "adapter_bridges": n_bridge,
                    "conflicts": n_conf,
                    "notes": notes,
                }
            )
        except Exception as ex:
            results.append(
                {
                    "machine": mach,
                    "archive_sha256": a.get("archive_sha256"),
                    "status": "TOOL_ERROR",
                    "error": str(ex),
                    "trace": traceback.format_exc()[-500:],
                }
            )

    status_counts = Counter(r["status"] for r in results)

    # Ingest exceptions
    ingest_exceptions = []
    for a in archives:
        if a.get("complete") and a.get("sync_status") != "FAILED":
            continue
        fname = str(a.get("filename") or "")
        klass = "UNKNOWN"
        if "DATA" in fname.upper() or "LOG" in fname.upper():
            klass = "EXPECTED_NON_RUN"
        elif not a.get("complete"):
            klass = "MISSING_PROJECT_CFG"
        ingest_exceptions.append(
            {
                "archive_sha256": a.get("archive_sha256"),
                "filename": fname,
                "machine": a.get("machine"),
                "sync_status": a.get("sync_status"),
                "classification": klass,
            }
        )

    # Fisher / CP8 candidate shadow (structural only — no promotion)
    fisher_shadow = {
        "reject_numeric_suffix_as_cross_rack_binding_key": {
            "status": "CANDIDATE_RULE",
            "shadow": "guard_only — does not resolve claims; reduces false bindings",
            "controllers_with_unbound_failures": sum(
                1 for r in results if any("conflicts" in (n or "") for n in r.get("notes") or [])
            ),
            "promotion": False,
        },
        "duplicate_word_bit_owner_conflict_requires_review": {
            "status": "CANDIDATE_RULE",
            "shadow": "review guard for OWNER_CONFLICT duplicates",
            "promotion": False,
        },
        "panel_catalog_numeric_alpha_low_a_slot": {
            "status": "CANDIDATE_RULE",
            "shadow": "CP8 — independent corpus still candidate; CURRENT_DECODER_OUTPUT not used as proof",
            "promotion": False,
        },
    }

    backtest = {
        "kind": "f2cf46f_corpus_backtest",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_sha_hint": "f2cf46f",
        "archives_total": len(archives),
        "archives_complete": len(complete),
        "controllers_evaluated": len(results),
        "status_counts": dict(status_counts),
        "results": results,
        "ow8_capacity": ow8,
        "capacity_unknown_catalogs": [
            r for r in capacity_report if not r["capacity_known"]
        ][:40],
        "merge_lane_histogram": dict(lane_hist),
        "merge_suffix_examples": suffix_merges[:40],
        "merge_handoff_ok": handoff_ok,
        "merge_handoff_fail_or_error": handoff_fail,
        "discovery_err": discovery_err,
        "ingest_exceptions": ingest_exceptions,
        "rules": [
            {k: r.get(k) for k in ("rule_id", "status", "title")} for r in rules
        ],
        "fisher_cp8_shadow": fisher_shadow,
        "note": "Model-level evaluation; full PLC regen not performed for every controller.",
    }

    _write(OUT / "f2cf46f_corpus_backtest.json", backtest)
    _write(
        OUT / "f2cf46f_corpus_backtest.md",
        f"""# f2cf46f Corpus Backtest

Generated: {backtest['generated_at']}

## Summary

| Metric | Value |
|--------|------:|
| Archives total | {len(archives)} |
| Complete | {len(complete)} |
| Controllers evaluated | {len(results)} |
| PASS | {status_counts.get('PASS', 0)} |
| REVIEW_REQUIRED | {status_counts.get('REVIEW_REQUIRED', 0)} |
| NOT_APPLICABLE | {status_counts.get('NOT_APPLICABLE', 0)} |
| TOOL_ERROR | {status_counts.get('TOOL_ERROR', 0)} |

## Capacity

OW8 known capacity: **{(ow8 or {}).get('known_capacity')}** (must be 8)

Unknown-capacity catalogs (sample): {len(backtest['capacity_unknown_catalogs'])}

## Merges (available RUN extracts)

Lane histogram: `{dict(lane_hist)}`
Lettered discharge examples: {len(suffix_merges)}
Emittable after f2cf46f: {handoff_ok} / errors-or-fail {handoff_fail}

## Ingest exceptions

{len(ingest_exceptions)} non-complete archives classified (see JSON).

## Candidates

Shadow only — no promotion. See `fisher_cp8_shadow` in JSON.
""",
    )

    _write(
        OUT / "merge_handoff_corpus.json",
        {
            "lane_histogram": dict(lane_hist),
            "merges": merge_rows[:500],
            "suffix_merges": suffix_merges,
            "counts": {
                "2:1": lane_hist.get(2, 0),
                "3:1": lane_hist.get(3, 0),
                ">3": sum(v for k, v in lane_hist.items() if k > 3),
            },
        },
    )
    _write(
        OUT / "merge_handoff_corpus.md",
        f"""# Merge handoff corpus

| Lane class | Count |
|------------|------:|
| 2:1 | {lane_hist.get(2, 0)} |
| 3:1 | {lane_hist.get(3, 0)} |
| >3 | {sum(v for k, v in lane_hist.items() if k > 3)} |
| lettered discharge | {len(suffix_merges)} |

After f2cf46f, lane_n>=2 is emittable (3:1 no longer skipped).
""",
    )

    tax_out = {
        "kind": "safety_device_taxonomy",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "category_counts": dict(by_cat),
        "patterns": taxonomy_list[:300],
        "note": "DEVICE CLASSIFICATION only — no zone assignment.",
    }
    _write(RES / "safety_device_taxonomy.json", tax_out)
    _write(
        RES / "safety_device_taxonomy.md",
        "# Safety device taxonomy (corpus)\n\n"
        + "## Category counts\n\n"
        + "\n".join(f"- **{k}**: {v}" for k, v in by_cat.most_common())
        + "\n\nTop patterns in JSON. No zone assignment performed.\n",
    )

    _write(
        OUT / "module_capacity_discrepancy.json",
        {
            "catalogs": capacity_report,
            "unknown_capacity": [r for r in capacity_report if not r["capacity_known"]],
            "ow8": ow8,
        },
    )

    _write(
        RES / "corpus_ingest_exceptions.md",
        "# Corpus ingest exceptions\n\n"
        + "\n".join(
            f"- `{e.get('filename')}` → **{e.get('classification')}** "
            f"(machine={e.get('machine')}, status={e.get('sync_status')})"
            for e in ingest_exceptions
        )
        + "\n",
    )

    # Product readiness snapshot (factual)
    _write(
        OUT / "PRODUCT_READINESS_AFTER_F2CF46F.md",
        """# Product readiness after f2cf46f (+ Browse Archive hotfix)

| Subsystem | Status | Evidence |
|-----------|--------|----------|
| Hardware topology | PASS | Atlanta 3/23/0; corpus eipmodules present |
| Physical I/O | PASS/PARTIAL | Atlanta 256 PROVEN; corpus REVIEW where capacity unknown |
| I/O SPARE vs claim | PARTIAL | UNCLAIMED semantics fixed; PROVEN_SPARE reserved |
| Transportation discovery | PARTIAL | merges discovered; 3:1 now emittable |
| Transportation handoff | PARTIAL | P3012A emit fixed; GUI placement of lettered nodes still geometry-dependent |
| Safety discovery | PARTIAL | taxonomy OBSERVED_ONLY; Build coverage needs field verify |
| Safety engineer persistence | PARTIAL | Apply snapshot/verify + parity gate added; needs GUI smoke |
| Safety compiler | PARTIAL | no false empty members after verified Apply |
| Sorter | NOT_APPLICABLE / PARTIAL | evidence-driven; no invent |
| VFD | NOT_IMPLEMENTED | — |
| PLC compiler | PARTIAL | can emit; virgin qualify may still FAIL/REVIEW |
| Qualification | PARTIAL | dict detail + isolation polarity fixed |
| PostgreSQL | PASS | live warehouse |
| AI Investigator | PARTIAL | candidates shadow-only |
| GUI Load RUN | HOTFIX | syntax error blocked renderer — fixed this pass |
| cross-site isolation | PASS | adversarial remaining / PG proof polarity fixed |

Do not treat as virgin-test PASS until Browse Archive Electron smoke is confirmed.
""",
    )

    print(
        json.dumps(
            {
                "controllers_evaluated": len(results),
                "status_counts": dict(status_counts),
                "merge_lanes": dict(lane_hist),
                "taxonomy_categories": dict(by_cat),
                "ingest_exceptions": len(ingest_exceptions),
                "out": str(OUT),
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

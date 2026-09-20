#!/usr/bin/env python3
"""Deterministic dossier for PANEL_CATALOG_NUMERIC_ALPHA (e.g. CP8-1794-IA16-1A).

Shadow analysis only — does NOT modify production resolver.
No finished L5X. No live API. No site-specific rules.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tarfile
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tools"))

from fortna_asc import read_asc  # noqa: E402
from fortna_eip_adapter_bridge import (  # noqa: E402
    build_adapter_bridges,
    load_eipadapters_rows,
)
from fortna_physical_word_resolver import (  # noqa: E402
    _load_eipmodules_rows,
    parse_eipcfg,
)

from siteforge_learning.classify_configio_dialect import (  # noqa: E402
    classify_configio_dialect,
)
from siteforge_learning.corpus_models import FORM_PANEL_CATALOG_NUMERIC_ALPHA  # noqa: E402

_FORM_RE = re.compile(
    r"^(?P<panel>[A-Za-z][A-Za-z0-9_]*)-"
    r"(?P<catalog>\d{4}-[A-Za-z0-9]+)-"
    r"(?P<numeric>\d+)(?P<alpha>[ABab])$",
    re.I,
)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_run_from_tar(tar_path: Path, dest: Path) -> Path | None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:*") as tf:
        # safety: only extract needed members
        members = [
            m
            for m in tf.getmembers()
            if m.isfile()
            and any(
                x in m.name.replace("\\", "/")
                for x in (
                    "Configio.asc",
                    "EIPModules.asc",
                    "EIPAdapters.asc",
                    "eipcfg",
                    "project.cfg",
                )
            )
        ]
        tf.extractall(dest, members=members)
    # find RUN root
    for cfg in dest.rglob("project.cfg"):
        return cfg.parent
    return None


def _find_matching_archives(roots: list[Path]) -> list[tuple[Path, list[str]]]:
    hits = []
    for root in roots:
        for tar in sorted(root.rglob("*.tar.gz")):
            samples = []
            try:
                with tarfile.open(tar, "r:*") as tf:
                    for m in tf.getmembers():
                        if not m.isfile() or "Configio.asc" not in Path(m.name).name:
                            continue
                        f = tf.extractfile(m)
                        if not f:
                            continue
                        text = f.read().decode("utf-8", errors="replace")
                        for line in text.splitlines():
                            # crude: look for pattern tokens in tilde ASC lines
                            for tok in line.replace("~", " ").split():
                                if _FORM_RE.match(tok.strip()):
                                    samples.append(tok.strip())
                        if samples:
                            break
            except Exception:
                continue
            if samples:
                hits.append((tar, sorted(set(samples))[:40]))
    return hits


def _load_configio(run: Path) -> list[dict[str, Any]]:
    paths = sorted(run.rglob("Configio.asc*"))
    if not paths:
        return []
    paths.sort(key=lambda p: (0 if p.name.count(".") >= 2 else 1, str(p)))
    try:
        _, rows = read_asc(paths[0])
    except Exception:
        return []
    out = []
    for r in rows:
        desc = (r.get("Desc") or "").strip()
        m = _FORM_RE.match(desc)
        if not m:
            continue
        out.append(
            {
                "desc": desc,
                "panel": m.group("panel").upper(),
                "catalog": m.group("catalog"),
                "numeric_token": int(m.group("numeric")),
                "alpha_suffix": m.group("alpha").upper(),
                "bank": r.get("Bank"),
                "octal_word": r.get("Octal_Word") or r.get("OctalWord"),
                "lohi": (r.get("LoHi") or "").strip(),
                "in_out": (r.get("In_Out") or "").strip(),
                "interface": (r.get("Interface") or "").strip(),
                "i_o_type": (r.get("I_O_Type") or "").strip(),
                "process": (r.get("Process") or "").strip(),
                "status": (r.get("Status") or "").strip(),
            }
        )
    return out


def _correlate(run: Path, machine: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    topo = parse_eipcfg(run, machine)
    eip = _load_eipmodules_rows(run, machine)
    ads = load_eipadapters_rows(run, machine)
    bridges = build_adapter_bridges(
        eipmodules_adapter_names=sorted({(r.get("adapter") or "") for r in eip}),
        eipadapters_rows=ads,
        eipcfg_adapters=topo.get("adapters") or [],
    )

    # Enrich each Configio row with bank-matched EIPModules candidates (direction-aware later)
    enriched = []
    for row in rows:
        try:
            bank = int(float(str(row.get("bank"))))
        except (TypeError, ValueError):
            bank = -1
        inputs = [r for r in eip if int(r.get("input_bank") or -1) == bank and bank > 0]
        outputs = [r for r in eip if int(r.get("output_bank") or -999) == bank]
        # Prefer catalog match
        cat_u = (row.get("catalog") or "").upper()
        inputs_c = [r for r in inputs if (r.get("type") or "").upper() == cat_u] or inputs
        outputs_c = [r for r in outputs if (r.get("type") or "").upper() == cat_u] or outputs
        # Direction from catalog
        direction = "I" if any(x in cat_u for x in ("IA", "IB", "IM")) else (
            "O" if any(x in cat_u for x in ("OA", "OB", "OW")) else ""
        )
        cands = inputs_c if direction == "I" else outputs_c if direction == "O" else inputs_c + outputs_c
        chosen = cands[0] if len(cands) == 1 else (cands[0] if cands else None)
        ambiguous = len(cands) > 1
        bridge = None
        if chosen:
            bridge = bridges.get((chosen.get("adapter") or "").strip())
            bridge = bridge.to_dict() if bridge and hasattr(bridge, "to_dict") else (
                bridge if isinstance(bridge, dict) else None
            )
        # eipcfg module by adapter IP bridge + slot
        eipcfg_mod = None
        if chosen and bridge and bridge.get("status") == "PROVEN":
            for ad in topo.get("adapters") or []:
                if (ad.get("name") or "") == bridge.get("eipcfg_adapter_name") or (
                    ad.get("targetip") or ""
                ) == bridge.get("target_ip"):
                    for mod in ad.get("modules") or []:
                        if int(mod.get("slot") or -1) == int(chosen.get("slot") or -2):
                            eipcfg_mod = mod
                            break
        enriched.append(
            {
                **row,
                "direction": direction,
                "eipmodules_candidates": [
                    {
                        "adapter": c.get("adapter"),
                        "type": c.get("type"),
                        "slot": c.get("slot"),
                        "input_bank": c.get("input_bank"),
                        "output_bank": c.get("output_bank"),
                    }
                    for c in cands
                ],
                "chosen_module": (
                    {
                        "adapter": chosen.get("adapter"),
                        "type": chosen.get("type"),
                        "slot": chosen.get("slot"),
                        "input_bank": chosen.get("input_bank"),
                        "output_bank": chosen.get("output_bank"),
                    }
                    if chosen
                    else None
                ),
                "ambiguous_module": ambiguous,
                "adapter_bridge": bridge,
                "eipcfg_module": (
                    {
                        "name": eipcfg_mod.get("name"),
                        "type": eipcfg_mod.get("type"),
                        "slot": eipcfg_mod.get("slot"),
                        "data_index": eipcfg_mod.get("data_index"),
                    }
                    if eipcfg_mod
                    else None
                ),
            }
        )

    # numeric_token correlations
    n = len(enriched)
    def _agree(pred) -> tuple[int, int]:
        ok = sum(1 for r in enriched if pred(r))
        return ok, n

    slot_agree, _ = _agree(
        lambda r: r.get("chosen_module")
        and int(r["chosen_module"]["slot"]) == int(r["numeric_token"])
    )
    # Flex data_index = slot-1
    di_agree, _ = _agree(
        lambda r: r.get("chosen_module")
        and int(r["chosen_module"]["slot"]) - 1 == int(r["numeric_token"])
    )
    bank_agree, _ = _agree(
        lambda r: r.get("bank") is not None
        and int(float(str(r["bank"]))) == int(r["numeric_token"])
    )
    name_suffix_agree, _ = _agree(
        lambda r: r.get("chosen_module")
        and str(r["chosen_module"].get("type") or "")
        and str(r["numeric_token"])
        in str(
            (r.get("eipcfg_module") or {}).get("name")
            or r["chosen_module"].get("adapter")
            or ""
        )
    )

    # A/B pairs: same panel+catalog+numeric
    pairs: dict[tuple, dict[str, Any]] = {}
    for r in enriched:
        key = (r["panel"], r["catalog"], r["numeric_token"])
        pairs.setdefault(key, {})[r["alpha_suffix"]] = r

    pair_analysis = []
    same_module = 0
    diff_module = 0
    lohi_agree = 0
    pair_count = 0
    for key, sides in sorted(pairs.items()):
        if "A" not in sides or "B" not in sides:
            continue
        pair_count += 1
        a, b = sides["A"], sides["B"]
        a_mod = a.get("chosen_module") or {}
        b_mod = b.get("chosen_module") or {}
        same = (
            a_mod
            and b_mod
            and a_mod.get("adapter") == b_mod.get("adapter")
            and a_mod.get("slot") == b_mod.get("slot")
            and a_mod.get("type") == b_mod.get("type")
        )
        if same:
            same_module += 1
        elif a_mod and b_mod:
            diff_module += 1
        lohi_match = (
            (a.get("lohi") or "").lower().startswith("l")
            and (b.get("lohi") or "").lower().startswith("h")
        ) or (
            (a.get("lohi") or "").lower().startswith("h")
            and (b.get("lohi") or "").lower().startswith("l")
        )
        if lohi_match and (a.get("lohi") or "").lower().startswith("l"):
            lohi_agree += 1
        # also accept A=Low B=High specifically
        if (a.get("lohi") or "").lower().startswith("l") and (b.get("lohi") or "").lower().startswith("h"):
            pass  # counted above
        pair_analysis.append(
            {
                "key": {"panel": key[0], "catalog": key[1], "numeric": key[2]},
                "A": {
                    "desc": a["desc"],
                    "word": a.get("octal_word"),
                    "bank": a.get("bank"),
                    "lohi": a.get("lohi"),
                    "module": a_mod,
                },
                "B": {
                    "desc": b["desc"],
                    "word": b.get("octal_word"),
                    "bank": b.get("bank"),
                    "lohi": b.get("lohi"),
                    "module": b_mod,
                },
                "same_physical_module": bool(same),
                "A_is_Low_B_High": (
                    (a.get("lohi") or "").lower().startswith("l")
                    and (b.get("lohi") or "").lower().startswith("h")
                ),
            }
        )

    # per-catalog
    by_cat: dict[str, list] = defaultdict(list)
    for p in pair_analysis:
        by_cat[p["key"]["catalog"]].append(p)
    catalog_summary = {}
    for cat, plist in sorted(by_cat.items()):
        catalog_summary[cat] = {
            "pair_count": len(plist),
            "same_module": sum(1 for p in plist if p["same_physical_module"]),
            "diff_module": sum(1 for p in plist if not p["same_physical_module"]),
            "A_Low_B_High": sum(1 for p in plist if p["A_is_Low_B_High"]),
            "examples": [p["A"]["desc"] + " / " + p["B"]["desc"] for p in plist[:5]],
        }

    numeric_semantics = {
        "physical_slot": {"agree": slot_agree, "n": n, "rate": slot_agree / n if n else 0},
        "data_index_slot_minus_1": {"agree": di_agree, "n": n, "rate": di_agree / n if n else 0},
        "configio_bank": {"agree": bank_agree, "n": n, "rate": bank_agree / n if n else 0},
    }
    # pick best if rate >= 0.9
    best_num = max(numeric_semantics.items(), key=lambda kv: kv[1]["rate"])
    numeric_conclusion = (
        best_num[0]
        if best_num[1]["rate"] >= 0.9
        else "UNPROVEN / NONE_OF_THE_ABOVE_STRONG"
    )

    alpha_conclusion = "UNPROVEN"
    if pair_count and lohi_agree == pair_count:
        alpha_conclusion = "A=Low / B=High on Configio.LoHi (same structural pair)"
    elif pair_count and same_module == pair_count:
        alpha_conclusion = "A/B share same physical module; LoHi relationship incomplete"
    elif pair_count and diff_module == pair_count:
        alpha_conclusion = "A/B map to DIFFERENT physical modules"

    return {
        "row_count": n,
        "enriched_rows": enriched,
        "numeric_token_correlations": numeric_semantics,
        "numeric_token_conclusion": numeric_conclusion,
        "ab_pair_count": pair_count,
        "ab_same_physical_module": same_module,
        "ab_different_physical_module": diff_module,
        "ab_A_Low_B_High_count": sum(1 for p in pair_analysis if p["A_is_Low_B_High"]),
        "alpha_suffix_conclusion": alpha_conclusion,
        "catalog_specific": catalog_summary,
        "pairs": pair_analysis,
        "proven_enough_for_production": bool(
            numeric_conclusion not in {"UNPROVEN / NONE_OF_THE_ABOVE_STRONG"}
            and alpha_conclusion not in {"UNPROVEN"}
            and pair_count > 0
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--roots",
        nargs="+",
        default=[],
        help="Corpus roots (or use config/local_corpus_roots.txt)",
    )
    ap.add_argument("--out", default=str(ROOT / "exports/learning/investigations/CP8_ALPHA_DIALECT"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    roots: list[Path] = [Path(r) for r in args.roots if Path(r).is_dir()]
    local = ROOT / "config" / "local_corpus_roots.txt"
    if local.is_file():
        for line in local.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and Path(line).is_dir():
                roots.append(Path(line))
    # also peeks / extracts
    for p in [
        ROOT / "exports/learning/_extract",
        ROOT / "workspace/inbox",
        ROOT / "workspace/_mscatl_peek",
    ]:
        if p.is_dir():
            roots.append(p)
    roots = list({str(p.resolve()): p.resolve() for p in roots}.values())

    archive_hits = _find_matching_archives(roots)
    cross_corpus = [
        {"archive": str(t), "sample_count": len(s), "samples": s[:15]}
        for t, s in archive_hits
    ]

    # Extract first hit with most samples for deep dossier
    dossiers = []
    extract_root = out / "_runs"
    for tar, samples in sorted(archive_hits, key=lambda x: -len(x[1]))[:5]:
        dest = extract_root / tar.stem
        run = _extract_run_from_tar(tar, dest)
        if not run:
            continue
        # machine from project.cfg
        machine = ""
        cfg = run / "project.cfg"
        if cfg.is_file():
            for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
                if "MACHINE" in line.upper() and "=" in line:
                    machine = line.split("=", 1)[1].strip()
                    break
        rows = _load_configio(run)
        if not rows:
            continue
        corr = _correlate(run, machine, rows)
        dossiers.append(
            {
                "archive": tar.name,
                "run": str(run),
                "machine": machine,
                "sample_descs": samples[:20],
                **{k: v for k, v in corr.items() if k != "enriched_rows"},
                "enriched_row_count": corr.get("row_count"),
                "enriched_rows_sample": (corr.get("enriched_rows") or [])[:30],
            }
        )

    # Aggregate conclusions
    all_proven = all(d.get("proven_enough_for_production") for d in dossiers) if dossiers else False
    unresolved = not all_proven

    dossier_doc = {
        "kind": "PANEL_CATALOG_NUMERIC_ALPHA_dossier",
        "form": FORM_PANEL_CATALOG_NUMERIC_ALPHA,
        "generated_at": _ts(),
        "live_api_called": False,
        "cross_corpus_occurrences": cross_corpus,
        "controllers_with_form": len(archive_hits),
        "dossiers": dossiers,
        "shadow_only": True,
        "production_resolver_modified": False,
    }
    (out / "dossier.json").write_text(json.dumps(dossier_doc, indent=2), encoding="utf-8")

    # Human summary
    lines = [
        "PANEL_CATALOG_NUMERIC_ALPHA DOSSIER (shadow)",
        f"generated: {_ts()}",
        f"cross-corpus archives with form: {len(archive_hits)}",
        "",
    ]
    for d in dossiers:
        lines.append(f"=== {d.get('machine') or d.get('archive')} ===")
        lines.append(f"  rows={d.get('enriched_row_count')} pairs={d.get('ab_pair_count')}")
        lines.append(f"  numeric_conclusion: {d.get('numeric_token_conclusion')}")
        lines.append(f"  numeric_correlations: {d.get('numeric_token_correlations')}")
        lines.append(f"  alpha_conclusion: {d.get('alpha_suffix_conclusion')}")
        lines.append(f"  same_module={d.get('ab_same_physical_module')} diff_module={d.get('ab_different_physical_module')}")
        lines.append(f"  catalog_specific: {d.get('catalog_specific')}")
        lines.append("")
    (out / "dossier.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if unresolved:
        # Blind packet — current-site evidence, NO suspected answer
        examples = []
        for d in dossiers:
            for row in (d.get("enriched_rows_sample") or [])[:8]:
                examples.append(
                    {
                        "desc": row.get("desc"),
                        "bank": row.get("bank"),
                        "octal_word": row.get("octal_word"),
                        "lohi": row.get("lohi"),
                        "in_out": row.get("in_out"),
                        "interface": row.get("interface"),
                        "catalog": row.get("catalog"),
                        "panel": row.get("panel"),
                        "numeric_token": row.get("numeric_token"),
                        "alpha_suffix": row.get("alpha_suffix"),
                        "eipmodules_candidates": row.get("eipmodules_candidates"),
                        "adapter_bridge": row.get("adapter_bridge"),
                        "eipcfg_module": row.get("eipcfg_module"),
                    }
                )
        blind = {
            "kind": "decoder_investigator_blind_packet",
            "investigation_id": "CP8_ALPHA_DIALECT",
            "generated_at": _ts(),
            "question": (
                "For Configio Desc values matching panel-catalog-numeric-alpha "
                "(e.g. PANEL-1794-IA16-1A / …-1B), what do the numeric token and "
                "A/B suffix mean relative to EIPModules banks/slots and Configio "
                "LoHi/Bank/Octal_Word? Do A and B refer to the same physical module?"
            ),
            "constraints": [
                "Use only provided current-site evidence",
                "Do not invent site-specific rules",
                "Do not use finished/reference L5X",
                "Separate numeric_token semantics from A/B semantics",
                "Test catalogs independently (IA16 vs OA8I vs OB16P)",
            ],
            "evidence_rows": examples,
            "cross_corpus_archive_count": len(archive_hits),
            # Explicitly omit suspected answers / conclusions
        }
        (out / "blind_packet.json").write_text(json.dumps(blind, indent=2), encoding="utf-8")
        print(json.dumps({"unresolved": True, "blind_packet": str(out / "blind_packet.json"), "archives": len(archive_hits), "dossiers": len(dossiers)}, indent=2))
    else:
        print(json.dumps({"unresolved": False, "dossiers": len(dossiers), "path": str(out / "dossier.json")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

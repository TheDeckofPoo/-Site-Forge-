#!/usr/bin/env python3
"""Structural L5X comparison / Autogen backtest harness.

Compares meaningful PLC engineering structures between a Site Forge
*generated* L5X and an engineered *reference* L5X.

This is NOT a byte-for-byte XML diff. Dates, metadata, AOI definitions,
ordering noise, and unrelated manual programs do not dominate scoring.

Greensboro is the first known-answer fixture only — no hardcoded P-numbers,
area names, equipment counts, or merge counts in comparison logic.

Usage:
  python fortna_l5x_compare.py \\
    --generated path/to/generated.L5X \\
    --reference path/to/finished.L5X \\
    --out exports/l5x-backtest/greensboro
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_CALL_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _call_re(aoi: str) -> re.Pattern[str]:
    if aoi not in _CALL_RE_CACHE:
        # Non-greedy until matching close paren; args do not nest parens in these AOIs
        _CALL_RE_CACHE[aoi] = re.compile(rf"\b{re.escape(aoi)}\(([^)]*)\)")
    return _CALL_RE_CACHE[aoi]


def _split_args(arg_blob: str) -> list[str]:
    return [a.strip() for a in (arg_blob or "").split(",")]


def _conv_tag_from_udt(token: str) -> str:
    """P138_Conv / P138A_Conv → P138 / P138A; NO_Conv → NO_CONV."""
    t = (token or "").strip()
    if not t:
        return ""
    if t.upper() == "NO_CONV":
        return "NO_CONV"
    m = re.match(r"^(P\d+[A-Za-z0-9]*)_Conv$", t, re.I)
    if m:
        body = m.group(1)
        return "P" + body[1:]
    if re.match(r"^P\d+[A-Za-z0-9]*$", t, re.I):
        return "P" + t[1:]
    return t


def _norm_pe(token: str) -> str:
    t = (token or "").strip()
    if not t:
        return ""
    if t.upper() == "NO_PE":
        return "NO_PE"
    return t


def _norm_downstream(token: str) -> str:
    t = _conv_tag_from_udt(token)
    if t.upper() == "NO_CONV":
        return "NO_CONV"
    return t


def _area_from_program(program: str) -> str:
    """Heuristic: ModuleB_Area_Area_Fast → ModuleB_Area; ORNCCP2_Area_Fast → ORNCCP2_Area."""
    p = program or ""
    for suffix in (
        "_Area_Fast",
        "_Area_Slow",
        "_Area_L1",
        "_Area_L2",
        "_Area_L3",
        "_Fast",
        "_Slow",
        "_L1",
        "_L2",
        "_L3",
    ):
        # Finished PLC uses ModuleB_Area_Area_Fast
        if p.endswith("_Area" + suffix.replace("_Area", "")):
            pass
    if re.search(r"_Area_Area_(Fast|Slow|L\d)$", p):
        return re.sub(r"_Area_(Fast|Slow|L\d)$", "", p)
    if re.search(r"_Area_(Fast|Slow|L\d)$", p):
        return re.sub(r"_(Fast|Slow|L\d)$", "", p)
    return p


def _classify_program(name: str) -> str:
    n = name or ""
    nu = n.upper()
    if nu in {"SYS", "SYSTEM"}:
        return "system"
    if nu == "IO_MAP" or nu.endswith("_IO_MAP"):
        return "io_map"
    if re.search(r"_Area_Area_Fast$|_Area_Fast$", n):
        return "area_fast"
    if re.search(r"_Area_Area_Slow$|_Area_Slow$", n):
        return "area_slow"
    if re.search(r"_Area_Area_L2$|_Area_L2$", n):
        return "area_l2"
    if re.search(r"_Area_Area_L3$|_Area_L3$", n):
        return "area_l3"
    if re.search(r"_Area_Area_L1$|_Area_L1$", n):
        return "area_l1"
    return "other"


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

@dataclass
class FastConvRecord:
    conveyor: str
    program: str
    area: str
    safety_zone: str
    downstream: str
    exit_pe: str
    add_pe: str
    type_arg: str
    vfd: str
    raw_args: list[str] = field(default_factory=list)


@dataclass
class SlowFltRecord:
    conveyor: str
    program: str
    area: str
    vfd: str
    encoder: str
    ms: str
    raw_args: list[str] = field(default_factory=list)


@dataclass
class SlowJamRecord:
    conveyor: str
    program: str
    area: str
    jam_pes: list[str] = field(default_factory=list)
    raw_args: list[str] = field(default_factory=list)


@dataclass
class FullPeRecord:
    pe_tag: str
    conveyor: str
    program: str
    arg_a: str = ""
    arg_b: str = ""
    raw_args: list[str] = field(default_factory=list)


@dataclass
class Merge2to1Record:
    name: str
    lane_a: str
    lane_b: str
    discharge: str
    pe_a: str
    pe_b: str
    jam_pe: str
    hold_mode: str
    program: str = ""
    raw_args: list[str] = field(default_factory=list)


@dataclass
class L5XInventory:
    path: str
    programs: list[str]
    program_classes: dict[str, str]
    fast_conv: dict[str, FastConvRecord]
    slow_flt: dict[str, SlowFltRecord]
    slow_jam: dict[str, SlowJamRecord]
    full_pe: list[FullPeRecord]
    merges_2to1: dict[str, Merge2to1Record]


def _iter_program_spans(text: str) -> list[tuple[str, int, int]]:
    """Return (program_name, start, end) spans covering each <Program>...</Program>."""
    opens = list(re.finditer(r"<Program\b([^>]*)>", text, re.I))
    spans: list[tuple[str, int, int]] = []
    for i, m in enumerate(opens):
        attrs = m.group(1) or ""
        nm = re.search(r'\bName="([^"]+)"', attrs)
        name = nm.group(1) if nm else f"Program_{i}"
        start = m.end()
        # Find matching close — L5X programs are not deeply nested with other Programs
        close = re.search(r"</Program>", text[start:], re.I)
        end = start + close.start() if close else len(text)
        spans.append((name, start, end))
    return spans


def _program_at(spans: list[tuple[str, int, int]], pos: int) -> str:
    for name, start, end in spans:
        if start <= pos < end:
            return name
    return ""


def extract_l5x(path: Path | str) -> L5XInventory:
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    spans = _iter_program_spans(text)
    programs = [n for n, _, _ in spans]
    program_classes = {n: _classify_program(n) for n in programs}

    fast: dict[str, FastConvRecord] = {}
    for m in _call_re("Fast_Conv").finditer(text):
        args = _split_args(m.group(1))
        if len(args) < 9:
            continue
        conv = _conv_tag_from_udt(args[1])
        if not conv or conv.upper() == "NO_CONV":
            continue
        prog = _program_at(spans, m.start())
        rec = FastConvRecord(
            conveyor=conv,
            program=prog,
            area=(args[2] or "").strip(),
            safety_zone=(args[3] or "").strip(),
            downstream=_norm_downstream(args[4]),
            exit_pe=_norm_pe(args[5]),
            add_pe=_norm_pe(args[6]),
            type_arg=(args[7] or "").strip(),
            vfd=(args[8] or "").strip(),
            raw_args=args,
        )
        # Last wins if duplicated (should be rare)
        fast[conv.upper()] = rec

    slow_flt: dict[str, SlowFltRecord] = {}
    for m in _call_re("Slow_Flt").finditer(text):
        args = _split_args(m.group(1))
        if len(args) < 7:
            continue
        conv = _conv_tag_from_udt(args[1])
        if not conv:
            continue
        prog = _program_at(spans, m.start())
        slow_flt[conv.upper()] = SlowFltRecord(
            conveyor=conv,
            program=prog,
            area=(args[2] or "").strip(),
            vfd=(args[3] or "").strip(),
            encoder=(args[4] or "").strip() if len(args) > 4 else "",
            ms=(args[6] or "").strip() if len(args) > 6 else "",
            raw_args=args,
        )

    slow_jam: dict[str, SlowJamRecord] = {}
    for m in _call_re("Slow_Jam").finditer(text):
        args = _split_args(m.group(1))
        if len(args) < 4:
            continue
        conv = _conv_tag_from_udt(args[1])
        if not conv:
            continue
        prog = _program_at(spans, m.start())
        pes = [_norm_pe(a) for a in args[3:] if str(a).strip()]
        real = [p for p in pes if p and p != "NO_PE"]
        jam_pes = real if real else ["NO_PE"]
        slow_jam[conv.upper()] = SlowJamRecord(
            conveyor=conv,
            program=prog,
            area=(args[2] or "").strip(),
            jam_pes=jam_pes,
            raw_args=args,
        )

    full_pe: list[FullPeRecord] = []
    for m in _call_re("Full_PE").finditer(text):
        args = _split_args(m.group(1))
        if len(args) < 3:
            continue
        pe = (args[1] or "").strip()
        conv = _conv_tag_from_udt(args[2])
        prog = _program_at(spans, m.start())
        full_pe.append(
            FullPeRecord(
                pe_tag=pe,
                conveyor=conv,
                program=prog,
                arg_a=(args[3] if len(args) > 3 else "").strip(),
                arg_b=(args[4] if len(args) > 4 else "").strip(),
                raw_args=args,
            )
        )

    merges: dict[str, Merge2to1Record] = {}
    for m in _call_re("Merge_2to1").finditer(text):
        args = _split_args(m.group(1))
        if len(args) < 11:
            continue
        prog = _program_at(spans, m.start())
        # Signature observed in Site Forge transport L5X:
        # 0 name, 1 lane_a, 2 lane_b, 3 discharge, 4 ?, 5 ?, 6, 7,
        # 8 pe_a, 9 pe_b, 10 jam_pe, ... RunHold tags near end
        name_tok = (args[0] or "").strip()
        name = re.sub(r"_Merge$", "", name_tok, flags=re.I) or name_tok
        hold = "runhold" if any("RunHold" in a for a in args) else ""
        if any(re.search(r"hold", a, re.I) and "RunHold" not in a for a in args):
            # leave runhold if RunHold present; else unknown
            pass
        rec = Merge2to1Record(
            name=name,
            lane_a=_conv_tag_from_udt(args[1]),
            lane_b=_conv_tag_from_udt(args[2]),
            discharge=_conv_tag_from_udt(args[3]),
            pe_a=_norm_pe(args[8] if len(args) > 8 else ""),
            pe_b=_norm_pe(args[9] if len(args) > 9 else ""),
            jam_pe=_norm_pe(args[10] if len(args) > 10 else ""),
            hold_mode=hold or "unknown",
            program=prog,
            raw_args=args,
        )
        key = (rec.discharge or rec.name or name).upper()
        merges[key] = rec

    # Rebuild fast dict with original casing keys via conveyor field
    fast_out = {r.conveyor.upper(): r for r in fast.values()}
    return L5XInventory(
        path=str(p),
        programs=programs,
        program_classes=program_classes,
        fast_conv=fast_out,
        slow_flt={k: v for k, v in slow_flt.items()},
        slow_jam={k: v for k, v in slow_jam.items()},
        full_pe=full_pe,
        merges_2to1=merges,
    )


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

DIFF_MISSING_GENERATED = "MISSING_GENERATED"
DIFF_EXTRA_GENERATED = "EXTRA_GENERATED"
DIFF_TOPOLOGY = "TOPOLOGY_MISMATCH"
DIFF_AREA = "AREA_MISMATCH"
DIFF_SAFETY = "SAFETY_MISMATCH"
DIFF_PE = "PE_MISMATCH"
DIFF_MERGE = "MERGE_MISMATCH"
DIFF_PROGRAM = "PROGRAM_STRUCTURE_DIFFERENCE"
DIFF_OTHER = "ARGUMENT_DIFFERENCE"


def _pct(num: int, den: int) -> float:
    if den <= 0:
        return 0.0
    return round(100.0 * num / den, 1)


def _field_cmp(gen_val: str, ref_val: str) -> dict[str, Any]:
    g = (gen_val or "").strip()
    r = (ref_val or "").strip()
    # Treat empty and NO_CONV as equivalent terminals for downstream
    def canon(v: str) -> str:
        u = v.upper()
        if u in {"", "NO_CONV"}:
            return "NO_CONV"
        return v

    match = canon(g) == canon(r) or g == r
    return {
        "status": "MATCH" if match else "MISMATCH",
        "generated": g,
        "reference": r,
    }


def compare_inventories(generated: L5XInventory, reference: L5XInventory) -> dict[str, Any]:
    gen_fc = generated.fast_conv
    ref_fc = reference.fast_conv
    gen_keys = set(gen_fc)
    ref_keys = set(ref_fc)

    matched = sorted(gen_keys & ref_keys)
    missing = sorted(ref_keys - gen_keys)  # in reference, not generated
    extra = sorted(gen_keys - ref_keys)  # in generated, not reference

    conveyor_diffs: list[dict[str, Any]] = []
    ds_ok = area_ok = safety_ok = exit_ok = 0
    classifications: list[str] = []

    for k in missing:
        r = ref_fc[k]
        conveyor_diffs.append(
            {
                "conveyor": r.conveyor,
                "classification": DIFF_MISSING_GENERATED,
                "fields": {
                    "area": {"status": "MISSING", "generated": None, "reference": r.area},
                    "safety_zone": {"status": "MISSING", "generated": None, "reference": r.safety_zone},
                    "downstream": {"status": "MISSING", "generated": None, "reference": r.downstream},
                    "exit_pe": {"status": "MISSING", "generated": None, "reference": r.exit_pe},
                },
            }
        )
        classifications.append(DIFF_MISSING_GENERATED)

    for k in extra:
        g = gen_fc[k]
        conveyor_diffs.append(
            {
                "conveyor": g.conveyor,
                "classification": DIFF_EXTRA_GENERATED,
                "fields": {
                    "area": {"status": "EXTRA", "generated": g.area, "reference": None},
                    "safety_zone": {"status": "EXTRA", "generated": g.safety_zone, "reference": None},
                    "downstream": {"status": "EXTRA", "generated": g.downstream, "reference": None},
                    "exit_pe": {"status": "EXTRA", "generated": g.exit_pe, "reference": None},
                },
            }
        )
        classifications.append(DIFF_EXTRA_GENERATED)

    for k in matched:
        g, r = gen_fc[k], ref_fc[k]
        fields = {
            "area": _field_cmp(g.area, r.area),
            "safety_zone": _field_cmp(g.safety_zone, r.safety_zone),
            "downstream": _field_cmp(g.downstream, r.downstream),
            "exit_pe": _field_cmp(g.exit_pe, r.exit_pe),
            "add_pe": _field_cmp(g.add_pe, r.add_pe),
            "program": _field_cmp(g.program, r.program),
        }
        if fields["downstream"]["status"] == "MATCH":
            ds_ok += 1
        else:
            classifications.append(DIFF_TOPOLOGY)
        if fields["area"]["status"] == "MATCH":
            area_ok += 1
        else:
            classifications.append(DIFF_AREA)
        if fields["safety_zone"]["status"] == "MATCH":
            safety_ok += 1
        else:
            classifications.append(DIFF_SAFETY)
        if fields["exit_pe"]["status"] == "MATCH":
            exit_ok += 1
        else:
            classifications.append(DIFF_PE)

        class_set = []
        if fields["downstream"]["status"] != "MATCH":
            class_set.append(DIFF_TOPOLOGY)
        if fields["area"]["status"] != "MATCH":
            class_set.append(DIFF_AREA)
        if fields["safety_zone"]["status"] != "MATCH":
            class_set.append(DIFF_SAFETY)
        if fields["exit_pe"]["status"] != "MATCH":
            class_set.append(DIFF_PE)
        conveyor_diffs.append(
            {
                "conveyor": r.conveyor,
                "classification": class_set[0] if class_set else "MATCH",
                "classifications": class_set,
                "fields": fields,
                "generated_program": g.program,
                "reference_program": r.program,
            }
        )

    # Slow_Flt
    gen_sf, ref_sf = set(generated.slow_flt), set(reference.slow_flt)
    slow_flt = {
        "generated_count": len(gen_sf),
        "reference_count": len(ref_sf),
        "matched": sorted(gen_sf & ref_sf),
        "missing": sorted(ref_sf - gen_sf),
        "extra": sorted(gen_sf - ref_sf),
        "argument_diffs": [],
    }
    for k in sorted(gen_sf & ref_sf):
        g, r = generated.slow_flt[k], reference.slow_flt[k]
        diffs = {}
        if g.area != r.area:
            diffs["area"] = {"generated": g.area, "reference": r.area}
        if g.vfd != r.vfd:
            diffs["vfd"] = {"generated": g.vfd, "reference": r.vfd}
        if g.ms != r.ms:
            diffs["ms"] = {"generated": g.ms, "reference": r.ms}
        if diffs:
            slow_flt["argument_diffs"].append({"conveyor": r.conveyor, "diffs": diffs})

    # Slow_Jam
    gen_sj, ref_sj = set(generated.slow_jam), set(reference.slow_jam)
    jam_match = 0
    jam_diffs = []
    for k in sorted(gen_sj & ref_sj):
        g, r = generated.slow_jam[k], reference.slow_jam[k]
        if g.jam_pes == r.jam_pes:
            jam_match += 1
        else:
            jam_diffs.append(
                {
                    "conveyor": r.conveyor,
                    "classification": DIFF_PE,
                    "generated": g.jam_pes,
                    "reference": r.jam_pes,
                }
            )
            classifications.append(DIFF_PE)
    slow_jam = {
        "generated_count": len(gen_sj),
        "reference_count": len(ref_sj),
        "matched_conveyors": sorted(gen_sj & ref_sj),
        "missing": sorted(ref_sj - gen_sj),
        "extra": sorted(gen_sj - ref_sj),
        "jam_config_matches": jam_match,
        "jam_config_mismatches": jam_diffs,
    }

    # Full_PE — key by pe_tag
    def _fp_key(fp: FullPeRecord) -> str:
        return f"{fp.pe_tag.upper()}|{fp.conveyor.upper()}"

    gen_fp = {_fp_key(x): x for x in generated.full_pe}
    ref_fp = {_fp_key(x): x for x in reference.full_pe}
    # Also allow match by PE tag alone
    gen_pe_tags = {x.pe_tag.upper(): x for x in generated.full_pe}
    ref_pe_tags = {x.pe_tag.upper(): x for x in reference.full_pe}
    fp_matched_tags = sorted(set(gen_pe_tags) & set(ref_pe_tags))
    full_pe = {
        "generated_count": len(generated.full_pe),
        "reference_count": len(reference.full_pe),
        "matched_pe_tags": fp_matched_tags,
        "missing_pe_tags": sorted(set(ref_pe_tags) - set(gen_pe_tags)),
        "extra_pe_tags": sorted(set(gen_pe_tags) - set(ref_pe_tags)),
        "conveyor_mismatches": [],
    }
    for tag in fp_matched_tags:
        g, r = gen_pe_tags[tag], ref_pe_tags[tag]
        if g.conveyor.upper() != r.conveyor.upper():
            full_pe["conveyor_mismatches"].append(
                {
                    "pe_tag": tag,
                    "generated_conveyor": g.conveyor,
                    "reference_conveyor": r.conveyor,
                    "classification": DIFF_PE,
                }
            )

    # Merges
    gen_m, ref_m = generated.merges_2to1, reference.merges_2to1
    merge_diffs = []
    for k in sorted(set(ref_m) - set(gen_m)):
        merge_diffs.append(
            {
                "key": k,
                "classification": DIFF_MISSING_GENERATED,
                "reference": asdict(ref_m[k]),
                "generated": None,
            }
        )
        classifications.append(DIFF_MERGE)
    for k in sorted(set(gen_m) - set(ref_m)):
        merge_diffs.append(
            {
                "key": k,
                "classification": DIFF_EXTRA_GENERATED,
                "generated": asdict(gen_m[k]),
                "reference": None,
            }
        )
        classifications.append(DIFF_MERGE)
    merge_field_ok = 0
    merge_pair = 0
    for k in sorted(set(gen_m) & set(ref_m)):
        merge_pair += 1
        g, r = gen_m[k], ref_m[k]
        fields = {
            "lane_a": _field_cmp(g.lane_a, r.lane_a),
            "lane_b": _field_cmp(g.lane_b, r.lane_b),
            "discharge": _field_cmp(g.discharge, r.discharge),
            "pe_a": _field_cmp(g.pe_a, r.pe_a),
            "pe_b": _field_cmp(g.pe_b, r.pe_b),
            "jam_pe": _field_cmp(g.jam_pe, r.jam_pe),
            "hold_mode": _field_cmp(g.hold_mode, r.hold_mode),
        }
        bad = [f for f, v in fields.items() if v["status"] != "MATCH"]
        if not bad:
            merge_field_ok += 1
        else:
            classifications.append(DIFF_MERGE)
        merge_diffs.append(
            {
                "key": k,
                "classification": DIFF_MERGE if bad else "MATCH",
                "fields": fields,
            }
        )

    # Programs
    gen_prog = set(generated.programs)
    ref_prog = set(reference.programs)
    program_rows = []
    for name in sorted(gen_prog | ref_prog):
        if name in gen_prog and name in ref_prog:
            status = "MATCH"
        elif name in ref_prog:
            status = "MISSING"
            classifications.append(DIFF_PROGRAM)
        else:
            status = "EXTRA"
            classifications.append(DIFF_PROGRAM)
        program_rows.append(
            {
                "program": name,
                "status": status,
                "generated_class": generated.program_classes.get(name),
                "reference_class": reference.program_classes.get(name),
            }
        )

    n_ref = len(ref_keys)
    n_gen = len(gen_keys)
    n_pair = len(matched)

    metrics = {
        "conveyor_coverage": {
            "matched": n_pair,
            "reference": n_ref,
            "generated": n_gen,
            "pct_of_reference": _pct(n_pair, n_ref),
        },
        "downstream_accuracy": {
            "correct": ds_ok,
            "compared": n_pair,
            "pct": _pct(ds_ok, n_pair),
        },
        "area_accuracy": {
            "correct": area_ok,
            "compared": n_pair,
            "pct": _pct(area_ok, n_pair),
        },
        "safety_zone_accuracy": {
            "correct": safety_ok,
            "compared": n_pair,
            "pct": _pct(safety_ok, n_pair),
        },
        "exit_pe_accuracy": {
            "correct": exit_ok,
            "compared": n_pair,
            "pct": _pct(exit_ok, n_pair),
        },
        "fast_conv_coverage": {"generated": n_gen, "reference": n_ref, "matched": n_pair},
        "slow_flt_coverage": {
            "generated": len(gen_sf),
            "reference": len(ref_sf),
            "matched": len(gen_sf & ref_sf),
        },
        "slow_jam_coverage": {
            "generated": len(gen_sj),
            "reference": len(ref_sj),
            "matched": len(gen_sj & ref_sj),
            "jam_config_matches": jam_match,
        },
        "full_pe_coverage": {
            "generated": len(generated.full_pe),
            "reference": len(reference.full_pe),
            "matched_pe_tags": len(fp_matched_tags),
        },
        "merge_2to1_coverage": {
            "generated": len(gen_m),
            "reference": len(ref_m),
            "matched_keys": merge_pair,
            "field_matches": merge_field_ok,
        },
    }

    return {
        "generated_path": generated.path,
        "reference_path": reference.path,
        "metrics": metrics,
        "classification_counts": dict(Counter(classifications)),
        "conveyor": {
            "generated_count": n_gen,
            "reference_count": n_ref,
            "exact_matches": n_pair,
            "missing_conveyors": [ref_fc[k].conveyor for k in missing],
            "extra_conveyors": [gen_fc[k].conveyor for k in extra],
            "diffs": conveyor_diffs,
        },
        "slow_flt": slow_flt,
        "slow_jam": slow_jam,
        "full_pe": full_pe,
        "merges_2to1": {
            "generated_count": len(gen_m),
            "reference_count": len(ref_m),
            "diffs": merge_diffs,
        },
        "programs": program_rows,
        "note": (
            "No single overall accuracy is reported. Category metrics are independent. "
            "The reference PLC may be unfinished/manual; differences are classifications, not always errors."
        ),
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _md_escape(s: Any) -> str:
    return str(s).replace("|", "\\|")


def write_report(result: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    m = result["metrics"]

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_path": result["generated_path"],
        "reference_path": result["reference_path"],
        "metrics": m,
        "classification_counts": result["classification_counts"],
        "note": result["note"],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "conveyor_diff.json").write_text(
        json.dumps(result["conveyor"], indent=2), encoding="utf-8"
    )
    (out_dir / "merge_diff.json").write_text(
        json.dumps(result["merges_2to1"], indent=2), encoding="utf-8"
    )
    (out_dir / "full_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append("# Autogen L5X Structural Backtest")
    lines.append("")
    lines.append(f"- Generated: `{result['generated_path']}`")
    lines.append(f"- Reference: `{result['reference_path']}`")
    lines.append("")
    lines.append("## Summary metrics")
    lines.append("")
    lines.append("```")
    lines.append("AUTOGEN L5X BACKTEST")
    lines.append("")
    cc = m["conveyor_coverage"]
    lines.append(
        f"Conveyor coverage        {cc['matched']} / {cc['reference']}   {cc['pct_of_reference']}%"
    )
    d = m["downstream_accuracy"]
    lines.append(f"Downstream accuracy      {d['correct']} / {d['compared']}   {d['pct']}%")
    a = m["area_accuracy"]
    lines.append(f"Area accuracy            {a['correct']} / {a['compared']}   {a['pct']}%")
    s = m["safety_zone_accuracy"]
    lines.append(f"Safety-zone accuracy     {s['correct']} / {s['compared']}   {s['pct']}%")
    e = m["exit_pe_accuracy"]
    lines.append(f"Exit-PE accuracy         {e['correct']} / {e['compared']}   {e['pct']}%")
    lines.append("")
    f = m["fast_conv_coverage"]
    lines.append(f"Fast_Conv coverage       {f['matched']} / {f['reference']}  (gen {f['generated']})")
    sf = m["slow_flt_coverage"]
    lines.append(f"Slow_Flt coverage        {sf['matched']} / {sf['reference']}  (gen {sf['generated']})")
    sj = m["slow_jam_coverage"]
    lines.append(
        f"Slow_Jam coverage        {sj['matched']} / {sj['reference']}  "
        f"(jam cfg matches {sj['jam_config_matches']})"
    )
    fp = m["full_pe_coverage"]
    lines.append(
        f"Full_PE                  {fp['matched_pe_tags']} / {fp['reference']}  (gen {fp['generated']})"
    )
    mg = m["merge_2to1_coverage"]
    lines.append(
        f"Merge_2to1               {mg['matched_keys']} / {mg['reference']}  (gen {mg['generated']})"
    )
    lines.append("```")
    lines.append("")
    lines.append(result["note"])
    lines.append("")
    lines.append("## Classification counts")
    lines.append("")
    for k, v in sorted(result["classification_counts"].items()):
        lines.append(f"- `{k}`: {v}")
    lines.append("")

    conv = result["conveyor"]
    lines.append("## Conveyor inventory")
    lines.append("")
    lines.append(f"- Generated Fast_Conv conveyors: **{conv['generated_count']}**")
    lines.append(f"- Reference Fast_Conv conveyors: **{conv['reference_count']}**")
    lines.append(f"- Exact tag overlap: **{conv['exact_matches']}**")
    lines.append(f"- Missing (in reference only): {', '.join(conv['missing_conveyors']) or '—'}")
    lines.append(f"- Extra (in generated only): {', '.join(conv['extra_conveyors']) or '—'}")
    lines.append("")

    lines.append("## Per-conveyor differences (mismatches / missing / extra)")
    lines.append("")
    shown = 0
    for row in conv["diffs"]:
        fields = row.get("fields") or {}
        interesting = row.get("classification") != "MATCH" or any(
            (fields.get(f) or {}).get("status") not in {"MATCH", None} for f in fields
        )
        if row.get("classification") == "MATCH" and not any(
            (fields.get(f) or {}).get("status") == "MISMATCH" for f in fields
        ):
            continue
        shown += 1
        lines.append(f"### {row['conveyor']} — `{row.get('classification')}`")
        lines.append("")
        for fname, fval in fields.items():
            st = fval.get("status")
            if st == "MATCH":
                lines.append(f"- {fname:12} MATCH      `{fval.get('reference')}`")
            elif st == "MISMATCH":
                lines.append(f"- {fname:12} MISMATCH")
                lines.append(f"    - generated: `{fval.get('generated')}`")
                lines.append(f"    - reference: `{fval.get('reference')}`")
            else:
                lines.append(
                    f"- {fname:12} {st:8} gen=`{fval.get('generated')}` ref=`{fval.get('reference')}`"
                )
        lines.append("")
        if shown >= 80:
            lines.append("_…truncated for readability; see conveyor_diff.json for full list._")
            lines.append("")
            break

    lines.append("## Slow_Jam")
    lines.append("")
    sj = result["slow_jam"]
    lines.append(
        f"- Coverage: gen {sj['generated_count']} / ref {sj['reference_count']}; "
        f"jam config matches on overlap: {sj['jam_config_matches']}"
    )
    if sj["missing"]:
        lines.append(f"- Missing conveyors: {', '.join(sj['missing'])}")
    if sj["extra"]:
        lines.append(f"- Extra conveyors: {', '.join(sj['extra'])}")
    for d in sj["jam_config_mismatches"][:30]:
        lines.append(
            f"- {d['conveyor']}: gen={d['generated']} ref={d['reference']}"
        )
    lines.append("")

    lines.append("## Full_PE")
    lines.append("")
    fp = result["full_pe"]
    lines.append(
        f"- gen {fp['generated_count']} / ref {fp['reference_count']}; "
        f"matched PE tags {len(fp['matched_pe_tags'])}"
    )
    if fp["missing_pe_tags"]:
        lines.append(f"- Missing PEs: {', '.join(fp['missing_pe_tags'])}")
    if fp["extra_pe_tags"]:
        lines.append(f"- Extra PEs: {', '.join(fp['extra_pe_tags'])}")
    lines.append("")

    lines.append("## Merge_2to1")
    lines.append("")
    mg = result["merges_2to1"]
    lines.append(f"- Generated merges: {mg['generated_count']}")
    lines.append(f"- Reference merges: {mg['reference_count']}")
    if not mg["generated_count"] and not mg["reference_count"]:
        lines.append("- No Merge_2to1 call sites found in either L5X (not necessarily an error).")
    for d in mg["diffs"][:40]:
        lines.append(f"- `{d.get('key')}` — {d.get('classification')}")
    lines.append("")

    lines.append("## Programs")
    lines.append("")
    lines.append("| Program | Status | Gen class | Ref class |")
    lines.append("|---|---|---|---|")
    for row in result["programs"]:
        lines.append(
            f"| {_md_escape(row['program'])} | {row['status']} | "
            f"{row.get('generated_class') or '—'} | {row.get('reference_class') or '—'} |"
        )
    lines.append("")

    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def run_compare(generated: Path, reference: Path, out_dir: Path) -> dict[str, Any]:
    gen_inv = extract_l5x(generated)
    ref_inv = extract_l5x(reference)
    result = compare_inventories(gen_inv, ref_inv)
    write_report(result, out_dir)
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Structural L5X Autogen backtest comparator")
    ap.add_argument("--generated", required=True, help="Site Forge generated L5X")
    ap.add_argument("--reference", required=True, help="Engineered / finished reference L5X")
    ap.add_argument("--out", required=True, help="Output directory for reports")
    args = ap.parse_args(argv)

    gen = Path(args.generated)
    ref = Path(args.reference)
    out = Path(args.out)
    if not gen.is_file():
        print(f"ERROR: generated L5X not found: {gen}", file=sys.stderr)
        return 2
    if not ref.is_file():
        print(f"ERROR: reference L5X not found: {ref}", file=sys.stderr)
        return 2

    result = run_compare(gen, ref, out)
    m = result["metrics"]
    print("AUTOGEN L5X BACKTEST")
    print(
        f"Conveyor coverage   {m['conveyor_coverage']['matched']} / "
        f"{m['conveyor_coverage']['reference']}  {m['conveyor_coverage']['pct_of_reference']}%"
    )
    print(
        f"Downstream accuracy {m['downstream_accuracy']['correct']} / "
        f"{m['downstream_accuracy']['compared']}  {m['downstream_accuracy']['pct']}%"
    )
    print(
        f"Area accuracy       {m['area_accuracy']['correct']} / "
        f"{m['area_accuracy']['compared']}  {m['area_accuracy']['pct']}%"
    )
    print(
        f"Safety-zone accuracy {m['safety_zone_accuracy']['correct']} / "
        f"{m['safety_zone_accuracy']['compared']}  {m['safety_zone_accuracy']['pct']}%"
    )
    print(
        f"Exit-PE accuracy    {m['exit_pe_accuracy']['correct']} / "
        f"{m['exit_pe_accuracy']['compared']}  {m['exit_pe_accuracy']['pct']}%"
    )
    print(f"Report: {out / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

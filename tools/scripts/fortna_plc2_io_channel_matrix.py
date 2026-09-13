#!/usr/bin/env python3
"""PLC2 IO channel + transport device matrix (validation only).

Compares current generated L5X vs finished oracle IO_MAP / transport objects.
Finished PLC is VALIDATION ONLY — never a generation template.
Classifies differences; does not invent generation rules from finished.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import CONVEYOR_TYPES, read_asc  # noqa: E402
from fortna_controller_scope import build_controller_scope  # noqa: E402
from fortna_io_regression_baselines import _parse_iomap_mappings  # noqa: E402
from fortna_plc2_io_truth import (  # noqa: E402
    CHANNEL_RE,
    _is_placeholder_tag,
    _split_real_placeholder,
)
from fortna_site_model import write_json  # noqa: E402

MECH_TYPES = {t.upper() for t in CONVEYOR_TYPES} | {"ZEROPRESSURE", "ACCUMULATOR", "MDR"}
SKIP_IO = frozenset({"", "INVALID", "N/A", "SPARE", "NEVERON", "ALWAYSON", "NONE"})

CLASSIFICATIONS = (
    "EXACT",
    "SEMANTIC_EQUIVALENT",
    "FALSE_PLACEHOLDER",
    "SHOULD_BE_PLACEHOLDER",
    "WRONG_DEVICE",
    "WRONG_MEMBER",
    "WRONG_ADAPTER",
    "WRONG_SLOT",
    "WRONG_BIT",
    "WRONG_DIRECTION",
    "RUN_UNRESOLVED",
)

AUTOGEN_FALLBACK = ROOT / "exports" / "autogen" / "ORNCCP2__2026_09_13_1113.L5X"
SEMANTIC_FALLBACK = ROOT / "exports" / "plc2-semantic-graph" / "ORNCCP2.L5X"
FINISHED_DEFAULT = ROOT / "workspace" / "validation" / "ORLY_GreensboroPLC2_NC_Finished.L5X"
OUT_DEFAULT = ROOT / "exports" / "plc2-validation"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(v: Any) -> str:
    return str(v or "").strip()


def _norm_tag(tag: str) -> str:
    return _clean(tag).upper()


def _parse_channel(ch: str) -> dict[str, Any]:
    m = CHANNEL_RE.match(_clean(ch))
    if not m:
        return {"adapter": "", "direction": "", "data_index": None, "bit": None, "channel": ch}
    return {
        "adapter": m.group("adapter"),
        "direction": m.group("dir").upper(),
        "data_index": int(m.group("slot")),
        "bit": int(m.group("bit")),
        "channel": ch,
    }


def _split_device_member(tag: str) -> tuple[str, str]:
    t = _clean(tag)
    if "." not in t:
        return t, ""
    device, member = t.split(".", 1)
    return device, member


def resolve_current_l5x(explicit: Path | None = None) -> Path:
    """Prefer exports/current/*ORNCCP2*.L5X newest, else autogen stamp, else semantic-graph."""
    if explicit is not None:
        p = explicit if explicit.is_absolute() else ROOT / explicit
        if not p.is_file():
            raise FileNotFoundError(f"current L5X not found: {p}")
        return p

    current_dir = ROOT / "exports" / "current"
    if current_dir.is_dir():
        cands = sorted(
            [
                p
                for p in current_dir.glob("*ORNCCP2*.L5X")
                if p.is_file() and "Library" not in p.name
            ],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if cands:
            return cands[0]

    if AUTOGEN_FALLBACK.is_file():
        return AUTOGEN_FALLBACK
    if SEMANTIC_FALLBACK.is_file():
        return SEMANTIC_FALLBACK
    raise FileNotFoundError(
        "No current ORNCCP2 L5X under exports/current, "
        f"{AUTOGEN_FALLBACK.name}, or {SEMANTIC_FALLBACK}"
    )


def _module_catalog_by_adapter(text: str) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = defaultdict(list)
    for m in re.finditer(r"<Module\b([^>]*)>(.*?)</Module>", text, re.I | re.S):
        attrs = m.group(1)
        nm = re.search(r'\bName="([^"]+)"', attrs)
        cat = re.search(r'\bCatalogNumber="([^"]+)"', attrs)
        parent = re.search(r'\bParentModule="([^"]+)"', attrs)
        if not nm:
            continue
        name = nm.group(1)
        catalog = cat.group(1) if cat else ""
        if parent:
            out[parent.group(1)].append({"name": name, "catalog": catalog})
        else:
            out.setdefault(name, [])
    return dict(out)


def _module_for_channel(channel: str, modules_by_adapter: dict[str, list[dict]]) -> str:
    parsed = _parse_channel(channel)
    adapter = parsed.get("adapter") or ""
    idx = parsed.get("data_index")
    children = modules_by_adapter.get(adapter) or []
    if idx is None or not children:
        return ""
    for c in children:
        n = c.get("name") or ""
        m = re.search(r"_(\d+)$", n)
        if m and int(m.group(1)) == idx:
            return c.get("catalog") or n
    if 0 <= idx < len(children):
        c = children[idx]
        return c.get("catalog") or c.get("name") or ""
    return ""


def _l5x_tag_names(text: str) -> set[str]:
    return set(re.findall(r'\bName="([A-Za-z_][A-Za-z0-9_]*)"', text))


def _build_run_logical_index(run_dir: Path) -> dict[tuple[str, int], str]:
    """(channel, bit) is not available without physical resolve; index by word:bit → IO_Name."""
    path = run_dir / "FORTNA" / "Conveyor.asc"
    if not path.is_file():
        return {}
    _h, rows = read_asc(path)
    out: dict[tuple[str, int], str] = {}
    for r in rows:
        name = _clean(r.get("IO_Name"))
        if not name:
            continue
        try:
            word = str(int(float(r.get("IO_Address_Word") or 0)))
        except (TypeError, ValueError):
            continue
        bit_raw = _clean(r.get("IO_Address_Bit"))
        if not bit_raw:
            continue
        try:
            if re.fullmatch(r"[0-7]", bit_raw):
                bit = int(bit_raw)
            elif re.fullmatch(r"1[0-7]", bit_raw):
                bit = 8 + int(bit_raw[1])
            else:
                bit = int(float(bit_raw))
        except (TypeError, ValueError):
            continue
        out[(word, bit)] = name
    return out


def _run_point_for_channel(
    channel: str,
    *,
    run_by_wb: dict[tuple[str, int], str],
    physical_by_channel: dict[str, tuple[str, int]],
) -> str:
    ch = _clean(channel)
    wb = physical_by_channel.get(ch.upper())
    if not wb:
        return ""
    return run_by_wb.get(wb, "")


def _build_physical_channel_index(run_dir: Path, machine: str) -> dict[str, tuple[str, int]]:
    """channel.upper() → (fortna_word, bit) via PhysicalWordResolver owned words."""
    try:
        from fortna_physical_word_resolver import PhysicalWordResolver, build_physical_word_map
    except Exception:
        return {}
    pm = build_physical_word_map(run_dir, machine)
    resolver = PhysicalWordResolver(run_dir, machine)
    out: dict[str, tuple[str, int]] = {}
    words = pm.get("words") or {}
    for wkey, meta in words.items():
        try:
            word = int(float(wkey))
        except (TypeError, ValueError):
            continue
        # Probe bits 0-15; resolver returns None for unused halves sometimes
        for bit in range(16):
            hit = resolver.resolve(word, bit)
            if not hit:
                continue
            ch = _clean(hit.get("channel"))
            if not ch:
                continue
            out[ch.upper()] = (str(word), bit)
    return out


def classify_channel_row(
    *,
    gen: dict | None,
    fin: dict | None,
    run_point: str,
) -> str:
    g_ph = _is_placeholder_tag((gen or {}).get("tag") or "") if gen else True
    f_ph = _is_placeholder_tag((fin or {}).get("tag") or "") if fin else True

    if gen and fin:
        if g_ph and not f_ph:
            return "FALSE_PLACEHOLDER"
        if (not g_ph) and f_ph:
            return "SHOULD_BE_PLACEHOLDER"
        if g_ph and f_ph:
            gp = _parse_channel(gen.get("channel") or "")
            fp = _parse_channel(fin.get("channel") or "")
            if (
                gp.get("adapter", "").upper() == fp.get("adapter", "").upper()
                and gp.get("data_index") == fp.get("data_index")
                and gp.get("bit") == fp.get("bit")
                and gp.get("direction") == fp.get("direction")
            ):
                return "EXACT"
            return "SEMANTIC_EQUIVALENT"

        gp = _parse_channel(gen.get("channel") or "")
        fp = _parse_channel(fin.get("channel") or "")
        g_dev, g_mem = _split_device_member(gen.get("tag") or "")
        f_dev, f_mem = _split_device_member(fin.get("tag") or "")
        same_ch = (
            gp.get("adapter", "").upper() == fp.get("adapter", "").upper()
            and gp.get("data_index") == fp.get("data_index")
            and gp.get("bit") == fp.get("bit")
            and gp.get("direction") == fp.get("direction")
        )
        same_tag = _norm_tag(gen.get("tag") or "") == _norm_tag(fin.get("tag") or "")

        if same_ch and same_tag:
            return "EXACT"
        if same_tag and not same_ch:
            if gp.get("direction") != fp.get("direction"):
                return "WRONG_DIRECTION"
            if gp.get("adapter", "").upper() != fp.get("adapter", "").upper():
                return "WRONG_ADAPTER"
            if gp.get("data_index") != fp.get("data_index"):
                return "WRONG_SLOT"
            if gp.get("bit") != fp.get("bit"):
                return "WRONG_BIT"
            return "SEMANTIC_EQUIVALENT"

        if same_ch and not same_tag:
            if _norm_tag(g_dev) == _norm_tag(f_dev) and _norm_tag(g_mem) != _norm_tag(f_mem):
                return "WRONG_MEMBER"
            return "WRONG_DEVICE"

        if gp.get("direction") != fp.get("direction"):
            return "WRONG_DIRECTION"
        if gp.get("adapter", "").upper() != fp.get("adapter", "").upper():
            return "WRONG_ADAPTER"
        if gp.get("data_index") != fp.get("data_index"):
            return "WRONG_SLOT"
        if gp.get("bit") != fp.get("bit"):
            return "WRONG_BIT"
        if _norm_tag(g_dev) != _norm_tag(f_dev):
            return "WRONG_DEVICE"
        if _norm_tag(g_mem) != _norm_tag(f_mem):
            return "WRONG_MEMBER"
        return "SEMANTIC_EQUIVALENT"

    if fin and not gen:
        if not f_ph and not run_point:
            return "RUN_UNRESOLVED"
        if not f_ph:
            return "FALSE_PLACEHOLDER"
        return "SEMANTIC_EQUIVALENT"

    if gen and not fin:
        if g_ph:
            return "SEMANTIC_EQUIVALENT"
        if not run_point:
            return "RUN_UNRESOLVED"
        return "SHOULD_BE_PLACEHOLDER"

    return "RUN_UNRESOLVED"


def build_io_channel_matrix(
    gen_text: str,
    fin_text: str,
    *,
    run_dir: Path | None = None,
    machine: str = "ORNCCP2",
) -> dict[str, Any]:
    gen_maps = _parse_iomap_mappings(gen_text, limit=5000)
    fin_maps = _parse_iomap_mappings(fin_text, limit=5000)
    gen_mods = _module_catalog_by_adapter(gen_text)
    fin_mods = _module_catalog_by_adapter(fin_text)

    run_by_wb: dict[tuple[str, int], str] = {}
    physical_by_channel: dict[str, tuple[str, int]] = {}
    if run_dir and run_dir.is_dir():
        run_by_wb = _build_run_logical_index(run_dir)
        physical_by_channel = _build_physical_channel_index(run_dir, machine)

    def ch_key(m: dict) -> tuple:
        p = _parse_channel(m.get("channel") or "")
        return (
            (p.get("adapter") or "").upper(),
            (p.get("direction") or "").upper(),
            p.get("data_index"),
            p.get("bit"),
        )

    gen_by = {ch_key(m): m for m in gen_maps if ch_key(m)[0]}
    fin_by = {ch_key(m): m for m in fin_maps if ch_key(m)[0]}
    keys = sorted(set(gen_by) | set(fin_by), key=lambda k: (k[0], k[1], k[2] or -1, k[3] or -1))

    rows: list[dict[str, Any]] = []
    counts: Counter = Counter()
    for k in keys:
        gm = gen_by.get(k)
        fm = fin_by.get(k)
        channel = (gm or fm or {}).get("channel") or (
            f"{k[0]}:{k[1]}.Data[{k[2]}].{k[3]}" if k[0] else ""
        )
        run_pt = _run_point_for_channel(
            channel,
            run_by_wb=run_by_wb,
            physical_by_channel=physical_by_channel,
        )
        classification = classify_channel_row(gen=gm, fin=fm, run_point=run_pt)

        # Refine placeholder / exact overrides (same policy as fidelity audit)
        if fm and not _is_placeholder_tag(fm.get("tag") or ""):
            if (not gm) or _is_placeholder_tag(gm.get("tag") or ""):
                classification = "FALSE_PLACEHOLDER"
        if gm and not _is_placeholder_tag(gm.get("tag") or ""):
            if (not fm) or _is_placeholder_tag(fm.get("tag") or ""):
                classification = "SHOULD_BE_PLACEHOLDER"
        if (
            gm
            and fm
            and not _is_placeholder_tag(gm.get("tag") or "")
            and not _is_placeholder_tag(fm.get("tag") or "")
        ):
            gp = _parse_channel(gm.get("channel") or "")
            fp = _parse_channel(fm.get("channel") or "")
            if (
                _norm_tag(gm.get("tag") or "") == _norm_tag(fm.get("tag") or "")
                and gp.get("adapter", "").upper() == fp.get("adapter", "").upper()
                and gp.get("data_index") == fp.get("data_index")
                and gp.get("bit") == fp.get("bit")
                and gp.get("direction") == fp.get("direction")
            ):
                classification = "EXACT"
            elif _norm_tag(gm.get("tag") or "") == _norm_tag(fm.get("tag") or ""):
                if gp.get("direction") != fp.get("direction"):
                    classification = "WRONG_DIRECTION"
                elif gp.get("adapter", "").upper() != fp.get("adapter", "").upper():
                    classification = "WRONG_ADAPTER"
                elif gp.get("data_index") != fp.get("data_index"):
                    classification = "WRONG_SLOT"
                elif gp.get("bit") != fp.get("bit"):
                    classification = "WRONG_BIT"
                else:
                    classification = "SEMANTIC_EQUIVALENT"
            else:
                g_dev, g_mem = _split_device_member(gm.get("tag") or "")
                f_dev, f_mem = _split_device_member(fm.get("tag") or "")
                same_phys = (
                    gp.get("adapter", "").upper() == fp.get("adapter", "").upper()
                    and gp.get("data_index") == fp.get("data_index")
                    and gp.get("bit") == fp.get("bit")
                )
                if same_phys and _norm_tag(g_dev) == _norm_tag(f_dev):
                    classification = "WRONG_MEMBER"
                elif same_phys:
                    classification = "WRONG_DEVICE"
                elif gp.get("adapter", "").upper() != fp.get("adapter", "").upper():
                    classification = "WRONG_ADAPTER"
                elif gp.get("data_index") != fp.get("data_index"):
                    classification = "WRONG_SLOT"
                elif gp.get("bit") != fp.get("bit"):
                    classification = "WRONG_BIT"
                elif gp.get("direction") != fp.get("direction"):
                    classification = "WRONG_DIRECTION"
                else:
                    classification = "WRONG_DEVICE"

        if (
            not run_pt
            and fm
            and not _is_placeholder_tag(fm.get("tag") or "")
            and not gm
            and classification
            not in {
                "EXACT",
                "SEMANTIC_EQUIVALENT",
                "FALSE_PLACEHOLDER",
                "SHOULD_BE_PLACEHOLDER",
            }
        ):
            classification = "RUN_UNRESOLVED"

        g_ch = (gm or {}).get("channel") or channel
        row = {
            "adapter": k[0],
            "module": _module_for_channel(g_ch, gen_mods) or _module_for_channel(g_ch, fin_mods),
            "direction": k[1],
            "Data_index": k[2],
            "bit": k[3],
            "channel": g_ch,
            "run_logical_point": run_pt or None,
            "generated_logical_point": None
            if not gm or _is_placeholder_tag(gm.get("tag") or "")
            else gm.get("tag"),
            "finished_logical_point": None
            if not fm or _is_placeholder_tag(fm.get("tag") or "")
            else fm.get("tag"),
            "generated_is_placeholder": bool(gm and _is_placeholder_tag(gm.get("tag") or "")),
            "finished_is_placeholder": bool(fm and _is_placeholder_tag(fm.get("tag") or "")),
            "classification": classification,
        }
        counts[classification] += 1
        rows.append(row)

    gen_real, gen_ph = _split_real_placeholder(gen_maps)
    fin_real, fin_ph = _split_real_placeholder(fin_maps)

    return {
        "generated_at": _ts(),
        "machine": machine,
        "policy": "Finished PLC is validation oracle only — classify differences; do not invent generation rules",
        "classifications": list(CLASSIFICATIONS),
        "counts": {c: int(counts.get(c, 0)) for c in CLASSIFICATIONS},
        "summary": {
            "channels_compared": len(rows),
            "generated_real_I": sum(1 for m in gen_real if m.get("direction") == "I"),
            "generated_real_O": sum(1 for m in gen_real if m.get("direction") == "O"),
            "finished_real_I": sum(1 for m in fin_real if m.get("direction") == "I"),
            "finished_real_O": sum(1 for m in fin_real if m.get("direction") == "O"),
            "generated_placeholders": len(gen_ph),
            "finished_placeholders": len(fin_ph),
        },
        "sample_mismatches": [
            {
                "channel": r.get("channel"),
                "classification": r.get("classification"),
                "generated": r.get("generated_logical_point"),
                "finished": r.get("finished_logical_point"),
                "run": r.get("run_logical_point"),
            }
            for r in rows
            if r.get("classification")
            not in {"EXACT", "SEMANTIC_EQUIVALENT"}
        ][:40],
        "channels": rows,
    }


def _parse_fast_conv(text: str) -> dict[str, dict[str, Any]]:
    """Map conveyor → Fast_Conv fields. Area / ESZone ignored for compare."""
    out: dict[str, dict[str, Any]] = {}
    for m in re.finditer(r"Fast_Conv\(([^)]*)\)", text, re.I):
        args = [a.strip() for a in m.group(1).split(",")]
        if len(args) < 8:
            continue
        mm = re.match(r"^(P\d+[A-Za-z0-9_]*)_Conv$", args[1], re.I)
        if not mm:
            continue
        conv = mm.group(1).upper()
        nxt = args[4]
        nm = re.match(r"^(P\d+[A-Za-z0-9_]*)_Conv$", nxt, re.I)
        next_conv = "NO_Conv" if nxt.upper() == "NO_CONV" else (nm.group(1).upper() if nm else nxt)
        typ = args[7]
        tm = re.match(r"^(P\d+[A-Za-z0-9_]*)_Conv\.Type$", typ, re.I)
        type_ref = tm.group(0) if tm else typ
        out[conv] = {
            "aoi": args[0],
            "conv": args[1],
            "next": next_conv,
            "exit_pe": args[5],
            "add_pe": args[6],
            "type": type_ref,
            # Area / ESZone intentionally omitted from compare keys
            "area_ignored": args[2],
            "eszone_ignored": args[3],
        }
    return out


def _drive_is_vfd_name(drive: str) -> bool:
    d = _clean(drive)
    if not d or d.upper() in SKIP_IO:
        return False
    if re.fullmatch(r"\d+(\.\d+)?", d):
        return False
    return bool(re.search(r"VFD", d, re.I)) or bool(re.match(r"^[A-Za-z]", d))


def _conveyor_meta(run_dir: Path, local: set[str]) -> dict[str, dict[str, Any]]:
    path = run_dir / "FORTNA" / "Conveyor.asc"
    _h, rows = read_asc(path)
    meta: dict[str, dict[str, Any]] = {}
    pe_by_conv: dict[str, list[str]] = defaultdict(list)
    motor_by_conv: dict[str, list[str]] = defaultdict(list)

    for r in rows:
        name = _clean(r.get("IO_Name")).upper()
        typ = _clean(r.get("Type")).upper()
        if not name:
            continue
        if re.match(r"^(?:EZ)?PE\d", name, re.I) or typ in {"PHOTOEYE", "PE", "PROX", "PHOTOCELL"}:
            m = re.match(r"^(?:EZ)?PE(\d+[A-Z0-9_]*)", name, re.I)
            if m:
                # Associate PE150_P1 → P150_P1 when suffix present; else P150
                digits = m.group(1).upper()
                pe_by_conv[f"P{digits.split('_')[0]}"].append(name)
                if "_" in digits:
                    pe_by_conv[f"P{digits}"].append(name)
        if re.match(r"^M\d", name, re.I) and not name.startswith("VFD"):
            m = re.match(r"^M(\d+[A-Z]*)", name, re.I)
            if m:
                motor_by_conv[f"P{m.group(1)}".upper()].append(name)

    for r in rows:
        name = _clean(r.get("IO_Name")).upper()
        if name not in local:
            continue
        typ = _clean(r.get("Type")).upper()
        if typ not in MECH_TYPES and not re.match(r"^P\d", name):
            continue
        motor = _clean(r.get("Motor"))
        drive = _clean(r.get("Drive"))
        has_motor = bool(motor and motor.upper() not in SKIP_IO) or bool(motor_by_conv.get(name))
        has_vfd = _drive_is_vfd_name(drive)
        pes = list(dict.fromkeys(pe_by_conv.get(name) or []))
        meta[name] = {
            "type": typ or "STRAIGHT",
            "has_motor": has_motor,
            "has_vfd": has_vfd,
            "photoeyes": pes,
            "has_pe": bool(pes),
        }
    for tag in local:
        if tag not in meta:
            meta[tag] = {
                "type": "UNKNOWN",
                "has_motor": bool(motor_by_conv.get(tag)),
                "has_vfd": False,
                "photoeyes": list(pe_by_conv.get(tag) or []),
                "has_pe": bool(pe_by_conv.get(tag)),
            }
    return meta


def build_transport_device_matrix(
    *,
    local: list[str],
    meta: dict[str, dict[str, Any]],
    gen_text: str,
    fin_text: str,
) -> dict[str, Any]:
    """Compare Conv / AOI / MS / PE / Fast_Conv next+Type; ignore Area names."""
    gen_tags = _l5x_tag_names(gen_text)
    fin_tags = _l5x_tag_names(fin_text)
    gen_fast = _parse_fast_conv(gen_text)
    fin_fast = _parse_fast_conv(fin_text)
    gen_pe = {t for t in gen_tags if re.match(r"^(?:EZ)?PE\d", t, re.I)}
    fin_pe = {t for t in fin_tags if re.match(r"^(?:EZ)?PE\d", t, re.I)}

    rows = []
    totals = Counter()
    field_counts = Counter()

    for conv in sorted(local):
        m = meta.get(conv) or {}
        gen = {
            "Conv": f"{conv}_Conv" in gen_tags,
            "Conv_AOI": f"{conv}_Conv_AOI" in gen_tags,
            "MS": f"{conv}_MS" in gen_tags,
            "PE": any(
                re.match(rf"^(?:EZ)?PE{re.escape(conv[1:])}\b", p, re.I)
                or p.upper().startswith(f"PE{conv[1:]}")
                for p in gen_pe
            )
            or any(p in gen_tags for p in (m.get("photoeyes") or [])),
            "Fast_Conv": conv in gen_fast,
        }
        fin = {
            "Conv": f"{conv}_Conv" in fin_tags,
            "Conv_AOI": f"{conv}_Conv_AOI" in fin_tags,
            "MS": f"{conv}_MS" in fin_tags,
            "PE": any(
                re.match(rf"^(?:EZ)?PE{re.escape(conv[1:])}\b", p, re.I)
                or p.upper().startswith(f"PE{conv[1:]}")
                for p in fin_pe
            )
            or any(p in fin_tags for p in (m.get("photoeyes") or [])),
            "Fast_Conv": conv in fin_fast,
        }

        g_fc = gen_fast.get(conv) or {}
        f_fc = fin_fast.get(conv) or {}
        next_match = None
        type_match = None
        if g_fc or f_fc:
            next_match = (_clean(g_fc.get("next")).upper() == _clean(f_fc.get("next")).upper())
            # Type compare ignores absolute area; only Conv.Type identity
            type_match = (_clean(g_fc.get("type")).upper() == _clean(f_fc.get("type")).upper())

        families: dict[str, Any] = {}
        for fam in ("Conv", "Conv_AOI", "MS", "PE", "Fast_Conv"):
            g_on, f_on = bool(gen.get(fam)), bool(fin.get(fam))
            if g_on and f_on:
                result = "BOTH"
            elif g_on and not f_on:
                result = "GENERATED_ONLY"
            elif f_on and not g_on:
                result = "FINISHED_ONLY"
            else:
                result = "NEITHER"
            families[fam] = {
                "generated": g_on,
                "finished": f_on,
                "result": result,
            }
            totals[f"{fam}_{result}"] += 1

        if next_match is True:
            field_counts["next_match"] += 1
        elif next_match is False:
            field_counts["next_mismatch"] += 1
        if type_match is True:
            field_counts["type_match"] += 1
        elif type_match is False:
            field_counts["type_mismatch"] += 1

        rows.append(
            {
                "conveyor": conv,
                "asc_type": m.get("type"),
                "families": families,
                "fast_conv": {
                    "generated_next": g_fc.get("next"),
                    "finished_next": f_fc.get("next"),
                    "next_match": next_match,
                    "generated_type": g_fc.get("type"),
                    "finished_type": f_fc.get("type"),
                    "type_match": type_match,
                    "area_ignored": True,
                    "generated_area_ignored": g_fc.get("area_ignored"),
                    "finished_area_ignored": f_fc.get("area_ignored"),
                },
            }
        )

    return {
        "generated_at": _ts(),
        "policy": "Compare Conv/AOI/MS/PE/Fast_Conv next+Type; ignore Area / ESZone names",
        "local_conveyor_count": len(local),
        "totals": dict(totals),
        "fast_conv_field_counts": dict(field_counts),
        "sample_next_mismatches": [
            {
                "conveyor": r["conveyor"],
                "generated_next": r["fast_conv"].get("generated_next"),
                "finished_next": r["fast_conv"].get("finished_next"),
            }
            for r in rows
            if r["fast_conv"].get("next_match") is False
        ][:30],
        "conveyors": rows,
    }


def write_report(
    out: Path,
    *,
    channel_matrix: dict[str, Any],
    device_matrix: dict[str, Any],
    current_l5x: Path,
    finished_l5x: Path,
) -> Path:
    counts = channel_matrix.get("counts") or {}
    summary = channel_matrix.get("summary") or {}
    samples = channel_matrix.get("sample_mismatches") or []
    lines = [
        "# PLC2 Validation — IO Channel + Transport Device Matrix",
        "",
        f"**Generated:** {_ts()}",
        f"**Current L5X:** `{current_l5x.as_posix()}`",
        f"**Finished oracle (validation only):** `{finished_l5x.as_posix()}`",
        "",
        "## Policy",
        "",
        "- RUN tables are the generation source.",
        "- Finished PLC2 is **validation only** — never a generation template.",
        "- This report classifies differences; it does not invent generation rules from finished.",
        "",
        "## I/O channel classification counts",
        "",
        "| Classification | Count |",
        "|----------------|------:|",
    ]
    for c in CLASSIFICATIONS:
        lines.append(f"| {c} | {counts.get(c, 0)} |")
    lines += [
        "",
        "## I/O summary",
        "",
        "| Metric | Count |",
        "|--------|------:|",
        f"| Channels compared | {summary.get('channels_compared', 0)} |",
        f"| Generated real I | {summary.get('generated_real_I', 0)} |",
        f"| Generated real O | {summary.get('generated_real_O', 0)} |",
        f"| Finished real I | {summary.get('finished_real_I', 0)} |",
        f"| Finished real O | {summary.get('finished_real_O', 0)} |",
        f"| Generated placeholders | {summary.get('generated_placeholders', 0)} |",
        f"| Finished placeholders | {summary.get('finished_placeholders', 0)} |",
        "",
        "## Sample mismatches",
        "",
    ]
    if not samples:
        lines.append("_None (all EXACT / SEMANTIC_EQUIVALENT)._")
    else:
        lines.append("| Channel | Class | Generated | Finished | RUN |")
        lines.append("|---------|-------|-----------|----------|-----|")
        for s in samples[:25]:
            lines.append(
                f"| `{s.get('channel')}` | {s.get('classification')} | "
                f"`{s.get('generated')}` | `{s.get('finished')}` | `{s.get('run')}` |"
            )

    dt = device_matrix.get("totals") or {}
    fc = device_matrix.get("fast_conv_field_counts") or {}
    lines += [
        "",
        "## Transport device matrix (Area names ignored)",
        "",
        f"- Local conveyors compared: **{device_matrix.get('local_conveyor_count', 0)}**",
        f"- Fast_Conv next match / mismatch: **{fc.get('next_match', 0)}** / **{fc.get('next_mismatch', 0)}**",
        f"- Fast_Conv type match / mismatch: **{fc.get('type_match', 0)}** / **{fc.get('type_mismatch', 0)}**",
        "",
        "| Family result | Count |",
        "|---------------|------:|",
    ]
    for k in sorted(dt):
        lines.append(f"| {k} | {dt[k]} |")
    lines += [
        "",
        "## Artifacts",
        "",
        "- `exports/plc2-validation/io_channel_matrix.json`",
        "- `exports/plc2-validation/transport_device_matrix.json`",
        "- `exports/plc2-validation/report.md`",
        "",
    ]
    path = out / "report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PLC2 IO channel + transport device matrix")
    ap.add_argument("--run-dir", type=Path, default=ROOT / "workspace" / "active" / "RUN")
    ap.add_argument("--finished", type=Path, default=FINISHED_DEFAULT)
    ap.add_argument("--current", type=Path, default=None, help="Override current L5X path")
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--machine", default="ORNCCP2")
    args = ap.parse_args(argv)

    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    run_dir = args.run_dir if args.run_dir.is_absolute() else ROOT / args.run_dir
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"
    fin_path = args.finished if args.finished.is_absolute() else ROOT / args.finished
    cur_path = resolve_current_l5x(args.current)

    if not fin_path.is_file():
        print(f"ERROR: finished L5X missing: {fin_path}")
        return 1

    print(f"[plc2-validation] current={cur_path}")
    print(f"[plc2-validation] finished={fin_path}")

    gen_text = cur_path.read_text(encoding="utf-8", errors="replace")
    fin_text = fin_path.read_text(encoding="utf-8", errors="replace")

    print("[plc2-validation] IO channel matrix…")
    channel_matrix = build_io_channel_matrix(
        gen_text, fin_text, run_dir=run_dir, machine=args.machine
    )
    channel_matrix["current_l5x"] = str(cur_path)
    channel_matrix["finished_l5x"] = str(fin_path)
    write_json(out / "io_channel_matrix.json", channel_matrix)

    print("[plc2-validation] controller scope + transport device matrix…")
    scope = build_controller_scope(run_dir, args.machine)
    local = list((scope.get("by_scope") or {}).get("LOCAL") or [])
    meta = _conveyor_meta(run_dir, set(local))
    device_matrix = build_transport_device_matrix(
        local=local, meta=meta, gen_text=gen_text, fin_text=fin_text
    )
    device_matrix["current_l5x"] = str(cur_path)
    device_matrix["finished_l5x"] = str(fin_path)
    write_json(out / "transport_device_matrix.json", device_matrix)

    report = write_report(
        out,
        channel_matrix=channel_matrix,
        device_matrix=device_matrix,
        current_l5x=cur_path,
        finished_l5x=fin_path,
    )

    print(json.dumps(channel_matrix.get("counts"), indent=2))
    print(f"Wrote {out / 'io_channel_matrix.json'}")
    print(f"Wrote {out / 'transport_device_matrix.json'}")
    print(f"Wrote {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

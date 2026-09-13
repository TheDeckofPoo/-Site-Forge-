#!/usr/bin/env python3
"""PLC2 transport fidelity audit — ORNCCP2 / Greensboro.

Produces exports/plc2-fidelity/* from RUN + generated L5X vs finished oracle.
Finished PLC is VALIDATION ONLY — never a generation template.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_asc import CONVEYOR_TYPES, read_asc  # noqa: E402
from fortna_controller_scope import build_controller_scope, write_controller_scope  # noqa: E402
from fortna_io_regression_baselines import _parse_iomap_mappings  # noqa: E402
from fortna_plc2_io_truth import (  # noqa: E402
    CHANNEL_RE,
    _guess_run_names_for_finished_tag,
    _is_placeholder_tag,
    _split_real_placeholder,
    build_io_evidence_graph,
)
from fortna_site_model import write_json  # noqa: E402

MECH_TYPES = {t.upper() for t in CONVEYOR_TYPES} | {"ZEROPRESSURE", "ACCUMULATOR", "MDR"}
SKIP_IO = frozenset({"", "INVALID", "N/A", "SPARE", "NEVERON", "ALWAYSON", "NONE"})

CLASSIFICATIONS = (
    "EXACT",
    "EQUIVALENT",
    "WRONG_DEVICE",
    "WRONG_MEMBER",
    "WRONG_ADAPTER",
    "WRONG_SLOT",
    "WRONG_BIT",
    "WRONG_DIRECTION",
    "FALSE_PLACEHOLDER",
    "SHOULD_BE_PLACEHOLDER",
    "RUN_UNRESOLVED",
)

ROUTINE_KEYS = ("Fast", "Slow_Flt", "Slow_Jam", "Slow_PI", "PE", "Full", "L1", "L2")


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
    """P400_MS.I.Auxiliary_Forward → (P400_MS, I.Auxiliary_Forward)."""
    t = _clean(tag)
    if "." not in t:
        return t, ""
    device, member = t.split(".", 1)
    return device, member


def _device_family(device: str) -> str:
    d = _clean(device)
    m = re.match(r"^(P\d+[A-Za-z0-9]*)_(Conv_AOI|Conv|MS|VFD)$", d, re.I)
    if m:
        return m.group(2).upper() if m.group(2).upper() != "CONV_AOI" else "CONV_AOI"
    m = re.match(r"^((?:EZ)?PE\d+[A-Za-z0-9_]*)", d, re.I)
    if m:
        return "PE"
    m = re.match(r"^(P\d+[A-Za-z0-9]*)", d, re.I)
    if m:
        return "P"
    return "OTHER"


def _ptag_from_device(device: str) -> str:
    d = _clean(device)
    m = re.match(r"^(P\d+[A-Za-z0-9]*)", d, re.I)
    if m:
        return m.group(1).upper()
    m = re.match(r"^(?:EZ)?PE(\d+[A-Za-z0-9]*)", d, re.I)
    if m:
        return f"P{m.group(1)}".upper()
    m = re.match(r"^M(\d+[A-Za-z0-9]*)", d, re.I)
    if m:
        return f"P{m.group(1)}".upper()
    return ""


def _l5x_tag_names(text: str) -> set[str]:
    return set(re.findall(r'\bName="([A-Za-z_][A-Za-z0-9_]*)"', text))


def _module_catalog_by_adapter(text: str) -> dict[str, list[dict[str, str]]]:
    """Map adapter name → child modules with catalog/name."""
    out: dict[str, list[dict[str, str]]] = defaultdict(list)
    for m in re.finditer(
        r'<Module\b([^>]*)>(.*?)</Module>',
        text,
        re.I | re.S,
    ):
        attrs, body = m.group(1), m.group(2)
        # Only top-level-ish: nested Module tags appear in body; take Name/CatalogNumber from attrs
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
    # Child naming CPxRIOn_k often aligns with Data[k]
    for c in children:
        n = c.get("name") or ""
        m = re.search(r"_(\d+)$", n)
        if m and int(m.group(1)) == idx:
            return c.get("catalog") or n
    if 0 <= idx < len(children):
        c = children[idx]
        return c.get("catalog") or c.get("name") or ""
    return ""


def _build_run_point_index(graph: dict[str, Any]) -> dict[str, str]:
    """channel-family key → RUN logical point name (best effort via word/bit)."""
    # Prefer LogicalPoint nodes with fortna_word + data_bit; keyed later via resolver
    by_wb: dict[str, str] = {}
    for n in graph.get("nodes") or []:
        if n.get("type") != "LogicalPoint":
            continue
        name = _clean(n.get("name"))
        w = _clean(n.get("fortna_word"))
        b = n.get("data_bit")
        if not name or not w or b is None:
            continue
        try:
            wkey = str(int(float(w)))
        except (TypeError, ValueError):
            wkey = w
        by_wb[f"{wkey}:{int(b)}"] = name
    return by_wb


def _run_point_for_tag(tag: str, graph: dict[str, Any], by_wb: dict[str, str]) -> str:
    cands = _guess_run_names_for_finished_tag(tag)
    by_name = {
        (n.get("name") or "").upper(): n
        for n in graph.get("nodes") or []
        if n.get("type") == "LogicalPoint" and n.get("name")
    }
    for c in cands:
        n = by_name.get(c.upper())
        if not n:
            continue
        w = _clean(n.get("fortna_word"))
        b = n.get("data_bit")
        if w and b is not None:
            try:
                wkey = str(int(float(w)))
            except (TypeError, ValueError):
                wkey = w
            return by_wb.get(f"{wkey}:{int(b)}", n.get("name") or c)
        return n.get("name") or c
    return ""


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
            # Both unused — treat as exact spare fill
            gp = _parse_channel(gen.get("channel") or "")
            fp = _parse_channel(fin.get("channel") or "")
            if (
                gp.get("adapter", "").upper() == fp.get("adapter", "").upper()
                and gp.get("data_index") == fp.get("data_index")
                and gp.get("bit") == fp.get("bit")
                and gp.get("direction") == fp.get("direction")
            ):
                return "EXACT"
            return "EQUIVALENT"

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
            return "EQUIVALENT"

        # Same physical channel, different logical
        if same_ch and not same_tag:
            if _norm_tag(g_dev) == _norm_tag(f_dev) and _norm_tag(g_mem) != _norm_tag(f_mem):
                return "WRONG_MEMBER"
            return "WRONG_DEVICE"

        # Different channel + different/same tag already handled; leftover structural
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
        return "EQUIVALENT"

    if fin and not gen:
        # Finished has mapping, generated missing for this channel key —
        # if finished is real and we somehow only have fin side via channel union
        if not f_ph and not run_point:
            return "RUN_UNRESOLVED"
        if not f_ph:
            return "FALSE_PLACEHOLDER"  # gen absent ⇒ effectively placeholder gap
        return "EQUIVALENT"

    if gen and not fin:
        if g_ph:
            return "EQUIVALENT"  # gen spare, fin absent on this channel
        if not run_point:
            return "RUN_UNRESOLVED"
        return "SHOULD_BE_PLACEHOLDER"

    return "RUN_UNRESOLVED"


def build_channel_matrix(
    gen_text: str,
    fin_text: str,
    graph: dict[str, Any],
) -> dict[str, Any]:
    gen_maps = _parse_iomap_mappings(gen_text, limit=5000)
    fin_maps = _parse_iomap_mappings(fin_text, limit=5000)
    gen_mods = _module_catalog_by_adapter(gen_text)
    fin_mods = _module_catalog_by_adapter(fin_text)
    by_wb = _build_run_point_index(graph)

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
        tag_for_run = (fm or gm or {}).get("tag") or ""
        run_pt = _run_point_for_tag(tag_for_run, graph, by_wb) if tag_for_run else ""
        # Prefer channel-derived RUN point when tag maps empty but word known — leave blank
        classification = classify_channel_row(gen=gm, fin=fm, run_point=run_pt)
        # Refine FALSE_PLACEHOLDER: gen placeholder / missing, finished real
        if fm and not _is_placeholder_tag(fm.get("tag") or ""):
            if (not gm) or _is_placeholder_tag(gm.get("tag") or ""):
                classification = "FALSE_PLACEHOLDER"
        if gm and not _is_placeholder_tag(gm.get("tag") or ""):
            if (not fm) or _is_placeholder_tag(fm.get("tag") or ""):
                classification = "SHOULD_BE_PLACEHOLDER"
        # Exact override when both real and identical
        if gm and fm and not _is_placeholder_tag(gm.get("tag") or "") and not _is_placeholder_tag(fm.get("tag") or ""):
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
                # Same logical, physical differs — pick most specific wrong_*
                if gp.get("direction") != fp.get("direction"):
                    classification = "WRONG_DIRECTION"
                elif gp.get("adapter", "").upper() != fp.get("adapter", "").upper():
                    classification = "WRONG_ADAPTER"
                elif gp.get("data_index") != fp.get("data_index"):
                    classification = "WRONG_SLOT"
                elif gp.get("bit") != fp.get("bit"):
                    classification = "WRONG_BIT"
                else:
                    classification = "EQUIVALENT"
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

        if not run_pt and fm and not _is_placeholder_tag(fm.get("tag") or ""):
            # Keep structural class but note unresolved when no RUN name
            if classification in {"EXACT", "EQUIVALENT"} and not _run_point_for_tag(
                fm.get("tag") or "", graph, by_wb
            ):
                pass

        adapter = k[0]
        direction = k[1]
        data_index = k[2]
        bit = k[3]
        g_ch = (gm or {}).get("channel") or (f"{adapter}:{direction}.Data[{data_index}].{bit}" if adapter else "")
        f_ch = (fm or {}).get("channel") or g_ch
        row = {
            "adapter": adapter,
            "module": _module_for_channel(g_ch or f_ch, gen_mods)
            or _module_for_channel(f_ch, fin_mods),
            "direction": direction,
            "Data_index": data_index,
            "bit": bit,
            "channel": g_ch or f_ch,
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
        if not run_pt and classification not in {
            "EXACT",
            "EQUIVALENT",
            "FALSE_PLACEHOLDER",
            "SHOULD_BE_PLACEHOLDER",
        }:
            # Mark unresolved only when we cannot explain the point from RUN at all
            if fm and not _is_placeholder_tag(fm.get("tag") or "") and not gm:
                cands = _guess_run_names_for_finished_tag(fm.get("tag") or "")
                by_name = {
                    (n.get("name") or "").upper()
                    for n in graph.get("nodes") or []
                    if n.get("type") == "LogicalPoint"
                }
                if not any(c.upper() in by_name for c in cands):
                    row["classification"] = "RUN_UNRESOLVED"
                    classification = "RUN_UNRESOLVED"
        counts[classification] += 1
        rows.append(row)

    gen_real, gen_ph = _split_real_placeholder(gen_maps)
    fin_real, fin_ph = _split_real_placeholder(fin_maps)

    # Tag-centric structural mismatches (same logical tag+dir, different physical channel)
    def td_key(m: dict) -> tuple:
        return (_norm_tag(m.get("tag") or ""), _clean(m.get("direction")).upper())

    fin_td = {td_key(m): m for m in fin_real if td_key(m)[0]}
    tag_struct: Counter = Counter()
    for gm in gen_real:
        k = td_key(gm)
        fm = fin_td.get(k)
        if not fm:
            continue
        gp = _parse_channel(gm.get("channel") or "")
        fp = _parse_channel(fm.get("channel") or "")
        if (
            gp.get("adapter", "").upper() == fp.get("adapter", "").upper()
            and gp.get("data_index") == fp.get("data_index")
            and gp.get("bit") == fp.get("bit")
            and gp.get("direction") == fp.get("direction")
        ):
            continue
        # Reclassify the generated channel row when it currently says EQUIVALENT/WRONG_DEVICE
        gk = ch_key(gm)
        for row in rows:
            if (
                row.get("adapter") == gk[0]
                and row.get("direction") == gk[1]
                and row.get("Data_index") == gk[2]
                and row.get("bit") == gk[3]
            ):
                if gp.get("direction") != fp.get("direction"):
                    new_c = "WRONG_DIRECTION"
                elif gp.get("adapter", "").upper() != fp.get("adapter", "").upper():
                    new_c = "WRONG_ADAPTER"
                elif gp.get("data_index") != fp.get("data_index"):
                    new_c = "WRONG_SLOT"
                elif gp.get("bit") != fp.get("bit"):
                    new_c = "WRONG_BIT"
                else:
                    new_c = "EQUIVALENT"
                old = row.get("classification")
                if old != new_c and old not in {"FALSE_PLACEHOLDER", "SHOULD_BE_PLACEHOLDER"}:
                    counts[old] -= 1
                    counts[new_c] += 1
                    row["classification"] = new_c
                    row["tag_centric_finished_channel"] = fm.get("channel")
                tag_struct[new_c] += 1
                break

    return {
        "generated_at": _ts(),
        "machine": "ORNCCP2",
        "policy": "Finished PLC is validation oracle only",
        "classifications": list(CLASSIFICATIONS),
        "counts": {c: max(0, counts.get(c, 0)) for c in CLASSIFICATIONS},
        "counts_other": {k: v for k, v in counts.items() if k not in CLASSIFICATIONS},
        "tag_centric_structural": dict(tag_struct),
        "summary": {
            "channels_compared": len(rows),
            "generated_real_I": sum(1 for m in gen_real if m.get("direction") == "I"),
            "generated_real_O": sum(1 for m in gen_real if m.get("direction") == "O"),
            "finished_real_I": sum(1 for m in fin_real if m.get("direction") == "I"),
            "finished_real_O": sum(1 for m in fin_real if m.get("direction") == "O"),
            "generated_placeholders": len(gen_ph),
            "finished_placeholders": len(fin_ph),
            "exact_real_tag_channel": sum(
                1
                for gm in gen_real
                if (fm := fin_td.get(td_key(gm)))
                and _norm_tag(gm.get("channel") or "") == _norm_tag(fm.get("channel") or "")
            ),
        },
        "channels": rows,
    }


def build_false_placeholder_audit(channel_matrix: dict[str, Any]) -> dict[str, Any]:
    rows = [
        {
            "adapter": r.get("adapter"),
            "direction": r.get("direction"),
            "Data_index": r.get("Data_index"),
            "bit": r.get("bit"),
            "channel": r.get("channel"),
            "finished_logical_point": r.get("finished_logical_point"),
            "run_logical_point": r.get("run_logical_point"),
            "generated_logical_point": r.get("generated_logical_point"),
            "generated_is_placeholder": r.get("generated_is_placeholder"),
        }
        for r in channel_matrix.get("channels") or []
        if r.get("classification") == "FALSE_PLACEHOLDER"
    ]
    return {
        "generated_at": _ts(),
        "definition": "Generated NO_PointPlaceholder (or missing) where finished has an active logical point",
        "count": len(rows),
        "rows": rows,
    }


def _drive_is_vfd_name(drive: str) -> bool:
    """Conveyor.Drive is often a numeric flag ('1'); only treat real VFD names as VFD."""
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
    vfd_by_conv: dict[str, list[str]] = defaultdict(list)

    # First pass: index PE/motor/VFD by associated P-tag
    for r in rows:
        name = _clean(r.get("IO_Name")).upper()
        typ = _clean(r.get("Type")).upper()
        if not name:
            continue
        if re.match(r"^(?:EZ)?PE\d", name, re.I) or typ in {"PHOTOEYE", "PE", "PROX"}:
            m = re.match(r"^(?:EZ)?PE(\d+[A-Z]?)", name, re.I)
            if m:
                pe_by_conv[f"P{m.group(1)}".upper()].append(name)
        # Discrete motor starters: M### / M###_AUX (not VFD* rows typed MOTOR)
        if re.match(r"^M\d", name, re.I) and not name.startswith("VFD"):
            m = re.match(r"^M(\d+[A-Z]*)", name, re.I)
            if m:
                motor_by_conv[f"P{m.group(1)}".upper()].append(name)
        if typ == "VFD" or re.match(r"^VFD\d", name, re.I):
            m = re.match(r"^VFD(\d+[A-Z]?)", name, re.I)
            if m:
                vfd_by_conv[f"P{m.group(1)}".upper()].append(name)

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
        has_vfd = _drive_is_vfd_name(drive) or bool(vfd_by_conv.get(name))
        # Desc/name VFD hint (same idea as fortna_autogen load_from_run)
        desc = _clean(r.get("Desc") or r.get("Description"))
        if re.search(r"\bVFD\b", f"{name} {desc} {drive}", re.I) and not re.fullmatch(r"\d+(\.\d+)?", drive or ""):
            has_vfd = True
        pes = list(dict.fromkeys(pe_by_conv.get(name) or []))
        meta[name] = {
            "type": typ or "STRAIGHT",
            "motor": motor,
            "drive": drive,
            "has_motor": has_motor,
            "has_vfd": has_vfd,
            "photoeyes": pes,
            "has_pe": bool(pes),
        }
    for tag in local:
        if tag not in meta:
            meta[tag] = {
                "type": "UNKNOWN",
                "motor": "",
                "drive": "",
                "has_motor": bool(motor_by_conv.get(tag)),
                "has_vfd": bool(vfd_by_conv.get(tag)),
                "photoeyes": list(pe_by_conv.get(tag) or []),
                "has_pe": bool(pe_by_conv.get(tag)),
            }
    return meta


def _required_device_families(meta: dict[str, Any]) -> dict[str, bool]:
    """Derive required object families from conveyor/device evidence (not P-number)."""
    has_motor = bool(meta.get("has_motor"))
    has_vfd = bool(meta.get("has_vfd"))
    has_pe = bool(meta.get("has_pe"))
    typ = (meta.get("type") or "").upper()
    is_mech = typ in MECH_TYPES or typ in {"", "UNKNOWN", "STRAIGHT", "BELT", "CURVE", "SPUR"}
    motorized = is_mech and (has_motor or has_vfd or typ in MECH_TYPES)
    return {
        "Conv": motorized,
        "Conv_AOI": motorized,
        # Discrete VFD feeders use P###_VFD Motor_Starter_UDT; otherwise P###_MS
        "MS": motorized and not has_vfd and (has_motor or typ in MECH_TYPES),
        "VFD": motorized and has_vfd,
        "PE": has_pe,
    }


def build_device_object_matrix(
    *,
    local: list[str],
    meta: dict[str, dict[str, Any]],
    gen_text: str,
    fin_text: str,
) -> dict[str, Any]:
    gen_tags = _l5x_tag_names(gen_text)
    fin_tags = _l5x_tag_names(fin_text)
    gen_pe_tags = {t for t in gen_tags if re.match(r"^(?:EZ)?PE\d", t, re.I)}
    fin_pe_tags = {t for t in fin_tags if re.match(r"^(?:EZ)?PE\d", t, re.I)}

    rows = []
    totals = Counter()
    for conv in sorted(local):
        m = meta.get(conv) or {}
        req = _required_device_families(m)
        gen = {
            "Conv": f"{conv}_Conv" in gen_tags,
            "Conv_AOI": f"{conv}_Conv_AOI" in gen_tags,
            "MS": f"{conv}_MS" in gen_tags,
            "VFD": f"{conv}_VFD" in gen_tags,
            "PE": any(
                re.match(rf"^(?:EZ)?PE{re.escape(conv[1:])}\b", p, re.I)
                or p.upper().startswith(f"PE{conv[1:]}")
                for p in gen_pe_tags
            )
            or any(p in gen_tags for p in (m.get("photoeyes") or [])),
        }
        fin = {
            "Conv": f"{conv}_Conv" in fin_tags,
            "Conv_AOI": f"{conv}_Conv_AOI" in fin_tags,
            "MS": f"{conv}_MS" in fin_tags,
            "VFD": f"{conv}_VFD" in fin_tags,
            "PE": any(
                re.match(rf"^(?:EZ)?PE{re.escape(conv[1:])}\b", p, re.I)
                or p.upper().startswith(f"PE{conv[1:]}")
                for p in fin_pe_tags
            )
            or any(p in fin_tags for p in (m.get("photoeyes") or [])),
        }
        families = {}
        for fam in ("Conv", "Conv_AOI", "MS", "VFD", "PE"):
            status = {
                "required": bool(req.get(fam)),
                "generated": bool(gen.get(fam)),
                "finished_present": bool(fin.get(fam)),
            }
            if status["required"] and status["generated"]:
                status["result"] = "PRESENT"
            elif status["required"] and not status["generated"]:
                status["result"] = "MISSING"
            elif (not status["required"]) and status["generated"]:
                status["result"] = "EXTRA"
            else:
                status["result"] = "N/A"
            families[fam] = status
            totals[f"{fam}_{status['result']}"] += 1
        rows.append(
            {
                "conveyor": conv,
                "type": m.get("type"),
                "has_motor": m.get("has_motor"),
                "has_vfd": m.get("has_vfd"),
                "photoeyes": m.get("photoeyes") or [],
                "families": families,
                "seed_case": conv == "P123",
            }
        )

    p123 = next((r for r in rows if r["conveyor"] == "P123"), None)
    return {
        "generated_at": _ts(),
        "local_conveyor_count": len(local),
        "seed_case": "P123",
        "P123": p123,
        "totals": dict(totals),
        "conveyors": rows,
        "note": "Required families derived from RUN motor/drive/PE evidence + mechanical type — not hard-coded device ids",
    }


def _expected_routines(meta: dict[str, Any], req: dict[str, bool]) -> dict[str, bool]:
    """Expected routine participation from device type / evidence."""
    motorized = bool(req.get("Conv"))
    return {
        "Fast": motorized,
        "Slow_Flt": motorized and (bool(meta.get("has_motor")) or bool(meta.get("has_vfd"))),
        "Slow_Jam": motorized,
        # Slow_PI (Conv_PI packs): motorized transport conveyors participate in finished pattern
        "Slow_PI": motorized and (bool(meta.get("has_motor")) or bool(meta.get("has_vfd"))),
        "PE": bool(req.get("PE")),
        "Full": bool(req.get("PE")),  # full PE when eyes exist (role refined by Full_PE calls)
        "L1": motorized,  # L1 Conv init params
        "L2": motorized,  # L2 speed / PETime
    }


def _scan_routine_participation(text: str, conveyors: list[str]) -> dict[str, dict[str, bool]]:
    """Detect per-conveyor participation in Fast/Slow_*/PE/Full/L1/L2."""
    fast = set()
    slow_flt = set()
    slow_jam = set()
    pe = set()
    full = set()
    slow_pi = set()
    l1 = set()
    l2 = set()

    for m in re.finditer(r"Fast_Conv\(([^)]*)\)", text, re.I):
        args = [a.strip() for a in m.group(1).split(",")]
        if len(args) >= 2:
            tok = args[1]
            mm = re.match(r"^(P\d+[A-Za-z0-9]*)_Conv$", tok, re.I)
            if mm:
                fast.add(mm.group(1).upper())

    for m in re.finditer(r"Slow_Flt\(([^)]*)\)", text, re.I):
        args = [a.strip() for a in m.group(1).split(",")]
        if len(args) >= 2:
            tok = args[1]
            mm = re.match(r"^(P\d+[A-Za-z0-9]*)_Conv$", tok, re.I)
            if mm:
                slow_flt.add(mm.group(1).upper())

    for m in re.finditer(r"Slow_Jam\(([^)]*)\)", text, re.I):
        args = [a.strip() for a in m.group(1).split(",")]
        if len(args) >= 2:
            tok = args[1]
            mm = re.match(r"^(P\d+[A-Za-z0-9]*)_Conv$", tok, re.I)
            if mm:
                slow_jam.add(mm.group(1).upper())

    for m in re.finditer(r"PE_Logic\(([^)]*)\)", text, re.I):
        args = [a.strip() for a in m.group(1).split(",")]
        if len(args) >= 3:
            tok = args[2]
            mm = re.match(r"^(P\d+[A-Za-z0-9]*)_Conv$", tok, re.I)
            if mm:
                pe.add(mm.group(1).upper())

    for m in re.finditer(r"Full_PE\(([^)]*)\)", text, re.I):
        args = [a.strip() for a in m.group(1).split(",")]
        if len(args) >= 3:
            tok = args[2]
            mm = re.match(r"^(P\d+[A-Za-z0-9]*)_Conv$", tok, re.I)
            if mm:
                full.add(mm.group(1).upper())

    # Slow_PI / Conv_PI: Slow_ConvPI* calls listing P###_Conv args
    for m in re.finditer(r"Slow_ConvPI\w*\(([^)]*)\)", text, re.I):
        for tok in m.group(1).split(","):
            mm = re.match(r"^\s*(P\d+[A-Za-z0-9]*)_Conv\s*$", tok, re.I)
            if mm:
                slow_pi.add(mm.group(1).upper())

    # L1/L2: area programs mentioning conveyor UDT / MS / VFD init or speed
    for prog in re.finditer(r'<Program\b[^>]*Name="([^"]*L1[^"]*)"[^>]*>(.*?)</Program>', text, re.I | re.S):
        body = prog.group(2)
        for mm in re.finditer(r"\b(P\d+[A-Za-z0-9]*)_(?:Conv|MS|VFD)\b", body):
            l1.add(mm.group(1).upper())

    for prog in re.finditer(r'<Program\b[^>]*Name="([^"]*L2[^"]*)"[^>]*>(.*?)</Program>', text, re.I | re.S):
        body = prog.group(2)
        for mm in re.finditer(r"\b(P\d+[A-Za-z0-9]*)_(?:Conv|MS|VFD)\b", body):
            l2.add(mm.group(1).upper())

    out = {}
    for c in conveyors:
        cu = c.upper()
        out[cu] = {
            "Fast": cu in fast,
            "Slow_Flt": cu in slow_flt,
            "Slow_Jam": cu in slow_jam,
            "Slow_PI": cu in slow_pi,
            "PE": cu in pe,
            "Full": cu in full,
            "L1": cu in l1,
            "L2": cu in l2,
        }
    return out


def build_routine_participation(
    *,
    local: list[str],
    meta: dict[str, dict[str, Any]],
    gen_text: str,
    fin_text: str,
) -> dict[str, Any]:
    gen_part = _scan_routine_participation(gen_text, local)
    fin_part = _scan_routine_participation(fin_text, local)
    rows = []
    summary = {k: Counter() for k in ROUTINE_KEYS}
    for conv in sorted(local):
        m = meta.get(conv) or {}
        req_fam = _required_device_families(m)
        expected = _expected_routines(m, req_fam)
        generated = gen_part.get(conv.upper()) or {k: False for k in ROUTINE_KEYS}
        finished = fin_part.get(conv.upper()) or {k: False for k in ROUTINE_KEYS}
        compare = {}
        for k in ROUTINE_KEYS:
            exp, gen, fin = expected[k], generated[k], finished[k]
            if exp and gen:
                result = "OK"
            elif exp and not gen:
                result = "MISSING"
            elif (not exp) and gen:
                result = "EXTRA"
            else:
                result = "N/A"
            compare[k] = {
                "expected": exp,
                "generated": gen,
                "finished": fin,
                "result": result,
            }
            summary[k][result] += 1
        rows.append(
            {
                "conveyor": conv,
                "type": m.get("type"),
                "routines": compare,
                "seed_case": conv == "P123",
            }
        )
    p123 = next((r for r in rows if r["conveyor"] == "P123"), None)
    return {
        "generated_at": _ts(),
        "routine_keys": list(ROUTINE_KEYS),
        "derivation": (
            "Expected participation from RUN mechanical type + motor/VFD/PE evidence: "
            "motorized → Fast/Slow_Flt/Slow_Jam/Slow_PI/L1/L2; PE evidence → PE/Full"
        ),
        "summary": {k: dict(summary[k]) for k in ROUTINE_KEYS},
        "P123": p123,
        "conveyors": rows,
    }


def build_connectivity_comparison(
    *,
    local: list[str],
    meta: dict[str, dict[str, Any]],
    gen_text: str,
    fin_text: str,
    gen_part: dict[str, dict[str, bool]],
    fin_part: dict[str, dict[str, bool]],
) -> dict[str, Any]:
    gen_tags = _l5x_tag_names(gen_text)
    fin_tags = _l5x_tag_names(fin_text)

    # Downstream from Fast_Conv args
    def downstream_map(text: str) -> dict[str, str]:
        out = {}
        for m in re.finditer(r"Fast_Conv\(([^)]*)\)", text, re.I):
            args = [a.strip() for a in m.group(1).split(",")]
            if len(args) < 5:
                continue
            mm = re.match(r"^(P\d+[A-Za-z0-9]*)_Conv$", args[1], re.I)
            if not mm:
                continue
            nxt = args[4]
            if nxt.upper() == "NO_CONV":
                out[mm.group(1).upper()] = "NO_Conv"
            else:
                nm = re.match(r"^(P\d+[A-Za-z0-9]*)_Conv$", nxt, re.I)
                out[mm.group(1).upper()] = nm.group(1).upper() if nm else nxt
        return out

    gen_ds = downstream_map(gen_text)
    fin_ds = downstream_map(fin_text)

    rows = []
    agg = Counter()
    for conv in sorted(local):
        m = meta.get(conv) or {}
        req = _required_device_families(m)
        g = gen_part.get(conv.upper()) or {}
        f = fin_part.get(conv.upper()) or {}
        rel = {
            "Conv_exists": {
                "required": req["Conv"],
                "generated": f"{conv}_Conv" in gen_tags,
                "finished": f"{conv}_Conv" in fin_tags,
            },
            "AOI": {
                "required": req["Conv_AOI"],
                "generated": f"{conv}_Conv_AOI" in gen_tags,
                "finished": f"{conv}_Conv_AOI" in fin_tags,
            },
            "motor_MS": {
                "required": req["MS"],
                "generated": f"{conv}_MS" in gen_tags,
                "finished": f"{conv}_MS" in fin_tags,
            },
            "VFD": {
                "required": req["VFD"],
                "generated": f"{conv}_VFD" in gen_tags,
                "finished": f"{conv}_VFD" in fin_tags,
            },
            "PE_refs": {
                "required": req["PE"],
                "generated": bool(g.get("PE") or g.get("Full")),
                "finished": bool(f.get("PE") or f.get("Full")),
            },
            "downstream": {
                "generated": gen_ds.get(conv.upper()),
                "finished": fin_ds.get(conv.upper()),
                "match": (
                    (gen_ds.get(conv.upper()) or "").upper()
                    == (fin_ds.get(conv.upper()) or "").upper()
                    if conv.upper() in gen_ds or conv.upper() in fin_ds
                    else None
                ),
            },
            "routine_participation": {
                k: {"generated": bool(g.get(k)), "finished": bool(f.get(k))}
                for k in ("Fast", "Slow_Flt", "Slow_Jam", "PE", "Full", "L1", "L2")
            },
        }
        # Score
        checks = []
        for key in ("Conv_exists", "AOI", "motor_MS", "VFD", "PE_refs"):
            r = rel[key]
            if not r["required"]:
                continue
            ok = bool(r["generated"])
            checks.append(ok)
            agg["required"] += 1
            if ok:
                agg["generated_ok"] += 1
            else:
                agg["generated_missing"] += 1
            if r["finished"]:
                agg["finished_present"] += 1
        rows.append({"conveyor": conv, "relationships": rel, "seed_case": conv == "P123"})

    return {
        "generated_at": _ts(),
        "policy": [
            "Ignore Area naming differences (ModuleB_Area vs ORNCCP2_Area)",
            "Finished PLC is validation-only answer sheet",
            "Relationship compare: Conv/AOI/motor/PE/VFD/downstream/routine participation",
        ],
        "aggregate": dict(agg),
        "coverage": round(agg["generated_ok"] / agg["required"], 4) if agg.get("required") else 0.0,
        "P123": next((r for r in rows if r["conveyor"] == "P123"), None),
        "conveyors": rows,
    }


def write_report(
    out: Path,
    *,
    channel_matrix: dict,
    false_ph: dict,
    device_matrix: dict,
    routines: dict,
    scope: dict,
    connectivity: dict,
    gen_path: Path,
    fin_path: Path,
) -> Path:
    s = channel_matrix.get("summary") or {}
    cc = channel_matrix.get("counts") or {}
    p123_dev = device_matrix.get("P123") or {}
    p123_rt = routines.get("P123") or {}
    fam = (p123_dev.get("families") or {}) if p123_dev else {}
    rt = (p123_rt.get("routines") or {}) if p123_rt else {}

    local_n = (scope.get("counts") or {}).get("LOCAL", 0)
    # Generated family totals among LOCAL
    conv_gen = sum(
        1
        for r in device_matrix.get("conveyors") or []
        if (r.get("families") or {}).get("Conv", {}).get("generated")
    )
    aoi_gen = sum(
        1
        for r in device_matrix.get("conveyors") or []
        if (r.get("families") or {}).get("Conv_AOI", {}).get("generated")
    )
    ms_gen = sum(
        1
        for r in device_matrix.get("conveyors") or []
        if (r.get("families") or {}).get("MS", {}).get("generated")
    )
    vfd_gen = sum(
        1
        for r in device_matrix.get("conveyors") or []
        if (r.get("families") or {}).get("VFD", {}).get("generated")
    )
    pe_gen = sum(
        1
        for r in device_matrix.get("conveyors") or []
        if (r.get("families") or {}).get("PE", {}).get("generated")
    )

    lines = [
        "# PLC2 Fidelity Audit — ORNCCP2 / Greensboro",
        "",
        f"**Generated:** {_ts()}",
        f"**Generated L5X:** `{gen_path.as_posix()}`",
        f"**Finished oracle (validation only):** `{fin_path.as_posix()}`",
        "",
        "## Policy",
        "",
        "- RUN tables are the generation source.",
        "- Finished PLC2 is **validation only** — never a generation template.",
        "- No hard-coded `if device == P123` rules (P123 reported as seed case only).",
        "",
        "## I/O channel summary",
        "",
        f"| Metric | Count |",
        f"|--------|------:|",
        f"| Finished real inputs | {s.get('finished_real_I')} |",
        f"| Finished real outputs | {s.get('finished_real_O')} |",
        f"| Generated real inputs | {s.get('generated_real_I')} |",
        f"| Generated real outputs | {s.get('generated_real_O')} |",
        f"| False placeholders | {false_ph.get('count')} |",
        f"| EXACT | {cc.get('EXACT', 0)} |",
        f"| EQUIVALENT | {cc.get('EQUIVALENT', 0)} |",
        f"| WRONG_ADAPTER | {cc.get('WRONG_ADAPTER', 0)} |",
        f"| WRONG_DEVICE | {cc.get('WRONG_DEVICE', 0)} |",
        f"| WRONG_MEMBER | {cc.get('WRONG_MEMBER', 0)} |",
        f"| WRONG_SLOT | {cc.get('WRONG_SLOT', 0)} |",
        f"| WRONG_BIT | {cc.get('WRONG_BIT', 0)} |",
        f"| SHOULD_BE_PLACEHOLDER | {cc.get('SHOULD_BE_PLACEHOLDER', 0)} |",
        f"| RUN_UNRESOLVED | {cc.get('RUN_UNRESOLVED', 0)} |",
        "",
        "## Controller scope",
        "",
        f"| Scope | Count |",
        f"|-------|------:|",
    ]
    for k, v in (scope.get("counts") or {}).items():
        lines.append(f"| {k} | {v} |")
    sample_local = (scope.get("by_scope") or {}).get("LOCAL") or []
    sample_ext = (scope.get("by_scope") or {}).get("EXTERNAL_REFERENCE") or []
    lines += [
        "",
        f"- LOCAL sample: {', '.join(sample_local[:12])}",
        f"- EXTERNAL_REFERENCE sample: {', '.join(sample_ext[:8])}",
        "",
        "## Device objects (LOCAL conveyors)",
        "",
        f"| Family | Generated among LOCAL |",
        f"|--------|----------------------:|",
        f"| Local conveyors | {local_n} |",
        f"| Conv | {conv_gen} |",
        f"| Conv_AOI | {aoi_gen} |",
        f"| MS | {ms_gen} |",
        f"| VFD | {vfd_gen} |",
        f"| PE | {pe_gen} |",
        "",
        "## P123 seed case",
        "",
        f"| Object / routine | Status |",
        f"|-----------------|--------|",
        f"| Conv | {(fam.get('Conv') or {}).get('result')} (gen={(fam.get('Conv') or {}).get('generated')}) |",
        f"| Conv_AOI | {(fam.get('Conv_AOI') or {}).get('result')} (gen={(fam.get('Conv_AOI') or {}).get('generated')}) |",
        f"| MS | {(fam.get('MS') or {}).get('result')} (gen={(fam.get('MS') or {}).get('generated')}) |",
        f"| Fast | {(rt.get('Fast') or {}).get('result')} (gen={(rt.get('Fast') or {}).get('generated')}) |",
        f"| Slow_Flt | {(rt.get('Slow_Flt') or {}).get('result')} (gen={(rt.get('Slow_Flt') or {}).get('generated')}) |",
        f"| Slow_Jam | {(rt.get('Slow_Jam') or {}).get('result')} (gen={(rt.get('Slow_Jam') or {}).get('generated')}) |",
        f"| L1 | {(rt.get('L1') or {}).get('result')} (gen={(rt.get('L1') or {}).get('generated')}) |",
        f"| L2 | {(rt.get('L2') or {}).get('result')} (gen={(rt.get('L2') or {}).get('generated')}) |",
        "",
        "## Connectivity",
        "",
        f"- Required relationship checks: **{(connectivity.get('aggregate') or {}).get('required')}**",
        f"- Generated OK: **{(connectivity.get('aggregate') or {}).get('generated_ok')}**",
        f"- Generated missing: **{(connectivity.get('aggregate') or {}).get('generated_missing')}**",
        f"- Coverage: **{connectivity.get('coverage')}**",
        "",
        "## Artifacts",
        "",
        "- `exports/plc2-fidelity/channel_matrix.json`",
        "- `exports/plc2-fidelity/false_placeholder_audit.json`",
        "- `exports/plc2-fidelity/device_object_matrix.json`",
        "- `exports/plc2-fidelity/routine_participation.json`",
        "- `exports/plc2-fidelity/controller_scope.json`",
        "- `exports/plc2-fidelity/connectivity_comparison.json`",
        "",
    ]
    path = out / "report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PLC2 fidelity audit (ORNCCP2)")
    ap.add_argument(
        "--run-dir",
        type=Path,
        default=ROOT / "workspace" / "active" / "RUN",
    )
    ap.add_argument(
        "--finished",
        type=Path,
        default=ROOT / "workspace" / "validation" / "ORLY_GreensboroPLC2_NC_Finished.L5X",
    )
    ap.add_argument(
        "--generated",
        type=Path,
        default=ROOT / "exports" / "plc2-configio-compiler" / "ORNCCP2_configio_candidate.L5X",
    )
    ap.add_argument("--out", type=Path, default=ROOT / "exports" / "plc2-fidelity")
    ap.add_argument("--machine", default="ORNCCP2")
    args = ap.parse_args(argv)

    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    run_dir = args.run_dir if args.run_dir.is_absolute() else ROOT / args.run_dir
    if (run_dir / "RUN" / "project.cfg").is_file():
        run_dir = run_dir / "RUN"
    gen_path = args.generated if args.generated.is_absolute() else ROOT / args.generated
    fin_path = args.finished if args.finished.is_absolute() else ROOT / args.finished

    if not gen_path.is_file():
        # Fall back to autogen path or generate
        alt = ROOT / "exports" / "plc2-configio-compiler" / "autogen" / "OReillyGreensboro_ORNCCP2.L5X"
        if alt.is_file():
            gen_path = alt
        else:
            autogen_out = out / "autogen"
            autogen_out.mkdir(parents=True, exist_ok=True)
            from fortna_runtime_acceptance_recovery import _py, _run

            r = _run(
                _py()
                + [
                    str(SCRIPTS / "fortna_autogen.py"),
                    "from-run",
                    "--run-dir",
                    str(run_dir),
                    "--with-io-map",
                    "--out-dir",
                    str(autogen_out),
                ]
            )
            cand = list(autogen_out.glob("*.L5X"))
            cand = [p for p in cand if "Library" not in p.name]
            if not cand:
                print("ERROR: no generated L5X", r.get("stderr") or r.get("stdout"))
                return 1
            gen_path = cand[0]

    # Copy generated into fidelity folder for traceability
    fidelity_l5x = out / "ORNCCP2_fidelity_candidate.L5X"
    if gen_path.resolve() != fidelity_l5x.resolve():
        shutil.copy2(gen_path, fidelity_l5x)

    gen_text = gen_path.read_text(encoding="utf-8", errors="replace")
    fin_text = fin_path.read_text(encoding="utf-8", errors="replace")

    print("[fidelity] building controller scope…")
    scope = build_controller_scope(run_dir, args.machine)
    write_controller_scope(scope, out / "controller_scope.json")

    print("[fidelity] building IO evidence graph…")
    graph = build_io_evidence_graph(run_dir, args.machine)

    print("[fidelity] channel matrix…")
    channel_matrix = build_channel_matrix(gen_text, fin_text, graph)
    write_json(out / "channel_matrix.json", channel_matrix)

    false_ph = build_false_placeholder_audit(channel_matrix)
    write_json(out / "false_placeholder_audit.json", false_ph)

    local = list((scope.get("by_scope") or {}).get("LOCAL") or [])
    meta = _conveyor_meta(run_dir, set(local))

    print("[fidelity] device object matrix…")
    device_matrix = build_device_object_matrix(
        local=local, meta=meta, gen_text=gen_text, fin_text=fin_text
    )
    write_json(out / "device_object_matrix.json", device_matrix)

    print("[fidelity] routine participation…")
    routines = build_routine_participation(
        local=local, meta=meta, gen_text=gen_text, fin_text=fin_text
    )
    write_json(out / "routine_participation.json", routines)

    gen_part = {
        r["conveyor"]: {k: v["generated"] for k, v in (r.get("routines") or {}).items()}
        for r in routines.get("conveyors") or []
    }
    fin_part = {
        r["conveyor"]: {k: v["finished"] for k, v in (r.get("routines") or {}).items()}
        for r in routines.get("conveyors") or []
    }

    print("[fidelity] connectivity comparison…")
    connectivity = build_connectivity_comparison(
        local=local,
        meta=meta,
        gen_text=gen_text,
        fin_text=fin_text,
        gen_part=gen_part,
        fin_part=fin_part,
    )
    write_json(out / "connectivity_comparison.json", connectivity)

    report = write_report(
        out,
        channel_matrix=channel_matrix,
        false_ph=false_ph,
        device_matrix=device_matrix,
        routines=routines,
        scope=scope,
        connectivity=connectivity,
        gen_path=gen_path,
        fin_path=fin_path,
    )

    summary = {
        "generated_at": _ts(),
        "ok": True,
        "machine": args.machine,
        "generated_l5x": str(gen_path),
        "finished_l5x": str(fin_path),
        "channel_counts": channel_matrix.get("counts"),
        "false_placeholders": false_ph.get("count"),
        "io_summary": channel_matrix.get("summary"),
        "controller_scope": scope.get("counts"),
        "P123": {
            "device": device_matrix.get("P123"),
            "routines": routines.get("P123"),
        },
        "connectivity_coverage": connectivity.get("coverage"),
        "report": str(report),
    }
    write_json(out / "summary.json", summary)
    print(json.dumps({k: summary[k] for k in summary if k != "P123"}, indent=2))
    print(f"Wrote {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

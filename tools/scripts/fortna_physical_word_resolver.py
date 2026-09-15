#!/usr/bin/env python3
"""Configio-primary physical Fortna word → RIO channel resolver (Greensboro-style).

Maps Configio.asc Octal_Word + Desc (PANEL-CATALOG-INDEX) onto eipcfg adapters/modules
to produce CP2RIO*/CP3RIO* channels. Does NOT hard-code word→adapter tables.

Data index scheme is FAMILY-AWARE (see fortna_hardware_family):
  1794 Flex: eipcfg bridged module at chassis slot S>0 → Logix Data[S-1]
             (head/AENT is slot 0; 2PBSTART word 201 bit0 → Data[1] with IA16-3 at slot 2).
  1734 POINT: keep chassis slot (print-accurate) — never apply Flex slot-1 shift.
  Unknown: raw slot — never silently assume 1794.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any

from fortna_hardware_family import (  # noqa: E402
    FAMILY_FLEX,
    FAMILY_POINT,
    FAMILY_UNKNOWN,
    adapter_family_from_modules,
    data_index_for_module as _family_data_index,
    detect_family_from_catalog,
    family_scheme_description,
    max_bits_for_catalog,
)

# PANEL-CATALOG-INDEX — allow missing hyphen after panel (CP31794-IA16-31)
_DESC_RE = re.compile(
    r"^(?P<panel>CP\d+)\s*-?\s*(?P<catalog>\d{4}-[A-Za-z0-9]+)\s*-?\s*(?P<index>\d+)\s*$",
    re.I,
)
_PANEL_RE = re.compile(r"^(CP\d+)", re.I)


def _normalize_run_dir(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    if (run_dir / "RUN" / "project.cfg").is_file():
        return run_dir / "RUN"
    return run_dir


def _module_direction(catalog_or_type: str) -> str:
    u = (catalog_or_type or "").upper()
    if any(x in u for x in ("IA", "IB", "IM")):
        return "I"
    if any(x in u for x in ("OA", "OB", "OW")):
        return "O"
    return ""


def _sanitize_adapter_fallback(name: str) -> str:
    t = re.sub(r"[^A-Za-z0-9_]", "_", (name or "").strip())
    t = re.sub(r"_+", "_", t).strip("_")
    if not t:
        return "RIO"
    if t[0].isdigit():
        t = f"T_{t}"
    return t[:40]


def parse_configio_desc(desc: str) -> dict[str, Any] | None:
    """Parse Greensboro Desc like CP2-1794-IA16-3 or CP31794-IA16-31."""
    d = (desc or "").strip()
    if not d:
        return None
    m = _DESC_RE.match(d)
    if not m:
        return None
    panel = m.group("panel").upper()
    catalog = m.group("catalog")
    index = m.group("index")
    return {
        "panel": panel,
        "catalog": catalog,
        "type": catalog,
        "index": index,
        "module_name": f"{catalog}-{index}",
        "direction": _module_direction(catalog),
        "raw": d,
    }


def _find_eipcfg(run_dir: Path, machine: str) -> Path | None:
    fortna = run_dir / "FORTNA"
    mach = (machine or "").strip()
    candidates: list[Path] = []
    if mach:
        candidates.append(fortna / f"{mach}-RTA-eipcfg.xml")
        candidates.extend(sorted(fortna.glob(f"{mach}*eipcfg*.xml")))
    candidates.extend(sorted(fortna.glob("*-RTA-eipcfg.xml")))
    candidates.extend(sorted(fortna.glob("*eipcfg*.xml")))
    for p in candidates:
        if p.is_file():
            return p
    return None


def _load_configio_rows(run_dir: Path, machine: str) -> list[dict[str, Any]]:
    from fortna_asc import read_asc

    fortna = run_dir / "FORTNA"
    mach = (machine or "").strip()
    candidates: list[Path] = []
    if mach:
        candidates.append(fortna / f"Configio.asc.{mach}")
    candidates.append(fortna / "Configio.asc")
    path = next((p for p in candidates if p.is_file()), None)
    if not path:
        return []
    try:
        _, rows = read_asc(path)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows):
        try:
            octal = int(float(r.get("Octal_Word") or 0))
        except (TypeError, ValueError):
            continue
        if octal <= 0:
            continue
        iface = (r.get("Interface") or "").strip().upper()
        if iface and iface != "RTA":
            continue
        try:
            bank = int(float(r.get("Bank") or -1))
        except (TypeError, ValueError):
            bank = -1
        desc = (r.get("Desc") or "").strip()
        out.append(
            {
                "row": i,
                "octal_word": octal,
                "bank": bank,
                "lohi": (r.get("LoHi") or "").strip() or "Low",
                "desc": desc,
                "in_out": (r.get("In_Out") or "").strip(),
                "interface": iface or "RTA",
                "parsed": parse_configio_desc(desc),
            }
        )
    return out


def _data_index_for_module(slot: int, family: str | None = None) -> int:
    """Logix Data[] index for a bridged module — family-aware (no silent 1794 default)."""
    fam = (family or "").strip() or None
    return _family_data_index(slot, fam)


def parse_eipcfg(run_dir: Path, machine: str = "") -> dict[str, Any]:
    """Parse ORNCCP*-RTA-eipcfg.xml and assign display rio_name from Configio panels.

    Returns adapters with modules, targetip, input_address, output_address, rio_name.
    """
    run_dir = _normalize_run_dir(run_dir)
    if not machine:
        try:
            from fortna_io_extract import read_project_meta

            machine = (read_project_meta(run_dir).get("machine_name") or "").strip()
        except Exception:
            machine = ""

    eipcfg_path = _find_eipcfg(run_dir, machine)
    adapters: list[dict[str, Any]] = []
    if eipcfg_path and eipcfg_path.is_file():
        root = ET.parse(eipcfg_path).getroot()
        for ai, a in enumerate(root.findall(".//Adapter")):
            name = (a.attrib.get("name") or f"adapter_{ai}").strip()
            modules: list[dict[str, Any]] = []
            for m in a.findall("Module"):
                try:
                    slot = int(float(m.attrib.get("slot") or 0))
                except (TypeError, ValueError):
                    slot = 0
                mt = (m.attrib.get("type") or "").strip()
                mname = (m.attrib.get("name") or "").strip()
                conn = (m.attrib.get("connection") or "").strip()
                family = detect_family_from_catalog(mt) or detect_family_from_catalog(mname)
                if family == FAMILY_UNKNOWN:
                    # Do not invent FLEX — leave UNKNOWN so callers cannot silently
                    # apply 1794 word/channel assumptions.
                    family = FAMILY_UNKNOWN
                modules.append(
                    {
                        "name": mname,
                        "type": mt,
                        "slot": slot,
                        "connection": conn,
                        "direction": _module_direction(mt),
                        "family": family,
                        "data_index": _data_index_for_module(slot, family),
                    }
                )
            adapters.append(
                {
                    "name": name,
                    "targetip": (a.attrib.get("targetip") or "").strip(),
                    "input_address": a.attrib.get("InputAddress") or a.attrib.get("inputaddress") or "",
                    "output_address": a.attrib.get("OutputAddress") or a.attrib.get("outputaddress") or "",
                    "modules": modules,
                    "family": adapter_family_from_modules(modules),
                    "adapter_index": ai,
                }
            )

    configio_rows = _load_configio_rows(run_dir, machine)
    # Panel evidence from Configio Desc prefixes (RUN evidence for CP2/CP3 naming)
    panel_order: list[str] = []
    panel_word_dirs: dict[str, dict[str, set[int]]] = defaultdict(
        lambda: {"I": set(), "O": set()}
    )
    # module name → set of panels that reference it via Desc
    module_panels: dict[str, set[str]] = defaultdict(set)
    for row in configio_rows:
        parsed = row.get("parsed")
        if not parsed:
            continue
        panel = parsed["panel"]
        if panel not in panel_order:
            panel_order.append(panel)
        direction = parsed.get("direction") or ""
        if direction in ("I", "O"):
            panel_word_dirs[panel][direction].add(int(row["octal_word"]))
        module_panels[parsed["module_name"].upper()].add(panel)

    # Score each adapter by which panel Descs reference its modules (name hits)
    adapter_panel_scores: list[dict[str, int]] = []
    for ad in adapters:
        scores: dict[str, int] = defaultdict(int)
        for mod in ad.get("modules") or []:
            if (mod.get("connection") or "").upper() == "HEADNODE":
                continue
            if "AENT" in (mod.get("type") or "").upper():
                continue
            hits = module_panels.get((mod.get("name") or "").upper()) or set()
            for p in hits:
                scores[p] += 1
        adapter_panel_scores.append(dict(scores))

    # Capacity-pack adapters onto panels using Configio word counts (generic).
    # Each Fortna word consumes one physical module of matching direction.
    panel_need: dict[str, int] = {
        p: len(panel_word_dirs[p]["I"]) + len(panel_word_dirs[p]["O"])
        for p in panel_order
    }
    adapter_capacity = []
    for ad in adapters:
        bridged = [
            m
            for m in (ad.get("modules") or [])
            if (m.get("connection") or "").upper() != "HEADNODE"
            and "AENT" not in (m.get("type") or "").upper()
        ]
        adapter_capacity.append(len(bridged))

    assigned_panel: list[str | None] = [None] * len(adapters)
    if panel_order and adapters:
        # Prefer packing by capacity in adapter order; fall back to majority name-hit.
        ai = 0
        for panel in panel_order:
            need = panel_need.get(panel, 0)
            got = 0
            while ai < len(adapters) and got < need:
                assigned_panel[ai] = panel
                got += adapter_capacity[ai]
                ai += 1
        # leftover adapters: assign by name-hit majority or last panel
        while ai < len(adapters):
            scores = adapter_panel_scores[ai]
            if scores:
                assigned_panel[ai] = max(scores.items(), key=lambda kv: kv[1])[0]
            else:
                assigned_panel[ai] = panel_order[-1] if panel_order else None
            ai += 1
    elif adapters:
        # No Configio panel evidence — sanitized eipcfg names only
        assigned_panel = [None] * len(adapters)

    # Assign CP2RIO0, CP2RIO1, CP3RIO0... within each panel in adapter order
    panel_rio_counters: dict[str, int] = defaultdict(int)
    for i, ad in enumerate(adapters):
        panel = assigned_panel[i]
        if panel:
            n = panel_rio_counters[panel]
            rio = f"{panel}RIO{n}"
            panel_rio_counters[panel] = n + 1
            naming_how = "configio_panel_prefix"
        else:
            rio = _sanitize_adapter_fallback(ad.get("name") or f"adapter_{i}")
            naming_how = "eipcfg_sanitized"
        ad["rio_name"] = rio
        ad["panel"] = panel
        ad["naming_how"] = naming_how
        for mod in ad.get("modules") or []:
            mod["rio_name"] = rio
            mod["panel"] = panel

    return {
        "machine": machine,
        "eipcfg_path": str(eipcfg_path) if eipcfg_path else None,
        "adapters": adapters,
        "panel_order": panel_order,
        "panel_need": panel_need,
        "configio_row_count": len(configio_rows),
        "data_index_scheme": (
            "family-aware: 1794 Flex Data[slot-1] when slot>0; "
            "1734 POINT Data[slot] (no Flex shift); unknown → raw slot"
        ),
    }


def _find_module_by_name(
    adapters: list[dict[str, Any]], module_name: str, catalog: str
) -> dict[str, Any] | None:
    want = (module_name or "").upper()
    cat_u = (catalog or "").upper()
    idx = want.rsplit("-", 1)[-1] if "-" in want else ""
    for ad in adapters:
        for mod in ad.get("modules") or []:
            if (mod.get("connection") or "").upper() == "HEADNODE":
                continue
            name = (mod.get("name") or "").upper()
            mt = (mod.get("type") or "").upper()
            if name == want:
                return {**mod, "adapter_name": ad.get("name"), "rio_name": ad.get("rio_name"),
                        "panel": ad.get("panel"), "adapter_index": ad.get("adapter_index")}
            if idx and name.endswith(f"-{idx}") and (
                mt == cat_u or cat_u in name or mt in cat_u
            ):
                return {**mod, "adapter_name": ad.get("name"), "rio_name": ad.get("rio_name"),
                        "panel": ad.get("panel"), "adapter_index": ad.get("adapter_index")}
    return None


def build_physical_word_map(run_dir: Path, machine: str = "") -> dict[str, Any]:
    """Build Octal_Word → physical channel map from Configio + eipcfg.

    Primary assignment: panel from Configio Desc + sequential modules within that
    panel's adapters (direction-matched). Name match (Desc → eipcfg module name)
    is attempted for provenance and accepted only when it agrees with the sequential
    module for that word (Desc indices often diverge from eipcfg name suffixes).

    High-half Desc missing → use Low half module with bit_half=high.
    """
    run_dir = _normalize_run_dir(run_dir)
    topology = parse_eipcfg(run_dir, machine)
    adapters = list(topology.get("adapters") or [])
    configio_rows = _load_configio_rows(run_dir, machine or topology.get("machine") or "")

    # Group configio halves by word
    by_word: dict[int, dict[str, dict]] = defaultdict(dict)
    for row in configio_rows:
        w = int(row["octal_word"])
        side = (row.get("lohi") or "Low").strip().title()
        if side not in ("Low", "High"):
            side = "Low" if "high" not in side.lower() else "High"
        by_word[w][side] = row

    # Panel → adapters in order
    panel_adapters: dict[str, list[dict]] = defaultdict(list)
    for ad in adapters:
        p = ad.get("panel")
        if p:
            panel_adapters[p].append(ad)

    # Sequential module pools per panel+direction
    def _bridged_mods(ad: dict) -> list[dict]:
        out = []
        for mod in sorted(ad.get("modules") or [], key=lambda m: int(m.get("slot") or 0)):
            if (mod.get("connection") or "").upper() == "HEADNODE":
                continue
            if "AENT" in (mod.get("type") or "").upper():
                continue
            out.append(
                {
                    **mod,
                    "adapter_name": ad.get("name"),
                    "rio_name": ad.get("rio_name"),
                    "panel": ad.get("panel"),
                    "adapter_index": ad.get("adapter_index"),
                }
            )
        return out

    panel_dir_mods: dict[str, dict[str, list[dict]]] = {}
    for panel, ads in panel_adapters.items():
        pool_i: list[dict] = []
        pool_o: list[dict] = []
        for ad in ads:
            for mod in _bridged_mods(ad):
                d = mod.get("direction") or _module_direction(mod.get("type") or "")
                if d == "I":
                    pool_i.append(mod)
                elif d == "O":
                    pool_o.append(mod)
        panel_dir_mods[panel] = {"I": pool_i, "O": pool_o}

    # Words per panel+direction in ascending octal order (sequential zip target)
    panel_dir_words: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: {"I": [], "O": []}
    )
    for w, halves in sorted(by_word.items()):
        low = halves.get("Low") or halves.get("High") or {}
        parsed = (low.get("parsed") if low else None) or (
            (halves.get("High") or {}).get("parsed")
        )
        if not parsed:
            # try any half
            for h in halves.values():
                if h.get("parsed"):
                    parsed = h["parsed"]
                    break
        if not parsed:
            continue
        panel = parsed["panel"]
        direction = parsed.get("direction") or ""
        if not direction:
            # Infer from In_Out mask / catalog on either half
            for h in halves.values():
                p2 = h.get("parsed") or {}
                direction = p2.get("direction") or ""
                if direction:
                    break
        if direction not in ("I", "O"):
            continue
        panel_dir_words[panel][direction].append(w)

    # Zip-assign word → module
    word_module: dict[int, dict[str, Any]] = {}
    for panel, dirs in panel_dir_words.items():
        pools = panel_dir_mods.get(panel) or {"I": [], "O": []}
        for direction, words in dirs.items():
            mods = list(pools.get(direction) or [])
            for i, w in enumerate(words):
                if i < len(mods):
                    word_module[w] = {
                        "module": mods[i],
                        "direction": direction,
                        "panel": panel,
                        "assign_how": "configio_panel_sequential",
                        "seq_index": i,
                    }

    words_out: dict[str, dict[str, Any]] = {}
    by_word_bit: dict[str, dict[str, Any]] = {}
    unresolved: list[dict[str, Any]] = []

    for w, halves in sorted(by_word.items()):
        low = halves.get("Low")
        high = halves.get("High")
        low_p = (low or {}).get("parsed")
        high_p = (high or {}).get("parsed")
        panel = (low_p or high_p or {}).get("panel") or ""
        direction = (low_p or high_p or {}).get("direction") or ""
        if not direction:
            for p in (low_p, high_p):
                if p and p.get("direction"):
                    direction = p["direction"]
                    break

        # Name-match attempts (Low preferred; High if Low missing)
        name_hit = None
        name_side = None
        bit_half_default = "low"
        for side, row in (("Low", low), ("High", high)):
            if not row or not row.get("parsed"):
                continue
            p = row["parsed"]
            hit = _find_module_by_name(adapters, p["module_name"], p["catalog"])
            if hit:
                name_hit = hit
                name_side = side
                break
        # High missing → use Low module, bit_half=high (task rule)
        if low_p and not high_p:
            pass
        elif high_p and not (_find_module_by_name(
            adapters, high_p["module_name"], high_p["catalog"]
        )) and low_p:
            low_hit = _find_module_by_name(adapters, low_p["module_name"], low_p["catalog"])
            if low_hit and not name_hit:
                name_hit = low_hit
                name_side = "Low"
                bit_half_default = "high"

        seq = word_module.get(w)
        chosen = None
        assign_how = ""
        if seq:
            chosen = seq["module"]
            assign_how = seq["assign_how"]
            direction = seq["direction"] or direction
            panel = seq["panel"] or panel
            # Corroborate name match when it points at the same module
            if name_hit and (
                (name_hit.get("name") or "").upper() == (chosen.get("name") or "").upper()
                and name_hit.get("rio_name") == chosen.get("rio_name")
            ):
                assign_how = "configio_desc_name+sequential"
        elif name_hit and (not panel or name_hit.get("panel") == panel or not name_hit.get("panel")):
            # Sequential unavailable — accept name match (still Configio Desc driven)
            chosen = name_hit
            assign_how = "configio_desc_name"
            if name_side == "High" and bit_half_default == "high":
                pass
            direction = direction or name_hit.get("direction") or ""
            panel = panel or name_hit.get("panel") or ""
        elif name_hit:
            # Name hit on foreign panel — keep as provenance only; still unresolved channel
            pass

        if not chosen:
            unresolved.append(
                {
                    "octal_word": w,
                    "panel": panel,
                    "direction": direction,
                    "low_desc": (low or {}).get("desc"),
                    "high_desc": (high or {}).get("desc"),
                    "name_hit": (name_hit or {}).get("name") if name_hit else None,
                }
            )
            continue

        eip_slot = int(chosen.get("slot") or 0)
        family = (
            chosen.get("family")
            or detect_family_from_catalog(chosen.get("type") or "")
            or FAMILY_UNKNOWN
        )
        data_index = int(
            chosen.get("data_index")
            if chosen.get("data_index") is not None
            else _data_index_for_module(eip_slot, family)
        )
        rio = chosen.get("rio_name") or ""
        mod_type = chosen.get("type") or ""
        channel_base = f"{rio}:{direction}.Data[{data_index}]"

        entry = {
            "octal_word": w,
            "rio_name": rio,
            "direction": direction,
            "flex_slot": data_index,  # IO_MAP Data[] index
            "data_index": data_index,
            "eip_slot": eip_slot,
            "type": mod_type,
            "module_name": chosen.get("name") or "",
            "panel": panel,
            "family": family,
            "child_name": f"{rio}_{data_index}",
            "resolve_how": "configio_physical",
            "assign_how": assign_how,
            "channel_base": channel_base,
            "bit_half_default": bit_half_default,
            "low_desc": (low or {}).get("desc"),
            "high_desc": (high or {}).get("desc"),
            "low_bank": (low or {}).get("bank"),
            "high_bank": (high or {}).get("bank"),
            "name_match_module": (name_hit or {}).get("name") if name_hit else None,
            "name_match_agrees": bool(
                name_hit
                and (name_hit.get("name") or "").upper()
                == (chosen.get("name") or "").upper()
            ),
            "provenance": {
                "source_tables": ["Configio.asc", "eipcfg"],
                "configio_panel": panel,
                "eipcfg_adapter": chosen.get("adapter_name"),
                "eipcfg_module": chosen.get("name"),
                "eipcfg_slot": eip_slot,
                "data_index_scheme": topology.get("data_index_scheme"),
                "assign_how": assign_how,
            },
        }
        words_out[str(w)] = entry

        # Bit fan-out from catalog capacity (POINT 4/8-pt must not assume 16)
        max_bits = max_bits_for_catalog(mod_type)
        for bit in range(max_bits):
            bit_half = "high" if bit >= 8 else "low"
            channel = f"{channel_base}.{bit}"
            by_word_bit[f"{w}:{bit}"] = {
                **entry,
                "bit": bit,
                "bit_half": bit_half,
                "channel": channel,
            }

    # Autogen-compatible word_map (str word → resolve info)
    io_word_map = {
        w: {
            "rio_name": e["rio_name"],
            "child_name": e["child_name"],
            "flex_slot": e["flex_slot"],
            "eip_slot": e.get("eip_slot"),
            "type": e["type"],
            "catalog": e["type"],
            "direction": e["direction"],
            "family": e.get("family") or FAMILY_UNKNOWN,
            "resolve_how": "configio_physical",
            "panel": e.get("panel"),
            "module_name": e.get("module_name"),
            "provenance": e.get("provenance"),
        }
        for w, e in words_out.items()
    }

    return {
        "machine": topology.get("machine") or machine,
        "eipcfg_path": topology.get("eipcfg_path"),
        "data_index_scheme": topology.get("data_index_scheme"),
        "adapters": [
            {
                "name": a.get("name"),
                "rio_name": a.get("rio_name"),
                "panel": a.get("panel"),
                "targetip": a.get("targetip"),
                "input_address": a.get("input_address"),
                "output_address": a.get("output_address"),
                "naming_how": a.get("naming_how"),
                "family": a.get("family")
                or adapter_family_from_modules(a.get("modules") or []),
                "modules": [
                    {
                        "name": m.get("name"),
                        "type": m.get("type"),
                        "slot": m.get("slot"),
                        "data_index": m.get("data_index"),
                        "direction": m.get("direction"),
                        "connection": m.get("connection"),
                        "family": m.get("family")
                        or detect_family_from_catalog(m.get("type") or ""),
                    }
                    for m in (a.get("modules") or [])
                ],
            }
            for a in adapters
        ],
        "words": words_out,
        "by_word_bit": by_word_bit,
        "io_word_map": io_word_map,
        "unresolved": unresolved,
        "stats": {
            "adapter_count": len(adapters),
            "word_count": len(words_out),
            "unresolved_count": len(unresolved),
            "by_word_bit_count": len(by_word_bit),
            "rio_names": [a.get("rio_name") for a in adapters],
        },
    }


def resolve_word_bit(
    physical_map: dict[str, Any], word: int | str, bit: int | str
) -> dict[str, Any] | None:
    """Lookup physical channel for a Fortna word/bit."""
    try:
        w = int(float(str(word).strip()))
    except (TypeError, ValueError):
        return None
    try:
        b_raw = str(bit).strip()
        if not b_raw:
            return None
        # octal-ish 10-17 → 8-15
        try:
            bv = int(b_raw, 8) if re.fullmatch(r"[0-7]+", b_raw) and len(b_raw) <= 2 else int(b_raw, 10)
        except ValueError:
            bv = int(float(b_raw))
        if 10 <= int(b_raw) <= 17 and not re.fullmatch(r"[0-7]+", b_raw):
            # decimal 10-17 already
            bv = int(b_raw)
        elif re.fullmatch(r"[0-7]+", b_raw) and int(b_raw, 8) >= 8:
            bv = int(b_raw, 8)
        elif 0 <= int(float(b_raw)) <= 15:
            bv = int(float(b_raw))
            if 10 <= bv <= 17:
                # Conveyor often stores octal 10-17 as decimal integers 10-17
                bv = 8 + (bv - 10)
    except (TypeError, ValueError):
        return None

    # Prefer explicit index; fall back to raw bit
    key = f"{w}:{bv}"
    hit = (physical_map.get("by_word_bit") or {}).get(key)
    if hit:
        return hit
    # try without octal remap
    try:
        raw_b = int(float(str(bit).strip()))
    except (TypeError, ValueError):
        return None
    return (physical_map.get("by_word_bit") or {}).get(f"{w}:{raw_b}")


def physical_map_to_topology(physical_map: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert resolver adapters into fortna_autogen eip_topology children shape.

    Preserves proven hardware FAMILY — never hardcodes 1794 for POINT racks.
    """
    topo: list[dict[str, Any]] = []
    for ad in physical_map.get("adapters") or []:
        ad_family = (
            ad.get("family")
            or adapter_family_from_modules(ad.get("modules") or [])
            or FAMILY_UNKNOWN
        )
        children = []
        for m in ad.get("modules") or []:
            if (m.get("connection") or "").upper() == "HEADNODE":
                continue
            if "AENT" in (m.get("type") or "").upper():
                continue
            eip_slot = int(m.get("slot") or 0)
            m_family = (
                m.get("family")
                or detect_family_from_catalog(m.get("type") or "")
                or ad_family
            )
            data_index = int(
                m.get("data_index")
                if m.get("data_index") is not None
                else _data_index_for_module(eip_slot, m_family)
            )
            children.append(
                {
                    "name": f"{ad.get('rio_name')}_{data_index}",
                    "type": m.get("type") or "",
                    "catalog": m.get("type") or "",
                    "eip_slot": eip_slot,
                    "flex_slot": data_index,
                    "direction": m.get("direction") or _module_direction(m.get("type") or ""),
                    "family": m_family,
                    "module_name": m.get("name") or "",
                }
            )
        topo.append(
            {
                "rio_name": ad.get("rio_name"),
                "name": ad.get("name"),
                "ip": ad.get("targetip") or "",
                "rack": ad.get("panel") or "",
                "family": ad_family,
                "panel": ad.get("panel"),
                "naming_how": ad.get("naming_how"),
                "children": children,
            }
        )
    return topo


def write_physical_word_map_json(physical_map: dict[str, Any], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # by_word_bit can be large — keep it (needed for tests/lookup)
    path.write_text(json.dumps(physical_map, indent=2), encoding="utf-8")
    return path


class PhysicalWordResolver:
    """Convenience wrapper around parse_eipcfg / build_physical_word_map."""

    def __init__(self, run_dir: Path, machine: str = ""):
        self.run_dir = _normalize_run_dir(Path(run_dir))
        self.machine = machine
        self.topology = parse_eipcfg(self.run_dir, machine)
        self.physical_map = build_physical_word_map(self.run_dir, machine or self.topology.get("machine") or "")

    def resolve(self, word: int | str, bit: int | str) -> dict[str, Any] | None:
        return resolve_word_bit(self.physical_map, word, bit)

    def io_word_map(self) -> dict[str, dict]:
        return dict(self.physical_map.get("io_word_map") or {})

    def eip_topology(self) -> list[dict]:
        return physical_map_to_topology(self.physical_map)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Configio-primary physical word resolver")
    ap.add_argument("--run-dir", type=Path, default=Path("workspace/active/RUN"))
    ap.add_argument("--machine", default="ORNCCP2")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    pm = build_physical_word_map(args.run_dir, args.machine)
    out = args.out or Path("exports/plc2-configio-compiler/physical_word_map.json")
    write_physical_word_map_json(pm, out)
    print(json.dumps(pm.get("stats"), indent=2))
    for key in ("201:0", "307:0"):
        print(key, resolve_word_bit(pm, *key.split(":")))

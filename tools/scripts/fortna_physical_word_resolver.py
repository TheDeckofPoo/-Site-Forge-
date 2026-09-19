#!/usr/bin/env python3
"""Configio-primary physical Fortna word → RIO channel resolver (FortnaPlus-style).

Maps Configio.asc Octal_Word + Desc onto eipcfg adapters/modules to produce
CPxRIO* channels. Does NOT hard-code word→adapter tables.

Desc forms:
  PANEL-CATALOG-INDEX (PLC2): CP2-1794-IA16-3 → sequential / name match within panel.
  PANEL-NODE-slotHalf (PLC5): CP5-NODE53-1A → NODE→TargetIP adapter + EIPModules
    InputBank/OutputBank match → chassis Slot (never bank→slot arithmetic alone).
  CATALOG-WORD-BANK (ORINDYAC6 / RTA): 1794-IA16-600-4 → catalog + Fortna word
    corroboration + Configio.Bank ↔ EIPModules InputBank/OutputBank.
  CATALOG-AENT-NODE-BANK: 1794-AENT-51-0 → head/topology only (skip bridged map).

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
# PANEL-NODEnn-slotHalf — PLC5-style (CP5-NODE53-1A / CP5NODE52-7B)
_NODE_DESC_RE = re.compile(
    r"^(?P<panel>CP\d+)\s*-?\s*NODE(?P<node>\d+)\s*-?\s*(?P<slot>\d+)(?P<half>[AB])\s*$",
    re.I,
)
# CATALOG-WORD-BANK — RTA style (1794-IA16-600-4 / 1794-OA8I-613-26)
_CATALOG_WORD_BANK_RE = re.compile(
    r"^(?P<catalog>\d{4}-[A-Za-z0-9]+)-(?P<word>\d+)-(?P<bank>\d+)$",
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
    """Parse Fortna Configio Desc like CP2-1794-IA16-3 or CP31794-IA16-31."""
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
        "form": "panel_catalog",
    }


def parse_configio_node_desc(desc: str) -> dict[str, Any] | None:
    """Parse PLC5-style Desc like CP5-NODE53-1A (panel + EIP node + chassis slot).

    Node number matches EIPAdapters TargetIP last octet (NODE53 → …53 → 1794-AENT-3).
    Slot corroborates EIPModules InputBank/OutputBank on that adapter (never
    bank→slot arithmetic alone). A Desc slot that disagrees with the bank-
    matched module is REVIEW_REQUIRED — do not invent or collapse endpoints.
    """
    d = (desc or "").strip()
    if not d:
        return None
    m = _NODE_DESC_RE.match(d)
    if not m:
        return None
    half = (m.group("half") or "A").upper()
    return {
        "panel": m.group("panel").upper(),
        "node": int(m.group("node")),
        "desc_slot": int(m.group("slot")),
        "half": half,
        "lohi": "Low" if half == "A" else "High",
        "direction": "",  # from EIPModules bank field match
        "raw": d,
        "form": "panel_node",
    }


def parse_configio_catalog_word_bank(desc: str) -> dict[str, Any] | None:
    """Parse RTA-style Desc like 1794-IA16-600-4 or 1794-AENT-51-0.

    catalog-word-bank: Fortna Octal_Word often equals embedded word; Bank column
    matches EIPModules InputBank/OutputBank. AENT rows are head topology only.
    """
    d = (desc or "").strip()
    if not d:
        return None
    m = _CATALOG_WORD_BANK_RE.match(d)
    if not m:
        return None
    catalog = m.group("catalog")
    word = int(m.group("word"))
    bank = int(m.group("bank"))
    is_aent = "AENT" in catalog.upper()
    return {
        "panel": "",  # not encoded — bank match does not need panel
        "catalog": catalog,
        "type": catalog,
        "index": str(bank),
        "module_name": f"{catalog}-{bank}",
        "direction": "" if is_aent else _module_direction(catalog),
        "fortna_word": word,
        "eip_bank": bank,
        "is_aent_head": is_aent,
        "raw": d,
        "form": "catalog_aent_node_bank" if is_aent else "catalog_word_bank",
    }


def configio_desc_evidence(desc: str) -> dict[str, Any] | None:
    """Return best Configio Desc parse (panel forms preferred, then catalog-word-bank)."""
    return (
        parse_configio_desc(desc)
        or parse_configio_node_desc(desc)
        or parse_configio_catalog_word_bank(desc)
    )


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
        # Accept RTA / RTA1 / RTA2… (MSC Reno uses Interface=RTA1). Skip non-RTA buses.
        if iface and not (iface == "RTA" or iface.startswith("RTA")):
            continue
        try:
            bank = int(float(r.get("Bank") or -1))
        except (TypeError, ValueError):
            bank = -1
        desc = (r.get("Desc") or "").strip()
        parsed = parse_configio_desc(desc)
        node_parsed = parse_configio_node_desc(desc)
        catalog_bank = parse_configio_catalog_word_bank(desc)
        # IMPORTANT: do NOT promote catalog_word_bank into `parsed`.
        # Its trailing number is Configio.Bank / EIPModules bank, NOT an eipcfg
        # module-name suffix. Putting it in `parsed.module_name` caused false
        # name matches (1794-IA16-4 → slot 3 / Data[2] instead of bank 4 → Data[0]).
        out.append(
            {
                "row": i,
                "octal_word": octal,
                "bank": bank,
                "lohi": (r.get("LoHi") or "").strip() or "Low",
                "desc": desc,
                "in_out": (r.get("In_Out") or "").strip(),
                "interface": iface or "RTA",
                "parsed": parsed,
                "node_parsed": node_parsed,
                "catalog_bank_parsed": catalog_bank,
            }
        )
    return out


def _find_eipmodules(run_dir: Path, machine: str = "") -> Path | None:
    proj = run_dir / "PROJECT"
    if not proj.is_dir():
        return None
    mach = (machine or "").strip()
    candidates: list[Path] = []
    if mach:
        candidates.append(proj / f"EIPModules.asc.{mach}")
    candidates.extend(sorted(proj.glob("EIPModules.asc*")))
    for p in candidates:
        if p.is_file():
            return p
    return None


def _load_eipmodules_rows(run_dir: Path, machine: str = "") -> list[dict[str, Any]]:
    """Load EIPModules.asc* bridged cards with InputBank/OutputBank/Slot."""
    from fortna_asc import read_asc

    path = _find_eipmodules(run_dir, machine)
    if not path:
        return []
    try:
        _, rows = read_asc(path)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for r in rows:
        name = (r.get("Name") or "").strip()
        adapter = (r.get("Adapter") or "").strip()
        mt = (r.get("Type") or "").strip()
        conn = (r.get("Connection") or "").strip()
        if not adapter or adapter.upper() in ("N/A", "INVALID"):
            continue
        if not mt or mt.upper() in ("N/A", "INVALID"):
            continue
        if conn.upper() == "HEADNODE" or "AENT" in mt.upper():
            continue
        try:
            slot = int(float(r.get("Slot") or 0))
        except (TypeError, ValueError):
            slot = 0
        try:
            ib = int(float(r.get("InputBank") or 0))
        except (TypeError, ValueError):
            ib = 0
        try:
            ob = int(float(r.get("OutputBank") or 0))
        except (TypeError, ValueError):
            ob = 0
        direction = _module_direction(mt)
        out.append(
            {
                "name": name,
                "adapter": adapter,
                "type": mt,
                "slot": slot,
                "connection": conn or "BRIDGED",
                "input_bank": ib,
                "output_bank": ob,
                "direction": direction,
            }
        )
    return out


def _enrich_adapters_with_eipmodules(
    adapters: list[dict[str, Any]], eip_rows: list[dict[str, Any]]
) -> None:
    """Attach EIPModules InputBank/OutputBank onto matching eipcfg modules by slot."""
    by_adapter: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in eip_rows:
        ad = (row.get("adapter") or "").strip()
        if ad:
            by_adapter[ad].append(row)
            by_adapter[ad.replace("-", "_")].append(row)
            by_adapter[ad.replace("_", "-")].append(row)
    for ad in adapters:
        name = (ad.get("name") or "").strip()
        mods = ad.get("modules") or []
        rows = by_adapter.get(name) or by_adapter.get(name.replace("_", "-")) or []
        if not rows:
            continue
        by_slot = {int(r.get("slot") or -1): r for r in rows}
        for mod in mods:
            if (mod.get("connection") or "").upper() == "HEADNODE":
                continue
            try:
                slot = int(mod.get("slot") or -1)
            except (TypeError, ValueError):
                continue
            hit = by_slot.get(slot)
            if not hit:
                continue
            # EIPModules banks are authoritative for Configio Bank matching
            if hit.get("input_bank") is not None:
                mod["input_bank"] = int(hit["input_bank"])
            if hit.get("output_bank") is not None:
                mod["output_bank"] = int(hit["output_bank"])


def _adapter_for_node(
    adapters: list[dict[str, Any]], node: int
) -> dict[str, Any] | None:
    """Map Configio NODE number → eipcfg adapter via TargetIP last octet."""
    for ad in adapters:
        ip = (ad.get("targetip") or "").strip()
        m = re.search(r"\.(\d+)$", ip)
        if m and int(m.group(1)) == int(node):
            return ad
    # Fallback: 1794-AENT-(node-50) for CP* RIO nodes numbered 51..58
    idx = int(node) - 50
    if idx >= 1:
        want = {f"1794-AENT-{idx}", f"1794_AENT_{idx}", f"AENT-{idx}", f"AENT_{idx}"}
        for ad in adapters:
            if (ad.get("name") or "").strip() in want:
                return ad
    return None


def _module_matching_bank(
    adapter: dict[str, Any], bank: int
) -> tuple[dict[str, Any], str] | None:
    """Find bridged module on adapter whose EIPModules InputBank/OutputBank == bank.

    Returns (module_dict_with_adapter_fields, direction). Does not invent slots
    from bank arithmetic — Slot comes from the EIPModules/eipcfg module record.
    """
    if bank < 0 or not adapter:
        return None
    bridged = []
    for mod in sorted(adapter.get("modules") or [], key=lambda m: int(m.get("slot") or 0)):
        if (mod.get("connection") or "").upper() == "HEADNODE":
            continue
        if "AENT" in (mod.get("type") or "").upper():
            continue
        bridged.append(mod)
    # Prefer direction-consistent bank field (OB→O, IB→I)
    candidates: list[tuple[dict[str, Any], str]] = []
    for mod in bridged:
        direction = mod.get("direction") or _module_direction(mod.get("type") or "")
        try:
            ib = int(mod.get("input_bank")) if mod.get("input_bank") is not None else -1
        except (TypeError, ValueError):
            ib = -1
        try:
            ob = int(mod.get("output_bank")) if mod.get("output_bank") is not None else -1
        except (TypeError, ValueError):
            ob = -1
        if direction == "O" and ob == bank:
            candidates.append((mod, "O"))
        elif direction == "I" and ib == bank and ib > 0:
            candidates.append((mod, "I"))
        elif direction == "O" and ib == bank and ib > 0 and ob != bank:
            # status IB on output card — ignore for discrete bank match
            continue
        elif ob == bank and direction != "I":
            candidates.append((mod, direction or "O"))
        elif ib == bank and ib > 0 and direction != "O":
            candidates.append((mod, direction or "I"))
    if not candidates:
        return None
    # Exact direction+bank wins; otherwise first slot-ordered match
    mod, direction = candidates[0]
    enriched = {
        **mod,
        "adapter_name": adapter.get("name"),
        "rio_name": adapter.get("rio_name"),
        "panel": adapter.get("panel"),
        "adapter_index": adapter.get("adapter_index"),
        "targetip": adapter.get("targetip"),
    }
    return enriched, direction


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
    eip_rows = _load_eipmodules_rows(run_dir, machine)
    if eip_rows and adapters:
        _enrich_adapters_with_eipmodules(adapters, eip_rows)

    # Panel evidence from Configio Desc prefixes (RUN evidence for CP2/CP3/CP5 naming)
    panel_order: list[str] = []
    panel_word_dirs: dict[str, dict[str, set[int]]] = defaultdict(
        lambda: {"I": set(), "O": set()}
    )
    # module name → set of panels that reference it via Desc
    module_panels: dict[str, set[str]] = defaultdict(set)
    for row in configio_rows:
        parsed = row.get("parsed")
        node_parsed = row.get("node_parsed")
        evidence = parsed or node_parsed
        if not evidence:
            continue
        panel = evidence.get("panel") or ""
        if panel and panel not in panel_order:
            panel_order.append(panel)
        direction = (parsed or {}).get("direction") or ""
        if not direction and node_parsed and eip_rows:
            # Direction from EIPModules bank match on the NODE adapter
            try:
                b = int(row.get("bank"))
            except (TypeError, ValueError):
                b = -1
            ad = _adapter_for_node(adapters, int(node_parsed.get("node") or -1))
            if ad is not None and b >= 0:
                hit = _module_matching_bank(ad, b)
                if hit:
                    direction = hit[1]
        if panel and direction in ("I", "O"):
            panel_word_dirs[panel][direction].add(int(row["octal_word"]))
        if parsed and parsed.get("module_name"):
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


def _synthesize_point_banks_from_adapter_addresses(adapters: list[dict]) -> None:
    """Canonical POINT bank layout from adapter InputAddress/OutputAddress.

    first InputBank = InputAddress + 8
    first OutputBank = OutputAddress
    Each IA/IB/IM consumes one input bank; OA/OB consume one output bank.
    OB8E also consumes one input status bank.

    Recomputes banks whenever bridged cards lack banks OR existing banks do not
    start at InputAddress+8 (MSC Reno EIPModules sometimes stamps wrong racks).
    """
    for ad in adapters or []:
        mods = list(ad.get("modules") or [])
        bridged = sorted(
            [
                m
                for m in mods
                if (m.get("connection") or "").upper() != "HEADNODE"
                and "AENT" not in (m.get("type") or "").upper()
            ],
            key=lambda m: int(m.get("slot") or 0),
        )
        if not bridged:
            continue
        try:
            in_addr = int(float(ad.get("input_address") or 0))
        except (TypeError, ValueError):
            in_addr = 0
        try:
            out_addr = int(float(ad.get("output_address") or 0))
        except (TypeError, ValueError):
            out_addr = 0
        if in_addr <= 0 and out_addr < 0:
            continue
        expected_first_ib = in_addr + 8 if in_addr > 0 else None
        need = False
        for m in bridged:
            ib = m.get("input_bank")
            ob = m.get("output_bank")
            if ib in (None, "", 0, "0") and ob in (None, "", 0, "0"):
                need = True
                break
        if expected_first_ib is not None:
            first_in = next(
                (
                    m
                    for m in bridged
                    if any(x in (m.get("type") or "").upper() for x in ("IA", "IB", "IM"))
                ),
                None,
            )
            if first_in is not None:
                try:
                    if int(float(first_in.get("input_bank") or -1)) != expected_first_ib:
                        need = True
                except (TypeError, ValueError):
                    need = True
        if not need:
            continue
        next_ib = expected_first_ib if expected_first_ib is not None else 0
        next_ob = out_addr if out_addr >= 0 else 0
        for m in bridged:
            mt = (m.get("type") or "").upper()
            is_in = any(x in mt for x in ("IA", "IB", "IM"))
            is_out = any(x in mt for x in ("OA", "OB", "OW"))
            if is_in and next_ib is not None:
                m["input_bank"] = next_ib
                next_ib += 1
            if is_out:
                if "OB8" in mt or "OB16" in mt:
                    m["input_bank"] = next_ib
                    next_ib += 1
                m["output_bank"] = next_ob
                next_ob += 1


def parse_fortna_octal_bit(io_bit: Any) -> dict[str, Any] | None:
    """Normalize Fortna bit into Low/High half + module channel bit.

    Fortna high-half values 10–17 (or 8–15) must not be carried into a 4-channel
    POINT card as Data[10]. After choosing Configio Low/High, module_bit is 0..(n-1).
    """
    if io_bit is None:
        return None
    raw_s = str(io_bit).strip()
    if raw_s == "":
        return None
    try:
        if re.fullmatch(r"[0-7]+", raw_s) and len(raw_s) <= 2:
            raw = int(raw_s, 8)
        else:
            raw = int(float(raw_s))
            # Conveyor often stores octal 10-17 as decimal integers 10-17
            if 10 <= raw <= 17:
                raw = 8 + (raw - 10)
    except (TypeError, ValueError):
        return None
    if raw < 0:
        return None
    half = "High" if raw >= 8 else "Low"
    module_bit = raw - 8 if raw >= 8 else raw
    return {"raw": raw, "half": half, "module_bit": module_bit}


def build_physical_word_map(run_dir: Path, machine: str = "") -> dict[str, Any]:
    """Build Octal_Word → physical channel map from Configio + eipcfg.

    Primary assignment: panel from Configio Desc + sequential modules within that
    panel's adapters (direction-matched). Name match (Desc → eipcfg module name)
    is attempted for provenance and accepted only when it agrees with the sequential
    module for that word (Desc indices often diverge from eipcfg name suffixes).

    High-half Desc missing → use Low half module with bit_half=high.

    Empty-Desc RTA rows (MSC Reno): Configio.Bank ↔ synthesized POINT banks from
    adapter InputAddress+8 / OutputAddress.
    """
    run_dir = _normalize_run_dir(run_dir)
    topology = parse_eipcfg(run_dir, machine)
    adapters = list(topology.get("adapters") or [])
    _synthesize_point_banks_from_adapter_addresses(adapters)
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
        low_n = (low or {}).get("node_parsed")
        high_n = (high or {}).get("node_parsed")
        panel = (
            (low_p or high_p or {}).get("panel")
            or (low_n or high_n or {}).get("panel")
            or ""
        )
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
        eip_bank_used = None
        node_used = None

        # --- Profile: CONFIGIO_CATALOG_WORD_BANK (RTA / ORINDYAC6) ---
        # Configio.Bank ↔ EIPModules InputBank/OutputBank; Octal_Word = Fortna word.
        # Does not require panel prefix. AENT head Desc rows are skipped.
        if not seq and not chosen:
            bank_hit = None
            bank_how = ""
            for side, row in (("Low", low), ("High", high)):
                if not row:
                    continue
                cbp = row.get("catalog_bank_parsed") or {}
                if not cbp or cbp.get("is_aent_head"):
                    continue
                eip_bank = row.get("bank")
                if eip_bank is None or int(eip_bank) < 0:
                    eip_bank = cbp.get("eip_bank")
                try:
                    eip_bank_i = int(eip_bank)
                except (TypeError, ValueError):
                    continue
                cat_u = str(cbp.get("catalog") or "").upper()
                direction = cbp.get("direction") or _module_direction(cat_u)
                for ad in adapters:
                    for mod in ad.get("modules") or []:
                        if (mod.get("connection") or "").upper() == "HEADNODE":
                            continue
                        if "AENT" in (mod.get("type") or "").upper():
                            continue
                        ib = mod.get("input_bank")
                        ob = mod.get("output_bank")
                        try:
                            ib_i = int(ib) if ib is not None else None
                        except (TypeError, ValueError):
                            ib_i = None
                        try:
                            ob_i = int(ob) if ob is not None else None
                        except (TypeError, ValueError):
                            ob_i = None
                        matched = False
                        if direction == "I" and ib_i == eip_bank_i:
                            matched = True
                        elif direction == "O" and ob_i == eip_bank_i:
                            matched = True
                        elif direction == "" and (ib_i == eip_bank_i or ob_i == eip_bank_i):
                            matched = True
                            direction = "I" if ib_i == eip_bank_i else "O"
                        if not matched:
                            continue
                        # Catalog family corroboration when present
                        mt = (mod.get("type") or "").upper()
                        if cat_u and cat_u not in mt and mt not in cat_u:
                            # allow OA8 vs OA8I soft match
                            if not (
                                cat_u.replace("OA8I", "OA8") in mt.replace("OA8I", "OA8")
                                or mt.replace("OA8I", "OA8") in cat_u.replace("OA8I", "OA8")
                            ):
                                continue
                        bank_hit = {
                            **mod,
                            "adapter_name": ad.get("name"),
                            "rio_name": ad.get("rio_name"),
                            "panel": ad.get("panel") or "",
                            "adapter_index": ad.get("adapter_index"),
                            "direction": direction or mod.get("direction") or _module_direction(mt),
                        }
                        bank_how = "configio_bank_match"
                        eip_bank_used = eip_bank_i
                        break
                    if bank_hit:
                        break
                if bank_hit:
                    break
            if bank_hit:
                chosen = bank_hit
                assign_how = bank_how
                if not direction:
                    direction = bank_hit.get("direction") or ""

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
        elif chosen and assign_how == "configio_bank_match":
            # Bank match already selected the module — do not overwrite with name match.
            # catalog_word_bank Desc trailing digits are EIP banks, not module-name indices.
            pass
        elif name_hit and (not panel or name_hit.get("panel") == panel or not name_hit.get("panel")):
            # Sequential unavailable — accept name match (still Configio Desc driven)
            # Only for panel_catalog / panel_node parsed forms (not catalog_word_bank).
            chosen = name_hit
            assign_how = "configio_desc_name"
            if name_side == "High" and bit_half_default == "high":
                pass
            direction = direction or name_hit.get("direction") or ""
            panel = panel or name_hit.get("panel") or ""
        elif name_hit:
            # Name hit on foreign panel — keep as provenance only; still unresolved channel
            pass

        # PLC5 NODE Desc → EIPModules InputBank/OutputBank on that adapter (not bank math)
        if not chosen:
            node_info = low_n or high_n
            bank_row = low or high or {}
            try:
                cfg_bank = int(bank_row.get("bank"))
            except (TypeError, ValueError):
                cfg_bank = -1
            if node_info and cfg_bank >= 0:
                ad = _adapter_for_node(adapters, int(node_info.get("node") or -1))
                hit = _module_matching_bank(ad, cfg_bank) if ad else None
                if not hit and cfg_bank > 0:
                    # High half often stores Low+1; EIPModules stores the Low bank only
                    hit = _module_matching_bank(ad, cfg_bank - 1) if ad else None
                    if hit:
                        cfg_bank = cfg_bank - 1
                if hit:
                    cand, cand_dir = hit[0], hit[1]
                    try:
                        desc_slot = int(node_info.get("desc_slot") or -1)
                    except (TypeError, ValueError):
                        desc_slot = -1
                    eip_slot_hit = int(cand.get("slot") or -2)
                    # Conflicting Desc slot vs EIPModules bank match → do not
                    # collapse onto the bank-matched channel (e.g. word 517
                    # NODE52-8 / bank 32 vs IA16 slot3). Leave REVIEW_REQUIRED.
                    if desc_slot >= 0 and eip_slot_hit >= 0 and desc_slot != eip_slot_hit:
                        unresolved.append(
                            {
                                "octal_word": w,
                                "panel": panel or node_info.get("panel") or "",
                                "direction": cand_dir or direction,
                                "low_desc": (low or {}).get("desc"),
                                "high_desc": (high or {}).get("desc"),
                                "name_hit": (name_hit or {}).get("name") if name_hit else None,
                                "reason": "desc_slot_mismatch_eipmodules_bank",
                                "classification": "REVIEW_REQUIRED",
                                "configio_node": int(node_info.get("node") or 0),
                                "configio_bank": cfg_bank,
                                "desc_slot": desc_slot,
                                "eipmodules_slot": eip_slot_hit,
                                "eipmodules_module": cand.get("name"),
                                "eipmodules_type": cand.get("type"),
                            }
                        )
                        continue
                    chosen, direction = cand, cand_dir
                    assign_how = "configio_node_eipmodules_bank"
                    panel = panel or chosen.get("panel") or node_info.get("panel") or ""
                    eip_bank_used = cfg_bank
                    node_used = int(node_info.get("node") or 0)

        # --- Profile: CONFIGIO_BANK_ONLY (empty Desc / RTA1 MSC Reno) ---
        # Configio.Bank is authoritative; match synthesized POINT InputBank/OutputBank.
        if not chosen:
            for side, row in (("Low", low), ("High", high)):
                if not row:
                    continue
                try:
                    cfg_bank = int(row.get("bank"))
                except (TypeError, ValueError):
                    continue
                if cfg_bank < 0:
                    continue
                hit = None
                for ad in adapters:
                    hit = _module_matching_bank(ad, cfg_bank)
                    if hit:
                        cand, cand_dir = hit
                        chosen = {
                            **cand,
                            "adapter_name": ad.get("name"),
                            "rio_name": ad.get("rio_name") or ad.get("name"),
                            "panel": ad.get("panel") or "",
                            "adapter_index": ad.get("adapter_index"),
                            "direction": cand_dir,
                        }
                        direction = cand_dir or direction or "I"
                        assign_how = "configio_bank_only"
                        eip_bank_used = cfg_bank
                        panel = panel or chosen.get("panel") or ""
                        break
                if chosen:
                    break

        if not chosen:
            unresolved.append(
                {
                    "octal_word": w,
                    "panel": panel,
                    "direction": direction,
                    "low_desc": (low or {}).get("desc"),
                    "high_desc": (high or {}).get("desc"),
                    "name_hit": (name_hit or {}).get("name") if name_hit else None,
                    "reason": "no_eipmodules_bank_match",
                    "classification": "REVIEW_REQUIRED",
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
                "source_tables": (
                    ["Configio.asc", "eipcfg", "EIPModules"]
                    if assign_how == "configio_node_eipmodules_bank"
                    else ["Configio.asc", "eipcfg"]
                ),
                "configio_panel": panel,
                "eipcfg_adapter": chosen.get("adapter_name"),
                "eipcfg_module": chosen.get("name"),
                "eipcfg_slot": eip_slot,
                "eipmodules_bank": eip_bank_used,
                "configio_node": node_used,
                "input_bank": chosen.get("input_bank"),
                "output_bank": chosen.get("output_bank"),
                "data_index_scheme": topology.get("data_index_scheme"),
                "assign_how": assign_how,
            },
        }
        words_out[str(w)] = entry

        # Bit fan-out: Low/High Configio halves may map to DIFFERENT POINT modules
        # (bank 80 vs 81). Never carry Fortna high-half 10–17 into Data[10] on a
        # 4-channel card — normalize to module_bit within the half's module.
        def _emit_half(half_row: dict | None, half_name: str) -> None:
            if not half_row:
                return
            try:
                half_bank = int(half_row.get("bank"))
            except (TypeError, ValueError):
                half_bank = -1
            half_mod = None
            half_dir = direction
            if half_bank >= 0:
                for ad in adapters:
                    hit = _module_matching_bank(ad, half_bank)
                    if hit:
                        half_mod, half_dir = hit[0], hit[1]
                        half_mod = {
                            **half_mod,
                            "adapter_name": ad.get("name"),
                            "rio_name": ad.get("rio_name") or ad.get("name"),
                        }
                        break
            use = half_mod or chosen
            use_dir = half_dir or direction
            use_type = use.get("type") or mod_type
            use_family = (
                use.get("family")
                or detect_family_from_catalog(use_type)
                or family
            )
            use_slot = int(use.get("slot") or eip_slot)
            use_di = int(
                use.get("data_index")
                if use.get("data_index") is not None
                else _data_index_for_module(use_slot, use_family)
            )
            use_rio = use.get("rio_name") or rio
            use_base = f"{use_rio}:{use_dir}.Data[{use_di}]"
            capacity = max_bits_for_catalog(use_type)
            for module_bit in range(capacity):
                # Fortna raw bit: Low uses 0..n-1; High uses 8..8+n-1 (normalized)
                raw_bit = module_bit if half_name == "Low" else (8 + module_bit)
                channel = f"{use_base}.{module_bit}"
                by_word_bit[f"{w}:{raw_bit}"] = {
                    **entry,
                    "bit": module_bit,
                    "fortna_raw_bit": raw_bit,
                    "bit_half": half_name.lower(),
                    "channel": channel,
                    "channel_base": use_base,
                    "data_index": use_di,
                    "eip_slot": use_slot,
                    "rio_name": use_rio,
                    "type": use_type,
                    "module_name": use.get("name") or entry.get("module_name"),
                    "low_bank": (low or {}).get("bank"),
                    "high_bank": (high or {}).get("bank"),
                    "half_bank": half_bank,
                    "assign_how": assign_how or "configio_bank_only",
                }
                # Also index decimal 10-17 style for Conveyor ASC consumers
                if half_name == "High":
                    by_word_bit[f"{w}:{10 + module_bit}"] = by_word_bit[f"{w}:{raw_bit}"]

        _emit_half(low, "Low")
        _emit_half(high, "High")
        # Fallback when only one half existed and fan-out above was skipped
        if not low and not high:
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
    parsed = parse_fortna_octal_bit(bit)
    if not parsed:
        return None
    bv = int(parsed["raw"])
    key = f"{w}:{bv}"
    hit = (physical_map.get("by_word_bit") or {}).get(key)
    if hit:
        return hit
    # Decimal 10-17 index (Conveyor ASC style)
    if 8 <= bv <= 15:
        alt = (physical_map.get("by_word_bit") or {}).get(f"{w}:{10 + (bv - 8)}")
        if alt:
            return alt
    # Module-local bit on Low half
    return (physical_map.get("by_word_bit") or {}).get(f"{w}:{int(parsed['module_bit'])}")


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

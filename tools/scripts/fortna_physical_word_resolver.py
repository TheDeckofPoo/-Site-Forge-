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
    """Locate eipcfg for the ACTIVE machine only.

    Never silently fall back to a sibling controller's *-RTA-eipcfg.xml
    (e.g. RESPNA when MACHINENAME=RESPICK). Uses fortna_machine_source_scope.
    """
    try:
        from fortna_machine_source_scope import select_active_eipcfg

        sel = select_active_eipcfg(run_dir, machine)
        path = sel.get("selected_eipcfg")
        if path:
            p = Path(path)
            if p.is_file():
                return p
        # Explicit refuse sibling — do not scan remaining *-RTA-eipcfg.xml
        if sel.get("refused_sibling_fallback"):
            return None
    except Exception:
        pass
    # Legacy fallback only when scoping module unavailable: prefer machine prefix
    fortna = run_dir / "FORTNA"
    mach = (machine or "").strip()
    candidates: list[Path] = []
    if mach:
        candidates.append(fortna / f"{mach}-RTA-eipcfg.xml")
        candidates.extend(sorted(fortna.glob(f"{mach}*eipcfg*.xml")))
    # Do NOT append unscoped *-RTA-eipcfg.xml here — that was the leakage path
    for p in candidates:
        if p.is_file() and "eipcfg" in p.name.lower() and p.suffix.lower() == ".xml":
            # exclude EDITED/TEST variants unless exact
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
    adapters: list[dict[str, Any]],
    eip_rows: list[dict[str, Any]],
    *,
    run_dir: Path | None = None,
    machine: str = "",
) -> dict[str, Any]:
    """Attach EIPModules banks onto eipcfg modules via exact EIPAdapters bridge.

    Preferred PROVEN chain:
      EIPModules.Adapter == EIPAdapters.Name
      EIPAdapters.TargetIP == eipcfg Adapter.targetip (unique)

    Fallbacks (honest):
      exact adapter-name match → PROVEN (exact_name)
      substring/containment → DERIVED only (never inflated to PROVEN)
    """
    eipadapters_rows: list[dict[str, Any]] = []
    if run_dir is not None:
        try:
            from fortna_eip_adapter_bridge import (
                enrich_adapters_via_exact_bridge,
                load_eipadapters_rows,
            )

            eipadapters_rows = load_eipadapters_rows(run_dir, machine)
            return enrich_adapters_via_exact_bridge(adapters, eip_rows, eipadapters_rows)
        except Exception:
            pass

    # Legacy fallback when run_dir unavailable — name/substring only
    by_adapter: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_adapter_keys: list[str] = []
    for row in eip_rows:
        ad = (row.get("adapter") or "").strip()
        if ad:
            by_adapter[ad].append(row)
            by_adapter[ad.replace("-", "_")].append(row)
            by_adapter[ad.replace("_", "-")].append(row)
            if ad not in all_adapter_keys:
                all_adapter_keys.append(ad)
    stats = {"proven_bridge": 0, "exact_name_fallback": 0, "substring_fallback": 0, "unjoined": 0}
    for ad in adapters:
        name = (ad.get("name") or "").strip()
        rio = (ad.get("rio_name") or "").strip()
        mods = ad.get("modules") or []
        rows = by_adapter.get(name) or by_adapter.get(name.replace("_", "-")) or []
        join = "exact_name"
        if not rows:
            soft_key = None
            for key in all_adapter_keys:
                ku = key.upper().replace("_", "-")
                for cand in (name, rio):
                    cu = (cand or "").upper().replace("_", "-")
                    if cu and (cu in ku or ku in cu):
                        soft_key = key
                        break
                if soft_key:
                    break
            if soft_key:
                rows = by_adapter.get(soft_key) or []
                join = "substring"
                stats["substring_fallback"] += 1
            else:
                stats["unjoined"] += 1
                continue
        else:
            stats["exact_name_fallback"] += 1
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
            if hit.get("input_bank") is not None:
                mod["input_bank"] = int(hit["input_bank"])
            if hit.get("output_bank") is not None:
                mod["output_bank"] = int(hit["output_bank"])
            mod["bank_join"] = join
            mod["adapter_bridge_status"] = (
                "DERIVED" if join == "substring" else "PROVEN"
            )
    return stats


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


def find_module_for_configio_bank(
    adapter: dict[str, Any],
    bank: int,
    *,
    expected_direction: str = "",
    expected_catalog: str = "",
    family: str = "",
) -> dict[str, Any]:
    """Direction/catalog-aware module selection for a Configio bank.

    Bank alone is insufficient when the same numeric bank is one module's
    InputBank and another's OutputBank. Never first-by-slot as physical truth.
    Returns {ok, module, direction, status, candidates, reason}.
    """
    empty = {
        "ok": False,
        "module": None,
        "direction": expected_direction or "",
        "status": "NO_MATCH",
        "candidates": [],
        "reason": "no_match",
    }
    if bank < 0 or not adapter:
        return {**empty, "reason": "invalid_bank_or_adapter"}
    want_dir = (expected_direction or "").upper()
    if want_dir not in ("I", "O", ""):
        want_dir = ""
    cat_u = (expected_catalog or "").upper().strip()
    bridged = []
    for mod in sorted(adapter.get("modules") or [], key=lambda m: int(m.get("slot") or 0)):
        if (mod.get("connection") or "").upper() == "HEADNODE":
            continue
        if "AENT" in (mod.get("type") or "").upper():
            continue
        bridged.append(mod)

    candidates: list[dict[str, Any]] = []
    for mod in bridged:
        direction = (mod.get("direction") or _module_direction(mod.get("type") or "") or "").upper()
        try:
            ib = int(mod.get("input_bank")) if mod.get("input_bank") is not None else -1
        except (TypeError, ValueError):
            ib = -1
        try:
            ob = int(mod.get("output_bank")) if mod.get("output_bank") is not None else -1
        except (TypeError, ValueError):
            ob = -1
        mt = (mod.get("type") or "").upper()
        # Direction-appropriate bank field only
        if want_dir == "I":
            if ib != bank or ib <= 0:
                continue
            direction = "I"
        elif want_dir == "O":
            if ob != bank:
                continue
            direction = "O"
        else:
            # No expected direction — still do not mix I/O bank fields casually
            if direction == "I" and ib == bank and ib > 0:
                pass
            elif direction == "O" and ob == bank:
                pass
            else:
                continue
        if cat_u:
            if cat_u != mt and cat_u not in mt and mt not in cat_u:
                # allow OA8 vs OA8I soft family match only when prefixes align
                soft = cat_u.replace("OA8I", "OA8") == mt.replace("OA8I", "OA8")
                if not soft:
                    continue
        candidates.append(
            {
                "module": mod,
                "direction": direction,
                "type": mt,
                "slot": mod.get("slot"),
                "input_bank": ib if ib >= 0 else None,
                "output_bank": ob if ob >= 0 else None,
            }
        )

    if not candidates:
        return {**empty, "reason": "no_direction_catalog_bank_match"}
    if len(candidates) > 1:
        return {
            "ok": False,
            "module": None,
            "direction": want_dir,
            "status": "AMBIGUOUS",
            "candidates": candidates,
            "reason": "multiple_compatible_modules",
        }
    mod = candidates[0]["module"]
    direction = candidates[0]["direction"]
    enriched = {
        **mod,
        "adapter_name": adapter.get("name"),
        "rio_name": adapter.get("rio_name"),
        "panel": adapter.get("panel"),
        "adapter_index": adapter.get("adapter_index"),
        "targetip": adapter.get("targetip"),
    }
    return {
        "ok": True,
        "module": enriched,
        "direction": direction,
        "status": "UNIQUE",
        "candidates": candidates,
        "reason": "unique_direction_catalog_bank_match",
    }


def _module_matching_bank(
    adapter: dict[str, Any],
    bank: int,
    *,
    expected_direction: str = "",
    expected_catalog: str = "",
) -> tuple[dict[str, Any], str] | None:
    """Compatibility wrapper — requires direction when possible; never undirected first-slot."""
    result = find_module_for_configio_bank(
        adapter,
        bank,
        expected_direction=expected_direction,
        expected_catalog=expected_catalog,
    )
    if not result.get("ok") or not result.get("module"):
        return None
    return result["module"], str(result.get("direction") or "")


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
    adapter_bridge_stats: dict[str, Any] = {}
    if eip_rows and adapters:
        adapter_bridge_stats = _enrich_adapters_with_eipmodules(
            adapters, eip_rows, run_dir=run_dir, machine=machine
        )

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
                # Direction unknown yet — try both; ambiguous stays empty
                hit_i = _module_matching_bank(ad, b, expected_direction="I")
                hit_o = _module_matching_bank(ad, b, expected_direction="O")
                if hit_i and not hit_o:
                    direction = "I"
                elif hit_o and not hit_i:
                    direction = "O"
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

    # Birth certificate / machine scope for selected eipcfg
    machine_scope: dict[str, Any] = {}
    try:
        from fortna_machine_source_scope import (
            read_machine_name,
            read_project_name,
            select_active_eipcfg,
        )

        active = machine or read_machine_name(run_dir)
        sel = select_active_eipcfg(run_dir, active)
        machine_scope = {
            "project": read_project_name(run_dir),
            "active_machine": active,
            "source_file": sel.get("selected_eipcfg"),
            "selection_reason": sel.get("selection_reason"),
            "scope_status": "ACTIVE_MACHINE_SOURCE" if sel.get("selected_eipcfg") else "NONE",
            "classified_eipcfg": sel.get("classified") or [],
            "siblings": sel.get("siblings") or [],
            "refused_sibling_fallback": sel.get("refused_sibling_fallback"),
        }
    except Exception as exc:
        machine_scope = {"error": str(exc)}

    return {
        "machine": machine,
        "eipcfg_path": str(eipcfg_path) if eipcfg_path else None,
        "adapters": adapters,
        "panel_order": panel_order,
        "panel_need": panel_need,
        "configio_row_count": len(configio_rows),
        "adapter_bridge_stats": adapter_bridge_stats,
        "machine_source_scope": machine_scope,
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

    POINT-only: never overwrite FLEX (1794) EIPModules InputBank/OutputBank.
    Those banks are authoritative for catalog_word_bank Configio joins
    (ORINDYAC6 AENT-2 words 610–617). Overwriting them made raw RUN claims
    disappear at physical resolution (NO_RESOLVE).
    """
    for ad in adapters or []:
        mods = list(ad.get("modules") or [])
        cats = [(m.get("type") or m.get("catalog") or "").upper() for m in mods]
        is_flex = any("1794" in c for c in cats)
        is_point = any(("1734" in c or "1738" in c) for c in cats)
        # FLEX racks already carry EIPModules banks — do not recompute as POINT
        if is_flex and not is_point:
            continue
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
        # Only force recompute for POINT when banks disagree with InputAddress+8
        if is_point and expected_first_ib is not None:
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

    Delegates to FortnaBitAddress so raw source text is not lost to int().
    Fortna high-half labels "10"–"17" are octal labels → logical 8–15.
    After choosing Configio Low/High, module_bit is 0..(n-1).

    Returns legacy dict plus source-preserving fields:
      raw, half, module_bit, raw_text, encoding, logical_bit
    """
    from fortna_bit_address import parse_fortna_bit_address

    addr = parse_fortna_bit_address(io_bit)
    if addr.logical_bit is None:
        return None
    return {
        "raw": addr.logical_bit,
        "half": addr.half,
        "module_bit": addr.module_bit,
        "raw_text": addr.raw_text,
        "encoding": addr.encoding,
        "logical_bit": addr.logical_bit,
        "confidence": addr.confidence,
    }


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
    # Separate from logical keys: Fortna octal label "10" → logical key "w:8"
    by_word_bit_labels: dict[str, str] = {}
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
                # Prefer direction from catalog if Desc parsed; else try Low bank as-is
                exp_dir = direction if direction in ("I", "O") else ""
                hit = (
                    _module_matching_bank(ad, cfg_bank, expected_direction=exp_dir)
                    if ad
                    else None
                )
                if not hit and cfg_bank > 0 and exp_dir:
                    # High half often stores Low+1; EIPModules stores the Low bank only
                    hit = _module_matching_bank(ad, cfg_bank - 1, expected_direction=exp_dir) if ad else None
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

        # --- Profile: CONFIGIO_CATALOG_PREFIX_BANK (general RTA 1794/1734) ---
        # Desc may be catalog-index (1794-IA16-5) or catalog-word-bank.
        # Uses Rockwell catalog detector + direction-aware bank match. No site names.
        if not chosen:
            try:
                from fortna_rockwell_catalog import first_catalog, KNOWN_CATALOG
            except Exception:
                first_catalog = None  # type: ignore
                KNOWN_CATALOG = "KNOWN_CATALOG"  # type: ignore
            for side, row in (("Low", low), ("High", high)):
                if not row or first_catalog is None:
                    continue
                desc = str(row.get("desc") or "")
                cat_ev = first_catalog(desc, run_dir=run_dir, source_table="Configio")
                if not cat_ev or cat_ev.catalog_status != KNOWN_CATALOG:
                    continue
                if "AENT" in cat_ev.catalog_number.upper():
                    continue  # adapter/status words — not discrete module bank rule
                try:
                    cfg_bank = int(row.get("bank"))
                except (TypeError, ValueError):
                    continue
                if cfg_bank < 0:
                    continue
                # High half: normalize through paired Low when adjacent
                base_bank = cfg_bank
                if side == "High" and low is not None:
                    try:
                        low_bank = int(low.get("bank"))
                    except (TypeError, ValueError):
                        low_bank = -1
                    low_cat = first_catalog(str(low.get("desc") or ""), run_dir=run_dir)
                    if (
                        low_cat
                        and low_cat.catalog_number.upper() == cat_ev.catalog_number.upper()
                        and (cfg_bank == low_bank or cfg_bank == low_bank + 1)
                    ):
                        base_bank = low_bank
                    else:
                        continue  # invalid pair — leave for REVIEW via unresolved
                exp_dir = cat_ev and _module_direction(cat_ev.catalog_number) or ""
                # Corroborate In_Out without inventing per-bit rules
                try:
                    from fortna_configio_direction import resolve_configio_direction

                    dinfo = resolve_configio_direction(
                        catalog=cat_ev.catalog_number, in_out=row.get("in_out")
                    )
                    if dinfo.get("status") == "DIRECTION_CONFLICT":
                        continue
                    if dinfo.get("direction") in ("I", "O"):
                        exp_dir = dinfo["direction"]
                except Exception:
                    pass
                if exp_dir not in ("I", "O"):
                    continue
                hit = None
                ambiguous = False
                for ad in adapters:
                    result = find_module_for_configio_bank(
                        ad,
                        base_bank,
                        expected_direction=exp_dir,
                        expected_catalog=cat_ev.catalog_number,
                        family=cat_ev.hardware_family,
                    )
                    if result.get("status") == "AMBIGUOUS":
                        ambiguous = True
                        break
                    if result.get("ok") and result.get("module"):
                        hit = (result["module"], result["direction"])
                        chosen = {
                            **result["module"],
                            "adapter_name": ad.get("name"),
                            "rio_name": ad.get("rio_name") or ad.get("name"),
                            "panel": ad.get("panel") or "",
                            "adapter_index": ad.get("adapter_index"),
                            "direction": result["direction"],
                        }
                        direction = result["direction"]
                        assign_how = "configio_catalog_prefix_bank"
                        eip_bank_used = base_bank
                        panel = panel or chosen.get("panel") or ""
                        break
                if ambiguous:
                    unresolved.append(
                        {
                            "octal_word": w,
                            "panel": panel,
                            "direction": exp_dir,
                            "low_desc": (low or {}).get("desc"),
                            "high_desc": (high or {}).get("desc"),
                            "reason": "ambiguous_configio_bank_module",
                            "classification": "REVIEW_REQUIRED",
                            "configio_bank": base_bank,
                            "expected_catalog": cat_ev.catalog_number,
                        }
                    )
                    chosen = None
                    break
                if chosen:
                    break

        # --- Profile: CONFIGIO_BANK_ONLY (empty Desc / RTA1 MSC Reno POINT) ---
        # Configio.Bank is authoritative; match synthesized POINT banks with direction.
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
                exp_dir = direction if direction in ("I", "O") else ""
                # Infer direction from In_Out / module when empty Desc
                if not exp_dir:
                    try:
                        from fortna_configio_direction import direction_from_in_out_mask

                        mi = direction_from_in_out_mask(row.get("in_out"))
                        if mi.get("direction") in ("I", "O"):
                            exp_dir = mi["direction"]
                    except Exception:
                        pass
                hit = None
                for ad in adapters:
                    if exp_dir in ("I", "O"):
                        hit = _module_matching_bank(ad, cfg_bank, expected_direction=exp_dir)
                    else:
                        # Try both; require uniqueness across I/O
                        hi = _module_matching_bank(ad, cfg_bank, expected_direction="I")
                        ho = _module_matching_bank(ad, cfg_bank, expected_direction="O")
                        if hi and ho:
                            hit = None  # ambiguous
                        else:
                            hit = hi or ho
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

        bank_join = str(chosen.get("bank_join") or "")
        adapter_bridge_status = str(chosen.get("adapter_bridge_status") or "")
        # Claim confidence follows bank-join evidence strength (never inflate substring → PROVEN)
        if bank_join == "substring" or adapter_bridge_status == "DERIVED":
            binding_confidence = "DERIVED"
        elif bank_join in {"exact_ip_bridge", "exact_name", "exact"} or adapter_bridge_status == "PROVEN":
            binding_confidence = "PROVEN"
        elif assign_how in {
            "configio_bank_match",
            "configio_bank_only",
            "configio_node_eipmodules_bank",
            "configio_panel_sequential",
            "configio_desc_name+sequential",
        }:
            binding_confidence = "PROVEN"
        elif assign_how == "configio_catalog_prefix_bank":
            # Catalog+direction+bank unique; PROVEN only with exact adapter bridge
            binding_confidence = (
                "PROVEN"
                if bank_join in {"exact_ip_bridge", "exact_name", "exact"}
                else "DERIVED"
            )
        else:
            binding_confidence = "DERIVED" if assign_how else "UNKNOWN"

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
            "bank_join": bank_join or None,
            "binding_confidence": binding_confidence,
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
                "bank_join": bank_join or None,
                "binding_confidence": binding_confidence,
            },
        }
        words_out[str(w)] = entry

        # Bit fan-out: carry forward proven word context (catalog/direction/module).
        # Never re-query by bank alone — that caused OA* words_out vs IA* by_word_bit.
        # Low/High may still split modules only when direction-aware evidence proves it.
        word_catalog = str(chosen.get("type") or mod_type or "")
        word_dir = str(direction or chosen.get("direction") or "")

        def _resolve_half_module(half_row: dict | None) -> tuple[dict | None, str, int]:
            if not half_row:
                return None, word_dir, -1
            try:
                half_bank = int(half_row.get("bank"))
            except (TypeError, ValueError):
                half_bank = -1
            # Default: inherit the word's chosen module (same catalog/direction/bank context)
            half_mod = chosen
            half_dir = word_dir
            # Optional explicit split: only if direction-aware lookup finds a *different*
            # unique module that still matches word catalog+direction.
            if half_bank >= 0 and word_dir in ("I", "O"):
                for ad in adapters:
                    hit = _module_matching_bank(
                        ad,
                        half_bank,
                        expected_direction=word_dir,
                        expected_catalog=word_catalog,
                    )
                    if hit:
                        cand, cand_dir = hit
                        half_mod = {
                            **cand,
                            "adapter_name": ad.get("name"),
                            "rio_name": ad.get("rio_name") or ad.get("name"),
                        }
                        half_dir = cand_dir or word_dir
                        break
            return half_mod, half_dir or word_dir, half_bank

        low_mod, low_dir, low_bank_i = _resolve_half_module(low)
        high_mod, high_dir, high_bank_i = _resolve_half_module(high)

        def _mod_key(mod: dict | None) -> tuple:
            if not mod:
                return ("", -1, -1)
            try:
                slot = int(mod.get("slot") if mod.get("slot") is not None else -1)
            except (TypeError, ValueError):
                slot = -1
            try:
                di = int(
                    mod.get("data_index")
                    if mod.get("data_index") is not None
                    else _data_index_for_module(slot, mod.get("family"))
                )
            except (TypeError, ValueError):
                di = -1
            return (str(mod.get("rio_name") or mod.get("name") or ""), slot, di)

        shared_16ch = bool(
            low
            and high
            and low_mod
            and high_mod
            and _mod_key(low_mod) == _mod_key(high_mod)
            and max_bits_for_catalog(str((low_mod or {}).get("type") or mod_type)) >= 16
        )

        def _emit_half(
            half_row: dict | None,
            half_name: str,
            use: dict | None,
            use_dir: str,
            half_bank: int,
        ) -> None:
            if not half_row:
                return
            use = use or chosen
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
            FORTNA_HALF = 8
            FORTNA_WORD = 16
            # Shared 16ch module: Low→module 0-7, High→module 8-15 (one physical word).
            # Separate High module: High logical 8-15 → that module's bits 0-7.
            # Solo Low IA16: logical 0-15 → module 0-15.
            if half_name == "Low":
                if high and (shared_16ch or capacity <= FORTNA_HALF):
                    nbits = min(capacity, FORTNA_HALF)
                elif high and capacity >= 16:
                    # High exists but bound elsewhere — Low still only owns Fortna 0-7
                    nbits = min(capacity, FORTNA_HALF)
                else:
                    nbits = min(capacity, FORTNA_WORD)
                logical_base = 0
                module_offset = 0
            else:
                nbits = min(capacity, FORTNA_HALF)
                logical_base = FORTNA_HALF
                module_offset = FORTNA_HALF if shared_16ch else 0
            for i in range(nbits):
                module_bit = module_offset + i
                logical_bit = logical_base + i
                if logical_bit < 0 or logical_bit > 15:
                    unresolved.append(
                        {
                            "octal_word": w,
                            "logical_bit": logical_bit,
                            "reason": "fortna_logical_bit_out_of_word_domain",
                            "half": half_name,
                            "module_bit": module_bit,
                            "capacity": capacity,
                        }
                    )
                    continue
                channel = f"{use_base}.{module_bit}"
                rec = {
                    **entry,
                    "bit": module_bit,
                    "fortna_raw_bit": logical_bit,
                    "logical_bit": logical_bit,
                    "bit_half": half_name.lower(),
                    "channel": channel,
                    "channel_base": use_base,
                    "data_index": use_di,
                    "eip_slot": use_slot,
                    "flex_slot": use_di,
                    "rio_name": use_rio,
                    "direction": use_dir,
                    "type": use_type,
                    "family": use_family,
                    "module_name": use.get("name") or entry.get("module_name"),
                    "low_bank": (low or {}).get("bank"),
                    "high_bank": (high or {}).get("bank"),
                    "half_bank": half_bank,
                    "assign_how": assign_how or "configio_bank_only",
                    "module_capacity": capacity,
                    "shared_16ch_word": shared_16ch,
                }
                key = f"{w}:{logical_bit}"
                prior = by_word_bit.get(key)
                if prior and prior.get("channel") and prior.get("channel") != channel:
                    unresolved.append(
                        {
                            "octal_word": w,
                            "logical_bit": logical_bit,
                            "reason": "by_word_bit_key_conflict",
                            "existing_channel": prior.get("channel"),
                            "new_channel": channel,
                        }
                    )
                    continue
                by_word_bit[key] = rec
                if half_name == "High":
                    label_key = f"{w}:{format(logical_bit, 'o')}"
                    by_word_bit_labels[label_key] = key

        _emit_half(low, "Low", low_mod, low_dir, low_bank_i)
        _emit_half(high, "High", high_mod, high_dir, high_bank_i)
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
        "by_word_bit_labels": by_word_bit_labels,
        "io_word_map": io_word_map,
        "unresolved": unresolved,
        "stats": {
            "adapter_count": len(adapters),
            "word_count": len(words_out),
            "unresolved_count": len(unresolved),
            "by_word_bit_count": len(by_word_bit),
            "by_word_bit_label_count": len(by_word_bit_labels),
            "rio_names": [a.get("rio_name") for a in adapters],
        },
    }


def resolve_word_bit(
    physical_map: dict[str, Any], word: int | str, bit: int | str
) -> dict[str, Any] | None:
    """Lookup physical channel for a Fortna word/bit.

    Always parse via FortnaBitAddress semantics first so label "10" → logical 8.
    Optional capacity miss reason is attached when Low half bit exceeds module width.
    """
    try:
        w = int(float(str(word).strip()))
    except (TypeError, ValueError):
        return None
    parsed = parse_fortna_octal_bit(bit)
    if not parsed:
        return None
    bv = int(parsed["logical_bit"] if parsed.get("logical_bit") is not None else parsed["raw"])
    key = f"{w}:{bv}"
    bwb = physical_map.get("by_word_bit") or {}
    hit = bwb.get(key)
    if hit:
        return hit
    # Label alias map (e.g. "1011:10" → "1011:8") — never mixed into logical keys
    labels = physical_map.get("by_word_bit_labels") or {}
    raw_text = str(parsed.get("raw_text") or bit).strip()
    label_key = f"{w}:{raw_text}"
    if label_key in labels:
        hit = bwb.get(labels[label_key])
        if hit:
            return hit
    # Diagnostic-only: Low half bit beyond module capacity (outcome still miss)
    if parsed.get("half") == "Low":
        # Probe any Low key on this word for capacity
        for lb in range(0, 8):
            sample = bwb.get(f"{w}:{lb}")
            if sample and sample.get("module_capacity"):
                cap = int(sample["module_capacity"])
                if bv >= cap:
                    return None  # unchanged miss; callers may use parse notes
                break
    # Module-local Low half fallback (legacy)
    mb = parsed.get("module_bit")
    if mb is not None and parsed.get("half") == "Low":
        return bwb.get(f"{w}:{int(mb)}")
    return None


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

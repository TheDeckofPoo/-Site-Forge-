#!/usr/bin/env python3
"""Sawtooth parameterization — Site Model → generic pack → site-specific objects.

Uses an explicit parameter map. Does NOT perform arbitrary whole-file L5X mangling
beyond mapped symbol renames from that map.

Finished PLC4 is never read.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROV_RUN = "RUN_EXPLICIT"
PROV_CFG = "CONFIGURATION REQUIRED"
PROV_GENERIC = "GENERIC_KEEP"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def collector_id_from_motor_io(motor_io: str) -> str | None:
    """VFD414_AUX → 414."""
    m = re.search(r"(\d{2,4})", (motor_io or "").upper())
    return m.group(1) if m else None


@dataclass
class SawtoothParamMap:
    """Explicit rename / bind map from RUN site model into the generic pack."""

    collector_digits: str
    merge_name: str
    motor_io: str
    reservation: str
    slice_seconds_merge: float | None
    symbol_renames: dict[str, str] = field(default_factory=dict)
    lane_bindings: list[dict[str, Any]] = field(default_factory=list)
    unmapped_pack_symbols: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "generated_at": _ts(),
            "collector_digits": self.collector_digits,
            "merge_name": self.merge_name,
            "motor_io": self.motor_io,
            "reservation": self.reservation,
            "slice_seconds_merge": self.slice_seconds_merge,
            "symbol_renames": self.symbol_renames,
            "lane_bindings": self.lane_bindings,
            "unmapped_pack_symbols": self.unmapped_pack_symbols,
            "notes": self.notes,
            "method": "explicit_parameter_map",
            "arbitrary_text_replace": False,
            "finished_plc4_used": False,
        }


def build_parameter_map(
    sawtooth: dict[str, Any],
    *,
    pack_symbols: list[str] | None = None,
    gold_collector: str = "414",
) -> SawtoothParamMap:
    merges = sawtooth.get("merges") or []
    lanes = sawtooth.get("lanes") or []
    merge = merges[0] if merges else {}
    motor_io = str(merge.get("motor_io") or "")
    collector = collector_id_from_motor_io(motor_io) or gold_collector

    pmap = SawtoothParamMap(
        collector_digits=collector,
        merge_name=str(merge.get("name") or "SAWTOOTH_MERGE"),
        motor_io=motor_io,
        reservation=str(merge.get("reservation") or ""),
        slice_seconds_merge=merge.get("slice_seconds"),
    )
    pmap.notes.append(
        "Lane PE/drive/conveyor taken from RUN SawLane — never normalized by equal digits"
    )
    pmap.notes.append(
        "Example preserved: LANE_3_P116 conveyor=P116 PE=PE118_P drive=VFD118_EN"
    )

    # Collector family rename MRG414_* → MRG{collector}_*
    if collector != gold_collector:
        pmap.symbol_renames[f"MRG{gold_collector}"] = f"MRG{collector}"
    # Always record gold→site for clarity even when same digits
    pmap.symbol_renames[f"MRG{gold_collector}_"] = f"MRG{collector}_"

    # HMI / enc / collector conveyor tags commonly tied to collector id
    for suffix in ("_Conv", "_Enc", "_SawMerge_HMI"):
        gold = f"P{gold_collector}{suffix}"
        site = f"P{collector}{suffix}"
        if gold != site:
            pmap.symbol_renames[gold] = site

    # Lane bindings from RUN (authoritative)
    for lane in lanes:
        binding = {
            "lane_name": lane.get("name"),
            "lane_index": lane.get("lane_index"),
            "conveyor": lane.get("conveyor"),
            "approach": lane.get("approach"),
            "collision": lane.get("collision"),
            "lane_input": lane.get("lane_input"),
            "photoeye": lane.get("photoeye"),
            "drive": lane.get("drive") or lane.get("vfd"),
            "slice_seconds": lane.get("slice_seconds"),
            "reserve_seconds": lane.get("reserve_seconds"),
            "provenance": lane.get("provenance") or PROV_RUN,
            "pack_bindings": [],
        }
        # Map known gold PE/conveyor tokens when they clearly correspond to this lane
        conv = str(lane.get("conveyor") or "").upper()
        pe = str(lane.get("photoeye") or "").upper()
        if conv:
            gold_conv = f"{conv}_Conv"
            binding["pack_bindings"].append(
                {"pack_symbol_pattern": gold_conv, "site_value": gold_conv, "role": "lane_conveyor_udt"}
            )
            pmap.symbol_renames.setdefault(gold_conv, gold_conv)
        if pe:
            binding["pack_bindings"].append(
                {"pack_symbol_pattern": pe, "site_value": pe, "role": "lane_pe"}
            )
            # Map EZPE###_F style gold full eyes toward RUN PE when digits relate to lane
            # Only via explicit map entries — not digit guessing across different numbers
            pmap.symbol_renames.setdefault(pe, pe)
        pmap.lane_bindings.append(binding)

    # Inventory leftover pack symbols that look site-specific but aren't mapped
    if pack_symbols:
        mapped_keys = set(pmap.symbol_renames.keys()) | set(pmap.symbol_renames.values())
        for sym in pack_symbols:
            su = sym.upper()
            if su in mapped_keys or any(su.startswith(k.upper()) for k in mapped_keys if k.endswith("_")):
                continue
            if re.match(r"^(MRG|P|PE|EZPE|ENC|VFD)\d", su):
                pmap.unmapped_pack_symbols.append(
                    {
                        "symbol": sym,
                        "classification": PROV_CFG,
                        "reason": "Site-like pack symbol without explicit RUN bind in this map",
                    }
                )

    return pmap


def apply_parameter_map_to_program_xml(xml: str, pmap: SawtoothParamMap) -> tuple[str, dict[str, Any]]:
    """Apply explicit renames longest-first. No bare digit search/replace."""
    report = {
        "generated_at": _ts(),
        "renames_applied": [],
        "method": "explicit_symbol_renames_longest_first",
        "arbitrary_global_digit_replace": False,
    }
    out = xml
    # Longest keys first to avoid partial collisions (MRG414_ before MRG414)
    items = sorted(pmap.symbol_renames.items(), key=lambda kv: len(kv[0]), reverse=True)
    for old, new in items:
        if not old or old == new:
            continue
        count = out.count(old)
        if count:
            out = out.replace(old, new)
            report["renames_applied"].append({"from": old, "to": new, "occurrences": count})
    return out, report


def load_pack_program_xml(pack_path: Path) -> str:
    return pack_path.read_text(encoding="utf-8", errors="replace")


def parameterize_sawtooth_pack(
    pack_path: Path,
    sawtooth: dict[str, Any],
) -> dict[str, Any]:
    """Build map, apply to pack XML, return artifacts for Pass 2."""
    text = load_pack_program_xml(pack_path)
    pack_syms = sorted(
        set(
            re.findall(
                r"\b(?:MRG\d+_[A-Za-z0-9_]+|P\d+[A-Z]?_Conv|P\d+[A-Z]?_Enc|"
                r"P\d+[A-Z]?_SawMerge_HMI|PE\d+[A-Z]?_[A-Z0-9]+|EZPE\d+[A-Z0-9_]*)\b",
                text,
            )
        )
    )
    pmap = build_parameter_map(sawtooth, pack_symbols=pack_syms)
    new_xml, apply_report = apply_parameter_map_to_program_xml(text, pmap)
    return {
        "parameter_map": pmap.to_json(),
        "apply_report": apply_report,
        "program_xml": new_xml,
        "lane_count": len(pmap.lane_bindings),
        "rename_count": len(apply_report["renames_applied"]),
        "template_path": str(pack_path),
    }

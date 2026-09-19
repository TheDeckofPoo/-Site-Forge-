#!/usr/bin/env python3
"""Family-neutral PhysicalEndpoint + family-specific Rockwell channel renderers.

PhysicalEndpoint is evidence-derived and family-agnostic:
  adapter / slot / direction / module_bit / catalog / family

Rockwell logical channel strings are rendered ONLY by the family renderer:

  1734 POINT → {adapter}:{I|O}.Data[{slot}].{channel}
  1794 FLEX  → {adapter}:{I|O}.Data[{slot-1}].{channel}  (head at slot 0)

Never force POINT through FLEX addressing or FLEX through POINT.
Finished L5X files are validation oracles only — never discovery inputs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from fortna_hardware_family import (
    FAMILY_FLEX,
    FAMILY_POINT,
    FAMILY_UNKNOWN,
    data_index_for_module,
    detect_family_from_catalog,
)


@dataclass(frozen=True)
class PhysicalEndpoint:
    """Canonical physical I/O endpoint (family-neutral)."""

    machine: str
    adapter: str  # eipcfg / rio name (e.g. AENTR13)
    slot: int  # chassis slot on adapter
    direction: str  # I | O
    module_bit: int  # channel within the module (0-based)
    module_type: str = ""
    family: str = FAMILY_UNKNOWN
    bank_word: int | None = None  # Fortna Octal_Word when known
    fortna_raw_bit: int | None = None
    module_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def physical_endpoint_from_hit(
    hit: dict[str, Any] | None,
    *,
    machine: str = "",
) -> PhysicalEndpoint | None:
    """Build PhysicalEndpoint from a physical_word_map / resolve_word_bit hit."""
    if not isinstance(hit, dict) or not hit:
        return None
    adapter = str(hit.get("rio_name") or hit.get("adapter") or "").strip()
    if not adapter:
        return None
    try:
        slot = int(hit.get("eip_slot") if hit.get("eip_slot") is not None else hit.get("slot") or -1)
    except (TypeError, ValueError):
        slot = -1
    if slot < 0:
        return None
    direction = str(hit.get("direction") or "").strip().upper()
    if direction not in ("I", "O"):
        return None
    try:
        bit = int(hit.get("bit") if hit.get("bit") is not None else 0)
    except (TypeError, ValueError):
        bit = 0
    mtype = str(hit.get("type") or hit.get("module_type") or "")
    family = str(hit.get("family") or detect_family_from_catalog(mtype) or FAMILY_UNKNOWN)
    bank_word = hit.get("octal_word")
    try:
        bank_word_i = int(bank_word) if bank_word is not None else None
    except (TypeError, ValueError):
        bank_word_i = None
    raw_bit = hit.get("fortna_raw_bit")
    try:
        raw_bit_i = int(raw_bit) if raw_bit is not None else None
    except (TypeError, ValueError):
        raw_bit_i = None
    return PhysicalEndpoint(
        machine=str(machine or hit.get("machine") or "").strip(),
        adapter=adapter,
        slot=slot,
        direction=direction,
        module_bit=bit,
        module_type=mtype,
        family=family,
        bank_word=bank_word_i,
        fortna_raw_bit=raw_bit_i,
        module_name=str(hit.get("module_name") or ""),
    )


def render_rockwell_channel(ep: PhysicalEndpoint) -> str:
    """Family-specific Rockwell logical channel string."""
    fam = str(ep.family or detect_family_from_catalog(ep.module_type) or FAMILY_UNKNOWN)
    data_index = data_index_for_module(ep.slot, fam)
    return f"{ep.adapter}:{ep.direction}.Data[{data_index}].{ep.module_bit}"


def render_point_channel(adapter: str, slot: int, direction: str, bit: int) -> str:
    """1734 POINT renderer — Data[slot] (no Flex slot-1 shift)."""
    di = data_index_for_module(int(slot), FAMILY_POINT)
    return f"{adapter}:{direction}.Data[{di}].{int(bit)}"


def render_flex_channel(adapter: str, slot: int, direction: str, bit: int) -> str:
    """1794 FLEX renderer — Data[slot-1] when slot>0."""
    di = data_index_for_module(int(slot), FAMILY_FLEX)
    return f"{adapter}:{direction}.Data[{di}].{int(bit)}"


def assert_family_render_rules() -> None:
    """Invariant checks used by unit tests."""
    assert render_point_channel("AENTR13", 1, "I", 0) == "AENTR13:I.Data[1].0"
    assert render_point_channel("AENTR13", 12, "O", 0) == "AENTR13:O.Data[12].0"
    assert render_point_channel("AENTR13", 14, "O", 0) == "AENTR13:O.Data[14].0"
    # FLEX must differ at slot 1
    assert render_flex_channel("CP5RIO0", 1, "I", 0) == "CP5RIO0:I.Data[0].0"
    assert render_flex_channel("CP5RIO0", 2, "I", 0) == "CP5RIO0:I.Data[1].0"

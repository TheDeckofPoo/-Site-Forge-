#!/usr/bin/env python3
"""Area identity contract: display_name ≠ plc_symbol.

Engineer-visible Area names (Area_Test1, North Sort, Area 1) are display /
engineering identities. They are NOT automatically PLC operand authority.

ES_SIL1_Cat1 IO_AREA requires an Area_UDT controller tag. Site Forge must
create that tag deterministically (clone Main_Area → plc_symbol) or resolve
an explicit mapping. Never assume the display string already exists as a tag.
Never invent controller prefixes (MSCRENOPICK_Area, …).

Layers:
  display_name       — UI / workbook engineering identity (may contain spaces)
  canonical_area_id  — stable internal identity (survives rename)
  plc_symbol         — Logix-legal Area_UDT tag used in ES / Reset / Silence
"""
from __future__ import annotations

import re
from typing import Any


_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
_MULTI_US = re.compile(r"_+")


def area_display_name(raw: Any) -> str:
    """Engineer-facing Area name from a string or area row dict."""
    if isinstance(raw, dict):
        for k in ("display_name", "name", "engineering_name", "area", "areaRef", "id"):
            v = str(raw.get(k) or "").strip()
            if v:
                return v
        return ""
    return str(raw or "").strip()


def area_canonical_id(raw: Any, *, fallback_display: str = "") -> str:
    """Stable internal Area identity.

    Prefer an explicit id / canonical_area_id / source_id. Otherwise derive a
    durable key from the display name without inventing site prefixes.
    Changing display_name later should keep this id when the row carries one.
    """
    if isinstance(raw, dict):
        for k in ("canonical_area_id", "source_id", "id"):
            v = str(raw.get(k) or "").strip()
            # Ignore ids that are just the display string when a better id exists later
            if v:
                return v
        disp = area_display_name(raw) or fallback_display
    else:
        disp = str(raw or "").strip() or fallback_display
    sym = area_plc_symbol(disp)
    if not sym:
        return ""
    # Prefix area_ only when id would otherwise collide with a PLC symbol convention
    # that starts with a digit after sanitization — keep human ids readable.
    return f"area_{sym}" if not sym.startswith("area_") else sym


def area_plc_symbol(display_name: str) -> str:
    """Logix-legal Area_UDT tag from engineer display name.

    Rules:
      - whitespace / punctuation → underscore
      - collapse repeated underscores
      - digit-leading → Area_<rest> (Studio rejects digit-leading tags)
      - never invent MSCRENOPICK_ / controller prefixes
      - empty input → empty (caller must not invent Main_Area here)
    """
    raw = str(display_name or "").strip()
    if not raw:
        return ""
    s = _NON_WORD.sub("_", raw)
    s = _MULTI_US.sub("_", s).strip("_")
    if not s:
        return ""
    if re.match(r"^\d", s):
        s = f"Area_{s}"
    return s


def normalize_area_row(raw: Any) -> dict[str, str]:
    """Return a workbook-ready Area row with the three-layer contract."""
    disp = area_display_name(raw)
    if isinstance(raw, dict):
        cid = area_canonical_id(raw, fallback_display=disp)
        # Preserve prior plc_symbol only when it still sanitizes from same display
        prior_sym = str(raw.get("plc_symbol") or "").strip()
        sym = prior_sym or area_plc_symbol(disp)
        if area_plc_symbol(disp) and prior_sym and prior_sym != area_plc_symbol(disp):
            # Display changed — recompute symbol; identity stays
            sym = area_plc_symbol(disp)
        row = {
            "name": disp,  # back-compat: existing code reads .name as display
            "display_name": disp,
            "id": str(raw.get("id") or cid or disp),
            "canonical_area_id": cid or str(raw.get("id") or disp),
            "plc_symbol": sym,
        }
        src = str(raw.get("source") or "").strip()
        if src:
            row["source"] = src
        return row
    sym = area_plc_symbol(disp)
    cid = area_canonical_id(disp)
    return {
        "name": disp,
        "display_name": disp,
        "id": cid or disp,
        "canonical_area_id": cid or disp,
        "plc_symbol": sym,
    }


def collect_area_plc_symbols(
    *,
    areas: list[Any] | None = None,
    safety_zones: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Union of plc_symbols that must receive Area_UDT tags for generation."""
    out: list[str] = []
    seen: set[str] = set()

    def _add(disp_or_row: Any) -> None:
        if isinstance(disp_or_row, dict):
            sym = str(disp_or_row.get("plc_symbol") or "").strip() or area_plc_symbol(
                area_display_name(disp_or_row)
            )
        else:
            sym = area_plc_symbol(str(disp_or_row or ""))
        if not sym:
            return
        key = sym.upper()
        if key in seen:
            return
        seen.add(key)
        out.append(sym)

    for a in areas or []:
        _add(a)
    for z in safety_zones or []:
        if not isinstance(z, dict):
            continue
        # Engineer / operational zones only — Default inventory has no Area_UDT
        if z.get("defaultSafety") or z.get("isDefault") or z.get("isUnassignedBucket"):
            continue
        if z.get("operational") is False:
            continue
        if z.get("areaUnlinked"):
            continue
        _add(z.get("area") or z.get("areaRef") or "")
    return out

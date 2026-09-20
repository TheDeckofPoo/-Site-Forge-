#!/usr/bin/env python3
"""Explicit hardware FAMILY registry for Site Forge I/O.

HardwareIOModel
       ↓
Hardware Family
       ├── 1794 FLEX I/O
       ├── 1734 POINT I/O
       ├── ETHERNET_DRIVE (PowerFlex / 20-COMM / PF70 — NOT Flex AENT)
       └── future family
              ↓
      correct renderer / module semantics / L5X generation

Do NOT scatter one-off catalog checks. Do NOT silently translate 1734 ↔ 1794.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable


FAMILY_FLEX = "1794"
FAMILY_POINT = "1734"
FAMILY_ETHERNET_DRIVE = "ETHERNET_DRIVE"
FAMILY_UNKNOWN = "UNKNOWN"

# Compiler-supported POINT child catalogs (must match fortna_autogen EIP_CHILD_TEMPLATE).
POINT_SUPPORTED_CATALOGS = frozenset(
    {
        "1734-IB8",
        "1734-OB8",
        "1734-OB8E",
        "1734-IA4",
        "1734-OA4",
    }
)
POINT_SUPPORTED_ADAPTERS = frozenset(
    {
        "1734-AENT",
        "1734-AENTR",
    }
)

# Compiler-supported FLEX child catalogs.
FLEX_SUPPORTED_CATALOGS = frozenset(
    {
        "1794-IA16",
        "1794-OA8I",
        "1794-OW8",
        "1794-IB16",
        "1794-OB16P",
    }
)
FLEX_SUPPORTED_ADAPTERS = frozenset(
    {
        "1794-AENT",
        "1794-AENTR",
    }
)


@dataclass(frozen=True)
class HardwareFamily:
    """Family identity + compiler/renderer hooks."""

    family: str
    label: str
    adapter_prefix: str
    bus_size: int
    parent_template: str
    parent_catalog: str
    parent_type: str
    renderer_id: str  # 'flex' | 'point'
    supported_adapters: frozenset[str] = field(default_factory=frozenset)
    supported_modules: frozenset[str] = field(default_factory=frozenset)
    # Data[] index: FLEX uses chassis_slot-1 (head at 0); POINT keeps chassis slot.
    data_index_mode: str = "slot"  # 'slot_minus_one' | 'slot'


FAMILIES: dict[str, HardwareFamily] = {
    FAMILY_FLEX: HardwareFamily(
        family=FAMILY_FLEX,
        label="FLEX I/O",
        adapter_prefix="1794",
        bus_size=8,
        parent_template="IO_1N90",
        parent_catalog="1794-AENT",
        parent_type="1794-AENT",
        renderer_id="flex",
        supported_adapters=FLEX_SUPPORTED_ADAPTERS,
        supported_modules=FLEX_SUPPORTED_CATALOGS,
        data_index_mode="slot_minus_one",
    ),
    FAMILY_POINT: HardwareFamily(
        family=FAMILY_POINT,
        label="POINT I/O",
        adapter_prefix="1734",
        bus_size=40,
        parent_template="IO_1N80",
        parent_catalog="1734-AENTR/C",
        parent_type="1734-AENT",
        renderer_id="point",
        supported_adapters=POINT_SUPPORTED_ADAPTERS,
        supported_modules=POINT_SUPPORTED_CATALOGS,
        data_index_mode="slot",
    ),
}


_CATALOG_RE = re.compile(r"^(\d{4})-([A-Za-z0-9]+)", re.I)
# Proven EIP PowerFlex / drive catalog patterns (topology presentation only).
# 20AD… / 20BD… = PF70-style; 22A/B/C = PF4/40/400; 25B/C = PF525/755.
_DRIVE_CATALOG_RE = re.compile(
    r"^(?:"
    r"20-COMM|"
    r"20COMM|"
    r"20[ABCD]|"  # PF70 / PF700 / PF753 family catalogs (e.g. 20AD014A3AYNANNN)
    r"22[ABC]|"  # PF4 / PF40 / PF400
    r"25[ABC]|"  # PF525 / PF755
    r"PF70|"
    r"PF525|"
    r"PF755|"
    r"POWERFLEX"
    r")",
    re.I,
)


def normalize_catalog(raw: str | None) -> str:
    """Strip revision / whitespace → e.g. 1734-AENTR/C → 1734-AENTR."""
    cat = str(raw or "").strip().upper()
    cat = re.sub(r"[/_\-][A-Z]\d*$", "", cat)
    cat = re.sub(r"\s+", "", cat)
    return cat


def is_ethernet_drive_catalog(catalog: str | None) -> bool:
    """True for PowerFlex / 20-COMM / PF70 / Drive EIP catalogs — never Flex AENT."""
    raw = str(catalog or "").strip()
    if not raw:
        return False
    u = raw.upper()
    cat = normalize_catalog(raw)
    if "1794" in cat or "1734" in cat or "1738" in cat:
        return False
    if "AENT" in cat:
        return False
    if "POWERFLEX" in u or "PF70" in u or "PF525" in u or "PF755" in u or "PF4" in u:
        return True
    if "20-COMM" in u or cat.startswith("20COMM") or cat.startswith("20-COMM"):
        return True
    if _DRIVE_CATALOG_RE.match(cat) or _DRIVE_CATALOG_RE.match(u.replace(" ", "")):
        return True
    # Generic 'Drive' token only when not an I/O family catalog
    if re.search(r"\bDRIVE\b", u) and not cat[:4].isdigit():
        return True
    return False


def detect_family_from_catalog(catalog: str | None) -> str:
    """Map a single catalog number to family id. Unknown stays UNKNOWN — never invent 1794.

    PowerFlex / 20-COMM / PF70 drive catalogs → ETHERNET_DRIVE (not Flex AENT).
    """
    cat = normalize_catalog(catalog)
    if not cat:
        return FAMILY_UNKNOWN
    if is_ethernet_drive_catalog(catalog):
        return FAMILY_ETHERNET_DRIVE
    m = _CATALOG_RE.match(cat)
    if m:
        prefix = m.group(1)
        if prefix == "1794":
            return FAMILY_FLEX
        if prefix in ("1734", "1738"):
            return FAMILY_POINT
    if "1734" in cat or "1738" in cat:
        return FAMILY_POINT
    if "1794" in cat:
        return FAMILY_FLEX
    return FAMILY_UNKNOWN


def detect_family_from_types(types: list[str] | None) -> str:
    """Detect family from a list of module/adapter type strings.

    Prefer explicit POINT / FLEX evidence. Do NOT default unknown → 1794.
    Mixed evidence prefers POINT if any 1734 present (never translate POINT→FLEX).
    Drive-only sets return ETHERNET_DRIVE.
    """
    found: set[str] = set()
    for t in types or []:
        fam = detect_family_from_catalog(t)
        if fam != FAMILY_UNKNOWN:
            found.add(fam)
    if FAMILY_POINT in found:
        return FAMILY_POINT
    if FAMILY_FLEX in found:
        return FAMILY_FLEX
    if FAMILY_ETHERNET_DRIVE in found:
        return FAMILY_ETHERNET_DRIVE
    return FAMILY_UNKNOWN


def get_family(family_id: str | None) -> HardwareFamily | None:
    if not family_id:
        return None
    return FAMILIES.get(str(family_id).strip())


def data_index_for_module(slot: int, family: str | None) -> int:
    """Logix Data[] index for a bridged module — family-aware.

    1794 Flex: chassis slot S>0 → Data[S-1] (head/AENT at slot 0).
    1734 POINT: keep chassis slot (print-accurate 1-based addressing).
    UNKNOWN: do not apply Flex slot-1 assumption — return raw slot.
    """
    s = int(slot or 0)
    fam = get_family(family)
    if fam and fam.data_index_mode == "slot_minus_one" and s > 0:
        return s - 1
    return s


def channel_capacity_for_catalog(catalog: str | None, *, connection: str = "") -> int:
    """Digital channel capacity from catalog — family-agnostic bounds."""
    u = normalize_catalog(catalog)
    conn = (connection or "").upper()
    if is_ethernet_drive_catalog(catalog):
        return 0
    if conn == "HEADNODE" or "AENT" in u:
        return 0
    if any(x in u for x in ("OA8", "OB8", "OW8", "IA8", "IB8")):
        return 8
    if any(x in u for x in ("IA16", "IB16", "OB16", "OW16", "OA16")):
        return 16
    if any(x in u for x in ("IA4", "IB4", "OA4", "OB4")):
        return 4
    return 0


def max_bits_for_catalog(catalog: str | None) -> int:
    """Bit fan-out for word/bit indexing (POINT 4/8-pt must not assume 16)."""
    cap = channel_capacity_for_catalog(catalog)
    return cap if cap > 0 else 16


def is_adapter_catalog(catalog: str | None) -> bool:
    """True for FLEX/POINT AENT adapters only — PowerFlex drives are never adapters."""
    if is_ethernet_drive_catalog(catalog):
        return False
    u = normalize_catalog(catalog)
    return "AENT" in u


def compiler_supports_catalog(catalog: str | None) -> tuple[bool, str]:
    """Return (ok, reason). Adapters always ok when family known; children need template.

    ETHERNET_DRIVE is topology-classification only — not an I/O child template path.
    """
    cat = normalize_catalog(catalog)
    fam_id = detect_family_from_catalog(catalog if catalog else cat)
    if fam_id == FAMILY_ETHERNET_DRIVE:
        # Classification only — do not activate ETHERNET_VFD_UDT generation here
        return True, ""
    if fam_id == FAMILY_UNKNOWN:
        return False, f"Unknown hardware family for catalog: {cat or '(empty)'}"
    fam = get_family(fam_id)
    assert fam is not None
    if is_adapter_catalog(catalog if catalog else cat):
        # Accept known adapters; unknown AENT revision still blocks precisely
        base = cat.split("/")[0]
        if any(base.startswith(a) or a.startswith(base) for a in fam.supported_adapters):
            return True, ""
        return False, f"Unsupported {fam.label} adapter catalog:\n{cat}"
    if cat in fam.supported_modules:
        return True, ""
    # Allow prefix match for revision-stripped forms already normalized
    if any(cat == m or cat.startswith(m + "/") for m in fam.supported_modules):
        return True, ""
    if fam_id == FAMILY_POINT:
        return False, f"Unsupported POINT I/O catalog:\n{cat}"
    if fam_id == FAMILY_FLEX:
        return False, f"Unsupported FLEX I/O catalog:\n{cat}"
    return False, f"Unsupported catalog:\n{cat}"


def assert_no_family_substitution(
    proven_catalog: str | None, emitted_catalog: str | None
) -> None:
    """Raise if L5X emission substituted a different hardware family."""
    proven_fam = detect_family_from_catalog(proven_catalog)
    emitted_fam = detect_family_from_catalog(emitted_catalog)
    if proven_fam == FAMILY_UNKNOWN or emitted_fam == FAMILY_UNKNOWN:
        return
    if proven_fam != emitted_fam:
        raise ValueError(
            f"Hardware family substitution blocked: proven {proven_catalog} "
            f"({proven_fam}) must not emit as {emitted_catalog} ({emitted_fam})"
        )


def adapter_family_from_modules(modules: list[dict[str, Any]] | None) -> str:
    """Resolve adapter-level family from child/head module catalogs."""
    types = []
    for m in modules or []:
        types.append(str(m.get("type") or m.get("catalog") or ""))
        if m.get("family"):
            fam = str(m.get("family")).strip()
            if fam in FAMILIES:
                # Prefer explicit POINT if any module declares it
                if fam == FAMILY_POINT:
                    return FAMILY_POINT
                types.append(fam)
    return detect_family_from_types(types)


def family_scheme_description(family: str | None) -> str:
    fam = get_family(family)
    if fam and fam.family == FAMILY_FLEX:
        return (
            "1794 Flex: Data[slot-1] when slot>0 (head=slot0); "
            "do not apply to 1734 POINT"
        )
    if fam and fam.family == FAMILY_POINT:
        return (
            "1734 POINT: Data[slot] print-accurate chassis addressing "
            "(no Flex slot-1 shift)"
        )
    if str(family or "").strip() == FAMILY_ETHERNET_DRIVE:
        return (
            "ETHERNET_DRIVE: PowerFlex / 20-COMM / PF70 topology presentation; "
            "not Flex AENT; no ETHERNET_VFD_UDT auto-generation"
        )
    return "family unknown — no Flex slot-1 assumption applied"


# UI / renderer registry key (mirrors JS HardwareFamily.renderer_id)
RENDERER_BY_FAMILY = {
    FAMILY_FLEX: "flex",
    FAMILY_POINT: "point",
    FAMILY_ETHERNET_DRIVE: "ethernet_drive",
}


def renderer_for_family(family: str | None) -> str:
    return RENDERER_BY_FAMILY.get(str(family or "").strip(), "unknown")

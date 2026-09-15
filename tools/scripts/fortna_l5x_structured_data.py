#!/usr/bin/env python3
"""Datatype-aware Rockwell L5X Decorated (+ optional L5K) structured tag data.

Fixes Studio import warnings:
  - empty <Structure DataType="X"/> without StructureMember/DataValueMember
  - Comm_UDT String DATA emitted as SINT Dimensions (datatype mismatch)
  - Merge_Time / nested UDT shells without expanded members

Walks DataType definitions from library/controller XML and emits recursive
Structure / StructureMember / DataValueMember matching the datatype shape.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from xml.sax.saxutils import escape as _xml_escape


# Atomic / scalar families that use DataValueMember (not StructureMember)
_SCALAR_TYPES = frozenset(
    {
        "BOOL",
        "BIT",
        "SINT",
        "INT",
        "DINT",
        "LINT",
        "USINT",
        "UINT",
        "UDINT",
        "ULINT",
        "REAL",
        "LREAL",
        "STRING",
    }
)


@dataclass
class DtMember:
    name: str
    data_type: str
    dimension: int = 0
    radix: str = ""
    hidden: bool = False
    bit_number: int | None = None
    target: str = ""


@dataclass
class DataTypeDef:
    name: str
    members: list[DtMember] = field(default_factory=list)
    family: str = ""


def parse_datatypes(xml_text: str) -> dict[str, DataTypeDef]:
    """Parse all <DataType Name=...> blocks into a name→def map."""
    out: dict[str, DataTypeDef] = {}
    for m in re.finditer(
        r'<DataType\s+Name="([^"]+)"([^>]*)>(.*?)</DataType>',
        xml_text or "",
        re.S | re.I,
    ):
        name = m.group(1)
        attrs = m.group(2) or ""
        body = m.group(3) or ""
        fam_m = re.search(r'Family="([^"]*)"', attrs)
        fam = fam_m.group(1) if fam_m else ""
        members: list[DtMember] = []
        for mm in re.finditer(r"<Member\b([^>]*)/?>", body, re.I):
            a = mm.group(1) or ""
            def _attr(k: str) -> str:
                hm = re.search(rf'{k}="([^"]*)"', a)
                return hm.group(1) if hm else ""

            mn = _attr("Name")
            dt = _attr("DataType")
            if not mn or not dt:
                continue
            try:
                dim = int(float(_attr("Dimension") or "0"))
            except ValueError:
                dim = 0
            hidden = (_attr("Hidden") or "").lower() == "true"
            bit_s = _attr("BitNumber")
            bit_n = int(bit_s) if bit_s.isdigit() else None
            members.append(
                DtMember(
                    name=mn,
                    data_type=dt,
                    dimension=dim,
                    radix=_attr("Radix"),
                    hidden=hidden,
                    bit_number=bit_n,
                    target=_attr("Target"),
                )
            )
        out[name] = DataTypeDef(name=name, members=members, family=fam)
    return out


def _is_scalar(dt: str, defs: dict[str, DataTypeDef]) -> bool:
    u = (dt or "").upper()
    if u in _SCALAR_TYPES:
        return True
    if u.startswith("STRING"):
        return True
    # BIT packed into hidden SINT — still scalar DataValueMember when visible
    d = defs.get(dt)
    if d and d.family == "StringFamily":
        return False  # string UDT → StructureMember
    return False


def _default_scalar_value(dt: str) -> str:
    u = (dt or "").upper()
    if u == "REAL" or u == "LREAL":
        return "0.0"
    if u == "BOOL" or u == "BIT":
        return "0"
    return "0"


def _emit_string_udt(dt_name: str, text: str = "") -> str:
    """Gold Fortna string UDT Decorated form (String_15 / String_20)."""
    s = text or ""
    return (
        f'<StructureMember Name="{{NAME}}" DataType="{_xml_escape(dt_name)}">'
        f'<DataValueMember Name="LEN" DataType="DINT" Radix="Decimal" Value="{len(s)}"/>'
        f'<DataValueMember Name="DATA" DataType="{_xml_escape(dt_name)}" Radix="ASCII">'
        f"<![CDATA['{_xml_escape(s)}']]>"
        f"</DataValueMember>"
        f"</StructureMember>"
    )


def _emit_timer(name: str = "CommLoss_Tmr") -> str:
    return (
        f'<StructureMember Name="{_xml_escape(name)}" DataType="TIMER">'
        f'<DataValueMember Name="PRE" DataType="DINT" Radix="Decimal" Value="0"/>'
        f'<DataValueMember Name="ACC" DataType="DINT" Radix="Decimal" Value="0"/>'
        f'<DataValueMember Name="EN" DataType="BOOL" Value="0"/>'
        f'<DataValueMember Name="TT" DataType="BOOL" Value="0"/>'
        f'<DataValueMember Name="DN" DataType="BOOL" Value="0"/>'
        f"</StructureMember>"
    )


def emit_structure_members(
    dt_name: str,
    defs: dict[str, DataTypeDef],
    *,
    values: dict[str, Any] | None = None,
    depth: int = 0,
) -> str:
    """Emit inner StructureMember/DataValueMember XML for a datatype (no outer Structure)."""
    if depth > 12:
        return ""
    values = values or {}
    ddef = defs.get(dt_name)
    if not ddef:
        # Built-ins without DataType block
        if (dt_name or "").upper() == "TIMER":
            return _emit_timer("PRE_PLACEHOLDER").replace(
                'Name="PRE_PLACEHOLDER"', 'Name="__TIMER__"'
            )
        return ""

    parts: list[str] = []
    for mem in ddef.members:
        if mem.hidden and mem.bit_number is None and not mem.target:
            # Skip hidden padding SINTs (ZZZZ…) — BITs targeting them are emitted as BOOL
            if mem.name.startswith("ZZZZ") or mem.data_type.upper() == "SINT":
                continue
        if mem.data_type.upper() == "BIT":
            # Visible BIT → BOOL DataValueMember (Decorated convention)
            val = values.get(mem.name, 0)
            parts.append(
                f'<DataValueMember Name="{_xml_escape(mem.name)}" DataType="BOOL" '
                f'Value="{int(val)}"/>'
            )
            continue
        if mem.hidden and mem.name.startswith("ZZZZ"):
            continue

        child_def = defs.get(mem.data_type)
        if child_def and child_def.family == "StringFamily":
            sm = _emit_string_udt(mem.data_type, str(values.get(mem.name, "") or ""))
            parts.append(sm.replace('{NAME}', mem.name).replace("{NAME}", mem.name))
            # fix placeholder
            parts[-1] = _emit_string_udt(mem.data_type, str(values.get(mem.name, "") or "")).replace(
                'Name="{NAME}"', f'Name="{_xml_escape(mem.name)}"'
            )
            continue

        if (mem.data_type or "").upper() == "TIMER":
            parts.append(_emit_timer(mem.name))
            continue

        if child_def and not _is_scalar(mem.data_type, defs):
            inner = emit_structure_members(
                mem.data_type, defs, values=values.get(mem.name) if isinstance(values.get(mem.name), dict) else {}, depth=depth + 1
            )
            parts.append(
                f'<StructureMember Name="{_xml_escape(mem.name)}" '
                f'DataType="{_xml_escape(mem.data_type)}">{inner}</StructureMember>'
            )
            continue

        # Scalar
        radix = mem.radix if mem.radix and mem.radix not in ("NullType", "") else "Decimal"
        if (mem.data_type or "").upper() in ("REAL", "LREAL"):
            radix = "Float"
        if (mem.data_type or "").upper() == "BOOL":
            parts.append(
                f'<DataValueMember Name="{_xml_escape(mem.name)}" DataType="BOOL" '
                f'Value="{int(values.get(mem.name, 0) or 0)}"/>'
            )
        else:
            val = values.get(mem.name, _default_scalar_value(mem.data_type))
            parts.append(
                f'<DataValueMember Name="{_xml_escape(mem.name)}" '
                f'DataType="{_xml_escape(mem.data_type)}" Radix="{_xml_escape(radix)}" '
                f'Value="{_xml_escape(str(val))}"/>'
            )
    return "".join(parts)


def emit_decorated_structure(
    dt_name: str,
    defs: dict[str, DataTypeDef],
    *,
    values: dict[str, Any] | None = None,
) -> str:
    """Full <Structure DataType="…">…</Structure> with members expanded."""
    inner = emit_structure_members(dt_name, defs, values=values)
    if not inner:
        # Never emit empty Structure — caller should omit Data or use L5K-only
        return ""
    return f'<Structure DataType="{_xml_escape(dt_name)}">{inner}</Structure>'


def emit_comm_udt_tag(name: str, defs: dict[str, DataTypeDef] | None = None) -> str:
    """Known-good Comm_UDT tag: L5K zero-init + Decorated StructureMembers (string form)."""
    # Gold L5K zero template (empty MAC/IP)
    l5k = "[[[0,0,0],[0],0,0.00000000e+000,[0,''],[0,'']]]"
    defs = defs or {}
    struct = ""
    if "Comm_UDT" in defs:
        struct = emit_decorated_structure("Comm_UDT", defs)
    if not struct or 'DataType="SINT" Dimensions="' in struct:
        # Hardcoded gold shape — String DATA as String_N CDATA (not SINT Dimensions)
        struct = (
            '<Structure DataType="Comm_UDT">'
            f'{_emit_timer("CommLoss_Tmr")}'
            '<StructureMember Name="Flt" DataType="Comm_Flt">'
            '<DataValueMember Name="CommLoss" DataType="BOOL" Value="0"/>'
            '<DataValueMember Name="UpStrmCommLoss" DataType="BOOL" Value="0"/>'
            "</StructureMember>"
            '<DataValueMember Name="Comm_Code" DataType="DINT" Radix="Decimal" Value="0"/>'
            '<DataValueMember Name="Firmware" DataType="REAL" Radix="Float" Value="0.0"/>'
            '<StructureMember Name="MACId" DataType="String_20">'
            '<DataValueMember Name="LEN" DataType="DINT" Radix="Decimal" Value="0"/>'
            '<DataValueMember Name="DATA" DataType="String_20" Radix="ASCII"><![CDATA[\'\']]></DataValueMember>'
            "</StructureMember>"
            '<StructureMember Name="IP_Address" DataType="String_15">'
            '<DataValueMember Name="LEN" DataType="DINT" Radix="Decimal" Value="0"/>'
            '<DataValueMember Name="DATA" DataType="String_15" Radix="ASCII"><![CDATA[\'\']]></DataValueMember>'
            "</StructureMember>"
            "</Structure>"
        )
    return (
        f'<Tag Name="{_xml_escape(name)}" TagType="Base" DataType="Comm_UDT" '
        f'Constant="false" ExternalAccess="Read/Write">'
        f'<Data Format="L5K"><![CDATA[{l5k}]]></Data>'
        f'<Data Format="Decorated">{struct}</Data></Tag>'
    )


def emit_merge_time_tag(
    name: str,
    defs: dict[str, DataTypeDef],
    *,
    clear: int = 8000,
    no_cartons: int = 8000,
    release: int = 10000,
    release_full: int = 15000,
) -> str:
    """Merge_Time UDT with gold HMI defaults + L5K."""
    values = {
        "HMI": {
            "FltClearTime": 0,
            "ReleaseTime": release,
            "ReleaseTimeFull": release_full,
            "ClearTime": clear,
            "NoCartonsTime": no_cartons,
            "Enable_CX": 0,
            "CX_TimeReset": 0,
        },
        "ReleaseTime": release,
        "ClearTime": clear,
        "NoCartonsTime": no_cartons,
    }
    struct = emit_decorated_structure("Merge_Time", defs, values=values)
    # L5K from PLC5 gold: [[[HMI...],Release,Clear,NoCartons]]
    l5k = f"[[[0,{release},{release_full},{clear},{no_cartons},0],{release},{clear},{no_cartons}]]"
    if not struct:
        # Minimal hand-built if datatype missing from defs
        struct = (
            '<Structure DataType="Merge_Time">'
            '<StructureMember Name="HMI" DataType="Merge_Time_HMI">'
            f'<DataValueMember Name="FltClearTime" DataType="INT" Radix="Decimal" Value="0"/>'
            f'<DataValueMember Name="ReleaseTime" DataType="DINT" Radix="Decimal" Value="{release}"/>'
            f'<DataValueMember Name="ReleaseTimeFull" DataType="DINT" Radix="Decimal" Value="{release_full}"/>'
            f'<DataValueMember Name="ClearTime" DataType="INT" Radix="Decimal" Value="{clear}"/>'
            f'<DataValueMember Name="NoCartonsTime" DataType="INT" Radix="Decimal" Value="{no_cartons}"/>'
            f'<DataValueMember Name="Enable_CX" DataType="BOOL" Value="0"/>'
            f'<DataValueMember Name="CX_TimeReset" DataType="BOOL" Value="0"/>'
            "</StructureMember>"
            f'<DataValueMember Name="ReleaseTime" DataType="DINT" Radix="Decimal" Value="{release}"/>'
            f'<DataValueMember Name="ClearTime" DataType="INT" Radix="Decimal" Value="{clear}"/>'
            f'<DataValueMember Name="NoCartonsTime" DataType="INT" Radix="Decimal" Value="{no_cartons}"/>'
            "</Structure>"
        )
    return (
        f'<Tag Name="{_xml_escape(name)}" TagType="Base" DataType="Merge_Time" '
        f'Constant="false" ExternalAccess="Read/Write">'
        f'<Data Format="L5K"><![CDATA[{l5k}]]></Data>'
        f'<Data Format="Decorated">{struct}</Data></Tag>'
    )


# Gold L5K zero-init for Merge_2to1 AOI instance (from PLC5 EDITED export)
_MERGE_2TO1_L5K = (
    "[1,0,0,0,0,0,0,0,0,0,0,0,0,"
    "[[0,0,0],[0,0,0],[0,0,0],0,0,0,0],"
    "[[0,0,0],[0,0,0],[0,0,0],0,0,0,0],"
    "[[0,0,0],[0,0,0],0,0,0,0,0],"
    "0,0,0,[0,0,0],[0,0,0],32000]"
)

# Visible Decorated scalars for Merge_2to1 (EnableIn=1 matches gold). Nested
# TIMER/UDT locals are carried by L5K; Studio accepts this hybrid.
_MERGE_2TO1_DECORATED_SCALARS = (
    '<DataValueMember Name="EnableIn" DataType="BOOL" Value="1"/>'
    '<DataValueMember Name="EnableOut" DataType="BOOL" Value="0"/>'
    '<DataValueMember Name="I_MainLane_Conv_Type" DataType="BOOL" Value="0"/>'
    '<DataValueMember Name="I_InductLane_Conv_Type" DataType="BOOL" Value="0"/>'
    '<DataValueMember Name="I_Enable_Upstream_ExitPE_Check" DataType="BOOL" Value="0"/>'
    '<DataValueMember Name="I_Hold_InductLane" DataType="BOOL" Value="0"/>'
    '<DataValueMember Name="I_Merge_FltClearTime" DataType="INT" Radix="Decimal" Value="0"/>'
    '<DataValueMember Name="I_MergeCX_Enable" DataType="BOOL" Value="0"/>'
    '<DataValueMember Name="I_MergeCX_TimeReset" DataType="BOOL" Value="0"/>'
    '<DataValueMember Name="I_MainLane_AddNotReadyBit" DataType="BOOL" Value="0"/>'
    '<DataValueMember Name="I_InductLane_AddNotlReadyBit" DataType="BOOL" Value="0"/>'
    '<DataValueMember Name="O_MainLane_Conv_RunHold" DataType="BOOL" Value="0"/>'
    '<DataValueMember Name="O_InductLane_Conv_RunHold" DataType="BOOL" Value="0"/>'
)


def emit_merge_2to1_tag(name: str) -> str:
    """Merge_2to1 AOI instance with gold L5K + non-empty Decorated Structure."""
    struct = (
        f'<Structure DataType="Merge_2to1">{_MERGE_2TO1_DECORATED_SCALARS}</Structure>'
    )
    return (
        f'<Tag Name="{_xml_escape(name)}" TagType="Base" DataType="Merge_2to1" '
        f'Constant="false" ExternalAccess="Read/Write">'
        f'<Data Format="L5K"><![CDATA[{_MERGE_2TO1_L5K}]]></Data>'
        f'<Data Format="Decorated">{struct}</Data></Tag>'
    )


def emit_aoi_instance_tag(name: str, aoi_type: str) -> str:
    """AOI instance tag — prefer typed helpers; generic falls back to L5K-less stub."""
    if (aoi_type or "") == "Merge_2to1":
        return emit_merge_2to1_tag(name)
    return (
        f'<Tag Name="{_xml_escape(name)}" TagType="Base" '
        f'DataType="{_xml_escape(aoi_type)}" Constant="false" '
        f'ExternalAccess="Read/Write"/>'
    )


def validate_decorated_structure(xml_fragment: str, dt_name: str) -> list[str]:
    """Return list of structural problems in a Decorated Structure fragment."""
    issues: list[str] = []
    if not xml_fragment or not xml_fragment.strip():
        issues.append(f"{dt_name}: empty data fragment")
        return issues
    if re.search(
        rf'<Structure\s+DataType="{re.escape(dt_name)}"\s*/>', xml_fragment
    ):
        issues.append(f"{dt_name}: empty Structure shell (needs StructureMember/DataValueMember)")
    if "DataType=\"SINT\" Dimensions=" in xml_fragment and "String_" in xml_fragment:
        issues.append(f"{dt_name}: String DATA emitted as SINT Dimensions (use String_N CDATA form)")
    return issues

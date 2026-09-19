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
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as _xml_escape


class UnsupportedStructuredDataError(ValueError):
    """Raised when Decorated cannot be emitted safely from a datatype."""


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

# Types rewritten from DataType on pack/autogen export (Decorated must match alone).
DEFAULT_REWRITE_STRUCTURED_TYPES = frozenset({"Track_Divert_UDT", "Area_UDT"})

# Scalar array Dimensions above this are rejected (do not invent huge blobs).
_MAX_SCALAR_ARRAY_DIM = 512


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


def _emit_string_udt(dt_name: str, name: str, text: str = "") -> str:
    """Gold Fortna string UDT Decorated form (String_15 / String_20 / Location_String).

    Empty DATA uses bare CDATA (`<![CDATA[]]>`); non-empty wraps the ASCII
    payload in single quotes inside CDATA (`<![CDATA['text']]>`), matching
    Studio-exported Fortna library / finished PLC tags.
    """
    s = text or ""
    if s:
        cdata = f"<![CDATA['{_xml_escape(s)}']]>"
    else:
        cdata = "<![CDATA[]]>"
    return (
        f'<StructureMember Name="{_xml_escape(name)}" DataType="{_xml_escape(dt_name)}">'
        f'<DataValueMember Name="LEN" DataType="DINT" Radix="Decimal" Value="{len(s)}"/>'
        f'<DataValueMember Name="DATA" DataType="{_xml_escape(dt_name)}" Radix="ASCII">'
        f"{cdata}"
        f"</DataValueMember>"
        f"</StructureMember>"
    )


def _emit_timer(name: str = "CommLoss_Tmr", values: dict[str, Any] | None = None) -> str:
    vals = values if isinstance(values, dict) else {}
    pre = int(vals.get("PRE", 0) or 0)
    acc = int(vals.get("ACC", 0) or 0)
    en = int(vals.get("EN", 0) or 0)
    tt = int(vals.get("TT", 0) or 0)
    dn = int(vals.get("DN", 0) or 0)
    return (
        f'<StructureMember Name="{_xml_escape(name)}" DataType="TIMER">'
        f'<DataValueMember Name="PRE" DataType="DINT" Radix="Decimal" Value="{pre}"/>'
        f'<DataValueMember Name="ACC" DataType="DINT" Radix="Decimal" Value="{acc}"/>'
        f'<DataValueMember Name="EN" DataType="BOOL" Value="{en}"/>'
        f'<DataValueMember Name="TT" DataType="BOOL" Value="{tt}"/>'
        f'<DataValueMember Name="DN" DataType="BOOL" Value="{dn}"/>'
        f"</StructureMember>"
    )


def _emit_scalar_array_member(
    name: str,
    data_type: str,
    dimension: int,
    *,
    radix: str = "Decimal",
    values: list[Any] | None = None,
) -> str:
    """Emit ArrayMember of scalar elements in datatype order."""
    if dimension <= 0:
        raise UnsupportedStructuredDataError(f"{name}: array Dimension must be > 0")
    if dimension > _MAX_SCALAR_ARRAY_DIM:
        raise UnsupportedStructuredDataError(
            f"{name}: array Dimension {dimension} exceeds supported max {_MAX_SCALAR_ARRAY_DIM}"
        )
    dt_u = (data_type or "").upper()
    if dt_u in ("REAL", "LREAL"):
        radix = "Float"
    elif not radix or radix in ("NullType",):
        radix = "Decimal"
    seq = list(values) if isinstance(values, (list, tuple)) else []
    elems: list[str] = []
    for i in range(dimension):
        raw = seq[i] if i < len(seq) else _default_scalar_value(data_type)
        if dt_u in ("BOOL", "BIT"):
            elems.append(f'<Element Index="[{i}]" Value="{int(raw or 0)}"/>')
        else:
            elems.append(
                f'<Element Index="[{i}]" Value="{_xml_escape(str(raw))}"/>'
            )
    return (
        f'<ArrayMember Name="{_xml_escape(name)}" DataType="{_xml_escape(data_type)}" '
        f'Dimensions="{dimension}" Radix="{_xml_escape(radix)}">'
        f'{"".join(elems)}</ArrayMember>'
    )


def emit_structure_members(
    dt_name: str,
    defs: dict[str, DataTypeDef],
    *,
    values: dict[str, Any] | None = None,
    depth: int = 0,
    strict: bool = False,
) -> str:
    """Emit inner StructureMember/DataValueMember/ArrayMember XML for a datatype.

    Members follow DataType declaration order/names. Nested structures, scalar
    arrays, and scalars are supported. When ``strict`` is True, missing nested
    datatypes / structure-arrays raise UnsupportedStructuredDataError instead of
    inventing order.
    """
    if depth > 12:
        if strict:
            raise UnsupportedStructuredDataError(f"{dt_name}: nesting depth exceeded")
        return ""
    values = values or {}
    ddef = defs.get(dt_name)
    if not ddef:
        if (dt_name or "").upper() == "TIMER":
            return _emit_timer("__TIMER__", values if isinstance(values, dict) else None)
        if strict:
            raise UnsupportedStructuredDataError(
                f"{dt_name}: datatype definition missing — cannot invent Decorated members"
            )
        return ""

    parts: list[str] = []
    for mem in ddef.members:
        if mem.hidden and mem.bit_number is None and not mem.target:
            # Skip hidden packing SINTs (ZZZZ…) — BITs targeting them emit as BOOL
            if mem.name.startswith("ZZZZ") or mem.data_type.upper() == "SINT":
                continue
        if mem.data_type.upper() == "BIT":
            val = values.get(mem.name, 0)
            parts.append(
                f'<DataValueMember Name="{_xml_escape(mem.name)}" DataType="BOOL" '
                f'Value="{int(val or 0)}"/>'
            )
            continue
        if mem.hidden and mem.name.startswith("ZZZZ"):
            continue

        child_def = defs.get(mem.data_type)
        mem_vals = values.get(mem.name)

        if mem.dimension and mem.dimension > 0:
            # Scalar arrays only — structure arrays are unsupported
            if child_def and child_def.family == "StringFamily":
                raise UnsupportedStructuredDataError(
                    f"{dt_name}.{mem.name}: string-array Decorated not supported"
                )
            if child_def and not _is_scalar(mem.data_type, defs):
                raise UnsupportedStructuredDataError(
                    f"{dt_name}.{mem.name}: structure-array Decorated not supported "
                    f"(DataType={mem.data_type} Dimension={mem.dimension})"
                )
            if not _is_scalar(mem.data_type, defs) and (mem.data_type or "").upper() != "BOOL":
                if strict or (mem.data_type or "").upper() not in _SCALAR_TYPES:
                    raise UnsupportedStructuredDataError(
                        f"{dt_name}.{mem.name}: unsupported array element type {mem.data_type}"
                    )
            radix = mem.radix if mem.radix and mem.radix not in ("NullType", "") else "Decimal"
            parts.append(
                _emit_scalar_array_member(
                    mem.name,
                    mem.data_type,
                    mem.dimension,
                    radix=radix,
                    values=mem_vals if isinstance(mem_vals, (list, tuple)) else None,
                )
            )
            continue

        if child_def and child_def.family == "StringFamily":
            parts.append(
                _emit_string_udt(
                    mem.data_type,
                    mem.name,
                    str(mem_vals or "") if not isinstance(mem_vals, dict) else str(
                        mem_vals.get("DATA") or mem_vals.get("text") or ""
                    ),
                )
            )
            continue

        if (mem.data_type or "").upper() == "TIMER":
            parts.append(
                _emit_timer(mem.name, mem_vals if isinstance(mem_vals, dict) else None)
            )
            continue

        if child_def and not _is_scalar(mem.data_type, defs):
            nested_vals = mem_vals if isinstance(mem_vals, dict) else {}
            inner = emit_structure_members(
                mem.data_type,
                defs,
                values=nested_vals,
                depth=depth + 1,
                strict=strict,
            )
            parts.append(
                f'<StructureMember Name="{_xml_escape(mem.name)}" '
                f'DataType="{_xml_escape(mem.data_type)}">{inner}</StructureMember>'
            )
            continue

        if not _is_scalar(mem.data_type, defs) and not child_def:
            if strict:
                raise UnsupportedStructuredDataError(
                    f"{dt_name}.{mem.name}: nested DataType {mem.data_type} missing"
                )
            # Non-strict: skip unknown nested shell rather than invent members
            continue

        # Scalar
        radix = mem.radix if mem.radix and mem.radix not in ("NullType", "") else "Decimal"
        if (mem.data_type or "").upper() in ("REAL", "LREAL"):
            radix = "Float"
        if (mem.data_type or "").upper() == "BOOL":
            parts.append(
                f'<DataValueMember Name="{_xml_escape(mem.name)}" DataType="BOOL" '
                f'Value="{int(mem_vals or 0)}"/>'
            )
        else:
            val = mem_vals if mem_vals is not None else _default_scalar_value(mem.data_type)
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
    strict: bool = False,
) -> str:
    """Full <Structure DataType="…">…</Structure> with members expanded."""
    inner = emit_structure_members(dt_name, defs, values=values, strict=strict)
    if not inner:
        # Never emit empty Structure — caller should omit Data or use L5K-only
        return ""
    return f'<Structure DataType="{_xml_escape(dt_name)}">{inner}</Structure>'


def _string_l5k_empty(dim: int) -> str:
    """Rockwell L5K empty string: LEN=0 + $00 padding to DATA dimension."""
    pad = "$00" * max(0, int(dim))
    return f"[0,'{pad}']"


def emit_comm_udt_tag(name: str, defs: dict[str, DataTypeDef] | None = None) -> str:
    """Comm_UDT tag matched to Fortna library datatype (verbatim gold shape).

    Studio 'Data type mismatch' root causes observed on ORNCCP2:
      1. Extra L5K array wrap (`[[[...]]]` instead of gold `[[...]]`)
      2. Invalid empty-string L5K (`[0,'']`) — need $00-padded DATA to dimension
      3. Decorated empty string CDATA must be bare `<![CDATA[]]>` (not `['']`)

    L5K member order matches Comm_UDT in THIS L5X / library:
      CommLoss_Tmr(TIMER), Flt(Comm_Flt), Comm_Code, Firmware, MACId, IP_Address
    """
    # Prefer walking THIS L5X datatype when provided (matched pair).
    ddef = (defs or {}).get("Comm_UDT")
    if ddef is not None:
        expected = [m.name for m in ddef.members if not (m.hidden and m.name.startswith("ZZZZ"))]
        # Current Fortna Comm_UDT always includes CommLoss_Tmr; refuse silent drift.
        if expected and expected[0] != "CommLoss_Tmr":
            raise ValueError(
                f"Comm_UDT member order unexpected for emitter: {expected}"
            )
    mac = _string_l5k_empty(20)
    ip = _string_l5k_empty(15)
    # ONE outer structure array — matches library CP2N6_RIO / Studio exports.
    l5k = f"[[0,0,0],[0],0,0.00000000e+000,{mac},{ip}]"
    struct = (
        "<Structure DataType=\"Comm_UDT\">"
        "<StructureMember Name=\"CommLoss_Tmr\" DataType=\"TIMER\">"
        "<DataValueMember Name=\"PRE\" DataType=\"DINT\" Radix=\"Decimal\" Value=\"0\"/>"
        "<DataValueMember Name=\"ACC\" DataType=\"DINT\" Radix=\"Decimal\" Value=\"0\"/>"
        "<DataValueMember Name=\"EN\" DataType=\"BOOL\" Value=\"0\"/>"
        "<DataValueMember Name=\"TT\" DataType=\"BOOL\" Value=\"0\"/>"
        "<DataValueMember Name=\"DN\" DataType=\"BOOL\" Value=\"0\"/>"
        "</StructureMember>"
        "<StructureMember Name=\"Flt\" DataType=\"Comm_Flt\">"
        "<DataValueMember Name=\"CommLoss\" DataType=\"BOOL\" Value=\"0\"/>"
        "<DataValueMember Name=\"UpStrmCommLoss\" DataType=\"BOOL\" Value=\"0\"/>"
        "</StructureMember>"
        "<DataValueMember Name=\"Comm_Code\" DataType=\"DINT\" Radix=\"Decimal\" Value=\"0\"/>"
        "<DataValueMember Name=\"Firmware\" DataType=\"REAL\" Radix=\"Float\" Value=\"0.0\"/>"
        "<StructureMember Name=\"MACId\" DataType=\"String_20\">"
        "<DataValueMember Name=\"LEN\" DataType=\"DINT\" Radix=\"Decimal\" Value=\"0\"/>"
        "<DataValueMember Name=\"DATA\" DataType=\"String_20\" Radix=\"ASCII\">"
        "<![CDATA[]]>"
        "</DataValueMember>"
        "</StructureMember>"
        "<StructureMember Name=\"IP_Address\" DataType=\"String_15\">"
        "<DataValueMember Name=\"LEN\" DataType=\"DINT\" Radix=\"Decimal\" Value=\"0\"/>"
        "<DataValueMember Name=\"DATA\" DataType=\"String_15\" Radix=\"ASCII\">"
        "<![CDATA[]]>"
        "</DataValueMember>"
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
    defs: dict[str, DataTypeDef] | None = None,
    *,
    clear: int = 10000,
    no_cartons: int = 10000,
    release: int = 10000,
    release_full: int = 15000,
) -> str:
    """Merge_Time tag matched to datatype in current L5X (PLC5 P444_MergeTime shape).

    Member order must match DataType Merge_Time / Merge_Time_HMI exactly:
      HMI: FltClearTime, ReleaseTime, ReleaseTimeFull, ClearTime, NoCartonsTime,
           (hidden SINT packing Enable_CX/CX_TimeReset) → L5K 6th HMI element
      then ReleaseTime, ClearTime, NoCartonsTime
    """
    # Matched pair: L5K shape must equal Studio-exported Merge_Time (ONE outer []).
    # Extra wrap `[[[...]]]` is the Studio "Data type mismatch" failure mode.
    ddef = (defs or {}).get("Merge_Time")
    if ddef is not None:
        expected = [m.name for m in ddef.members if not (m.hidden and m.name.startswith("ZZZZ"))]
        if expected != ["HMI", "ReleaseTime", "ClearTime", "NoCartonsTime"]:
            raise ValueError(
                f"Merge_Time member order unexpected for emitter: {expected}"
            )
    # L5K: [ [HMI 6 elems], ReleaseTime, ClearTime, NoCartonsTime ]
    l5k = (
        f"[[0,{release},{release_full},{clear},{no_cartons},0],"
        f"{release},{clear},{no_cartons}]"
    )
    # Verbatim Decorated from PLC5 gold (Enable_CX/CX_TimeReset as BOOL)
    struct = (
        "<Structure DataType=\"Merge_Time\">"
        "<StructureMember Name=\"HMI\" DataType=\"Merge_Time_HMI\">"
        f"<DataValueMember Name=\"FltClearTime\" DataType=\"INT\" Radix=\"Decimal\" Value=\"0\"/>"
        f"<DataValueMember Name=\"ReleaseTime\" DataType=\"DINT\" Radix=\"Decimal\" Value=\"{release}\"/>"
        f"<DataValueMember Name=\"ReleaseTimeFull\" DataType=\"DINT\" Radix=\"Decimal\" Value=\"{release_full}\"/>"
        f"<DataValueMember Name=\"ClearTime\" DataType=\"INT\" Radix=\"Decimal\" Value=\"{clear}\"/>"
        f"<DataValueMember Name=\"NoCartonsTime\" DataType=\"INT\" Radix=\"Decimal\" Value=\"{no_cartons}\"/>"
        "<DataValueMember Name=\"Enable_CX\" DataType=\"BOOL\" Value=\"0\"/>"
        "<DataValueMember Name=\"CX_TimeReset\" DataType=\"BOOL\" Value=\"0\"/>"
        "</StructureMember>"
        f"<DataValueMember Name=\"ReleaseTime\" DataType=\"DINT\" Radix=\"Decimal\" Value=\"{release}\"/>"
        f"<DataValueMember Name=\"ClearTime\" DataType=\"INT\" Radix=\"Decimal\" Value=\"{clear}\"/>"
        f"<DataValueMember Name=\"NoCartonsTime\" DataType=\"INT\" Radix=\"Decimal\" Value=\"{no_cartons}\"/>"
        "</Structure>"
    )
    return (
        f'<Tag Name="{_xml_escape(name)}" TagType="Base" DataType="Merge_Time" '
        f'Constant="false" ExternalAccess="Read/Write">'
        f'<Data Format="L5K"><![CDATA[{l5k}]]></Data>'
        f'<Data Format="Decorated">{struct}</Data></Tag>'
    )


# Gold L5K zero-init for Merge_2to1 AOI instance (from PLC5 EDITED export).
# ONE outer [] — do not add an extra wrap.
_MERGE_2TO1_L5K = (
    "[1,0,0,0,0,0,0,0,0,0,0,0,0,"
    "[[0,0,0],[0,0,0],[0,0,0],0,0,0,0],"
    "[[0,0,0],[0,0,0],[0,0,0],0,0,0,0],"
    "[[0,0,0],[0,0,0],0,0,0,0,0],"
    "0,0,0,[0,0,0],[0,0,0],32000]"
)

_MERGE_2TO1_TEMPLATE = (
    Path(__file__).resolve().parent / "templates" / "merge_2to1_decorated_zero.xml"
)


def _load_merge_2to1_decorated() -> str:
    """Full AOI Decorated Structure from finished-cookie-cutter zero template.

    Partial scalar-only Decorated caused Studio:
      Format of data element value inside a structure element is invalid.
    """
    if _MERGE_2TO1_TEMPLATE.is_file():
        body = _MERGE_2TO1_TEMPLATE.read_text(encoding="utf-8").strip()
        if body.startswith("<Structure"):
            return body
        return f'<Structure DataType="Merge_2to1">{body}</Structure>'
    # Minimal fallback — still better than truncated member list
    return (
        '<Structure DataType="Merge_2to1">'
        '<DataValueMember Name="EnableIn" DataType="BOOL" Value="1"/>'
        '<DataValueMember Name="EnableOut" DataType="BOOL" Value="0"/>'
        "</Structure>"
    )


def emit_merge_2to1_tag(name: str) -> str:
    """Merge_2to1 AOI instance with gold L5K + complete Decorated Structure."""
    struct = _load_merge_2to1_decorated()
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
    if dt_name == "Comm_UDT" and "[0,'']" in xml_fragment:
        issues.append(f"{dt_name}: empty string L5K [0,''] is invalid — need $00-padded DATA")
    if "<![CDATA['']]>" in xml_fragment:
        issues.append(f"{dt_name}: Decorated empty string must be bare CDATA, not ['']")
    return issues


def _parse_cdata_string(raw: str) -> str:
    """Decode Decorated string DATA CDATA payload (`'text'` or bare empty)."""
    s = (raw or "").strip()
    if s.startswith("'") and s.endswith("'") and len(s) >= 2:
        return s[1:-1]
    return s


def extract_decorated_values(structure_xml: str) -> dict[str, Any]:
    """Parse a Decorated Structure (or its inner body) into a nested values dict.

    Used to preserve existing tag values when rewriting Decorated from datatype.
    """
    body = structure_xml or ""
    m = re.search(r"<Structure\b[^>]*>(.*)</Structure>\s*$", body, re.S)
    if m:
        body = m.group(1)
    out: dict[str, Any] = {}
    i = 0
    while i < len(body):
        am = re.match(
            r'<ArrayMember\s+Name="([^"]+)"\s+DataType="([^"]+)"([^>]*)>',
            body[i:],
        )
        if am:
            name = am.group(1)
            start = i + am.end()
            end = body.find("</ArrayMember>", start)
            if end < 0:
                break
            inner = body[start:end]
            elems = re.findall(r'<Element\s+Index="\[\d+\]"\s+Value="([^"]*)"', inner)
            out[name] = elems
            i = end + len("</ArrayMember>")
            continue

        sm = re.match(
            r'<StructureMember\s+Name="([^"]+)"\s+DataType="([^"]+)"([^>]*)(/?)>',
            body[i:],
        )
        if sm:
            name, dtype, _rest, self_close = (
                sm.group(1),
                sm.group(2),
                sm.group(3),
                sm.group(4),
            )
            if self_close == "/":
                out[name] = {}
                i += sm.end()
                continue
            start = i + sm.end()
            # Find matching close at depth 0 for this StructureMember
            depth = 1
            j = start
            while j < len(body) and depth > 0:
                if body.startswith("</StructureMember>", j):
                    depth -= 1
                    if depth == 0:
                        break
                    j += len("</StructureMember>")
                    continue
                open_m = re.match(r"<StructureMember\b[^>]*(/?)>", body[j:])
                if open_m:
                    if open_m.group(1) != "/":
                        depth += 1
                    j += open_m.end()
                    continue
                j += 1
            inner = body[start:j]
            # String UDTs: direct LEN + DATA only (no nested Structure/Array members).
            # Do not treat parent UDTs that embed a string member as strings themselves.
            if "<StructureMember" not in inner and "<ArrayMember" not in inner:
                cdata = re.search(
                    r'<DataValueMember\s+Name="DATA"[^>]*>\s*<!\[CDATA\[(.*?)\]\]>',
                    inner,
                    re.S,
                )
                if cdata and re.search(r'Name="LEN"', inner):
                    out[name] = _parse_cdata_string(cdata.group(1))
                    i = j + len("</StructureMember>")
                    continue
            out[name] = extract_decorated_values(inner)
            i = j + len("</StructureMember>")
            continue

        dv = re.match(
            r'<DataValueMember\s+Name="([^"]+)"\s+DataType="([^"]+)"([^>]*)(/?)>',
            body[i:],
        )
        if dv:
            name, dtype, rest, self_close = (
                dv.group(1),
                dv.group(2),
                dv.group(3),
                dv.group(4),
            )
            if "Radix=\"ASCII\"" in rest or name == "DATA":
                if self_close == "/":
                    out[name] = ""
                    i += dv.end()
                    continue
                start = i + dv.end()
                end = body.find("</DataValueMember>", start)
                chunk = body[start:end] if end >= 0 else ""
                cm = re.search(r"<!\[CDATA\[(.*?)\]\]>", chunk, re.S)
                out[name] = _parse_cdata_string(cm.group(1) if cm else "")
                i = (end + len("</DataValueMember>")) if end >= 0 else i + dv.end()
                continue
            vm = re.search(r'Value="([^"]*)"', rest)
            raw = vm.group(1) if vm else "0"
            if (dtype or "").upper() in ("BOOL", "BIT"):
                out[name] = int(raw or 0)
            elif (dtype or "").upper() in ("REAL", "LREAL"):
                try:
                    out[name] = float(raw)
                except ValueError:
                    out[name] = raw
            else:
                try:
                    out[name] = int(raw)
                except ValueError:
                    out[name] = raw
            i += dv.end()
            if self_close != "/":
                end = body.find("</DataValueMember>", i)
                if end >= 0:
                    i = end + len("</DataValueMember>")
            continue
        i += 1
    return out


def rewrite_tag_decorated_from_datatype(
    tag_xml: str,
    defs: dict[str, DataTypeDef],
    *,
    dt_name: str | None = None,
    strip_l5k: bool = False,
) -> str:
    """Rewrite one Tag's Decorated Structure from its DataType definition.

    Preserves scalar/nested values from existing Decorated when present; otherwise
    zeros. Raises UnsupportedStructuredDataError when the datatype cannot be
    emitted safely (missing def / unsupported array shape).
    """
    tag = tag_xml or ""
    if not dt_name:
        dm = re.search(r'\bDataType="([^"]+)"', tag)
        if not dm:
            raise UnsupportedStructuredDataError("tag has no DataType attribute")
        dt_name = dm.group(1)
    if dt_name not in defs:
        raise UnsupportedStructuredDataError(
            f"{dt_name}: datatype definition missing — refuse to invent member order"
        )

    deco_m = re.search(r'<Data Format="Decorated">(.*?)</Data>', tag, re.S)
    values: dict[str, Any] = {}
    if deco_m:
        values = extract_decorated_values(deco_m.group(1))

    struct = emit_decorated_structure(dt_name, defs, values=values, strict=True)
    if not struct:
        raise UnsupportedStructuredDataError(
            f"{dt_name}: emit produced empty Structure"
        )

    # Validate before export
    issues = validate_tag_matches_datatype(
        f'<Tag Name="_" DataType="{dt_name}">'
        f'<Data Format="Decorated">{struct}</Data></Tag>',
        defs,
        dt_name=dt_name,
        require_l5k=False,
    )
    # Filter string-form issues already covered
    hard = [x for x in issues if "member names" in x or "DataType" in x and "!=" in x]
    if hard:
        raise UnsupportedStructuredDataError(
            f"{dt_name}: rewritten Decorated failed validation: {hard}"
        )
    shell = validate_decorated_structure(struct, dt_name)
    if shell:
        raise UnsupportedStructuredDataError(
            f"{dt_name}: rewritten Decorated invalid: {shell}"
        )

    new_deco = f'<Data Format="Decorated">{struct}</Data>'
    if deco_m:
        tag = tag[: deco_m.start()] + new_deco + tag[deco_m.end() :]
    else:
        # Insert Decorated before </Tag>
        tag = re.sub(r"</Tag>\s*$", new_deco + "</Tag>", tag, count=1)

    if strip_l5k and 'Format="L5K"' in tag:
        tag = re.sub(r'<Data Format="L5K">.*?</Data>\s*', "", tag, count=1, flags=re.S)
    return tag


def rewrite_l5x_structured_decorated(
    l5x: str,
    defs: dict[str, DataTypeDef] | None = None,
    *,
    types: frozenset[str] | set[str] | None = None,
    strip_l5k: bool = True,
) -> str:
    """Rewrite Decorated for structured tags (Track_Divert_UDT / Area_UDT by default).

    Parses DataTypes from ``l5x`` when ``defs`` is omitted. Unsupported tags are
    left unchanged only when their DataType is not in ``types``; tags of a
    requested type with missing datatype raise.
    """
    text = l5x or ""
    target = frozenset(types) if types is not None else DEFAULT_REWRITE_STRUCTURED_TYPES
    if not target:
        return text
    parsed = defs if defs is not None else parse_datatypes(text)
    type_alt = "|".join(re.escape(t) for t in sorted(target))

    def _rew(m: re.Match) -> str:
        tag = m.group(0)
        dm = re.search(r'\bDataType="([^"]+)"', tag)
        dt = dm.group(1) if dm else ""
        if dt not in target:
            return tag
        try:
            return rewrite_tag_decorated_from_datatype(
                tag, parsed, dt_name=dt, strip_l5k=strip_l5k
            )
        except UnsupportedStructuredDataError:
            # Reject inventing order — leave tag for secondary sanitizers / validators.
            return tag

    return re.sub(
        rf'<Tag\b[^>]*\bDataType="(?:{type_alt})"[^>]*>.*?</Tag>',
        _rew,
        text,
        flags=re.S,
    )


def _top_level_decorated_members(structure_inner_xml: str) -> list[tuple[str, str]]:
    """Parse direct children of a Structure body into (name, dataType) list."""
    body = structure_inner_xml or ""
    found: list[tuple[str, str]] = []
    i = 0
    sm_depth = 0
    while i < len(body):
        if body.startswith("</StructureMember>", i):
            sm_depth = max(0, sm_depth - 1)
            i += len("</StructureMember>")
            continue
        if body.startswith("</ArrayMember>", i):
            i += len("</ArrayMember>")
            continue
        m = re.match(
            r"<(StructureMember|DataValueMember|ArrayMember)\s+Name=\"([^\"]+)\"\s+DataType=\"([^\"]+)\"([^>]*)(/?)>",
            body[i:],
        )
        if not m:
            i += 1
            continue
        kind, nm, dtype, _rest, self_close = (
            m.group(1),
            m.group(2),
            m.group(3),
            m.group(4),
            m.group(5),
        )
        if sm_depth == 0:
            found.append((nm, dtype))
        if kind == "StructureMember" and self_close != "/":
            sm_depth += 1
        if kind == "ArrayMember" and self_close != "/":
            # Skip array body without affecting StructureMember depth
            end = body.find("</ArrayMember>", i + m.end())
            if end >= 0:
                i = end + len("</ArrayMember>")
                continue
        i += m.end()
    return found


def validate_tag_matches_datatype(
    tag_xml: str,
    defs: dict[str, DataTypeDef],
    *,
    dt_name: str,
    require_l5k: bool | None = None,
) -> list[str]:
    """Member-by-member: Decorated top-level members must match DataType definition order.

    Skips hidden ZZZZ packing SINTs (represented as BOOL bit members in Decorated).
    For Track_Divert_UDT / Area_UDT, L5K is optional when Decorated alone is valid
    (``require_l5k`` defaults False for those types).
    """
    issues: list[str] = []
    ddef = defs.get(dt_name)
    if not ddef:
        issues.append(f"{dt_name}: datatype definition missing from L5X")
        return issues
    root = re.search(
        rf'<Structure DataType="{re.escape(dt_name)}">(.*)</Structure>\s*</Data>',
        tag_xml or "",
        re.S,
    )
    if not root:
        # Also accept bare Structure without trailing </Data>
        root = re.search(
            rf'<Structure DataType="{re.escape(dt_name)}">(.*)</Structure>',
            tag_xml or "",
            re.S,
        )
    if not root:
        issues.append(f"{dt_name}: no Decorated Structure root")
        return issues
    found = _top_level_decorated_members(root.group(1))
    expected: list[tuple[str, str]] = []
    for mem in ddef.members:
        if mem.hidden and mem.name.startswith("ZZZZ"):
            continue
        if mem.data_type.upper() == "BIT":
            expected.append((mem.name, "BOOL"))
        else:
            expected.append((mem.name, mem.data_type))

    if [x[0] for x in found] != [x[0] for x in expected]:
        issues.append(
            f"{dt_name}: Decorated member names {[x[0] for x in found]} "
            f"!= datatype {[x[0] for x in expected]}"
        )
    else:
        for (fn, ft), (_en, et) in zip(found, expected):
            if ft != et:
                issues.append(f"{dt_name}.{fn}: Decorated DataType {ft} != datatype {et}")

    if require_l5k is None:
        require_l5k = dt_name not in DEFAULT_REWRITE_STRUCTURED_TYPES
    if require_l5k and 'Format="L5K"' not in (tag_xml or ""):
        issues.append(f"{dt_name}: missing L5K Data (gold Fortna tags include L5K+Decorated)")
    if "[0,'']" in (tag_xml or ""):
        issues.append(f"{dt_name}: L5K contains invalid empty string [0,'']")
    if "<![CDATA['']]>" in (tag_xml or ""):
        issues.append(f"{dt_name}: Decorated empty string must be bare CDATA, not ['']")

    # L5K must use ONE outer structure array (Studio rejects extra wrap).
    l5k_m = re.search(r'Format="L5K"\s*>\s*<!\[CDATA\[(.*?)\]\]>', tag_xml or "", re.S)
    if l5k_m:
        l5k = (l5k_m.group(1) or "").strip()
        if dt_name in ("Merge_Time", "Comm_UDT") and l5k.startswith("[[["):
            issues.append(
                f"{dt_name}: L5K has extra array wrap [[[...]]] — Studio gold is [[...]]"
            )
        if l5k.count("[") != l5k.count("]"):
            issues.append(f"{dt_name}: L5K bracket imbalance")
    return issues

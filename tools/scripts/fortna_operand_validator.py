#!/usr/bin/env python3
"""Deterministic PLC operand / member-path validator (Gate I).

Catches Studio 5000 "Invalid member specifier" BEFORE export.

Resolves FULL operand paths:
  Tag.Member
  Tag.I.Member
  Tag.O.Member
  NestedUDT.Member.SubMember
  Module:I.Data[5].14   (best-effort against emitted Module structure)

Does NOT guess replacement members. Does NOT silently rewrite.
"""
from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree as ET

_BUILTIN = {
    "BOOL", "SINT", "INT", "DINT", "LINT", "USINT", "UINT", "UDINT", "ULINT",
    "REAL", "LREAL", "STRING", "TIMER", "COUNTER", "CONTROL", "MESSAGE",
    "BIT", "CONNECTION_STATUS", "ALARM_ANALOG", "ALARM_DIGITAL",
}

# Valid Logix structured builtins — members are real; do NOT reject as atomic.
_STRUCTURED_BUILTIN_MEMBERS: dict[str, dict[str, str]] = {
    "TIMER": {"PRE": "DINT", "ACC": "DINT", "EN": "BOOL", "TT": "BOOL", "DN": "BOOL"},
    "COUNTER": {"PRE": "DINT", "ACC": "DINT", "CU": "BOOL", "CD": "BOOL", "DN": "BOOL", "OV": "BOOL", "UN": "BOOL"},
    "CONTROL": {"LEN": "DINT", "POS": "DINT", "EN": "BOOL", "EU": "BOOL", "DN": "BOOL", "EM": "BOOL", "ER": "BOOL", "UL": "BOOL", "IN": "BOOL", "FD": "BOOL"},
}

_INSTR = ("XIC", "XIO", "OTE", "OTL", "OTU")


def _parse_datatypes(root: ET.Element) -> dict[str, dict[str, str]]:
    """DataType name → {memberName: memberType}."""
    out: dict[str, dict[str, str]] = {}
    for dt in root.iter("DataType"):
        name = dt.attrib.get("Name") or ""
        if not name:
            continue
        members: dict[str, str] = {}
        for m in dt.iter("Member"):
            mn = m.attrib.get("Name") or ""
            mt = m.attrib.get("DataType") or ""
            if mn:
                members[mn] = mt
        out[name] = members
    return out


def _parse_tags(root: ET.Element) -> dict[str, str]:
    """Tag name → DataType (controller + program scoped flattened by Name)."""
    tags: dict[str, str] = {}
    for tag in root.iter("Tag"):
        n = tag.attrib.get("Name") or ""
        dt = tag.attrib.get("DataType") or ""
        if n:
            tags[n] = dt
    return tags


def _split_operand(operand: str) -> tuple[str, list[str], list[str]]:
    """Return (base, member_segments, array_index_tokens)."""
    op = (operand or "").strip()
    # Module path: CP2RIO0:I.Data[5].1
    if ":" in op and not op.startswith("["):
        # Treat whole module:channel as base for now; members after first '.'
        # e.g. CP2RIO0:I.Data[5].1 → base=CP2RIO0:I, segs=[Data, 5?, 1?] — special-cased later
        return op, [], []
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)(.*)$", op)
    if not m:
        return op, [], []
    base = m.group(1)
    rest = m.group(2) or ""
    segs: list[str] = []
    for part in re.findall(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]", rest):
        if part[0]:
            segs.append(part[0])
        elif part[1]:
            segs.append(f"[{part[1]}]")
    return base, segs, []


def _members_for_type(
    type_name: str,
    datatypes: dict[str, dict[str, str]],
) -> dict[str, str] | None:
    """Return member map for UDT or structured builtin; None if unknown/sealed."""
    if type_name in _STRUCTURED_BUILTIN_MEMBERS:
        return _STRUCTURED_BUILTIN_MEMBERS[type_name]
    if type_name in datatypes:
        return datatypes[type_name]
    return None


def _resolve_members(
    base_type: str,
    segs: list[str],
    datatypes: dict[str, dict[str, str]],
    *,
    aoi_names: set[str] | None = None,
) -> dict[str, Any]:
    cur = base_type
    path_ok: list[str] = []
    for seg in segs:
        if seg.startswith("[") and seg.endswith("]"):
            # Array index — accept if current type looks like array or STRUCT walk continues
            path_ok.append(seg)
            continue
        # Atomic builtins (BOOL/DINT/…) cannot have members
        if cur in _BUILTIN and cur not in _STRUCTURED_BUILTIN_MEMBERS:
            return {
                "ok": False,
                "kind": "MEMBER_NOT_FOUND",
                "failed_segment": seg,
                "resolved_type": cur,
                "path_ok": path_ok,
            }
        members = _members_for_type(cur, datatypes)
        if members is None:
            # Sealed AOI / external type — cannot expand EncodedData; accept path
            if aoi_names and cur in aoi_names:
                return {
                    "ok": True,
                    "kind": "UNKNOWN_EXTERNAL_DEFINITION",
                    "resolved_type": cur,
                    "path_ok": path_ok + [seg],
                    "external": True,
                    "note": f"Sealed AOI type {cur} members not expandable",
                }
            # Unknown nested type (often sealed AOI host used as UDT member type)
            return {
                "ok": True,
                "kind": "UNKNOWN_EXTERNAL_DEFINITION",
                "resolved_type": cur,
                "path_ok": path_ok + [seg],
                "external": True,
                "note": f"DataType {cur} not expandable — treating nested path as external",
            }
        if seg not in members:
            return {
                "ok": False,
                "kind": "MEMBER_NOT_FOUND",
                "failed_segment": seg,
                "resolved_type": cur,
                "path_ok": path_ok,
                "available_members": sorted(members.keys())[:40],
            }
        path_ok.append(seg)
        cur = members[seg]
    return {"ok": True, "resolved_type": cur, "path_ok": path_ok}


def validate_operand(
    operand: str,
    *,
    tags: dict[str, str],
    datatypes: dict[str, dict[str, str]],
    module_names: set[str] | None = None,
    aoi_names: set[str] | None = None,
) -> dict[str, Any]:
    op = (operand or "").strip()
    if not op:
        return {"ok": False, "kind": "TAG_NOT_FOUND", "operand": op}

    # Rockwell controller status / system operands (S:FS, S:V, …)
    if re.match(r"^[SG]:", op, re.I):
        return {
            "ok": True,
            "kind": "SYSTEM_OPERAND_OK",
            "operand": op,
            "base_tag": op.split(":", 1)[0],
            "external": True,
        }

    # Module-defined: CPxRIOn:I.Data[s].b or Scanner:I.ConnectionFaulted
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*:", op):
        mod = op.split(":", 1)[0]
        if module_names is not None and mod not in module_names:
            # Still accept as external module-binding — Studio needs the Module
            # element, but path shape is valid Logix. Report as external, not
            # invalid_member (rough-build readiness; MODULE_BINDING_REQUIRED).
            return {
                "ok": True,
                "kind": "MODULE_BINDING_REQUIRED",
                "operand": op,
                "base_tag": mod,
                "external": True,
                "note": f"Module {mod} not in emitted Modules — engineer/hardware binding",
            }
        # Structure of AB modules is external — mark external when we cannot deep-validate
        if re.search(r":[IO]\.Data\[\d+\]\.\d+$", op):
            return {
                "ok": True,
                "kind": "MODULE_CHANNEL_OK",
                "operand": op,
                "base_tag": mod,
                "external": True,
            }
        return {
            "ok": True,
            "kind": "UNKNOWN_EXTERNAL_DEFINITION",
            "operand": op,
            "base_tag": mod,
            "external": True,
            "note": "Module/channel path accepted best-effort",
        }

    base, segs, _ = _split_operand(op)
    if base not in tags:
        return {
            "ok": False,
            "kind": "TAG_NOT_FOUND",
            "operand": op,
            "base_tag": base,
            "failed_segment": base,
        }
    if not segs:
        return {"ok": True, "kind": "TAG_OK", "operand": op, "base_tag": base, "datatype": tags[base]}

    dt = tags[base]
    # Structured builtins (TIMER/COUNTER/CONTROL) have real members — resolve them.
    # Plain atomics (BOOL/DINT/…) must NEVER have members.
    if dt in _BUILTIN and dt not in _STRUCTURED_BUILTIN_MEMBERS and segs:
        return {
            "ok": False,
            "kind": "MEMBER_NOT_FOUND",
            "operand": op,
            "base_tag": base,
            "datatype": dt,
            "failed_segment": segs[0],
            "failed_member_segment": segs[0],
            "note": f"Atomic type {dt} cannot have members",
        }
    if aoi_names and dt in aoi_names and dt not in datatypes:
        return {
            "ok": True,
            "kind": "UNKNOWN_EXTERNAL_DEFINITION",
            "operand": op,
            "base_tag": base,
            "datatype": dt,
            "external": True,
            "note": "Sealed AOI members not expandable from L5X EncodedData",
        }
    result = _resolve_members(dt, segs, datatypes, aoi_names=aoi_names)
    result["operand"] = op
    result["base_tag"] = base
    result["datatype"] = dt
    if result.get("external"):
        return result
    if not result.get("ok"):
        if len(result.get("path_ok") or []) > 0:
            result["kind"] = "NESTED_MEMBER_NOT_FOUND"
        result["failed_member_segment"] = result.get("failed_segment")
        # DataType missing entirely (common for sealed AOI host types) → external
        if dt and dt not in datatypes and dt not in _BUILTIN and dt not in _STRUCTURED_BUILTIN_MEMBERS:
            return {
                "ok": True,
                "kind": "UNKNOWN_EXTERNAL_DEFINITION",
                "operand": op,
                "base_tag": base,
                "datatype": dt,
                "external": True,
                "note": f"DataType {dt} not present as expandable UDT",
            }
    return result


def extract_instruction_operands(l5x_text: str) -> list[dict[str, Any]]:
    """Walk Program/Routine/Rung CDATA for XIC/XIO/OTE/OTL/OTU operands."""
    root = ET.fromstring(l5x_text)
    findings: list[dict[str, Any]] = []
    for prog in root.iter("Program"):
        pname = prog.attrib.get("Name") or ""
        for routine in prog.iter("Routine"):
            rname = routine.attrib.get("Name") or ""
            for rung in routine.iter("Rung"):
                rnum = rung.attrib.get("Number") or ""
                text_el = None
                for child in rung:
                    if child.tag.endswith("Text") or child.tag == "Text":
                        text_el = child
                        break
                raw = (text_el.text or "") if text_el is not None else ""
                # Also handle CDATA already expanded by ET
                for instr in _INSTR:
                    for m in re.finditer(rf"\b{instr}\s*\(\s*([^)]+?)\s*\)", raw, re.I):
                        findings.append(
                            {
                                "program": pname,
                                "routine": rname,
                                "rung": rnum,
                                "instruction": instr.upper(),
                                "operand": m.group(1).strip(),
                            }
                        )
    return findings


def validate_l5x_operands(l5x_text: str) -> dict[str, Any]:
    root = ET.fromstring(l5x_text)
    tags = _parse_tags(root)
    datatypes = _parse_datatypes(root)
    module_names = {m.attrib.get("Name") or "" for m in root.iter("Module") if m.attrib.get("Name")}
    aoi_names = set(
        re.findall(
            r'(?:EncodedData EncodedType="AddOnInstructionDefinition"|AddOnInstructionDefinition)'
            r'[^>]*Name="([^"]+)"',
            l5x_text,
        )
    )
    ops = extract_instruction_operands(l5x_text)
    invalid: list[dict[str, Any]] = []
    external: list[dict[str, Any]] = []
    checked = 0
    for item in ops:
        checked += 1
        res = validate_operand(
            item["operand"],
            tags=tags,
            datatypes=datatypes,
            module_names=module_names,
            aoi_names=aoi_names,
        )
        row = {**item, **res}
        if res.get("external") and res.get("ok"):
            external.append(row)
        if not res.get("ok"):
            invalid.append(row)
    return {
        "operands_checked": checked,
        "invalid_count": len(invalid),
        "invalid": invalid[:80],
        "external_count": len(external),
        "external": external[:40],
        "ok": len(invalid) == 0,
    }

#!/usr/bin/env python3
"""Pre-Studio structural validators for generated L5X (Gate 1).

Catches Rockwell import classes locally:
  - RLL routines with raw <Rung> outside <RLLContent>
  - ST routines with <STLines> instead of <STContent>
  - Decorated Structure member names/order vs DataType definition
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fortna_l5x_structured_data import (
    parse_datatypes,
    rewrite_l5x_structured_decorated,
)


def validate_routine_language_containers(l5x: str) -> list[dict[str, Any]]:
    errs: list[dict[str, Any]] = []
    for m in re.finditer(r'<Routine\b([^>]*)>(.*?)</Routine>', l5x or "", re.S):
        attrs, body = m.group(1), m.group(2)
        nm = re.search(r'Name="([^"]+)"', attrs)
        ty = re.search(r'Type="([^"]+)"', attrs)
        name = nm.group(1) if nm else "?"
        rtype = (ty.group(1) if ty else "").upper()
        if rtype == "RLL":
            if re.search(r"<Rung\b", body) and "<RLLContent>" not in body:
                errs.append(
                    {
                        "kind": "RLL_RUNG_OUTSIDE_RLLCONTENT",
                        "routine": name,
                        "detail": "Rung elements must be inside RLLContent",
                    }
                )
        elif rtype == "ST":
            if "<STLines>" in body:
                errs.append(
                    {
                        "kind": "ST_STLINES_NOT_STCONTENT",
                        "routine": name,
                        "detail": "ST routines must use STContent, not STLines",
                    }
                )
            if re.search(r"<Line\b", body) and "<STContent>" not in body and "<STLines>" not in body:
                errs.append(
                    {
                        "kind": "ST_LINE_OUTSIDE_STCONTENT",
                        "routine": name,
                        "detail": "ST Line elements must be inside STContent",
                    }
                )
            # Studio: Unexpected element 'Text' will be ignored — CDATA must be
            # direct child of <Line>, not nested <Text><![CDATA[]]></Text>.
            if re.search(r"<Line\b[^>]*>\s*<Text\b", body):
                errs.append(
                    {
                        "kind": "ST_LINE_NESTED_TEXT",
                        "routine": name,
                        "detail": (
                            "ST Line must be <Line Number=\"N\"><![CDATA[...]]></Line> "
                            "without nested <Text>"
                        ),
                    }
                )
    return errs


def _top_level_decorated_members(structure_xml: str) -> list[str]:
    """Names of first-level DataValueMember/StructureMember under a Structure."""
    # Strip outer Structure wrapper if present
    body = structure_xml
    m = re.search(r"<Structure\b[^>]*>(.*)</Structure>\s*$", structure_xml, re.S)
    if m:
        body = m.group(1)
    top: list[str] = []
    depth = 0
    for mm in re.finditer(r"</?(?:StructureMember|DataValueMember|Structure)\b[^>]*>", body):
        tag = mm.group(0)
        opening = not tag.startswith("</")
        is_sm = "StructureMember" in tag or tag.startswith("<Structure ")
        is_dv = "DataValueMember" in tag
        if opening and (is_sm or is_dv) and depth == 0:
            nm = re.search(r'Name="([^"]+)"', tag)
            if nm:
                top.append(nm.group(1))
        if opening and is_sm and not tag.endswith("/>"):
            depth += 1
        elif tag.startswith("</StructureMember") or (
            tag.startswith("</Structure>") and depth > 0
        ):
            depth = max(0, depth - 1)
    return top


def validate_decorated_against_datatypes(l5x: str) -> list[dict[str, Any]]:
    """Compare Decorated Structure top-level member order to DataType when present."""
    defs = parse_datatypes(l5x)
    errs: list[dict[str, Any]] = []
    for m in re.finditer(
        r'<Tag Name="([^"]+)"[^>]*DataType="([^"]+)"[^>]*>.*?'
        r'<Data Format="Decorated">(.*?)</Data>',
        l5x or "",
        re.S,
    ):
        tag, dt, deco = m.group(1), m.group(2), m.group(3)
        ddef = defs.get(dt)
        if not ddef:
            # AOI-backed types often lack DataType block — skip hard fail
            continue
        expected = [
            mem.name
            for mem in ddef.members
            if not (mem.hidden and mem.name.startswith("ZZZZ"))
        ]
        # BIT members appear as BOOL DataValueMembers — still named
        # Only validate the Structure whose DataType matches the tag DataType
        sm = re.search(
            rf'<Structure DataType="{re.escape(dt)}">(.*)</Structure>\s*$',
            deco.strip(),
            re.S,
        )
        if not sm:
            continue
        got = _top_level_decorated_members(sm.group(0))
        if not got:
            continue
        # Track_Divert_UDT / Area_UDT: exact member list must match datatype order.
        if dt in ("Track_Divert_UDT", "Area_UDT"):
            if got != expected:
                errs.append(
                    {
                        "kind": "DECORATED_MEMBER_ORDER_OR_NAME",
                        "tag": tag,
                        "datatype": dt,
                        "member": next(
                            (g for g in got if g not in expected),
                            (expected[len(got)] if len(got) < len(expected) else "?"),
                        ),
                        "expected_order": expected,
                        "got": got,
                    }
                )
            continue
        # Other UDTs: prefix match — emitted must follow datatype order for names present
        exp_i = 0
        for g in got:
            while exp_i < len(expected) and expected[exp_i] != g:
                exp_i += 1
            if exp_i >= len(expected):
                errs.append(
                    {
                        "kind": "DECORATED_MEMBER_ORDER_OR_NAME",
                        "tag": tag,
                        "datatype": dt,
                        "member": g,
                        "expected_order": expected,
                        "got": got,
                    }
                )
                break
            exp_i += 1
    return errs


def validate_l5x_studio_structure(l5x: str) -> dict[str, Any]:
    routine_errs = validate_routine_language_containers(l5x)
    deco_errs = validate_decorated_against_datatypes(l5x)
    return {
        "ok": not routine_errs and not deco_errs,
        "routine_language_errors": routine_errs,
        "decorated_member_errors": deco_errs,
        "counts": {
            "routine_language_errors": len(routine_errs),
            "decorated_member_errors": len(deco_errs),
        },
    }


def sanitize_l5x_studio_structure(l5x: str) -> str:
    """Apply generic Studio-structure repairs before write/export.

    - Wrap bare RLL Rungs in RLLContent (Wave_Divert class)
    - STLines → STContent for Type=ST routines
    - ST Line nested <Text> → direct CDATA on <Line>
    - Primary: rewrite Track_Divert_UDT / Area_UDT / Comm_UDT /
      Barcode_Scanner_UDT Decorated from DataType (string DATA → SINT+Dimensions)
    - Secondary: drop L5K on Track/Area when Decorated present (L5K revision drift)
    """
    text = l5x or ""

    def _wrap_rll(m: re.Match) -> str:
        head, body, tail = m.group(1), m.group(2), m.group(3)
        if re.search(r"<Rung\b", body) and "<RLLContent>" not in body:
            body = f"<RLLContent>{body}</RLLContent>"
        return head + body + tail

    text = re.sub(
        r'(<Routine\b[^>]*Type="RLL"[^>]*>)(.*?)(</Routine>)',
        _wrap_rll,
        text,
        flags=re.S,
    )
    text = re.sub(
        r'(<Routine\b[^>]*Type="ST"[^>]*>)\s*<STLines>(.*?)</STLines>(\s*</Routine>)',
        r"\1<STContent>\2</STContent>\3",
        text,
        flags=re.S,
    )
    # <Line>...<Text><![CDATA[...]]></Text></Line> → <Line>...<![CDATA[...]]></Line>
    text = re.sub(
        r"(<Line\b[^>]*>)\s*<Text\b[^>]*>\s*<!\[CDATA\[(.*?)\]\]>\s*</Text>\s*(</Line>)",
        r"\1<![CDATA[\2]]>\3",
        text,
        flags=re.S,
    )

    # Primary fix: datatype-driven Decorated rewrite (values preserved when present).
    # Rewrites Track_Divert_UDT / Area_UDT / Comm_UDT / Barcode_Scanner_UDT.
    # strip_l5k applies only to Track/Area inside rewrite; Comm keeps L5K.
    text = rewrite_l5x_structured_decorated(text, strip_l5k=True)

    def _strip_l5k(m: re.Match) -> str:
        tag = m.group(0)
        if 'Format="Decorated"' in tag and 'Format="L5K"' in tag:
            tag = re.sub(r'<Data Format="L5K">.*?</Data>\s*', "", tag, count=1, flags=re.S)
        return tag

    # Secondary mitigation only — Decorated must already be valid alone.
    text = re.sub(
        r'<Tag Name="[^"]+"[^>]*DataType="(?:Track_Divert_UDT|Area_UDT)"[^>]*>.*?</Tag>',
        _strip_l5k,
        text,
        flags=re.S,
    )
    return text


def write_validation_report(l5x_path: Path, out_dir: Path) -> dict[str, Any]:
    text = Path(l5x_path).read_text(encoding="utf-8", errors="ignore")
    # strip junk before xml
    i = text.find("<?xml")
    if i > 0:
        text = text[i:]
    report = validate_l5x_studio_structure(text)
    report["l5x"] = str(l5x_path)
    report["l5x_bytes"] = Path(l5x_path).stat().st_size
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jp = out_dir / "orindyac6_l5x_validation.json"
    jp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = [
        "# ORINDYAC6 L5X structural validation",
        "",
        f"- L5X: `{l5x_path}`",
        f"- ok: **{report['ok']}**",
        f"- routine language errors: {report['counts']['routine_language_errors']}",
        f"- decorated member errors: {report['counts']['decorated_member_errors']}",
        "",
    ]
    if report["routine_language_errors"]:
        md.append("## Routine language")
        for e in report["routine_language_errors"]:
            md.append(f"- `{e['routine']}`: {e['kind']} — {e['detail']}")
    if report["decorated_member_errors"]:
        md.append("## Decorated vs DataType")
        for e in report["decorated_member_errors"][:40]:
            md.append(f"- `{e['tag']}` ({e['datatype']}): {e['kind']} member `{e.get('member')}`")
    (out_dir / "orindyac6_l5x_validation.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--l5x", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("exports/stabilization"))
    args = ap.parse_args()
    r = write_validation_report(args.l5x, args.out)
    print(json.dumps(r["counts"], indent=2))
    print("ok", r["ok"])

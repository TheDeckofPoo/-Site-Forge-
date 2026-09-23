#!/usr/bin/env python3
"""Diagnostics-only finished-L5X IO_MAP oracle parser.

Parses IO_MAP routines CP_I / CP_O into physical endpoint → tag → member
mappings with Tag DataType lookup. Finished PLC is validation authority only.

NEVER import this module from fortna_autogen / fortna_equipment_binding
(or any other production generation path).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ORACLE = ROOT / "workspace" / "validation" / "ORLY_GreensboroPLC2_NC_Finished.L5X"

CHANNEL_RE = re.compile(
    r"(?P<adapter>[A-Za-z0-9_]+):(?P<dir>[IO])\.Data\[(?P<slot>\d+)\]\.(?P<bit>\d+)"
)
OTE_RE = re.compile(r"OTE\(([^)]+)\)")
PLACEHOLDER_RE = re.compile(r"NO_PointPlaceholder", re.I)
TAG_ATTR_RE = re.compile(r"<Tag\b([^>]*)/?>", re.I)

__all__ = [
    "CHANNEL_RE",
    "DEFAULT_ORACLE",
    "build_oracle_io_map",
    "parse_io_map_routines",
    "parse_l5x_tag_datatypes",
    "split_device_member",
]


def _clean(v: Any) -> str:
    return str(v or "").strip()


def split_device_member(logical: str) -> tuple[str, str]:
    """ES406.I.ES_OK → (ES406, I.ES_OK); bare BOOL → (TAG, '')."""
    t = _clean(logical)
    if not t or "." not in t:
        return t, ""
    device, member = t.split(".", 1)
    return device, member


def _load_l5x_text(source: str | Path) -> str:
    if isinstance(source, Path):
        return source.read_text(encoding="utf-8", errors="replace")
    s = str(source)
    # Path-like string (not raw XML).
    if "<" not in s[:120] and Path(s).is_file():
        return Path(s).read_text(encoding="utf-8", errors="replace")
    return s


def parse_l5x_tag_datatypes(source: str | Path) -> dict[str, str]:
    """Map controller Tag Name → DataType from L5X Tag definitions."""
    text = _load_l5x_text(source)
    out: dict[str, str] = {}
    for attrs in TAG_ATTR_RE.findall(text):
        nm = re.search(r'\bName="([^"]+)"', attrs)
        dt = re.search(r'\bDataType="([^"]+)"', attrs)
        if not nm or not dt:
            continue
        name = nm.group(1)
        # First definition wins (controller scope before program locals).
        if name not in out:
            out[name] = dt.group(1)
    return out


def _is_placeholder(tag: str) -> bool:
    t = _clean(tag)
    if not t:
        return True
    if PLACEHOLDER_RE.search(t):
        return True
    return t.upper() in {"SPARE", "INVALID", "N/A", "NONE", "NOP()"}


def _extract_routine_bodies(text: str, routines: tuple[str, ...]) -> dict[str, str]:
    prog = re.search(
        r'<Program[^>]*Name="IO_MAP"[^>]*>(.*?)</Program>',
        text,
        re.I | re.S,
    )
    if not prog:
        return {}
    section = prog.group(1)
    bodies: dict[str, str] = {}
    for name in routines:
        m = re.search(
            rf'<Routine Name="{re.escape(name)}"[^>]*>(.*?)</Routine>',
            section,
            re.I | re.S,
        )
        if m:
            bodies[name] = m.group(1)
    return bodies


def _logical_from_rung(logic: str, channel: str, direction: str) -> str:
    ote_m = OTE_RE.search(logic)
    ote_raw = _clean(ote_m.group(1) if ote_m else "")
    if direction == "I":
        return "" if ote_raw == channel else ote_raw
    # Outputs: XIC(logical)OTE(channel)
    if ote_raw == channel:
        for x in re.findall(r"XIC\(([^)]+)\)", logic):
            xu = _clean(x)
            if xu.startswith("_EMU_"):
                continue
            if CHANNEL_RE.fullmatch(xu):
                continue
            return xu
        return ""
    return ote_raw


def parse_io_map_routines(
    source: str | Path,
    *,
    routines: tuple[str, ...] = ("CP_I", "CP_O"),
    tag_datatypes: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Parse CP_I / CP_O XIC/OTE endpoint → logical tag mappings."""
    path: Path | None = source if isinstance(source, Path) else None
    if path is None and isinstance(source, str) and "<" not in source[:120] and Path(source).is_file():
        path = Path(source)
    text = _load_l5x_text(source)

    dts = tag_datatypes if tag_datatypes is not None else parse_l5x_tag_datatypes(text)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, int]] = set()

    for routine, body in _extract_routine_bodies(text, routines).items():
        for rung in re.finditer(r"<!\[CDATA\[(.*?)\]\]>", body, re.S):
            logic = rung.group(1).strip()
            if not logic or logic.startswith("$"):
                continue
            if "NOP()" in logic and "XIC(" not in logic:
                continue
            channels = list(CHANNEL_RE.finditer(logic))
            if not channels:
                continue
            phys = next(
                (cm for cm in channels if not cm.group("adapter").startswith("_EMU_")),
                None,
            )
            if phys is None:
                continue
            adapter = phys.group("adapter")
            direction = phys.group("dir").upper()
            data_index = int(phys.group("slot"))
            bit = int(phys.group("bit"))
            key = (adapter, direction, data_index, bit)
            if key in seen:
                continue
            seen.add(key)
            endpoint = f"{adapter}:{direction}.Data[{data_index}].{bit}"
            logical = _logical_from_rung(logic, endpoint, direction)
            device, member = split_device_member(logical)
            datatype = dts.get(device, "")
            rows.append(
                {
                    "routine": routine,
                    "endpoint": endpoint,
                    "adapter": adapter,
                    "direction": direction,
                    "data_index": data_index,
                    "bit": bit,
                    "logical_tag": logical,
                    "device": device,
                    "member": member,
                    "datatype": datatype,
                    "placeholder": _is_placeholder(logical),
                    "rung": logic,
                    "source": str(path) if path else "",
                }
            )
    return rows


def build_oracle_io_map(l5x_path: str | Path) -> dict[str, Any]:
    """Structured oracle map: mappings + endpoint index + datatype catalog."""
    path = Path(l5x_path)
    text = path.read_text(encoding="utf-8", errors="replace")
    tag_datatypes = parse_l5x_tag_datatypes(text)
    mappings = parse_io_map_routines(text, tag_datatypes=tag_datatypes)
    for row in mappings:
        row["source"] = str(path)

    by_endpoint = {r["endpoint"]: r for r in mappings if not r.get("placeholder")}
    by_device: dict[str, list[str]] = {}
    for r in mappings:
        if r.get("placeholder"):
            continue
        by_device.setdefault(r["device"], []).append(r["endpoint"])

    udt_family = Counter(
        (r.get("datatype") or "UNKNOWN") for r in mappings if not r.get("placeholder")
    )
    return {
        "oracle_path": str(path),
        "mapping_count": len(mappings),
        "mapped_count": sum(1 for r in mappings if not r.get("placeholder") and r.get("logical_tag")),
        "placeholder_count": sum(1 for r in mappings if r.get("placeholder")),
        "routines": sorted({r["routine"] for r in mappings}),
        "udt_family_counts": dict(udt_family.most_common()),
        "tag_datatypes": tag_datatypes,
        "by_endpoint": by_endpoint,
        "by_device": by_device,
        "mappings": mappings,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--l5x", type=Path, default=DEFAULT_ORACLE)
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--sample", type=str, default="ES406", help="Device substring to sample")
    args = ap.parse_args(argv)

    if not args.l5x.is_file():
        print(f"MISSING oracle L5X: {args.l5x}", file=sys.stderr)
        return 2

    oracle = build_oracle_io_map(args.l5x)
    sample = [
        {
            "endpoint": r["endpoint"],
            "logical_tag": r["logical_tag"],
            "datatype": r["datatype"],
            "routine": r["routine"],
        }
        for r in oracle["mappings"]
        if args.sample.lower() in (r.get("logical_tag") or "").lower()
    ]
    summary = {
        "oracle_path": oracle["oracle_path"],
        "mapping_count": oracle["mapping_count"],
        "mapped_count": oracle["mapped_count"],
        "udt_family_counts": oracle["udt_family_counts"],
        "sample": sample[:20],
    }
    print(json.dumps(summary, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(oracle, indent=2), encoding="utf-8")
        print(f"wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

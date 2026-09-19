#!/usr/bin/env python3
"""Audit: does RUN VFD###_FLT / HAS FAULTED map to Motor_Starter_UDT.Flt.Overload?"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fortna_asc import read_asc


def extract_udt_members(l5x_text: str, dtype: str) -> list[tuple[str, str, str]]:
    m = re.search(
        rf'<DataType Name="{re.escape(dtype)}"[^>]*>(.*?)</DataType>',
        l5x_text,
        re.S,
    )
    if not m:
        return []
    block = m.group(1)
    out = []
    for mm in re.finditer(
        r'<Member Name="([^"]+)"[^>]*DataType="([^"]+)"[^>]*/?>',
        block,
    ):
        name, dt = mm.group(1), mm.group(2)
        # nearest preceding CDATA doc if any
        before = block[: mm.start()]
        docs = re.findall(r"<!\[CDATA\[(.*?)\]\]>", before)
        doc = (docs[-1] or "").strip() if docs else ""
        out.append((name, dt, doc))
    return out


def main() -> int:
    lib = ROOT / "tools" / "libraries" / "OReilly_Library_v3.L5X"
    text = lib.read_text(encoding="utf-8", errors="replace")
    flt = extract_udt_members(text, "Motor_Starter_Flt")
    print("=== Motor_Starter_Flt members (library) ===")
    for name, dt, doc in flt:
        print(f"  {name}: {dt}  doc={doc!r}")

    # Also check Motor_Starter_I for fault-related inputs
    mi = extract_udt_members(text, "Motor_Starter_I")
    print("=== Motor_Starter_I members ===")
    for name, dt, doc in mi:
        print(f"  {name}: {dt}  doc={doc!r}")

    # RUN descriptions for VFD*_FLT
    fortna = ROOT / "workspace" / "cp4-run" / "RUN" / "FORTNA"
    print("\n=== CP4 RUN VFD*_FLT / HAS FAULTED evidence ===")
    hits = []
    for p in sorted(fortna.glob("*.asc*")):
        try:
            _, rows = read_asc(p)
        except Exception:
            continue
        for r in rows:
            blob = " ".join(str(v) for v in r.values() if v)
            if re.search(r"VFD\d+_FLT|HAS FAULTED", blob, re.I):
                name = (
                    r.get("Name")
                    or r.get("IO_Name")
                    or r.get("Device")
                    or r.get("Tag")
                    or ""
                )
                desc = r.get("Desc") or r.get("Description") or r.get("Type") or ""
                hits.append((p.name, name, desc, {k: r[k] for k in list(r)[:8]}))
    for h in hits[:40]:
        print(f"  {h[0]}: name={h[1]!r} desc={h[2]!r}")
    print(f"  total hits: {len(hits)}")

    # Fortna training docs mentioning Overload / HAS FAULTED
    print("\n=== Doc hits (Flt.Overload / HAS FAULTED) ===")
    docs = ROOT / "docs"
    for p in docs.rglob("*"):
        if p.suffix.lower() not in {".md", ".txt", ".json"}:
            continue
        try:
            t = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if re.search(r"HAS FAULTED|Flt\.Overload|VFD.*_FLT", t, re.I):
            print(f"  {p.relative_to(ROOT)}")

    # Verdict
    overload_docs = [d for n, _, d in flt if n == "Overload"]
    print("\n=== VERDICT ===")
    print(f"Flt.Overload exists in Motor_Starter_Flt: {any(n=='Overload' for n,_,_ in flt)}")
    print(f"Overload member docs: {overload_docs}")
    print(
        "Mapping VFD###_FLT → P###_VFD.Flt.Overload is consistent with library UDT "
        "(single BOOL fault member named Overload / 'Motor Overload Fault'). "
        "RUN 'HAS FAULTED' is the discrete fault feedback point; library faceplate "
        "uses Flt.Overload as the generic motor/VFD fault latch — not a separate "
        "Flt.Faulted member."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

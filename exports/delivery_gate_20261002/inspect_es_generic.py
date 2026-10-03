"""Inspect ES program routines in any L5X."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def inspect(l5x: Path) -> dict:
    text = l5x.read_text(encoding="utf-8", errors="replace")
    es = re.search(r'<Program Name="ES"[^>]*>(.*?)</Program>', text, re.S)
    if not es:
        return {"l5x": str(l5x), "error": "NO_ES_PROGRAM"}
    body = es.group(1)
    routines = re.findall(r'<Routine Name="([^"]+)"', body)
    detail = {}
    for rn in routines:
        m = re.search(
            rf'<Routine Name="{re.escape(rn)}"[^>]*>.*?<RLLContent>(.*?)</RLLContent>',
            body,
            re.S,
        )
        if not m:
            detail[rn] = {"rungs": 0, "non_nop": 0, "sample": []}
            continue
        rungs = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", m.group(1))
        nonempty = [r for r in rungs if r.strip() and r.strip() != "NOP();"]
        detail[rn] = {
            "rungs": len(rungs),
            "non_nop": len(nonempty),
            "populated": len(nonempty) > 0,
            "sample": (nonempty or rungs)[:5],
        }
    return {
        "l5x": str(l5x),
        "routines": routines,
        "detail": detail,
        "main_populated": bool(detail.get("Main_Routine", {}).get("populated")),
        "has_safe_logic": any("Safe_Logic" in r for r in routines),
        "has_safe_pi": any("Safe_PI" in r for r in routines),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("l5x")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    out = inspect(Path(args.l5x))
    print(json.dumps(out, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

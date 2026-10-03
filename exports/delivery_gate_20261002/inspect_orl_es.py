"""Inspect known-good ORL_AC3 ES program for Safety zone members/routines."""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
L5X = REPO / "exports" / "current" / "ORL_AC3_2026_09_29_2008.L5X"


def main() -> None:
    text = L5X.read_text(encoding="utf-8", errors="replace")
    es = re.search(r'<Program Name="ES"[^>]*>(.*?)</Program>', text, re.S)
    if not es:
        raise SystemExit("NO ES PROGRAM")
    body = es.group(1)
    routines = re.findall(r'<Routine Name="([^"]+)"', body)
    print("ES_ROUTINES", routines)

    main_m = re.search(
        r'<Routine Name="Main_Routine"[^>]*>.*?<RLLContent>(.*?)</RLLContent>',
        body,
        re.S,
    )
    if main_m:
        rungs = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", main_m.group(1))
        print("MAIN_RUNG_COUNT", len(rungs))
        for i, r in enumerate(rungs[:20]):
            print(f"MAIN[{i}]", r[:220])

    out = {"routines": routines, "zones": {}}
    for rn in routines:
        if "Safe_Logic" not in rn and "Safe_PI" not in rn:
            continue
        m = re.search(
            rf'<Routine Name="{re.escape(rn)}"[^>]*>.*?<RLLContent>(.*?)</RLLContent>',
            body,
            re.S,
        )
        if not m:
            continue
        rungs = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", m.group(1))
        comments = re.findall(r"<Comment><!\[CDATA\[(.*?)\]\]></Comment>", m.group(1))
        # Extract member device names from comments like "ESPB2 → Zone" or ES_SIL calls
        members = []
        for r in rungs:
            for call in re.findall(r"ES_SIL\w+\(([^,]+),([^,]+),", r):
                members.append(call[1].strip())
            for call in re.findall(r"ES_\w+\(([^,]+),([^,]+),", r):
                if call[1].strip() not in members and not call[1].strip().endswith("_AOI"):
                    members.append(call[1].strip())
        print(rn, "RUNGS", len(rungs))
        for i, (c, r) in enumerate(zip(comments, rungs)):
            if i > 12:
                break
            print(f"  [{i}] {c[:80]} | {r[:160]}")
        out["zones"][rn] = {
            "rung_count": len(rungs),
            "members_guess": members,
            "rungs_sample": rungs[:8],
            "comments_sample": comments[:8],
        }

    # Also hunt ESPB/ESLS style tags near Area_Test1_ESZone1
    zone = "Area_Test1_ESZone1"
    near = []
    for m in re.finditer(rf"{re.escape(zone)}", text):
        pass
    # device tags that appear in Safe_Logic rungs
    safe_logic_name = f"{zone}_Safe_Logic"
    if safe_logic_name in out["zones"]:
        print("SAFE_LOGIC_MEMBERS_GUESS", out["zones"][safe_logic_name]["members_guess"])

    dest = Path(__file__).with_name("orl_known_good_es.json")
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("WROTE", dest)


if __name__ == "__main__":
    main()

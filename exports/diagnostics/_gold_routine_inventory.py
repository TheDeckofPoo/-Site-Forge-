#!/usr/bin/env python3
import re
from pathlib import Path

gold = Path(r"C:\dev\worktree\FortnaPlus-anton\exports\current\MSCRENOPICK_2026_10_13_1725.L5X")
t = gold.read_text(encoding="utf-8", errors="replace")
for name, body in re.findall(r'<Program Name="([^"]+)"[^>]*>(.*?)</Program>', t, re.S):
    if "Area" in name or name in ("System", "Sys", "ES", "IO_MAP"):
        rts = re.findall(r'<Routine Name="([^"]+)"', body)
        print(f"{name} -> {rts}")
print("---")
for needle in (
    "Conv_PE",
    "Conv_PI",
    "Control_Station",
    "Area_Logic",
    "Area_PI",
    "Slow_ControlStation",
    "AOI_SNTP_QUERY",
    "SNTP_AOI_TAG",
    "SNTP_SERVER_ADDRESS",
    "CommDiag_UDT",
    "NO_PointPlaceholder",
):
    print(needle, t.count(needle) if needle != "Slow_ControlStation" else len(re.findall(r"Slow_ControlStation\(", t)))

# Control_Station body sample
m = re.search(r'<Routine Name="Control_Station"[^>]*>(.*?)</Routine>', t, re.S)
if m:
    texts = re.findall(r"<!\[CDATA\[(.*?)\]\]>", m.group(1))
    print("Control_Station rungs sample:", texts[:6])
m2 = re.search(r'<Routine Name="Area_Logic"[^>]*>(.*?)</Routine>', t, re.S)
if m2:
    texts = re.findall(r"<!\[CDATA\[(.*?)\]\]>", m2.group(1))
    print("Area_Logic rungs sample:", texts[:6])

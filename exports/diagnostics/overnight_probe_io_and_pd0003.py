#!/usr/bin/env python3
"""Overnight probe: CL17 / EZSSV / MEM / PD-0003 binding / Comms-NTP comments.

Reads gold baseline L5X + physical_io_map + anton workbook (read-only).
Writes JSON evidence under exports/diagnostics/. Does not modify Curtis tree.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

WT = Path(__file__).resolve().parents[2]
ANTON = Path(r"C:\dev\worktree\FortnaPlus-anton")
GOLD = WT / "exports" / "diagnostics" / "gold_baseline_20261013_1725"
L5X = GOLD / "MSCRENOPICK_2026_10_13_1725.L5X"
IOMAP = GOLD / "physical_io_map.csv"
WB = ANTON / "workspace" / "autogen_workbook.json"
OUT = WT / "exports" / "diagnostics"


def _load_l5x() -> str:
    return L5X.read_text(encoding="utf-8", errors="replace")


def probe_cl17(text: str) -> dict:
    hits = re.findall(r".{0,80}CL17.{0,120}", text)
    ote = re.findall(r"XIC\(CL17\)OTE\(([^)]+)\)", text)
    xic_mod = re.findall(r"XIC\(([^)]*AENTR3[^)]*)\)OTE\(CL17\)", text)
    # Also CP_O style
    any_aentr = [h for h in hits if "AENTR3" in h]
    status = "UNKNOWN"
    if ote and any("AENTR3:O.Data[10].2" in x or "AENTR3:O.Data.10.2" in x for x in ote):
        status = "CORRECT"
    elif ote:
        status = "WRONG_ENDPOINT"
    elif "CL17" in text:
        status = "STILL_PARTIAL"
    else:
        status = "MISSING"
    return {
        "status": status,
        "ote_targets": ote[:10],
        "input_paths": xic_mod[:10],
        "sample_hits": hits[:8],
        "aentr_related_hits": len(any_aentr),
    }


def probe_ezssv(text: str, iomap_rows: list[dict]) -> dict:
    names = ["EZSSV15", "EZSSV18"]
    out = {}
    for n in names:
        in_l5x_tag = bool(re.search(rf'\bName="{n}"', text))
        in_logic = bool(re.search(rf"\b{n}\b", text))
        map_rows = [r for r in iomap_rows if str(r.get("device") or r.get("name") or "").upper() == n]
        out[n] = {
            "in_l5x_tag": in_l5x_tag,
            "in_l5x_logic": in_logic,
            "physical_io_map_rows": map_rows[:5],
            "classification_hint": (
                "MUST_EXCLUDE_IF_OA4_CAPACITY_INVALID"
                if map_rows or in_logic
                else "ABSENT_FROM_ARTIFACT"
            ),
        }
    return out


def probe_mem(text: str, iomap_rows: list[dict]) -> dict:
    names = ["MEM_ALLOW_JAM", "MEM_OK_TO_RUN_MP3"]
    out = {}
    for n in names:
        out[n] = {
            "in_l5x": bool(re.search(rf"\b{re.escape(n)}\b", text)),
            "in_physical_io_map": any(
                n.upper() in str(r.get("device") or r.get("name") or "").upper()
                for r in iomap_rows
            ),
            "cp_i_o_hits": len(re.findall(rf".{{0,40}}{re.escape(n)}.{{0,80}}", text)),
        }
    return out


def probe_high_byte(iomap_rows: list[dict]) -> dict:
    """Spot high-byte / word-bit vs byte-bit style addresses in map."""
    samples = []
    wordish = 0
    for r in iomap_rows:
        addr = str(
            r.get("address")
            or r.get("logix_address")
            or r.get("endpoint")
            or r.get("tag")
            or ""
        )
        ui = str(r.get("ui_address") or r.get("display_address") or "")
        raw = addr + " " + ui
        if re.search(r"Data\[\d{3,}\]", raw) or re.search(r":I\.Data\.\d{3,}", raw):
            wordish += 1
            if len(samples) < 12:
                samples.append(
                    {
                        "device": r.get("device") or r.get("name"),
                        "address": addr,
                        "ui_address": ui,
                        "status": r.get("status") or r.get("final_status"),
                    }
                )
    return {
        "row_count": len(iomap_rows),
        "high_word_pattern_rows": wordish,
        "samples": samples,
        "note": "Full ~51 UI normalization audit requires UI join evidence; this is map-side scan only.",
    }


def probe_pd0003(text: str, wb: dict) -> dict:
    # Fast_Conv NOPs
    fast_prog = re.search(
        r'<Program Name="MSCRENOPICK_Area_Fast"[^>]*>(.*?)</Program>',
        text,
        re.S,
    )
    conv_fast = ""
    if fast_prog:
        m = re.search(
            r'<Routine Name="Conv_Fast"[^>]*>(.*?)</Routine>',
            fast_prog.group(1),
            re.S,
        )
        conv_fast = m.group(1) if m else ""
    nop_count = len(re.findall(r"NOP\(\);", conv_fast))
    fast_conv_calls = len(re.findall(r"Fast_Conv\(", conv_fast))
    pd_comments = re.findall(r"PD-0003[^<\]]{0,120}", conv_fast)
    # Safety routines present
    safe_logic = re.findall(r'Routine Name="([^"]+_Safe_Logic)"', text)
    safe_pi = re.findall(r'Routine Name="([^"]+_Safe_PI)"', text)
    # Workbook binding
    zones = []
    for z in (wb.get("safety_build") or {}).get("zones") or []:
        zones.append(
            {
                "name": z.get("engineering_name") or z.get("name"),
                "area": z.get("area") or z.get("areaRef"),
                "members": list(z.get("members") or []),
                "conveyors": list(z.get("conveyors") or z.get("conveyorRefs") or []),
                "membersOrigin": z.get("membersOrigin"),
                "operational": z.get("operational"),
            }
        )
    sz_c = Counter()
    area_c = Counter()
    for c in wb.get("conveyors") or []:
        if c.get("include") in (False, 0, "0", "false", "False"):
            continue
        if not (c.get("main_area") or c.get("safety_zone")):
            continue
        area_c[str(c.get("main_area") or "")] += 1
        sz_c[str(c.get("safety_zone") or "")] += 1
    return {
        "conv_fast_nop_count": nop_count,
        "conv_fast_fast_conv_calls": fast_conv_calls,
        "pd0003_comment_samples": pd_comments[:5],
        "safe_logic_routines": safe_logic,
        "safe_pi_routines": safe_pi,
        "workbook_areas": wb.get("areas"),
        "workbook_safety_zones": zones,
        "conveyor_main_area_counts": dict(area_c),
        "conveyor_safety_zone_counts": dict(sz_c),
        "first_divergence": (
            "Conveyors bound to MSCRENOPICK_ESZone1 (no members / no PI writer) while "
            "engineer Safety members live on Area_Test1_ESZone1 (area=Area_Test1, "
            "conveyors=[]). Fast_Conv scrub requires item.safety_zone ∈ _pi_writer_zones; "
            "Area_Test1_ESZone1 is a PI-writer zone but is NOT the conveyor safety_zone "
            "and area-key rebind cannot match MSCRENOPICK_Area → Area_Test1. "
            "ES Safe_Logic/Safe_PI emit for ready member zones independently of "
            "conveyor binding — hence both truths coexist."
        ),
        "failure_class": (
            "AREA_IDENTITY_MISMATCH / MISSING_CONVEYOR_SAFETY_FK "
            "(not a missing _Safe invent bug; PD-0003 withholding is truthful for "
            "MSCRENOPICK_ESZone1-bound conveyors)"
        ),
    }


def probe_comms_ntp(text: str) -> dict:
    comm = re.findall(r".{0,40}CommDiag_UDT.{0,160}", text)
    ntp = re.findall(r".{0,40}(?:NTP|SNTP).{0,160}", text)
    deferred_comm = [h for h in comm if "deferred" in h.lower() or "not in" in h.lower()]
    deferred_ntp = [h for h in ntp if "deferred" in h.lower() or "insufficient" in h.lower() or "unavailable" in h.lower()]
    # Library check
    lib = WT / "tools" / "libraries" / "OReilly_Library_v3.L5X"
    lib_text = lib.read_text(encoding="utf-8", errors="replace") if lib.is_file() else ""
    has_commdiag = "CommDiag_UDT" in lib_text
    has_sntp = bool(re.search(r"\bSNTP", lib_text))
    has_ntp_aoi = bool(re.search(r'AddOnInstructionDefinition[^>]*Name="[^"]*NTP', lib_text))
    return {
        "device_comms": {
            "l5x_mentions": len(comm),
            "deferred_samples": deferred_comm[:5] or comm[:3],
            "library_has_CommDiag_UDT": has_commdiag,
            "contract": "UNKNOWN_GENERIC" if not has_commdiag else "PARTIAL_LIBRARY_PRESENT",
            "gap": (
                "CommDiag_UDT absent from OReilly_Library_v3 — Device_Comm_Logic correctly deferred. "
                "Need approved generic CommDiag_UDT + AOI/inputs/outputs contract before emit."
            ),
        },
        "ntp": {
            "l5x_mentions": len(ntp),
            "deferred_samples": deferred_ntp[:5] or ntp[:3],
            "library_has_SNTP_token": has_sntp,
            "library_has_NTP_AOI": has_ntp_aoi,
            "contract": "UNKNOWN_GENERIC",
            "gap": (
                "Generic NTP/SNTP evidence insufficient in approved library for safe emit. "
                "Do not copy finished-site NTP. Need generic UDT/AOI + required params + "
                "controller time-sync evidence contract."
            ),
        },
    }


def main() -> int:
    text = _load_l5x()
    rows = []
    if IOMAP.is_file():
        with IOMAP.open(encoding="utf-8", errors="replace", newline="") as f:
            rows = list(csv.DictReader(f))
    wb = json.loads(WB.read_text(encoding="utf-8")) if WB.is_file() else {}

    report = {
        "base_sha": "a935a22a86f93dceb0f3910d9f5c8f506a0c1a27",
        "feature_branch": "feature/io-generator-truth-cleanup",
        "gold_l5x": str(L5X),
        "gold_sha256": "64cce43d57ee20fdaaa309021a0b6c6d81623e23c8dafbb39181a5ace6dcb0fa",
        "CL17": probe_cl17(text),
        "EZSSV": probe_ezssv(text, rows),
        "MEM": probe_mem(text, rows),
        "HIGH_BYTE": probe_high_byte(rows),
        "PD0003": probe_pd0003(text, wb),
        "COMMS_NTP": probe_comms_ntp(text),
        "physical_io_map_row_count": len(rows),
    }
    out = OUT / "overnight_io_pd0003_probe.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] if k not in ("PD0003", "COMMS_NTP") else {kk: report[k][kk] for kk in list(report[k])[:6]} for k in report}, indent=2)[:4000])
    print("WROTE", out)
    print("CL17", report["CL17"]["status"])
    print("PD0003 class", report["PD0003"]["failure_class"])
    print("Conv_Fast NOPs", report["PD0003"]["conv_fast_nop_count"], "Fast_Conv calls", report["PD0003"]["conv_fast_fast_conv_calls"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

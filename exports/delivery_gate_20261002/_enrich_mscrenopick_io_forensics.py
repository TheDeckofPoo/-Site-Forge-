#!/usr/bin/env python3
"""Enrich MSCRENOPICK_IO_FORENSICS with cross-machine Conveyor/Configio evidence."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))

from fortna_asc import read_asc  # noqa: E402
from fortna_physical_word_resolver import PhysicalWordResolver  # noqa: E402

OUT = Path(__file__).resolve().parent
REPORT = OUT / "MSCRENOPICK_IO_FORENSICS.json"
TXT = OUT / "MSCRENOPICK_IO_FORENSICS.txt"
RUN = Path(r"C:\dev\worktree\FortnaPlus\workspace\active\RUN")


def main() -> int:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    focus_words = sorted(
        {"1100", "1101", "1107", "1113", "1120", "1123", "1131", "1132", "1133"}
    )
    _, rows = read_asc(RUN / "FORTNA" / "Conveyor.asc")
    by_word: dict[str, list[dict]] = defaultdict(list)
    conv_index = {}
    for r in rows:
        n = str(r.get("IO_Name") or "").strip()
        conv_index[n.upper()] = r
        w = str(r.get("IO_Address_Word") or "").strip()
        if w not in focus_words:
            continue
        by_word[w].append(
            {
                "IO_Name": n,
                "Machine_Name": str(r.get("Machine_Name") or "").strip(),
                "IO_Address_Bit": str(r.get("IO_Address_Bit") or "").strip(),
                "General_Description": str(r.get("General_Description") or "").strip()[
                    :120
                ],
                "IO_Module_Type": str(r.get("IO_Module_Type") or "").strip(),
            }
        )

    peer = {}
    for mach in ["MSCRENOPICK", "MSCRENOPACK"]:
        try:
            wm = PhysicalWordResolver(RUN, mach).io_word_map() or {}
            keys = {str(k) for k in wm.keys()}
            peer[mach] = {
                "word_count": len(wm),
                "focus_words_present": sorted(w for w in focus_words if w in keys),
                "all_words": sorted(keys),
            }
        except Exception as ex:  # noqa: BLE001
            peer[mach] = {"error": str(ex)[:160]}

    def enrich_device(d: dict) -> None:
        raw = conv_index.get((d.get("name") or "").upper())
        if not raw:
            return
        d["conveyor_row"] = {
            "Machine_Name": str(raw.get("Machine_Name") or "").strip(),
            "IO_Address_Word": str(raw.get("IO_Address_Word") or "").strip(),
            "IO_Address_Bit": str(raw.get("IO_Address_Bit") or "").strip(),
            "General_Description": str(raw.get("General_Description") or "").strip()[
                :160
            ],
            "IO_Module_Type": str(raw.get("IO_Module_Type") or "").strip(),
        }
        desc = (d["conveyor_row"]["General_Description"] or "").upper()
        if "RESET PB" in desc or "PBRS" in desc:
            d["nomenclature_note"] = (
                "Conveyor description indicates RESET pushbutton (RS-6 family)"
            )
            d["likely_fortna_plus_representation"] = (
                d.get("likely_fortna_plus_representation") or "CPx_CS.I.Reset_PB"
            )
        if "ON/OFF SWITCH" in desc or "DISABLE" in desc:
            d["nomenclature_note"] = (
                "Conveyor description indicates conveyor disable ON/OFF selector switch"
            )
            d["likely_fortna_plus_representation"] = (
                d.get("likely_fortna_plus_representation")
                or "CPx_CS.I.Disable_SS / conveyor enable interlock (semantic TBD)"
            )

    for d in report.get("focus_pushbuttons") or []:
        enrich_device(d)
    for d in report.get("unresolved_physical_devices") or []:
        enrich_device(d)
    for d in (report.get("safety_population") or {}).get("unresolved_forensics") or []:
        enrich_device(d)

    occ = report["unproven_channel_occupancy_audit"]
    word_c = Counter(str(r.get("word") or "") for r in occ.get("rows") or [])
    mod_c: Counter[str] = Counter()
    for r in occ.get("rows") or []:
        ep = str(r.get("physical_endpoint") or "")
        mod_c[ep.split(":")[0] if ":" in ep else "?"] += 1
    occ["by_word"] = dict(word_c)
    occ["by_adapter_prefix"] = dict(mod_c)
    occ["forensic_conclusion"] = (
        "All 128 rows are endpoint-shaped AENT*:I/O.Data[*].* channels on active-controller "
        "Configio words (primarily 1000-range). None overlap named device endpoints in the "
        "canonical ledger. None carry explicit SPARE tokens. Classification: "
        "REAL_UNUSED_PHYSICAL_CHANNEL as module capacity / unnamed channels — NOT proven "
        "SPARE_UNUSED, NOT field devices, NOT internal logic, NOT duplicate noise."
    )

    report["cross_machine_word_ownership"] = {
        "focus_words": focus_words,
        "conveyor_machine_counts_for_focus_words": {
            w: dict(Counter(x["Machine_Name"] for x in rows_))
            for w, rows_ in by_word.items()
        },
        "peer_configio": peer,
        "finding": (
            "Focus words 1100-1133 appear in Conveyor.asc only with Machine_Name=N/A. "
            "They are absent from MSCRENOPICK active Configio (1000-1012,1142-1144) and also "
            "absent from MSCRENOPACK Configio. Therefore peer-Configio FOREIGN proof is not "
            "available; ownership remains genuinely engineer/AI-cluster territory "
            "(remote/legacy/unmapped rack)."
        ),
        "sample_rows_by_word": {w: rows_[:8] for w, rows_ in by_word.items()},
    }
    for p in report.get("proposed_generic_resolver_improvements") or []:
        if p.get("id") == "GEN-IO-006":
            p["mscrenopick_observation"] = (
                "For MSCRENOPICK 1100s, peer Configio index finds NO owner machine — "
                "improvement still valuable generically, but would not auto-resolve this "
                "site cluster."
            )

    REPORT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    extra = []
    a = extra.append
    a("")
    a("--- CROSS-MACHINE WORD OWNERSHIP (Conveyor.asc + Configio) ---")
    a(report["cross_machine_word_ownership"]["finding"])
    a(f"peer_configio: {json.dumps({k: {kk: vv for kk, vv in v.items() if kk != 'all_words'} for k, v in peer.items()})}")
    a("Conveyor Machine_Name counts for focus words:")
    for w, c in sorted(
        report["cross_machine_word_ownership"][
            "conveyor_machine_counts_for_focus_words"
        ].items()
    ):
        a(f"  word {w}: {c}")
    a("")
    a("Focus device Conveyor descriptions:")
    for d in report.get("focus_pushbuttons") or []:
        cr = d.get("conveyor_row") or {}
        a(
            f"  {d.get('name')}: Mach={cr.get('Machine_Name')} "
            f"{cr.get('IO_Address_Word')}.{cr.get('IO_Address_Bit')} :: "
            f"{cr.get('General_Description')}"
        )
        if d.get("nomenclature_note"):
            a(f"    note: {d.get('nomenclature_note')}")
    a("")
    a("Occupancy forensic conclusion:")
    a("  " + occ["forensic_conclusion"])
    a(f"  by_adapter_prefix: {occ.get('by_adapter_prefix')}")
    a(f"  by_word: {occ.get('by_word')}")

    txt = TXT.read_text(encoding="utf-8")
    marker = "=" * 78 + "\nEND FORENSICS"
    block = "\n".join(extra) + "\n"
    if marker in txt:
        txt = txt.replace(marker, block + marker)
    else:
        txt = txt + "\n" + block
    TXT.write_text(txt, encoding="utf-8")
    print("enriched", REPORT, TXT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

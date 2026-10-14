#!/usr/bin/env python3
"""Build routine matrix + audit for Safe Partial virgin SHIP L5X."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "exports/diagnostics/p0_truth_chain_virgin_ship"
L5X = OUT / "generated_safe_partial" / "MSCRENOSHIP.L5X"
sys.path.insert(0, str(REPO / "tools" / "scripts"))


def main() -> int:
    text = L5X.read_text(encoding="utf-8", errors="replace")
    print("bytes", L5X.stat().st_size)
    print("NTP_Configured", "NTP_Configured" in text)
    print("XIC(NTP_Configured)", "XIC(NTP_Configured)" in text)
    print("AOI_SNTP_QUERY", "AOI_SNTP_QUERY" in text)
    sorter = bool(re.search(r'Program Name="[^"]*Sorter_Track', text, re.I))
    print("Sorter_Track program", sorter)
    print(
        "NO_PointPlaceholder spare hazard",
        bool(re.search(r"XIC\(NO_PointPlaceholder\).*OTE\(", text)),
    )
    progs = re.findall(r'<Program Name="([^"]+)"', text)
    print("programs", progs)

    rows: list[dict] = []
    for prog in re.finditer(
        r'<Program Name="([^"]+)"[^>]*>(.*?)</Program>', text, re.I | re.S
    ):
        pname = prog.group(1)
        body = prog.group(2)
        scheduled = set(re.findall(r"JSR\(([^,)]+)", body, re.I))
        for rout in re.finditer(
            r'<Routine Name="([^"]+)"[^>]*>(.*?)</Routine>', body, re.I | re.S
        ):
            rname = rout.group(1)
            rbody = rout.group(2)
            texts = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", rbody, re.S)
            joined = "\n".join(texts)
            logic = bool(texts) and not all(
                re.fullmatch(r"\s*(NOP\(\);)?\s*", t or "") for t in texts
            )
            status = "FUNCTIONAL" if logic else "PRESENT_BUT_INERT"
            reason = ""
            if rname.upper() == "NTP" or "NTP_Configured" in joined:
                status = "FUNCTIONAL_BUT_CONFIG_REQUIRED"
                reason = "NTP_Configured=0 / Enable_Instruction=0 — no SNTP traffic"
            if "REVIEW_REQUIRED" in joined and rname.upper() != "NTP":
                status = "REVIEW_REQUIRED"
                reason = "REVIEW_REQUIRED marker in routine"
            if rname.lower() == "stacklight" and "OTE(" in joined:
                status = "PRESENT_BUT_INERT"
                reason = "Stacklight UDT bits written; no proven physical/HMI consumer"
            if "CommDiag" in joined or (
                "device" in rname.lower() and "REVIEW" in joined.upper()
            ):
                status = "REVIEW_REQUIRED"
                reason = "Device Comm / CommDiag_UDT incomplete"
            rows.append(
                {
                    "PROGRAM": pname,
                    "ROUTINE": rname,
                    "EXISTS": "YES",
                    "SCHEDULED": (
                        "YES"
                        if (rname in scheduled or rname == "Main_Routine")
                        else "NO"
                    ),
                    "LOGIC_PRESENT": "YES" if logic else "NO",
                    "STATUS": status,
                    "REASON": reason,
                }
            )

    (OUT / "routine_matrix.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8"
    )
    print("status counts", Counter(r["STATUS"] for r in rows))
    print("routine count", len(rows))
    for want in [
        "NTP",
        "Pulse",
        "TimeStamp",
        "System_Logic",
        "Stacklight",
        "Area_Logic",
        "Conv_PI",
        "Conv_PE",
        "Devices_Comm_Logic",
        "PLC_Init",
    ]:
        hits = [r for r in rows if r["ROUTINE"] == want or want in r["ROUTINE"]]
        print(want, hits[:3])

    audit: dict = {"ran": False}
    try:
        from fortna_l5x_acceptance_auditor import audit_l5x

        audit = audit_l5x(L5X, machine="MSCRENOSHIP")
        if not isinstance(audit, dict):
            audit = {"raw": str(audit)}
        audit["ran"] = True
    except Exception as e:
        audit = {"ran": True, "error": str(e)}
    (OUT / "safe_partial_audit.json").write_text(
        json.dumps(audit, indent=2, default=str), encoding="utf-8"
    )
    print("audit keys", list(audit)[:15])
    print(
        "audit summary",
        {
            k: audit.get(k)
            for k in ("ok", "status", "audit_pass", "error", "disposition", "result")
            if k in audit
        },
    )

    summary_path = OUT / "virgin_ship_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["SAFE_PARTIAL"] = {
        "PLC_ARTIFACT_GENERATED": "YES",
        "l5x": str(L5X),
        "l5x_bytes": L5X.stat().st_size,
        "SORTER_TRACK_GENERATED": "YES" if sorter else "NO",
        "NTP_Configured_tag": "NTP_Configured" in text,
        "NTP_Configured_gate": "XIC(NTP_Configured)" in text,
        "routine_count": len(rows),
        "status_counts": dict(Counter(r["STATUS"] for r in rows)),
        "audit_ok": bool(
            audit.get("ok")
            or audit.get("status") == "PASS"
            or audit.get("audit_pass")
        ),
        "commissioning_ready": False,
        "note": (
            "Normal generate blocked by Safety assignment; "
            "Safe Partial with acknowledge_safety_shell_only emitted structural PLC"
        ),
    }
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print("SAFE_PARTIAL", summary["SAFE_PARTIAL"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

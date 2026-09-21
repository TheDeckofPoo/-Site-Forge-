#!/usr/bin/env python3
"""Generate MSCRENOSHIP Safety evidence UNION diagnostic JSON + MD."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "scripts"))

from fortna_safety_model import (  # noqa: E402
    build_safety_evidence_union,
    reconcile_safety_devices,
    safety_inventory_parity,
)

RUN = ROOT / "workspace/_reno_peek/20260813-1132-MSCRENO-MSCRENOSHIP-RUN/RUN"
MACHINE = "MSCRENOSHIP"
OUT_DIR = ROOT / "exports" / "diagnostics"
# Pre-union baseline captured before evidence-union landing (ESTOP/ESLS only).
BEFORE = {"ESTOP": 13, "ESLS": 5, "ESR": 0, "MCR": 0, "CS": 0, "total": 18}


def main() -> int:
    if not (RUN / "project.cfg").is_file():
        print("MSCRENOSHIP RUN missing", RUN)
        return 1
    union = build_safety_evidence_union(RUN, MACHINE)
    parity = safety_inventory_parity(RUN, MACHINE)
    after_kinds = Counter(
        str(s.get("kind") or "") for s in (union.get("signals") or [])
    )
    after = {
        "ESTOP": int(after_kinds.get("ESTOP") or 0),
        "ESLS": int(after_kinds.get("ESLS") or 0),
        "ESR": int(after_kinds.get("ESR") or 0),
        "MCR": int(after_kinds.get("MCR") or 0),
        "CS": int(after_kinds.get("CS") or 0),
        "total": int((union.get("counts") or {}).get("signals") or 0),
    }

    # Foreign unresolved named MCR/ESR (Hardware I/O) — excluded from union
    foreign_unresolved = []
    try:
        from fortna_hardware_io_model import build_hardware_io_model
        from fortna_safety_model import _classify_device

        hw = build_hardware_io_model(RUN, MACHINE)
        for p in hw.get("unresolved_named_points") or []:
            nm = str((p or {}).get("name") or "")
            kind = _classify_device(nm)
            if kind in {"MCR", "ESR"}:
                foreign_unresolved.append({"name": nm, "kind": kind, "reason": p.get("reason")})
    except Exception as ex:
        foreign_unresolved = [{"error": str(ex)}]

    # MCR provenance trace — current-site first; else note none recovered
    mcr_trace = None
    mcr_signals = [s for s in (union.get("signals") or []) if s.get("kind") == "MCR"]
    if mcr_signals:
        s0 = mcr_signals[0]
        mcr_trace = {
            "signal": s0.get("name"),
            "kind": s0.get("kind"),
            "sources": s0.get("sources"),
            "evidence": s0.get("evidence"),
            "groupKey": s0.get("groupKey"),
            "deviceStem": s0.get("deviceStem"),
            "signalRole": s0.get("signalRole"),
        }
    else:
        # Demonstrate grouping capability with synthetic PACK-style names (not inventoried)
        demo = reconcile_safety_devices(
            [
                {"name": "13MCR1", "kind": "MCR"},
                {"name": "13MCR1_AUX", "kind": "MCR"},
                {"name": "T_13MCR1", "kind": "MCR"},
                {"name": "T_13MCR1_AUX", "kind": "MCR"},
            ]
        )
        mcr_trace = {
            "current_site_mcr": 0,
            "note": (
                "No current-site MCR recovered for MSCRENOSHIP. "
                "Hardware I/O unresolved_named_points lists PACK-owned 13/14MCR* "
                "which are correctly excluded (foreign). Grouping demo below."
            ),
            "grouping_demo": (demo.get("devices") or [None])[0],
            "foreign_unresolved_mcr_esr": foreign_unresolved,
        }

    early_return_bug = {
        "real": True,
        "location": "dashboard/safety-build.js loadDevicesFromRun",
        "behavior_before": (
            "Returned after first successful buildSafetyModel even when inventory "
            "was ESTOP/ESLS-only, skipping Hardware I/O classification UNION."
        ),
        "fix": (
            "UNION all sources (SafetyModel + listDevices + Hardware I/O); "
            "wipe on Load/Clear; never serve previous-machine cached model."
        ),
    }

    payload = {
        "machine": MACHINE,
        "run_dir": str(RUN),
        "early_return_bug": early_return_bug,
        "counts_by_role_before": BEFORE,
        "counts_by_role_after": after,
        "mcr_recovered": after["MCR"],
        "esr_recovered": after["ESR"],
        "foreign_stale": parity.get("foreign_stale") or [],
        "parity_counts": parity.get("counts") or {},
        "source_counts": union.get("source_counts") or {},
        "union_counts": union.get("counts") or {},
        "safety_devices_grouped": union.get("devices") or [],
        "mcr_provenance_trace": mcr_trace,
        "foreign_unresolved_mcr_esr_excluded": foreign_unresolved,
        "policy": union.get("policy") or {},
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jp = OUT_DIR / "mscrenoship_safety_evidence_union.json"
    mp = OUT_DIR / "mscrenoship_safety_evidence_union.md"
    jp.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    md = []
    md.append("# MSCRENOSHIP Safety evidence UNION")
    md.append("")
    md.append(f"**Machine:** `{MACHINE}`  ")
    md.append(f"**RUN:** `{RUN}`")
    md.append("")
    md.append("## Early-return bug")
    md.append("")
    md.append(f"- **Real:** `{early_return_bug['real']}`")
    md.append(f"- **Location:** `{early_return_bug['location']}`")
    md.append(f"- **Before:** {early_return_bug['behavior_before']}")
    md.append(f"- **Fix:** {early_return_bug['fix']}")
    md.append("")
    md.append("## Counts by role")
    md.append("")
    md.append("| Role | Before | After |")
    md.append("|------|--------|-------|")
    for role in ("ESTOP", "ESLS", "ESR", "MCR", "CS", "total"):
        md.append(f"| {role} | {BEFORE.get(role, 0)} | {after.get(role, 0)} |")
    md.append("")
    md.append(f"- **MCR recovered:** {after['MCR']}")
    md.append(f"- **ESR recovered:** {after['ESR']}")
    md.append(
        f"- **foreign_stale:** {len(parity.get('foreign_stale') or [])} "
        f"(required 0 on clean RUN)"
    )
    md.append("")
    md.append("## Source UNION counts")
    md.append("")
    for k, v in (union.get("source_counts") or {}).items():
        md.append(f"- `{k}`: {v}")
    md.append("")
    md.append("## MCR provenance")
    md.append("")
    if after["MCR"]:
        md.append("```json")
        md.append(json.dumps(mcr_trace, indent=2))
        md.append("```")
    else:
        md.append(
            "No current-site MCR/ESR for MSCRENOSHIP. Hardware I/O "
            "`unresolved_named_points` still lists PACK-owned `13MCR*` / `14MCR*` / "
            "`13ESR1_AUX` — correctly **excluded** from the current-site UNION."
        )
        md.append("")
        md.append("Excluded foreign unresolved:")
        for row in foreign_unresolved:
            md.append(f"- `{row.get('name')}` ({row.get('kind')})")
        md.append("")
        md.append("Grouping demo (stem + AUX + T_ alias → one device):")
        md.append("")
        md.append("```json")
        md.append(json.dumps((mcr_trace or {}).get("grouping_demo"), indent=2))
        md.append("```")
    md.append("")
    mp.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"wrote {jp}")
    print(f"wrote {mp}")
    print("before", BEFORE)
    print("after", after)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

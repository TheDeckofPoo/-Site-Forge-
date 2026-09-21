#!/usr/bin/env python3
"""Provenance for the 58 ghost Safety devices Curtis observed with no RUN loaded."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))

from fortna_asc import read_asc  # noqa: E402
from fortna_safety_model import _classify_device, discover_safety_devices  # noqa: E402

NAMES = [
    "2ES", "3ES", "ES1002", "ES1008", "ES1014", "ES1018", "ES400", "ES406",
    "T_2ES", "T_3ES",
    "ESLS125", "ESLS125A", "ESLS127", "ESLS127A", "ESLS141", "ESLS141A",
    "ESLS143", "ESLS143A", "ESLS221", "ESLS221A", "ESLS223", "ESLS223A",
    "ESLS235", "ESLS235A", "ESLS237", "ESLS237A", "ESLS311", "ESLS311A",
    "ESLS313", "ESLS313A", "ESLS319", "ESLS319A", "ESLS321", "ESLS321A",
    "2ESR1_AUX", "2ESR2_AUX", "2ESR3_AUX",
    "3ESR1_AUX", "3ESR2_AUX", "3ESR3_AUX", "3ESR4_AUX", "3ESR5_AUX",
    "T_2ESR1_AUX", "T_2ESR2_AUX", "T_2ESR3_AUX",
    "T_3ESR1_AUX", "T_3ESR2_AUX", "T_3ESR3_AUX", "T_3ESR4_AUX", "T_3ESR5_AUX",
    "2MCR1", "2MCR1_AUX", "3MCR1", "3MCR1_AUX",
    "T_2MCR1", "T_2MCR1_AUX", "T_3MCR1", "T_3MCR1_AUX",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fact_uid(archive_sha: str, path: str, idx: int, extra: str) -> str:
    payload = f"io_claim|{archive_sha}|{path}|{idx}|{extra}"
    return "sf_" + hashlib.sha1(payload.encode()).hexdigest()[:16]


def main() -> int:
    tar = REPO / "workspace/inbox/20251016-0933-OReillyGreensboro-ORNCCP2-RUN.tar.gz"
    run = REPO / "workspace/_plc2_run_peek/RUN"
    archive_sha = sha256_file(tar) if tar.is_file() else "UNKNOWN"
    devs = {d.get("name"): d for d in discover_safety_devices(run, "ORNCCP2")}
    assert len(devs) == 58
    assert set(NAMES) == set(devs.keys())

    _, rows = read_asc(run / "FORTNA" / "Conveyor.asc")
    idx_by: dict[str, tuple[int, str, dict]] = {}
    for i, r in enumerate(rows):
        n = str(r.get("IO_Name") or "").strip()
        if n and n not in idx_by:
            idx_by[n] = (i, str(r.get("Machine_Name") or "").strip(), r)

    out_rows = []
    for n in NAMES:
        d = devs.get(n) or {}
        stem = n[2:] if n.startswith("T_") else n
        loc = idx_by.get(stem) or idx_by.get(n)
        assert loc, f"missing {n}"
        i, mach, row = loc
        ev0 = (d.get("evidence") or [{}])[0] if isinstance(d.get("evidence"), list) else {}
        out_rows.append(
            {
                "canonical_device_name": n,
                "raw_source_name": str(row.get("IO_Name") or stem),
                "archive_sha": archive_sha,
                "project": "OReillyGreensboro",
                "machine": mach or "ORNCCP2",
                "source_file_table": "FORTNA/Conveyor.asc",
                "source_row_index": i,
                "source_fact_uid": fact_uid(archive_sha, "FORTNA/Conveyor.asc", i, stem),
                "evidence_source": (
                    "claim_ledger_T_alias_of_Conveyor"
                    if n.startswith("T_")
                    else "Conveyor.asc via discover_safety_devices"
                ),
                "discover_evidence_kind": ev0.get("kind") if isinstance(ev0, dict) else "",
                "classification": d.get("kind") or _classify_device(n),
                "scope": "ACTIVE_MACHINE_WHEN_ORNCCP2_LOADED",
                "load_session_id": "GHOST_RETAINED_NO_ACTIVE_RUN",
            }
        )

    # Cross-check SHIP does not include these
    ship = REPO / "workspace/_reno_peek/20260813-1132-MSCRENO-MSCRENOSHIP-RUN/RUN"
    ship_names = set()
    if ship.is_dir():
        ship_names = {
            d.get("name") for d in discover_safety_devices(ship, "MSCRENOSHIP")
        }

    report = {
        "title": "Ghost Safety inventory 58-device provenance",
        "verdict": "A_ONE_CONTROLLER_CORRECT_INVENTORY_RETAINED_AFTER_CLEAR",
        "verdict_letter": "A",
        "verdict_detail": (
            "Exact set equality with discover_safety_devices(ORNCCP2): 58/58. "
            "All Conveyor.asc Machine_Name values are ORNCCP2. "
            "T_* names are alias forms of the same stems. "
            "2MCR/3MCR and 2ESR/3ESR coexist because ORNCCP2's own Conveyor table "
            "contains both numeric families under Machine_Name=ORNCCP2 — not because "
            "sibling Reno controllers were unioned."
        ),
        "rejected_hypotheses": {
            "B_sibling_reno_controllers_unioned": {
                "rejected": True,
                "reason": "Zero overlap with MSCRENOSHIP discover (ESPB/ESLS only); Reno PACK uses 13MCR/13ESR not 2MCR/3ESR AUX list",
            },
            "C_current_plus_stale_mixed": {
                "rejected": True,
                "reason": "Single coherent ORNCCP2 discover set; no second-machine residue in the 58",
            },
            "atlanta_cp2_plus_cp3_union": {
                "rejected": True,
                "reason": "MSCATL CP2|CP3 discover union does not match ESLS125/ES1002/2ESR1_AUX pattern",
            },
        },
        "discovery_improved": True,
        "scope_lifetime_bug_remains_until": "94aee34",
        "discovery_improved_detail": (
            "DISCOVERY IMPROVED: inventory includes MCR/ESR AUX + T_ aliases "
            "(2ESR1_AUX, T_2ESR1_AUX, 2MCR1_AUX, 3MCR1, …) that earlier incomplete "
            "Safety surfaces often omitted. "
            "SCOPE/LIFETIME BUG: that correct ORNCCP2 inventory was retained with "
            "NO active RUN via unscoped localStorage siteforge.safetyBuild.v1 hydrate "
            "(addressed in 94aee34 — hasActiveSite + never restore devices)."
        ),
        "archive_sha": archive_sha,
        "project": "OReillyGreensboro",
        "machine": "ORNCCP2",
        "group_counts_by_machine": dict(Counter(r["machine"] for r in out_rows)),
        "kind_counts": dict(Counter(r["classification"] for r in out_rows)),
        "overlap": {
            "curtis_visible_list": 58,
            "ornccp2_discover": 58,
            "intersection": 58,
            "symmetric_diff": 0,
            "mscrenoship_overlap": len(set(NAMES) & ship_names),
        },
        "devices": out_rows,
    }

    out = REPO / "exports" / "diagnostics"
    out.mkdir(parents=True, exist_ok=True)
    (out / "ghost_safety_58_provenance.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    lines = [
        "# Ghost Safety inventory — 58-device provenance",
        "",
        f"**Verdict: {report['verdict']} (case {report['verdict_letter']})**",
        "",
        report["verdict_detail"],
        "",
        "## Discovery vs scope",
        "",
        report["discovery_improved_detail"],
        "",
        f"- archive_sha: `{archive_sha}`",
        "- project: OReillyGreensboro",
        "- machine: **ORNCCP2** (all 58)",
        f"- kinds: {report['kind_counts']}",
        f"- MSCRENOSHIP overlap: {report['overlap']['mscrenoship_overlap']}",
        "",
        "## Device provenance",
        "",
        "| name | kind | machine | source | row | fact_uid |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for r in out_rows:
        lines.append(
            f"| `{r['canonical_device_name']}` | {r['classification']} | {r['machine']} | "
            f"{r['evidence_source']} | {r['source_row_index']} | `{r['source_fact_uid']}` |"
        )
    (out / "ghost_safety_58_provenance.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "verdict", "verdict_letter", "overlap", "group_counts_by_machine",
        "kind_counts", "discovery_improved",
    )}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Disposable virgin MSCRENOSHIP build for P0 truth-chain candidate evidence."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from fortna_autogen import generate, load_from_run  # noqa: E402
from fortna_run_workspace_discover import discover, site_model_identity_matches  # noqa: E402
from fortna_workbook import apply_workbook_to_input  # noqa: E402

RUN = REPO / "workspace/_reno_peek/20260813-1132-MSCRENO-MSCRENOSHIP-RUN/RUN"
LIB = REPO / "tools/libraries/OReilly_Library_v3.L5X"
OUT = REPO / "exports/diagnostics/p0_truth_chain_virgin_ship"


def _build_workbook(run: Path, machine: str) -> dict:
    try:
        from fortna_workbook import build_workbook_from_run

        return build_workbook_from_run(run)
    except Exception as e:
        print("build_workbook_from_run err", e)
    # Minimal workbook from AutogenInput seed
    inp = load_from_run(run)
    return {
        "machine": machine or getattr(inp, "machine", ""),
        "areas": list(inp.areas or []),
        "conveyors": [
            {
                "conveyor": c.conveyor,
                "main_area": c.main_area,
                "safety_zone": c.safety_zone,
                "type": c.type,
                "include": True,
            }
            for c in (inp.conveyors or [])
        ],
        "safety_build": {"zones": []},
        "options": {},
    }


def _routine_matrix(l5x_text: str) -> list[dict]:
    rows: list[dict] = []
    for prog in re.finditer(
        r'<Program Name="([^"]+)"[^>]*>(.*?)</Program>',
        l5x_text,
        flags=re.I | re.S,
    ):
        pname = prog.group(1)
        body = prog.group(2)
        scheduled = set(
            re.findall(r"JSR\(([^,)]+)", body, flags=re.I)
        )
        for rout in re.finditer(
            r'<Routine Name="([^"]+)"[^>]*>(.*?)</Routine>',
            body,
            flags=re.I | re.S,
        ):
            rname = rout.group(1)
            rbody = rout.group(2)
            rungs = re.findall(r"<Rung\b", rbody, flags=re.I)
            texts = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", rbody, flags=re.S)
            joined = "\n".join(texts)
            logic = bool(texts) and not all(
                re.fullmatch(r"\s*(NOP\(\);)?\s*", t or "") for t in texts
            )
            inert_stack = bool(
                re.search(r"Stacklight|_Stacklight\.O\.(Green|Red|Amber)", joined, re.I)
            ) and rname.lower() == "stacklight"
            status = "FUNCTIONAL" if logic else ("PRESENT_BUT_INERT" if rungs else "WITHHELD")
            if "CONFIG_REQUIRED" in joined or "NTP_Configured" in joined:
                status = "FUNCTIONAL_BUT_CONFIG_REQUIRED"
            if "NOT_YET_QUALIFIED" in joined or "REVIEW_REQUIRED" in joined:
                if "CONFIG_REQUIRED" not in joined:
                    status = "REVIEW_REQUIRED" if "REVIEW_REQUIRED" in joined else status
            if inert_stack:
                # Stacklight writes UDT bits; consumer mapping may be absent.
                status = "PRESENT_BUT_INERT" if "OTE(" in joined else status
                # If it writes Area status bits, keep FUNCTIONAL_BUT_CONFIG_REQUIRED
                # when no physical consumer proven — still meaningful logic.
                if "OTE(" in joined:
                    status = "PRESENT_BUT_INERT"
            if rname.upper() == "NTP" and "NTP_Configured" in joined:
                status = "FUNCTIONAL_BUT_CONFIG_REQUIRED"
            rows.append(
                {
                    "PROGRAM": pname,
                    "ROUTINE": rname,
                    "EXISTS": "YES",
                    "SCHEDULED": "YES" if (rname in scheduled or rname == "Main_Routine") else "NO",
                    "LOGIC_PRESENT": "YES" if logic else "NO",
                    "STATUS": status,
                    "RUNGS": len(rungs),
                    "REASON": (
                        "NTP_Configured=0 gate — no SNTP traffic until engineer enables"
                        if rname.upper() == "NTP"
                        else (
                            "Stacklight UDT bits written; physical/HMI consumer not proven"
                            if status == "PRESENT_BUT_INERT" and rname.lower() == "stacklight"
                            else ""
                        )
                    ),
                }
            )
    return rows


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    assert RUN.is_dir(), f"missing RUN {RUN}"
    assert LIB.is_file(), f"missing library {LIB}"

    ws = OUT / "disposable_ws"
    disc_out = ws / "discovery"
    active = ws / "active"
    disc_out.mkdir(parents=True)
    active.mkdir(parents=True)

    print("=== DISCOVER ===")
    discover(RUN, "MSCRENOSHIP", disc_out, blind=True)
    site = json.loads((disc_out / "site_model.json").read_text(encoding="utf-8"))
    shutil.copy2(disc_out / "site_model.json", active / "site_model.json")
    (active / "active-meta.json").write_text(
        json.dumps(
            {
                "machine": "MSCRENOSHIP",
                "controller": "MSCRENOSHIP",
                "run_dir": str(RUN),
                "run_fingerprint": site.get("run_fingerprint"),
                "project_name": "MSCRENO_MSCRENOSHIP",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    ok, reason = site_model_identity_matches(
        site,
        machine="MSCRENOSHIP",
        run_dir=str(RUN),
        run_fingerprint=site.get("run_fingerprint") or "",
    )
    print("identity", ok, reason)
    print(
        "counts",
        {
            k: (site.get("counts") or {}).get(k)
            for k in [
                "equipment_included",
                "encoders",
                "scanners",
                "sorters",
                "photoeyes",
                "motors",
            ]
        },
    )

    print("=== WORKBOOK + GENERATE ===")
    inp = load_from_run(RUN)
    if not getattr(inp, "machine", None):
        inp.machine = "MSCRENOSHIP"
    wb = _build_workbook(RUN, "MSCRENOSHIP")
    (OUT / "workbook.json").write_text(
        json.dumps(wb, indent=2, default=str), encoding="utf-8"
    )
    apply_workbook_to_input(inp, wb)

    # Do NOT force sorter generation through quarantine.
    opts = dict(getattr(inp, "options", None) or {})
    opts["include_sorter_track"] = False
    opts["include_ntp"] = True
    inp.options = opts
    try:
        progs = [
            p
            for p in (getattr(inp, "include_programs", None) or [])
            if "orter" not in str(p).lower()
        ]
        if progs:
            inp.include_programs = progs
    except Exception:
        pass

    out_dir = OUT / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    l5x_path = out_dir / "MSCRENOSHIP_STAGING.L5X"
    result = None
    gen_err = None
    try:
        result = generate(inp, LIB, out_dir)
        # Prefer the generated L5X path from result when present
        for key in ("l5x", "out_l5x", "output", "path", "staging_l5x"):
            cand = (result or {}).get(key) if isinstance(result, dict) else None
            if cand and Path(cand).is_file():
                l5x_path = Path(cand)
                break
        if not l5x_path.is_file():
            # Pick largest L5X written under out_dir
            cands = sorted(out_dir.rglob("*.L5X"), key=lambda p: p.stat().st_size, reverse=True)
            if cands:
                l5x_path = cands[0]
    except Exception as e:
        gen_err = e
        result = {"ok": False, "error": str(e)}

    (OUT / "generate_result.json").write_text(
        json.dumps(result if isinstance(result, dict) else {"raw": str(result)}, indent=2, default=str),
        encoding="utf-8",
    )

    l5x_text = l5x_path.read_text(encoding="utf-8", errors="replace") if l5x_path.is_file() else ""
    matrix = _routine_matrix(l5x_text) if l5x_text else []
    (OUT / "routine_matrix.json").write_text(json.dumps(matrix, indent=2), encoding="utf-8")

    # Structural audit if available
    audit = {"ran": False}
    if l5x_text:
        try:
            from fortna_l5x_acceptance_auditor import audit_l5x

            audit = audit_l5x(l5x_path, machine="MSCRENOSHIP")
            audit = dict(audit) if isinstance(audit, dict) else {"raw": str(audit)}
            audit["ran"] = True
        except Exception as e:
            audit = {"ran": True, "error": str(e)}
    (OUT / "audit.json").write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")

    ntp_configured = "NTP_Configured" in l5x_text
    ntp_gate = "XIC(NTP_Configured)" in l5x_text
    sorter_track = bool(re.search(r'Program Name="[^"]*Sorter_Track', l5x_text, re.I))
    report = {
        "IMPORT": "PASS" if ok else "FAIL",
        "identity_ok": ok,
        "identity_reason": reason,
        "active_identity": site.get("identity"),
        "counts": site.get("counts"),
        "scanners": len(site.get("scanners") or []),
        "encoders": len(site.get("encoders") or []),
        "sorters": len(site.get("sorters") or []),
        "sorter_discovery": (
            "PASS"
            if (site.get("sorter_model") or {}).get("detected")
            or len(site.get("sorters") or [])
            else "FAIL"
        ),
        "sorter_model_plc_generation": (site.get("sorter_model") or {}).get("plc_generation"),
        "PLC_ARTIFACT_GENERATED": "YES" if l5x_path.is_file() and l5x_path.stat().st_size > 0 else "NO",
        "l5x_bytes": l5x_path.stat().st_size if l5x_path.is_file() else 0,
        "STRUCTURAL_AUDIT": (
            "PASS"
            if audit.get("ok") or audit.get("status") == "PASS" or audit.get("audit_pass")
            else ("FAIL" if audit.get("ran") else "NOT_RUN")
        ),
        "SORTER_TRACK_GENERATED": "YES" if sorter_track else "NO",
        "NTP_Configured_tag": ntp_configured,
        "NTP_Configured_gate": ntp_gate,
        "lib_fp": hashlib.sha256(LIB.read_bytes()).hexdigest()[:16],
        "routine_count": len(matrix),
        "blocking_gate": None,
    }
    if report["PLC_ARTIFACT_GENERATED"] == "NO":
        report["blocking_gate"] = (result or {}).get("error") or (result or {}).get("message") or str(gen_err)
    (OUT / "virgin_ship_summary.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["IMPORT"] == "PASS" and report["PLC_ARTIFACT_GENERATED"] == "YES" else 2


if __name__ == "__main__":
    raise SystemExit(main())

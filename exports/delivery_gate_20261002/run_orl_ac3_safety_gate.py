#!/usr/bin/env python3
"""ORL_AC3 Safety regression gate — third permanent qualification fixture.

Validates that the engineer-assigned Safety path still yields a populated ES
program (Main_Routine + Safe_Logic + Safe_PI) on the frozen delivery L5X.

Heavy re-build (optional): python exports/delivery_gate_20261002/run_orl_safety_repro.py

This gate does not modify compiler behavior. It fails when Safety shells go blank.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))
os.chdir(REPO)

OUT = REPO / "exports" / "delivery_gate_20261002"
CURRENT = REPO / "exports" / "current"


def _latest_orl_l5x() -> Path:
    pinned = CURRENT / "ORL_AC3_2026_10_02_2328.L5X"
    if pinned.is_file():
        return pinned
    cands = sorted(
        CURRENT.glob("ORL_AC3_*.L5X"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return cands[0] if cands else pinned


L5X = _latest_orl_l5x()
ISSUES = CURRENT / "ORL_AC3_BUILD_ISSUES.json"
EXPECTED_ZONE = "Area_Test1_ESZone1"
EXPECTED_MEMBERS = {
    "1ES",
    "1ES1",
    "ESLS101",
    "ESLS103",
    "1ESR1",
    "1ESR2",
    "1MCR1",
    "3MCR1",
}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest().lower()


def git_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(REPO), text=True)
            .strip()
        )
    except Exception:
        return ""


def inspect_es(l5x: Path) -> dict:
    text = l5x.read_text(encoding="utf-8", errors="replace")
    es = re.search(r'<Program Name="ES"[^>]*>(.*?)</Program>', text, re.S)
    if not es:
        return {"error": "NO_ES_PROGRAM", "detail": {}}
    body = es.group(1)
    routines = re.findall(r'<Routine Name="([^"]+)"', body)
    detail: dict = {}
    for rn in routines:
        m = re.search(
            rf'<Routine Name="{re.escape(rn)}"[^>]*>.*?<RLLContent>(.*?)</RLLContent>',
            body,
            re.S,
        )
        if not m:
            detail[rn] = {"populated": False}
            continue
        rungs = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", m.group(1))
        nonempty = [r for r in rungs if r.strip() and r.strip() != "NOP();"]
        detail[rn] = {
            "rungs": len(rungs),
            "non_nop": len(nonempty),
            "populated": len(nonempty) > 0,
            "sample": (nonempty or rungs)[:4],
        }
    return {"routines": routines, "detail": detail}


def blank_operand_hits(text: str) -> list[str]:
    pat = re.compile(
        r"\b(?:XIC|XIO|OTE|OTL|OTU)\s*\(\s*(?:\)|\?[,)]|,\s*[,)]|\"\"|''|_unnamed_)",
        re.I,
    )
    return [m.group(0)[:80] for m in pat.finditer(text)][:20]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    l5x = _latest_orl_l5x()
    summary: dict = {
        "phase": "ORL_AC3_SAFETY_REGRESSION",
        "git_sha": git_sha(),
        "repo": str(REPO),
        "l5x": str(l5x) if l5x.is_file() else "",
        "expected_zone": EXPECTED_ZONE,
    }
    gates: dict = {}

    if not l5x.is_file():
        # Rebuild via the Safety repro runner (does not change compiler behavior).
        repro = OUT / "run_orl_safety_repro.py"
        summary["rebuild_attempted"] = True
        summary["rebuild_script"] = str(repro)
        if repro.is_file():
            rc = subprocess.call([sys.executable, str(repro)], cwd=str(REPO))
            summary["rebuild_exit"] = rc
            l5x = _latest_orl_l5x()
            summary["l5x"] = str(l5x) if l5x.is_file() else ""
        if not l5x.is_file():
            summary["orl_ac3_safety_pass"] = False
            summary["error"] = "ORL_AC3 L5X missing under exports/current after rebuild attempt"
            (OUT / "orl_ac3_safety_summary.json").write_text(
                json.dumps(summary, indent=2), encoding="utf-8"
            )
            print("ORL_AC3 FAIL missing L5X")
            return 1

    text = l5x.read_text(encoding="utf-8", errors="replace")
    summary["l5x_sha256"] = sha256_file(l5x)
    summary["l5x_bytes"] = l5x.stat().st_size

    es = inspect_es(l5x)
    summary["es_inspect"] = es
    detail = es.get("detail") or {}
    sl_name = f"{EXPECTED_ZONE}_Safe_Logic"
    sp_name = f"{EXPECTED_ZONE}_Safe_PI"
    main_ok = bool(detail.get("Main_Routine", {}).get("populated"))
    sl_ok = bool(detail.get(sl_name, {}).get("populated"))
    sp_ok = bool(detail.get(sp_name, {}).get("populated"))
    members_ok = all(m in text for m in ("ESLS101", "ESLS103", "1ES", "1ES1"))

    gates["L5X_present"] = {"pass": True, "path": str(l5x.resolve())}
    gates["Safety"] = {
        "pass": main_ok and sl_ok and sp_ok and members_ok,
        "main_populated": main_ok,
        "safe_logic_populated": sl_ok,
        "safe_pi_populated": sp_ok,
        "members_present": members_ok,
        "zone": EXPECTED_ZONE,
        "expected_members": sorted(EXPECTED_MEMBERS),
    }

    blanks = blank_operand_hits(text)
    gates["no_blank_operands"] = {"pass": not blanks, "hits": blanks}

    issues_ok = False
    build_status = None
    if ISSUES.is_file():
        try:
            issues = json.loads(ISSUES.read_text(encoding="utf-8"))
            build_status = issues.get("BUILD STATUS") or issues.get("build_status")
            issues_ok = bool(build_status)
        except Exception as exc:  # noqa: BLE001
            gates["BUILD_ISSUES"] = {"pass": False, "error": str(exc)}
    gates["BUILD_ISSUES"] = {
        "pass": issues_ok,
        "build_status": build_status,
        "path": str(ISSUES) if ISSUES.is_file() else "",
    }

    # Foreign MSCRENOPICK residue must not dominate ORL (light check)
    foreign = {
        "MSCRENOPICK": len(re.findall("MSCRENOPICK", text)),
        "TFCP1_ESZone1": len(re.findall("TFCP1_ESZone1", text)),
    }
    gates["no_foreign_safety_zones"] = {
        "pass": foreign["MSCRENOPICK"] == 0 and foreign["TFCP1_ESZone1"] == 0,
        "counts": foreign,
    }

    summary["gates"] = gates
    summary["ORL_AC3"] = {
        "site": "ORL_AC3",
        "Safety": "PASS" if gates["Safety"]["pass"] else "FAIL",
        "ES_Main_Routine_populated": "YES" if main_ok else "NO",
        "Safe_Logic_populated": "YES" if sl_ok else "NO",
        "Safe_PI_populated": "YES" if sp_ok else "NO",
        "L5X_present": "YES",
        "BUILD_ISSUES_explanations": "PASS" if issues_ok else "FAIL",
        "no_blank_operands": "PASS" if gates["no_blank_operands"]["pass"] else "FAIL",
        "no_foreign_safety_zones": "PASS"
        if gates["no_foreign_safety_zones"]["pass"]
        else "FAIL",
        "L5X_absolute_path": str(l5x.resolve()),
    }
    summary["orl_ac3_safety_pass"] = all(
        summary["ORL_AC3"][k] in ("PASS", "YES")
        for k in (
            "Safety",
            "ES_Main_Routine_populated",
            "Safe_Logic_populated",
            "Safe_PI_populated",
            "L5X_present",
            "BUILD_ISSUES_explanations",
            "no_blank_operands",
            "no_foreign_safety_zones",
        )
    )

    (OUT / "orl_ac3_safety_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (OUT / "orl_ac3_es_inspect.json").write_text(json.dumps(es, indent=2), encoding="utf-8")
    print("ORL_AC3", summary["orl_ac3_safety_pass"], summary["ORL_AC3"])
    return 0 if summary["orl_ac3_safety_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

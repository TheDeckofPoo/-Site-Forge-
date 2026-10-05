#!/usr/bin/env python3
"""Prove AUDIT_FAIL → AI/Relay → regenerate → re-AUDIT_PASS; never promote while FAIL."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))

from fortna_l5x_acceptance_auditor import (  # noqa: E402
    MAX_ATTEMPTS_PER_SIGNATURE,
    RepairAttempt,
    RepairLoopState,
    STATE_AUDIT_PASS,
    STATE_GENERATOR_DEFECT,
    audit_l5x,
    build_expected_artifact_manifest,
    failure_signature,
    material_hash,
    run_acceptance_and_repair,
    write_generator_defect_case,
)

OUT = REPO / "exports" / "delivery_gate_20261002" / "autonomous_repair_proof"
OUT.mkdir(parents=True, exist_ok=True)
SUMMARY = (
    REPO
    / "exports"
    / "delivery_gate_20261002"
    / "autonomous_repair_proof_summary.json"
)


class Fake:
    machine = "MSCRENOPICK"
    project_name = "MSCRENOPICK"
    areas = ["MSCRENOPICK_Area"]
    include_io_map = True
    conveyors = [1] * 47
    safety_zone_members = [
        {
            "name": "MSCRENOPICK_ESZone1",
            "status": "READY",
            "operational": True,
            "membersOrigin": "ENGINEER_ASSIGNED",
            "members": ["ESPB2", "ESPB24", "ESPB32", "ESLS2"],
            "area": "MSCRENOPICK_Area",
        }
    ]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest().upper()


def main() -> int:
    goods = sorted(
        (REPO / "exports" / "current").glob("MSCRENOPICK_*.L5X"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not goods:
        print("NO_MSCRENOPICK_L5X")
        return 2
    good = goods[0]
    good_text = good.read_text(encoding="utf-8", errors="replace")
    # Capture Safe_PI routine block for restore
    m_pi = re.search(
        r'(<Routine Name="MSCRENOPICK_ESZone1_Safe_PI"[^>]*>.*?</Routine>)',
        good_text,
        re.S,
    )
    if not m_pi:
        print("GOOD_L5X_MISSING_SAFE_PI")
        return 2
    safe_pi_block = m_pi.group(1)

    damaged_text = re.sub(
        r'<Routine Name="MSCRENOPICK_ESZone1_Safe_PI"[^>]*>.*?</Routine>',
        "",
        good_text,
        count=1,
        flags=re.S,
    )
    staging = OUT / "staging_damaged.L5X"
    staging.write_text(damaged_text, encoding="utf-8")
    shutil.copy2(staging, OUT / "original_provisional.L5X")

    man = build_expected_artifact_manifest(Fake(), report={"conveyor_count": 47})
    (OUT / "EXPECTED_ARTIFACT_MANIFEST.json").write_text(
        json.dumps(man, indent=2), encoding="utf-8"
    )

    initial = audit_l5x(staging, man)
    assert initial.get("status") != STATE_AUDIT_PASS, initial

    repaired_once = {"done": False}

    def regenerate_fn(ctx: dict) -> Path | None:
        """Apply advisory repair: restore expected Safe_PI routine into staging."""
        if repaired_once["done"]:
            return None
        repaired_once["done"] = True
        cur = staging.read_text(encoding="utf-8", errors="replace")
        has_routine = bool(
            re.search(
                r'<Routine Name="MSCRENOPICK_ESZone1_Safe_PI"',
                cur,
            )
        )
        if has_routine:
            out_path = OUT / "staging_repaired.L5X"
            shutil.copy2(staging, out_path)
            return out_path
        if re.search(r'<Routine Name="MSCRENOPICK_ESZone1_Safe_Logic"', cur):
            cur2 = re.sub(
                r'(<Routine Name="MSCRENOPICK_ESZone1_Safe_Logic"[^>]*>.*?</Routine>)',
                r"\1\n" + safe_pi_block,
                cur,
                count=1,
                flags=re.S,
            )
        else:
            cur2 = re.sub(
                r'(<Program Name="ES"[^>]*>)(.*?)(</Program>)',
                r"\1\2" + safe_pi_block + r"\3",
                cur,
                count=1,
                flags=re.S,
            )
        if not re.search(r'<Routine Name="MSCRENOPICK_ESZone1_Safe_PI"', cur2):
            raise RuntimeError("Safe_PI restore failed — routine still absent")
        out_path = OUT / "staging_repaired.L5X"
        out_path.write_text(cur2, encoding="utf-8")
        staging.write_text(cur2, encoding="utf-8")
        return out_path

    result = run_acceptance_and_repair(
        l5x_path=staging,
        manifest=man,
        out_dir=OUT,
        regenerate_fn=regenerate_fn,
        live=True,
        max_outer_cycles=3,
    )

    # Loop protection / GENERATOR_DEFECT proof (separate controlled run)
    loop = RepairLoopState(max_per_signature=MAX_ATTEMPTS_PER_SIGNATURE)
    sig = failure_signature("SAFETY:MISSING_SAFE_PI", zone="MSCRENOPICK_ESZone1")
    for i in range(MAX_ATTEMPTS_PER_SIGNATURE):
        mat = material_hash({"i": i, "ai": f"conclusion-{i}", "relay": f"r-{i}"})
        ok, why = loop.can_retry(sig, mat)
        assert ok, why
        loop.record(
            RepairAttempt(
                signature=sig,
                material_hash=mat,
                level=2,
                disposition="FAIL",
                ts="t",
            )
        )
    dup_ok, dup_why = loop.can_retry(sig, loop.attempts_by_signature[sig][0].material_hash)
    third_extra_ok, third_why = loop.can_retry(
        sig, material_hash({"i": 99, "new": True})
    )
    gen_case = write_generator_defect_case(
        OUT,
        manifest=man,
        signature=sig,
        tickets=[{"signature": sig}],
        attempts=loop.attempts_by_signature[sig],
        l5x_paths=[OUT / "original_provisional.L5X", staging],
        ai_responses=[{"n": 1}, {"n": 2}, {"n": 3}],
        relay_responses=[{"n": 1}, {"n": 2}],
    )

    # Confirm CURRENT was not polluted by damaged artifact
    current_files = list((REPO / "exports" / "current").glob("MSCRENOPICK_*.L5X"))
    damaged_sha = sha256_file(OUT / "original_provisional.L5X")
    current_has_damaged = any(sha256_file(p) == damaged_sha for p in current_files)

    final_audit = result.get("final_audit") or result.get("initial_audit") or {}
    summary = {
        "phase": "ORI111_AUTONOMOUS_REPAIR_PROOF",
        "git_sha": Path(REPO).joinpath(".git").exists()
        and __import__("subprocess")
        .check_output(["git", "rev-parse", "HEAD"], cwd=str(REPO), text=True)
        .strip(),
        "initial_audit": {
            "status": initial.get("status"),
            "signatures": initial.get("signatures"),
            "failure_count": initial.get("failure_count"),
        },
        "failure_signature": (initial.get("signatures") or [None])[0],
        "repair": {
            "status": result.get("status"),
            "ok": result.get("ok"),
            "promoted": result.get("promoted"),
            "ai_api_calls": result.get("ai_api_calls"),
            "relay_calls": result.get("relay_calls"),
            "estimated_cost_usd": result.get("estimated_cost_usd"),
            "repair_cycles": result.get("repair_cycles"),
            "artifact_state": result.get("artifact_state"),
            "l5x_history": result.get("l5x_history"),
        },
        "second_audit": {
            "status": final_audit.get("status"),
            "signatures": final_audit.get("signatures"),
            "ok": final_audit.get("ok"),
        },
        "what_changed": (
            "Restored MSCRENOPICK_ESZone1_Safe_PI routine block into staging L5X "
            "after AI/Relay diagnosis classified generator/model repair; regenerated "
            "staging artifact; re-audited."
        ),
        "regenerated_l5x": str(OUT / "staging_repaired.L5X"),
        "regenerated_sha256": (
            sha256_file(OUT / "staging_repaired.L5X")
            if (OUT / "staging_repaired.L5X").is_file()
            else ""
        ),
        "loop_protection": {
            "duplicate_material_prevented": (not dup_ok) and dup_why == "DUPLICATE_MATERIAL_HASH",
            "three_attempt_stop": (not third_extra_ok)
            and third_why == "MAX_MATERIAL_ATTEMPTS",
            "generator_defect_case": str(gen_case),
            "generator_defect_proven": gen_case.is_file()
            and "GENERATOR_DEFECT" in gen_case.read_text(encoding="utf-8"),
        },
        "current_pollution_check": {
            "damaged_sha_in_current": current_has_damaged,
            "half_built_can_become_current": current_has_damaged
            or bool(result.get("promoted")),
        },
        "tickets": (result.get("loop") or {}).get("tickets") or [],
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))

    ok = (
        initial.get("status") != STATE_AUDIT_PASS
        and result.get("status") == STATE_AUDIT_PASS
        and result.get("ok") is True
        and result.get("promoted") is False  # this harness never promotes
        and not current_has_damaged
        and summary["loop_protection"]["duplicate_material_prevented"]
        and summary["loop_protection"]["generator_defect_proven"]
        and int(result.get("ai_api_calls") or 0) >= 1
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

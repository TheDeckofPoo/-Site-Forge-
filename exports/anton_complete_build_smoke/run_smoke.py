#!/usr/bin/env python3
"""ANTON MSCRENOPICK complete-build closeout smoke (Stage A/B + TFCP1/ORFPCP6)."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))

from fortna_autogen import (  # noqa: E402
    generate,
    load_from_run,
    resolve_production_library,
    validate_bit_writers_scoped,
)

OUT = Path(__file__).resolve().parent
LIB = resolve_production_library(None)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def analyze_l5x(l5x_path: Path) -> dict:
    text = l5x_path.read_text(encoding="utf-8", errors="replace")
    bw = validate_bit_writers_scoped(text)
    return {
        "fast_conv_calls": len(re.findall(r"\bFast_Conv\(", text)),
        "fast_conv_withheld_comments": len(
            re.findall(r"Fast_Conv withheld", text, flags=re.I)
        ),
        "size": l5x_path.stat().st_size,
        "sha256": sha256(l5x_path),
        "bit_writers": {
            "controller_undeclared": len(
                bw.get("undeclared_controller")
                or bw.get("invalid_bit_writer_undeclared_controller")
                or []
            ),
            "program_undeclared": len(
                bw.get("undeclared_program")
                or bw.get("invalid_bit_writer_undeclared_program")
                or []
            ),
            "aoi_undeclared": len(
                bw.get("undeclared_aoi")
                or bw.get("invalid_bit_writer_undeclared_aoi")
                or []
            ),
            "udt_root": len(
                bw.get("udt_root_bit_writers") or bw.get("invalid_udt_root_otes") or []
            ),
            "no_member": len(
                bw.get("nonexistent_members")
                or bw.get("invalid_bit_writer_no_member")
                or []
            ),
            "non_bool": len(
                bw.get("non_bool_bit_targets")
                or bw.get("invalid_bit_writer_non_bool")
                or []
            ),
            "raw_keys": sorted(bw.keys())[:40],
        },
        "safe_pi": len(re.findall(r"\bSafe_PI\(|\bES_PI20\(", text)),
        "safe_logic": len(re.findall(r"\bSafe_Logic\(|\bES_SIL1", text)),
    }


def find_run(*cands: str) -> Path | None:
    for c in cands:
        p = REPO / c
        if (p / "project.cfg").is_file():
            return p
        if (p / "RUN" / "project.cfg").is_file():
            return p / "RUN"
    return None


def smoke_site(label, run, machine=None, safety_zone_members=None, stage="A"):
    site_out = OUT / label / stage
    site_out.mkdir(parents=True, exist_ok=True)
    result = {
        "site": label,
        "stage": stage,
        "run": str(run),
        "crash": False,
        "generate_ok": False,
        "error": None,
    }
    try:
        inp = load_from_run(run)
        # Match CLI default: generic System program (RUN EIP + library Slow_Sys).
        inp.include_sys = True
        if machine:
            inp.machine = machine
        if safety_zone_members is not None:
            inp.safety_zone_members = list(safety_zone_members)
            sb = dict(getattr(inp, "safety_build", None) or {})
            sb["zones"] = list(safety_zone_members)
            inp.safety_build = sb
            znames = [
                str(z.get("name") or "")
                for z in safety_zone_members
                if isinstance(z, dict)
            ]
            inp.safety_zones = [n for n in znames if n]
            for c in inp.conveyors or []:
                if znames:
                    c.safety_zone = znames[0]
        outer = generate(inp, LIB, site_out)
        rep = outer.get("report") if isinstance(outer.get("report"), dict) else outer
        result["generate_ok"] = bool(rep.get("ok", True)) and not rep.get(
            "build_failed"
        )
        # Loud-stop codes on outer result still count as non-crash generate path
        if outer.get("error") and not result["error"]:
            result["outer_error"] = outer.get("error")
        result["error"] = rep.get("error") or outer.get("error")
        if rep.get("build_failed") or (
            str(rep.get("error") or "").startswith("PACK_TEMPLATE")
        ):
            result["generate_ok"] = False
            result["loud_stop"] = True
        result["writer_coverage"] = rep.get("writer_coverage")
        result["function_disclosure"] = rep.get("function_disclosure")
        result["fast_conv_status"] = rep.get("fast_conv_status")
        result["fast_conv_artifact_count"] = rep.get("fast_conv_artifact_count")
        result["conv_pi_status"] = rep.get("conv_pi_status")
        result["slow_flt_status"] = rep.get("slow_flt_status")
        result["safety_zone_candidate"] = rep.get("safety_zone_candidate")
        result["safety_candidate_produced"] = rep.get("safety_candidate_produced")
        result["safety_candidate_membership_count"] = rep.get(
            "safety_candidate_membership_count"
        )
        result["safety_engineer_confirmation_required"] = rep.get(
            "safety_engineer_confirmation_required"
        )
        result["generic_transport_area"] = rep.get("generic_transport_area")
        result["m120_ownership"] = rep.get("m120_ownership") or (
            rep.get("motor_ownership") or {}
        ).get("M120")
        result["motor_ownership"] = rep.get("motor_ownership")
        result["stage0"] = rep.get("stage0") or rep.get("evidence_entry") or {}
        s0 = result["stage0"] if isinstance(result["stage0"], dict) else {}
        result["claims"] = {
            "raw": s0.get("CLAIMS_CREATED") or s0.get("raw_physical_claims"),
            "resolved": s0.get("CLAIMS_RESOLVED"),
            "unresolved": s0.get("CLAIMS_UNRESOLVED"),
            "ok": s0.get("ok"),
        }
        result["programs"] = rep.get("programs")
        result["merges_emitted"] = rep.get("merges_emitted")
        result["merges_withheld_review"] = rep.get("merges_withheld_review")
        result["es_program"] = rep.get("es_program")
        result["runnability"] = rep.get("runnability")
        result["areas_summary"] = rep.get("areas_summary")
        result["conveyor_count"] = rep.get("conveyor_count")
        result["plc_fast"] = bool(rep.get("plc_fast"))
        result["sys"] = "Sys" in (rep.get("programs") or [])
        result["system"] = "System" in (rep.get("programs") or [])
        result["config_program_status"] = rep.get("config_program_status")
        result["foreign_generated"] = rep.get("foreign_generated") or []
        result["io_source_conservation_ok"] = rep.get("io_source_conservation_ok")
        result["invalid_udt_root_ote_count"] = rep.get(
            "invalid_udt_root_ote_count"
        ) or len(rep.get("invalid_udt_root_otes") or [])
        result["invalid_bit_writer_undeclared_controller"] = rep.get(
            "invalid_bit_writer_undeclared_controller"
        )
        result["invalid_bit_writer_undeclared_program"] = rep.get(
            "invalid_bit_writer_undeclared_program"
        )
        result["invalid_bit_writer_undeclared_aoi"] = rep.get(
            "invalid_bit_writer_undeclared_aoi"
        )
        l5x_name = outer.get("l5x_filename") or rep.get("l5x_filename") or f"{label}.L5X"
        l5x = site_out / l5x_name
        if not l5x.is_file():
            # engineer export may place L5X in out root
            cands = [c for c in site_out.glob("*.L5X") if "Library" not in c.name]
            if not cands:
                cands = [
                    c
                    for c in Path(outer.get("out_dir") or site_out).glob("*.L5X")
                    if "Library" not in c.name
                ]
            l5x = cands[0] if cands else l5x
        result["l5x"] = l5x.name if l5x.is_file() else None
        result["l5x_sha256_outer"] = outer.get("l5x_sha256")
        if l5x.is_file():
            result["l5x_analysis"] = analyze_l5x(l5x)
            wc = rep.get("writer_coverage") or {}
            by = wc.get("by_class") or {}
            result["effective_writers"] = len(by.get("VALID_WRITER") or [])
            result["intentional_review"] = len(
                by.get("INTENTIONALLY_UNDRIVEN_REVIEW") or []
            )
            result["unsupported"] = len(by.get("UNSUPPORTED") or [])
            result["defects"] = list(by.get("DEFECT") or [])
            result["writer_sample_valid"] = list(by.get("VALID_WRITER") or [])[:15]
            all_classes = {}
            for cls, items in by.items():
                for it in items or []:
                    all_classes[str(it).upper()] = cls
            eps = [
                "M120",
                "CL17",
                "SSV105A",
                "EZSSV3",
                "EZSSV4",
                "EZSSV5",
                "EZSSV9",
                "EZSSV10",
                "EZSSV11",
                "P120C_Conv",
            ]
            result["endpoint_classes"] = {
                k: all_classes.get(k.upper(), "NOT_IN_MAPPED_OUTPUTS") for k in eps
            }
        (site_out / "stage_summary.json").write_text(
            json.dumps(result, indent=2, default=str), encoding="utf-8"
        )
        print(
            f"OK {label}/{stage} generate_ok={result['generate_ok']} "
            f"fast={result.get('fast_conv_artifact_count')} "
            f"writers={result.get('effective_writers')} "
            f"cand={result.get('safety_candidate_produced')}"
        )
    except Exception as ex:
        result["crash"] = True
        result["error"] = f"{type(ex).__name__}: {ex}"
        result["traceback"] = traceback.format_exc()
        print(f"CRASH {label}/{stage}: {result['error']}")
        (site_out / "stage_summary.json").write_text(
            json.dumps(result, indent=2, default=str), encoding="utf-8"
        )
    return result


def main() -> int:
    reno = find_run(
        "workspace/_reno_peek/20260813-1132-MSCRENO-MSCRENOPICK-RUN/RUN",
        "workspace/_reno_peek/20260813-1132-MSCRENO-MSCRENOPICK-RUN",
    )
    if not reno:
        print("MSCRENOPICK RUN missing")
        return 2
    stage_a = smoke_site(
        "MSCRENOPICK", reno, machine="MSCRENOPICK", stage="A_zero_decision"
    )
    cand = (stage_a.get("safety_zone_candidate") or {}).get("candidate") or {}
    confirmed = None
    if cand and cand.get("members"):
        confirmed = [
            {
                "name": cand["name"],
                "area": cand.get("area") or "MSCRENOPICK_Area",
                "members": list(cand["members"]),
                "conveyors": list(cand.get("conveyors") or []),
                "membersOrigin": "ENGINEER_ASSIGNED",
                "operational": True,
            }
        ]
        print(
            "Stage B confirming zone",
            confirmed[0]["name"],
            "members",
            confirmed[0]["members"],
        )
    else:
        print("NO CANDIDATE for Stage B")
    stage_b = smoke_site(
        "MSCRENOPICK",
        reno,
        machine="MSCRENOPICK",
        safety_zone_members=confirmed,
        stage="B_engineer_confirmed_safety",
    )

    tf = find_run(
        "workspace/_cross_site_peek/TFCP1/RUN",
        "workspace/_cross_site_peek/TFCP1",
        "workspace/TFCP1/RUN",
    )
    orf = find_run(
        "workspace/_cross_site_peek/ORFPCP6/RUN",
        "workspace/_cross_site_peek/ORFPCP6",
        "workspace/ORFPCP6/RUN",
        "workspace/ORFPCP6",
    )
    print("TFCP1", tf, "ORFPCP6", orf)
    tf_res = (
        smoke_site("TFCP1", tf, machine="TFCP1", stage="cross")
        if tf
        else {"crash": True, "error": "TFCP1 RUN missing"}
    )
    orf_res = (
        smoke_site("ORFPCP6", orf, machine="ORFPCP6", stage="cross")
        if orf
        else {"crash": True, "error": "ORFPCP6 RUN missing"}
    )
    summary = {
        "MSCRENOPICK_A": stage_a,
        "MSCRENOPICK_B": stage_b,
        "TFCP1": tf_res,
        "ORFPCP6": orf_res,
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print("WROTE", OUT / "summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

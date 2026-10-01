#!/usr/bin/env python3
"""MSCRENOSHIP first real Beta build — Safe Partial + routine coverage."""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "scripts"))

# Isolate PRISM during this beta build (do not mutate shared corpus).
os.environ.setdefault("FORTNA_PRISM_DISABLE", "1")

from fortna_autogen import generate, load_from_run, resolve_production_library  # noqa: E402

OUT = Path(__file__).resolve().parent
RUN = (
    REPO
    / "workspace"
    / "_reno_peek"
    / "20260813-1132-MSCRENO-MSCRENOSHIP-RUN"
    / "RUN"
)
LIB = resolve_production_library(None)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    summary: dict = {"site": "MSCRENOSHIP", "run": str(RUN)}
    if not (RUN / "project.cfg").is_file():
        summary["crash"] = True
        summary["error"] = f"MSCRENOSHIP RUN missing: {RUN}"
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(summary["error"])
        return 2
    try:
        inp = load_from_run(RUN)
        inp.include_sys = True
        inp.machine = "MSCRENOSHIP"
        # Prefer discovery overlays when available (generic — no site hacks).
        try:
            from fortna_cp4_discovery import discover_sawtooth

            disc = discover_sawtooth(RUN, "MSCRENOSHIP")
            summary["sawtooth_discovery"] = {
                "merge_count": len((disc or {}).get("merges") or []),
                "lane_count": len((disc or {}).get("lanes") or []),
                "sample": list((disc or {}).get("merges") or [])[:3],
            }
        except Exception as ex:  # noqa: BLE001
            summary["sawtooth_discovery_error"] = f"{type(ex).__name__}: {ex}"
        try:
            from fortna_cp4_discovery import discover_sawtooth
            from fortna_sorter_discovery import discover as discover_sorters

            # Best-effort discovery overlays — never invent ownership.
            disc = discover_sawtooth(RUN, "MSCRENOSHIP")
            if isinstance(disc, dict) and (disc.get("merges") or disc.get("lanes")):
                # Map discovery into sawtooth_build shape when possible.
                merges = list(disc.get("merges") or [])
                lanes = list(disc.get("lanes") or [])
                saw_b = {
                    "source": "discover_sawtooth",
                    "merges": merges,
                    "lanes": lanes,
                    "collector": (merges[0].get("collector") if merges else None),
                    "total_time_slice": (merges[0].get("totalTimeSlice") if merges else None),
                }
                # Prefer explicit SHIP_SAW identity when present.
                for m in merges:
                    name = str(m.get("name") or m.get("id") or "").upper()
                    if "SHIP_SAW" in name or name == "SHIP_SAW":
                        saw_b["name"] = m.get("name") or m.get("id")
                        saw_b["collector"] = m.get("collector") or saw_b.get("collector")
                        saw_b["total_time_slice"] = (
                            m.get("totalTimeSlice")
                            or m.get("TotalTimeSlice")
                            or saw_b.get("total_time_slice")
                        )
                        break
                inp.sawtooth_build = saw_b
                summary["sawtooth_build"] = {
                    "name": saw_b.get("name"),
                    "merge_count": len(merges),
                    "lane_count": len(lanes),
                    "collector": saw_b.get("collector"),
                    "total_time_slice": saw_b.get("total_time_slice"),
                }
            try:
                sdisc = discover_sorters(RUN, "MSCRENOSHIP")
                summary["sorter_discovery"] = {
                    "count": len(sdisc) if isinstance(sdisc, list) else (
                        len((sdisc or {}).get("sorters") or [])
                        if isinstance(sdisc, dict)
                        else 0
                    ),
                }
            except Exception as sex:  # noqa: BLE001
                summary["sorter_discovery_error"] = f"{type(sex).__name__}: {sex}"
        except Exception as ex:  # noqa: BLE001
            summary["site_model_overlay_error"] = f"{type(ex).__name__}: {ex}"

        # Default path: diagnostics under .internal/builds, promote to exports/current.
        outer = generate(inp, LIB, None)
        rep = outer.get("report") if isinstance(outer.get("report"), dict) else {}
        summary["outer_ok"] = outer.get("ok")
        summary["outer_error"] = outer.get("error")
        summary["build_status"] = rep.get("build_status") or outer.get("build_status")
        summary["build_failed"] = rep.get("build_failed")
        summary["error"] = rep.get("error") or outer.get("error")
        summary["l5x"] = outer.get("l5x") or rep.get("l5x_path")
        summary["l5x_filename"] = outer.get("l5x_filename") or rep.get("l5x_filename")
        summary["l5x_sha256"] = outer.get("l5x_sha256") or rep.get("l5x_sha256")
        summary["l5x_promoted_to_current"] = outer.get("l5x_promoted_to_current") or rep.get(
            "l5x_promoted_to_current"
        )
        summary["build_id"] = outer.get("build_id") or rep.get("build_id")
        summary["out_dir"] = outer.get("out_dir")
        summary["diagnostics_dir"] = outer.get("diagnostics_dir")
        summary["build_issues_txt"] = rep.get("build_issues_txt")
        summary["build_issues_json"] = rep.get("build_issues_json")
        summary["actionable_issue_count"] = (rep.get("build_issues") or {}).get(
            "actionable_issue_count"
        )
        summary["commissioning_ready"] = (rep.get("runnability") or {}).get(
            "COMMISSIONING_READY"
        )
        summary["symbol_closure"] = {
            "ok": (rep.get("symbol_closure") or {}).get("ok"),
            "failure_count": (rep.get("symbol_closure") or {}).get("failure_count")
            or len((rep.get("symbol_closure") or {}).get("failures") or []),
        }
        summary["rung_quarantine"] = {
            k: (rep.get("rung_quarantine") or {}).get(k)
            for k in (
                "ok",
                "blocked",
                "issue_count",
                "quarantined_rung_count",
                "fail_closed_count",
            )
        }
        summary["routine_coverage"] = {
            k: (rep.get("routine_coverage") or {}).get(k)
            for k in (
                "programs_expected",
                "programs_present",
                "routines_expected_applicable",
                "summary",
                "issue_count",
            )
        }
        summary["programs"] = rep.get("programs")
        summary["conveyor_count"] = rep.get("conveyor_count")
        summary["writer_coverage"] = {
            k: (rep.get("writer_coverage") or {}).get(k)
            for k in (
                "mapped_outputs",
                "outputs_with_valid_writers",
                "intentional_review_outputs",
                "writerless_defect_outputs",
            )
        }
        summary["merges_emitted"] = rep.get("merges_emitted")
        summary["merges_withheld_review"] = rep.get("merges_withheld_review")
        summary["es_program"] = {
            k: (rep.get("es_program") or {}).get(k)
            for k in ("status", "zones", "omitted_zones")
        }
        summary["stage0"] = {
            k: (rep.get("stage0") or {}).get(k)
            for k in (
                "CLAIMS_CREATED",
                "CLAIMS_RESOLVED",
                "CLAIMS_UNRESOLVED",
                "ok",
            )
        }
        summary["physical_io_unmapped_names"] = rep.get("physical_io_unmapped_names")
        summary["default_unassigned_operational_safety_refs"] = rep.get(
            "default_unassigned_operational_safety_refs"
        )
        summary["sawtooth_inclusion"] = rep.get("sawtooth_inclusion")
        summary["function_disclosure"] = rep.get("function_disclosure")
        # Persist slim report pointer
        (OUT / "summary.json").write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )
        # Copy key artifacts into this folder for easy handoff
        for key in ("build_issues_txt", "build_issues_json", "l5x"):
            p = summary.get(key)
            if p and Path(p).is_file():
                dest = OUT / Path(p).name
                try:
                    dest.write_bytes(Path(p).read_bytes())
                except Exception:
                    pass
        print(
            "SHIP BUILD",
            summary.get("build_status"),
            "promoted",
            summary.get("l5x_promoted_to_current"),
            "l5x",
            summary.get("l5x_filename"),
            "issues",
            summary.get("actionable_issue_count"),
        )
        return 0 if summary.get("build_status") in {"SUCCESS", "PARTIAL"} else 1
    except Exception as ex:
        summary["crash"] = True
        summary["error"] = f"{type(ex).__name__}: {ex}"
        summary["traceback"] = traceback.format_exc()
        (OUT / "summary.json").write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )
        print("CRASH", summary["error"])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

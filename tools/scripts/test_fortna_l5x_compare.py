#!/usr/bin/env python3
"""Unit tests for fortna_l5x_compare using synthetic L5X fragments."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_l5x_compare import (  # noqa: E402
    compare_inventories,
    extract_l5x,
    run_compare,
)


def _wrap_program(name: str, body: str) -> str:
    return f'<Program Name="{name}" TestEdits="false">\n{body}\n</Program>\n'


def _rung(text: str) -> str:
    return (
        "<Routine Name=\"Conv_Fast\" Type=\"RLL\"><RLLContent>"
        f"<Rung Number=\"0\" Type=\"N\"><Text><![CDATA[{text}]]></Text></Rung>"
        "</RLLContent></Routine>"
    )


def _l5x(programs: dict[str, str]) -> str:
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<RSLogix5000Content>"]
    for name, body in programs.items():
        parts.append(_wrap_program(name, body))
    parts.append("</RSLogix5000Content>")
    return "\n".join(parts)


def _write(tmp: Path, name: str, content: str) -> Path:
    p = tmp / name
    p.write_text(content, encoding="utf-8")
    return p


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        checks.append((name, bool(cond), detail))
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    print("=== fortna_l5x_compare unit tests ===")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Exact Fast_Conv match
        fc = (
            "Fast_Conv(P138_Conv_AOI.Fast,P138_Conv,ModuleB_Area,ModuleB_ESZone2,"
            "P406_Conv,PE138_P,NO_PE,P138_Conv.Type,NO_VFD,0,1,0,0,HMIColor,HMI_StatsClear)"
        )
        exact = _l5x({"ModuleB_Area_Fast": _rung(fc)})
        inv = extract_l5x(_write(tmp, "exact.L5X", exact))
        rec = inv.fast_conv.get("P138")
        check("exact Fast_Conv parsed", rec is not None)
        check("exact conveyor P138", rec.conveyor == "P138" if rec else False, repr(getattr(rec, "conveyor", None)))
        check("exact downstream P406", rec.downstream == "P406" if rec else False)
        check("exact area ModuleB_Area", rec.area == "ModuleB_Area" if rec else False)
        check("exact safety ModuleB_ESZone2", rec.safety_zone == "ModuleB_ESZone2" if rec else False)
        check("exact exit_pe PE138_P", rec.exit_pe == "PE138_P" if rec else False)

        # Downstream mismatch
        gen_ds = _l5x(
            {
                "A_Fast": _rung(
                    "Fast_Conv(X.Fast,P140_Conv,AreaA,ES1,P144_Conv,PE140_P,NO_PE,P140_Conv.Type,NO_VFD,0,1,0,0,HMIColor,HMI_StatsClear)"
                )
            }
        )
        ref_ds = _l5x(
            {
                "A_Fast": _rung(
                    "Fast_Conv(X.Fast,P140_Conv,AreaA,ES1,P142_Conv,PE140_P,NO_PE,P140_Conv.Type,NO_VFD,0,1,0,0,HMIColor,HMI_StatsClear)"
                )
            }
        )
        out = tmp / "ds"
        result = run_compare(_write(tmp, "gen_ds.L5X", gen_ds), _write(tmp, "ref_ds.L5X", ref_ds), out)
        row = next(r for r in result["conveyor"]["diffs"] if r["conveyor"] == "P140")
        check(
            "downstream mismatch detected",
            row["fields"]["downstream"]["status"] == "MISMATCH",
            str(row["fields"]["downstream"]),
        )
        check(
            "downstream classification TOPOLOGY_MISMATCH",
            "TOPOLOGY_MISMATCH" in (row.get("classifications") or [row.get("classification")]),
        )

        # PE mismatch
        gen_pe = _l5x(
            {
                "A_Fast": _rung(
                    "Fast_Conv(X.Fast,P200_Conv,AreaA,ES1,NO_Conv,PE200_P,NO_PE,P200_Conv.Type,NO_VFD,0,1,0,0,HMIColor,HMI_StatsClear)"
                )
            }
        )
        ref_pe = _l5x(
            {
                "A_Fast": _rung(
                    "Fast_Conv(X.Fast,P200_Conv,AreaA,ES1,NO_Conv,PE200_J,NO_PE,P200_Conv.Type,NO_VFD,0,1,0,0,HMIColor,HMI_StatsClear)"
                )
            }
        )
        result = compare_inventories(extract_l5x(_write(tmp, "gpe.L5X", gen_pe)), extract_l5x(_write(tmp, "rpe.L5X", ref_pe)))
        row = next(r for r in result["conveyor"]["diffs"] if r["conveyor"] == "P200")
        check("PE mismatch detected", row["fields"]["exit_pe"]["status"] == "MISMATCH")

        # Missing / extra conveyor
        gen_m = _l5x(
            {
                "A_Fast": _rung(
                    "Fast_Conv(X.Fast,P10_Conv,AreaA,ES1,NO_Conv,NO_PE,NO_PE,P10_Conv.Type,NO_VFD,0,1,0,0,HMIColor,HMI_StatsClear)"
                    "Fast_Conv(X.Fast,P99_Conv,AreaA,ES1,NO_Conv,NO_PE,NO_PE,P99_Conv.Type,NO_VFD,0,1,0,0,HMIColor,HMI_StatsClear)"
                )
            }
        )
        ref_m = _l5x(
            {
                "A_Fast": _rung(
                    "Fast_Conv(X.Fast,P10_Conv,AreaA,ES1,NO_Conv,NO_PE,NO_PE,P10_Conv.Type,NO_VFD,0,1,0,0,HMIColor,HMI_StatsClear)"
                    "Fast_Conv(X.Fast,P11_Conv,AreaA,ES1,NO_Conv,NO_PE,NO_PE,P11_Conv.Type,NO_VFD,0,1,0,0,HMIColor,HMI_StatsClear)"
                )
            }
        )
        result = compare_inventories(extract_l5x(_write(tmp, "gm.L5X", gen_m)), extract_l5x(_write(tmp, "rm.L5X", ref_m)))
        check("missing conveyor P11", "P11" in result["conveyor"]["missing_conveyors"], str(result["conveyor"]["missing_conveyors"]))
        check("extra conveyor P99", "P99" in result["conveyor"]["extra_conveyors"], str(result["conveyor"]["extra_conveyors"]))
        check("exact match P10", result["conveyor"]["exact_matches"] == 1)

        # Slow_Jam multiple PEs
        jam = _l5x(
            {
                "A_Slow": _rung(
                    "Slow_Jam(P50_Conv_AOI.Jam,P50_Conv,AreaA,PE50_P,PE50_J,NO_PE,NO_PE,NO_PE)"
                )
            }
        )
        inv = extract_l5x(_write(tmp, "jam.L5X", jam))
        sj = inv.slow_jam.get("P50")
        check("Slow_Jam multi PE", sj is not None and sj.jam_pes == ["PE50_P", "PE50_J"], repr(getattr(sj, "jam_pes", None)))

        # Full_PE
        full = _l5x({"A_Slow": _rung("Full_PE(PE50_F_AOI,PE50_F,P50_Conv,1,0,HMI_StatsClear)")})
        inv = extract_l5x(_write(tmp, "full.L5X", full))
        check("Full_PE parsed", len(inv.full_pe) == 1 and inv.full_pe[0].pe_tag == "PE50_F")
        check("Full_PE conveyor", inv.full_pe[0].conveyor == "P50" if inv.full_pe else False)

        # Merge_2to1
        merge_call = (
            "Merge_2to1(P406_Merge,P138_Conv,P402_Conv,P406_Conv,P406_Conv,NO_Conv,1,1,"
            "PE138_P,PE402_P,NO_PE,0,NO_PE,NO_PE,P138_MergeTime,P402_MergeTime,0,"
            "P406_Merge.I_Merge_FltClearTime,P406_Merge.I_MergeCX_Enable,"
            "P406_Merge.I_MergeCX_TimeReset,P406_MainLane_Conv_RunHold,P406_InductLane_Conv_RunHold)"
        )
        merge_l5x = _l5x({"A_L2": _rung(merge_call)})
        inv = extract_l5x(_write(tmp, "merge.L5X", merge_l5x))
        mg = inv.merges_2to1.get("P406")
        check("Merge_2to1 parsed", mg is not None)
        check("Merge lanes", mg is not None and mg.lane_a == "P138" and mg.lane_b == "P402")
        check("Merge discharge", mg is not None and mg.discharge == "P406")
        check("Merge hold runhold", mg is not None and mg.hold_mode == "runhold", repr(getattr(mg, "hold_mode", None)))
        check("Merge PEs", mg is not None and mg.pe_a == "PE138_P" and mg.pe_b == "PE402_P")

    passed = sum(1 for _, ok, _ in checks if ok)
    failed = sum(1 for _, ok, _ in checks if not ok)
    print("====================================================")
    print(f"{'PASS' if failed == 0 else 'FAIL'} — {passed}/{passed + failed} unit checks")
    print("====================================================")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

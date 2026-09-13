#!/usr/bin/env python3
"""MSCRENO Aug28 transport structural regression gates (not byte-identical).

Locks that current from-run output still emits the historical transport shape:
  modules > 50, real CP_I > 100, Conv_UDT > 30, Conv_AOI > 30, MS > 30,
  Area_Fast + Area_Slow + Area_L1 + Area_L2 programs (or equivalent naming).

Primary fixture:
  exports/mscreno-aug28-regression/MSCRENO_MSCRENOSHIP_CURRENT.L5X

Historical comparator (optional context only):
  workspace/validation/MSCRENO_MSCRENOSHIP_AUG28.L5X
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CURRENT_L5X = ROOT / "exports" / "mscreno-aug28-regression" / "MSCRENO_MSCRENOSHIP_CURRENT.L5X"
AUG28_L5X = ROOT / "workspace" / "validation" / "MSCRENO_MSCRENOSHIP_AUG28.L5X"
COMPARE_JSON = ROOT / "exports" / "mscreno-aug28-regression" / "compare.json"


def _analyze(path: Path) -> dict:
    t = path.read_text(encoding="utf-8", errors="replace")
    mod_map: dict[str, str] = {}
    for n, c in re.findall(
        r'<Module\b[^>]*\bName="([^"]+)"[^>]*\bCatalogNumber="([^"]*)"', t
    ):
        mod_map[n] = c
    for c, n in re.findall(
        r'<Module\b[^>]*\bCatalogNumber="([^"]*)"[^>]*\bName="([^"]+)"', t
    ):
        mod_map[n] = c

    tags: dict[str, str] = {}
    for n, d in re.findall(
        r'<Tag\b[^>]*\bName="([^"]+)"[^>]*\bDataType="([^"]+)"', t
    ):
        tags[n] = d
    for d, n in re.findall(
        r'<Tag\b[^>]*\bDataType="([^"]+)"[^>]*\bName="([^"]+)"', t
    ):
        tags[n] = d

    conv = [n for n, d in tags.items() if d == "Conv_UDT"]
    conv_aoi = [n for n in tags if n.endswith("_Conv_AOI")]
    ms = [n for n in tags if n.endswith("_MS")]

    programs: list[str] = []
    seen: set[str] = set()
    for p in re.findall(r'<Program\b[^>]*\bName="([^"]+)"', t):
        if p not in seen:
            seen.add(p)
            programs.append(p)

    def count_rungs(routine_name: str) -> dict:
        m = re.search(
            rf'<Routine\b[^>]*\bName="{re.escape(routine_name)}"[^>]*>(.*?)</Routine>',
            t,
            re.S,
        )
        if not m:
            return {"present": False, "rungs": 0, "real": 0, "nop": 0, "placeholder": 0}
        body = m.group(1)
        rungs = re.findall(r"<Rung\b[^>]*>(.*?)</Rung>", body, re.S)
        real = nop = placeholder = 0
        for r in rungs:
            if "NOP()" in r:
                nop += 1
            elif "NO_PointPlaceholder" in r or "PointPlaceholder" in r:
                placeholder += 1
            else:
                real += 1
        return {
            "present": True,
            "rungs": len(rungs),
            "real": real,
            "nop": nop,
            "placeholder": placeholder,
        }

    def has_area(suffix: str) -> bool:
        return any(
            p.endswith(suffix)
            or f"Area{suffix}" in p
            or f"Area_{suffix.lstrip('_')}" in p
            for p in programs
        )

    return {
        "path": str(path).replace("\\", "/"),
        "modules": len(mod_map),
        "catalogs": dict(Counter(mod_map.values()).most_common()),
        "Conv_UDT": len(conv),
        "Conv_AOI": len(conv_aoi),
        "MS": len(ms),
        "programs": programs,
        "has_Area_Fast": has_area("_Fast") or any("Area_Fast" in p for p in programs),
        "has_Area_Slow": has_area("_Slow") or any("Area_Slow" in p for p in programs),
        "has_Area_L1": has_area("_L1") or any("Area_L1" in p for p in programs),
        "has_Area_L2": has_area("_L2") or any("Area_L2" in p for p in programs),
        "CP_I": count_rungs("CP_I"),
        "CP_O": count_rungs("CP_O"),
    }


def _gate(name: str, cond: bool, detail: str, failures: list[str]) -> None:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name} — {detail}")
    if not cond:
        failures.append(f"{name}: {detail}")


def test_current_structural_gates(path: Path | None = None) -> list[str]:
    l5x = path or CURRENT_L5X
    print(f"-- MSCRENO Aug28 regression gates on {l5x} --")
    failures: list[str] = []
    if not l5x.is_file():
        _gate("fixture_present", False, f"missing {l5x}", failures)
        return failures

    s = _analyze(l5x)
    _gate("modules>50", s["modules"] > 50, f"modules={s['modules']}", failures)
    _gate(
        "real CP_I>100",
        s["CP_I"]["real"] > 100,
        f"CP_I real={s['CP_I']['real']} (placeholders={s['CP_I']['placeholder']})",
        failures,
    )
    _gate("Conv objects>30", s["Conv_UDT"] > 30, f"Conv_UDT={s['Conv_UDT']}", failures)
    _gate("Conv_AOI>30", s["Conv_AOI"] > 30, f"Conv_AOI={s['Conv_AOI']}", failures)
    _gate("MS>30", s["MS"] > 30, f"MS={s['MS']}", failures)
    _gate("has Area_Fast", s["has_Area_Fast"], f"programs={s['programs']}", failures)
    _gate("has Area_Slow", s["has_Area_Slow"], f"programs={s['programs']}", failures)
    _gate("has Area_L1", s["has_Area_L1"], f"programs={s['programs']}", failures)
    _gate("has Area_L2", s["has_Area_L2"], f"programs={s['programs']}", failures)
    return failures


def test_compare_json_gates() -> list[str]:
    failures: list[str] = []
    if not COMPARE_JSON.is_file():
        print("  [SKIP] compare.json not present")
        return failures
    print(f"-- compare.json gates ({COMPARE_JSON}) --")
    data = json.loads(COMPARE_JSON.read_text(encoding="utf-8"))
    gates = data.get("gates") or {}
    for key, ok in gates.items():
        _gate(f"compare.{key}", bool(ok), str(ok), failures)
    recovered = bool(data.get("transport_generation_recovered"))
    _gate("transport_generation_recovered", recovered, str(recovered), failures)
    return failures


def main() -> int:
    failures: list[str] = []
    failures.extend(test_current_structural_gates())
    if AUG28_L5X.is_file():
        aug = _analyze(AUG28_L5X)
        print(
            "  [INFO] AUG28 reference — "
            f"modules={aug['modules']} Conv={aug['Conv_UDT']} AOI={aug['Conv_AOI']} "
            f"MS={aug['MS']} CP_I.real={aug['CP_I']['real']} CP_O.real={aug['CP_O']['real']}"
        )
    failures.extend(test_compare_json_gates())
    if failures:
        print(f"FAILED ({len(failures)})")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("OK — MSCRENO Aug28 structural gates passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""DATA-LEAKAGE TEST — finished L5X must not affect Auto Build generation.

SOURCE-OF-TRUTH POLICY:
  Reference PLC is validation-only. Hiding/renaming it must not change
  fortna_run_physical_layout.build_transport_graph() output.

Also asserts the builder module does not open known finished L5X paths.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_run_physical_layout import build_transport_graph  # noqa: E402

RUN = ROOT / "workspace" / "active" / "RUN"
FINISHED_CANDIDATES = [
    Path(r"C:\Users\curtiskricke\Desktop\WIth GPT\Folder to GPT\ORLY_GreensboroPLC2_NC_Finished.L5X"),
    Path(r"C:\Users\curtiskricke\Desktop\WIth GPT\Folder to GPT\OReillyGreensboroPLC2_NC_Autogen.L5X"),
]


def _canon(graph: dict) -> str:
    """Stable JSON for comparison — drop volatile timestamps and random UUIDs.

    Node/wire/area ids are generated with uuid4(); replace with deterministic
    placeholders keyed by conveyorTag so we detect real content leakage, not
    id churn.
    """
    g = json.loads(json.dumps(graph))
    g.pop("exportedAt", None)
    if isinstance(g.get("metrics"), dict):
        gs = g["metrics"].get("geometry_summary")
        if isinstance(gs, dict):
            gs.pop("generated_at", None)

    id_map: dict[str, str] = {}

    def map_id(old: str, hint: str = "") -> str:
        if not old:
            return old
        if old in id_map:
            return id_map[old]
        nid = f"ID_{len(id_map)}_{hint or 'x'}"
        id_map[old] = nid
        return nid

    for area in g.get("areas") or []:
        area["id"] = map_id(area.get("id") or "", "area")
        for n in area.get("nodes") or []:
            hint = (n.get("conveyorTag") or n.get("label") or "node").replace(" ", "_")
            n["id"] = map_id(n.get("id") or "", hint)
            for d in n.get("devices") or []:
                d["id"] = map_id(d.get("id") or "", "dev")
        # Node ids already remapped; wire from/to still hold original ids (id_map keys)
        for w in area.get("wires") or []:
            w["id"] = map_id(w.get("id") or "", "wire")
            if w.get("from") in id_map:
                w["from"] = id_map[w["from"]]
            if w.get("to") in id_map:
                w["to"] = id_map[w["to"]]
    if g.get("activeAreaId") in id_map:
        g["activeAreaId"] = id_map[g["activeAreaId"]]

    return json.dumps(g, sort_keys=True, separators=(",", ":"))


def _digest(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def test_module_does_not_reference_finished_paths() -> tuple[bool, str]:
    src = (SCRIPTS / "fortna_run_physical_layout.py").read_text(encoding="utf-8")
    bad = []
    for needle in (
        "Finished.L5X",
        "PLC2_NC_Finished",
        "ORLY_GreensboroPLC2_NC_Finished",
        "from_reference",
        "workbook_from_reference",
    ):
        if needle.lower() in src.lower():
            bad.append(needle)
    # investigate import is OK; finished path is not
    ok = not bad
    return ok, f"forbidden tokens in builder: {bad}" if bad else "builder source clean"


def test_identical_with_finished_present_absent_renamed() -> tuple[bool, str]:
    if not (RUN / "FORTNA" / "Conveyor.asc").is_file():
        return False, "missing RUN"

    # Present
    g1 = build_transport_graph(RUN, "ORNCCP2")
    d1 = _digest(_canon(g1))

    # Absent / renamed: temporarily rename any existing finished candidates
    renamed: list[tuple[Path, Path]] = []
    try:
        for p in FINISHED_CANDIDATES:
            if p.is_file():
                tmp = p.with_suffix(p.suffix + ".hidden_for_leak_test")
                p.rename(tmp)
                renamed.append((p, tmp))
        g2 = build_transport_graph(RUN, "ORNCCP2")
        d2 = _digest(_canon(g2))

        # Renamed back then rename again to a different name
        for orig, tmp in renamed:
            tmp.rename(orig)
        renamed2: list[tuple[Path, Path]] = []
        for p in FINISHED_CANDIDATES:
            if p.is_file():
                tmp = p.with_name(p.name + ".renamed_leak_test")
                p.rename(tmp)
                renamed2.append((p, tmp))
        g3 = build_transport_graph(RUN, "ORNCCP2")
        d3 = _digest(_canon(g3))
        for orig, tmp in renamed2:
            tmp.rename(orig)

        if d1 == d2 == d3:
            return True, f"identical digests {d1[:16]}… (present/absent/renamed)"
        return False, f"digest mismatch present={d1[:16]} absent={d2[:16]} renamed={d3[:16]}"
    finally:
        # Restore any leftovers
        for orig, tmp in renamed:
            if tmp.is_file() and not orig.is_file():
                tmp.rename(orig)
        for p in FINISHED_CANDIDATES:
            alt = p.with_name(p.name + ".renamed_leak_test")
            if alt.is_file() and not p.is_file():
                alt.rename(p)
            alt2 = p.with_suffix(p.suffix + ".hidden_for_leak_test")
            if alt2.is_file() and not p.is_file():
                alt2.rename(p)


def test_autogen_workbook_apply_ignores_l5x_path() -> tuple[bool, str]:
    """Practical Autogen principle: apply_workbook_to_input has no L5X argument."""
    import inspect
    from fortna_workbook import apply_workbook_to_input

    sig = inspect.signature(apply_workbook_to_input)
    params = list(sig.parameters)
    if "l5x" in params or "reference" in params or "finished" in params:
        return False, f"apply_workbook_to_input params unexpectedly include reference: {params}"
    return True, "apply_workbook_to_input(inp, workbook) only — no reference L5X parameter"


def main() -> int:
    print("=== SOURCE-OF-TRUTH DATA-LEAKAGE TEST ===")
    checks = []

    def check(name: str, fn) -> None:
        ok, detail = fn()
        checks.append((name, ok))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} — {detail}")

    check("builder source has no finished-L5X fill paths", test_module_does_not_reference_finished_paths)
    check("Auto Build identical when finished L5X present/absent/renamed", test_identical_with_finished_present_absent_renamed)
    check("Autogen workbook apply has no reference L5X parameter", test_autogen_workbook_apply_ignores_l5x_path)

    failed = sum(1 for _, ok in checks if not ok)
    print(f"{'PASS' if failed == 0 else 'FAIL'} — {len(checks) - failed}/{len(checks)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

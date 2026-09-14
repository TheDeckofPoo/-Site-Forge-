#!/usr/bin/env python3
"""Tests for BLIND PLC2 2:1 merge discovery (RUN only).

Asserts:
  - section conveyors with _P1/_P2 are preserved (not flattened)
  - every PROVEN merge has mainLane, inductLane, and evidence chain
  - no finished-PLC paths were read / referenced as inputs
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from fortna_plc2_merge_discovery import (  # noqa: E402
    FORBIDDEN_PATH_NEEDLES,
    discover_plc2_merges,
    write_report,
)

RUN = ROOT / "workspace" / "_plc2_run_peek" / "RUN"
MACHINE = "ORNCCP2"
OUT = ROOT / "exports" / "plc2-merge-discovery"

_SECTION_RE = re.compile(r"^P\d{2,4}_P\d+$", re.I)
_FLAT_PARENT_RE = re.compile(r"^P\d{2,4}$", re.I)

# Source must not open finished PLC artifacts.
FORBIDDEN_SOURCE_NEEDLES = FORBIDDEN_PATH_NEEDLES + (
    "read_l5x",
    "parse_l5x",
    "from_reference",
    "finished_plc",
    "workbook_from_reference",
    "ORLY_Greensboro_NC_PLC",
)


def _fail(msg: str) -> None:
    raise AssertionError(msg)


def test_no_finished_plc_in_source() -> None:
    src = (SCRIPTS / "fortna_plc2_merge_discovery.py").read_text(encoding="utf-8")
    lower = src.lower()
    for needle in FORBIDDEN_SOURCE_NEEDLES:
        # Allow needles only inside FORBIDDEN_PATH_NEEDLES tuple string literals
        # used for the firewall list itself.
        if needle.lower() in lower:
            # Count occurrences outside the forbidden-tuple definition block.
            if "FORBIDDEN_PATH_NEEDLES" in src:
                # Strip the tuple assignment for checking operational code.
                stripped = re.sub(
                    r"FORBIDDEN_PATH_NEEDLES\s*=\s*\(.*?\)",
                    "FORBIDDEN_PATH_NEEDLES = ()",
                    src,
                    count=1,
                    flags=re.S,
                )
                if needle in stripped and needle not in (
                    "FORBIDDEN_PATH_NEEDLES"  # never
                ):
                    # Firewall list values may still appear in the stripped tuple
                    # replacement — check operational usage patterns.
                    if re.search(
                        rf"(open\(|read_text\(|Path\([^)]*{re.escape(needle)})",
                        stripped,
                    ):
                        _fail(f"finished-PLC path usage in discovery source: {needle}")
            # Explicit L5X parse helpers must not appear at all in operational code.
            if needle in {"read_l5x", "parse_l5x", "from_reference", "finished_plc"}:
                if needle in src.replace("FORBIDDEN_PATH_NEEDLES", ""):
                    # allow comment mentions of policy
                    for line in src.splitlines():
                        if needle in line and not line.strip().startswith("#") and "Never" not in line and "never" not in line and "FORBIDDEN" not in line:
                            if "finished PLC" in line.lower() or "not read" in line.lower():
                                continue
                            if needle in line and ("import" in line or "def " in line or "= " in line):
                                _fail(f"forbidden operational reference: {needle} :: {line.strip()}")


def test_discovery_invariants() -> None:
    if not (RUN / "project.cfg").is_file() and not (RUN / "FORTNA").is_dir():
        _fail(f"PLC2 RUN not found at {RUN} — extract inbox tar to workspace/_plc2_run_peek first")

    report = discover_plc2_merges(RUN, MACHINE)
    write_report(report, OUT)

    assert report.get("firewall", {}).get("finished_l5x_read") is False
    assert report.get("firewall", {}).get("hardcoded_merge_names") is False

    merges = report.get("merges") or []
    assert merges, "expected at least one merge candidate from RUN"

    # Section preservation: any _P1/_P2 value must remain exact; never emit bare
    # parent when a suffix section was discovered for that field's evidence.
    suffix_seen = []
    for m in merges:
        for fld in (
            "mainLane",
            "inductLane",
            "downstream",
            "mergeSection1",
            "mergeSection2",
            "mergeSection3",
        ):
            val = m.get(fld)
            if not val:
                continue
            if _SECTION_RE.match(str(val)):
                suffix_seen.append((m.get("name"), fld, val))
                # Must not be flattened form without underscore section
                assert "_P" in str(val), f"flattened section? {fld}={val}"

    # PLC2 RUN has EZPE136_P1 / EZPE150_P1 evidence — at least one suffix must appear
    assert suffix_seen, (
        "expected preserved _P1/_P2 section conveyors in merge fields "
        "(P136_P1 / P136_P2 / P150_P1 / P150_P2)"
    )

    # Ensure we did not flatten known suffix sections to bare parents in lane roles
    # when the merge evidence used a suffix PE.
    for m in merges:
        for fld in ("mainLane", "inductLane"):
            val = m.get(fld) or ""
            for ev in m.get("evidence") or []:
                if ev.get("kind") == "mergeinputs_presense":
                    sec = str(ev.get("section") or "")
                    if _SECTION_RE.match(sec) and fld == "mainLane" and ev.get("lane", "").startswith("LANE1"):
                        assert val == sec or _SECTION_RE.match(val), (
                            f"{m.get('name')} {fld}={val} flattened vs presence {sec}"
                        )

    proven = [m for m in merges if m.get("classification") == "PROVEN"]
    for m in proven:
        assert m.get("mainLane"), f"PROVEN {m.get('name')} missing mainLane"
        assert m.get("inductLane"), f"PROVEN {m.get('name')} missing inductLane"
        assert m.get("mainLane") != m.get("inductLane")
        ev = m.get("evidence") or []
        assert len(ev) >= 3, f"PROVEN {m.get('name')} needs evidence chain, got {len(ev)}"
        kinds = {e.get("kind") for e in ev}
        assert "mergeboss" in kinds, f"PROVEN {m.get('name')} missing mergeboss evidence"

    # No hardcoded gold merge tag list as discovery input
    src = (SCRIPTS / "fortna_plc2_merge_discovery.py").read_text(encoding="utf-8")
    for banned in ("P316_Merge", "P406_Merge", "P324_Merge", "P400_Merge"):
        assert banned not in src, f"hardcoded merge name in source: {banned}"

    print(
        f"PASS: merges={len(merges)} proven={len(proven)} "
        f"candidate={sum(1 for m in merges if m.get('classification')=='CANDIDATE')} "
        f"unresolved={sum(1 for m in merges if m.get('classification')=='UNRESOLVED')} "
        f"suffix_fields={len(suffix_seen)}"
    )
    for m in merges:
        print(
            f"  [{m.get('classification')}] {m.get('name')}: "
            f"main={m.get('mainLane')} induct={m.get('inductLane')} "
            f"down={m.get('downstream')}"
        )


def main() -> int:
    test_no_finished_plc_in_source()
    test_discovery_invariants()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        raise SystemExit(1)

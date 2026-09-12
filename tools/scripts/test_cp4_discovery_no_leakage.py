#!/usr/bin/env python3
"""DATA-LEAKAGE TEST — finished PLC4 L5X must not affect CP4 RUN discovery.

SOURCE-OF-TRUTH POLICY:
  Discovery is RUN-only. A decoy finished PLC4 L5X present/absent/renamed
  (or pointed at via env) must not change discovery JSON digests.

Also asserts fortna_cp4_discovery.py source has no finished-L5X parse paths
or ORLY*PLC4 references used as inputs.
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

from fortna_cp4_discovery import discover  # noqa: E402

RUN = ROOT / "workspace" / "cp4-run" / "RUN"
MACHINE = "ORNCCP4"

# Digested artifact set (exclude report.md — contains generated_at narrative)
DIGEST_FILES = (
    "equipment.json",
    "vfd.json",
    "sawtooth.json",
    "encoders.json",
    "tracking_wcs.json",
    "layout_metrics.json",
)

FORBIDDEN_SOURCE_NEEDLES = (
    "Finished.L5X",
    "PLC4Finished",
    "PLC4_Finished",
    "ORLY_Greensboro_NC_PLC4",
    "ORLY*PLC4",
    "ORLY_GreensboroPLC4",
    "read_l5x",
    "parse_l5x",
    "from_reference",
    "workbook_from_reference",
    "finished_plc4",
    "plc4_finished",
)


def _strip_volatile(obj):
    """Drop timestamps so digests compare content, not clock."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in {"generated_at", "exported_at", "exportedAt"}:
                continue
            out[k] = _strip_volatile(v)
        return out
    if isinstance(obj, list):
        return [_strip_volatile(x) for x in obj]
    return obj


def _canon_dir(out_dir: Path) -> str:
    payload = {}
    for name in DIGEST_FILES:
        path = out_dir / name
        if not path.is_file():
            raise FileNotFoundError(path)
        payload[name] = _strip_volatile(json.loads(path.read_text(encoding="utf-8")))
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _digest(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _run_discovery(out_dir: Path, env_extra: dict[str, str] | None = None) -> str:
    old_env = {}
    try:
        if env_extra:
            for k, v in env_extra.items():
                old_env[k] = os.environ.get(k)
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        discover(RUN, MACHINE, out_dir)
        return _digest(_canon_dir(out_dir))
    finally:
        for k, prev in old_env.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev


def test_source_has_no_finished_l5x_inputs() -> tuple[bool, str]:
    src = (SCRIPTS / "fortna_cp4_discovery.py").read_text(encoding="utf-8")
    lower = src.lower()
    bad = []
    for needle in FORBIDDEN_SOURCE_NEEDLES:
        if needle.lower() in lower:
            bad.append(needle)
    # Also forbid opening .L5X as an input path pattern
    if ".l5x" in lower and ("open(" in lower or "read_text" in lower or "parse" in lower):
        # Allow mentioning L5X only in firewall / negative documentation strings
        # Fail if code constructs Path(...L5X) or similar input usage.
        if re_has_l5x_input(src):
            bad.append("L5X_input_path_usage")
    ok = not bad
    return ok, f"forbidden tokens/paths: {bad}" if bad else "discovery source clean of finished-L5X inputs"


def re_has_l5x_input(src: str) -> bool:
    import re

    # Path/open patterns that would consume an L5X as input
    patterns = [
        r"Path\([^\)]*\.L5X",
        r"open\([^\)]*\.L5X",
        r"read_text\([^\)]*\.L5X",
        r"parse.*L5X",
        r"lxml.*L5X",
        r"ElementTree.*L5X",
    ]
    return any(re.search(p, src, flags=re.I) for p in patterns)


def test_identical_with_decoy_present_absent_renamed() -> tuple[bool, str]:
    if not (RUN / "FORTNA" / "Conveyor.asc").is_file():
        return False, f"missing CP4 RUN at {RUN}"

    with tempfile.TemporaryDirectory(prefix="cp4_disc_") as td:
        td_path = Path(td)
        decoy = td_path / "ORLY_Greensboro_NC_PLC4v4_Finished.L5X"
        decoy.write_text(
            '<?xml version="1.0"?><RSLogix5000Content Name="DECOY_PLC4_FINISHED"/>',
            encoding="utf-8",
        )

        out1 = td_path / "out_present"
        out2 = td_path / "out_absent"
        out3 = td_path / "out_renamed"
        out4 = td_path / "out_env"

        # Present: decoy beside out + env pointing at it
        d1 = _run_discovery(
            out1,
            {
                "FORTNA_FINISHED_PLC4_L5X": str(decoy),
                "FORTNA_REFERENCE_PLC4": str(decoy),
            },
        )

        # Absent: hide decoy + clear env
        hidden = decoy.with_suffix(decoy.suffix + ".hidden_for_leak_test")
        decoy.rename(hidden)
        d2 = _run_discovery(
            out2,
            {
                "FORTNA_FINISHED_PLC4_L5X": "",
                "FORTNA_REFERENCE_PLC4": "",
            },
        )

        # Renamed: different decoy name nearby
        renamed = td_path / "ORLY_GreensboroPLC4_NC_Finished.renamed_leak_test.L5X"
        hidden.rename(renamed)
        d3 = _run_discovery(
            out3,
            {
                "FORTNA_FINISHED_PLC4_L5X": str(renamed),
                "FORTNA_REFERENCE_PLC4": str(renamed),
            },
        )

        # Env-only decoy path that does not exist
        d4 = _run_discovery(
            out4,
            {
                "FORTNA_FINISHED_PLC4_L5X": str(
                    td_path / "missing_ORLY_Greensboro_NC_PLC4_Finished.L5X"
                ),
            },
        )

        if d1 == d2 == d3 == d4:
            return True, f"identical digests {d1[:16]}… (present/absent/renamed/env)"
        return (
            False,
            f"digest mismatch present={d1[:16]} absent={d2[:16]} "
            f"renamed={d3[:16]} env={d4[:16]}",
        )


def main() -> int:
    print("=== CP4 DISCOVERY DATA-LEAKAGE TEST ===")
    checks: list[tuple[str, bool]] = []

    def check(name: str, fn) -> None:
        ok, detail = fn()
        checks.append((name, ok))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} — {detail}")

    check(
        "fortna_cp4_discovery.py has no finished-L5X parse/input paths",
        test_source_has_no_finished_l5x_inputs,
    )
    check(
        "discovery JSON digests identical with decoy PLC4 present/absent/renamed/env",
        test_identical_with_decoy_present_absent_renamed,
    )

    failed = sum(1 for _, ok in checks if not ok)
    print(f"{'PASS' if failed == 0 else 'FAIL'} — {len(checks) - failed}/{len(checks)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

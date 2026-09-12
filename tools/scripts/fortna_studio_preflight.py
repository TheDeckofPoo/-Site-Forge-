#!/usr/bin/env python3
"""Static Studio 5000 import pre-flight checker.

Does NOT claim Studio download/import verification — Curtis must confirm in Studio.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def preflight_l5x(path: Path) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []

    def add(severity: str, kind: str, message: str, **extra: Any) -> None:
        issues.append({"severity": severity, "kind": kind, "message": message, **extra})

    if not path.is_file():
        return {
            "path": str(path),
            "ok": False,
            "issues": [{"severity": "ERROR", "kind": "missing_file", "message": "L5X not found"}],
        }

    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return {
            "path": str(path),
            "ok": False,
            "xml_parses": False,
            "issues": [{"severity": "ERROR", "kind": "xml_parse", "message": str(exc)}],
        }

    # Controller
    ctrl = root.find(".//Controller")
    if ctrl is None:
        add("ERROR", "controller_missing", "No Controller element")
    else:
        if not ctrl.attrib.get("Name"):
            add("ERROR", "controller_name", "Controller Name missing")
        if not ctrl.attrib.get("ProcessorType"):
            add("WARNING", "processor_type", "ProcessorType missing")

    # Programs / Main routines
    programs_with_main = []
    programs_missing_main = []
    routine_names: set[str] = set()
    for prog in root.iter("Program"):
        pname = prog.attrib.get("Name") or ""
        routines = [r.attrib.get("Name") for r in prog.iter("Routine") if r.attrib.get("Name")]
        for r in routines:
            routine_names.add(r or "")
            routine_names.add(f"{pname}.{r}")
        if any((r or "").upper() == "MAIN" for r in routines):
            programs_with_main.append(pname)
        elif pname:
            programs_missing_main.append(pname)
            add("WARNING", "missing_main_routine", f"Program {pname} has no Main routine", program=pname)

    # Duplicate tags
    tag_names: list[str] = []
    for tag in root.iter("Tag"):
        n = tag.attrib.get("Name")
        if n:
            tag_names.append(n)
    seen: set[str] = set()
    dups: set[str] = set()
    for n in tag_names:
        if n in seen:
            dups.add(n)
        seen.add(n)
    for d in sorted(dups)[:50]:
        add("ERROR", "duplicate_tag", f"Duplicate tag: {d}", tag=d)

    # Invalid tag names (Rockwell: must start with letter or underscore)
    for n in tag_names:
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", n):
            add("ERROR", "invalid_tag_name", f"Invalid tag name: {n}", tag=n)

    # JSR targets
    jsr_targets = set(re.findall(r"JSR\s*\(\s*([A-Za-z0-9_\.]+)", text))
    undefined = sorted(t for t in jsr_targets if t not in routine_names and t.split(".")[-1] not in routine_names)
    for t in undefined[:40]:
        add("WARNING", "undefined_routine_call", f"JSR target not found: {t}", routine=t)

    # AOI / datatype dependency presence (best-effort)
    if "<AddOnInstructionDefinitions" not in text and "AddOnInstructionName" in text:
        add("WARNING", "aoi_definitions", "AOI references present but definitions block missing")
    if "<DataTypes" not in text:
        add("WARNING", "datatypes", "DataTypes block missing")

    # Modules
    modules = list(root.iter("Module"))
    if not modules:
        add("INFO", "modules", "No Module elements (may be OK for soft controller packs)")

    errors = sum(1 for i in issues if i["severity"] == "ERROR")
    warnings = sum(1 for i in issues if i["severity"] == "WARNING")
    return {
        "generated_at": _ts(),
        "path": str(path),
        "sha256": sha256_file(path),
        "xml_parses": True,
        "ok": errors == 0,
        "studio_import_claimed": False,
        "note": "Static precheck only — Curtis must import in Studio 5000",
        "counts": {
            "errors": errors,
            "warnings": warnings,
            "info": sum(1 for i in issues if i["severity"] == "INFO"),
            "programs_with_main": len(programs_with_main),
            "programs_missing_main": len(programs_missing_main),
            "tags": len(tag_names),
            "duplicate_tags": len(dups),
            "modules": len(modules),
        },
        "programs_with_main": programs_with_main,
        "issues": issues,
    }


def write_markdown(report: dict[str, Any], out: Path) -> None:
    lines = [
        f"# Studio Import Precheck — {Path(report.get('path') or '').name}",
        "",
        f"Generated: `{report.get('generated_at')}`",
        "",
        f"- XML parses: **{report.get('xml_parses')}**",
        f"- Static ok (no ERROR): **{report.get('ok')}**",
        f"- Studio import claimed: **{report.get('studio_import_claimed')}**",
        f"- SHA256: `{report.get('sha256')}`",
        "",
        "## Counts",
        "",
        "```json",
        __import__("json").dumps(report.get("counts") or {}, indent=2),
        "```",
        "",
        "## Issues",
        "",
    ]
    for i in report.get("issues") or []:
        lines.append(f"- **{i.get('severity')}** `{i.get('kind')}`: {i.get('message')}")
    if not report.get("issues"):
        lines.append("- (none)")
    lines.extend(
        [
            "",
            "## Curtis checklist",
            "",
            "1. Open Studio 5000",
            "2. Import / open this L5X",
            "3. Note any import errors/warnings",
            "4. Confirm controller opens",
            "5. Do not treat this precheck as PASS until Curtis reports",
            "",
        ]
    )
    out.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Studio 5000 static import precheck")
    ap.add_argument("l5x", type=Path)
    ap.add_argument("--out-json", type=Path, default=None)
    ap.add_argument("--out-md", type=Path, default=None)
    args = ap.parse_args(argv)
    report = preflight_l5x(args.l5x)
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(__import__("json").dumps(report, indent=2), encoding="utf-8")
    if args.out_md:
        write_markdown(report, args.out_md)
    print(__import__("json").dumps({"ok": report["ok"], "counts": report["counts"]}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

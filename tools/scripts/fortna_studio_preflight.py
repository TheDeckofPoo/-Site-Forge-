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
        main_attr = (prog.attrib.get("MainRoutineName") or "").strip()
        has_main = any((r or "").upper() in ("MAIN", "MAIN_ROUTINE") for r in routines)
        if main_attr and main_attr in (routines or []):
            has_main = True
        if has_main:
            programs_with_main.append(pname)
        elif pname:
            programs_missing_main.append(pname)
            add("WARNING", "missing_main_routine", f"Program {pname} has no Main routine", program=pname)

    # Duplicate tags — scope-aware (controller vs program:<name>).
    # Same name at controller + program is allowed in Logix (program shadows),
    # but TRUE duplicates are: twice in controller Tags, or twice in one program.
    from collections import defaultdict

    scope_names: dict[str, list[str]] = defaultdict(list)

    # Controller-level Tags: direct children under Controller before Programs
    for ctrl in root.iter("Controller"):
        for child in list(ctrl):
            if child.tag == "Tags":
                for tag in child.findall("Tag"):
                    n = tag.attrib.get("Name")
                    if n:
                        scope_names["controller"].append(n)
            if child.tag == "Programs":
                break

    for prog in root.iter("Program"):
        pname = prog.attrib.get("Name") or "?"
        for tags_el in prog.findall("Tags"):
            for tag in tags_el.findall("Tag"):
                n = tag.attrib.get("Name")
                if n:
                    scope_names[f"program:{pname}"].append(n)

    dups: set[str] = set()
    for scope, names in scope_names.items():
        seen: set[str] = set()
        for n in names:
            if n in seen:
                dups.add(f"{n} @{scope}")
            seen.add(n)
    for d in sorted(dups)[:50]:
        add("ERROR", "duplicate_tag", f"Duplicate tag: {d}", tag=d.split(" @", 1)[0])

    # Flat list still used for invalid-name checks
    tag_names = [n for names in scope_names.values() for n in names]

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
    module_names = {
        m.attrib.get("Name") for m in modules if m.attrib.get("Name")
    }
    if not modules:
        add("INFO", "modules", "No Module elements (may be OK for soft controller packs)")

    # NO_PS Decorated members must match PS_UDT (I, Flt, PS_FltTime) — never O_Reset
    _check_no_ps_members(text, add)

    # SNTP_MSG_* ConnectionPath must reference an emitted Module name
    _check_sntp_connection_paths(text, module_names, add)

    # Duplicate OTE targets inside IO_MAP routines cause overlapping coils
    _check_iomap_duplicate_otes(text, add)

    # Gate I — full operand member-path validation (Invalid member specifier)
    operand_report: dict[str, Any] = {}
    try:
        from fortna_operand_validator import validate_l5x_operands

        operand_report = validate_l5x_operands(text)
        for inv in operand_report.get("invalid") or []:
            extra = {
                k: inv.get(k)
                for k in (
                    "program", "routine", "rung", "instruction", "operand",
                    "base_tag", "datatype", "failed_segment", "failed_member_segment",
                )
                if inv.get(k) is not None
            }
            extra["operand_kind"] = inv.get("kind")
            add(
                "ERROR",
                "invalid_member_specifier",
                (
                    f"PLC OPERAND ERROR Program:{inv.get('program')} "
                    f"Routine:{inv.get('routine')} Rung:{inv.get('rung')} "
                    f"{inv.get('instruction')} Operand:{inv.get('operand')} "
                    f"DataType:{inv.get('datatype') or '—'} "
                    f"Invalid segment:{inv.get('failed_member_segment') or inv.get('failed_segment') or '—'}"
                ),
                **extra,
            )
    except Exception as exc:
        add("WARNING", "operand_validator_error", f"Operand validator failed: {exc}")

    # PL-8 — structural subsystem preflight (does not block on Safety REVIEW)
    structural = _structural_subsystem_report(text, root)
    if structural.get("safety", {}).get("status") == "REVIEW_REQUIRED":
        add(
            "INFO",
            "safety_membership_review",
            structural["safety"].get("detail")
            or "SAFETY STRUCTURE READY · MEMBERSHIP REVIEW REQUIRED · COMMISSIONING READY = NO",
        )

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
            "programs": len(list(root.iter("Program"))),
            "tasks": len(list(root.iter("Task"))),
            "datatypes": len(list(root.iter("DataType"))),
            "controller_tags": len(tag_names),
        },
        "programs_with_main": programs_with_main,
        "structural": structural,
        "operand_validation": operand_report,
        "issues": issues,
    }


# PS_UDT top-level members (from Slow_Flt_AOI / library datatype)
_PS_UDT_TOP_MEMBERS = frozenset({"I", "Flt", "PS_FltTime"})


def _check_no_ps_members(text: str, add) -> None:
    """Fail when NO_PS Decorated Structure has members outside PS_UDT."""
    m = re.search(
        r'<Tag\b[^>]*\bName="NO_PS"[^>]*>.*?</Tag>',
        text,
        re.S,
    )
    if not m:
        return
    block = m.group(0)
    struct = re.search(
        r'<Structure\s+DataType="PS_UDT">(.*?)</Structure>',
        block,
        re.S,
    )
    if not struct:
        return
    body = struct.group(1)
    # Depth-aware: only top-level StructureMember / DataValueMember under PS_UDT
    bad: list[str] = []
    depth = 0
    pos = 0
    while pos < len(body):
        if body.startswith("</StructureMember>", pos):
            depth = max(0, depth - 1)
            pos += len("</StructureMember>")
            continue
        m_open = re.match(
            r'<(StructureMember|DataValueMember)\s+Name="([^"]+)"([^>]*)>',
            body[pos:],
        )
        if m_open:
            kind, name, rest = m_open.group(1), m_open.group(2), m_open.group(3)
            if depth == 0 and name not in _PS_UDT_TOP_MEMBERS:
                bad.append(name)
            self_close = rest.rstrip().endswith("/")
            pos += m_open.end()
            if kind == "StructureMember" and not self_close:
                depth += 1
            continue
        pos += 1
    for name in bad:
        add(
            "ERROR",
            "no_ps_invalid_member",
            f"NO_PS Decorated member '{name}' is not in PS_UDT "
            f"(allowed: {', '.join(sorted(_PS_UDT_TOP_MEMBERS))})",
            member=name,
        )


def _check_sntp_connection_paths(text: str, module_names: set[str], add) -> None:
    """Fail when SNTP_MSG_* ConnectionPath does not match an emitted Module."""
    for tm in re.finditer(
        r'<Tag\b[^>]*\bName="(SNTP_MSG_[^"]+)"[^>]*>(.*?)</Tag>',
        text,
        re.S,
    ):
        tname = tm.group(1)
        body = tm.group(2)
        paths = re.findall(r'ConnectionPath="([^"]*)"', body)
        for path in paths:
            if not path:
                add(
                    "ERROR",
                    "sntp_connection_path_empty",
                    f"{tname} has empty ConnectionPath",
                    tag=tname,
                )
            elif path not in module_names:
                add(
                    "ERROR",
                    "sntp_connection_path_missing_module",
                    f"{tname} ConnectionPath='{path}' is not an emitted Module name",
                    tag=tname,
                    connection_path=path,
                )


def _structural_subsystem_report(text: str, root: ET.Element) -> dict[str, Any]:
    """PL-8 structural counts + mandatory subsystem status (report only)."""
    programs = [p.attrib.get("Name") or "" for p in root.iter("Program")]
    tasks = [t.attrib.get("Name") or "" for t in root.iter("Task")]
    ctrl = root.find(".//Controller")
    controller_name = (ctrl.attrib.get("Name") if ctrl is not None else "") or ""

    def _has_prog(name: str) -> bool:
        return name in programs

    area_fast = [n for n in programs if n.endswith("_Fast")]
    area_slow = [n for n in programs if n.endswith("_Slow")]
    area_l1 = [n for n in programs if n.endswith("_L1")]
    area_l2 = [n for n in programs if n.endswith("_L2")]
    areas = sorted(
        {
            n[: -len(suf)]
            for n, suf in (
                *((x, "_Fast") for x in area_fast),
                *((x, "_Slow") for x in area_slow),
                *((x, "_L1") for x in area_l1),
                *((x, "_L2") for x in area_l2),
            )
        }
    )

    es_xml = ""
    for prog in root.iter("Program"):
        if (prog.attrib.get("Name") or "") == "ES":
            es_xml = ET.tostring(prog, encoding="unicode")
            break
    safe_logic = len(re.findall(r'Routine Name="[^"]*_Safe_Logic"', es_xml))
    safe_pi = len(re.findall(r'Routine Name="[^"]*_Safe_PI"', es_xml))
    has_main = bool(re.search(r'Routine Name="Main_Routine"', es_xml)) or bool(
        re.search(r'MainRoutineName="Main_Routine"', es_xml)
    )
    shell = bool(es_xml) and safe_logic == 0 and safe_pi == 0 and has_main
    # Unresolved membership heuristic: shell present, or REVIEW comment in ES
    unresolved = 0
    if shell:
        unresolved = len(re.findall(r"Unresolved zones", es_xml)) or 1
    safety_status = (
        "NOT_DETECTED"
        if not es_xml
        else ("REVIEW_REQUIRED" if shell or unresolved else "READY")
    )
    safety_detail = (
        "SAFETY STRUCTURE READY · MEMBERSHIP REVIEW REQUIRED · PROGRAM GENERATED · "
        "COMMISSIONING READY = NO"
        if shell
        else (
            "SAFETY — READY"
            if safety_status == "READY"
            else "SAFETY — NOT DETECTED"
        )
    )

    return {
        "controller": controller_name,
        "programs_count": len(programs),
        "tasks_count": len(tasks),
        "controller_tags_count": len(list(root.iter("Tag"))),
        "datatypes_count": len(list(root.iter("DataType"))),
        "modules_count": len(list(root.iter("Module"))),
        "sys": {"present": _has_prog("Sys"), "status": "READY" if _has_prog("Sys") else "MISSING"},
        "system": {
            "present": _has_prog("System"),
            "status": "READY" if _has_prog("System") else "MISSING",
        },
        "io_map": {
            "present": _has_prog("IO_MAP"),
            "status": "READY" if _has_prog("IO_MAP") else "MISSING",
        },
        "transportation": {
            "areas_included": areas,
            "fast": area_fast,
            "slow": area_slow,
            "l1": area_l1,
            "l2": area_l2,
            "status": "READY" if area_fast or area_slow else "NOT_DETECTED",
        },
        "safety": {
            "es_program": bool(es_xml),
            "p01_safety_20ms": "P01_Safety_20ms" in tasks,
            "main_routine": has_main,
            "safe_logic_count": safe_logic,
            "safe_pi_count": safe_pi,
            "unresolved_membership_count": unresolved,
            "shell": shell,
            "status": safety_status,
            "structure": "READY" if es_xml else "MISSING",
            "membership": "REVIEW_REQUIRED" if shell or unresolved else ("READY" if es_xml else "NOT_DETECTED"),
            "commissioning_ready": False if shell or unresolved or not es_xml else True,
            "detail": safety_detail,
        },
    }


def _check_iomap_duplicate_otes(text: str, add) -> None:
    """Fail when IO_MAP routines contain duplicate OTE targets.

    NO_PointPlaceholder is an intentional multi-rung sink for unused bits — excluded.
    One physical OUTPUT bit must have exactly one logical owner.
    """
    prog = re.search(
        r'<Program\b[^>]*\bName="IO_MAP"[^>]*>(.*?)</Program>',
        text,
        re.S,
    )
    if not prog:
        return
    body = prog.group(1)
    # Collect OTE target → list of (xic writers, comment) for diagnostics
    writers: dict[str, list[dict[str, str]]] = {}
    for rm in re.finditer(r"<Rung\b[^>]*>(.*?)</Rung>", body, re.S):
        inner = rm.group(1)
        tm = re.search(r"<Text>\s*<!\[CDATA\[(.*?)\]\]>\s*</Text>", inner, re.S)
        if not tm:
            continue
        rung = tm.group(1)
        cm = re.search(r"<Comment>\s*<!\[CDATA\[(.*?)\]\]>\s*</Comment>", inner, re.S)
        comment = (cm.group(1) if cm else "").strip()
        xics = re.findall(r"\bXIC\s*\(\s*([^)]+?)\s*\)", rung, re.I)
        for t in re.findall(r"\bOTE\s*\(\s*([^)]+?)\s*\)", rung, re.I):
            key = t.strip()
            if not key:
                continue
            writers.setdefault(key, []).append(
                {
                    "xic": ",".join(x.strip() for x in xics) or "",
                    "comment": comment,
                }
            )
    _allow_multi = {"NO_PointPlaceholder"}
    for t, hits in sorted(writers.items()):
        if t in _allow_multi:
            continue
        if len(hits) < 2:
            continue
        detail = " | ".join(
            f"writer{i+1}={h.get('xic') or '?'} ({h.get('comment') or 'no comment'})"
            for i, h in enumerate(hits[:4])
        )
        # RUN-backed shared physical outputs are annotated REVIEW_SHARED_OUTPUT —
        # preserve all claims; do not ERROR-block generation (qualification stays REVIEW).
        run_shared = all(
            "REVIEW_SHARED_OUTPUT" in str(h.get("comment") or "")
            or "RUN_PROVEN" in str(h.get("comment") or "")
            for h in hits
        )
        if run_shared:
            add(
                "WARNING",
                "iomap_review_shared_output",
                f"IO_MAP REVIEW_SHARED_OUTPUT: {t} — {detail}",
                target=t,
                writers=hits,
                status="REVIEW_SHARED_OUTPUT",
            )
            continue
        add(
            "ERROR",
            "iomap_duplicate_ote",
            f"IO_MAP duplicate OTE target: {t} — {detail}",
            target=t,
            writers=hits,
        )


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

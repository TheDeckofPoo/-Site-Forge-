#!/usr/bin/env python3
"""Generic Fortna transportation routine completeness / coverage contract.

Establishes structural expectations for Area Fast/Slow/L1 (and detected sorter /
sawtooth / merge packs). Greensboro may inform the contract shape only — never
as a generation parent or copied logic source.

Statuses:
  COMPLETE | PRESENT_PARTIAL | PLACEHOLDER | EMPTY | MISSING_EXPECTED
  | WITHHELD_REVIEW | UNSUPPORTED | NOT_APPLICABLE | UNREACHABLE
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

STATUS_COMPLETE = "COMPLETE"
STATUS_PRESENT_PARTIAL = "PRESENT_PARTIAL"
STATUS_PLACEHOLDER = "PLACEHOLDER"
STATUS_EMPTY = "EMPTY"
STATUS_MISSING_EXPECTED = "MISSING_EXPECTED"
STATUS_WITHHELD_REVIEW = "WITHHELD_REVIEW"
STATUS_UNSUPPORTED = "UNSUPPORTED"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
STATUS_UNREACHABLE = "UNREACHABLE"

# Generic transportation Slow / Fast / L1 expectations (feature-driven applicability).
SLOW_CORE_ROUTINES: tuple[str, ...] = (
    "Main_Routine",
    "Area_Logic",
    "Area_PI",
    "Control_Station",
    "Conv_Flt",
    "Conv_Jam",
    "Conv_PI",
    "Stacklight",
)
FAST_CORE_ROUTINES: tuple[str, ...] = (
    "Main_Routine",
    "Conv_Fast",
    "Conv_PE",
)
FAST_OPTIONAL_ROUTINES: tuple[str, ...] = (
    "Conv_Full",
    "Merge",
)
# L1 program always expects Main_Routine. Timing/config routines (Conv_Speed /
# FullTime / PETime) are the generic "L1/Config" contract — valid Fortna
# architecture may place them in Area_L1 OR Area_L2. ORI-107: never flag them
# MISSING_EXPECTED on L1 when L2 already owns the generated routines.
L1_CORE_ROUTINES: tuple[str, ...] = (
    "Main_Routine",
)
L1_OPTIONAL_ROUTINES: tuple[str, ...] = ("Merge",)
CONFIG_TIMING_ROUTINES: tuple[str, ...] = (
    "Conv_Speed",
    "FullTime",
    "PETime",
)

SORTER_EXPECTED_ROUTINES: tuple[str, ...] = (
    "Main",
    "Main_Routine",
    "Encoder",
    "Track_Induct_Package",
    "Track_Divert_Package",
    "Wave_Divert",
    "Scanner",
    "Sorter_Track",
)

SAWTOOTH_EXPECTED_ROUTINES: tuple[str, ...] = (
    "Main_Routine",
    "Sawtooth",
    "Saw_Merge",
    "Merge",
)

_ATTR_NAME_RE = re.compile(r'(?<![A-Za-z0-9_])Name="([^"]+)"')
_JSR_RE = re.compile(r"\bJSR\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:,|\))", re.I)
_NOP_ONLY_RE = re.compile(r"^\s*(?:NOP\s*\(\s*\)\s*;?\s*)+$", re.I)


@dataclass
class RoutineCoverageRow:
    program: str
    routine: str
    expected_because: str
    feature: str
    present: bool
    scheduled: bool
    caller: str
    jsr_rung: str
    rung_count: int
    non_nop_executable_count: int
    status: str
    issue_ids: list[str] = field(default_factory=list)
    engineer_action: str = ""
    effect: str = "NON_BLOCKING"

    def to_dict(self) -> dict[str, Any]:
        return {
            "PROGRAM": self.program,
            "ROUTINE": self.routine,
            "EXPECTED BECAUSE": self.expected_because,
            "FEATURE / ARCHETYPE": self.feature,
            "PRESENT": "YES" if self.present else "NO",
            "SCHEDULED / CALLED": "YES" if self.scheduled else "NO",
            "CALLER": self.caller or "N/A",
            "JSR RUNG": self.jsr_rung if self.jsr_rung != "" else "N/A",
            "RUNG / LINE COUNT": self.rung_count,
            "NON-NOP EXECUTABLE LOGIC COUNT": self.non_nop_executable_count,
            "STATUS": self.status,
            "ASSOCIATED ISSUE IDS": list(self.issue_ids),
            "ENGINEER ACTION": self.engineer_action or "N/A",
            "EFFECT": self.effect,
            # build_issues back-compat
            "object/device": f"{self.program}/{self.routine}",
            "subsystem": "routine_coverage",
            "severity/classification": self.status,
            "reason": self.engineer_action or self.expected_because,
            "source/provenance": "fortna_routine_completeness",
            "what Site Forge did": (
                "PLACEHOLDER"
                if self.status == STATUS_PLACEHOLDER
                else (
                    "REVIEW_ONLY"
                    if self.status
                    in {
                        STATUS_MISSING_EXPECTED,
                        STATUS_EMPTY,
                        STATUS_PRESENT_PARTIAL,
                        STATUS_UNREACHABLE,
                        STATUS_WITHHELD_REVIEW,
                    }
                    else "GENERATED"
                )
            ),
            "effect": self.effect,
            "engineer action": self.engineer_action or "N/A",
            "program": self.program,
            "routine": self.routine,
            "rung": self.jsr_rung if self.jsr_rung != "" else "N/A",
            "operand": "N/A",
        }


@dataclass
class RoutineCoverageReport:
    rows: list[RoutineCoverageRow] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    programs_expected: int = 0
    programs_present: int = 0
    issues: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "programs_expected": self.programs_expected,
            "programs_present": self.programs_present,
            "routines_expected_applicable": int(self.summary.get("APPLICABLE", 0)),
            "summary": dict(self.summary),
            "rows": [r.to_dict() for r in self.rows],
            "issue_count": len(self.issues),
            "issues": list(self.issues),
        }


def _attr_name(attrs: str) -> str:
    m = _ATTR_NAME_RE.search(attrs or "")
    return m.group(1) if m else ""


def _parse_l5x_programs(l5x_text: str) -> dict[str, dict[str, Any]]:
    """program -> {routines: {name: {rungs, texts, jsr_targets}}, main_calls}."""
    out: dict[str, dict[str, Any]] = {}
    if not l5x_text:
        return out
    for pm in re.finditer(r"<Program\b([^>]*)>(.*?)</Program>", l5x_text, re.S):
        pname = _attr_name(pm.group(1))
        if not pname:
            continue
        pbody = pm.group(2)
        routines: dict[str, dict[str, Any]] = {}
        for rm in re.finditer(r"<Routine\b([^>]*)>(.*?)</Routine>", pbody, re.S):
            rname = _attr_name(rm.group(1))
            if not rname:
                continue
            rbody = rm.group(2)
            texts = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", rbody, re.S)
            jsr_targets: list[tuple[str, str]] = []  # (target, rung_number)
            rung_nums = re.findall(
                r'<Rung\b[^>]*Number="(\d+)"[^>]*>.*?<Text><!\[CDATA\[(.*?)\]\]></Text>',
                rbody,
                re.S,
            )
            if not rung_nums and texts:
                # fallback without number capture
                for i, tx in enumerate(texts):
                    for tgt in _JSR_RE.findall(tx or ""):
                        jsr_targets.append((tgt, str(i)))
            else:
                for num, tx in rung_nums:
                    for tgt in _JSR_RE.findall(tx or ""):
                        jsr_targets.append((tgt, str(num)))
            non_nop = 0
            for tx in texts:
                s = (tx or "").strip()
                if not s:
                    continue
                if _NOP_ONLY_RE.match(s):
                    continue
                if s.upper().startswith("NOP"):
                    continue
                non_nop += 1
            routines[rname] = {
                "rung_count": len(texts),
                "texts": texts,
                "non_nop": non_nop,
                "jsr_targets": jsr_targets,
            }
        # Aggregate JSR map from Main_Routine / Main
        calls: dict[str, tuple[str, str]] = {}
        for main_name in ("Main_Routine", "Main"):
            main = routines.get(main_name) or {}
            for tgt, rung in main.get("jsr_targets") or []:
                calls.setdefault(tgt, (main_name, rung))
        out[pname] = {"routines": routines, "calls": calls}
    return out


def _classify_present_routine(
    *,
    present: bool,
    scheduled: bool,
    rung_count: int,
    non_nop: int,
    withheld: bool = False,
    unsupported: bool = False,
) -> str:
    if unsupported:
        return STATUS_UNSUPPORTED
    if withheld:
        return STATUS_WITHHELD_REVIEW
    if not present:
        return STATUS_MISSING_EXPECTED
    if present and not scheduled:
        if non_nop > 0:
            return STATUS_UNREACHABLE
        if rung_count <= 0:
            return STATUS_EMPTY
        return STATUS_PLACEHOLDER
    if rung_count <= 0:
        return STATUS_EMPTY
    if non_nop <= 0:
        return STATUS_PLACEHOLDER
    # Heuristic: single executable rung that is only a trivial stub may still be partial;
    # treat any non-NOP as COMPLETE for core transport unless explicitly withheld.
    return STATUS_COMPLETE


def _area_program_names(programs: dict[str, dict[str, Any]], suffix: str) -> list[str]:
    suf = suffix.lower()
    hits = [p for p in programs if p.lower().endswith(suf)]
    return sorted(hits)


def _issue_from_row(row: RoutineCoverageRow, issue_n: int) -> dict[str, Any]:
    iid = f"SF-R{issue_n:04d}"
    row.issue_ids.append(iid)
    action = row.to_dict().get("what Site Forge did") or "REVIEW_ONLY"
    return {
        "issue_id": iid,
        "CATEGORY": "ROUTINE COVERAGE / COMPLETENESS",
        "SEVERITY": row.status,
        "PROGRAM": row.program,
        "ROUTINE": row.routine,
        "RUNG NUMBER / RUNG INDEX": row.jsr_rung if row.jsr_rung != "" else "N/A",
        "OBJECT / DEVICE": f"{row.program}/{row.routine}",
        "OPERAND / TAG / ENDPOINT": "N/A",
        "REASON": (
            f"Routine status={row.status}. {row.expected_because}. "
            f"PRESENT={'YES' if row.present else 'NO'}; "
            f"SCHEDULED={'YES' if row.scheduled else 'NO'}; "
            f"non-NOP rungs={row.non_nop_executable_count}."
        ),
        "SOURCE / PROVENANCE": "fortna_routine_completeness / transportation contract",
        "SITE FORGE ACTION": action,
        "ENGINEER ACTION": row.engineer_action
        or "Review routine completeness before commissioning.",
        "EFFECT": row.effect,
        "object/device": f"{row.program}/{row.routine}",
        "subsystem": "routine_coverage",
        "severity/classification": row.status,
        "reason": row.engineer_action or row.expected_because,
        "source/provenance": "fortna_routine_completeness",
        "what Site Forge did": action,
        "effect": row.effect,
        "engineer action": row.engineer_action
        or "Review routine completeness before commissioning.",
        "program": row.program,
        "routine": row.routine,
        "rung": row.jsr_rung if row.jsr_rung != "" else "N/A",
        "operand": "N/A",
    }


def _row(
    *,
    program: str,
    routine: str,
    because: str,
    feature: str,
    prog_info: dict[str, Any] | None,
    applicable: bool = True,
    withheld: bool = False,
    unsupported: bool = False,
) -> RoutineCoverageRow:
    if not applicable:
        return RoutineCoverageRow(
            program=program,
            routine=routine,
            expected_because=because,
            feature=feature,
            present=False,
            scheduled=False,
            caller="N/A",
            jsr_rung="",
            rung_count=0,
            non_nop_executable_count=0,
            status=STATUS_NOT_APPLICABLE,
            engineer_action="Feature not detected for this controller — not a defect.",
            effect="NON_BLOCKING",
        )
    routines = (prog_info or {}).get("routines") or {}
    calls = (prog_info or {}).get("calls") or {}
    present = routine in routines
    info = routines.get(routine) or {}
    scheduled = routine == "Main_Routine" or routine == "Main" or routine in calls
    caller = "N/A"
    jsr_rung = ""
    if routine in ("Main_Routine", "Main"):
        scheduled = True
        caller = "Program (main)"
    elif routine in calls:
        caller, jsr_rung = calls[routine]
    rung_count = int(info.get("rung_count") or 0)
    non_nop = int(info.get("non_nop") or 0)
    status = _classify_present_routine(
        present=present,
        scheduled=scheduled,
        rung_count=rung_count,
        non_nop=non_nop,
        withheld=withheld,
        unsupported=unsupported,
    )
    if status == STATUS_COMPLETE:
        eng = "No action — routine present with executable logic."
        effect = "NON_BLOCKING"
    elif status == STATUS_PLACEHOLDER:
        eng = (
            f"Complete project-specific {routine} logic before commissioning "
            "(currently NOP/placeholder only)."
        )
        effect = "COMMISSIONING"
    elif status == STATUS_EMPTY:
        eng = f"Populate {routine} or accept empty shell; currently no rungs."
        effect = "COMMISSIONING"
    elif status == STATUS_MISSING_EXPECTED:
        eng = (
            f"Create/populate expected routine {routine} in {program} "
            f"(called/expected by transportation contract)."
        )
        effect = "COMMISSIONING"
    elif status == STATUS_UNREACHABLE:
        eng = (
            f"Schedule/call {routine} from Main_Routine (or document why unreachable)."
        )
        effect = "COMMISSIONING"
    elif status == STATUS_WITHHELD_REVIEW:
        eng = f"Review withheld {routine}; complete evidence before generating logic."
        effect = "COMMISSIONING"
    elif status == STATUS_UNSUPPORTED:
        eng = f"Unsupported beta function {routine} — hand-complete or defer."
        effect = "COMMISSIONING"
    else:
        eng = f"Review {routine} completeness."
        effect = "COMMISSIONING"
    return RoutineCoverageRow(
        program=program,
        routine=routine,
        expected_because=because,
        feature=feature,
        present=present,
        scheduled=scheduled,
        caller=caller,
        jsr_rung=jsr_rung,
        rung_count=rung_count,
        non_nop_executable_count=non_nop,
        status=status,
        engineer_action=eng,
        effect=effect,
    )


def analyze_routine_coverage(
    l5x_text: str,
    *,
    report: dict[str, Any] | None = None,
    start_issue_n: int = 1,
) -> RoutineCoverageReport:
    """Compute routine coverage against generic transportation + detected features."""
    rep = report if isinstance(report, dict) else {}
    programs = _parse_l5x_programs(l5x_text or "")
    rows: list[RoutineCoverageRow] = []

    # Feature detection (generic — no site-name branches).
    merges_emitted = list(rep.get("merges_emitted") or [])
    merges_withheld = list(rep.get("merges_withheld_review") or [])
    has_merge_feature = bool(merges_emitted or merges_withheld or rep.get("merges_2to1"))
    merge_generated = bool(merges_emitted)
    merge_withheld = bool(merges_withheld) and not merge_generated

    sorter = rep.get("sorter_build") or rep.get("sorter") or {}
    sorter_detected = bool(
        sorter
        or rep.get("sorter_detected")
        or any("sorter" in str(p).lower() for p in programs)
        or "Sorter_Track" in (rep.get("programs") or [])
        or any("Sorter_Track" in str(p) for p in programs)
    )
    sorter_generated = any(
        "sorter" in p.lower() or p.endswith("Sorter_Track") or "Sorter" in p
        for p in programs
    )
    fd = rep.get("function_disclosure") if isinstance(rep.get("function_disclosure"), dict) else {}
    sorter_unsupported = False
    if isinstance(fd, dict):
        for _name, meta in fd.items():
            if not isinstance(meta, dict):
                continue
            if "sorter" in str(_name).lower() or "Sorter" in str(_name):
                st = str(meta.get("status") or "").upper()
                if st in {"UNSUPPORTED", "UNSUPPORTED_BETA_FUNCTION"}:
                    sorter_unsupported = True

    saw = rep.get("sawtooth_build") or rep.get("sawtooth_inclusion") or {}
    saw_detected = bool(
        (isinstance(saw, dict) and (saw.get("allowed") or saw.get("want_include") or saw.get("merges")))
        or any("sawtooth" in p.lower() for p in programs)
        or "Sawtooth_Merge" in (rep.get("programs") or [])
    )
    saw_generated = any("sawtooth" in p.lower() for p in programs) or "Sawtooth_Merge" in programs
    saw_withheld = bool(
        isinstance(rep.get("sawtooth_inclusion"), dict)
        and rep["sawtooth_inclusion"].get("stripped")
    )

    # Slow / Fast / L1 / L2 / L3 area programs
    slow_progs = _area_program_names(programs, "_Area_Slow")
    fast_progs = _area_program_names(programs, "_Area_Fast")
    l1_progs = _area_program_names(programs, "_Area_L1")
    # Also catch Config-style L1 naming
    if not l1_progs:
        l1_progs = [p for p in programs if p.lower().endswith("_area_l1") or "Config" in p]

    expected_program_names: set[str] = set()

    for sp in slow_progs or []:
        expected_program_names.add(sp)
        info = programs.get(sp)
        for rname in SLOW_CORE_ROUTINES:
            rows.append(
                _row(
                    program=sp,
                    routine=rname,
                    because="Transportation Slow routine contract",
                    feature="SLOW",
                    prog_info=info,
                )
            )

    for fp in fast_progs or []:
        expected_program_names.add(fp)
        info = programs.get(fp)
        for rname in FAST_CORE_ROUTINES:
            rows.append(
                _row(
                    program=fp,
                    routine=rname,
                    because="Transportation Fast routine contract",
                    feature="FAST",
                    prog_info=info,
                )
            )
        # Conv_Full — applicable when Full_PE / full logic present in report
        full_applicable = int(rep.get("pe_logic_rungs") or 0) > 0 or bool(
            rep.get("conv_full_status")
        )
        rows.append(
            _row(
                program=fp,
                routine="Conv_Full",
                because="Optional Fast full-PE transport function",
                feature="FAST",
                prog_info=info,
                applicable=full_applicable or ("Conv_Full" in ((info or {}).get("routines") or {})),
            )
        )
        rows.append(
            _row(
                program=fp,
                routine="Merge",
                because="Fast merge routine when merge feature detected",
                feature="MERGE",
                prog_info=info,
                applicable=has_merge_feature
                or ("Merge" in ((info or {}).get("routines") or {})),
                withheld=merge_withheld,
            )
        )

    for lp in l1_progs or []:
        expected_program_names.add(lp)
        info = programs.get(lp)
        for rname in L1_CORE_ROUTINES:
            rows.append(
                _row(
                    program=lp,
                    routine=rname,
                    because="Transportation L1/Config routine contract",
                    feature="L1",
                    prog_info=info,
                )
            )
        rows.append(
            _row(
                program=lp,
                routine="Merge",
                because="L1 merge parameterization when merge feature detected",
                feature="MERGE",
                prog_info=info,
                applicable=has_merge_feature
                or ("Merge" in ((info or {}).get("routines") or {})),
                withheld=merge_withheld,
            )
        )

    # ORI-107: Conv_Speed / FullTime / PETime live on L1 or L2 depending on
    # generated architecture. Attribute expectation to the program that owns
    # them when present; otherwise expect on L2 when L2 exists, else L1.
    l2_progs = _area_program_names(programs, "_Area_L2")
    for lp2 in l2_progs or []:
        expected_program_names.add(lp2)

    def _program_has_routine(pname: str, rname: str) -> bool:
        info = programs.get(pname) if pname else None
        routines = (info or {}).get("routines") or {}
        if isinstance(routines, dict):
            return rname in routines
        if isinstance(routines, (list, tuple, set)):
            return rname in routines
        return False

    for rname in CONFIG_TIMING_ROUTINES:
        owners = [
            p
            for p in list(l1_progs or []) + list(l2_progs or [])
            if _program_has_routine(p, rname)
        ]
        if owners:
            for owner in owners:
                rows.append(
                    _row(
                        program=owner,
                        routine=rname,
                        because="Transportation L1/Config timing routine contract",
                        feature="L1_CONFIG",
                        prog_info=programs.get(owner),
                    )
                )
            continue
        # Not present anywhere — expect on L2 when that program exists (valid
        # Fortna placement), else on L1.
        target = (l2_progs or [None])[0] or (l1_progs or [None])[0]
        if not target:
            continue
        rows.append(
            _row(
                program=target,
                routine=rname,
                because="Transportation L1/Config timing routine contract",
                feature="L1_CONFIG",
                prog_info=programs.get(target),
            )
        )

    # Sorter programs
    sorter_progs = [
        p
        for p in programs
        if "sorter" in p.lower() or p.endswith("Sorter_Track") or "Sorter_Track" in p
    ]
    if sorter_detected and not sorter_progs:
        # Expected program missing entirely
        pname = "Sorter_Track"
        expected_program_names.add(pname)
        for rname in ("Main_Routine", "Encoder", "Track_Induct_Package", "Track_Divert_Package", "Wave_Divert", "Scanner"):
            rows.append(
                _row(
                    program=pname,
                    routine=rname,
                    because="Sorter architecture detected — expected Sorter_Track pack",
                    feature="SORTER",
                    prog_info=None,
                    applicable=True,
                    unsupported=sorter_unsupported,
                    withheld=not sorter_generated,
                )
            )
    for sp in sorter_progs:
        expected_program_names.add(sp)
        info = programs.get(sp)
        # Prefer whichever main name exists
        main_names = {"Main_Routine", "Main"}
        emitted_main = False
        for rname in SORTER_EXPECTED_ROUTINES:
            if rname in main_names and emitted_main:
                continue
            if rname in main_names:
                # Only expect the main that exists, else Main_Routine
                if "Main_Routine" in ((info or {}).get("routines") or {}):
                    if rname != "Main_Routine":
                        continue
                elif "Main" in ((info or {}).get("routines") or {}):
                    if rname != "Main":
                        continue
                else:
                    if rname != "Main_Routine":
                        continue
                emitted_main = True
            rows.append(
                _row(
                    program=sp,
                    routine=rname if rname != "Sorter_Track" else "Main_Routine",
                    because="Existing generalized sorter architecture contract",
                    feature="SORTER",
                    prog_info=info,
                    unsupported=sorter_unsupported,
                )
            )

    # Sawtooth
    saw_progs = [p for p in programs if "sawtooth" in p.lower()]
    if saw_detected and not saw_progs:
        expected_program_names.add("Sawtooth_Merge")
        rows.append(
            _row(
                program="Sawtooth_Merge",
                routine="Main_Routine",
                because="Sawtooth merge evidence detected in RUN",
                feature="SAWTOOTH",
                prog_info=None,
                withheld=saw_withheld or not saw_generated,
            )
        )
    for sp in saw_progs:
        expected_program_names.add(sp)
        info = programs.get(sp)
        for rname in ("Main_Routine", "Sawtooth", "Merge"):
            rows.append(
                _row(
                    program=sp,
                    routine=rname,
                    because="Sawtooth structural pack contract",
                    feature="SAWTOOTH",
                    prog_info=info,
                    applicable=(
                        rname == "Main_Routine"
                        or rname in ((info or {}).get("routines") or {})
                        or saw_generated
                    ),
                    withheld=saw_withheld,
                )
            )

    # Also inventory any other programs' Main_Routine for visibility (not all as defects)
    for pname, info in programs.items():
        if pname in expected_program_names:
            continue
        # Skip library-ish / system unless useful
        rows.append(
            _row(
                program=pname,
                routine="Main_Routine",
                because="Additional emitted program (inventory)",
                feature="OTHER",
                prog_info=info,
                applicable="Main_Routine" in (info.get("routines") or {})
                or "Main" in (info.get("routines") or {}),
            )
        )

    # Summary counts
    summary: dict[str, int] = {
        STATUS_COMPLETE: 0,
        STATUS_PRESENT_PARTIAL: 0,
        STATUS_PLACEHOLDER: 0,
        STATUS_EMPTY: 0,
        STATUS_MISSING_EXPECTED: 0,
        STATUS_WITHHELD_REVIEW: 0,
        STATUS_UNSUPPORTED: 0,
        STATUS_NOT_APPLICABLE: 0,
        STATUS_UNREACHABLE: 0,
        "APPLICABLE": 0,
    }
    for row in rows:
        summary[row.status] = summary.get(row.status, 0) + 1
        if row.status != STATUS_NOT_APPLICABLE:
            summary["APPLICABLE"] = summary.get("APPLICABLE", 0) + 1
        # Map UNREACHABLE into PRESENT_PARTIAL bucket for high-level rollup display
        if row.status == STATUS_UNREACHABLE:
            summary[STATUS_PRESENT_PARTIAL] = summary.get(STATUS_PRESENT_PARTIAL, 0) + 1

    # Issues for non-complete applicable routines
    issues: list[dict[str, Any]] = []
    issue_n = max(1, int(start_issue_n))
    for row in rows:
        if row.status in {
            STATUS_COMPLETE,
            STATUS_NOT_APPLICABLE,
        }:
            continue
        issues.append(_issue_from_row(row, issue_n))
        issue_n += 1

    programs_present = len(programs)
    programs_expected = len(expected_program_names) or programs_present

    return RoutineCoverageReport(
        rows=rows,
        summary=summary,
        programs_expected=programs_expected,
        programs_present=programs_present,
        issues=issues,
    )


__all__ = [
    "STATUS_COMPLETE",
    "STATUS_PRESENT_PARTIAL",
    "STATUS_PLACEHOLDER",
    "STATUS_EMPTY",
    "STATUS_MISSING_EXPECTED",
    "STATUS_WITHHELD_REVIEW",
    "STATUS_UNSUPPORTED",
    "STATUS_NOT_APPLICABLE",
    "STATUS_UNREACHABLE",
    "RoutineCoverageRow",
    "RoutineCoverageReport",
    "analyze_routine_coverage",
    "SLOW_CORE_ROUTINES",
    "FAST_CORE_ROUTINES",
    "L1_CORE_ROUTINES",
]

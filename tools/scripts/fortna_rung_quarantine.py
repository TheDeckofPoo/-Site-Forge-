#!/usr/bin/env python3
"""Safe partial emit — pre-final L5X rung/object quarantine (engineer-first).

Product contract:
  GENERATE → VALIDATE operands → EMIT valid / QUARANTINE localizable /
  FAIL_CLOSED safety-critical / BLOCK only unrecoverable structural defects.

Never invents operational tags. Never deletes Safety protection to enable motion.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from fortna_symbol_closure import (
    CLOSURE_FAIL,
    ALLOWED,
    classify_root,
    collect_declarations,
    operand_root,
    _OPERAND_RE,
    _split_args,
    _looks_like_tag,
)

# Safety / motion-critical patterns — unresolved refs here must FAIL_CLOSED,
# never be stripped in a way that enables motion.
_SAFETY_CRITICAL_RE = re.compile(
    r"(?:"
    r"\.PI\.Tripped\b|"
    r"\.PI\.Reset\b|"
    r"\.PI\.Silence\b|"
    r"_ESZone\d|"
    r"Default_Safety|"
    r"Unassigned_Safety|"
    r"(?:^|[.(])Area\.Run\b|"
    r"\.HMI\.Start\b|"
    r"OTE\([^)]*\.Run\)|"
    r"(?:ESPB|ESLS|ESR|MCR)\d|"
    r"PICKING_ENABLE|"
    r"CombinedEnable|"
    r"Safe_PI|ES_PI20|Safe_Logic|ES_SIL"
    r")",
    re.I,
)

_MOTION_WRITE_RE = re.compile(
    r"OTE\(\s*([A-Za-z_][A-Za-z0-9_]*(?:_Area)?\.Run)\s*\)",
    re.I,
)


@dataclass
class QuarantineIssue:
    issue_id: str
    category: str
    severity: str
    program: str
    routine: str
    rung: str  # number or N/A
    object_device: str
    operand: str
    reason: str
    source: str
    site_forge_action: str
    engineer_action: str
    effect: str  # LOCAL | COMMISSIONING | STRUCTURAL
    classification: str = ""  # LOCALIZABLE | SAFETY_CRITICAL | UNRECOVERABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "CATEGORY": self.category,
            "SEVERITY": self.severity,
            "PROGRAM": self.program or "N/A",
            "ROUTINE": self.routine or "N/A",
            "RUNG NUMBER / RUNG INDEX": self.rung if self.rung != "" else "N/A",
            "OBJECT / DEVICE": self.object_device or "N/A",
            "OPERAND / TAG / ENDPOINT": self.operand or "N/A",
            "REASON": self.reason,
            "SOURCE / PROVENANCE": self.source,
            "SITE FORGE ACTION": self.site_forge_action,
            "ENGINEER ACTION": self.engineer_action,
            "EFFECT": self.effect,
            "classification": self.classification,
            # Back-compat keys used by fortna_build_issues collectors
            "object/device": self.object_device or self.operand or self.issue_id,
            "subsystem": "quarantine",
            "severity/classification": self.severity,
            "reason": self.reason,
            "source/provenance": self.source,
            "what Site Forge did": self.site_forge_action,
            "effect": self.effect,
            "engineer action": self.engineer_action,
            "program": self.program or "N/A",
            "routine": self.routine or "N/A",
            "rung": self.rung if self.rung != "" else "N/A",
            "operand": self.operand or "N/A",
        }


@dataclass
class QuarantineReport:
    ok: bool  # True when final L5X is structurally usable after quarantine
    blocked: bool
    l5x_text: str
    issues: list[QuarantineIssue] = field(default_factory=list)
    quarantined_rung_count: int = 0
    fail_closed_count: int = 0
    structural_blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "blocked": self.blocked,
            "quarantined_rung_count": self.quarantined_rung_count,
            "fail_closed_count": self.fail_closed_count,
            "structural_blockers": list(self.structural_blockers),
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


def _next_issue_id(n: int) -> str:
    return f"SF-{n:04d}"


def _is_safety_critical(operand: str, rung_text: str) -> bool:
    blob = f"{operand}\n{rung_text}"
    if _SAFETY_CRITICAL_RE.search(blob):
        return True
    if _MOTION_WRITE_RE.search(rung_text or ""):
        return True
    return False


# JSR/SBR/RET arguments name Routines (or return params), not Logix tags.
# Quarantining them would NOP the scheduler/call structure — never treat as tags.
_ROUTINE_REF_INST = frozenset({"JSR", "SBR", "RET", "EVENT"})


def _extract_rung_operands(rung_text: str) -> list[str]:
    """Extract tag-like operands from rung Text, excluding routine-call targets."""
    out: list[str] = []
    if not rung_text or rung_text.strip().upper().startswith("NOP"):
        return out
    for inst, args in _OPERAND_RE.findall(rung_text):
        if str(inst or "").upper() in _ROUTINE_REF_INST:
            continue
        for tok in _split_args(args):
            if _looks_like_tag(tok):
                out.append(tok)
    return out


def _placeholder_rung_xml(
    *,
    number: str,
    issue_id: str,
    program: str,
    routine: str,
    operand: str,
    reason: str,
    action: str,
) -> str:
    comment = (
        f"SITE FORGE ISSUE {issue_id}\n"
        f"Program: {program}\n"
        f"Routine: {routine}\n"
        f"Rung: {number}\n"
        f"Operand: {operand}\n"
        f"Reason: {reason}\n"
        f"Site Forge action: {action}\n"
        f"Engineer action: Resolve operand evidence or accept withhold before commissioning."
    )
    comment = comment.replace("]]>", "]]]]><![CDATA[>")
    return (
        f'<Rung Number="{number}" Type="N">'
        f"<Comment><![CDATA[{comment}]]></Comment>"
        f"<Text><![CDATA[NOP();]]></Text>"
        f"</Rung>"
    )


def _rung_has_unrecoverable_shape(rung_xml: str) -> bool:
    """True when the rung XML itself is malformed beyond safe rewrite."""
    if "<Text>" not in rung_xml:
        return True
    if not re.search(r"<Text><!\[CDATA\[.*?\]\]></Text>", rung_xml, re.S):
        return True
    return False


def _enclosing_names(text: str, pos: int) -> tuple[str, str]:
    """Best-effort Program/Routine names from text before position pos."""
    before = text[:pos]
    pname = "N/A"
    rname = "N/A"
    for m in re.finditer(r"<Program\b([^>]*)>", before):
        nm = re.search(r'(?<![A-Za-z0-9_])Name="([^"]+)"', m.group(1))
        if nm:
            pname = nm.group(1)
    for m in re.finditer(r"<Routine\b([^>]*)>", before):
        nm = re.search(r'(?<![A-Za-z0-9_])Name="([^"]+)"', m.group(1))
        if nm:
            rname = nm.group(1)
    return pname, rname


def quarantine_l5x(
    l5x_text: str,
    *,
    external_bindings: set[str] | None = None,
    start_issue_n: int = 1,
) -> QuarantineReport:
    """Scan candidate L5X; quarantine localizable invalid rungs; fail-close Safety.

    Returns rewritten L5X text + issue punch-list. Sets blocked=True only when
    the controller cannot be made structurally valid / safely fail-closed.
    """
    text = l5x_text or ""
    if not text.strip():
        return QuarantineReport(
            ok=False,
            blocked=True,
            l5x_text=text,
            structural_blockers=["empty L5X candidate"],
        )
    if "<Controller" not in text:
        return QuarantineReport(
            ok=False,
            blocked=True,
            l5x_text=text,
            structural_blockers=["controller/root cannot be established"],
        )

    decl = collect_declarations(text)
    ext = set(external_bindings or [])
    issues: list[QuarantineIssue] = []
    issue_n = max(1, int(start_issue_n))
    quarantined = 0
    fail_closed = 0
    blockers: list[str] = []

    replacements: list[tuple[str, str]] = []

    def _attr_name(attrs: str) -> str:
        # Prefer bare Name= over MainRoutineName= / similar compound attrs.
        m = re.search(r'(?<![A-Za-z0-9_])Name="([^"]+)"', attrs or "")
        return m.group(1) if m else "N/A"

    for pm in re.finditer(
        r"(<Program\b)([^>]*)(>)(.*?)(</Program>)",
        text,
        re.S,
    ):
        pname = _attr_name(pm.group(2))
        pbody = pm.group(4)
        new_pbody = pbody
        for rm in re.finditer(
            r"(<Routine\b)([^>]*)(>)(.*?)(</Routine>)",
            pbody,
            re.S,
        ):
            rname = _attr_name(rm.group(2))
            rbody = rm.group(4)
            new_rbody = rbody
            for rung_m in re.finditer(
                r'(<Rung\b[^>]*Number=")(\d+)("[^>]*>)(.*?)(</Rung>)',
                rbody,
                re.S,
            ):
                full = rung_m.group(0)
                number = rung_m.group(2)
                inner = rung_m.group(4)
                text_m = re.search(
                    r"<Text><!\[CDATA\[(.*?)\]\]></Text>",
                    inner,
                    re.S,
                )
                if not text_m:
                    if _rung_has_unrecoverable_shape(full):
                        blockers.append(
                            f"malformed rung Program:{pname}/Routine:{rname}/Rung:{number}"
                        )
                    continue
                rung_text = text_m.group(1)
                if not rung_text or rung_text.strip().upper().startswith("NOP"):
                    continue

                bad_operands: list[str] = []
                for op in _extract_rung_operands(rung_text):
                    root = operand_root(op)
                    finding = classify_root(
                        root,
                        declarations=decl,
                        external_bindings=ext,
                        producer=f"Program:{pname}/Routine:{rname}",
                        operand=op,
                    )
                    is_fail = (
                        finding.classification == CLOSURE_FAIL
                        or finding.classification not in ALLOWED
                    )
                    if is_fail:
                        bad_operands.append(op)

                if not bad_operands:
                    continue

                primary = bad_operands[0]
                safety = any(
                    _is_safety_critical(op, rung_text) for op in bad_operands
                ) or _is_safety_critical(primary, rung_text)

                iid = _next_issue_id(issue_n)
                issue_n += 1

                if safety:
                    action = "FAIL_CLOSED"
                    category = "QUARANTINED LOGIC"
                    severity = "SAFETY_FAIL_CLOSED"
                    effect = "COMMISSIONING"
                    reason = (
                        "Unresolved Safety/motion-critical operand — function fail-closed; "
                        "invalid rung replaced with Studio-valid NOP placeholder. "
                        f"Operands: {', '.join(bad_operands[:6])}."
                    )
                    eng = (
                        "Prove Safety/run permissive ownership before enabling motion; "
                        "do not commission until this issue is closed."
                    )
                    fail_closed += 1
                    classification = "SAFETY_CRITICAL"
                    action_note = (
                        "Affected function fail-closed; safe NOP placeholder emitted."
                    )
                else:
                    action = "QUARANTINED"
                    category = "QUARANTINED LOGIC"
                    severity = "UNDECLARED_OPERAND"
                    effect = "LOCAL"
                    reason = (
                        "Operand does not resolve to an emitted operational Logix tag. "
                        "Invalid rung withheld; Program/Routine retained. "
                        f"Operands: {', '.join(bad_operands[:6])}."
                    )
                    eng = (
                        "Declare/bind the operand or accept withhold; "
                        "re-generate or hand-complete the rung before commissioning."
                    )
                    quarantined += 1
                    classification = "LOCALIZABLE"
                    action_note = (
                        "Invalid condition excluded/quarantined; remaining valid logic emitted."
                    )

                issues.append(
                    QuarantineIssue(
                        issue_id=iid,
                        category=category,
                        severity=severity,
                        program=pname,
                        routine=rname,
                        rung=number,
                        object_device=operand_root(primary) or primary,
                        operand=primary,
                        reason=reason,
                        source="fortna_rung_quarantine / symbol_closure",
                        site_forge_action=action,
                        engineer_action=eng,
                        effect=effect,
                        classification=classification,
                    )
                )

                new_rung = _placeholder_rung_xml(
                    number=number,
                    issue_id=iid,
                    program=pname,
                    routine=rname,
                    operand=primary,
                    reason=reason.split(".")[0] + ".",
                    action=action_note,
                )
                new_rbody = new_rbody.replace(full, new_rung, 1)

            if new_rbody != rbody:
                old_routine = rm.group(0)
                new_routine = (
                    rm.group(1)
                    + rm.group(2)
                    + rm.group(3)
                    + new_rbody
                    + rm.group(5)
                )
                new_pbody = new_pbody.replace(old_routine, new_routine, 1)

        if new_pbody != pbody:
            old_prog = pm.group(0)
            new_prog = (
                pm.group(1)
                + pm.group(2)
                + pm.group(3)
                + new_pbody
                + pm.group(5)
            )
            replacements.append((old_prog, new_prog))

    out_text = text
    for old, new in replacements:
        out_text = out_text.replace(old, new, 1)

    # Routine completeness: empty RLLContent gets a Studio-valid NOP placeholder.
    def _fill_empty_rll(m: re.Match[str]) -> str:
        nonlocal issue_n, quarantined
        if re.search(r"<Rung\b", m.group(2) or ""):
            return m.group(0)
        pname, rname = _enclosing_names(out_text, m.start())
        iid = _next_issue_id(issue_n)
        issue_n += 1
        quarantined += 1
        issues.append(
            QuarantineIssue(
                issue_id=iid,
                category="QUARANTINED LOGIC",
                severity="ROUTINE_INCOMPLETE",
                program=pname,
                routine=rname,
                rung="0",
                object_device=rname if rname != "N/A" else "N/A",
                operand="N/A",
                reason="Empty RLLContent retained with Studio-valid NOP placeholder.",
                source="fortna_rung_quarantine / routine_completeness",
                site_forge_action="QUARANTINED",
                engineer_action="Complete routine logic or accept placeholder.",
                effect="LOCAL",
                classification="LOCALIZABLE",
            )
        )
        ph = _placeholder_rung_xml(
            number="0",
            issue_id=iid,
            program=pname,
            routine=rname,
            operand="N/A",
            reason="Empty routine placeholder.",
            action="Placeholder emitted.",
        )
        return f"{m.group(1)}{ph}{m.group(3)}"

    out_text = re.sub(
        r"(<RLLContent>)(.*?)(</RLLContent>)",
        _fill_empty_rll,
        out_text,
        flags=re.S,
    )

    blocked = bool(blockers)
    return QuarantineReport(
        ok=not blocked,
        blocked=blocked,
        l5x_text=out_text,
        issues=issues,
        quarantined_rung_count=quarantined,
        fail_closed_count=fail_closed,
        structural_blockers=blockers,
    )


def actionable_issue_count(report_or_manifest: dict[str, Any] | None) -> int:
    """Count actionable BUILD_ISSUES entries for the UI badge."""
    if not isinstance(report_or_manifest, dict):
        return 0
    sections = report_or_manifest.get("sections")
    if isinstance(sections, dict):
        n = 0
        for items in sections.values():
            if isinstance(items, list):
                n += len(items)
        return n
    from fortna_build_issues import SECTION_ORDER  # local import avoids load cycles

    n = 0
    for name in SECTION_ORDER:
        items = report_or_manifest.get(name)
        if isinstance(items, list):
            n += len(items)
    if n:
        return n
    q = report_or_manifest.get("rung_quarantine") or report_or_manifest.get("quarantine")
    if isinstance(q, dict):
        return int(q.get("issue_count") or len(q.get("issues") or []))
    return 0


__all__ = [
    "QuarantineIssue",
    "QuarantineReport",
    "quarantine_l5x",
    "actionable_issue_count",
]

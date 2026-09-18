#!/usr/bin/env python3
"""Pre-generation / post-emit symbol closure invariant (Gate 7).

Every emitted operand root must resolve to one of:
  DECLARED | MODULE_BOUND | PROGRAM_LOCAL | AOI_MEMBER | EXPLICIT_EXTERNAL_BINDING

Else FAIL with producer → operand → expected owner → missing evidence.

Does not invent BOOL tags or whitelist unknowns.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

CLOSURE_DECLARED = "DECLARED"
CLOSURE_MODULE_BOUND = "MODULE_BOUND"
CLOSURE_PROGRAM_LOCAL = "PROGRAM_LOCAL"
CLOSURE_AOI_MEMBER = "AOI_MEMBER"
CLOSURE_EXTERNAL = "EXPLICIT_EXTERNAL_BINDING"
CLOSURE_SYSTEM = "SYSTEM_PLACEHOLDER"
CLOSURE_FAIL = "FAIL"

ALLOWED = frozenset(
    {
        CLOSURE_DECLARED,
        CLOSURE_MODULE_BOUND,
        CLOSURE_PROGRAM_LOCAL,
        CLOSURE_AOI_MEMBER,
        CLOSURE_EXTERNAL,
        CLOSURE_SYSTEM,
    }
)

_SYSTEM_BASES = frozenset(
    {
        "NO_POINTPLACEHOLDER",
        "ALWAYSON",
        "ALWAYSOFF",
        "NEVERON",
        "NEVEROFF",
        "NO_PE",
        "NO_CONV",
        "NO_MS",
        "NO_VFD",
        "NO_ENC",
        "NO_PS",
        "NO_AIRPRESS",
        "NO_ADDITIONALFLT",
        "NO_ES",
        "NO_CS",
    }
)

# Ethernet-only VFD command suffixes that must never appear as bare undeclared BOOL roots.
ETHERNET_VFD_COMMAND_SUFFIXES = frozenset(
    {
        "JOG",
        "CLR_FLT",
        "CLEAR_FLT",
        "CLEARFAULTS",
        "DIR_BIT0",
        "DIR_BIT1",
        "LOC_CTRL",
        "MOP_INC",
        "MOP_DEC",
        "ACC_BIT0",
        "ACC_BIT1",
        "DEC_BIT0",
        "DEC_BIT1",
    }
)

_VFD_OPTIONAL_ROOT_RE = re.compile(
    r"^(?:T_)?(?:VFD\d+[A-Z]?|P\d+[A-Z]?_VFD)_("
    + "|".join(sorted(ETHERNET_VFD_COMMAND_SUFFIXES, key=len, reverse=True))
    + r")$",
    re.I,
)

_OPERAND_RE = re.compile(
    r"\b(XIC|XIO|OTE|OTL|OTU|ONS|OSR|OSF|JSR|SBR|RET|MOV|COP|CPS|CPT|"
    r"ADD|SUB|MUL|DIV|EQU|NEQ|LES|GRT|LEQ|GEQ|LIM|MEQ|CMP|TND|TOF|TON|RTO|"
    r"CTU|CTD|RES|MSG|GSV|SSV)\(([^)]+)\)",
    re.I,
)


@dataclass
class ClosureFinding:
    operand: str
    root: str
    producer: str
    classification: str
    expected_owner: str
    missing_evidence: str = ""
    routine: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "operand": self.operand,
            "root": self.root,
            "producer": self.producer,
            "classification": self.classification,
            "expected_owner": self.expected_owner,
            "missing_evidence": self.missing_evidence,
            "routine": self.routine,
        }


@dataclass
class ClosureReport:
    ok: bool
    findings: list[ClosureFinding] = field(default_factory=list)
    failures: list[ClosureFinding] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "counts": dict(self.counts),
            "failure_count": len(self.failures),
            "failures": [f.to_dict() for f in self.failures],
            "findings_sample": [f.to_dict() for f in self.findings[:40]],
        }


def operand_root(operand: str) -> str:
    op = (operand or "").strip()
    if not op:
        return ""
    if ":" in op:
        return op.split(":", 1)[0].strip()
    return op.split(".", 1)[0].strip()


def is_ethernet_vfd_command_root(root: str) -> bool:
    """True for bare VFD###_JOG / P###_VFD_CLR_FLT style dangling command symbols."""
    r = (root or "").strip()
    if not r:
        return False
    if _VFD_OPTIONAL_ROOT_RE.match(r):
        return True
    # Also catch trailing role alone when producer used role as base
    suf = r.upper().rsplit("_", 1)[-1] if "_" in r else r.upper()
    if r.upper().startswith(("VFD", "P")) and suf in ETHERNET_VFD_COMMAND_SUFFIXES:
        return True
    return False


def extract_operands_from_l5x(l5x_text: str) -> list[tuple[str, str, str]]:
    """Return (producer, operand, routine) from RLL Text CDATA and ST CDATA."""
    out: list[tuple[str, str, str]] = []
    if not l5x_text:
        return out

    # RLL programs / routines
    for pm in re.finditer(
        r'<Program\b[^>]*Name="([^"]+)"[^>]*>(.*?)</Program>',
        l5x_text,
        re.S,
    ):
        pname = pm.group(1)
        body = pm.group(2)
        for rm in re.finditer(
            r'<Routine\b[^>]*Name="([^"]+)"[^>]*>(.*?)</Routine>',
            body,
            re.S,
        ):
            rname = rm.group(1)
            producer = f"Program:{pname}/Routine:{rname}"
            rbody = rm.group(2)
            for text in re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", rbody, re.S):
                if not text or text.strip().upper().startswith("NOP"):
                    continue
                for _inst, args in _OPERAND_RE.findall(text):
                    # AOI / multi-arg: take comma-separated tokens that look like tags
                    for tok in _split_args(args):
                        if _looks_like_tag(tok):
                            out.append((producer, tok, rname))
            for text in re.findall(r"<!\[CDATA\[(.*?)\]\]>", rbody, re.S):
                # ST lines: Tag.Member := Other.Member;
                if " := " in text or ":=" in text:
                    for tok in re.findall(
                        r"\b([A-Za-z_][A-Za-z0-9_]*(?::[IO]\.[A-Za-z0-9_\[\]\.]+|\.[A-Za-z0-9_\.]+)?)\b",
                        text,
                    ):
                        if _looks_like_tag(tok) and not tok.upper().startswith(
                            ("IF", "THEN", "ELSE", "END", "FOR", "WHILE", "CASE")
                        ):
                            out.append((producer, tok, rname))
    return out


def _split_args(args: str) -> list[str]:
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    for ch in args or "":
        if ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur).strip())
    return [p for p in parts if p]


def _looks_like_tag(tok: str) -> bool:
    t = (tok or "").strip()
    if not t or t[0] in "0123456789\"'":
        return False
    if re.match(r"^-?\d", t):
        return False
    if t.upper() in {"TRUE", "FALSE", "NULL"}:
        return False
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*([:.]|$)", t))


def collect_declarations(l5x_text: str) -> dict[str, dict[str, Any]]:
    """Map root name → {scope, datatype, kind}."""
    decl: dict[str, dict[str, Any]] = {}
    if not l5x_text:
        return decl

    # Modules
    for m in re.finditer(r'<Module\b[^>]*\bName="([^"]+)"', l5x_text):
        name = m.group(1)
        decl[name] = {
            "scope": "module",
            "datatype": "MODULE",
            "kind": CLOSURE_MODULE_BOUND,
            "owner": "ModuleTree",
        }

    # Controller tags (first Tags under Controller)
    for cm in re.finditer(
        r"<Controller\b[^>]*>(.*?)</Controller>",
        l5x_text,
        re.S,
    ):
        cbody = cm.group(1)
        # Stop at Programs for controller Tags only
        tags_m = re.search(r"<Tags>(.*?)</Tags>", cbody, re.S)
        if tags_m:
            for tm in re.finditer(
                r'<Tag\b[^>]*\bName="([^"]+)"[^>]*\bDataType="([^"]+)"',
                tags_m.group(1),
            ):
                decl.setdefault(
                    tm.group(1),
                    {
                        "scope": "controller",
                        "datatype": tm.group(2),
                        "kind": CLOSURE_DECLARED,
                        "owner": "controller_tags",
                    },
                )
        break

    # Program-local tags
    for pm in re.finditer(
        r'<Program\b[^>]*Name="([^"]+)"[^>]*>(.*?)</Program>',
        l5x_text,
        re.S,
    ):
        pname = pm.group(1)
        tags_m = re.search(r"<Tags>(.*?)</Tags>", pm.group(2), re.S)
        if not tags_m:
            continue
        for tm in re.finditer(
            r'<Tag\b[^>]*\bName="([^"]+)"[^>]*\bDataType="([^"]+)"',
            tags_m.group(1),
        ):
            name = tm.group(1)
            if name not in decl:
                decl[name] = {
                    "scope": f"program:{pname}",
                    "datatype": tm.group(2),
                    "kind": CLOSURE_PROGRAM_LOCAL,
                    "owner": f"Program:{pname}",
                }

    # AOI definitions (AddOnInstructionDefinitions) — instance params are AOI_MEMBER
    for am in re.finditer(
        r'<AddOnInstructionDefinition\b[^>]*\bName="([^"]+)"',
        l5x_text,
    ):
        decl.setdefault(
            am.group(1),
            {
                "scope": "aoi_definition",
                "datatype": "AOI",
                "kind": CLOSURE_AOI_MEMBER,
                "owner": "AOIDefinitions",
            },
        )

    return decl


def classify_root(
    root: str,
    *,
    declarations: dict[str, dict[str, Any]],
    external_bindings: set[str] | None = None,
    producer: str = "",
    operand: str = "",
) -> ClosureFinding:
    r = (root or "").strip()
    ext = {str(x).strip() for x in (external_bindings or set()) if str(x).strip()}
    if not r:
        return ClosureFinding(
            operand=operand,
            root=r,
            producer=producer or "unknown",
            classification=CLOSURE_SYSTEM,
            expected_owner="n/a",
        )
    ru = r.upper()
    if ru in _SYSTEM_BASES or ru.startswith("S:"):
        return ClosureFinding(
            operand=operand,
            root=r,
            producer=producer or "unknown",
            classification=CLOSURE_SYSTEM,
            expected_owner="system/placeholder",
        )
    if r in declarations:
        d = declarations[r]
        return ClosureFinding(
            operand=operand,
            root=r,
            producer=producer or d.get("owner") or "declaration",
            classification=str(d.get("kind") or CLOSURE_DECLARED),
            expected_owner=str(d.get("owner") or d.get("scope") or "declaration"),
        )
    # Case-insensitive fallback
    for k, d in declarations.items():
        if k.lower() == r.lower():
            return ClosureFinding(
                operand=operand,
                root=r,
                producer=producer or d.get("owner") or "declaration",
                classification=str(d.get("kind") or CLOSURE_DECLARED),
                expected_owner=str(d.get("owner") or d.get("scope") or "declaration"),
            )
    if r in ext or ru in {x.upper() for x in ext}:
        return ClosureFinding(
            operand=operand,
            root=r,
            producer=producer or "explicit_external_binding",
            classification=CLOSURE_EXTERNAL,
            expected_owner="EXPLICIT_EXTERNAL_BINDING",
        )

    # Dangling Ethernet VFD command role — expected owner is VFD_UDT when ethernet mode
    if is_ethernet_vfd_command_root(r):
        return ClosureFinding(
            operand=operand,
            root=r,
            producer=producer or "IO_MAP/template",
            classification=CLOSURE_FAIL,
            expected_owner="VFD_UDT.VFDOut.* (ETHERNET_VFD_UDT only) — not discrete BOOL",
            missing_evidence=(
                "Ethernet VFD command role referenced without VFD_UDT declaration / "
                "module binding / SpdControl proof"
            ),
        )

    return ClosureFinding(
        operand=operand,
        root=r,
        producer=producer or "unknown",
        classification=CLOSURE_FAIL,
        expected_owner="controller_or_program_declaration",
        missing_evidence="No DECLARED|MODULE_BOUND|PROGRAM_LOCAL|AOI_MEMBER|EXTERNAL binding",
    )


def check_symbol_closure(
    l5x_text: str,
    *,
    external_bindings: set[str] | None = None,
    producers_filter: set[str] | None = None,
    fail_iomap_unknowns: bool = True,
    fail_ethernet_vfd_command_leaks: bool = True,
) -> ClosureReport:
    """Fail-closed symbol closure over emitted L5X operands.

    Hard-fail policy (Gate 7):
      - IO_MAP CP_I/CP_O unknown roots → FAIL
      - Ethernet optional VFD command roots (VFD###_JOG, …) without declaration → FAIL
    Other programs may reference library-sealed AOI internals; those are classified
    but only escalate when they match the hard-fail policy (or producers_filter).
    """
    decl = collect_declarations(l5x_text)
    findings: list[ClosureFinding] = []
    failures: list[ClosureFinding] = []
    counts: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()

    for producer, operand, routine in extract_operands_from_l5x(l5x_text):
        if producers_filter and not any(p in producer for p in producers_filter):
            continue
        root = operand_root(operand)
        key = (producer, root)
        if key in seen:
            continue
        seen.add(key)
        finding = classify_root(
            root,
            declarations=decl,
            external_bindings=external_bindings,
            producer=producer,
            operand=operand,
        )
        finding.routine = routine
        findings.append(finding)
        counts[finding.classification] = counts.get(finding.classification, 0) + 1
        is_fail = (
            finding.classification == CLOSURE_FAIL
            or finding.classification not in ALLOWED
        )
        if not is_fail:
            continue
        in_iomap = "Program:IO_MAP" in producer or routine.upper() in {"CP_I", "CP_O"}
        eth_leak = is_ethernet_vfd_command_root(root)
        if producers_filter:
            failures.append(finding)
        elif fail_iomap_unknowns and in_iomap:
            failures.append(finding)
        elif fail_ethernet_vfd_command_leaks and eth_leak:
            failures.append(finding)

    return ClosureReport(
        ok=not failures,
        findings=findings,
        failures=failures,
        counts=counts,
    )


def closure_failure_messages(report: ClosureReport, *, limit: int = 8) -> list[str]:
    msgs: list[str] = []
    for f in report.failures[:limit]:
        msgs.append(
            "BUILD FAILED: symbol closure — "
            f"producer={f.producer} operand={f.operand} root={f.root} "
            f"expected_owner={f.expected_owner} missing={f.missing_evidence or 'declaration'}"
        )
    if len(report.failures) > limit:
        msgs.append(
            f"BUILD FAILED: symbol closure — +{len(report.failures) - limit} more unresolved roots"
        )
    return msgs

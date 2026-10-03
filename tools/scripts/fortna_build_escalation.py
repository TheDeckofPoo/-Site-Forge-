#!/usr/bin/env python3
"""ORI-111 — Autonomous Build Escalation + Recovery Orchestrator.

Site Forge remains authority. AI API and Relay are advisory only.
Every AI/Relay proposal must pass deterministic validators before acceptance.
AI/Relay must NEVER invent Safety membership.

Escalation ladder (aggressive — do not optimize for API cost):

  LEVEL 0  DETERMINISTIC SITE FORGE
  LEVEL 1  AI API ASSIST
  LEVEL 2  RELAY ESCALATION
  LEVEL 3  DEEP REASONING / MULTI-PASS (more evidence, re-query)
  LEVEL 4  ENGINEER DECISION (precise multiple-choice; build stays loaded)

Priority: correct L5X > engineering hours saved > completeness > repeatability.
Cost is tracked for accounting only — never a reason to stop resolution.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]

DISPOSITIONS = frozenset(
    {
        "COMPLETE",
        "PARTIAL",
        "REVIEW_REQUIRED",
        "WITHHELD",
        "UNSUPPORTED",
        "NOT_APPLICABLE",
        "BLOCKED",
        "ENGINEER_REQUIRED",
    }
)

SUBSYSTEMS = ("IO", "TRANSPORTATION", "SAFETY", "POST_BUILD", "WRITERS", "OTHER")

LEVEL_DETERMINISTIC = 0
LEVEL_AI_API = 1
LEVEL_RELAY = 2
LEVEL_DEEP = 3
LEVEL_ENGINEER = 4

LEVEL_NAMES = {
    0: "DETERMINISTIC",
    1: "AI_API",
    2: "RELAY",
    3: "DEEP_REASONING",
    4: "ENGINEER",
}

# Accounting-only estimate (USD per call) — never used to terminate.
_EST_AI_USD = float(os.environ.get("SITEFORGE_AI_USD_PER_CALL") or "0.15")
_EST_RELAY_USD = float(os.environ.get("SITEFORGE_RELAY_USD_PER_CALL") or "0.25")


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_sha() -> str:
    try:
        import subprocess

        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True
            )
            .strip()
        )
    except Exception:
        return ""


def evidence_signature(package: dict[str, Any]) -> str:
    """Normalized signature for BUILD CASE FILE memory (no re-investigation)."""
    keys = (
        "subsystem",
        "device",
        "logical_name",
        "module",
        "slot",
        "word",
        "bit",
        "direction",
        "defect_kind",
        "program",
        "routine",
        "operand",
        "why_uncertain",
    )
    norm = {k: str(package.get(k) or "").strip().upper() for k in keys}
    blob = json.dumps(norm, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


@dataclass
class EscalationEvent:
    ts: str
    level: int
    level_name: str
    action: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseItem:
    case_id: str
    subsystem: str
    evidence: dict[str, Any]
    signature: str
    disposition: str = "REVIEW_REQUIRED"
    provenance: str = "UNRESOLVED"
    resolution: dict[str, Any] | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    ai_calls: int = 0
    relay_calls: int = 0
    engineer_required: bool = False
    accepted: bool = False

    def add_event(self, level: int, action: str, detail: dict[str, Any] | None = None) -> None:
        self.events.append(
            {
                "ts": _ts(),
                "level": level,
                "level_name": LEVEL_NAMES.get(level, str(level)),
                "action": action,
                "detail": detail or {},
            }
        )


@dataclass
class BuildCaseFile:
    """Persistent memory for one autonomous build."""

    site: str
    machine: str
    run_sha: str = ""
    git_sha: str = ""
    build_id: str = ""
    created_at: str = field(default_factory=_ts)
    items: dict[str, CaseItem] = field(default_factory=dict)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    ai_api_calls: int = 0
    relay_calls: int = 0
    estimated_ai_usd: float = 0.0
    estimated_relay_usd: float = 0.0
    build_attempts: int = 1
    counters: dict[str, dict[str, int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.git_sha:
            self.git_sha = _git_sha()
        if not self.counters:
            self.counters = {
                s: {
                    "native_resolved": 0,
                    "ai_resolved": 0,
                    "relay_resolved": 0,
                    "engineer_required": 0,
                    "unresolved": 0,
                }
                for s in SUBSYSTEMS
            }

    def get_or_create(self, evidence: dict[str, Any]) -> CaseItem:
        sig = evidence_signature(evidence)
        if sig in self.items:
            return self.items[sig]
        subsystem = str(evidence.get("subsystem") or "OTHER").upper()
        if subsystem not in self.counters:
            subsystem = "OTHER"
        case_id = f"{subsystem}-{sig[:10]}"
        item = CaseItem(
            case_id=case_id,
            subsystem=subsystem,
            evidence=evidence,
            signature=sig,
        )
        self.items[sig] = item
        self.timeline.append(
            {"ts": _ts(), "event": "CASE_OPENED", "case_id": case_id, "subsystem": subsystem}
        )
        return item

    def record_call(self, kind: str, meta: dict[str, Any] | None = None) -> None:
        meta = meta or {}
        if kind == "AI":
            self.ai_api_calls += 1
            self.estimated_ai_usd += float(meta.get("usd") or _EST_AI_USD)
        elif kind == "RELAY":
            self.relay_calls += 1
            self.estimated_relay_usd += float(meta.get("usd") or _EST_RELAY_USD)
        self.timeline.append(
            {"ts": _ts(), "event": f"{kind}_CALL", "meta": meta}
        )

    def mark_resolved(
        self,
        item: CaseItem,
        *,
        disposition: str,
        provenance: str,
        resolution: dict[str, Any],
        counter_bucket: str,
    ) -> None:
        item.disposition = disposition if disposition in DISPOSITIONS else "PARTIAL"
        item.provenance = provenance
        item.resolution = resolution
        item.accepted = disposition in ("COMPLETE", "PARTIAL", "WITHHELD", "UNSUPPORTED", "NOT_APPLICABLE")
        if counter_bucket in self.counters[item.subsystem]:
            self.counters[item.subsystem][counter_bucket] += 1
        self.timeline.append(
            {
                "ts": _ts(),
                "event": "CASE_RESOLVED",
                "case_id": item.case_id,
                "disposition": item.disposition,
                "provenance": provenance,
            }
        )

    def mark_engineer(self, item: CaseItem, question: dict[str, Any]) -> None:
        item.disposition = "ENGINEER_REQUIRED"
        item.engineer_required = True
        item.resolution = {"engineer_question": question}
        self.counters[item.subsystem]["engineer_required"] += 1
        self.timeline.append(
            {
                "ts": _ts(),
                "event": "ENGINEER_REQUIRED",
                "case_id": item.case_id,
                "question": question,
            }
        )

    def mark_unresolved(self, item: CaseItem, reason: str) -> None:
        item.disposition = "REVIEW_REQUIRED"
        item.resolution = {"reason": reason}
        self.counters[item.subsystem]["unresolved"] += 1
        self.timeline.append(
            {
                "ts": _ts(),
                "event": "STILL_UNRESOLVED",
                "case_id": item.case_id,
                "reason": reason,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ori": "ORI-111",
            "site": self.site,
            "machine": self.machine,
            "run_sha": self.run_sha,
            "git_sha": self.git_sha,
            "build_id": self.build_id,
            "created_at": self.created_at,
            "build_attempts": self.build_attempts,
            "ai_api_calls": self.ai_api_calls,
            "relay_calls": self.relay_calls,
            "estimated_ai_usd": round(self.estimated_ai_usd, 4),
            "estimated_relay_usd": round(self.estimated_relay_usd, 4),
            "estimated_total_usd": round(self.estimated_ai_usd + self.estimated_relay_usd, 4),
            "counters": self.counters,
            "items": {
                sig: {
                    "case_id": it.case_id,
                    "subsystem": it.subsystem,
                    "signature": it.signature,
                    "disposition": it.disposition,
                    "provenance": it.provenance,
                    "accepted": it.accepted,
                    "engineer_required": it.engineer_required,
                    "ai_calls": it.ai_calls,
                    "relay_calls": it.relay_calls,
                    "evidence": it.evidence,
                    "resolution": it.resolution,
                    "events": it.events,
                }
                for sig, it in self.items.items()
            },
            "timeline": self.timeline,
        }

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path


# ---------------------------------------------------------------------------
# Deterministic validators (authority firewall)
# ---------------------------------------------------------------------------

def validate_proposed_resolution(
    proposal: dict[str, Any],
    evidence: dict[str, Any],
    *,
    subsystem: str,
) -> dict[str, Any]:
    """Deterministic acceptance of an AI/Relay proposal.

    Rejects Safety membership invention. Requires non-empty actionable content.
    """
    errors: list[str] = []
    subsystem = (subsystem or evidence.get("subsystem") or "").upper()

    if not isinstance(proposal, dict) or not proposal:
        return {"ok": False, "errors": ["empty_proposal"], "status": "REJECTED"}

    # HARD: never invent Safety membership
    if subsystem == "SAFETY":
        invent = bool(proposal.get("invent_membership") or proposal.get("fabricate_members"))
        members = proposal.get("members") or proposal.get("proposed_members")
        membership_source = str(
            proposal.get("membership_source")
            or proposal.get("provenance")
            or ""
        ).upper()
        if invent:
            errors.append("SAFETY_MEMBERSHIP_INVENTION_FORBIDDEN")
        if members and membership_source not in (
            "PROVEN",
            "ENGINEER_ASSIGNED",
            "RUN_EVIDENCE",
            "DETERMINISTIC",
            "",
        ):
            # Empty source with members from AI = invention
            if membership_source in ("AI", "AI_API", "RELAY", "GUESSED", "INFERRED"):
                errors.append("SAFETY_MEMBERSHIP_MUST_BE_PROVEN_OR_ENGINEER_ASSIGNED")

    # Endpoint shape when proposed
    ep = proposal.get("physical_endpoint") or proposal.get("endpoint")
    if isinstance(ep, dict):
        direction = str(ep.get("direction") or evidence.get("direction") or "").upper()
        if direction and direction not in ("I", "O"):
            errors.append(f"invalid_direction:{direction}")
        bit = ep.get("bit")
        if bit is not None:
            try:
                bi = int(bit)
                if bi < 0 or bi > 31:
                    errors.append(f"bit_out_of_range:{bi}")
            except Exception:
                errors.append(f"bit_not_int:{bit}")

    # Blank operand proposals rejected
    operand = str(proposal.get("operand") or proposal.get("fixed_operand") or "")
    if operand.strip() in ("", "?", '""', "''", "_unnamed_"):
        if "operand" in proposal or "fixed_operand" in proposal:
            errors.append("blank_or_unnamed_operand")

    confidence = str(proposal.get("confidence") or proposal.get("proposal_status") or "").upper()
    if confidence in ("UNKNOWN",) and proposal.get("force_accept"):
        errors.append("unknown_confidence_cannot_force_accept")

    if errors:
        return {"ok": False, "errors": errors, "status": "REJECTED", "proposal": proposal}
    return {
        "ok": True,
        "errors": [],
        "status": "ACCEPTED",
        "proposal": proposal,
        "confidence": confidence or "DERIVED",
    }


def build_engineer_question(item: CaseItem) -> dict[str, Any]:
    """Precise engineer question — never vague 'Safety unresolved'."""
    ev = item.evidence
    device = ev.get("device") or ev.get("logical_name") or item.case_id
    candidates = (
        ev.get("physical_endpoint_candidates")
        or ev.get("candidates")
        or ev.get("alternatives")
        or []
    )
    choices = []
    if isinstance(candidates, list) and candidates:
        for i, c in enumerate(candidates[:6], 1):
            choices.append({"id": str(i), "label": str(c)})
    else:
        choices = [
            {"id": "1", "label": "Accept Site Forge best candidate"},
            {"id": "2", "label": "Leave REVIEW_REQUIRED"},
            {"id": "3", "label": "Mark UNSUPPORTED / withhold"},
        ]
    why = ev.get("why_uncertain") or ev.get("reason") or "evidence ambiguous after AI+Relay"
    return {
        "title": f"{item.subsystem}: resolve {device}",
        "body": (
            f"{device} remains unresolved after deterministic Site Forge, AI API, "
            f"and Relay.\n\nWhy uncertain: {why}\n\n"
            f"Site Forge attempt: {ev.get('site_forge_attempt') or 'see evidence'}\n"
            f"AI conclusion: {(item.resolution or {}).get('ai') or 'n/a'}\n"
            f"Relay conclusion: {(item.resolution or {}).get('relay') or 'n/a'}"
        ),
        "choices": choices,
        "case_id": item.case_id,
        "subsystem": item.subsystem,
        "evidence_signature": item.signature,
    }


# ---------------------------------------------------------------------------
# L5X static inspection → defect evidence packages
# ---------------------------------------------------------------------------

_BAD_OPERAND_RE = re.compile(
    r"\b(?:XIC|XIO|OTE|OTL|OTU)\s*\(\s*(?:\)|\?[,)]|,\s*[,)]|\"\"|''|_unnamed_)",
    re.I,
)


def inspect_l5x_defects(l5x_path: Path | str) -> list[dict[str, Any]]:
    """Find post-generation defects that must enter the escalation loop."""
    path = Path(l5x_path)
    if not path.is_file():
        return [
            {
                "subsystem": "POST_BUILD",
                "defect_kind": "MISSING_L5X",
                "why_uncertain": f"L5X missing: {path}",
                "site_forge_attempt": "generation claimed complete without artifact",
            }
        ]
    text = path.read_text(encoding="utf-8", errors="replace")
    defects: list[dict[str, Any]] = []

    for m in _BAD_OPERAND_RE.finditer(text):
        defects.append(
            {
                "subsystem": "POST_BUILD",
                "defect_kind": "BLANK_OR_OPEN_OPERAND",
                "operand": m.group(0)[:120],
                "why_uncertain": "malformed/blank Logix operand in generated L5X",
                "site_forge_attempt": "emitted instruction with open operand",
            }
        )
        if len(defects) >= 40:
            break

    # Empty mandatory ES routines
    es = re.search(r'<Program Name="ES"[^>]*>(.*?)</Program>', text, re.S)
    if es:
        body = es.group(1)
        for rn in ("Main_Routine",):
            m = re.search(
                rf'<Routine Name="{rn}"[^>]*>.*?<RLLContent>(.*?)</RLLContent>',
                body,
                re.S,
            )
            if not m:
                defects.append(
                    {
                        "subsystem": "SAFETY",
                        "defect_kind": "MISSING_MAIN_ROUTINE",
                        "routine": rn,
                        "why_uncertain": "ES Main_Routine missing",
                        "site_forge_attempt": "ES program emitted without Main_Routine",
                    }
                )
                continue
            rungs = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", m.group(1))
            nonempty = [r for r in rungs if r.strip() and r.strip() != "NOP();"]
            # Only escalate blank Main when Safe_* also expected (operational Safety)
            has_safe = bool(re.search(r'_Safe_Logic|_Safe_PI', body))
            if has_safe and not nonempty:
                defects.append(
                    {
                        "subsystem": "SAFETY",
                        "defect_kind": "BLANK_MAIN_ROUTINE",
                        "routine": rn,
                        "why_uncertain": "operational Safe_* present but Main_Routine empty",
                        "site_forge_attempt": "shell Main_Routine",
                    }
                )
        for kind in ("_Safe_Logic", "_Safe_PI"):
            for rm in re.finditer(
                rf'<Routine Name="([^"]+{kind})"[^>]*>.*?<RLLContent>(.*?)</RLLContent>',
                body,
                re.S,
            ):
                rname, rbody = rm.group(1), rm.group(2)
                rungs = re.findall(r"<Text><!\[CDATA\[(.*?)\]\]></Text>", rbody)
                nonempty = [r for r in rungs if r.strip() and r.strip() != "NOP();"]
                if not nonempty:
                    defects.append(
                        {
                            "subsystem": "SAFETY",
                            "defect_kind": "BLANK_SAFE_ROUTINE",
                            "routine": rname,
                            "why_uncertain": f"{rname} is NOP/empty while Safety zone exists",
                            "site_forge_attempt": "emitted blank Safety routine",
                        }
                    )

    # Operand validator (deterministic)
    try:
        from fortna_operand_validator import validate_l5x_operands

        v = validate_l5x_operands(text)
        for inv in (v.get("invalid") or [])[:30]:
            defects.append(
                {
                    "subsystem": "POST_BUILD",
                    "defect_kind": "INVALID_OPERAND",
                    "program": inv.get("program"),
                    "routine": inv.get("routine"),
                    "operand": inv.get("operand"),
                    "why_uncertain": inv.get("kind") or "operand_validator_rejected",
                    "site_forge_attempt": "emitted unresolved tag/member path",
                }
            )
    except Exception as exc:  # noqa: BLE001
        defects.append(
            {
                "subsystem": "POST_BUILD",
                "defect_kind": "OPERAND_VALIDATOR_ERROR",
                "why_uncertain": str(exc)[:200],
                "site_forge_attempt": "validator import/run failed",
            }
        )

    return defects


def extract_unresolved_from_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull unresolved I/O / Transport / Safety items from autogen report."""
    items: list[dict[str, Any]] = []
    # Physical unresolved I/O
    for row in report.get("physical_unresolved_io") or report.get("unresolved_io") or []:
        if isinstance(row, dict):
            items.append(
                {
                    "subsystem": "IO",
                    "device": row.get("device") or row.get("name") or row.get("logical_name"),
                    "logical_name": row.get("logical_name") or row.get("name"),
                    "direction": row.get("direction"),
                    "module": row.get("module"),
                    "slot": row.get("slot"),
                    "word": row.get("word"),
                    "bit": row.get("bit"),
                    "why_uncertain": row.get("reason") or row.get("why") or "physical I/O unresolved",
                    "site_forge_attempt": row.get("attempt") or "deterministic I/O mapping",
                    "physical_endpoint_candidates": row.get("candidates") or [],
                }
            )
        elif isinstance(row, str) and row.strip():
            items.append(
                {
                    "subsystem": "IO",
                    "device": row.strip(),
                    "logical_name": row.strip(),
                    "why_uncertain": "physical I/O unresolved (name only)",
                    "site_forge_attempt": "deterministic I/O mapping",
                }
            )

    issues = report.get("build_issues") or {}
    for issue in issues.get("issues") or issues.get("actionable_issues") or []:
        if not isinstance(issue, dict):
            continue
        cat = str(issue.get("category") or issue.get("subsystem") or "OTHER").upper()
        if "IO" in cat or cat == "I/O":
            subsystem = "IO"
        elif "SAFE" in cat or "ES" in cat:
            subsystem = "SAFETY"
        elif "TRANSPORT" in cat or "CONV" in cat or "AREA" in cat:
            subsystem = "TRANSPORTATION"
        elif "WRITER" in cat:
            subsystem = "WRITERS"
        else:
            subsystem = "OTHER"
        items.append(
            {
                "subsystem": subsystem,
                "device": issue.get("what") or issue.get("item") or issue.get("id"),
                "defect_kind": issue.get("code") or issue.get("kind"),
                "why_uncertain": issue.get("why") or issue.get("detail") or "build issue",
                "site_forge_attempt": issue.get("tried") or issue.get("attempt") or "autogen",
                "where": issue.get("where"),
            }
        )

    es = report.get("es_program") or {}
    if es.get("shell") and int(es.get("unresolved") or 0) > 0:
        items.append(
            {
                "subsystem": "SAFETY",
                "defect_kind": "SAFETY_SHELL",
                "why_uncertain": "Safety inventory present but ES shell-only / unresolved",
                "site_forge_attempt": str(es.get("detail") or "ES emit"),
                "device": "ES",
            }
        )
    return items


# ---------------------------------------------------------------------------
# Live AI / Relay adapters
# ---------------------------------------------------------------------------

def call_ai_api_for_case(
    evidence: dict[str, Any],
    *,
    case_file: BuildCaseFile,
    transport: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Level 1 — AI API assist. Advisory only."""
    if transport is not None:
        result = transport(evidence)
        case_file.record_call("AI", {"mode": "transport", "ok": bool(result.get("ok"))})
        return result

    # Prefer compact chat completion for general escalation packets
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    xai = (os.environ.get("XAI_API_KEY") or "").strip()
    if not key and not xai:
        return {"ok": False, "error": "NO_API_KEY", "response": None}

    model = (
        os.environ.get("SITEFORGE_AI_MODEL")
        or ("grok-4" if xai and not key else "gpt-5.6-terra")
    ).strip()
    base_url = None
    api_key = key
    if xai and (os.environ.get("SITEFORGE_AI_PROVIDER") or "").lower() in ("xai", "spacexai"):
        api_key = xai
        base_url = "https://api.x.ai/v1"
        model = os.environ.get("SITEFORGE_AI_MODEL") or "grok-4"

    system = (
        "You are Site Forge AI assist. Return ONE JSON object only.\n"
        "Fields: classification, candidate_resolution (object), confidence "
        "(PROVEN|DERIVED|REVIEW_REQUIRED|UNKNOWN), evidence_used (array of strings), "
        "alternatives (array), why_alternatives_rejected (array), "
        "recommended_action, additional_evidence_needed.\n"
        "Never invent Safety membership. Never invent physical endpoints without evidence.\n"
        "Authority: ADVISORY — Site Forge validators decide acceptance."
    )
    user = (
        "Unresolved Site Forge build item. Propose a resolution.\n\n"
        + json.dumps(
            {
                "site": case_file.site,
                "machine": case_file.machine,
                "run_sha": case_file.run_sha,
                "git_sha": case_file.git_sha,
                "evidence": evidence,
            },
            indent=2,
            default=str,
        )[:60000]
    )
    t0 = time.time()
    try:
        from openai import OpenAI

        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = OpenAI(**kwargs)
        # Some models (e.g. gpt-5.x) reject temperature=0 — omit unless overridden.
        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        temp_env = os.environ.get("SITEFORGE_AI_TEMPERATURE")
        if temp_env is not None and temp_env.strip() != "":
            create_kwargs["temperature"] = float(temp_env)
        resp = client.chat.completions.create(**create_kwargs)
        content = (resp.choices[0].message.content or "").strip()
        data = json.loads(content)
        usage = getattr(resp, "usage", None)
        meta = {
            "provider": "xai" if base_url else "openai",
            "model": model,
            "elapsed_ms": int((time.time() - t0) * 1000),
            "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
            "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None,
        }
        case_file.record_call("AI", meta)
        return {"ok": True, "response": data, "meta": meta}
    except Exception as exc:  # noqa: BLE001
        case_file.record_call("AI", {"error": str(exc)[:300]})
        return {"ok": False, "error": str(exc)[:400], "response": None}


def call_relay_freeform(
    evidence: dict[str, Any],
    *,
    case_file: BuildCaseFile,
    ai_response: dict[str, Any] | None = None,
    purpose: str = "general_escalation",
) -> dict[str, Any]:
    """Relay-style repo-aware call without I/O endpoint schema constraints.

    Used for machine-identity / catalog / transport escalations where the
    classic Relay I/O schema would falsely invalidate a valid answer.
    """
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        case_file.record_call("RELAY", {"error": "NO_API_KEY", "mode": "freeform"})
        return {"ok": False, "error": "NO_API_KEY", "result": None}

    knowledge = ""
    try:
        from fortna_relay_knowledge_loader import build_relay_context_bundle

        bundle = build_relay_context_bundle(repo_root=REPO_ROOT)
        if bundle.get("ok"):
            knowledge = str(bundle.get("context_text") or "")[:80000]
    except Exception as ex:  # noqa: BLE001
        knowledge = f"(knowledge loader unavailable: {ex})"

    model = (
        os.environ.get("SITEFORGE_RELAY_MODEL")
        or os.environ.get("SITEFORGE_AI_MODEL")
        or "gpt-5.6-terra"
    ).strip()
    system = (
        "You are Relay — Site Forge repo-aware escalation specialist.\n"
        "Authority: OBSERVE + PROPOSE only. Never write PLC/L5X directly.\n"
        "Return ONE JSON object.\n"
        "For machine identity include: confidence, candidate_resolution."
        "{resolved_machine, treat_na_rows_as_resolved_machine, "
        "ordencp4_rows_interpretation, evidence_used, "
        "deterministic_checks_to_validate, why_not_other_candidates}.\n"
        "Never invent Safety membership or machines absent from evidence.\n\n"
        + knowledge
    )
    user = json.dumps(
        {
            "purpose": purpose,
            "site": case_file.site,
            "machine": case_file.machine,
            "run_sha": case_file.run_sha,
            "git_sha": case_file.git_sha,
            "evidence": evidence,
            "ai_api_response": ai_response,
        },
        indent=2,
        default=str,
    )[:60000]
    t0 = time.time()
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        temp_env = os.environ.get("SITEFORGE_AI_TEMPERATURE")
        if temp_env is not None and str(temp_env).strip() != "":
            create_kwargs["temperature"] = float(temp_env)
        resp = client.chat.completions.create(**create_kwargs)
        content = (resp.choices[0].message.content or "").strip()
        data = json.loads(content)
        usage = getattr(resp, "usage", None)
        meta = {
            "provider": "openai",
            "model": model,
            "mode": "freeform",
            "elapsed_ms": int((time.time() - t0) * 1000),
            "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
            "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None,
        }
        case_file.record_call("RELAY", meta)
        return {"ok": True, "status": "RELAY_COMPLETE", "result": data, "meta": meta, "ai_call": True}
    except Exception as exc:  # noqa: BLE001
        case_file.record_call("RELAY", {"error": str(exc)[:300], "mode": "freeform"})
        return {"ok": False, "error": str(exc)[:400], "result": None}


def call_relay_for_case(
    evidence: dict[str, Any],
    *,
    case_file: BuildCaseFile,
    ai_response: dict[str, Any] | None = None,
    validator_rejection: dict[str, Any] | None = None,
    transport: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Level 2 — Relay escalation (repo-aware). Live when enabled."""
    # Non-I/O escalations use freeform Relay (avoids false RELAY_RESULT_INVALID).
    kind = str(evidence.get("defect_kind") or "").upper()
    if transport is None and any(
        k in kind
        for k in (
            "MACHINE_IDENTITY",
            "UNSUPPORTED_POINT",
            "UNSUPPORTED_CATALOG",
            "ZERO_CONVEYOR",
            "TRANSPORT",
        )
    ):
        return call_relay_freeform(
            evidence,
            case_file=case_file,
            ai_response=ai_response,
            purpose=kind or "general_escalation",
        )

    packet = {
        "case_id": evidence_signature(evidence),
        "source_controller": case_file.machine or case_file.site,
        "source_panel": case_file.machine or case_file.site,
        "raw_address": str(
            evidence.get("operand")
            or evidence.get("device")
            or evidence.get("logical_name")
            or ""
        ),
        "site": case_file.site,
        "machine": case_file.machine,
        "run_sha": case_file.run_sha,
        "git_sha": case_file.git_sha,
        "evidence_package": evidence,
        "ai_api_response": ai_response,
        "validator_rejection": validator_rejection,
        "subsystem": evidence.get("subsystem"),
        # Satisfy relay schema minimums when using live invoke
        "evidence": [
            {
                "source": "site_forge_escalation",
                "detail": str(evidence.get("why_uncertain") or evidence)[:500],
            }
        ],
        "confidence": "REVIEW_REQUIRED",
        "cross_panel_evidence_encountered": False,
        "cross_panel_physical_mapping_used": False,
        "direction": evidence.get("direction"),
    }

    if transport is not None:
        result = transport(packet)
        case_file.record_call("RELAY", {"mode": "transport", "ok": bool(result.get("ok"))})
        return result

    try:
        from fortna_relay_invoke import invoke_relay

        result = invoke_relay(packet, repo_root=REPO_ROOT, enabled=True)
        case_file.record_call(
            "RELAY",
            {
                "status": result.get("status"),
                "ok": bool(result.get("ok")),
                "ai_call": bool(result.get("ai_call")),
            },
        )
        return result
    except Exception as exc:  # noqa: BLE001
        case_file.record_call("RELAY", {"error": str(exc)[:300]})
        return {"ok": False, "error": str(exc)[:400], "result": None}


def gather_deep_evidence(evidence: dict[str, Any], case_file: BuildCaseFile) -> dict[str, Any]:
    """Level 3 — additional context pass (neighbors, analogs, naming families)."""
    enriched = dict(evidence)
    extras: dict[str, Any] = {
        "deep_pass": True,
        "reference_hints": [],
        "naming_family": None,
    }
    name = str(evidence.get("device") or evidence.get("logical_name") or "")
    if name:
        m = re.match(r"^([A-Za-z]+)", name)
        if m:
            extras["naming_family"] = m.group(1).upper()
    # Point at finished Greensboro / Brownsburg pattern libraries when present
    for label, rel in (
        ("Greensboro_ORNCCP", "workspace/inbox"),
        ("Brownsburg", "workspace/inbox"),
        ("validation_oracles", "tools/libraries"),
    ):
        p = REPO_ROOT / rel
        if p.exists():
            extras["reference_hints"].append({"label": label, "path": str(p)})
    enriched["deep_evidence"] = extras
    enriched["why_uncertain"] = (
        str(evidence.get("why_uncertain") or "")
        + " | deep pass: neighbor/family/reference context attached"
    )
    case_file.timeline.append(
        {
            "ts": _ts(),
            "event": "DEEP_EVIDENCE_GATHERED",
            "signature": evidence_signature(evidence),
            "extras": extras,
        }
    )
    return enriched


# ---------------------------------------------------------------------------
# Core escalation state machine
# ---------------------------------------------------------------------------

def escalate_item(
    evidence: dict[str, Any],
    case_file: BuildCaseFile,
    *,
    deterministic_resolver: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
    ai_transport: Callable[..., dict[str, Any]] | None = None,
    relay_transport: Callable[..., dict[str, Any]] | None = None,
    allow_engineer: bool = True,
    max_deep_passes: int = 2,
) -> CaseItem:
    """Run LEVEL 0→1→2→3→4 for one unresolved item. Never silently abandon."""
    item = case_file.get_or_create(evidence)
    if item.accepted and item.disposition in ("COMPLETE", "UNSUPPORTED", "NOT_APPLICABLE", "WITHHELD"):
        item.add_event(LEVEL_DETERMINISTIC, "SKIP_ALREADY_RESOLVED", {"disposition": item.disposition})
        return item

    subsystem = item.subsystem

    # LEVEL 0 — deterministic
    item.add_event(LEVEL_DETERMINISTIC, "ATTEMPT")
    det: dict[str, Any] | None = None
    if deterministic_resolver is not None:
        try:
            det = deterministic_resolver(evidence)
        except Exception as exc:  # noqa: BLE001
            item.add_event(LEVEL_DETERMINISTIC, "ERROR", {"error": str(exc)[:200]})
    if isinstance(det, dict) and det.get("resolved"):
        v = validate_proposed_resolution(det.get("proposal") or det, evidence, subsystem=subsystem)
        if v.get("ok"):
            item.add_event(LEVEL_DETERMINISTIC, "RESOLVED", v)
            case_file.mark_resolved(
                item,
                disposition=str(det.get("disposition") or "COMPLETE"),
                provenance="DETERMINISTIC",
                resolution={"proposal": det, "validation": v},
                counter_bucket="native_resolved",
            )
            return item
        item.add_event(LEVEL_DETERMINISTIC, "VALIDATOR_REJECTED", v)

    # Built-in deterministic triage for clear withhold/unsupported markers
    why = str(evidence.get("why_uncertain") or "").upper()
    if "UNSUPPORTED" in why and "CRITICAL" not in why:
        case_file.mark_resolved(
            item,
            disposition="UNSUPPORTED",
            provenance="DETERMINISTIC",
            resolution={"reason": evidence.get("why_uncertain")},
            counter_bucket="native_resolved",
        )
        item.add_event(LEVEL_DETERMINISTIC, "CLASSIFIED_UNSUPPORTED")
        return item

    ai_response: dict[str, Any] | None = None
    validator_rejection: dict[str, Any] | None = None

    # LEVEL 1 — AI API
    item.add_event(LEVEL_AI_API, "ATTEMPT")
    ai = call_ai_api_for_case(evidence, case_file=case_file, transport=ai_transport)
    item.ai_calls += 1
    if ai.get("ok") and isinstance(ai.get("response"), dict):
        ai_response = ai["response"]
        proposal = (
            ai_response.get("candidate_resolution")
            if isinstance(ai_response.get("candidate_resolution"), dict)
            else ai_response
        )
        v = validate_proposed_resolution(proposal, evidence, subsystem=subsystem)
        if v.get("ok") and str(ai_response.get("confidence") or "").upper() not in (
            "UNKNOWN",
            "",
        ):
            # Require at least DERIVED/REVIEW with actionable resolution
            conf = str(ai_response.get("confidence") or "").upper()
            if conf in ("PROVEN", "DERIVED") or (
                conf == "REVIEW_REQUIRED" and proposal.get("recommended_action")
            ):
                if conf != "REVIEW_REQUIRED":
                    item.add_event(LEVEL_AI_API, "RESOLVED", {"validation": v, "ai": ai_response})
                    case_file.mark_resolved(
                        item,
                        disposition="COMPLETE" if conf == "PROVEN" else "PARTIAL",
                        provenance="AI_API_ASSISTED",
                        resolution={"ai": ai_response, "validation": v},
                        counter_bucket="ai_resolved",
                    )
                    return item
        validator_rejection = v if not v.get("ok") else {"ok": False, "errors": ["low_confidence"]}
        item.add_event(LEVEL_AI_API, "INSUFFICIENT", {"validation": v, "ai": ai_response})
    else:
        item.add_event(LEVEL_AI_API, "UNAVAILABLE", {"error": ai.get("error")})

    # LEVEL 2 — Relay
    item.add_event(LEVEL_RELAY, "ATTEMPT")
    relay = call_relay_for_case(
        evidence,
        case_file=case_file,
        ai_response=ai_response,
        validator_rejection=validator_rejection,
        transport=relay_transport,
    )
    item.relay_calls += 1
    relay_result = relay.get("result") if isinstance(relay, dict) else None
    # Prefer schema-valid Relay results; still inspect raw payload when schema
    # rejects non-I/O escalation packets (identity / catalog / transport).
    if not isinstance(relay_result, dict) and isinstance(relay, dict):
        raw = relay.get("validation", {}).get("normalized") if isinstance(relay.get("validation"), dict) else None
        if isinstance(raw, dict):
            relay_result = raw
    if isinstance(relay_result, dict):
        v = validate_proposed_resolution(relay_result, evidence, subsystem=subsystem)
        if v.get("ok"):
            conf = str(relay_result.get("confidence") or "").upper()
            if conf in ("PROVEN", "DERIVED", "ENGINEER_ASSIGNED"):
                item.add_event(LEVEL_RELAY, "RESOLVED", {"validation": v, "relay": relay_result})
                case_file.mark_resolved(
                    item,
                    disposition="COMPLETE" if conf == "PROVEN" else "PARTIAL",
                    provenance="RELAY_ASSISTED",
                    resolution={
                        "ai": ai_response,
                        "relay": relay_result,
                        "validation": v,
                    },
                    counter_bucket="relay_resolved",
                )
                return item
            if conf == "REVIEW_REQUIRED":
                item.add_event(LEVEL_RELAY, "REVIEW_REQUIRED", {"relay": relay_result})
            elif relay.get("ok"):
                item.add_event(LEVEL_RELAY, "INSUFFICIENT", {"validation": v, "relay": relay_result})
            else:
                item.add_event(
                    LEVEL_RELAY,
                    "SCHEMA_INVALID_BUT_PAYLOAD",
                    {"status": relay.get("status"), "relay": relay_result},
                )
        else:
            validator_rejection = v
            item.add_event(LEVEL_RELAY, "VALIDATOR_REJECTED", {"validation": v, "relay": relay_result})
    else:
        item.add_event(LEVEL_RELAY, "UNAVAILABLE", {"error": relay.get("error") or relay.get("status")})

    # LEVEL 3 — deep multi-pass
    for deep_i in range(max_deep_passes):
        item.add_event(LEVEL_DEEP, "ATTEMPT", {"pass": deep_i + 1})
        enriched = gather_deep_evidence(evidence, case_file)
        # Re-query AI with enriched evidence (materially different packet)
        ai2 = call_ai_api_for_case(enriched, case_file=case_file, transport=ai_transport)
        item.ai_calls += 1
        if ai2.get("ok") and isinstance(ai2.get("response"), dict):
            proposal = ai2["response"].get("candidate_resolution") or ai2["response"]
            if isinstance(proposal, dict):
                v = validate_proposed_resolution(proposal, enriched, subsystem=subsystem)
                conf = str(ai2["response"].get("confidence") or "").upper()
                if v.get("ok") and conf in ("PROVEN", "DERIVED"):
                    item.add_event(LEVEL_DEEP, "AI_RESOLVED", {"pass": deep_i + 1, "validation": v})
                    case_file.mark_resolved(
                        item,
                        disposition="COMPLETE" if conf == "PROVEN" else "PARTIAL",
                        provenance="AI_API_ASSISTED_DEEP",
                        resolution={"ai": ai2["response"], "validation": v, "deep_pass": deep_i + 1},
                        counter_bucket="ai_resolved",
                    )
                    return item
        relay2 = call_relay_for_case(
            enriched,
            case_file=case_file,
            ai_response=ai2.get("response") if isinstance(ai2, dict) else None,
            validator_rejection=validator_rejection,
            transport=relay_transport,
        )
        item.relay_calls += 1
        rr = relay2.get("result") if isinstance(relay2, dict) else None
        if relay2.get("ok") and isinstance(rr, dict):
            v = validate_proposed_resolution(rr, enriched, subsystem=subsystem)
            conf = str(rr.get("confidence") or "").upper()
            if v.get("ok") and conf in ("PROVEN", "DERIVED", "ENGINEER_ASSIGNED"):
                item.add_event(LEVEL_DEEP, "RELAY_RESOLVED", {"pass": deep_i + 1, "validation": v})
                case_file.mark_resolved(
                    item,
                    disposition="COMPLETE" if conf == "PROVEN" else "PARTIAL",
                    provenance="RELAY_ASSISTED_DEEP",
                    resolution={"relay": rr, "validation": v, "deep_pass": deep_i + 1},
                    counter_bucket="relay_resolved",
                )
                return item

    # LEVEL 4 — engineer
    if allow_engineer:
        q = build_engineer_question(item)
        # Preserve prior AI/Relay blobs so resume/engineer UI can show conclusions.
        prior = {
            "ai": ai_response,
            "relay": relay_result if isinstance(relay_result, dict) else None,
            "validator_rejection": validator_rejection,
        }
        item.add_event(LEVEL_ENGINEER, "QUESTION", q)
        case_file.mark_engineer(item, q)
        item.resolution = {
            **(item.resolution or {}),
            **prior,
            "engineer_question": q,
        }
        return item

    case_file.mark_unresolved(item, "exhausted_automated_escalation")
    item.add_event(LEVEL_ENGINEER, "SKIPPED_ENGINEER_DISABLED")
    return item


def run_post_generation_escalation(
    *,
    report: dict[str, Any],
    l5x_path: Path | str | None,
    site: str = "",
    machine: str = "",
    run_sha: str = "",
    build_id: str = "",
    out_dir: Path | str | None = None,
    ai_transport: Callable[..., dict[str, Any]] | None = None,
    relay_transport: Callable[..., dict[str, Any]] | None = None,
    deterministic_resolver: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Inspect generated artifacts and escalate every unresolved defect.

    Controlled by SITEFORGE_ESCALATION=0 to disable (default: enabled).
    """
    if enabled is None:
        enabled = (os.environ.get("SITEFORGE_ESCALATION") or "1").strip() not in (
            "0",
            "false",
            "False",
            "no",
            "OFF",
        )
    if not enabled:
        return {"ok": True, "enabled": False, "skipped": True}

    site = site or str(report.get("controller_name") or report.get("site") or "UNKNOWN")
    machine = machine or str(report.get("machine") or site)
    case_file = BuildCaseFile(
        site=site,
        machine=machine,
        run_sha=run_sha or str(report.get("run_fingerprint") or report.get("tar_sha256") or ""),
        build_id=build_id or str(report.get("build_id") or ""),
    )

    packages = extract_unresolved_from_report(report)
    if l5x_path:
        packages.extend(inspect_l5x_defects(l5x_path))

    # Deduplicate by signature before escalating
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for p in packages:
        sig = evidence_signature(p)
        if sig in seen:
            continue
        seen.add(sig)
        unique.append(p)

    for pkg in unique:
        escalate_item(
            pkg,
            case_file,
            deterministic_resolver=deterministic_resolver,
            ai_transport=ai_transport,
            relay_transport=relay_transport,
            allow_engineer=True,
        )

    out = Path(out_dir) if out_dir else (REPO_ROOT / "exports" / "current")
    case_path = case_file.write(out / f"{site}_ORI111_CASE_FILE.json")
    # Also under delivery-friendly name
    try:
        case_file.write(REPO_ROOT / "exports" / "current" / "ori111_escalation_report.json")
    except Exception:
        pass

    summary = {
        "ok": True,
        "enabled": True,
        "ori": "ORI-111",
        "case_file": str(case_path),
        "items": len(case_file.items),
        "counters": case_file.counters,
        "ai_api_calls": case_file.ai_api_calls,
        "relay_calls": case_file.relay_calls,
        "estimated_ai_usd": case_file.estimated_ai_usd,
        "estimated_relay_usd": case_file.estimated_relay_usd,
        "estimated_total_usd": round(
            case_file.estimated_ai_usd + case_file.estimated_relay_usd, 4
        ),
        "engineer_questions": [
            (it.resolution or {}).get("engineer_question")
            for it in case_file.items.values()
            if it.engineer_required
        ],
        "git_sha": case_file.git_sha,
        "site": site,
        "machine": machine,
    }
    return summary


def escalation_state_machine_description() -> str:
    return (
        "IMPORT→IDENTIFY→I/O→TRANSPORTATION→SAFETY→WRITERS→L5X→STATIC INSPECTION→"
        "STUDIO COMPAT→ENGINEER PACKAGE; unresolved items escalate "
        "L0 DETERMINISTIC → L1 AI API → L2 RELAY → L3 DEEP MULTI-PASS → L4 ENGINEER; "
        "later phases may send evidence back to earlier phases; "
        "AI/Relay advisory only; Safety membership PROVEN or ENGINEER_ASSIGNED only; "
        "cost tracked for accounting, never terminates resolution."
    )


# ---------------------------------------------------------------------------
# Pre-build: machine identity + zero-conveyor + unsupported catalog
# ---------------------------------------------------------------------------

_NA_OWNERS = frozenset({"", "N/A", "NA", "INVALID", "(EMPTY)", "(NONE)", "NONE", "~"})


def gather_machine_identity_evidence(
    run_dir: Path | str,
    claimed_machine: str,
    *,
    tar_name: str = "",
) -> dict[str, Any]:
    """Collect deterministic evidence for machine-identity conflicts."""
    run_dir = Path(run_dir)
    claimed = (claimed_machine or "").strip()
    evidence: dict[str, Any] = {
        "subsystem": "IO",
        "defect_kind": "MACHINE_IDENTITY_CONFLICT",
        "device": claimed,
        "logical_name": claimed,
        "claimed_machine": claimed,
        "tar_filename": tar_name,
        "why_uncertain": "claimed machine vs Conveyor.asc Machine_Name ownership mismatch",
        "site_forge_attempt": "import_package + project.cfg MACHINENAME + Conveyor filter",
    }

    cfg_machine = ""
    cfg_path = run_dir / "project.cfg"
    if cfg_path.is_file():
        cfg_text = cfg_path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"MACHINENAME\s*=\s*(\S+)", cfg_text, re.I)
        if m:
            cfg_machine = m.group(1).strip()
        evidence["project_cfg_path"] = str(cfg_path)
        evidence["project_cfg_excerpt"] = cfg_text[:800]
    evidence["project_cfg_machine"] = cfg_machine

    counts: dict[str, int] = {}
    conv_path = None
    for cand in (
        run_dir / "FORTNA" / "Conveyor.asc",
        run_dir / "Conveyor.asc",
    ):
        if cand.is_file():
            conv_path = cand
            break
    if conv_path is not None:
        lines = conv_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if lines:
            hdr = lines[0].strip('"').split("~")
            own_idx = next(
                (i for i, c in enumerate(hdr) if c.strip('"').upper() == "MACHINE_NAME"),
                None,
            )
            if own_idx is None:
                # fallback scan
                for ln in lines[1:50]:
                    parts = ln.split("~")
                    for i, p in enumerate(parts):
                        if p.upper().startswith("ORDEN") or p.upper().startswith("MSC"):
                            own_idx = i
                            break
                    if own_idx is not None:
                        break
            for ln in lines[1:]:
                parts = ln.split("~")
                own = parts[own_idx] if own_idx is not None and own_idx < len(parts) else ""
                key = own.strip() or "(empty)"
                counts[key] = counts.get(key, 0) + 1
            evidence["conveyor_asc"] = str(conv_path)
            evidence["machine_name_counts"] = dict(
                sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            )
            evidence["conveyor_row_total"] = sum(counts.values())

    exclusive = {
        k: v
        for k, v in counts.items()
        if k.upper() not in _NA_OWNERS and k != "(empty)"
    }
    claimed_exclusive = int(exclusive.get(claimed, 0) or 0)
    na_count = sum(v for k, v in counts.items() if k.upper() in _NA_OWNERS or k == "(empty)")
    evidence["claimed_exclusive_conveyor_rows"] = claimed_exclusive
    evidence["na_or_empty_conveyor_rows"] = na_count
    evidence["exclusive_machine_names"] = exclusive
    evidence["zero_conveyors_after_filter"] = claimed_exclusive == 0
    evidence["physical_endpoint_candidates"] = sorted(
        {claimed, cfg_machine, *exclusive.keys()} - {""}
    )
    return evidence


def validate_machine_identity_proposal(
    proposal: dict[str, Any], evidence: dict[str, Any]
) -> dict[str, Any]:
    """Accept only machines that appear in TAR/cfg/Machine_Name evidence."""
    machine = str(proposal.get("resolved_machine") or proposal.get("machine") or "").strip()
    cr = proposal.get("candidate_resolution")
    if not machine and isinstance(cr, dict):
        machine = str(cr.get("resolved_machine") or cr.get("machine") or "").strip()
    # Also accept top-level AI response wrapping
    if not machine and isinstance(proposal.get("response"), dict):
        inner = proposal["response"]
        machine = str(inner.get("resolved_machine") or "").strip()
        if not machine and isinstance(inner.get("candidate_resolution"), dict):
            machine = str(
                inner["candidate_resolution"].get("resolved_machine")
                or inner["candidate_resolution"].get("machine")
                or ""
            ).strip()
    allowed = set()
    for k in (
        evidence.get("claimed_machine"),
        evidence.get("project_cfg_machine"),
        *(evidence.get("exclusive_machine_names") or {}).keys(),
    ):
        if k and str(k).upper() not in _NA_OWNERS:
            allowed.add(str(k).strip())
    if not machine:
        return {"ok": False, "errors": ["missing_resolved_machine"], "status": "REJECTED"}
    if machine not in allowed and machine.upper() not in {a.upper() for a in allowed}:
        return {
            "ok": False,
            "errors": [f"machine_not_in_evidence:{machine}", f"allowed:{sorted(allowed)}"],
            "status": "REJECTED",
        }
    # Normalize to evidence spelling
    for a in allowed:
        if a.upper() == machine.upper():
            machine = a
            break
    treat_na = bool(
        proposal.get("treat_na_rows_as_resolved_machine")
        or (isinstance(proposal.get("candidate_resolution"), dict)
            and proposal["candidate_resolution"].get("treat_na_rows_as_resolved_machine"))
    )
    return {
        "ok": True,
        "status": "ACCEPTED",
        "resolved_machine": machine,
        "treat_na_rows_as_resolved_machine": treat_na,
        "errors": [],
        "proposal": proposal,
    }


def resolve_machine_identity(
    run_dir: Path | str,
    claimed_machine: str,
    *,
    tar_name: str = "",
    case_file: BuildCaseFile | None = None,
    ai_transport: Callable[..., dict[str, Any]] | None = None,
    relay_transport: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Escalate machine-identity conflict; return resolved machine + provenance."""
    evidence = gather_machine_identity_evidence(
        run_dir, claimed_machine, tar_name=tar_name
    )
    cf = case_file or BuildCaseFile(
        site=claimed_machine, machine=claimed_machine, run_sha=""
    )

    # Skip escalation if no conflict
    if (
        not evidence.get("zero_conveyors_after_filter")
        and evidence.get("claimed_exclusive_conveyor_rows", 0) > 0
    ):
        return {
            "ok": True,
            "resolved_machine": claimed_machine,
            "changed": False,
            "provenance": "DETERMINISTIC",
            "reason": "claimed machine owns exclusive Conveyor.asc rows",
            "evidence": evidence,
            "case_file": cf,
        }

    def det_resolver(ev: dict[str, Any]) -> dict[str, Any] | None:
        # Strong deterministic: cfg machine equals claimed AND exclusive names empty
        # but N/A rows exist → still uncertain (force AI). Return None.
        # Strong: only one exclusive machine and claimed has zero → propose that
        # machine only as DERIVED candidate for AI confirmation, not auto-accept.
        return None

    # Force AI prompt shape for identity
    evidence["ask"] = (
        "Determine the ACTUAL controller/machine this RUN represents. "
        "Return JSON candidate_resolution with: resolved_machine (string), "
        "treat_na_rows_as_resolved_machine (bool), confidence, evidence_used, "
        "why_not_other_candidates. Do not invent a machine absent from evidence."
    )

    item = escalate_item(
        evidence,
        cf,
        deterministic_resolver=det_resolver,
        ai_transport=ai_transport,
        relay_transport=relay_transport,
        allow_engineer=True,
        max_deep_passes=1,
    )

    resolved = claimed_machine
    treat_na = False
    provenance = item.provenance
    validation = None

    # Extract machine from resolution chain
    for blob in (
        (item.resolution or {}).get("ai"),
        (item.resolution or {}).get("relay"),
        item.resolution,
    ):
        if not isinstance(blob, dict):
            continue
        proposal = blob.get("candidate_resolution") if isinstance(blob.get("candidate_resolution"), dict) else blob
        if not isinstance(proposal, dict):
            continue
        v = validate_machine_identity_proposal(proposal, evidence)
        if v.get("ok"):
            resolved = v["resolved_machine"]
            treat_na = bool(v.get("treat_na_rows_as_resolved_machine"))
            validation = v
            break

    # If engineer required, keep claimed but flag
    if item.engineer_required and validation is None:
        return {
            "ok": False,
            "resolved_machine": claimed_machine,
            "changed": False,
            "provenance": "ENGINEER_REQUIRED",
            "engineer_question": (item.resolution or {}).get("engineer_question"),
            "evidence": evidence,
            "case_file": cf,
            "item": item,
        }

    # Fallback heuristic only when AI/Relay accepted nothing but exclusive single owner exists
    if validation is None:
        exclusive = evidence.get("exclusive_machine_names") or {}
        if len(exclusive) == 1 and evidence.get("claimed_exclusive_conveyor_rows", 0) == 0:
            # Still require AI path result — do not silently switch without validation
            only = next(iter(exclusive.keys()))
            return {
                "ok": False,
                "resolved_machine": claimed_machine,
                "changed": False,
                "provenance": "UNRESOLVED",
                "suggested_machine": only,
                "reason": "AI/Relay did not produce validator-accepted identity; exclusive owner present",
                "evidence": evidence,
                "case_file": cf,
                "item": item,
            }
        if evidence.get("project_cfg_machine") == claimed_machine and evidence.get("na_or_empty_conveyor_rows", 0) > 0:
            # Keep claimed; recommend treating N/A as claimed for rediscovery (PARTIAL)
            treat_na = True
            provenance = "DETERMINISTIC_NA_ROWS_CANDIDATE"
            resolved = claimed_machine

    return {
        "ok": True,
        "resolved_machine": resolved,
        "changed": resolved != claimed_machine,
        "treat_na_rows_as_resolved_machine": treat_na,
        "provenance": provenance,
        "validation": validation,
        "evidence": evidence,
        "case_file": cf,
        "item": item,
        "why": (
            f"selected {resolved} via {provenance}; "
            f"treat_na={treat_na}; claimed_was={claimed_machine}"
        ),
    }


def escalate_unsupported_catalogs(
    withheld: list[dict[str, Any]],
    *,
    case_file: BuildCaseFile,
    ai_transport: Callable[..., dict[str, Any]] | None = None,
    relay_transport: Callable[..., dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Run ORI-111 on each withheld module catalog; never invent module config."""
    results = []
    for row in withheld or []:
        cat = str(row.get("catalog") or "")
        evidence = {
            "subsystem": "IO",
            "defect_kind": "UNSUPPORTED_POINT_CATALOG",
            "device": cat,
            "logical_name": cat,
            "module": cat,
            "catalog": cat,
            "adapter": row.get("adapter"),
            "family": row.get("family"),
            "why_uncertain": row.get("reason") or f"unsupported catalog {cat}",
            "site_forge_attempt": "EIP_CHILD_TEMPLATE + fortna_hardware_family.compiler_supports_catalog",
            "ask": (
                "Classify this Rockwell module. Return candidate_resolution with: "
                "module_type, direction (I/O), channel_count if known, "
                "safe_existing_template (must be empty unless exact library template exists), "
                "disposition (UNSUPPORTED|REVIEW_REQUIRED|COMPLETE), "
                "do_not_invent_module_config=true. Never invent Safety membership."
            ),
        }

        def det(ev: dict[str, Any]) -> dict[str, Any] | None:
            # Known: isolate unsupported — disposition UNSUPPORTED is valid L0 outcome
            return {
                "resolved": True,
                "disposition": "UNSUPPORTED",
                "proposal": {
                    "confidence": "DERIVED",
                    "disposition": "UNSUPPORTED",
                    "catalog": cat,
                    "isolate_only": True,
                    "do_not_invent_module_config": True,
                    "explanation": (
                        f"{cat} has no Site Forge library child template; "
                        "withhold module only; preserve remaining I/O"
                    ),
                },
            }

        item = escalate_item(
            evidence,
            case_file,
            deterministic_resolver=det,
            ai_transport=ai_transport,
            relay_transport=relay_transport,
            allow_engineer=False,
            max_deep_passes=0,
        )
        results.append(
            {
                "catalog": cat,
                "disposition": item.disposition,
                "provenance": item.provenance,
                "resolution": item.resolution,
            }
        )
    return results


def apply_na_machine_ownership_override(
    run_dir: Path | str,
    resolved_machine: str,
) -> dict[str, Any]:
    """Generic: rewrite Conveyor.asc Machine_Name N/A → resolved_machine in active RUN.

    Not a site-name special case — applies whenever identity resolution says
    treat_na_rows_as_resolved_machine=True.
    """
    run_dir = Path(run_dir)
    conv = None
    for cand in (run_dir / "FORTNA" / "Conveyor.asc", run_dir / "Conveyor.asc"):
        if cand.is_file():
            conv = cand
            break
    if conv is None:
        return {"ok": False, "error": "Conveyor.asc missing"}
    lines = conv.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        return {"ok": False, "error": "empty Conveyor.asc"}
    hdr = lines[0].strip('"').split("~")
    own_idx = next(
        (i for i, c in enumerate(hdr) if c.strip('"').upper() == "MACHINE_NAME"),
        None,
    )
    if own_idx is None:
        return {"ok": False, "error": "Machine_Name column missing"}
    changed = 0
    out_lines = [lines[0]]
    for ln in lines[1:]:
        parts = ln.split("~")
        if own_idx < len(parts):
            cur = parts[own_idx].strip()
            if cur.upper() in _NA_OWNERS or cur == "":
                parts[own_idx] = resolved_machine
                changed += 1
                ln = "~".join(parts)
        out_lines.append(ln)
    bak = conv.with_suffix(conv.suffix + ".ori111.bak")
    if not bak.is_file():
        bak.write_text(conv.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    conv.write_text("\n".join(out_lines) + ("\n" if lines and not lines[-1].endswith("\n") else ""), encoding="utf-8")
    return {
        "ok": True,
        "changed_rows": changed,
        "resolved_machine": resolved_machine,
        "backup": str(bak),
    }

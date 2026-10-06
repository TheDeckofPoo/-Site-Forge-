#!/usr/bin/env python3
"""ORI-111 PRE-BUILD I/O escalation — ownership / canonical ambiguity.

Ladder (before L5X generation):
  deterministic → AI API → validate → Relay → validate → engineer confirm required

REVIEW_REQUIRED is an escalation trigger for critical physical I/O, not a
silent terminal success state.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fortna_build_escalation import (  # noqa: E402
    BuildCaseFile,
    call_ai_api_for_case,
    call_relay_freeform,
)
from fortna_run_io_source_ledger import (  # noqa: E402
    STATUS_ENGINEER_REQUIRED,
    STATUS_FOREIGN,
    STATUS_MAPPED,
    STATUS_REVIEW,
    STATUS_SPARE,
    STATUS_UNSUPPORTED,
)

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s: Any) -> str:
    return str(s or "").strip()


def probe_escalation_services(
    *,
    case_file: BuildCaseFile | None = None,
) -> dict[str, Any]:
    """One real AI + one real Relay health/inference call."""
    cf = case_file or BuildCaseFile(site="HEALTH", machine="HEALTH", run_sha="", build_id="io-health")
    health: dict[str, Any] = {
        "probed_at": _ts(),
        "ai_api": {"available": False},
        "relay": {"available": False},
        "escalation_service_unavailable": False,
    }
    evidence = {
        "subsystem": "IO",
        "device": "HEALTHCHECK",
        "why_uncertain": "prebuild I/O escalation health probe",
        "site_forge_attempt": "health",
        "prompt_hint": (
            "Health check only. Return JSON "
            '{"classification":"HEALTH_OK","confidence":"PROVEN",'
            '"recommended_action":"NONE","evidence_used":["health_probe"]}.'
        ),
    }
    t0 = time.time()
    ai = call_ai_api_for_case(evidence, case_file=cf)
    health["ai_api"] = {
        "available": bool(ai.get("ok")),
        "error": ai.get("error"),
        "meta": ai.get("meta") or {},
        "elapsed_ms": int((time.time() - t0) * 1000),
        "model": (ai.get("meta") or {}).get("model"),
        "provider": (ai.get("meta") or {}).get("provider"),
    }
    t1 = time.time()
    relay = call_relay_freeform(
        evidence, case_file=cf, ai_response=ai.get("response"), purpose="io_ownership_health"
    )
    relay_ok = bool(relay.get("ok")) or str(relay.get("status") or "") in {
        "RELAY_COMPLETE",
        "OK",
        "COMPLETE",
    }
    health["relay"] = {
        "available": relay_ok,
        "error": None if relay_ok else (relay.get("error") or relay.get("status")),
        "meta": relay.get("meta") or {},
        "elapsed_ms": int((time.time() - t1) * 1000),
        "model": (relay.get("meta") or {}).get("model"),
        "status": relay.get("status"),
    }
    if not health["ai_api"]["available"] or not health["relay"]["available"]:
        health["escalation_service_unavailable"] = True
        health["code"] = "ESCALATION_SERVICE_UNAVAILABLE"
    return health


def _validate_ownership_proposal(
    proposal: dict[str, Any] | None,
    *,
    device: dict[str, Any],
    machine: str,
    active_words: set[str],
) -> dict[str, Any]:
    """Deterministic validation of AI/Relay ownership classification."""
    if not isinstance(proposal, dict):
        return {"ok": False, "reason": "empty_proposal"}
    # Prefer top-level classification; nested ownership may be UNRESOLVED.
    cand = proposal.get("candidate_resolution") if isinstance(proposal.get("candidate_resolution"), dict) else {}
    classification = _norm(
        proposal.get("classification")
        or cand.get("classification")
        or proposal.get("recommended_action")
        or cand.get("ownership")
        or proposal.get("ownership")
    )
    endpoint = _norm(
        cand.get("physical_endpoint")
        or cand.get("endpoint")
        or proposal.get("physical_endpoint")
        or proposal.get("endpoint")
    )
    owner = _norm(
        cand.get("controller")
        or cand.get("owner")
        or cand.get("machine")
        or proposal.get("controller")
        or proposal.get("owner")
    )

    classification_u = classification.upper().replace(" ", "_")
    conf = _norm(proposal.get("confidence")).upper() or "UNKNOWN"
    word = _norm(device.get("word"))
    # Normalize common AI phrasings
    if classification_u in {
        "UNRESOLVED",
        "UNRESOLVED_PENDING_ENGINEERING_EVIDENCE",
        "ENGINEER_CONFIRM",
        "ENGINEER_REQUIRED",
        "LEAVE_REVIEW",
        "NEEDS_ENGINEER",
    } or "ENGINEER_CONFIRM" in classification_u or classification_u.endswith("UNRESOLVED"):
        classification_u = "ENGINEER_CONFIRM_REQUIRED"

    if classification_u in {"FOREIGN", "FOREIGN_CONTROLLER", "CONFIRM_FOREIGN"}:
        # Require evidence citation — Machine_Name other OR explicit reason
        evidence_used = proposal.get("evidence_used") or []
        reason = _norm(proposal.get("recommended_action") or proposal.get("why") or proposal.get("reason"))
        if not evidence_used and not reason and conf not in {"PROVEN", "DERIVED"}:
            return {"ok": False, "reason": "foreign_without_evidence"}
        return {
            "ok": True,
            "final_status": STATUS_FOREIGN,
            "ownership": "FOREIGN",
            "endpoint": endpoint,
            "controller": owner,
            "confidence": conf or "DERIVED",
            "reason": reason or "AI/Relay classified FOREIGN with evidence",
        }

    if classification_u in {"SPARE", "SPARE_UNUSED", "MARK_SPARE"}:
        return {
            "ok": True,
            "final_status": STATUS_SPARE,
            "ownership": "LOCAL",
            "endpoint": endpoint or _norm(device.get("physical_endpoint")),
            "confidence": conf or "DERIVED",
            "reason": "AI/Relay classified SPARE",
        }

    if classification_u in {"UNSUPPORTED"}:
        return {
            "ok": True,
            "final_status": STATUS_UNSUPPORTED,
            "ownership": _norm(device.get("ownership")) or "UNKNOWN",
            "confidence": conf or "DERIVED",
            "reason": "AI/Relay classified UNSUPPORTED",
        }

    if classification_u in {"LOCAL", "MAPPED", "OWN", "CONFIRM_LOCAL", "ACTIVE_CONTROLLER"}:
        # Must not invent LOCAL when word is proven absent from active Configio
        # unless proposal supplies a validated alternate binding evidence.
        if word and active_words and word not in active_words and not endpoint:
            return {
                "ok": False,
                "reason": "local_claimed_but_word_not_in_active_configio_and_no_endpoint",
            }
        # Reject invented Safety membership fields if present
        if proposal.get("safety_zone_members") or proposal.get("invent_safety_membership"):
            return {"ok": False, "reason": "invented_safety_membership_forbidden"}
        return {
            "ok": True,
            "final_status": STATUS_MAPPED if endpoint or _norm(device.get("physical_endpoint")) else STATUS_REVIEW,
            "ownership": "LOCAL",
            "endpoint": endpoint or _norm(device.get("physical_endpoint")),
            "controller": owner or machine,
            "confidence": conf or "DERIVED",
            "reason": reason if (reason := _norm(proposal.get("reason"))) else "AI/Relay classified LOCAL",
            "needs_map": True,
        }

    if classification_u in {"REVIEW_REQUIRED", "ENGINEER_CONFIRM_REQUIRED", "UNKNOWN", "HEALTH_OK"}:
        return {
            "ok": True,
            "final_status": STATUS_ENGINEER_REQUIRED,
            "ownership": "UNKNOWN",
            "confidence": conf or "REVIEW_REQUIRED",
            "reason": "AI/Relay could not prove ownership — engineer confirmation required",
            "engineer_required": True,
        }

    return {"ok": False, "reason": f"unrecognized_classification:{classification}"}


def _build_device_evidence_pack(
    device: dict[str, Any],
    *,
    machine: str,
    active_words: list[str],
    peer_claims: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "subsystem": "IO",
        "defect_kind": "OWNERSHIP_UNRESOLVED",
        "device": device.get("canonical_name"),
        "logical_name": device.get("canonical_name"),
        "word": device.get("word"),
        "bit": device.get("bit"),
        "direction": device.get("direction"),
        "module": device.get("module"),
        "slot": device.get("slot"),
        "physical_endpoint": device.get("physical_endpoint"),
        "source_machine": device.get("source_machine"),
        "device_type": device.get("device_type"),
        "deterministic_code": device.get("deterministic_code"),
        "deterministic_reason": device.get("reason"),
        "word_in_active_configio": device.get("word_in_active_configio"),
        "active_controller": machine,
        "active_configio_words_sample": list(active_words)[:40],
        "source_evidence": device.get("source_evidence") or [],
        "peer_claims_on_word": peer_claims or [],
        "why_uncertain": (
            "Machine_Name is N/A/wildcard and word is absent from active-controller "
            "Configio/EIP map — need ownership classification without inventing LOCAL."
        ),
        "site_forge_attempt": "PhysicalWordResolver + Conveyor/EStop/safety evidence collapse",
        "constraints": [
            "Never invent Safety membership",
            "Never invent physical endpoints without evidence",
            "Machine_Name=N/A is uncertainty not foreign proof",
            "If word not in active Configio, LOCAL requires alternate proven binding",
            "FOREIGN requires cited evidence",
        ],
        "allowed_classifications": [
            "FOREIGN_CONTROLLER",
            "LOCAL",
            "SPARE_UNUSED",
            "UNSUPPORTED",
            "ENGINEER_CONFIRM_REQUIRED",
        ],
    }


def run_prebuild_io_escalation(
    canonical: dict[str, Any],
    *,
    machine: str,
    run_dir: Path | str | None = None,
    health: dict[str, Any] | None = None,
    skip_noncritical: bool = True,
    max_devices: int | None = None,
) -> dict[str, Any]:
    """Escalate unresolved unique devices. Mutates canonical devices in place."""
    mach = _norm(machine)
    active_words = {str(w) for w in (canonical.get("active_configio_words") or [])}
    devices = list(canonical.get("devices") or [])

    # Peer claims index by word
    by_word: dict[str, list[dict[str, Any]]] = {}
    for d in devices:
        w = _norm(d.get("word"))
        if w:
            by_word.setdefault(w, []).append(
                {
                    "canonical_name": d.get("canonical_name"),
                    "bit": d.get("bit"),
                    "ownership": d.get("ownership"),
                    "source_machine": d.get("source_machine"),
                    "final_status": d.get("final_status"),
                }
            )

    unresolved = []
    for d in devices:
        st = _norm(d.get("final_status")).split(":")[0]
        if st not in {STATUS_REVIEW, STATUS_ENGINEER_REQUIRED}:
            continue
        if skip_noncritical and not d.get("critical") and d.get("device_type") == "PHYSICAL_CHANNEL":
            # Still record WHY not escalated
            d.setdefault("escalation_trace", {})
            d["escalation_trace"].update(
                {
                    "ai_api_called": False,
                    "relay_called": False,
                    "why_ai_not_called": "noncritical_physical_channel",
                    "why_relay_not_called": "noncritical_physical_channel",
                    "final_classification": st,
                }
            )
            continue
        unresolved.append(d)

    if max_devices is not None:
        unresolved = unresolved[: max(0, int(max_devices))]

    cf = BuildCaseFile(
        site=mach,
        machine=mach,
        run_sha="",
        build_id="prebuild-io",
    )
    if health is None:
        health = probe_escalation_services(case_file=cf)

    stats = {
        "health": health,
        "candidates": len(unresolved),
        "ai_calls": 0,
        "ai_resolved": 0,
        "ai_unresolved": 0,
        "relay_calls": 0,
        "relay_resolved": 0,
        "relay_unresolved": 0,
        "engineer_confirm_required": 0,
        "skipped_service_unavailable": 0,
        "traces": [],
    }

    service_down = bool(health.get("escalation_service_unavailable"))

    for d in unresolved:
        trace = dict(d.get("escalation_trace") or {})
        trace["deterministic_result"] = {
            "ownership": d.get("ownership"),
            "code": d.get("deterministic_code"),
            "reason": d.get("reason"),
            "word_in_active_configio": d.get("word_in_active_configio"),
            "endpoint": d.get("physical_endpoint"),
        }
        peers = [
            p
            for p in by_word.get(_norm(d.get("word")), [])
            if p.get("canonical_name") != d.get("canonical_name")
        ][:12]
        pack = _build_device_evidence_pack(
            d, machine=mach, active_words=sorted(active_words), peer_claims=peers
        )

        ai_available = bool((health.get("ai_api") or {}).get("available"))
        relay_available = bool((health.get("relay") or {}).get("available"))

        # If AI is down, cannot start the ladder — mark engineer required with WHY.
        if not ai_available:
            trace.update(
                {
                    "ai_api_called": False,
                    "relay_called": False,
                    "why_ai_not_called": "ESCALATION_SERVICE_UNAVAILABLE",
                    "why_relay_not_called": (
                        "ESCALATION_SERVICE_UNAVAILABLE"
                        if not relay_available
                        else "ai_unavailable_short_circuit"
                    ),
                    "final_classification": STATUS_ENGINEER_REQUIRED,
                    "engineer_confirmation_required": True,
                }
            )
            d["final_status"] = STATUS_ENGINEER_REQUIRED
            d["escalation_trace"] = trace
            d["reason"] = "ESCALATION_SERVICE_UNAVAILABLE — engineer confirmation required"
            stats["skipped_service_unavailable"] += 1
            stats["engineer_confirm_required"] += 1
            stats["traces"].append({"device": d.get("canonical_name"), **trace})
            continue

        # AI
        ai = call_ai_api_for_case(pack, case_file=cf)
        stats["ai_calls"] += 1
        trace["ai_api_called"] = True
        trace["why_ai_not_called"] = ""
        trace["ai_result"] = {
            "ok": ai.get("ok"),
            "error": ai.get("error"),
            "response": ai.get("response"),
            "meta": ai.get("meta"),
        }
        ai_val = _validate_ownership_proposal(
            ai.get("response") if ai.get("ok") else None,
            device=d,
            machine=mach,
            active_words=active_words,
        )
        trace["ai_validation"] = ai_val

        accepted = None
        if ai_val.get("ok") and not ai_val.get("engineer_required"):
            accepted = ai_val
            stats["ai_resolved"] += 1
        else:
            stats["ai_unresolved"] += 1
            # Relay (freeform — ownership is not endpoint-schema constrained)
            if not relay_available:
                trace["relay_called"] = False
                trace["why_relay_not_called"] = "ESCALATION_SERVICE_UNAVAILABLE"
                trace["relay_validation"] = {
                    "ok": False,
                    "reason": "ESCALATION_SERVICE_UNAVAILABLE",
                }
                stats["relay_unresolved"] += 1
                stats["skipped_service_unavailable"] += 1
            else:
                relay = call_relay_freeform(
                    pack,
                    case_file=cf,
                    ai_response=ai.get("response"),
                    purpose="io_ownership_unresolved",
                )
                stats["relay_calls"] += 1
                trace["relay_called"] = True
                trace["why_relay_not_called"] = ""
                relay_ok = bool(relay.get("ok")) or str(relay.get("status") or "") in {
                    "RELAY_COMPLETE",
                    "OK",
                    "COMPLETE",
                }
                trace["relay_result"] = {
                    "ok": relay_ok,
                    "error": None if relay_ok else (relay.get("error") or relay.get("status")),
                    "result": relay.get("result") or relay.get("response"),
                    "meta": relay.get("meta"),
                }
                relay_payload = relay.get("result") or relay.get("response")
                relay_val = _validate_ownership_proposal(
                    relay_payload if relay_ok else None,
                    device=d,
                    machine=mach,
                    active_words=active_words,
                )
                trace["relay_validation"] = relay_val
                if relay_val.get("ok") and not relay_val.get("engineer_required"):
                    accepted = relay_val
                    stats["relay_resolved"] += 1
                else:
                    stats["relay_unresolved"] += 1

        if accepted:
            d["final_status"] = accepted["final_status"]
            d["ownership"] = accepted.get("ownership") or d.get("ownership")
            if accepted.get("endpoint"):
                d["physical_endpoint"] = accepted["endpoint"]
            if accepted.get("controller"):
                d["controller"] = accepted["controller"]
            d["confidence"] = accepted.get("confidence") or d.get("confidence")
            d["reason"] = accepted.get("reason") or d.get("reason")
            d["assignable"] = d["final_status"] in {STATUS_MAPPED, "ENGINEER_CONFIRMED"}
            trace["final_classification"] = d["final_status"]
            trace["engineer_confirmation_required"] = False
        else:
            d["final_status"] = STATUS_ENGINEER_REQUIRED
            d["ownership"] = "UNKNOWN"
            d["reason"] = (
                (trace.get("relay_validation") or {}).get("reason")
                or (trace.get("ai_validation") or {}).get("reason")
                or "AI+Relay could not prove ownership"
            )
            d["assignable"] = False
            trace["final_classification"] = STATUS_ENGINEER_REQUIRED
            trace["engineer_confirmation_required"] = True
            stats["engineer_confirm_required"] += 1

        d["escalation_trace"] = trace
        stats["traces"].append({"device": d.get("canonical_name"), **{k: trace.get(k) for k in (
            "ai_api_called", "relay_called", "final_classification", "engineer_confirmation_required",
            "why_ai_not_called", "why_relay_not_called",
        )}})

    # Recompute metrics after escalation mutations
    _recompute_canonical_metrics(canonical)
    canonical["prebuild_escalation"] = stats
    return stats


def _recompute_canonical_metrics(canonical: dict[str, Any]) -> None:
    from fortna_run_io_source_ledger import (
        RESOLVED_STATUSES,
        RESOLUTION_THRESHOLD_PCT,
        STATUS_ENGINEER_CONFIRMED,
        STATUS_FOREIGN,
        STATUS_MAPPED,
        STATUS_REVIEW,
        STATUS_SPARE,
        STATUS_UNSUPPORTED,
        STATUS_ENGINEER_REQUIRED,
        STATUS_SILENT,
    )

    devices = list(canonical.get("devices") or [])
    unique_foreign = [d for d in devices if d.get("final_status") == STATUS_FOREIGN or d.get("ownership") == "FOREIGN"]
    unique_local = [
        d for d in devices if d.get("ownership") != "FOREIGN" and d.get("final_status") != STATUS_FOREIGN
    ]

    def _count(status: str) -> int:
        return sum(1 for d in devices if _norm(d.get("final_status")).split(":")[0] == status)

    local_resolved_n = sum(
        1
        for d in unique_local
        if _norm(d.get("final_status")).split(":")[0]
        in {STATUS_MAPPED, STATUS_SPARE, STATUS_UNSUPPORTED, STATUS_ENGINEER_CONFIRMED}
    )
    local_denom = len(unique_local)
    resolution_pct = round(100.0 * local_resolved_n / max(1, local_denom), 2) if local_denom else 0.0
    local_named = [d for d in unique_local if d.get("device_type") != "PHYSICAL_CHANNEL"]
    gen_mapped = sum(1 for d in local_named if d.get("final_status") == STATUS_MAPPED)
    generated_pct = round(100.0 * gen_mapped / max(1, len(local_named)), 2)

    critical_unresolved = [
        d
        for d in unique_local
        if d.get("critical")
        and _norm(d.get("final_status")).split(":")[0]
        not in {STATUS_MAPPED, STATUS_SPARE, STATUS_UNSUPPORTED, STATUS_ENGINEER_CONFIRMED, STATUS_FOREIGN}
    ]
    canonical.update(
        {
            "unique_foreign": len(unique_foreign),
            "unique_local": local_denom,
            "unique_mapped": _count(STATUS_MAPPED),
            "unique_review": sum(
                1
                for d in devices
                if _norm(d.get("final_status")).split(":")[0]
                in {STATUS_REVIEW, STATUS_ENGINEER_REQUIRED}
            ),
            "unique_unsupported": _count(STATUS_UNSUPPORTED),
            "unique_spare": _count(STATUS_SPARE),
            "unique_engineer_confirmed": _count(STATUS_ENGINEER_CONFIRMED),
            "device_resolution_coverage_pct": resolution_pct,
            "generated_io_coverage_pct": generated_pct,
            "engineering_resolution_ok": resolution_pct >= RESOLUTION_THRESHOLD_PCT
            and len(critical_unresolved) == 0,
            "critical_unresolved_count": len(critical_unresolved),
            "critical_unresolved": [
                {
                    "canonical_device": d.get("canonical_name"),
                    "status": d.get("final_status"),
                    "reason": d.get("reason"),
                }
                for d in critical_unresolved
            ],
        }
    )
    # Refresh safety review counts
    safety = canonical.get("safety") or {}
    if isinstance(safety, dict):
        safety["review"] = sum(
            1
            for d in devices
            if d.get("device_type") in {"ESPB", "ESLS", "ESR", "MCR", "SAFETY", "ESTOP"}
            and _norm(d.get("final_status")).split(":")[0]
            in {STATUS_REVIEW, STATUS_ENGINEER_REQUIRED}
        )
        safety["assignable"] = sum(
            1
            for d in devices
            if d.get("assignable")
            and d.get("device_type") in {"ESPB", "ESLS", "ESR", "MCR", "SAFETY", "ESTOP"}
        )
        canonical["safety"] = safety

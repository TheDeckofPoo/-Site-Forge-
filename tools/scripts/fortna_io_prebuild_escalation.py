#!/usr/bin/env python3
"""ORI-111 PRE-BUILD I/O escalation — ownership / canonical ambiguity.

Ladder (before L5X generation):
  deterministic → cluster AI API → validate → cluster Relay → validate
  → engineer confirm required (individual residual only)

REVIEW_REQUIRED is an escalation trigger for critical physical I/O, not a
silent terminal success state.

AI/Relay operate on SITE-LEVEL clusters (word-range / family / ownership
pattern), not one isolated call per device.
"""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict
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

# Ledger may not yet define INTERNAL; keep a string the ledger/metrics understand.
try:
    from fortna_run_io_source_ledger import STATUS_INTERNAL_LOGICAL  # type: ignore
except ImportError:  # pragma: no cover
    STATUS_INTERNAL_LOGICAL = "INTERNAL_LOGICAL"  # exclude from physical denominator

WORD_NEAR_DELTA = 50

_SAFETY_FAMILY = frozenset(
    {"ESPB", "ESLS", "ESR", "MCR", "SAFETY", "ESTOP"}
)
_PB_FAMILY = frozenset({"PUSHBUTTON_CONTROL", "PUSHBUTTON", "CS"})


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _yesno(flag: bool) -> str:
    return "YES" if flag else "NO"


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


def _device_family(device: dict[str, Any]) -> str:
    dt = _norm(device.get("device_type")).upper()
    if dt in _SAFETY_FAMILY:
        return "SAFETY"
    if dt in _PB_FAMILY:
        return "PUSHBUTTON"
    if dt == "PHYSICAL_CHANNEL":
        return "PHYSICAL_CHANNEL"
    if dt == "INTERNAL_LOGICAL":
        return "INTERNAL_LOGICAL"
    return dt or "OTHER"


def _parse_word(device: dict[str, Any]) -> int | None:
    raw = _norm(device.get("word"))
    if not raw:
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def _word_hundreds(word: int | None) -> str:
    if word is None:
        return "no_word"
    return f"{(word // 100) * 100}s"


def _primary_source_file(device: dict[str, Any]) -> str:
    for se in device.get("source_evidence") or []:
        if isinstance(se, dict):
            sf = _norm(se.get("source_file"))
            if sf:
                return sf
        elif se:
            return _norm(se)
    return _norm(device.get("source_file"))


def _cluster_seed_key(device: dict[str, Any]) -> tuple[str, str, str]:
    """Strongest cluster key: deterministic_code + family + word hundreds."""
    code = _norm(device.get("deterministic_code")) or "OWNERSHIP_UNRESOLVED"
    family = _device_family(device)
    bucket = _word_hundreds(_parse_word(device))
    return (code, family, bucket)


def form_ownership_clusters(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group unresolved devices into site-level ownership clusters.

    Prefer same deterministic_code + nearby word range + same device_type family.
    Soft signals (module/adapter, source_file) refine the cluster id but do not
    split a strong code+family+nearby-word group.
    """
    if not devices:
        return []

    # Initial buckets by strong key
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for d in devices:
        buckets[_cluster_seed_key(d)].append(d)

    # Merge buckets that share code+family and have word ranges within ±50
    # (covers "nearby words" across adjacent hundreds when applicable).
    group_ids: dict[tuple[str, str, str], int] = {}
    next_gid = 0
    keys = sorted(buckets.keys())
    for i, k in enumerate(keys):
        if k in group_ids:
            continue
        group_ids[k] = next_gid
        code_i, fam_i, _ = k
        words_i = [w for d in buckets[k] if (w := _parse_word(d)) is not None]
        min_i = min(words_i) if words_i else None
        max_i = max(words_i) if words_i else None
        for k2 in keys[i + 1 :]:
            if k2 in group_ids:
                continue
            code_j, fam_j, _ = k2
            if code_j != code_i or fam_j != fam_i:
                continue
            words_j = [w for d in buckets[k2] if (w := _parse_word(d)) is not None]
            if min_i is None or not words_j:
                # no_word only merges with other no_word under same code+family
                if min_i is None and not words_j:
                    group_ids[k2] = next_gid
                continue
            min_j, max_j = min(words_j), max(words_j)
            if min_j <= (max_i or 0) + WORD_NEAR_DELTA and max_j >= (min_i or 0) - WORD_NEAR_DELTA:
                group_ids[k2] = next_gid
                min_i = min(min_i if min_i is not None else min_j, min_j)
                max_i = max(max_i if max_i is not None else max_j, max_j)
        next_gid += 1

    merged: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for k, members in buckets.items():
        merged[group_ids[k]].extend(members)

    clusters: list[dict[str, Any]] = []
    for gid in sorted(merged.keys()):
        members = sorted(
            merged[gid],
            key=lambda d: (
                _parse_word(d) if _parse_word(d) is not None else 10**9,
                _norm(d.get("canonical_name")),
            ),
        )
        words = [w for d in members if (w := _parse_word(d)) is not None]
        code = _norm(members[0].get("deterministic_code")) or "OWNERSHIP_UNRESOLVED"
        family = _device_family(members[0])
        modules = sorted({_norm(d.get("module")) for d in members if _norm(d.get("module"))})
        sources = sorted({_primary_source_file(d) for d in members if _primary_source_file(d)})
        types = sorted({_norm(d.get("device_type")) for d in members if _norm(d.get("device_type"))})
        raw = f"{code}|{family}|{min(words) if words else 'nw'}|{max(words) if words else 'nw'}|" + ",".join(
            _norm(d.get("canonical_name")) for d in members
        )
        cid = "io_clust_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
        clusters.append(
            {
                "cluster_id": cid,
                "deterministic_code": code,
                "device_family": family,
                "device_types": types,
                "word_min": min(words) if words else None,
                "word_max": max(words) if words else None,
                "word_bucket": _word_hundreds(min(words) if words else None),
                "modules": modules,
                "source_files": sources,
                "devices": members,
                "device_names": [_norm(d.get("canonical_name")) for d in members],
                "size": len(members),
            }
        )
    return clusters


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

    if classification_u in {
        "INTERNAL",
        "INTERNAL_LOGICAL",
        "MARK_INTERNAL",
        "LOGICAL_MAPPING",
        "INTERNAL_LOGICAL_MAPPING",
    }:
        return {
            "ok": True,
            "final_status": STATUS_INTERNAL_LOGICAL,
            "ownership": "INTERNAL",
            "endpoint": endpoint,
            "controller": owner or machine,
            "confidence": conf or "DERIVED",
            "reason": _norm(proposal.get("reason"))
            or "AI/Relay classified INTERNAL_LOGICAL (excluded from physical denominator)",
            "evidence_class": "INTERNAL_LOGICAL",
        }

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
            "INTERNAL_LOGICAL",
            "UNSUPPORTED",
            "ENGINEER_CONFIRM_REQUIRED",
        ],
    }


def _build_cluster_evidence_pack(
    cluster: dict[str, Any],
    *,
    machine: str,
    active_words: list[str],
    by_word: dict[str, list[dict[str, Any]]],
    finished_site_knowledge: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Site-level ownership audit pack — one call covers the whole cluster."""
    device_rows = []
    peer_evidence: list[dict[str, Any]] = []
    seen_peers: set[str] = set()
    for d in cluster["devices"]:
        name = _norm(d.get("canonical_name"))
        device_rows.append(
            {
                "canonical_name": name,
                "word": d.get("word"),
                "bit": d.get("bit"),
                "direction": d.get("direction"),
                "device_type": d.get("device_type"),
                "module": d.get("module"),
                "slot": d.get("slot"),
                "physical_endpoint": d.get("physical_endpoint"),
                "source_machine": d.get("source_machine"),
                "deterministic_code": d.get("deterministic_code"),
                "deterministic_reason": d.get("reason"),
                "word_in_active_configio": d.get("word_in_active_configio"),
                "source_evidence": d.get("source_evidence") or [],
                "critical": bool(d.get("critical")),
            }
        )
        for p in by_word.get(_norm(d.get("word")), []):
            pn = _norm(p.get("canonical_name"))
            if not pn or pn == name or pn in seen_peers:
                continue
            seen_peers.add(pn)
            peer_evidence.append(p)
            if len(peer_evidence) >= 24:
                break

    return {
        "subsystem": "IO",
        "defect_kind": "CLUSTER_OWNERSHIP_AUDIT",
        "audit_scope": "SITE_LEVEL",
        "cluster_id": cluster["cluster_id"],
        "deterministic_code": cluster.get("deterministic_code"),
        "device_family": cluster.get("device_family"),
        "device_types": cluster.get("device_types"),
        "word_range": {
            "min": cluster.get("word_min"),
            "max": cluster.get("word_max"),
            "bucket": cluster.get("word_bucket"),
        },
        "modules": cluster.get("modules") or [],
        "source_files": cluster.get("source_files") or [],
        "active_controller": machine,
        "cluster_devices": device_rows,
        "cluster_size": len(device_rows),
        "peer_evidence": peer_evidence[:24],
        "active_configio_words_sample": list(active_words)[:40],
        "finished_site_knowledge": finished_site_knowledge or [],
        "site_audit_questions": [
            "What subsystem/controller owns these word ranges?",
            "Where else are these devices referenced (Conveyor/EStop/safety/EIP)?",
            "Are these physical devices, remote I/O, foreign controller, "
            "internal logical mapping, or a legacy word map?",
        ],
        "why_uncertain": (
            "Cluster of unresolved ownership devices sharing deterministic code / "
            "nearby word range / device family — classify at site level, not per isolated bit."
        ),
        "site_forge_attempt": "PhysicalWordResolver + Conveyor/EStop/safety evidence collapse",
        "constraints": [
            "Never invent Safety membership",
            "Never invent physical endpoints without evidence",
            "Machine_Name=N/A is uncertainty not foreign proof",
            "If word not in active Configio, LOCAL requires alternate proven binding",
            "FOREIGN requires cited evidence",
            "Prefer one cluster-level conclusion with optional per_device overrides",
        ],
        "allowed_classifications": [
            "FOREIGN_CONTROLLER",
            "LOCAL",
            "SPARE_UNUSED",
            "INTERNAL_LOGICAL",
            "UNSUPPORTED",
            "ENGINEER_CONFIRM_REQUIRED",
        ],
        "response_schema_hint": {
            "classification": "cluster default classification",
            "subsystem_owner": "string",
            "device_nature": (
                "physical_device|remote_io|foreign_controller|"
                "internal_logical_mapping|legacy_word_map"
            ),
            "confidence": "PROVEN|DERIVED|UNKNOWN",
            "reason": "string",
            "evidence_used": ["..."],
            "per_device": [
                {
                    "canonical_name": "NAME",
                    "classification": "FOREIGN_CONTROLLER|LOCAL|SPARE_UNUSED|"
                    "INTERNAL_LOGICAL|UNSUPPORTED|ENGINEER_CONFIRM_REQUIRED",
                    "physical_endpoint": "optional",
                    "controller": "optional",
                    "reason": "optional",
                }
            ],
        },
    }


def _load_finished_site_knowledge(
    *,
    machine: str,
    cluster: dict[str, Any],
) -> list[dict[str, Any]]:
    """Best-effort finished-site / prior-site knowledge. Omit gracefully if absent."""
    evidence: list[dict[str, Any]] = []
    loaders = (
        ("fortna_io_knowledge_base", "load_finished_site_knowledge"),
        ("fortna_io_knowledge_base", "lookup_cluster_knowledge"),
        ("fortna_relay_knowledge_loader", "load_finished_site_lessons"),
    )
    for mod_name, fn_name in loaders:
        try:
            mod = __import__(mod_name)
            fn = getattr(mod, fn_name, None)
            if not callable(fn):
                continue
            try:
                got = fn(machine=machine, cluster=cluster)
            except TypeError:
                got = fn(machine)
            if isinstance(got, list):
                evidence.extend(x for x in got if isinstance(x, dict))
            elif isinstance(got, dict) and got:
                evidence.append(got)
            if evidence:
                break
        except Exception:
            continue
    return evidence[:20]


def _per_device_proposals(cluster_proposal: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Extract optional per-device classifications from a cluster AI/Relay payload."""
    if not isinstance(cluster_proposal, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key in ("per_device", "devices", "device_classifications", "device_results"):
        rows = cluster_proposal.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = _norm(
                row.get("canonical_name") or row.get("device") or row.get("name")
            ).upper()
            if name:
                out[name] = row
    return out


def _proposal_for_device(
    cluster_proposal: dict[str, Any] | None,
    device: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(cluster_proposal, dict):
        return None
    per = _per_device_proposals(cluster_proposal)
    name = _norm(device.get("canonical_name")).upper()
    if name in per:
        # Merge device override onto cluster defaults (override wins).
        merged = dict(cluster_proposal)
        merged.update(per[name])
        return merged
    return cluster_proposal


def _apply_accepted(
    device: dict[str, Any],
    accepted: dict[str, Any],
) -> None:
    device["final_status"] = accepted["final_status"]
    device["ownership"] = accepted.get("ownership") or device.get("ownership")
    if accepted.get("endpoint"):
        device["physical_endpoint"] = accepted["endpoint"]
    if accepted.get("controller"):
        device["controller"] = accepted["controller"]
    if accepted.get("evidence_class"):
        device["evidence_class"] = accepted["evidence_class"]
    if accepted.get("final_status") == STATUS_INTERNAL_LOGICAL:
        device["device_type"] = device.get("device_type") or "INTERNAL_LOGICAL"
        device["evidence_class"] = "INTERNAL_LOGICAL"
    device["confidence"] = accepted.get("confidence") or device.get("confidence")
    device["reason"] = accepted.get("reason") or device.get("reason")
    device["assignable"] = device["final_status"] in {
        STATUS_MAPPED,
        "ENGINEER_CONFIRMED",
    }


def _base_trace(device: dict[str, Any], cluster_id: str) -> dict[str, Any]:
    return {
        "cluster_id": cluster_id,
        "deterministic_attempt": {
            "ownership": device.get("ownership"),
            "code": device.get("deterministic_code"),
            "reason": device.get("reason"),
            "word_in_active_configio": device.get("word_in_active_configio"),
            "endpoint": device.get("physical_endpoint"),
        },
        "deterministic_result": {
            "ownership": device.get("ownership"),
            "code": device.get("deterministic_code"),
            "reason": device.get("reason"),
            "word_in_active_configio": device.get("word_in_active_configio"),
            "endpoint": device.get("physical_endpoint"),
        },
        "ai_api_called": "NO",
        "ai_result": None,
        "ai_validation": None,
        "relay_called": "NO",
        "relay_result": None,
        "relay_validation": None,
        "knowledge_base_evidence": [],
        "engineer_decision": None,
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
    """Escalate unresolved unique devices via site-level clusters. Mutates canonical."""
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
            d.setdefault("escalation_trace", {})
            d["escalation_trace"].update(
                {
                    "ai_api_called": "NO",
                    "relay_called": "NO",
                    "why_ai_not_called": "noncritical_physical_channel",
                    "why_relay_not_called": "noncritical_physical_channel",
                    "final_classification": st,
                    "cluster_id": None,
                    "knowledge_base_evidence": [],
                }
            )
            continue
        unresolved.append(d)

    if max_devices is not None:
        unresolved = unresolved[: max(0, int(max_devices))]

    clusters = form_ownership_clusters(unresolved)

    cf = BuildCaseFile(
        site=mach,
        machine=mach,
        run_sha="",
        build_id="prebuild-io",
    )
    if health is None:
        health = probe_escalation_services(case_file=cf)

    stats: dict[str, Any] = {
        "health": health,
        "candidates": len(unresolved),
        "clusters_formed": len(clusters),
        "cluster_ai_calls": 0,
        "cluster_relay_calls": 0,
        "ai_calls": 0,
        "ai_resolved": 0,
        "ai_unresolved": 0,
        "relay_calls": 0,
        "relay_resolved": 0,
        "relay_unresolved": 0,
        "engineer_confirm_required": 0,
        "skipped_service_unavailable": 0,
        "traces": [],
        "cluster_traces": [],
    }

    ai_available = bool((health.get("ai_api") or {}).get("available"))
    relay_available = bool((health.get("relay") or {}).get("available"))
    active_words_sorted = sorted(active_words)

    for cluster in clusters:
        cid = cluster["cluster_id"]
        members: list[dict[str, Any]] = cluster["devices"]
        cluster_trace: dict[str, Any] = {
            "cluster_id": cid,
            "size": len(members),
            "deterministic_code": cluster.get("deterministic_code"),
            "device_family": cluster.get("device_family"),
            "word_bucket": cluster.get("word_bucket"),
            "device_names": list(cluster.get("device_names") or []),
            "ai_api_called": "NO",
            "relay_called": "NO",
            "ai_resolved_devices": 0,
            "relay_resolved_devices": 0,
            "engineer_confirm_required": 0,
        }

        kb_evidence = _load_finished_site_knowledge(machine=mach, cluster=cluster)
        pack = _build_cluster_evidence_pack(
            cluster,
            machine=mach,
            active_words=active_words_sorted,
            by_word=by_word,
            finished_site_knowledge=kb_evidence,
        )

        # Health-down short circuit: no AI → engineer confirm for all members.
        if not ai_available:
            for d in members:
                trace = _base_trace(d, cid)
                trace.update(
                    {
                        "ai_api_called": "NO",
                        "relay_called": "NO",
                        "why_ai_not_called": "ESCALATION_SERVICE_UNAVAILABLE",
                        "why_relay_not_called": (
                            "ESCALATION_SERVICE_UNAVAILABLE"
                            if not relay_available
                            else "ai_unavailable_short_circuit"
                        ),
                        "knowledge_base_evidence": kb_evidence,
                        "final_classification": STATUS_ENGINEER_REQUIRED,
                        "engineer_confirmation_required": True,
                    }
                )
                d["final_status"] = STATUS_ENGINEER_REQUIRED
                d["escalation_trace"] = trace
                d["reason"] = "ESCALATION_SERVICE_UNAVAILABLE — engineer confirmation required"
                stats["skipped_service_unavailable"] += 1
                stats["engineer_confirm_required"] += 1
                cluster_trace["engineer_confirm_required"] += 1
                stats["traces"].append({"device": d.get("canonical_name"), **trace})
            cluster_trace["why_ai_not_called"] = "ESCALATION_SERVICE_UNAVAILABLE"
            stats["cluster_traces"].append(cluster_trace)
            continue

        # --- Cluster AI (ONE call) ---
        ai = call_ai_api_for_case(pack, case_file=cf)
        stats["ai_calls"] += 1
        stats["cluster_ai_calls"] += 1
        cluster_trace["ai_api_called"] = "YES"
        ai_response = ai.get("response") if ai.get("ok") else None
        cluster_trace["ai_result"] = {
            "ok": ai.get("ok"),
            "error": ai.get("error"),
            "response": ai_response,
            "meta": ai.get("meta"),
        }

        still_unresolved: list[dict[str, Any]] = []
        for d in members:
            trace = _base_trace(d, cid)
            trace["ai_api_called"] = "YES"
            trace["why_ai_not_called"] = ""
            trace["ai_result"] = cluster_trace["ai_result"]
            trace["knowledge_base_evidence"] = kb_evidence
            device_proposal = _proposal_for_device(ai_response if isinstance(ai_response, dict) else None, d)
            ai_val = _validate_ownership_proposal(
                device_proposal,
                device=d,
                machine=mach,
                active_words=active_words,
            )
            trace["ai_validation"] = ai_val
            if ai_val.get("ok") and not ai_val.get("engineer_required"):
                _apply_accepted(d, ai_val)
                trace["final_classification"] = d["final_status"]
                trace["engineer_confirmation_required"] = False
                stats["ai_resolved"] += 1
                cluster_trace["ai_resolved_devices"] += 1
                d["escalation_trace"] = trace
                stats["traces"].append(
                    {
                        "device": d.get("canonical_name"),
                        "cluster_id": cid,
                        "ai_api_called": "YES",
                        "relay_called": "NO",
                        "final_classification": d["final_status"],
                        "engineer_confirmation_required": False,
                    }
                )
            else:
                stats["ai_unresolved"] += 1
                still_unresolved.append(d)
                d["_pending_trace"] = trace

        # --- Cluster Relay (ONE call) if residuals remain ---
        if still_unresolved:
            if not relay_available:
                for d in still_unresolved:
                    trace = dict(d.pop("_pending_trace", _base_trace(d, cid)))
                    trace["relay_called"] = "NO"
                    trace["why_relay_not_called"] = "ESCALATION_SERVICE_UNAVAILABLE"
                    trace["relay_validation"] = {
                        "ok": False,
                        "reason": "ESCALATION_SERVICE_UNAVAILABLE",
                    }
                    d["final_status"] = STATUS_ENGINEER_REQUIRED
                    d["ownership"] = "UNKNOWN"
                    d["reason"] = "ESCALATION_SERVICE_UNAVAILABLE after cluster AI"
                    d["assignable"] = False
                    trace["final_classification"] = STATUS_ENGINEER_REQUIRED
                    trace["engineer_confirmation_required"] = True
                    d["escalation_trace"] = trace
                    stats["relay_unresolved"] += 1
                    stats["skipped_service_unavailable"] += 1
                    stats["engineer_confirm_required"] += 1
                    cluster_trace["engineer_confirm_required"] += 1
                    stats["traces"].append(
                        {
                            "device": d.get("canonical_name"),
                            "cluster_id": cid,
                            "ai_api_called": "YES",
                            "relay_called": "NO",
                            "final_classification": STATUS_ENGINEER_REQUIRED,
                            "engineer_confirmation_required": True,
                            "why_relay_not_called": "ESCALATION_SERVICE_UNAVAILABLE",
                        }
                    )
                cluster_trace["why_relay_not_called"] = "ESCALATION_SERVICE_UNAVAILABLE"
            else:
                relay_pack = dict(pack)
                relay_pack["prior_ai_conclusion"] = ai_response
                relay_pack["prior_ai_validation_summary"] = {
                    "ai_resolved_devices": cluster_trace["ai_resolved_devices"],
                    "still_unresolved": [
                        _norm(d.get("canonical_name")) for d in still_unresolved
                    ],
                    "sample_ai_validation": (
                        (still_unresolved[0].get("_pending_trace") or {}).get("ai_validation")
                        if still_unresolved
                        else None
                    ),
                }
                relay_pack["audit_mode"] = "SITE_LEVEL_RELAY_AUDIT"
                relay = call_relay_freeform(
                    relay_pack,
                    case_file=cf,
                    ai_response=ai_response if isinstance(ai_response, dict) else None,
                    purpose="io_ownership_cluster_audit",
                )
                stats["relay_calls"] += 1
                stats["cluster_relay_calls"] += 1
                cluster_trace["relay_called"] = "YES"
                relay_ok = bool(relay.get("ok")) or str(relay.get("status") or "") in {
                    "RELAY_COMPLETE",
                    "OK",
                    "COMPLETE",
                }
                relay_payload = relay.get("result") or relay.get("response")
                cluster_trace["relay_result"] = {
                    "ok": relay_ok,
                    "error": None if relay_ok else (relay.get("error") or relay.get("status")),
                    "result": relay_payload,
                    "meta": relay.get("meta"),
                }

                for d in still_unresolved:
                    trace = dict(d.pop("_pending_trace", _base_trace(d, cid)))
                    trace["relay_called"] = "YES"
                    trace["why_relay_not_called"] = ""
                    trace["relay_result"] = cluster_trace["relay_result"]
                    device_proposal = _proposal_for_device(
                        relay_payload if relay_ok and isinstance(relay_payload, dict) else None,
                        d,
                    )
                    relay_val = _validate_ownership_proposal(
                        device_proposal,
                        device=d,
                        machine=mach,
                        active_words=active_words,
                    )
                    trace["relay_validation"] = relay_val
                    if relay_val.get("ok") and not relay_val.get("engineer_required"):
                        _apply_accepted(d, relay_val)
                        trace["final_classification"] = d["final_status"]
                        trace["engineer_confirmation_required"] = False
                        stats["relay_resolved"] += 1
                        cluster_trace["relay_resolved_devices"] += 1
                    else:
                        d["final_status"] = STATUS_ENGINEER_REQUIRED
                        d["ownership"] = "UNKNOWN"
                        d["reason"] = (
                            relay_val.get("reason")
                            or (trace.get("ai_validation") or {}).get("reason")
                            or "cluster AI+Relay could not prove ownership"
                        )
                        d["assignable"] = False
                        trace["final_classification"] = STATUS_ENGINEER_REQUIRED
                        trace["engineer_confirmation_required"] = True
                        stats["relay_unresolved"] += 1
                        stats["engineer_confirm_required"] += 1
                        cluster_trace["engineer_confirm_required"] += 1
                    d["escalation_trace"] = trace
                    stats["traces"].append(
                        {
                            "device": d.get("canonical_name"),
                            "cluster_id": cid,
                            "ai_api_called": "YES",
                            "relay_called": "YES",
                            "final_classification": d["final_status"],
                            "engineer_confirmation_required": bool(
                                trace.get("engineer_confirmation_required")
                            ),
                        }
                    )

        stats["cluster_traces"].append(cluster_trace)

    # Recompute metrics after escalation mutations
    _recompute_canonical_metrics(canonical)
    canonical["prebuild_escalation"] = stats
    return stats


def _is_proven_spare(device: dict[str, Any]) -> bool:
    """SPARE counts as resolved only when explicitly proven — no unproven inflation."""
    st = _norm(device.get("final_status")).split(":")[0]
    if st != STATUS_SPARE:
        return False
    code = _norm(device.get("deterministic_code")).upper()
    reason = _norm(device.get("reason")).lower()
    name = _norm(device.get("canonical_name")).upper()
    eng = device.get("engineer_confirmation") or {}
    if _norm(eng.get("classification")).upper() == "MARK_SPARE":
        return True
    if code == "LOCAL_SPARE_CHANNEL" and (
        name.startswith("SPARE") or name in {"", "SPARE", "INVALID", "N/A", "NA"}
        or "spare" in name.lower()
    ):
        return True
    if "proven spare" in reason or "explicit spare" in reason:
        return True
    return False


def _is_internal_logical(device: dict[str, Any]) -> bool:
    if _norm(device.get("device_type")).upper() == "INTERNAL_LOGICAL":
        return True
    if _norm(device.get("evidence_class")).upper() == "INTERNAL_LOGICAL":
        return True
    if _norm(device.get("final_status")).split(":")[0] == STATUS_INTERNAL_LOGICAL:
        return True
    if _norm(device.get("ownership")).upper() == "INTERNAL":
        return True
    return False


def _recompute_canonical_metrics(canonical: dict[str, Any]) -> None:
    # Prefer ledger three-metric helper when present.
    try:
        from fortna_run_io_source_ledger import recompute_physical_io_metrics  # type: ignore

        if callable(recompute_physical_io_metrics):
            recompute_physical_io_metrics(canonical)
            return
    except ImportError:
        pass

    from fortna_run_io_source_ledger import (
        RESOLUTION_THRESHOLD_PCT,
        STATUS_ENGINEER_CONFIRMED,
        STATUS_FOREIGN,
        STATUS_MAPPED,
        STATUS_REVIEW,
        STATUS_SPARE,
        STATUS_UNSUPPORTED,
        STATUS_ENGINEER_REQUIRED,
    )

    devices = list(canonical.get("devices") or [])
    unique_foreign = [
        d
        for d in devices
        if d.get("final_status") == STATUS_FOREIGN or d.get("ownership") == "FOREIGN"
    ]
    # Physical denominator: exclude FOREIGN and INTERNAL_LOGICAL
    unique_local = [
        d
        for d in devices
        if d.get("ownership") != "FOREIGN"
        and d.get("final_status") != STATUS_FOREIGN
        and not _is_internal_logical(d)
    ]

    def _count(status: str) -> int:
        return sum(1 for d in devices if _norm(d.get("final_status")).split(":")[0] == status)

    def _is_resolved_local(d: dict[str, Any]) -> bool:
        st = _norm(d.get("final_status")).split(":")[0]
        if st in {STATUS_MAPPED, STATUS_UNSUPPORTED, STATUS_ENGINEER_CONFIRMED}:
            return True
        if st == STATUS_SPARE:
            return _is_proven_spare(d)
        return False

    local_resolved_n = sum(1 for d in unique_local if _is_resolved_local(d))
    local_denom = len(unique_local)
    resolution_pct = (
        round(100.0 * local_resolved_n / max(1, local_denom), 2) if local_denom else 0.0
    )
    local_named = [d for d in unique_local if d.get("device_type") != "PHYSICAL_CHANNEL"]
    gen_mapped = sum(1 for d in local_named if d.get("final_status") == STATUS_MAPPED)
    generated_pct = round(100.0 * gen_mapped / max(1, len(local_named)), 2)

    critical_unresolved = [
        d
        for d in unique_local
        if d.get("critical")
        and not _is_resolved_local(d)
        and _norm(d.get("final_status")).split(":")[0] != STATUS_FOREIGN
    ]

    # Best-effort three-metric mirrors when ledger helpers are absent.
    source_conservation = bool(canonical.get("source_conservation_ok"))
    if isinstance(canonical.get("evidence_reconcile"), dict):
        source_conservation = bool(
            (canonical.get("evidence_reconcile") or {}).get("conservation_ok", source_conservation)
        )

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
            "unique_internal_logical": sum(1 for d in devices if _is_internal_logical(d)),
            "device_resolution_coverage_pct": resolution_pct,
            "generated_io_coverage_pct": generated_pct,
            "physical_device_resolution_pct": resolution_pct,
            "generated_physical_io_pct": generated_pct,
            "source_conservation": source_conservation,
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

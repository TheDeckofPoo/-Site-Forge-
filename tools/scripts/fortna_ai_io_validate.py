#!/usr/bin/env python3
"""Deterministically validate AI I/O proposals.

AI proposes. Site Forge verifies. Rejected proposals never enter the model.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_asc import read_asc  # noqa: E402
from fortna_hardware_family import (  # noqa: E402
    channel_capacity_for_catalog,
    detect_family_from_catalog,
)
from fortna_physical_word_resolver import parse_eipcfg  # noqa: E402

ALLOWED_STATUS = frozenset({"PROVEN", "DERIVED", "REVIEW_REQUIRED", "UNKNOWN"})
FORBIDDEN_STATUS = frozenset({"GUESSED"})


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _load_conveyor_rows(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "FORTNA" / "Conveyor.asc"
    if not path.is_file():
        return []
    _, rows = read_asc(path)
    return rows


def _load_configio_index(evidence: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    by_word: dict[int, list[dict[str, Any]]] = {}
    for r in evidence.get("configio") or []:
        try:
            w = int(r.get("Octal_Word"))
        except (TypeError, ValueError):
            continue
        by_word.setdefault(w, []).append(r)
    return by_word


def _adapter_index(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for ad in (evidence.get("eipcfg") or {}).get("adapters") or []:
        rio = _norm(ad.get("rio_name") or ad.get("eipcfg_name"))
        if rio:
            out[rio.upper()] = ad
    return out


def _find_module(ad: dict[str, Any], slot: Any) -> dict[str, Any] | None:
    try:
        want = int(slot)
    except (TypeError, ValueError):
        return None
    for m in ad.get("modules") or []:
        try:
            if int(m.get("slot")) == want:
                return m
        except (TypeError, ValueError):
            continue
    return None


def _conveyor_row_blob(evidence: dict[str, Any], run_dir: Path, row: int) -> str | None:
    """Prefer evidence.conveyor (bundle-scoped); fall back to disk Conveyor.asc."""
    for r in evidence.get("conveyor") or []:
        try:
            if int(r.get("row")) == int(row):
                return " ".join(str(v) for v in r.values()).upper()
        except (TypeError, ValueError):
            continue
    rows = _load_conveyor_rows(run_dir)
    if row < 0 or row >= len(rows):
        return None
    return " ".join(str(v) for v in rows[row].values()).upper()


def _fact_token_hits(fact: str, blob: str) -> tuple[int, int]:
    """Return (hits, significant_token_count) for fact tokens found in blob.

    Also expands KEY=VALUE pairs so value tokens match value-only row blobs.
    """
    fact_u = (fact or "").upper()
    blob_u = (blob or "").upper()
    raw_tokens = re.findall(r"[A-Z0-9_\-]+", fact_u)
    # Prefer values from KEY=VALUE pairs (Configio/Conveyor facts are often labeled)
    values = re.findall(r"=\s*([A-Z0-9_\-]+)", fact_u)
    candidates = values + [t for t in raw_tokens if t not in {"OCTAL", "WORD", "BANK", "LOHI", "DESC", "INTERFACE", "IN", "OUT", "IO", "ADDRESS", "NAME", "BIT"}]
    # Dedupe preserve order; significant = len >= 1 for numeric, >= 2 otherwise
    seen: set[str] = set()
    sig: list[str] = []
    for t in candidates + raw_tokens:
        if t in seen:
            continue
        seen.add(t)
        if t.isdigit() or len(t) >= 2:
            sig.append(t)
    hits = sum(1 for t in sig if t in blob_u)
    return hits, len(sig)


def _cite_fact_present(source: str, row: int | None, fact: str, evidence: dict[str, Any], run_dir: Path) -> bool:
    """Verify cited source row actually contains the claimed fact tokens."""
    src = (source or "").lower()
    if "conveyor" in src:
        if row is None:
            return False
        blob = _conveyor_row_blob(evidence, run_dir, int(row))
        if not blob:
            return False
        hits, n = _fact_token_hits(fact, blob)
        return n > 0 and hits >= max(1, min(3, (n + 1) // 2))
    if "configio" in src:
        for r in evidence.get("configio") or []:
            if row is not None and int(r.get("row") or -1) != int(row):
                continue
            # Include keys+values so labeled facts (Octal_Word=611) can match
            parts = []
            for k, v in r.items():
                if isinstance(v, dict):
                    continue
                parts.append(str(k))
                parts.append(str(v))
            if isinstance(r.get("catalog_bank_parsed"), dict):
                parts.extend(str(v) for v in r["catalog_bank_parsed"].values())
            blob = " ".join(parts).upper()
            hits, n = _fact_token_hits(fact, blob)
            if n > 0 and hits >= max(1, min(3, (n + 1) // 2)):
                return True
            if row is not None:
                return False
        return False
    # Unknown source kind — reject (AI must cite known tables)
    return False


def validate_proposal(
    proposal: dict[str, Any],
    *,
    evidence: dict[str, Any],
    raw_by_id: dict[str, dict[str, Any]],
    run_dir: Path,
) -> dict[str, Any]:
    """Validate one AI claim proposal. Returns status + reasons."""
    claim_id = _norm(proposal.get("claim_id"))
    reasons: list[str] = []
    status = "REVIEW_REQUIRED"

    if not claim_id or claim_id not in raw_by_id:
        return {
            "accepted": False,
            "proposal_status": "UNKNOWN",
            "reasons": ["claim_id not in raw ledger"],
            "claim_id": claim_id,
        }

    raw = raw_by_id[claim_id]
    machine = _norm(evidence.get("machine")).upper()
    prop_machine = _norm(proposal.get("machine") or evidence.get("machine")).upper()
    if prop_machine and machine and prop_machine != machine:
        return {
            "accepted": False,
            "proposal_status": "UNKNOWN",
            "reasons": ["foreign-machine claim rejected"],
            "claim_id": claim_id,
        }

    # Foreign Machine_Name on raw claim
    raw_mach = _norm(raw.get("machine")).upper()
    if raw_mach and raw_mach not in {"", "N/A", "NA", "NONE", "INVALID", "ALL", "0"}:
        if machine and raw_mach != machine:
            return {
                "accepted": False,
                "proposal_status": "UNKNOWN",
                "reasons": ["foreign-machine raw claim rejected"],
                "claim_id": claim_id,
            }

    ai_status = _norm(proposal.get("proposal_status")).upper()
    if ai_status in FORBIDDEN_STATUS or ai_status == "GUESSED":
        return {
            "accepted": False,
            "proposal_status": "UNKNOWN",
            "reasons": ["AI returned forbidden status GUESSED"],
            "claim_id": claim_id,
        }

    ep = proposal.get("physical_endpoint") if isinstance(proposal.get("physical_endpoint"), dict) else {}
    adapter = _norm(ep.get("adapter"))
    slot = ep.get("slot")
    direction = _norm(ep.get("direction")).upper()
    data_index = ep.get("data_index")
    bit = ep.get("bit")
    channel = _norm(ep.get("channel"))
    family = _norm(ep.get("family"))

    ads = _adapter_index(evidence)
    ad = ads.get(adapter.upper()) if adapter else None
    if not ad:
        return {
            "accepted": False,
            "proposal_status": "UNKNOWN",
            "reasons": [f"invented adapter rejected: {adapter or '(empty)'}"],
            "claim_id": claim_id,
        }

    mod = _find_module(ad, slot)
    if not mod:
        return {
            "accepted": False,
            "proposal_status": "UNKNOWN",
            "reasons": [f"module slot {slot} does not exist on {adapter}"],
            "claim_id": claim_id,
        }

    catalog = _norm(mod.get("catalog") or mod.get("type"))
    fam = detect_family_from_catalog(catalog) or ""
    if family and fam and family.replace("_", "") not in fam.replace("-", "") and fam not in family:
        # soft family check — 1794_FLEX vs 1794
        if "1794" in family and "1794" not in fam and "1734" in family and "1734" not in fam:
            reasons.append(f"family mismatch proposal={family} module={fam}")

    try:
        bit_i = int(bit)
    except (TypeError, ValueError):
        return {
            "accepted": False,
            "proposal_status": "UNKNOWN",
            "reasons": ["bad bit"],
            "claim_id": claim_id,
        }
    cap = channel_capacity_for_catalog(catalog)
    if cap > 0 and (bit_i < 0 or bit_i >= cap):
        return {
            "accepted": False,
            "proposal_status": "UNKNOWN",
            "reasons": [f"bit {bit_i} outside channel capacity {cap} for {catalog}"],
            "claim_id": claim_id,
        }

    # Channel string shape
    if channel:
        m = re.match(
            r"^([A-Za-z0-9_]+):(I|O)\.Data\[(\d+)\]\.(\d+)$",
            channel,
        )
        if not m:
            return {
                "accepted": False,
                "proposal_status": "UNKNOWN",
                "reasons": [f"bad channel format: {channel}"],
                "claim_id": claim_id,
            }
        if m.group(1).upper() != adapter.upper():
            reasons.append("channel adapter mismatch")
        if m.group(2).upper() != direction:
            reasons.append("channel direction mismatch")
        try:
            if int(m.group(3)) != int(data_index):
                reasons.append("channel data_index mismatch")
            if int(m.group(4)) != bit_i:
                reasons.append("channel bit mismatch")
        except (TypeError, ValueError):
            reasons.append("channel index parse error")

    # Evidence citations
    evidence_ok = 0
    cites = proposal.get("evidence") if isinstance(proposal.get("evidence"), list) else []
    if not cites:
        reasons.append("no evidence citations")
    for cite in cites:
        if not isinstance(cite, dict):
            reasons.append("malformed evidence cite")
            continue
        src = _norm(cite.get("source"))
        try:
            row = int(cite.get("row")) if cite.get("row") is not None else None
        except (TypeError, ValueError):
            row = None
        fact = _norm(cite.get("fact"))
        if not src or not fact:
            reasons.append("empty evidence cite")
            continue
        if _cite_fact_present(src, row, fact, evidence, run_dir):
            evidence_ok += 1
        else:
            reasons.append(f"invented/mismatched source row rejected: {src}#{row}")

    # Configio word when claimed in evidence
    cfg_index = _load_configio_index(evidence)
    try:
        word_i = int(raw.get("word"))
    except (TypeError, ValueError):
        word_i = None
    if word_i is not None and word_i not in cfg_index:
        # Not fatal alone — some sites resolve without Configio word present
        reasons.append(f"Configio word {word_i} not present in evidence")

    # Decide
    hard_reject = any(
        "invented" in r.lower()
        or "rejected" in r.lower()
        or "bad bit" in r.lower()
        or "bad channel" in r.lower()
        or "does not exist" in r.lower()
        or "foreign-machine" in r.lower()
        for r in reasons
    )
    if hard_reject or evidence_ok == 0:
        return {
            "accepted": False,
            "proposal_status": "UNKNOWN",
            "reasons": reasons or ["rejected"],
            "claim_id": claim_id,
            "logical_name": proposal.get("logical_name") or raw.get("io_name"),
            "physical_endpoint": ep,
        }

    if reasons or evidence_ok < 2:
        status = "REVIEW_REQUIRED"
        accepted = False  # does not enter DERIVED model; stays review
    else:
        status = "DERIVED"
        accepted = True

    return {
        "accepted": accepted,
        "proposal_status": status,
        "reasons": reasons,
        "claim_id": claim_id,
        "logical_name": proposal.get("logical_name") or raw.get("io_name"),
        "physical_endpoint": ep,
        "evidence": cites,
        "explanation": proposal.get("explanation"),
    }


TERMINAL_DET = frozenset(
    {"ASSIGNED", "UNRESOLVED_OWNER", "OWNER_CONFLICT", "physical_resolution_failure"}
)
TERMINAL_AI = frozenset({"ai_derived", "ai_review_required"})

# Claims that still require engineer/AI resolution. Conservation PASS ≠ solved.
NEEDS_RESOLUTION_STATES = frozenset(
    {
        "UNRESOLVED_OWNER",
        "OWNER_CONFLICT",
        "physical_resolution_failure",
        "ai_review_required",
    }
)

EVIDENCE_READY = "READY"
EVIDENCE_NEEDS_RESOLUTION = "NEEDS_RESOLUTION"
EVIDENCE_ALTERNATE = "ALTERNATE_EVIDENCE_REQUIRED"
EVIDENCE_MISSING = "EVIDENCE_MISSING"


def needs_resolution_count(counts: dict[str, Any] | None) -> int:
    """Sum of terminal states that still need resolution (includes phys_fail)."""
    c = counts or {}
    return sum(int(c.get(k) or 0) for k in NEEDS_RESOLUTION_STATES)


def derive_evidence_status(
    *,
    raw_physical_claims: int,
    needs_resolution: int,
    conservation_ok: bool,
    configio_words: int = 0,
    nonphysical_excluded: int = 0,
    fixture_role: str = "",
    run_available: bool = True,
) -> str:
    """Evidence/readiness — independent of conservation PASS/FAIL.

    conservation PASS only means every raw claim is accounted exactly once.
    Zero physical claims with no Configio is ALTERNATE_EVIDENCE, never READY.
    """
    if not run_available:
        return EVIDENCE_MISSING
    role = (fixture_role or "").strip().lower()
    if role in {"alternate_evidence", "alternate"}:
        return EVIDENCE_ALTERNATE
    if int(raw_physical_claims or 0) <= 0:
        # 0 = 0 conservation must never become I/O READY / solved
        if int(configio_words or 0) <= 0 or int(nonphysical_excluded or 0) > 0:
            return EVIDENCE_ALTERNATE
        return EVIDENCE_MISSING
    if int(needs_resolution or 0) > 0:
        return EVIDENCE_NEEDS_RESOLUTION
    if conservation_ok:
        return EVIDENCE_READY
    # Conserved accounting failed — still not READY
    return EVIDENCE_NEEDS_RESOLUTION


def enrich_conservation_with_readiness(
    conservation: dict[str, Any],
    *,
    configio_words: int = 0,
    nonphysical_excluded: int = 0,
    fixture_role: str = "",
    run_available: bool = True,
) -> dict[str, Any]:
    """Attach needs_resolution + evidence_status to a conservation result."""
    counts = conservation.get("counts") or {}
    needs = needs_resolution_count(counts)
    status = derive_evidence_status(
        raw_physical_claims=int(conservation.get("raw_physical_claims") or 0),
        needs_resolution=needs,
        conservation_ok=bool(conservation.get("ok")),
        configio_words=configio_words,
        nonphysical_excluded=nonphysical_excluded,
        fixture_role=fixture_role,
        run_available=run_available,
    )
    out = dict(conservation)
    out["needs_resolution"] = needs
    out["evidence_status"] = status
    out["proven"] = int(counts.get("ASSIGNED") or 0) + int(counts.get("ai_derived") or 0)
    out["assigned"] = int(counts.get("ASSIGNED") or 0)
    return out


def compute_claim_conservation(
    evidence: dict[str, Any],
    *,
    accepted: list[dict[str, Any]] | None = None,
    review_required: list[dict[str, Any]] | None = None,
    rejected: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Real conservation: every physical raw claim_id in exactly one terminal state.

    RAW PHYSICAL CLAIMS =
      deterministic ASSIGNED
      + deterministic UNRESOLVED_OWNER
      + OWNER_CONFLICT
      + physical_resolution_failure
      + AI-derived accepted
      + AI review_required

    AI-rejected proposals do NOT move the claim — it stays in its deterministic
    terminal state. lost/duplicate must both be zero for PASS.
    """
    raw_claims = evidence.get("raw_claims") or []
    raw_ids = [c.get("claim_id") for c in raw_claims if c.get("claim_id")]
    raw_set = set(raw_ids)

    accepted = accepted or []
    review_required = review_required or []
    rejected = rejected or []

    ai_derived_ids = {
        r.get("claim_id")
        for r in accepted
        if r.get("claim_id") and r.get("accepted") and r.get("proposal_status") == "DERIVED"
    }
    ai_review_ids = {
        r.get("claim_id")
        for r in review_required
        if r.get("claim_id") and r.get("proposal_status") == "REVIEW_REQUIRED"
    }
    # Rejected proposals never become a terminal claim state
    _ = rejected

    # Incompatible: same claim in both AI derived and AI review
    ai_dup = ai_derived_ids & ai_review_ids
    # Prefer DERIVED if both (should not happen); drop from review set for accounting
    ai_review_ids -= ai_derived_ids

    terminal: dict[str, str] = {}
    buckets: dict[str, list[str]] = {
        "ASSIGNED": [],
        "UNRESOLVED_OWNER": [],
        "OWNER_CONFLICT": [],
        "physical_resolution_failure": [],
        "ai_derived": [],
        "ai_review_required": [],
    }
    duplicate_accounting_ids: list[str] = sorted(ai_dup)

    for c in raw_claims:
        cid = c.get("claim_id")
        if not cid:
            continue
        states: list[str] = []
        if cid in ai_derived_ids:
            states.append("ai_derived")
        if cid in ai_review_ids:
            states.append("ai_review_required")
        if not states:
            disp = str(c.get("deterministic_disposition") or "physical_resolution_failure")
            if disp not in TERMINAL_DET:
                disp = "physical_resolution_failure"
            states.append(disp)
        if len(states) > 1:
            duplicate_accounting_ids.append(cid)
            # Keep first for primary map but flag duplicate
        primary = states[0]
        terminal[cid] = primary
        buckets.setdefault(primary, []).append(cid)

    accounted_ids = set(terminal.keys())
    lost_claim_ids = sorted(raw_set - accounted_ids)
    # Also flag raw claims missing claim_id
    missing_id_count = sum(1 for c in raw_claims if not c.get("claim_id"))

    counts = {k: len(v) for k, v in buckets.items()}
    accounted_n = sum(counts.values())
    raw_n = len(raw_claims)
    lost_n = len(lost_claim_ids) + missing_id_count
    dup_n = len(set(duplicate_accounting_ids))
    ok = lost_n == 0 and dup_n == 0 and accounted_n == raw_n
    needs = needs_resolution_count(counts)

    return {
        "ok": ok,
        "conservation": "PASS" if ok else "FAIL",
        "raw_physical_claims": raw_n,
        "accounted_claims": accounted_n,
        "lost_claims": lost_n,
        "duplicate_accounting": dup_n,
        "needs_resolution": needs,
        "assigned": int(counts.get("ASSIGNED") or 0),
        "proven": int(counts.get("ASSIGNED") or 0) + int(counts.get("ai_derived") or 0),
        "lost_claim_ids": lost_claim_ids[:50],
        "duplicate_accounting_ids": sorted(set(duplicate_accounting_ids))[:50],
        "counts": counts,
        "equation": (
            "raw_physical = ASSIGNED + UNRESOLVED_OWNER + OWNER_CONFLICT + "
            "physical_resolution_failure + ai_derived + ai_review_required"
        ),
        "needs_resolution_equation": (
            "needs_resolution = UNRESOLVED_OWNER + OWNER_CONFLICT + "
            "physical_resolution_failure + ai_review_required"
        ),
        "terminal_by_claim": terminal,
    }


def validate_ai_response(
    ai_payload: dict[str, Any],
    evidence: dict[str, Any],
    *,
    run_dir: Path | None = None,
) -> dict[str, Any]:
    run_dir = Path(run_dir or evidence.get("run_dir") or ".")
    raw_claims = evidence.get("raw_claims") or []
    raw_by_id = {c["claim_id"]: c for c in raw_claims if c.get("claim_id")}
    claims_in = ai_payload.get("claims") if isinstance(ai_payload.get("claims"), list) else []

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []

    for prop in claims_in:
        if not isinstance(prop, dict):
            rejected.append({"accepted": False, "reasons": ["malformed claim"], "proposal_status": "UNKNOWN"})
            continue
        result = validate_proposal(prop, evidence=evidence, raw_by_id=raw_by_id, run_dir=run_dir)
        if result.get("accepted") and result.get("proposal_status") == "DERIVED":
            accepted.append(result)
        elif result.get("proposal_status") == "REVIEW_REQUIRED":
            review.append(result)
        else:
            rejected.append(result)

    cc = evidence.get("conservation_counts") or {}
    conservation = enrich_conservation_with_readiness(
        compute_claim_conservation(
            evidence,
            accepted=accepted,
            review_required=review,
            rejected=rejected,
        ),
        configio_words=int(cc.get("configio_words") or len(evidence.get("configio") or [])),
        nonphysical_excluded=int(
            cc.get("nonphysical_excluded")
            or evidence.get("nonphysical_claims_count")
            or 0
        ),
        fixture_role=str(evidence.get("fixture_role") or ""),
    )
    return {
        "ok": True,
        "machine": evidence.get("machine"),
        "raw_claims": conservation["raw_physical_claims"],
        "ai_proposed": len(claims_in),
        "ai_validator_accepted": len(accepted),
        "ai_validator_rejected": len(rejected),
        "ai_validator_review": len(review),
        "lost_claims": conservation["lost_claims"],
        "duplicate_accounting": conservation["duplicate_accounting"],
        "accounted_claims": conservation["accounted_claims"],
        "needs_resolution": conservation["needs_resolution"],
        "evidence_status": conservation["evidence_status"],
        "conservation": conservation,
        "conservation_ok": conservation["ok"],
        "accepted": accepted,
        "review_required": review,
        "rejected": rejected,
        "unresolved_from_ai": ai_payload.get("unresolved") or [],
        "warnings": ai_payload.get("warnings") or [],
    }


def _unwrap_ai_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept either bare schema payload or resolver wrapper {ok, response: {...}}."""
    if isinstance(raw.get("response"), dict) and (
        "claims" in raw["response"] or raw.get("ok") is not None
    ):
        return raw["response"]
    return raw


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate AI I/O proposals")
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--ai-response", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    ai_raw = json.loads(args.ai_response.read_text(encoding="utf-8"))
    if not isinstance(ai_raw, dict):
        print(json.dumps({"ok": False, "error": "malformed AI response"}, indent=2))
        return 2
    ai_payload = _unwrap_ai_payload(ai_raw)
    result = validate_ai_response(ai_payload, evidence)
    out = args.out or args.ai_response.with_name("validated.json")
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"ok": result.get("ok"), "out": str(out), **{k: result[k] for k in (
        "raw_claims", "ai_proposed", "ai_validator_accepted", "ai_validator_rejected", "ai_validator_review", "lost_claims"
    )}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

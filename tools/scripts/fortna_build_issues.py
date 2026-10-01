#!/usr/bin/env python3
"""Site Forge BUILD ISSUES manifest — engineer-readable closeout of a build attempt.

Every Autogen attempt that reaches report construction should emit:
  {SITE}_BUILD_ISSUES.txt
  {SITE}_BUILD_ISSUES.json

Derives issues generically from the autogen report (no site special-cases).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SECTION_ORDER: tuple[str, ...] = (
    "BLOCKERS",
    "REVIEW REQUIRED",
    "UNRESOLVED I/O",
    "DUPLICATE / COLLISION",
    "UNSUPPORTED BETA FUNCTION",
    "WITHHELD FROM L5X",
    "SAFETY",
    "WRITER / OUTPUT ISSUES",
    "REPORT / ARTIFACT ISSUES",
    "WARNINGS / HYGIENE",
)

_ORI100_COMMISSIONING_GAPS: tuple[tuple[str, str], ...] = (
    (
        "held-Start",
        "Area_HMI Start path is present, but held-Start / anti-tie-down commissioning "
        "is not proven (physical_control_station=NONE_PROVEN).",
    ),
    (
        "jam reset",
        "Area_HMI.Jam_Reset commissioning path is not proven without a physical "
        "control station (NONE_PROVEN).",
    ),
    (
        "motor-fault reset",
        "Area_HMI.Motor_Fault_Reset commissioning path is not proven without a "
        "physical control station (NONE_PROVEN).",
    ),
    (
        "proven Area stop",
        "Proven physical Area stop (CS Stop_PB) is not available; HMI Stop alone "
        "is not commissioning-complete when physical_control_station=NONE_PROVEN.",
    ),
    (
        "fault/jam roll-up",
        "Fault/jam roll-up to Area_HMI/PI is not commissioning-complete without a "
        "proven physical control station (NONE_PROVEN).",
    ),
)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, (set, frozenset)):
        return list(value)
    return [value]


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "none", "null"}
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return bool(value)


def _issue(
    *,
    object_device: str = "",
    subsystem: str = "",
    severity: str = "",
    reason: str = "",
    source: str = "",
    site_forge_did: str = "REVIEW_ONLY",
    effect: str = "NON_BLOCKING",
    engineer_action: str = "",
    **extra: Any,
) -> dict[str, Any]:
    """Normalize one issue record."""
    rec: dict[str, Any] = {
        "object/device": object_device or "",
        "subsystem": subsystem or "",
        "severity/classification": severity or "",
        "reason": reason or "",
        "source/provenance": source or "",
        "what Site Forge did": site_forge_did or "REVIEW_ONLY",
        "effect": effect or "NON_BLOCKING",
        "engineer action": engineer_action or "",
    }
    for k, v in extra.items():
        if v is not None and k not in rec:
            rec[k] = v
    return rec


def _normalize_item(item: Any, *, default_object: str = "") -> dict[str, Any]:
    """Coerce planted string/dict issue-like values into a record."""
    if isinstance(item, dict):
        obj = (
            item.get("object/device")
            or item.get("object")
            or item.get("device")
            or item.get("name")
            or item.get("tag")
            or item.get("operand")
            or item.get("fortna_name")
            or default_object
            or ""
        )
        return _issue(
            object_device=str(obj or ""),
            subsystem=str(
                item.get("subsystem")
                or item.get("system")
                or item.get("area")
                or ""
            ),
            severity=str(
                item.get("severity/classification")
                or item.get("severity")
                or item.get("classification")
                or item.get("status")
                or item.get("fidelity_class")
                or ""
            ),
            reason=str(
                item.get("reason")
                or item.get("detail")
                or item.get("message")
                or item.get("note")
                or item.get("missing_evidence")
                or ""
            ),
            source=str(
                item.get("source/provenance")
                or item.get("source")
                or item.get("provenance")
                or item.get("producer")
                or ""
            ),
            site_forge_did=str(
                item.get("what Site Forge did")
                or item.get("site_forge_did")
                or item.get("action")
                or "REVIEW_ONLY"
            ),
            effect=str(item.get("effect") or "NON_BLOCKING"),
            engineer_action=str(
                item.get("engineer action")
                or item.get("engineer_action")
                or item.get("action_required")
                or ""
            ),
        )
    text = str(item or "").strip()
    return _issue(
        object_device=default_object or text,
        reason=text if default_object else "",
    )


def classify_build_status(
    report: dict,
    *,
    structural_ok: bool,
    promoted: bool,
) -> str:
    """SUCCESS | PARTIAL | BLOCKED per mission definitions.

    SUCCESS: structurally valid; no material intentionally withheld for stated scope
    PARTIAL: structurally valid but explicit REVIEW/unsupported/withheld remain
    BLOCKED: hard generation/integrity gate failed; cannot promote trustworthy artifact
    """
    rep = report if isinstance(report, dict) else {}
    assertions = rep.get("generation_assertions")
    assertion_failed = False
    if isinstance(assertions, dict):
        if assertions.get("ok") is False:
            assertion_failed = True
        if _as_list(assertions.get("failures")):
            assertion_failed = True

    hard_block = (
        (not structural_ok)
        or _truthy(rep.get("build_failed"))
        or assertion_failed
        or (
            isinstance(rep.get("ok"), bool)
            and rep.get("ok") is False
            and _truthy(rep.get("build_failed"))
        )
    )

    # Symbol-closure hard fail and studio ERROR also block promotion.
    sc = rep.get("symbol_closure")
    if isinstance(sc, dict) and (
        sc.get("ok") is False or int(sc.get("failure_count") or 0) > 0 or _as_list(sc.get("failures"))
    ):
        hard_block = True

    sp = rep.get("studio_preflight")
    if isinstance(sp, dict):
        if sp.get("ok") is False:
            hard_block = True
        for iss in _as_list(sp.get("issues")):
            if isinstance(iss, dict) and str(iss.get("severity") or "").upper() == "ERROR":
                hard_block = True
                break

    fav = rep.get("final_artifact_validation")
    if isinstance(fav, dict) and fav.get("ok") is False and _as_list(fav.get("errors")):
        hard_block = True

    if hard_block:
        return "BLOCKED"

    material_open = _has_material_open_issues(rep)
    # A promoted artifact with no open material issues is SUCCESS even if caller
    # passed promoted=False (promotion is advisory for classification).
    _ = promoted  # reserved for callers that gate CURRENT promotion separately
    if material_open:
        return "PARTIAL"
    return "SUCCESS"


def _has_material_open_issues(report: dict) -> bool:
    """True when explicit REVIEW / unsupported / withheld remain in scope."""
    if _as_list(report.get("merges_withheld_review")):
        return True
    if int(report.get("merges_withheld_count") or 0) > 0:
        return True

    wc = report.get("writer_coverage")
    if isinstance(wc, dict):
        by = wc.get("by_class") if isinstance(wc.get("by_class"), dict) else {}
        for key in (
            "INTENTIONALLY_UNDRIVEN_REVIEW",
            "UNSUPPORTED",
            "DEFECT",
        ):
            if _as_list(by.get(key)):
                return True
        if int(wc.get("intentional_review_outputs") or 0) > 0:
            return True
        if int(wc.get("writerless_defect_outputs") or 0) > 0:
            return True

    fd = report.get("function_disclosure")
    if isinstance(fd, dict):
        for name, meta in fd.items():
            if name == "policy" or not isinstance(meta, dict):
                continue
            st = str(meta.get("status") or "").upper()
            if st in {
                "REVIEW_WITHHELD",
                "UNSUPPORTED_BETA_FUNCTION",
                "UNSUPPORTED",
                "REVIEW_REQUIRED",
                "REVIEW",
            }:
                return True

    es = report.get("es_program")
    if isinstance(es, dict):
        st = str(es.get("status") or "").upper()
        if st in {"REVIEW_REQUIRED", "REVIEW", "OMITTED", "PARTIAL"}:
            return True
        if _as_list(es.get("omitted_zones")) or _as_list(es.get("omitted")):
            return True
        if es.get("report_matches_artifact") is False:
            return True

    run = report.get("runnability")
    if isinstance(run, dict) and str(run.get("COMMISSIONING_READY") or "").upper() == "NO":
        # Commissioning NO alone does not force PARTIAL if structure is clean and
        # nothing was intentionally withheld — but with Area_HMI + NONE_PROVEN the
        # ORI-100 gaps are material review items.
        ac = run.get("area_command") if isinstance(run.get("area_command"), dict) else {}
        if not ac:
            es = report.get("es_program") if isinstance(report.get("es_program"), dict) else {}
            ac = es.get("area_command_path") if isinstance(es.get("area_command_path"), dict) else {}
        if (
            str(ac.get("command_source") or "").strip() == "Area_HMI"
            and str(ac.get("physical_control_station") or "").upper() == "NONE_PROVEN"
        ):
            return True

    if _collect_unresolved_io_raw(report):
        return True

    return False


def _collect_unresolved_io_raw(report: dict) -> list[Any]:
    """Gather unresolved / UNKNOWN I/O entries from common report shapes."""
    found: list[Any] = []

    for key in (
        "unresolved_io",
        "io_unresolved",
        "unresolved_io_points",
        "io_unknown",
        "unknown_io",
    ):
        found.extend(_as_list(report.get(key)))

    io_block = report.get("io")
    if isinstance(io_block, dict):
        for key in ("unresolved", "unknown", "unresolved_io", "UNKNOWN"):
            found.extend(_as_list(io_block.get(key)))

    stage0 = report.get("stage0")
    if isinstance(stage0, dict):
        for key in (
            "unresolved",
            "unresolved_sample",
            "CLAIMS_UNRESOLVED_SAMPLE",
            "unresolved_claims",
            "UNKNOWN",
        ):
            found.extend(_as_list(stage0.get(key)))

    # Generic list-of-claim shapes with status/classification markers.
    for key in ("io_points", "claims", "resolved_rows", "physical_claims"):
        for row in _as_list(report.get(key)):
            if not isinstance(row, dict):
                continue
            markers = " ".join(
                str(row.get(k) or "")
                for k in (
                    "status",
                    "classification",
                    "owner_state",
                    "fidelity_class",
                    "confidence",
                    "endpoint_confidence",
                    "mapped",
                )
            ).upper()
            if any(
                tok in markers
                for tok in (
                    "UNRESOLVED",
                    "UNKNOWN",
                    "UNMAPPED",
                    "NOT_MAPPED",
                )
            ):
                found.append(row)

    # Deduplicate while preserving order (stringify dicts stably).
    out: list[Any] = []
    seen: set[str] = set()
    for item in found:
        if isinstance(item, dict):
            sig = json.dumps(item, sort_keys=True, default=str)
        else:
            sig = str(item)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(item)
    return out


def _area_command(report: dict) -> dict[str, Any]:
    run = report.get("runnability")
    if isinstance(run, dict) and isinstance(run.get("area_command"), dict):
        return dict(run["area_command"])
    es = report.get("es_program")
    if isinstance(es, dict) and isinstance(es.get("area_command_path"), dict):
        return dict(es["area_command_path"])
    return {}


def build_issues_manifest(
    report: dict,
    *,
    site: str,
    git_sha: str = "",
    tar_hash: str = "",
    build_id: str = "",
    timestamp: str = "",
    l5x_generated: bool = False,
    l5x_promoted: bool = False,
    l5x_path: str = "",
    build_status: str = "",
    commissioning_ready: str = "",
) -> dict:
    """Return structured manifest dict with keys matching TXT sections."""
    rep = report if isinstance(report, dict) else {}
    site_name = str(site or rep.get("project") or "").strip()

    sections: dict[str, list[dict[str, Any]]] = {name: [] for name in SECTION_ORDER}

    def add(section: str, issue: dict[str, Any]) -> None:
        if section not in sections:
            sections[section] = []
        sections[section].append(issue)

    # --- BLOCKERS: hard generation / integrity failures ---
    if _truthy(rep.get("build_failed")):
        add(
            "BLOCKERS",
            _issue(
                object_device=site_name,
                subsystem="generation",
                severity="BLOCKER",
                reason=str(rep.get("error") or "build_failed=true"),
                source="report.build_failed",
                site_forge_did="BLOCKED",
                effect="STRUCTURAL",
                engineer_action="Resolve generation failure before promoting L5X.",
            ),
        )
    elif rep.get("error"):
        add(
            "BLOCKERS",
            _issue(
                object_device=site_name,
                subsystem="generation",
                severity="BLOCKER",
                reason=str(rep.get("error")),
                source="report.error",
                site_forge_did="BLOCKED",
                effect="STRUCTURAL",
                engineer_action="Inspect report.error and re-run generation.",
            ),
        )

    assertions = rep.get("generation_assertions")
    if isinstance(assertions, dict):
        for fail in _as_list(assertions.get("failures")):
            rec = _normalize_item(fail, default_object="generation_assertion")
            rec["subsystem"] = rec["subsystem"] or "generation"
            rec["severity/classification"] = rec["severity/classification"] or "BLOCKER"
            rec["source/provenance"] = rec["source/provenance"] or "generation_assertions.failures"
            rec["what Site Forge did"] = "BLOCKED"
            rec["effect"] = "STRUCTURAL"
            if not rec["engineer action"]:
                rec["engineer action"] = "Fix assertion failure and regenerate."
            add("BLOCKERS", rec)
        if assertions.get("ok") is False and not _as_list(assertions.get("failures")):
            add(
                "BLOCKERS",
                _issue(
                    object_device=site_name,
                    subsystem="generation",
                    severity="BLOCKER",
                    reason="generation_assertions.ok=false",
                    source="generation_assertions",
                    site_forge_did="BLOCKED",
                    effect="STRUCTURAL",
                    engineer_action="Inspect generation assertions and regenerate.",
                ),
            )

    sc = rep.get("symbol_closure")
    if isinstance(sc, dict):
        failures = _as_list(sc.get("failures"))
        if sc.get("ok") is False or int(sc.get("failure_count") or 0) > 0 or failures:
            if failures:
                for fail in failures:
                    rec = _normalize_item(fail)
                    rec["subsystem"] = rec["subsystem"] or "symbol_closure"
                    rec["severity/classification"] = (
                        rec["severity/classification"] or "FAIL"
                    )
                    rec["source/provenance"] = (
                        rec["source/provenance"] or "symbol_closure.failures"
                    )
                    rec["what Site Forge did"] = "BLOCKED"
                    rec["effect"] = "STRUCTURAL"
                    if not rec["engineer action"]:
                        rec["engineer action"] = (
                            "Declare missing symbol owner or remove dangling operand."
                        )
                    add("BLOCKERS", rec)
            else:
                add(
                    "BLOCKERS",
                    _issue(
                        object_device=site_name,
                        subsystem="symbol_closure",
                        severity="FAIL",
                        reason=f"symbol_closure failure_count={sc.get('failure_count')}",
                        source="symbol_closure",
                        site_forge_did="BLOCKED",
                        effect="STRUCTURAL",
                        engineer_action="Resolve symbol closure failures before promote.",
                    ),
                )
            # Mirror into REPORT when closure failed (integrity of reported artifact).
            add(
                "REPORT / ARTIFACT ISSUES",
                _issue(
                    object_device=site_name,
                    subsystem="symbol_closure",
                    severity="FAIL",
                    reason="Symbol closure reported failures against generated artifact.",
                    source="symbol_closure",
                    site_forge_did="BLOCKED",
                    effect="STRUCTURAL",
                    engineer_action="Treat artifact as untrustworthy until closure is green.",
                ),
            )

    sp = rep.get("studio_preflight")
    if isinstance(sp, dict):
        for iss in _as_list(sp.get("issues")):
            if not isinstance(iss, dict):
                continue
            sev = str(iss.get("severity") or "").upper()
            if sev == "ERROR":
                rec = _normalize_item(iss)
                rec["subsystem"] = rec["subsystem"] or "studio_preflight"
                rec["severity/classification"] = "ERROR"
                rec["source/provenance"] = (
                    rec["source/provenance"] or "studio_preflight.issues"
                )
                rec["what Site Forge did"] = "BLOCKED"
                rec["effect"] = "STRUCTURAL"
                if not rec["engineer action"]:
                    rec["engineer action"] = "Fix Studio preflight ERROR before import."
                add("BLOCKERS", rec)
            elif sev == "WARNING":
                rec = _normalize_item(iss)
                rec["subsystem"] = rec["subsystem"] or "studio_preflight"
                rec["severity/classification"] = "WARNING"
                rec["source/provenance"] = (
                    rec["source/provenance"] or "studio_preflight.issues"
                )
                rec["effect"] = "NON_BLOCKING"
                add("WARNINGS / HYGIENE", rec)
        if sp.get("ok") is False and not any(
            isinstance(i, dict) and str(i.get("severity") or "").upper() == "ERROR"
            for i in _as_list(sp.get("issues"))
        ):
            add(
                "BLOCKERS",
                _issue(
                    object_device=site_name,
                    subsystem="studio_preflight",
                    severity="ERROR",
                    reason="studio_preflight.ok=false",
                    source="studio_preflight",
                    site_forge_did="BLOCKED",
                    effect="STRUCTURAL",
                    engineer_action="Inspect studio_preflight report.",
                ),
            )

    fav = rep.get("final_artifact_validation")
    if isinstance(fav, dict):
        for err in _as_list(fav.get("errors")):
            rec = _normalize_item(err, default_object="final_artifact")
            rec["subsystem"] = rec["subsystem"] or "final_artifact"
            rec["severity/classification"] = rec["severity/classification"] or "ERROR"
            rec["source/provenance"] = (
                rec["source/provenance"] or "final_artifact_validation.errors"
            )
            rec["what Site Forge did"] = "BLOCKED"
            rec["effect"] = "STRUCTURAL"
            add("BLOCKERS", rec)
        for rev in _as_list(fav.get("reviews")):
            rec = _normalize_item(rev, default_object="final_artifact")
            rec["subsystem"] = rec["subsystem"] or "final_artifact"
            rec["severity/classification"] = rec["severity/classification"] or "REVIEW"
            rec["source/provenance"] = (
                rec["source/provenance"] or "final_artifact_validation.reviews"
            )
            rec["effect"] = "COMMISSIONING"
            add("REVIEW REQUIRED", rec)

    # --- WITHHELD FROM L5X ---
    for merge in _as_list(rep.get("merges_withheld_review")):
        rec = _normalize_item(merge)
        if not rec["object/device"]:
            rec["object/device"] = str(merge)
        rec["subsystem"] = rec["subsystem"] or "merge"
        rec["severity/classification"] = (
            rec["severity/classification"] or "REVIEW_WITHHELD"
        )
        rec["reason"] = rec["reason"] or "Merge withheld from L5X pending review."
        rec["source/provenance"] = (
            rec["source/provenance"] or "merges_withheld_review"
        )
        rec["what Site Forge did"] = "WITHHELD"
        rec["effect"] = "COMMISSIONING"
        if not rec["engineer action"]:
            rec["engineer action"] = "Prove merge emission evidence or accept withhold."
        add("WITHHELD FROM L5X", rec)

    for prog in _as_list(rep.get("default_area_programs_withheld")):
        rec = _normalize_item(prog)
        if not rec["object/device"]:
            rec["object/device"] = str(prog)
        rec["subsystem"] = rec["subsystem"] or "area_program"
        rec["severity/classification"] = (
            rec["severity/classification"] or "WITHHELD"
        )
        rec["reason"] = rec["reason"] or "Default area program withheld from L5X."
        rec["source/provenance"] = (
            rec["source/provenance"] or "default_area_programs_withheld"
        )
        rec["what Site Forge did"] = "WITHHELD"
        rec["effect"] = "COMMISSIONING"
        add("WITHHELD FROM L5X", rec)

    # --- function_disclosure ---
    fd = rep.get("function_disclosure")
    if isinstance(fd, dict):
        for name, meta in fd.items():
            if name == "policy" or not isinstance(meta, dict):
                continue
            st = str(meta.get("status") or "").upper()
            note = str(meta.get("note") or meta.get("detail") or meta.get("reason") or "")
            if st in {"UNSUPPORTED_BETA_FUNCTION", "UNSUPPORTED"}:
                add(
                    "UNSUPPORTED BETA FUNCTION",
                    _issue(
                        object_device=str(name),
                        subsystem="function_disclosure",
                        severity=st,
                        reason=note or f"{name} marked {st}",
                        source="function_disclosure",
                        site_forge_did="WITHHELD",
                        effect="COMMISSIONING",
                        engineer_action="Approve generic pack or leave unsupported.",
                    ),
                )
            elif st in {"REVIEW_WITHHELD", "WITHHELD"}:
                add(
                    "WITHHELD FROM L5X",
                    _issue(
                        object_device=str(name),
                        subsystem="function_disclosure",
                        severity=st,
                        reason=note or f"{name} withheld from commissionable emit",
                        source="function_disclosure",
                        site_forge_did="WITHHELD",
                        effect="COMMISSIONING",
                        engineer_action="Review withheld function before commissioning.",
                    ),
                )
            elif st in {"REVIEW_REQUIRED", "REVIEW"}:
                add(
                    "REVIEW REQUIRED",
                    _issue(
                        object_device=str(name),
                        subsystem="function_disclosure",
                        severity=st,
                        reason=note or f"{name} requires review",
                        source="function_disclosure",
                        site_forge_did="REVIEW_ONLY",
                        effect="COMMISSIONING",
                        engineer_action="Review function disclosure before go-live.",
                    ),
                )

    # --- SAFETY / es_program ---
    es = rep.get("es_program")
    if isinstance(es, dict):
        st = str(es.get("status") or "").upper()
        omitted = _as_list(es.get("omitted_zones")) or _as_list(es.get("omitted"))
        review_zones = _as_list(es.get("review_zones"))
        review_devs = _as_list(es.get("review_required_devices"))
        if st in {"REVIEW_REQUIRED", "REVIEW", "OMITTED", "PARTIAL"} or omitted or review_zones:
            add(
                "SAFETY",
                _issue(
                    object_device="ES",
                    subsystem="safety",
                    severity=st or "REVIEW",
                    reason=str(es.get("detail") or f"es_program.status={st or 'REVIEW'}"),
                    source="es_program",
                    site_forge_did="REVIEW_ONLY" if st != "OMITTED" else "WITHHELD",
                    effect="COMMISSIONING",
                    engineer_action="Assign Safety zone membership and re-emit ES.",
                ),
            )
        for z in omitted:
            rec = _normalize_item(z, default_object=str(z))
            rec["subsystem"] = "safety"
            rec["severity/classification"] = rec["severity/classification"] or "OMITTED"
            rec["reason"] = rec["reason"] or "Safety zone omitted from ES emit."
            rec["source/provenance"] = rec["source/provenance"] or "es_program.omitted_zones"
            rec["what Site Forge did"] = "WITHHELD"
            rec["effect"] = "COMMISSIONING"
            if not rec["engineer action"]:
                rec["engineer action"] = "Complete zone membership; re-run Safety emit."
            add("SAFETY", rec)
        for z in review_zones:
            rec = _normalize_item(z, default_object=str(z))
            rec["subsystem"] = "safety"
            rec["severity/classification"] = rec["severity/classification"] or "REVIEW"
            rec["reason"] = rec["reason"] or "Safety zone requires review."
            rec["source/provenance"] = rec["source/provenance"] or "es_program.review_zones"
            rec["what Site Forge did"] = "REVIEW_ONLY"
            rec["effect"] = "COMMISSIONING"
            add("SAFETY", rec)
        for d in review_devs:
            rec = _normalize_item(d)
            if not rec["object/device"]:
                rec["object/device"] = str(d)
            rec["subsystem"] = "safety"
            rec["severity/classification"] = (
                rec["severity/classification"] or "REVIEW_REQUIRED"
            )
            rec["reason"] = rec["reason"] or "Safety device requires review."
            rec["source/provenance"] = (
                rec["source/provenance"] or "es_program.review_required_devices"
            )
            rec["what Site Forge did"] = "REVIEW_ONLY"
            rec["effect"] = "COMMISSIONING"
            add("SAFETY", rec)
        if es.get("report_matches_artifact") is False:
            add(
                "REPORT / ARTIFACT ISSUES",
                _issue(
                    object_device="ES",
                    subsystem="safety",
                    severity="MISMATCH",
                    reason="es_program.report_matches_artifact=false",
                    source="es_program.report_matches_artifact",
                    site_forge_did="BLOCKED",
                    effect="STRUCTURAL",
                    engineer_action="Reconcile ES report with emitted L5X routines.",
                ),
            )

    # Top-level report_matches_artifact (if present)
    if rep.get("report_matches_artifact") is False:
        add(
            "REPORT / ARTIFACT ISSUES",
            _issue(
                object_device=site_name,
                subsystem="report",
                severity="MISMATCH",
                reason="report_matches_artifact=false",
                source="report.report_matches_artifact",
                site_forge_did="BLOCKED",
                effect="STRUCTURAL",
                engineer_action="Reconcile report claims with generated artifact.",
            ),
        )

    # --- writer_coverage ---
    wc = rep.get("writer_coverage")
    if isinstance(wc, dict):
        by = wc.get("by_class") if isinstance(wc.get("by_class"), dict) else {}
        for tag in _as_list(by.get("DEFECT")):
            rec = _normalize_item(tag)
            if not rec["object/device"]:
                rec["object/device"] = str(tag)
            rec["subsystem"] = rec["subsystem"] or "writer_coverage"
            rec["severity/classification"] = "DEFECT"
            rec["reason"] = rec["reason"] or "Mapped output has no valid writer (DEFECT)."
            rec["source/provenance"] = (
                rec["source/provenance"] or "writer_coverage.by_class.DEFECT"
            )
            rec["what Site Forge did"] = "BLOCKED"
            rec["effect"] = "STRUCTURAL"
            if not rec["engineer action"]:
                rec["engineer action"] = "Add writer or classify as intentional undriven."
            add("WRITER / OUTPUT ISSUES", rec)
        for tag in _as_list(by.get("INTENTIONALLY_UNDRIVEN_REVIEW")):
            rec = _normalize_item(tag)
            if not rec["object/device"]:
                rec["object/device"] = str(tag)
            rec["subsystem"] = rec["subsystem"] or "writer_coverage"
            rec["severity/classification"] = "INTENTIONALLY_UNDRIVEN_REVIEW"
            rec["reason"] = (
                rec["reason"]
                or "Output intentionally undriven — review before commissioning."
            )
            rec["source/provenance"] = (
                rec["source/provenance"]
                or "writer_coverage.by_class.INTENTIONALLY_UNDRIVEN_REVIEW"
            )
            rec["what Site Forge did"] = "REVIEW_ONLY"
            rec["effect"] = "COMMISSIONING"
            if not rec["engineer action"]:
                rec["engineer action"] = "Confirm intentional undriven or add writer."
            add("REVIEW REQUIRED", rec)
            add("WRITER / OUTPUT ISSUES", rec)
        for tag in _as_list(by.get("UNSUPPORTED")):
            rec = _normalize_item(tag)
            if not rec["object/device"]:
                rec["object/device"] = str(tag)
            rec["subsystem"] = rec["subsystem"] or "writer_coverage"
            rec["severity/classification"] = "UNSUPPORTED"
            rec["reason"] = rec["reason"] or "Output writer unsupported by Site Forge."
            rec["source/provenance"] = (
                rec["source/provenance"] or "writer_coverage.by_class.UNSUPPORTED"
            )
            rec["what Site Forge did"] = "WITHHELD"
            rec["effect"] = "COMMISSIONING"
            add("UNSUPPORTED BETA FUNCTION", rec)
            add("WRITER / OUTPUT ISSUES", rec)

    # --- UNRESOLVED I/O ---
    unresolved_raw = _collect_unresolved_io_raw(rep)
    for item in unresolved_raw:
        rec = _normalize_item(item)
        if not rec["object/device"] and not isinstance(item, dict):
            rec["object/device"] = str(item)
        rec["subsystem"] = rec["subsystem"] or "io"
        if not rec["severity/classification"]:
            rec["severity/classification"] = "UNRESOLVED"
        if not rec["reason"]:
            rec["reason"] = "I/O point unresolved or UNKNOWN."
        if not rec["source/provenance"]:
            rec["source/provenance"] = "report unresolved_io / UNKNOWN"
        rec["what Site Forge did"] = rec["what Site Forge did"] or "WITHHELD"
        rec["effect"] = rec["effect"] or "COMMISSIONING"
        if not rec["engineer action"]:
            rec["engineer action"] = "Resolve physical endpoint ownership and remapping."
        add("UNRESOLVED I/O", rec)

    # Count-only unresolved disclosure when samples absent.
    if not unresolved_raw:
        stage0 = rep.get("stage0") if isinstance(rep.get("stage0"), dict) else {}
        unresolved_count = int(stage0.get("CLAIMS_UNRESOLVED") or 0)
        unmapped = int(rep.get("io_map_unmapped") or 0)
        if unresolved_count > 0:
            add(
                "UNRESOLVED I/O",
                _issue(
                    object_device=site_name,
                    subsystem="io",
                    severity="UNRESOLVED",
                    reason=f"stage0.CLAIMS_UNRESOLVED={unresolved_count}",
                    source="stage0.CLAIMS_UNRESOLVED",
                    site_forge_did="WITHHELD",
                    effect="COMMISSIONING",
                    engineer_action="Inspect unresolved claims and bind endpoints.",
                ),
            )
        elif unmapped > 0:
            add(
                "UNRESOLVED I/O",
                _issue(
                    object_device=site_name,
                    subsystem="io",
                    severity="UNMAPPED",
                    reason=f"io_map_unmapped={unmapped}",
                    source="io_map_unmapped",
                    site_forge_did="WITHHELD",
                    effect="COMMISSIONING",
                    engineer_action="Map remaining I/O or document intentional spare.",
                ),
            )

    # --- DUPLICATE / COLLISION ---
    for audit in _as_list(rep.get("io_map_dup_physical_audits")):
        rec = _normalize_item(audit)
        rec["subsystem"] = rec["subsystem"] or "io"
        rec["severity/classification"] = (
            rec["severity/classification"] or "DUPLICATE"
        )
        rec["reason"] = rec["reason"] or "Duplicate physical I/O ownership audit."
        rec["source/provenance"] = (
            rec["source/provenance"] or "io_map_dup_physical_audits"
        )
        rec["what Site Forge did"] = "BLOCKED"
        rec["effect"] = "STRUCTURAL"
        add("DUPLICATE / COLLISION", rec)

    for shared in _as_list(rep.get("io_map_shared_outputs")):
        rec = _normalize_item(shared)
        rec["subsystem"] = rec["subsystem"] or "io"
        rec["severity/classification"] = (
            rec["severity/classification"] or "SHARED_OUTPUT"
        )
        rec["reason"] = rec["reason"] or "Shared output requires ownership review."
        rec["source/provenance"] = (
            rec["source/provenance"] or "io_map_shared_outputs"
        )
        rec["what Site Forge did"] = "REVIEW_ONLY"
        rec["effect"] = "COMMISSIONING"
        add("DUPLICATE / COLLISION", rec)

    tag_reg = rep.get("tag_registry")
    if isinstance(tag_reg, dict):
        for conflict in _as_list(tag_reg.get("conflicts")):
            rec = _normalize_item(conflict)
            rec["subsystem"] = rec["subsystem"] or "tags"
            rec["severity/classification"] = (
                rec["severity/classification"] or "COLLISION"
            )
            rec["reason"] = rec["reason"] or "Tag registry conflict."
            rec["source/provenance"] = (
                rec["source/provenance"] or "tag_registry.conflicts"
            )
            rec["what Site Forge did"] = "BLOCKED"
            rec["effect"] = "STRUCTURAL"
            add("DUPLICATE / COLLISION", rec)

    # --- runnability / commissioning disclosures ---
    run = rep.get("runnability") if isinstance(rep.get("runnability"), dict) else {}
    run_ready = str(
        commissioning_ready
        or (run.get("COMMISSIONING_READY") if run else "")
        or ("YES" if _truthy(rep.get("commissionable")) else "")
        or "NO"
    ).upper()
    if run_ready not in {"YES", "NO"}:
        run_ready = "YES" if _truthy(run_ready) else "NO"

    if run and run_ready == "NO":
        reasons: list[str] = []
        for gate_key in ("AREA_COMMAND_PATH", "SAFETY_GATE"):
            val = str(run.get(gate_key) or "").upper()
            if val and val != "READY":
                reasons.append(f"{gate_key}={val}")
        if run.get("area_run_writer_present") is False:
            reasons.append("area_run_writer_present=false")
        if run.get("start_path_present") is False:
            reasons.append("start_path_present=false")
        if run.get("stop_path_present") is False:
            reasons.append("stop_path_present=false")
        if not reasons:
            reasons.append("COMMISSIONING_READY=NO")
        add(
            "REVIEW REQUIRED",
            _issue(
                object_device=site_name,
                subsystem="runnability",
                severity="COMMISSIONING_READY_NO",
                reason="; ".join(reasons),
                source="runnability",
                site_forge_did="REVIEW_ONLY",
                effect="COMMISSIONING",
                engineer_action="Close runnability gates before commissioning.",
            ),
        )

    # ORI-100 unimplemented commissioning when Area_HMI + NONE_PROVEN
    ac = _area_command(rep)
    if (
        str(ac.get("command_source") or "").strip() == "Area_HMI"
        and str(ac.get("physical_control_station") or "").upper() == "NONE_PROVEN"
    ):
        for gap_name, gap_reason in _ORI100_COMMISSIONING_GAPS:
            issue = _issue(
                object_device=str(ac.get("area") or site_name),
                subsystem="commissioning",
                severity="ORI-100",
                reason=gap_reason,
                source="ORI-100 / area_command.physical_control_station",
                site_forge_did="REVIEW_ONLY",
                effect="COMMISSIONING",
                engineer_action=(
                    f"Prove physical control station or explicitly accept "
                    f"unimplemented '{gap_name}' commissioning gap."
                ),
                gap=gap_name,
            )
            add("REVIEW REQUIRED", issue)
            add("WARNINGS / HYGIENE", issue)

    # Hygiene: missing excel templates, slow_flt review, studio blockers
    for tmpl in _as_list(rep.get("missing_excel_templates_in_library")):
        add(
            "WARNINGS / HYGIENE",
            _issue(
                object_device=str(tmpl),
                subsystem="library",
                severity="WARNING",
                reason="Excel template missing from library; fallback used.",
                source="missing_excel_templates_in_library",
                site_forge_did="GENERATED",
                effect="NON_BLOCKING",
                engineer_action="Add template to library or accept fallback.",
            ),
        )

    if str(rep.get("slow_flt_status") or "").upper() in {
        "REVIEW_REQUIRED",
        "REVIEW",
        "UNSUPPORTED_BETA_FUNCTION",
    }:
        add(
            "WARNINGS / HYGIENE",
            _issue(
                object_device="Slow_Flt",
                subsystem="transport",
                severity=str(rep.get("slow_flt_status") or "REVIEW"),
                reason=str(rep.get("slow_flt_note") or "Slow_Flt requires review."),
                source="slow_flt_status",
                site_forge_did="REVIEW_ONLY",
                effect="NON_BLOCKING",
                engineer_action="Approve generic Slow_Flt pack or leave review.",
            ),
        )

    for blocker in _as_list(rep.get("studio_blockers")):
        rec = _normalize_item(blocker)
        rec["subsystem"] = rec["subsystem"] or "studio"
        rec["severity/classification"] = rec["severity/classification"] or "BLOCKER"
        rec["source/provenance"] = rec["source/provenance"] or "studio_blockers"
        rec["what Site Forge did"] = "BLOCKED"
        rec["effect"] = "STRUCTURAL"
        add("BLOCKERS", rec)

    # Build status classification
    structural_ok = not bool(sections["BLOCKERS"])
    # Prefer caller-supplied status when valid; else classify.
    status = str(build_status or "").strip().upper()
    if status not in {"SUCCESS", "PARTIAL", "BLOCKED"}:
        status = classify_build_status(
            rep,
            structural_ok=structural_ok and not _truthy(rep.get("build_failed")),
            promoted=bool(l5x_promoted),
        )
        # If we already collected blockers, force BLOCKED even when report
        # flags were incomplete.
        if sections["BLOCKERS"]:
            status = "BLOCKED"
        elif status == "SUCCESS" and (
            sections["WITHHELD FROM L5X"]
            or sections["UNSUPPORTED BETA FUNCTION"]
            or sections["REVIEW REQUIRED"]
            or sections["UNRESOLVED I/O"]
            or sections["SAFETY"]
            or sections["WRITER / OUTPUT ISSUES"]
            or sections["REPORT / ARTIFACT ISSUES"]
        ):
            # Material open issues discovered during derivation → PARTIAL
            # (REPORT mismatches that are structural already go to BLOCKERS).
            if sections["REPORT / ARTIFACT ISSUES"] and any(
                str(i.get("effect") or "") == "STRUCTURAL"
                for i in sections["REPORT / ARTIFACT ISSUES"]
            ):
                status = "BLOCKED"
            else:
                status = "PARTIAL"

    build_id_ts = str(build_id or "").strip()
    ts = str(timestamp or "").strip()
    if build_id_ts and ts and ts not in build_id_ts:
        build_id_display = f"{build_id_ts} / {ts}"
    else:
        build_id_display = build_id_ts or ts

    manifest: dict[str, Any] = {
        "title": "SITE FORGE BUILD ISSUES",
        "site": site_name,
        "Site/controller": site_name,
        "Git SHA": str(git_sha or ""),
        "TAR/source hash": str(tar_hash or ""),
        "Build ID/timestamp": build_id_display,
        "BUILD STATUS": status,
        "COMMISSIONING READY": run_ready,
        "L5X GENERATED": "YES" if l5x_generated else "NO",
        "L5X PROMOTED TO CURRENT": "YES" if l5x_promoted else "NO",
        "l5x_path": str(l5x_path or ""),
        "sections": sections,
    }
    # Flatten section lists at top level for convenient JSON consumers / tests.
    for name in SECTION_ORDER:
        manifest[name] = sections[name]
    return manifest


def render_build_issues_txt(manifest: dict) -> str:
    """Engineer-readable TXT."""
    m = manifest if isinstance(manifest, dict) else {}
    lines: list[str] = [
        "SITE FORGE BUILD ISSUES",
        "",
        f"Site/controller: {m.get('Site/controller') or m.get('site') or ''}",
        f"Git SHA: {m.get('Git SHA') or ''}",
        f"TAR/source hash: {m.get('TAR/source hash') or ''}",
        f"Build ID/timestamp: {m.get('Build ID/timestamp') or ''}",
        "",
        "BUILD STATUS:",
        str(m.get("BUILD STATUS") or ""),
        "",
        "COMMISSIONING READY:",
        str(m.get("COMMISSIONING READY") or ""),
        "",
        "L5X GENERATED:",
        str(m.get("L5X GENERATED") or ""),
        "",
        "L5X PROMOTED TO CURRENT:",
        str(m.get("L5X PROMOTED TO CURRENT") or ""),
        "",
    ]

    sections = m.get("sections") if isinstance(m.get("sections"), dict) else None
    for name in SECTION_ORDER:
        lines.append(name)
        items = None
        if sections is not None:
            items = sections.get(name)
        if items is None:
            items = m.get(name)
        items = _as_list(items)
        if not items:
            lines.append("None")
            lines.append("")
            continue
        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                lines.append(f"  {idx}. {item}")
                continue
            obj = item.get("object/device") or ""
            reason = item.get("reason") or ""
            sev = item.get("severity/classification") or ""
            did = item.get("what Site Forge did") or ""
            effect = item.get("effect") or ""
            action = item.get("engineer action") or ""
            source = item.get("source/provenance") or ""
            subsystem = item.get("subsystem") or ""
            header = f"  {idx}. {obj}".rstrip()
            if sev:
                header = f"{header} [{sev}]" if obj else f"  {idx}. [{sev}]"
            lines.append(header if obj or sev else f"  {idx}.")
            if subsystem:
                lines.append(f"     subsystem: {subsystem}")
            if reason:
                lines.append(f"     reason: {reason}")
            if source:
                lines.append(f"     source: {source}")
            if did:
                lines.append(f"     Site Forge: {did}")
            if effect:
                lines.append(f"     effect: {effect}")
            if action:
                lines.append(f"     engineer action: {action}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_build_issues(
    manifest: dict,
    out_dir: Path,
    *,
    site: str,
) -> tuple[Path, Path]:
    """Write {SITE}_BUILD_ISSUES.txt and .json; return (txt_path, json_path)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    site_token = str(site or manifest.get("site") or "SITE").strip() or "SITE"
    # Sanitize path token lightly (keep readable site names).
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in site_token)
    txt_path = out / f"{safe}_BUILD_ISSUES.txt"
    json_path = out / f"{safe}_BUILD_ISSUES.json"
    txt_path.write_text(render_build_issues_txt(manifest), encoding="utf-8")
    json_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return txt_path, json_path


__all__ = [
    "SECTION_ORDER",
    "build_issues_manifest",
    "classify_build_status",
    "render_build_issues_txt",
    "write_build_issues",
]

#!/usr/bin/env python3
"""Site Forge BUILD ISSUES manifest — engineer-readable closeout of a build attempt.

Every Autogen attempt that reaches report construction should emit:
  {SITE}_BUILD_ISSUES.txt
  {SITE}_BUILD_ISSUES.json

Derives issues generically from the autogen report (no site special-cases).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SECTION_ORDER: tuple[str, ...] = (
    "BLOCKERS",
    "PLC COMPILE / SYMBOL ISSUES",
    "REVIEW REQUIRED",
    "UNRESOLVED I/O",
    "DUPLICATE / COLLISION",
    "UNSUPPORTED BETA FUNCTION",
    "QUARANTINED LOGIC",
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
    program: str = "N/A",
    routine: str = "N/A",
    rung: str = "N/A",
    operand: str = "N/A",
    issue_id: str = "",
    **extra: Any,
) -> dict[str, Any]:
    """Normalize one issue record. Location fields default to N/A when unknown."""
    rec: dict[str, Any] = {
        "object/device": object_device or "",
        "subsystem": subsystem or "",
        "severity/classification": severity or "",
        "reason": reason or "",
        "source/provenance": source or "",
        "what Site Forge did": site_forge_did or "REVIEW_ONLY",
        "effect": effect or "NON_BLOCKING",
        "engineer action": engineer_action or "",
        "program": program if str(program or "").strip() else "N/A",
        "routine": routine if str(routine or "").strip() else "N/A",
        "rung": rung if str(rung or "").strip() else "N/A",
        "operand": operand if str(operand or "").strip() else "N/A",
    }
    if issue_id:
        rec["issue_id"] = str(issue_id)
    for k, v in extra.items():
        if v is not None and k not in rec:
            rec[k] = v
    return rec


def _is_bogus_object_identity(value: Any) -> bool:
    """True for non-identities that must never become object/device labels."""
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return False
    text = str(value).strip()
    if not text:
        return True
    return text.lower() in {"true", "false", "none", "null"}


def _normalize_item(item: Any, *, default_object: str = "") -> dict[str, Any]:
    """Coerce planted string/dict issue-like values into a record."""
    if isinstance(item, bool) or item is None:
        # ORI-103F: boolean omitted flags must never become "False [OMITTED]".
        return _issue(
            object_device=default_object or "",
            reason="",
        )
    if isinstance(item, dict):
        obj = (
            item.get("object/device")
            or item.get("object")
            or item.get("device")
            or item.get("name")
            or item.get("tag")
            or item.get("operand")
            or item.get("fortna_name")
            or item.get("claim_name")
            or item.get("identity")
            or default_object
            or ""
        )
        if _is_bogus_object_identity(obj):
            obj = default_object or ""
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
    if _is_bogus_object_identity(item):
        return _issue(object_device=default_object or "", reason="")
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

    # Quarantine structural blockers force BLOCKED; localizable quarantine alone does not.
    rq = rep.get("rung_quarantine")
    if isinstance(rq, dict) and (
        rq.get("blocked") is True or _as_list(rq.get("structural_blockers"))
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
        omitted_zones = es.get("omitted_zones")
        if omitted_zones is None:
            omitted_zones = es.get("omitted")
        if not isinstance(omitted_zones, bool) and any(
            not _is_bogus_object_identity(z) for z in _as_list(omitted_zones)
        ):
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

    rq = report.get("rung_quarantine")
    if isinstance(rq, dict):
        if int(rq.get("issue_count") or 0) > 0 or _as_list(rq.get("issues")):
            return True
        if int(rq.get("quarantined_rung_count") or 0) > 0:
            return True
        if int(rq.get("fail_closed_count") or 0) > 0:
            return True

    return False


def _read_unmapped_physical_names(report: dict) -> list[str]:
    """Named unmapped physical I/O from planted lists or physical_io_map.csv."""
    names: list[str] = []
    for key in (
        "unresolved_io_names",
        "physical_io_unmapped_names",
        "unmapped_io_names",
    ):
        for item in _as_list(report.get(key)):
            if isinstance(item, dict):
                n = (
                    item.get("fortna_name")
                    or item.get("name")
                    or item.get("device")
                    or item.get("object/device")
                    or item.get("claim_name")
                    or ""
                )
            else:
                n = item
            ns = str(n or "").strip()
            if ns and not _is_bogus_object_identity(ns):
                names.append(ns)

    csv_path = str(report.get("physical_io_map_csv") or "").strip()
    if csv_path:
        try:
            import csv

            with Path(csv_path).open("r", encoding="utf-8", errors="replace", newline="") as fh:
                for row in csv.DictReader(fh):
                    mapped = str(row.get("mapped") or "").strip().upper()
                    if mapped in {"Y", "YES", "TRUE", "1"}:
                        continue
                    n = str(row.get("fortna_name") or row.get("name") or "").strip()
                    if n and not _is_bogus_object_identity(n):
                        names.append(n)
        except Exception:
            pass
    # Stable unique
    out: list[str] = []
    seen: set[str] = set()
    for n in names:
        key = n.upper()
        if key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out


def _collect_unresolved_io_raw(report: dict) -> list[Any]:
    """Gather unresolved / UNKNOWN I/O entries from common report shapes."""
    found: list[Any] = []

    for key in (
        "unresolved_io",
        "io_unresolved",
        "unresolved_io_points",
        "io_unknown",
        "unknown_io",
        "unresolved_points",
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
            "CLAIMS_UNRESOLVED_NAMES",
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
                    "disposition",
                )
            ).upper()
            if any(
                tok in markers
                for tok in (
                    "UNRESOLVED",
                    "UNKNOWN",
                    "UNMAPPED",
                    "NOT_MAPPED",
                    "PHYSICAL_RESOLUTION_FAILURE",
                )
            ):
                found.append(row)

    # Named unmapped physical endpoints (EZSSV15/18 capacity fail-safe, etc.).
    for name in _read_unmapped_physical_names(report):
        found.append(
            {
                "object/device": name,
                "status": "UNRESOLVED",
                "reason": "Physical endpoint unresolved / unmapped on this controller.",
                "source": "physical_io_map / unresolved_io_names",
            }
        )

    # Deduplicate while preserving order (prefer named dicts).
    out: list[Any] = []
    seen: set[str] = set()
    for item in found:
        if isinstance(item, bool) or item is None:
            continue
        if isinstance(item, dict):
            name = str(
                item.get("object/device")
                or item.get("object")
                or item.get("device")
                or item.get("name")
                or item.get("fortna_name")
                or item.get("claim_name")
                or item.get("identity")
                or ""
            ).strip()
            if _is_bogus_object_identity(name) and not any(
                item.get(k) for k in ("reason", "detail", "message", "note")
            ):
                continue
            sig = name.upper() if name else json.dumps(item, sort_keys=True, default=str)
        else:
            if _is_bogus_object_identity(item):
                continue
            sig = str(item).strip().upper()
        if not sig or sig in seen:
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


_SAFETY_DEVICE_RE = re.compile(
    r"^(?:T_)?(?:ESPB|ESLS|ESR|MCR|ES)\d",
    re.I,
)
_ESR_RE = re.compile(r"(?:^|_)(?:\d*)?ESR\d", re.I)
_MCR_RE = re.compile(r"(?:^|_)(?:\d*)?MCR\d", re.I)


def _operational_zone_member_names(report: dict) -> set[str]:
    """Names already assigned to an operational Safety zone."""
    out: set[str] = set()
    es = report.get("es_program") if isinstance(report.get("es_program"), dict) else {}
    for z in _as_list(es.get("zones")) + _as_list(es.get("emitted_zones")):
        if isinstance(z, dict):
            for m in _as_list(z.get("members")):
                ms = str(m or "").strip()
                if ms:
                    out.add(ms.upper())
            name = str(z.get("name") or "").strip()
            if name:
                out.add(name.upper())
        else:
            ms = str(z or "").strip()
            if ms:
                out.add(ms.upper())
    for m in _as_list(es.get("members_emitted")):
        ms = str(m or "").strip()
        if ms:
            out.add(ms.upper())
    return out


def _emit_report_artifact_truth(
    report: dict,
    add,
    *,
    site_name: str,
    sections: dict[str, list[dict[str, Any]]],
) -> None:
    """ORI-103G: REPORT / ARTIFACT ISSUES from actual checks (None only if clean)."""
    if sections.get("REPORT / ARTIFACT ISSUES"):
        return
    mismatches: list[str] = []
    es = report.get("es_program") if isinstance(report.get("es_program"), dict) else {}
    if es.get("report_matches_artifact") is False:
        mismatches.append("es_program.report_matches_artifact=false")
    if report.get("report_matches_artifact") is False:
        mismatches.append("report_matches_artifact=false")
    for m in _as_list(es.get("report_artifact_mismatches")):
        mismatches.append(str(m))

    sc = report.get("symbol_closure") if isinstance(report.get("symbol_closure"), dict) else {}
    if sc:
        ok = sc.get("ok")
        fail_n = int(sc.get("failure_count") or 0)
        fails = _as_list(sc.get("failures"))
        counts = sc.get("counts") if isinstance(sc.get("counts"), dict) else {}
        count_fail = int(counts.get("FAIL") or 0)
        review_ext = int(
            counts.get("REVIEW_EXTERNAL")
            or counts.get("LIBRARY_REFERENCE")
            or counts.get("NON_BLOCKING_UNRESOLVED")
            or 0
        )
        if ok is False or fail_n > 0 or fails:
            mismatches.append(
                f"symbol_closure hard failures failure_count={fail_n} ok={ok}"
            )
        elif ok is True and count_fail > 0 and review_ext == 0:
            # Stale presentation: counts.FAIL with ok=true and empty failures.
            # Surface as hygiene/review labeling — not a structural blocker.
            add(
                "WARNINGS / HYGIENE",
                _issue(
                    object_device=site_name,
                    subsystem="symbol_closure",
                    severity="PRESENTATION",
                    reason=(
                        f"symbol_closure ok=true with counts.FAIL={count_fail} and "
                        f"failure_count=0 — treating counts.FAIL as non-blocking "
                        f"library/external references, not hard failures."
                    ),
                    source="symbol_closure.counts",
                    site_forge_did="REVIEW_ONLY",
                    effect="NON_BLOCKING",
                    engineer_action=(
                        "Confirm closure label uses REVIEW_EXTERNAL for non-escalating refs."
                    ),
                ),
            )

    if mismatches:
        add(
            "REPORT / ARTIFACT ISSUES",
            _issue(
                object_device=site_name,
                subsystem="report",
                severity="MISMATCH",
                reason="; ".join(mismatches),
                source="report/artifact truth checks",
                site_forge_did="BLOCKED",
                effect="STRUCTURAL",
                engineer_action="Reconcile report claims with generated artifact.",
            ),
        )


def _emit_p105a_review(report: dict, add) -> None:
    """Ensure P105A appears as REVIEW_WITHHELD / commissioning review when present."""
    markers: list[str] = []
    for merge in _as_list(report.get("merges_withheld_review")):
        ms = str(merge if not isinstance(merge, dict) else (
            merge.get("name") or merge.get("object/device") or merge.get("lane") or ""
        ))
        if "P105A" in ms.upper():
            markers.append(ms)
    lea = report.get("local_equipment_accounting")
    if isinstance(lea, dict):
        lanes = lea.get("review_withheld_lanes")
        if isinstance(lanes, dict):
            for k, v in lanes.items():
                if "P105A" in str(k).upper() or "P105A" in str(v).upper():
                    markers.append(str(v or k))
        for name in _as_list(lea.get("ssv_intentional_review")):
            if str(name).upper() in {"SSV105A", "P105A"}:
                markers.append(str(name))
    # Also SSV105A intentional review implies P105A lane review.
    wc = report.get("writer_coverage") if isinstance(report.get("writer_coverage"), dict) else {}
    by = wc.get("by_class") if isinstance(wc.get("by_class"), dict) else {}
    for name in _as_list(by.get("INTENTIONALLY_UNDRIVEN_REVIEW")):
        if str(name).upper() in {"SSV105A", "P105A"}:
            markers.append(str(name))
    if not markers and "P105A" not in json.dumps(report.get("merges_withheld_review") or []):
        # No evidence of P105A in this build — stay silent.
        return
    add(
        "WITHHELD FROM L5X",
        _issue(
            object_device="P105A",
            subsystem="merge",
            severity="REVIEW_WITHHELD",
            reason=(
                "P105A lane remains REVIEW_WITHHELD / commissioning review "
                f"(evidence: {', '.join(dict.fromkeys(markers)) or 'merge withhold'})."
            ),
            source="merges_withheld_review / local_equipment_accounting",
            site_forge_did="WITHHELD",
            effect="COMMISSIONING",
            engineer_action="Prove P105A merge/SSV emission evidence or accept withhold.",
        ),
    )
    add(
        "REVIEW REQUIRED",
        _issue(
            object_device="P105A",
            subsystem="commissioning",
            severity="REVIEW_WITHHELD",
            reason="P105A requires commissioning review before merge/SSV release.",
            source="ORI-103 / P105A REVIEW_WITHHELD",
            site_forge_did="REVIEW_ONLY",
            effect="COMMISSIONING",
            engineer_action="Review P105A ownership and SSV105A writer before go-live.",
        ),
    )


def _emit_ori090_ip_mismatch(report: dict, add, *, site_name: str) -> None:
    """ORI-090: disclose interface IP vs adapter IP hygiene mismatches."""
    planted = report.get("ori_090") or report.get("ori090") or report.get("ip_mismatch")
    if isinstance(planted, dict) and planted:
        add(
            "WARNINGS / HYGIENE",
            _issue(
                object_device=str(
                    planted.get("object/device")
                    or planted.get("device")
                    or site_name
                    or "EIP"
                ),
                subsystem="eip",
                severity=str(planted.get("severity") or "ORI-090"),
                reason=str(
                    planted.get("reason")
                    or planted.get("detail")
                    or "ORI-090 IP mismatch / metadata hygiene."
                ),
                source=str(planted.get("source") or "ori_090"),
                site_forge_did="REVIEW_ONLY",
                effect="NON_BLOCKING",
                engineer_action="Reconcile controller/interface IP metadata with adapter IPs.",
            ),
        )
        return
    if planted and not isinstance(planted, dict):
        add(
            "WARNINGS / HYGIENE",
            _issue(
                object_device=site_name or "EIP",
                subsystem="eip",
                severity="ORI-090",
                reason=str(planted),
                source="ori_090",
                site_forge_did="REVIEW_ONLY",
                effect="NON_BLOCKING",
                engineer_action="Reconcile controller/interface IP metadata with adapter IPs.",
            ),
        )
        return

    iface = str(report.get("eip_interface_ip") or "").strip()
    adapter_ips: list[str] = []
    for key in ("eip_adapter_ips", "adapter_ips"):
        for ip in _as_list(report.get(key)):
            s = str(ip or "").strip()
            if s:
                adapter_ips.append(s)
    # Fall back to rio_inventory.json next to physical map when present.
    if not adapter_ips:
        csv_path = str(report.get("physical_io_map_csv") or "").strip()
        if csv_path:
            rio_path = Path(csv_path).with_name("rio_inventory.json")
            try:
                if rio_path.is_file():
                    rio = json.loads(rio_path.read_text(encoding="utf-8"))
                    if not iface:
                        iface = str(rio.get("interface_ip") or "").strip()
                    for ad in _as_list(rio.get("adapters")):
                        if isinstance(ad, dict):
                            ip = str(ad.get("ip") or ad.get("ip_address") or "").strip()
                            if ip:
                                adapter_ips.append(ip)
            except Exception:
                pass
    adapter_ips = list(dict.fromkeys(adapter_ips))
    if iface and adapter_ips and iface not in adapter_ips:
        add(
            "WARNINGS / HYGIENE",
            _issue(
                object_device=site_name or "EIP",
                subsystem="eip",
                severity="ORI-090",
                reason=(
                    f"ORI-090 IP mismatch: eip_interface_ip={iface} does not match "
                    f"adapter IPs [{', '.join(adapter_ips)}]."
                ),
                source="eip_interface_ip vs adapter inventory",
                site_forge_did="REVIEW_ONLY",
                effect="NON_BLOCKING",
                engineer_action="Reconcile interface/controller IP metadata with adapter IPs.",
            ),
        )


def _emit_safety_review_inventory(report: dict, add) -> None:
    """List remaining REVIEW Safety devices by identity + ESR/MCR status."""
    es = report.get("es_program") if isinstance(report.get("es_program"), dict) else {}
    ep = report.get("equipment_plan") if isinstance(report.get("equipment_plan"), dict) else {}
    has_safety_context = bool(
        es
        or ep.get("equipment_fidelity")
        or report.get("safety_review_devices")
        or report.get("safety_unassigned_devices")
        or report.get("review_safety_devices")
        or report.get("safety_zone_candidate")
    )
    if not has_safety_context:
        return

    assigned = _operational_zone_member_names(report)
    seen_devs: set[str] = set()
    esr_names: list[str] = []
    mcr_names: list[str] = []

    def _consider(name: str, *, cls: str = "", reason: str = "", source: str = "") -> None:
        n = str(name or "").strip()
        if not n or _is_bogus_object_identity(n):
            return
        nu = n.upper()
        if nu in seen_devs:
            return
        if nu.startswith("SZONE_"):
            return
        if nu in {"DEFAULT_SAFETY", "UNASSIGNED_SAFETY"}:
            return
        if _ESR_RE.search(n):
            esr_names.append(n)
            seen_devs.add(nu)
            return
        if _MCR_RE.search(n) and "AUX" not in nu:
            mcr_names.append(n)
            seen_devs.add(nu)
            return
        if not _SAFETY_DEVICE_RE.match(n):
            return
        if nu in assigned:
            return
        seen_devs.add(nu)
        add(
            "SAFETY",
            _issue(
                object_device=n,
                subsystem="safety",
                severity="REVIEW",
                reason=reason
                or (
                    f"Local Safety device remains REVIEW/unassigned"
                    + (f" ({cls})" if cls else "")
                    + "."
                ),
                source=source or "equipment_fidelity / safety inventory",
                site_forge_did="REVIEW_ONLY",
                effect="COMMISSIONING",
                engineer_action="Assign to an operational Safety zone or accept inventory-only.",
            ),
        )

    # Prefer planted safety review lists when present.
    for key in (
        "safety_review_devices",
        "safety_unassigned_devices",
        "review_safety_devices",
    ):
        for item in _as_list(report.get(key)):
            if isinstance(item, dict):
                _consider(
                    str(
                        item.get("object/device")
                        or item.get("device")
                        or item.get("name")
                        or item.get("identity")
                        or ""
                    ),
                    cls=str(item.get("fidelity_class") or item.get("class") or ""),
                    reason=str(item.get("reason") or item.get("detail") or ""),
                    source=key,
                )
            else:
                _consider(str(item), source=key)

    ef = ep.get("equipment_fidelity") if isinstance(ep.get("equipment_fidelity"), dict) else {}
    by = ef.get("by_class") if isinstance(ef.get("by_class"), dict) else {}
    for cls_name in ("RAW_EVIDENCE_ROW", "LOCAL_ACTIVE_EQUIPMENT", "REVIEW", "UNKNOWN_OWNER"):
        for name in _as_list(by.get(cls_name)):
            _consider(str(name), cls=cls_name, source=f"equipment_fidelity.by_class.{cls_name}")
    for row in _as_list(ef.get("rows")):
        if not isinstance(row, dict):
            continue
        ident = str(row.get("identity") or row.get("name") or "")
        cls = str(row.get("fidelity_class") or row.get("class") or "")
        if cls.upper() == "FOREIGN_EQUIPMENT":
            # Still capture ESR/MCR identities for status lines.
            if _ESR_RE.search(ident) or _MCR_RE.search(ident):
                _consider(ident, cls=cls, source="equipment_fidelity.rows")
            continue
        _consider(ident, cls=cls, source="equipment_fidelity.rows")

    # ESR / MCR status lines (even when none found — make status visible).
    if esr_names:
        for n in sorted(set(esr_names)):
            add(
                "SAFETY",
                _issue(
                    object_device=n,
                    subsystem="safety",
                    severity="REVIEW",
                    reason="ESR device present in inventory — membership/commissioning review.",
                    source="equipment_fidelity ESR inventory",
                    site_forge_did="REVIEW_ONLY",
                    effect="COMMISSIONING",
                    engineer_action="Confirm ESR zone membership and feedback wiring.",
                ),
            )
    else:
        add(
            "SAFETY",
            _issue(
                object_device="ESR",
                subsystem="safety",
                severity="REVIEW",
                reason="No local ESR device identity proven in current equipment inventory.",
                source="equipment_fidelity ESR inventory",
                site_forge_did="REVIEW_ONLY",
                effect="COMMISSIONING",
                engineer_action="Confirm whether ESR is absent, foreign, or unproven for this machine.",
            ),
        )
    if mcr_names:
        for n in sorted(set(mcr_names)):
            add(
                "SAFETY",
                _issue(
                    object_device=n,
                    subsystem="safety",
                    severity="REVIEW",
                    reason="MCR device present in inventory — energize/feedback commissioning review.",
                    source="equipment_fidelity MCR inventory",
                    site_forge_did="REVIEW_ONLY",
                    effect="COMMISSIONING",
                    engineer_action="Confirm MCR command writer and AUX feedback ownership.",
                ),
            )
    else:
        add(
            "SAFETY",
            _issue(
                object_device="MCR",
                subsystem="safety",
                severity="REVIEW",
                reason="No local MCR energize coil identity proven in current equipment inventory.",
                source="equipment_fidelity MCR inventory",
                site_forge_did="REVIEW_ONLY",
                effect="COMMISSIONING",
                engineer_action="Confirm whether MCR is absent, foreign, or unproven for this machine.",
            ),
        )


def build_issues_manifest(
    report: dict,
    *,
    site: str,
    git_sha: str = "",
    tar_hash: str = "",
    run_fingerprint: str = "",
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
        # ORI-103F: never emit boolean/None as an object/device identity.
        obj = issue.get("object/device")
        if _is_bogus_object_identity(obj):
            issue = dict(issue)
            issue["object/device"] = ""
            if not str(issue.get("reason") or "").strip():
                return
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

    # Safe-partial quarantine punch list — localizable / fail-closed issues.
    rq = rep.get("rung_quarantine")
    if isinstance(rq, dict):
        for qiss in _as_list(rq.get("issues")):
            if not isinstance(qiss, dict):
                continue
            action = str(
                qiss.get("SITE FORGE ACTION")
                or qiss.get("what Site Forge did")
                or qiss.get("site_forge_action")
                or "QUARANTINED"
            ).upper()
            severity = str(
                qiss.get("SEVERITY")
                or qiss.get("severity/classification")
                or qiss.get("severity")
                or "QUARANTINED"
            )
            effect = str(qiss.get("EFFECT") or qiss.get("effect") or "LOCAL")
            rec = _issue(
                object_device=str(
                    qiss.get("OBJECT / DEVICE")
                    or qiss.get("object/device")
                    or qiss.get("operand")
                    or qiss.get("issue_id")
                    or ""
                ),
                subsystem="quarantine",
                severity=severity,
                reason=str(qiss.get("REASON") or qiss.get("reason") or ""),
                source=str(
                    qiss.get("SOURCE / PROVENANCE")
                    or qiss.get("source/provenance")
                    or "rung_quarantine"
                ),
                site_forge_did=action,
                effect=effect,
                engineer_action=str(
                    qiss.get("ENGINEER ACTION")
                    or qiss.get("engineer action")
                    or qiss.get("engineer_action")
                    or ""
                ),
                issue_id=str(qiss.get("issue_id") or ""),
                program=str(qiss.get("PROGRAM") or qiss.get("program") or "N/A"),
                routine=str(qiss.get("ROUTINE") or qiss.get("routine") or "N/A"),
                rung=str(
                    qiss.get("RUNG NUMBER / RUNG INDEX")
                    or qiss.get("rung")
                    or "N/A"
                ),
                operand=str(
                    qiss.get("OPERAND / TAG / ENDPOINT")
                    or qiss.get("operand")
                    or "N/A"
                ),
            )
            if action == "FAIL_CLOSED" or severity.upper() in {
                "SAFETY_FAIL_CLOSED",
                "SAFETY",
            }:
                add("SAFETY", rec)
            elif action in {"WITHHELD", "REVIEW_ONLY"}:
                add("WITHHELD FROM L5X", rec)
            else:
                # Undeclared/localizable quarantine is the engineer punch-list home.
                add("QUARANTINED LOGIC", rec)
        for blocker in _as_list(rq.get("structural_blockers")):
            add(
                "BLOCKERS",
                _issue(
                    object_device=site_name,
                    subsystem="quarantine",
                    severity="BLOCKER",
                    reason=str(blocker),
                    source="rung_quarantine.structural_blockers",
                    site_forge_did="BLOCKED",
                    effect="STRUCTURAL",
                    engineer_action="Resolve unrecoverable structural defect and regenerate.",
                    program="N/A",
                    routine="N/A",
                    rung="N/A",
                    operand="N/A",
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
                    if not rec.get("program"):
                        rec["program"] = "N/A"
                    if not rec.get("routine"):
                        rec["routine"] = "N/A"
                    if not rec.get("rung"):
                        rec["rung"] = "N/A"
                    if not rec.get("operand"):
                        rec["operand"] = str(
                            (fail.get("operand") if isinstance(fail, dict) else "")
                            or "N/A"
                        )
                    if not rec["engineer action"]:
                        rec["engineer action"] = (
                            "Declare missing symbol owner or remove dangling operand."
                        )
                    add("BLOCKERS", rec)
                    # Mirror compile/symbol identity without double-counting blockers
                    # in the actionable badge — PLC COMPILE is the engineer section.
                    add("PLC COMPILE / SYMBOL ISSUES", dict(rec))
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
                        program="N/A",
                        routine="N/A",
                        rung="N/A",
                        operand="N/A",
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
                    program="N/A",
                    routine="N/A",
                    rung="N/A",
                    operand="N/A",
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
        # ORI-103F: es_program.omitted may be a bool flag — never treat True/False as a zone.
        omitted_raw = es.get("omitted_zones")
        if omitted_raw is None:
            omitted_raw = es.get("omitted")
        omitted: list[Any] = []
        if isinstance(omitted_raw, bool) or omitted_raw is None:
            omitted = []
        else:
            omitted = [
                z
                for z in _as_list(omitted_raw)
                if not _is_bogus_object_identity(z)
                and not (
                    isinstance(z, dict)
                    and _is_bogus_object_identity(
                        z.get("name") or z.get("object/device") or z.get("zone")
                    )
                )
            ]
        review_zones = [
            z
            for z in _as_list(es.get("review_zones"))
            if not _is_bogus_object_identity(z)
        ]
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
            rec = _normalize_item(z)
            if not rec["object/device"]:
                continue
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
            rec = _normalize_item(z)
            if not rec["object/device"]:
                continue
            # ORI-104: Default/Unassigned and durable szone_* ids are not operational
            # review-zone duplicates when an engineering zone already exists.
            zn = str(rec["object/device"])
            if zn.startswith("szone_") or zn.lower() in {
                "default_safety",
                "unassigned_safety",
                "default safety",
                "unassigned safety",
            }:
                continue
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
                continue
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

    # ORI-103C: Safety review inventory — named REVIEW devices + ESR/MCR status.
    _emit_safety_review_inventory(rep, add)

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
    # ORI-103E: writerless DEFECT that does not invalidate the L5X is COMMISSIONING
    # review (UNSUPPORTED/REVIEW), not STRUCTURAL — only escalate when the build
    # already failed hard gates / blockers elsewhere.
    artifact_structurally_valid = not (
        _truthy(rep.get("build_failed"))
        or (
            isinstance(rep.get("symbol_closure"), dict)
            and (
                rep["symbol_closure"].get("ok") is False
                or int(rep["symbol_closure"].get("failure_count") or 0) > 0
                or _as_list(rep["symbol_closure"].get("failures"))
            )
        )
        or (
            isinstance(rep.get("studio_preflight"), dict)
            and rep["studio_preflight"].get("ok") is False
        )
        or (
            isinstance(rep.get("final_artifact_validation"), dict)
            and rep["final_artifact_validation"].get("ok") is False
            and _as_list(rep["final_artifact_validation"].get("errors"))
        )
    )
    if isinstance(wc, dict):
        by = wc.get("by_class") if isinstance(wc.get("by_class"), dict) else {}
        for tag in _as_list(by.get("DEFECT")):
            rec = _normalize_item(tag)
            if not rec["object/device"]:
                rec["object/device"] = str(tag)
            if _is_bogus_object_identity(rec["object/device"]):
                continue
            rec["subsystem"] = rec["subsystem"] or "writer_coverage"
            rec["source/provenance"] = (
                rec["source/provenance"] or "writer_coverage.by_class.DEFECT"
            )
            if artifact_structurally_valid:
                # CL17 and similar: unsupported/unwritten but safely withheld.
                rec["severity/classification"] = "UNSUPPORTED / REVIEW"
                rec["reason"] = (
                    rec["reason"]
                    or "Mapped output has no supported writer — withheld as "
                    "UNSUPPORTED/REVIEW (non-structural while artifact remains valid)."
                )
                rec["what Site Forge did"] = "WITHHELD / REVIEW_ONLY"
                rec["effect"] = "COMMISSIONING"
                if not rec["engineer action"]:
                    rec["engineer action"] = (
                        "Add supported writer or accept unsupported undriven output."
                    )
                add("UNSUPPORTED BETA FUNCTION", rec)
                add("WRITER / OUTPUT ISSUES", rec)
                add("REVIEW REQUIRED", rec)
            else:
                rec["severity/classification"] = "DEFECT"
                rec["reason"] = rec["reason"] or "Mapped output has no valid writer (DEFECT)."
                rec["what Site Forge did"] = "BLOCKED"
                rec["effect"] = "STRUCTURAL"
                if not rec["engineer action"]:
                    rec["engineer action"] = "Add writer or classify as intentional undriven."
                add("WRITER / OUTPUT ISSUES", rec)
                add("BLOCKERS", rec)
        for tag in _as_list(by.get("INTENTIONALLY_UNDRIVEN_REVIEW")):
            rec = _normalize_item(tag)
            if not rec["object/device"]:
                rec["object/device"] = str(tag)
            if _is_bogus_object_identity(rec["object/device"]):
                continue
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
            if _is_bogus_object_identity(rec["object/device"]):
                continue
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

    # Count-only unresolved disclosure ONLY when names are unavailable.
    if not unresolved_raw and not sections["UNRESOLVED I/O"]:
        stage0 = rep.get("stage0") if isinstance(rep.get("stage0"), dict) else {}
        unresolved_count = int(stage0.get("CLAIMS_UNRESOLVED") or 0)
        unmapped = int(
            rep.get("io_map_unmapped") or rep.get("physical_io_unmapped") or 0
        )
        if unresolved_count > 0:
            add(
                "UNRESOLVED I/O",
                _issue(
                    object_device=site_name,
                    subsystem="io",
                    severity="UNRESOLVED",
                    reason=f"stage0.CLAIMS_UNRESOLVED={unresolved_count} (names unavailable)",
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
                    reason=f"io_map_unmapped={unmapped} (names unavailable)",
                    source="io_map_unmapped",
                    site_forge_did="WITHHELD",
                    effect="COMMISSIONING",
                    engineer_action="Map remaining I/O or document intentional spare.",
                ),
            )

    # ORI-103B: P105A must appear explicitly as REVIEW_WITHHELD / commissioning review.
    _emit_p105a_review(rep, add)

    # ORI-103D: ORI-090 IP mismatch hygiene.
    _emit_ori090_ip_mismatch(rep, add, site_name=site_name)

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

    # ORI-103G: populate REPORT / ARTIFACT from actual checks before status classify.
    _emit_report_artifact_truth(rep, add, site_name=site_name, sections=sections)

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
            or sections["QUARANTINED LOGIC"]
            or sections["PLC COMPILE / SYMBOL ISSUES"]
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
    # Even when caller supplied status, structural REPORT mismatches force BLOCKED.
    if sections["REPORT / ARTIFACT ISSUES"] and any(
        str(i.get("effect") or "") == "STRUCTURAL"
        for i in sections["REPORT / ARTIFACT ISSUES"]
    ):
        status = "BLOCKED"
    elif status == "SUCCESS" and (
        sections["WITHHELD FROM L5X"]
        or sections["UNSUPPORTED BETA FUNCTION"]
        or sections["REVIEW REQUIRED"]
        or sections["UNRESOLVED I/O"]
        or sections["SAFETY"]
        or sections["WRITER / OUTPUT ISSUES"]
        or sections["QUARANTINED LOGIC"]
        or sections["PLC COMPILE / SYMBOL ISSUES"]
    ):
        status = "PARTIAL"

    build_id_ts = str(build_id or "").strip()
    ts = str(timestamp or "").strip()
    if build_id_ts and ts and ts not in build_id_ts:
        build_id_display = f"{build_id_ts} / {ts}"
    else:
        build_id_display = build_id_ts or ts

    # ORI-103H: never substitute RUN fingerprint for TAR SHA256.
    tar_sha = str(
        tar_hash
        or rep.get("tar_sha256")
        or rep.get("source_tar_sha256")
        or rep.get("archive_sha256")
        or ""
    ).strip()
    run_fp = str(
        run_fingerprint
        or rep.get("run_fingerprint")
        or rep.get("source_run_fingerprint")
        or ""
    ).strip()
    # If caller historically passed fingerprint via tar_hash, keep it only as RUN fp.
    if tar_sha and run_fp and tar_sha == run_fp:
        # Identical values are ambiguous — prefer labeling as RUN fingerprint only
        # when it looks like a short fingerprint rather than a full SHA256.
        if len(tar_sha) < 64:
            run_fp = tar_sha
            tar_sha = ""
    elif tar_sha and not run_fp and len(tar_sha) < 64:
        # Short hash fed into tar_hash is almost certainly a RUN fingerprint.
        run_fp = tar_sha
        tar_sha = str(
            rep.get("tar_sha256")
            or rep.get("source_tar_sha256")
            or rep.get("archive_sha256")
            or ""
        ).strip()

    structural_label = "FAIL" if status == "BLOCKED" else "PASS"
    # Prefer explicit report structural signal when present.
    sc = rep.get("symbol_closure") if isinstance(rep.get("symbol_closure"), dict) else {}
    sp = rep.get("studio_preflight") if isinstance(rep.get("studio_preflight"), dict) else {}
    if status != "BLOCKED" and (
        (isinstance(sc, dict) and sc.get("ok") is False)
        or (isinstance(sp, dict) and sp.get("ok") is False)
    ):
        structural_label = "FAIL"

    # Unique actionable issues (prefer issue_id; else object+reason+section).
    _seen_ids: set[str] = set()
    _actionable = 0
    for _sec in SECTION_ORDER:
        for _it in sections[_sec]:
            if not isinstance(_it, dict):
                _actionable += 1
                continue
            _iid = str(_it.get("issue_id") or "").strip()
            if _iid:
                if _iid in _seen_ids:
                    continue
                _seen_ids.add(_iid)
            else:
                _key = "|".join(
                    [
                        str(_it.get("object/device") or ""),
                        str(_it.get("reason") or "")[:120],
                        str(_it.get("rung") or ""),
                        str(_it.get("operand") or ""),
                    ]
                )
                if _key in _seen_ids:
                    continue
                _seen_ids.add(_key)
            _actionable += 1

    manifest: dict[str, Any] = {
        "title": "SITE FORGE BUILD ISSUES",
        "site": site_name,
        "Site/controller": site_name,
        "Git SHA": str(git_sha or ""),
        "TAR SHA256": tar_sha,
        "RUN fingerprint": run_fp,
        # Back-compat alias — prefer TAR SHA256 when known; else leave blank
        # rather than silently substituting the RUN fingerprint.
        "TAR/source hash": tar_sha,
        "Build ID": str(build_id or ""),
        "Build ID/timestamp": build_id_display,
        "BUILD STATUS": status,
        "STRUCTURAL VALIDATION": structural_label,
        "COMMISSIONING READY": run_ready,
        "L5X GENERATED": "YES" if l5x_generated else "NO",
        "L5X PROMOTED TO CURRENT": "YES" if l5x_promoted else "NO",
        "l5x_path": str(l5x_path or ""),
        "actionable_issue_count": _actionable,
        "sections": sections,
    }
    # Flatten section lists at top level for convenient JSON consumers / tests.
    for name in SECTION_ORDER:
        manifest[name] = sections[name]
    return manifest


def _issue_location_fields(item: dict[str, Any]) -> dict[str, str]:
    """Normalize punch-list location fields; N/A when absent."""
    program = str(item.get("program") or item.get("PROGRAM") or "").strip() or "N/A"
    routine = str(item.get("routine") or item.get("ROUTINE") or "").strip() or "N/A"
    rung = str(
        item.get("rung")
        or item.get("RUNG NUMBER / RUNG INDEX")
        or item.get("rung_number")
        or ""
    ).strip() or "N/A"
    operand = str(
        item.get("operand")
        or item.get("OPERAND / TAG / ENDPOINT")
        or ""
    ).strip() or "N/A"
    return {
        "program": program,
        "routine": routine,
        "rung": rung,
        "operand": operand,
    }


def render_build_issues_txt(manifest: dict) -> str:
    """Engineer-readable TXT punch list."""
    m = manifest if isinstance(manifest, dict) else {}
    lines: list[str] = [
        "SITE FORGE BUILD ISSUES",
        "",
        f"Site/controller: {m.get('Site/controller') or m.get('site') or ''}",
        f"Git SHA: {m.get('Git SHA') or ''}",
        f"TAR SHA256: {m.get('TAR SHA256') or m.get('TAR/source hash') or ''}",
        f"RUN fingerprint: {m.get('RUN fingerprint') or ''}",
        f"Build ID: {m.get('Build ID') or ''}",
        f"Build ID/timestamp: {m.get('Build ID/timestamp') or ''}",
        "",
        "BUILD STATUS:",
        str(m.get("BUILD STATUS") or ""),
        "",
        "STRUCTURAL VALIDATION:",
        str(m.get("STRUCTURAL VALIDATION") or ("FAIL" if m.get("BUILD STATUS") == "BLOCKED" else "PASS")),
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
        f"L5X path: {m.get('l5x_path') or 'N/A'}",
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
            issue_id = str(item.get("issue_id") or "").strip()
            obj = item.get("object/device") or ""
            reason = item.get("reason") or ""
            sev = item.get("severity/classification") or ""
            did = item.get("what Site Forge did") or ""
            effect = item.get("effect") or ""
            action = item.get("engineer action") or ""
            source = item.get("source/provenance") or ""
            loc = _issue_location_fields(item)
            title = issue_id or obj or sev or f"ISSUE-{idx}"
            if issue_id and sev:
                banner = f"{issue_id} — {sev}"
            elif issue_id:
                banner = issue_id
            else:
                banner = f"{idx}. {title}"
                if sev and not issue_id:
                    banner = f"{idx}. {obj} [{sev}]" if obj else f"{idx}. [{sev}]"
            lines.append("=" * 60)
            lines.append(banner)
            lines.append("=" * 60)
            lines.append("")
            lines.append("Program:")
            lines.append(loc["program"])
            lines.append("")
            lines.append("Routine:")
            lines.append(loc["routine"])
            lines.append("")
            lines.append("Rung:")
            lines.append(loc["rung"])
            lines.append("")
            lines.append("Operand:")
            lines.append(loc["operand"])
            lines.append("")
            if obj:
                lines.append("Object / Device:")
                lines.append(str(obj))
                lines.append("")
            lines.append("Problem:")
            lines.append(str(reason) if reason else "N/A")
            lines.append("")
            if source:
                lines.append("Evidence:")
                lines.append(str(source))
                lines.append("")
            lines.append("Site Forge action:")
            lines.append(str(did) if did else "N/A")
            lines.append("")
            lines.append("Effect:")
            lines.append(str(effect) if effect else "N/A")
            lines.append("")
            lines.append("Engineer action:")
            lines.append(str(action) if action else "N/A")
            lines.append("")
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

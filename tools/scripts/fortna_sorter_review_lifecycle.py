#!/usr/bin/env python3
"""Sorter review lifecycle helpers (Gates I–N, X).

Pure model rules shared with dashboard contracts / permanent tests.
No site-specific production hardcodes.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

STATUS_CATS = (
    "PROVEN",
    "DERIVED",
    "REVIEW_REQUIRED",
    "ENGINEER_REQUIRED",
    "COMMISSIONING",
    "OPTIONAL",
)

RESOLUTION_TYPES = (
    "EDIT_REQUIRED",
    "ACCEPT_DERIVED",
    "ACCEPT_PROVEN",
    "COMMISSIONING_CONFIRM",
    "OPTIONAL",
    "UNRESOLVED",
)

LIFECYCLE = ("PENDING_REVIEW", "ACCEPTED", "EDITED", "RESOLVED")

ACTIONABLE = frozenset(
    {
        "REVIEW_REQUIRED",
        "ENGINEER_REQUIRED",
        "COMMISSIONING",
        "REVIEW",
        "UNKNOWN",
    }
)

# Canonical field → focus control id (dashboard SORTER_FIELD_FOCUS twin)
FIELD_FOCUS = {
    "induct_conveyor": "sorter-induct-conv",
    "induct_pe": "sorter-induct-pe",
    "induct_encoder": "sorter-induct-enc-tag",
    "sorter_type": "sorter-type",
    "transport_area": "sorter-area-name",
    "area_name": "sorter-area-name",
    "tracking_conveyors": "sorter-track-count",
    "tracking_conveyor_chain": "sorter-track-rows",
    "tracking_pe": "sorter-pe-count",
    "divert_output_io": "sorter-divert-rows",
    "divert_lane_topology": "sorter-divert-rows",
    "divert_pe": "sorter-divert-rows",
    "tracking_offset": "sorter-tracking-offset",
    "global_track_offset": "sorter-tracking-offset",
    "track_offset": "sorter-tracking-offset",
}

# Fields where DERIVED values intentionally offer Accept/Edit
DERIVED_ACCEPT_FIELDS = frozenset(
    {
        "induct_conveyor",
        "tracking_conveyor_chain",
        "tracking_conveyors",
        "tracking_order",
        "application_structure",
    }
)


def normalize_status(raw: Any) -> str:
    a = str(raw or "").upper().strip()
    if not a:
        return ""
    if a in ("PROVEN", "RUN_EXPLICIT"):
        return "PROVEN"
    if a in ("DERIVED", "RUN_DERIVED"):
        return "DERIVED"
    if a in ("OPTIONAL", "N/A", "NOT_APPLICABLE"):
        return "OPTIONAL"
    if a == "COMMISSIONING" or "COMMISSION" in a:
        return "COMMISSIONING"
    if a in ("ENGINEER_REQUIRED", "ENGINEER") or "ENGINEER_REQUIRED" in a:
        return "ENGINEER_REQUIRED"
    if "REVIEW" in a or a in ("UNKNOWN", "UNRESOLVED"):
        return "REVIEW_REQUIRED"
    return a


def review_group(field_key: str) -> str:
    k = str(field_key or "").lower()
    if "divert" in k or "lane" in k or "zone_lane" in k:
        return "divert"
    if (
        "track" in k
        or "encoder" in k
        or "induct_pe" in k
        or k == "tracking_pe"
        or "offset" in k
    ):
        return "tracking"
    return "sorter"


def field_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, dict) and not isinstance(v, list):
        if v.get("value") is not None:
            return str(v.get("value"))
        return ""
    return str(v)


def evidence_fingerprint(field: str, value: Any, source: str = "", status: str = "") -> str:
    return "|".join(
        [
            str(field or "").strip(),
            field_value(value).strip(),
            str(source or "").strip(),
            normalize_status(status) or str(status or "").strip(),
        ]
    )


def resolve_type_for(
    *,
    status: str,
    value: Any = "",
    policy_accept_proven: bool = False,
    commissioning: bool = False,
    why: str = "",
) -> str:
    st = normalize_status(status)
    if st == "OPTIONAL":
        return "OPTIONAL"
    if st == "DERIVED":
        return "ACCEPT_DERIVED"
    if st == "PROVEN":
        return "ACCEPT_PROVEN" if policy_accept_proven else "OPTIONAL"
    if st == "COMMISSIONING" or commissioning:
        return "COMMISSIONING_CONFIRM"
    if st in ("ENGINEER_REQUIRED", "REVIEW_REQUIRED") and not field_value(value):
        return "EDIT_REQUIRED" if st == "ENGINEER_REQUIRED" or not why else (
            "COMMISSIONING_CONFIRM" if "commission" in why.lower() or "offset" in why.lower()
            else "EDIT_REQUIRED"
        )
    if st in ACTIONABLE and not field_value(value):
        return "EDIT_REQUIRED"
    if st in ACTIONABLE:
        return "EDIT_REQUIRED"
    return "UNRESOLVED"


def tracking_offset_item(cfg: dict[str, Any]) -> dict[str, Any] | None:
    """Gate M — status from SorterModel; never invent an offset value."""
    fa = cfg.get("field_authority") or {}
    auth = normalize_status(fa.get("tracking_offset") or fa.get("global_track_offset") or "")
    raw_val = (
        cfg.get("tracking_offset")
        if cfg.get("tracking_offset") not in (None, "")
        else cfg.get("global_track_offset")
    )
    value = field_value(raw_val)
    provenance = ""
    source = "SorterModel"
    if isinstance(raw_val, dict):
        provenance = str(raw_val.get("provenance") or raw_val.get("source") or "")
        source = provenance or source

    # Live RUN/model value wins over bare field_authority REVIEW metadata
    live_auth = ""
    if isinstance(raw_val, dict):
        live_auth = normalize_status(raw_val.get("authority") or raw_val.get("provenance") or "")
        if live_auth in ("RUN_EXPLICIT",):
            live_auth = "PROVEN"
    if value and live_auth in ("PROVEN", "DERIVED"):
        # Proven/derived value present — not forced REVIEW by metadata alone
        if live_auth == "DERIVED":
            return {
                "field": "tracking_offset",
                "status": "DERIVED",
                "resolution_type": "ACCEPT_DERIVED",
                "group": "tracking",
                "focusId": FIELD_FOCUS["tracking_offset"],
                "current_value": value,
                "provenance": provenance or "DERIVED",
                "source": source,
                "why": "Derived track offset — Accept or Edit; do not invent.",
                "detail": "derived_offset",
                "lifecycle": "PENDING_REVIEW",
            }
        return None

    if auth in ("PROVEN", "DERIVED", "OPTIONAL") and not value:
        # Authority alone without value: still need engineer/commissioning entry
        pass
    if auth == "OPTIONAL":
        return None
    if not auth and not value:
        return {
            "field": "tracking_offset",
            "status": "REVIEW_REQUIRED",
            "resolution_type": "UNRESOLVED",
            "group": "tracking",
            "focusId": FIELD_FOCUS["tracking_offset"],
            "current_value": "",
            "provenance": "",
            "source": source,
            "why": (
                "Global induct→divert offset not present in RUN "
                "(Outpoints.Outpoint Location is per-outpoint only). "
                "Enter commissioning value or mark unresolved — do not invent."
            ),
            "detail": "missing_offset_evidence",
            "lifecycle": "PENDING_REVIEW",
        }

    if value and auth == "PROVEN":
        return None
    if value and auth == "DERIVED":
        return {
            "field": "tracking_offset",
            "status": "DERIVED",
            "resolution_type": "ACCEPT_DERIVED",
            "group": "tracking",
            "focusId": FIELD_FOCUS["tracking_offset"],
            "current_value": value,
            "provenance": provenance or "DERIVED",
            "source": source,
            "why": "Derived track offset — Accept or Edit.",
            "detail": "derived_offset",
            "lifecycle": "PENDING_REVIEW",
        }

    st = auth if auth in ACTIONABLE or auth in ("ENGINEER_REQUIRED", "COMMISSIONING", "REVIEW_REQUIRED") else "REVIEW_REQUIRED"
    if st == "COMMISSIONING" or (not value and "offset" in str(fa.get("tracking_offset", "")).lower()):
        rtype = "COMMISSIONING_CONFIRM"
        st = "COMMISSIONING" if st != "ENGINEER_REQUIRED" else st
    elif st == "ENGINEER_REQUIRED":
        rtype = "EDIT_REQUIRED"
    else:
        rtype = "COMMISSIONING_CONFIRM" if not value else "EDIT_REQUIRED"
        st = "COMMISSIONING" if not value else st

    return {
        "field": "tracking_offset",
        "status": st,
        "resolution_type": rtype,
        "group": "tracking",
        "focusId": FIELD_FOCUS["tracking_offset"],
        "current_value": value,
        "provenance": provenance,
        "source": source,
        "why": (
            "Global induct→divert offset not in RUN; Outpoint Location is per-outpoint only. "
            "Editable commissioning field — do not invent an offset."
        ),
        "detail": "field_authority",
        "lifecycle": "PENDING_REVIEW",
    }


def divert_pe_objects(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Rows that actually need divert PE review (skip PROVEN)."""
    out: list[dict[str, Any]] = []
    for i, d in enumerate(cfg.get("divert_rows") or []):
        auth = normalize_status((d.get("authority") or {}).get("divert_pe"))
        pe = field_value(d.get("divert_pe"))
        if auth == "PROVEN" and pe:
            continue
        if auth in ("OPTIONAL",):
            continue
        if auth in ("", "PROVEN", "DERIVED") and pe:
            # Has value with non-review auth — skip
            if auth in ("PROVEN", "DERIVED"):
                continue
        needs = (
            auth in ("REVIEW_REQUIRED", "ENGINEER_REQUIRED", "COMMISSIONING", "UNKNOWN", "")
            or not pe
        )
        if not needs:
            continue
        out.append(
            {
                "index": i,
                "name": field_value(d.get("name")),
                "lane": field_value(d.get("lane")),
                "host_zone": field_value(d.get("host_zone")),
                "divert_pe": pe,
                "authority": auth or "REVIEW_REQUIRED",
                "provenance": str(
                    (d.get("divert_pe") or {}).get("provenance")
                    if isinstance(d.get("divert_pe"), dict)
                    else (d.get("authority") or {}).get("divert_pe") or ""
                ),
            }
        )
    return out


def bulk_accept_derived_divert_pe(
    rows: list[dict[str, Any]],
    selected_indexes: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Accept derived PE values; never UNKNOWN→PROVEN. Stores ENGINEER_ACCEPTED."""
    selected = set(selected_indexes) if selected_indexes is not None else None
    updated = deepcopy(rows)
    for i, row in enumerate(updated):
        if selected is not None and i not in selected:
            continue
        auth = normalize_status((row.get("authority") or {}).get("divert_pe"))
        pe = field_value(row.get("divert_pe"))
        if auth == "UNKNOWN" or (not pe and auth != "DERIVED"):
            # Bulk must NEVER turn UNKNOWN→PROVEN
            continue
        if auth != "DERIVED":
            continue
        auth_map = dict(row.get("authority") or {})
        auth_map["divert_pe"] = "DERIVED"  # keep provenance class
        auth_map["divert_pe_acceptance"] = "ENGINEER_ACCEPTED"
        row["authority"] = auth_map
        row["divert_pe_acceptance"] = "ENGINEER_ACCEPTED"
    return updated


def bulk_mark_commissioning(
    rows: list[dict[str, Any]],
    selected_indexes: list[int],
    field: str = "divert_pe",
) -> list[dict[str, Any]]:
    updated = deepcopy(rows)
    for i in selected_indexes:
        if i < 0 or i >= len(updated):
            continue
        auth_map = dict(updated[i].get("authority") or {})
        auth_map[field] = "COMMISSIONING"
        updated[i]["authority"] = auth_map
    return updated


def bulk_apply_value(
    rows: list[dict[str, Any]],
    selected_indexes: list[int],
    value: str,
    field: str = "divert_pe",
) -> list[dict[str, Any]]:
    """Apply engineer value to selected rows; mark ENGINEER_ACCEPTED — do not falsify PROVEN."""
    updated = deepcopy(rows)
    val = str(value or "").strip()
    if not val:
        return updated
    for i in selected_indexes:
        if i < 0 or i >= len(updated):
            continue
        updated[i][field] = val
        auth_map = dict(updated[i].get("authority") or {})
        prev = normalize_status(auth_map.get(field))
        if prev == "PROVEN":
            # keep PROVEN if already proven
            pass
        else:
            auth_map[field] = "ENGINEER_REQUIRED"
            auth_map[f"{field}_acceptance"] = "ENGINEER_ACCEPTED"
        updated[i]["authority"] = auth_map
        updated[i][f"{field}_acceptance"] = "ENGINEER_ACCEPTED"
    return updated


def _should_skip_authority_only(field: str, auth: str, cfg: dict[str, Any]) -> bool:
    """field_authority metadata alone must NOT force REVIEW if value is PROVEN/DERIVED."""
    st = normalize_status(auth)
    if st not in ("REVIEW_REQUIRED", "ENGINEER_REQUIRED", "COMMISSIONING", "UNKNOWN"):
        return st in ("PROVEN", "DERIVED", "OPTIONAL")

    # Live value probes
    if field in ("divert_output_io", "divert_lane_topology"):
        rows = cfg.get("divert_rows") or []
        if rows and all(
            normalize_status((r.get("authority") or {}).get("divert_output_io")) == "PROVEN"
            and field_value(r.get("divert_output_io"))
            and field_value(r.get("divert_output_io")).upper() != "INVALID"
            for r in rows
        ):
            return True
    if field == "divert_pe":
        # Handled as object list — not skipped here
        return False
    if field in ("tracking_offset", "global_track_offset", "track_offset"):
        return False

    live = cfg.get(field)
    if field == "transport_area":
        live = cfg.get("area_name") or live
    if field == "induct_conveyor":
        live = cfg.get("induct_conveyor")
        live_auth = normalize_status((cfg.get("induct_authority") or {}).get("conveyor"))
        if live_auth == "PROVEN":
            return True
        if live_auth == "DERIVED" and field_value(live):
            return False  # may become ACCEPT_DERIVED via other path
    live_s = field_value(live)
    if not live_s:
        return False
    return False


def collect_review_items(cfg: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Build actionable review items with resolution types. OPTIONAL never active."""
    cfg = cfg or {}
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    def push(item: dict[str, Any]) -> None:
        field = str(item.get("field") or "").strip()
        if not field:
            return
        group = item.get("group") or review_group(field)
        key = f"{group}::{field}"
        if key in seen:
            return
        st = normalize_status(item.get("status"))
        rtype = item.get("resolution_type") or ""
        if st == "OPTIONAL" or rtype == "OPTIONAL":
            return
        if st in ("PROVEN",) and rtype != "ACCEPT_PROVEN":
            return
        if st == "DERIVED" and rtype != "ACCEPT_DERIVED":
            return
        if (
            st not in ACTIONABLE
            and st not in ("ENGINEER_REQUIRED", "COMMISSIONING", "REVIEW_REQUIRED")
            and rtype not in ("ACCEPT_DERIVED", "ACCEPT_PROVEN", "UNRESOLVED")
        ):
            return
        if not rtype:
            rtype = resolve_type_for(status=st, value=item.get("current_value"), why=str(item.get("why") or ""))
            item["resolution_type"] = rtype
        if rtype == "OPTIONAL":
            return
        seen.add(key)
        item = dict(item)
        item["field"] = field
        item["status"] = st or "REVIEW_REQUIRED"
        item["group"] = group
        item["focusId"] = item.get("focusId") or FIELD_FOCUS.get(field, "")
        item["lifecycle"] = item.get("lifecycle") or "PENDING_REVIEW"
        item["item_key"] = key
        item["evidence_fingerprint"] = evidence_fingerprint(
            field,
            item.get("current_value"),
            item.get("source") or item.get("detail") or "",
            item.get("status"),
        )
        items.append(item)

    for raw in cfg.get("configuration_required") or []:
        field = str(raw or "").strip()
        if not field:
            continue
        # divert_output_io mass-PROVEN must not become 32 review rows
        if field == "divert_output_io":
            rows = cfg.get("divert_rows") or []
            if rows and all(
                normalize_status((r.get("authority") or {}).get("divert_output_io")) == "PROVEN"
                for r in rows
            ):
                continue
        cur = ""
        if field in ("transport_area", "area_name"):
            cur = field_value(cfg.get("area_name"))
        elif field == "sorter_type":
            cur = field_value(cfg.get("sorter_type"))
        elif field == "induct_conveyor":
            cur = field_value(cfg.get("induct_conveyor"))
        elif field == "induct_pe":
            cur = field_value(cfg.get("induct_pe"))
        if cur and field in ("sorter_type", "transport_area", "area_name", "induct_pe"):
            continue
        push(
            {
                "field": field,
                "status": "REVIEW_REQUIRED",
                "resolution_type": "EDIT_REQUIRED",
                "detail": "configuration_required",
                "why": "Required configuration blank — engineer must enter/select a value.",
                "current_value": cur,
                "source": "configuration_required",
            }
        )

    fa = cfg.get("field_authority") or {}
    for field, auth in fa.items():
        st = normalize_status(auth)
        if st in ("OPTIONAL", "PROVEN", "DERIVED"):
            # Metadata alone must NOT force REVIEW when value class is PROVEN/DERIVED/OPTIONAL.
            # DERIVED confirmations use ACCEPT_DERIVED only when explicitly queued elsewhere.
            continue
        if field in ("tracking_offset", "global_track_offset", "track_offset", "divert_pe"):
            continue  # dedicated builders
        if field == "plc_generation":
            continue
        if _should_skip_authority_only(field, auth, cfg):
            continue
        if st not in ACTIONABLE and st not in ("ENGINEER_REQUIRED", "COMMISSIONING", "REVIEW_REQUIRED"):
            continue
        if st == "UNKNOWN":
            st = "REVIEW_REQUIRED"
        cur = ""
        if field in ("transport_area", "area_name"):
            cur = field_value(cfg.get("area_name"))
            if cur:
                continue
        if field == "sorter_type":
            cur = field_value(cfg.get("sorter_type"))
            if cur:
                continue
        if field == "induct_conveyor":
            cur = field_value(cfg.get("induct_conveyor"))
            live_auth = normalize_status((cfg.get("induct_authority") or {}).get("conveyor"))
            if live_auth in ("PROVEN", "DERIVED") and cur:
                continue
        rtype = resolve_type_for(status=st, value=cur)
        if rtype == "OPTIONAL":
            continue
        # Every active item must have actionable resolution or explicit UNRESOLVED reason
        if rtype not in RESOLUTION_TYPES:
            rtype = "UNRESOLVED"
        push(
            {
                "field": field,
                "status": st,
                "resolution_type": rtype,
                "detail": "field_authority",
                "why": (
                    f"Field authority {st} — resolution: {rtype}."
                    if rtype != "UNRESOLVED"
                    else f"Unresolved {field}: need evidence or engineer entry (authority={st})."
                ),
                "current_value": cur,
                "source": "field_authority",
            }
        )

    # Coverage gaps
    cov = cfg.get("coverage") or {}
    gap_lists: list[Any] = []
    for key in ("gaps", "coverage_gaps", "unresolved"):
        if isinstance(cov.get(key), list):
            gap_lists.extend(cov[key])
    for bucket in ("ENGINEER_REQUIRED", "REVIEW_REQUIRED"):
        fields = (cov.get(bucket) or {}).get("fields") if isinstance(cov.get(bucket), dict) else None
        if isinstance(fields, list):
            gap_lists.extend(fields)
    for g in gap_lists:
        if isinstance(g, str):
            field = g.strip()
            if not field:
                continue
            if field in ("tracking_offset", "divert_pe") or "Tracking distance" in field or "Divert PE" in field:
                continue
            push(
                {
                    "field": field,
                    "status": "REVIEW_REQUIRED",
                    "resolution_type": "EDIT_REQUIRED",
                    "detail": "coverage",
                    "why": "Coverage gap — engineer action required.",
                    "source": "coverage",
                }
            )
        elif isinstance(g, dict):
            field = str(g.get("field") or g.get("name") or g.get("key") or "").strip()
            if not field:
                continue
            st = normalize_status(g.get("authority") or g.get("status") or "REVIEW_REQUIRED")
            if st in ("OPTIONAL", "PROVEN", "DERIVED"):
                continue
            push(
                {
                    "field": field,
                    "status": st or "REVIEW_REQUIRED",
                    "resolution_type": resolve_type_for(status=st, value=g.get("value")),
                    "detail": g.get("detail") or "coverage",
                    "why": str(g.get("why") or g.get("detail") or "Coverage gap"),
                    "current_value": field_value(g.get("value")),
                    "source": "coverage",
                }
            )

    # Divert output IO: only unresolved rows — never force 32 identical PROVEN approvals
    unresolved_io = []
    for i, d in enumerate(cfg.get("divert_rows") or []):
        auth = normalize_status((d.get("authority") or {}).get("divert_output_io"))
        io = field_value(d.get("divert_output_io"))
        if auth == "PROVEN" and io and io.upper() != "INVALID":
            continue
        if auth in ("REVIEW_REQUIRED", "ENGINEER_REQUIRED", "COMMISSIONING", "UNKNOWN", "") or not io or io.upper() == "INVALID":
            unresolved_io.append(
                {
                    "index": i,
                    "name": field_value(d.get("name")),
                    "lane": field_value(d.get("lane")),
                    "divert_output_io": io,
                    "authority": auth or "REVIEW_REQUIRED",
                }
            )
    if unresolved_io:
        push(
            {
                "field": "divert_output_io",
                "status": "REVIEW_REQUIRED",
                "resolution_type": "EDIT_REQUIRED",
                "detail": f"{len(unresolved_io)} divert IO row(s)",
                "why": "Divert output IO unresolved on listed objects — not mass-approving PROVEN rows.",
                "objects": unresolved_io,
                "source": "divert_rows",
                "group": "divert",
                "focusId": FIELD_FOCUS["divert_output_io"],
            }
        )

    pe_objs = divert_pe_objects(cfg)
    fa_pe = normalize_status(fa.get("divert_pe"))
    if pe_objs or fa_pe in ("REVIEW_REQUIRED", "ENGINEER_REQUIRED", "COMMISSIONING"):
        if pe_objs or fa_pe:
            push(
                {
                    "field": "divert_pe",
                    "status": fa_pe if fa_pe in ACTIONABLE or fa_pe in ("ENGINEER_REQUIRED", "COMMISSIONING") else "REVIEW_REQUIRED",
                    "resolution_type": "EDIT_REQUIRED" if pe_objs else "UNRESOLVED",
                    "detail": f"{len(pe_objs)} divert PE object(s)" if pe_objs else "divert_pe",
                    "why": (
                        "Verify I/O INVALID / no distinct confirm PE — map PE on listed objects. "
                        "Bulk Accept All Derived / Apply Value / Mark Commissioning available; "
                        "never UNKNOWN→PROVEN."
                        if pe_objs
                        else "divert_pe marked REVIEW but no row objects available — need Verify I/O evidence."
                    ),
                    "objects": pe_objs,
                    "source": "divert_rows",
                    "group": "divert",
                    "focusId": FIELD_FOCUS["divert_pe"],
                    "current_value": "",
                }
            )

    off = tracking_offset_item(cfg)
    if off:
        push(off)

    return items


def collect_optional_items(cfg: dict[str, Any] | None) -> list[dict[str, Any]]:
    cfg = cfg or {}
    out = []
    for field, auth in (cfg.get("field_authority") or {}).items():
        if normalize_status(auth) == "OPTIONAL":
            out.append({"field": field, "status": "OPTIONAL", "group": review_group(field)})
    # Pack-level optional (Phase 1) — informational only
    for field in ("divert_confirm_pe", "global_track_offset"):
        # Only if not already an active review field with unresolved work
        if field == "global_track_offset":
            continue  # tracking_offset handled as review when required
        if not any(i.get("field") == field for i in out):
            # do not auto-push unless authority says OPTIONAL
            pass
    return out


def filter_active_items(
    items: list[dict[str, Any]],
    resolutions: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split PENDING vs RESOLVED; invalidate acceptance when fingerprint changed."""
    resolutions = resolutions or {}
    active: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []
    for it in items:
        key = it.get("item_key") or f"{it.get('group')}::{it.get('field')}"
        rec = resolutions.get(key) or resolutions.get(it.get("field"))
        if not rec:
            active.append(it)
            continue
        if str(rec.get("lifecycle") or rec.get("status") or "").upper() not in (
            "RESOLVED",
            "ACCEPTED",
            "EDITED",
        ):
            active.append(it)
            continue
        fp = it.get("evidence_fingerprint") or ""
        prior_fp = str(rec.get("evidence_fingerprint") or "")
        if prior_fp and fp and prior_fp != fp:
            # Source/value changed — re-open
            active.append(it)
            continue
        resolved.append(
            {
                **it,
                "lifecycle": "RESOLVED",
                "resolution": rec.get("resolution") or rec.get("lifecycle") or "ACCEPTED",
                "final_value": rec.get("final_value", it.get("current_value")),
                "original_classification": rec.get("original_classification") or it.get("status"),
                "resolved_at": rec.get("resolved_at"),
                "source": rec.get("source") or it.get("source"),
                "acceptance_kind": rec.get("acceptance_kind") or "ENGINEER_ACCEPTED",
            }
        )
    return active, resolved


def accept_item(
    resolutions: dict[str, Any],
    item: dict[str, Any],
    *,
    resolution: str = "ACCEPTED",
    final_value: Any = None,
    acceptance_kind: str = "ENGINEER_ACCEPTED",
) -> dict[str, Any]:
    """PENDING_REVIEW → ACCEPTED/EDITED → RESOLVED."""
    key = item.get("item_key") or f"{item.get('group')}::{item.get('field')}"
    res = "EDITED" if resolution.upper() == "EDITED" else "ACCEPTED"
    resolutions[key] = {
        "field": item.get("field"),
        "lifecycle": "RESOLVED",
        "resolution": res,
        "resolution_type": item.get("resolution_type"),
        "final_value": field_value(final_value if final_value is not None else item.get("current_value")),
        "source": item.get("source") or item.get("provenance") or "",
        "original_classification": item.get("status"),
        "acceptance_kind": acceptance_kind,
        "evidence_fingerprint": item.get("evidence_fingerprint")
        or evidence_fingerprint(
            item.get("field"),
            final_value if final_value is not None else item.get("current_value"),
            item.get("source") or "",
            item.get("status"),
        ),
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }
    return resolutions


def status_counts(
    active: list[dict[str, Any]],
    optional: list[dict[str, Any]],
    resolved: list[dict[str, Any]],
) -> dict[str, int]:
    counts = {
        "review_required": 0,
        "engineer_required": 0,
        "commissioning": 0,
        "optional": len(optional or []),
        "resolved": len(resolved or []),
    }
    for it in active or []:
        st = normalize_status(it.get("status"))
        if st == "ENGINEER_REQUIRED":
            counts["engineer_required"] += 1
        elif st == "COMMISSIONING":
            counts["commissioning"] += 1
        else:
            counts["review_required"] += 1
    return counts


def merge_resolutions_preserving(
    prior: dict[str, Any] | None,
    new_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Keep prior acceptance across Apply/reload unless fingerprint changed."""
    prior = dict(prior or {})
    fingerprints = {
        (it.get("item_key") or f"{it.get('group')}::{it.get('field')}"): it.get("evidence_fingerprint")
        for it in new_items
    }
    out: dict[str, Any] = {}
    for key, rec in prior.items():
        fp_now = fingerprints.get(key)
        prior_fp = str((rec or {}).get("evidence_fingerprint") or "")
        if fp_now is None:
            # Item no longer produced (e.g. filled) — keep record for REVIEWED section
            out[key] = rec
            continue
        if prior_fp and fp_now and prior_fp != fp_now:
            continue  # invalidate
        out[key] = rec
    return out

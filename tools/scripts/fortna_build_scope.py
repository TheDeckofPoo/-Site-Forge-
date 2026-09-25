"""Build scope architecture — PROJECT vs BUILD vs COMMISSIONABLE (addendum).

Minimum groundwork: allow PARTIAL / area-scoped generation without requiring
every Area/subsystem in the RUN to be fully engineered.

PD-0003 Safety integrity is NOT weakened:
  - no _Safe, fake PI writers, or fabricated ES devices
  - unresolved Safety *inside* the build closure still blocks COMPLETE/COMMISSIONABLE
  - unresolved Safety *outside* the build closure does not block PARTIAL generation
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SCOPE_FULL = "FULL_CONTROLLER"
SCOPE_AREA = "SELECTED_AREA"

INTENT_PARTIAL = "PARTIAL"
INTENT_COMPLETE = "COMPLETE"

CONF_RUN = "RUN_PROVEN"
CONF_DERIVED = "DERIVED"
CONF_ENGINEER = "ENGINEER_ASSIGNED"
CONF_REVIEW = "REVIEW_REQUIRED"
CONF_UNKNOWN = "UNKNOWN"


@dataclass
class BuildScope:
    """Selected build scope (subset of project)."""

    mode: str = SCOPE_FULL  # FULL_CONTROLLER | SELECTED_AREA
    selected_areas: list[str] = field(default_factory=list)
    # PARTIAL = engineering artifact OK with withheld unresolved deps
    # COMPLETE = all closure deps resolved (still may be non-commissionable)
    intent: str = INTENT_PARTIAL
    require_commissionable: bool = False

    def normalized_areas(self) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for a in self.selected_areas or []:
            if isinstance(a, dict):
                n = str(a.get("name") or a.get("id") or "").strip()
            else:
                n = str(a or "").strip()
            if not n or n in seen:
                continue
            seen.add(n)
            out.append(n)
        return out


@dataclass
class BuildClosure:
    """Deterministic dependency closure for the selected build scope."""

    scope: BuildScope
    areas: list[str] = field(default_factory=list)
    conveyors: list[str] = field(default_factory=list)
    safety_zones: list[str] = field(default_factory=list)
    # Shared / external deps crossing the build boundary (explicit, not duplicated)
    external_deps: list[dict[str, Any]] = field(default_factory=list)
    withheld: list[dict[str, Any]] = field(default_factory=list)

    def contains_conveyor(self, name: str) -> bool:
        n = str(name or "").strip().upper()
        if not n:
            return False
        if self.scope.mode != SCOPE_AREA:
            return True
        return n in {c.upper() for c in self.conveyors}

    def contains_area(self, name: str) -> bool:
        n = str(name or "").strip()
        if not n:
            return False
        if self.scope.mode != SCOPE_AREA:
            return True
        return n in set(self.areas)


def _area_name(a: Any) -> str:
    if isinstance(a, dict):
        return str(a.get("name") or a.get("id") or "").strip()
    return str(a or "").strip()


def _conv_area(c: Any) -> str:
    if isinstance(c, dict):
        return str(c.get("main_area") or c.get("area") or "").strip()
    return str(getattr(c, "main_area", "") or getattr(c, "area", "") or "").strip()


def _conv_name(c: Any) -> str:
    if isinstance(c, dict):
        return str(c.get("clean_name") or c.get("conveyor") or c.get("name") or "").strip()
    return str(
        getattr(c, "clean_name", None)
        or getattr(c, "conveyor", None)
        or getattr(c, "name", None)
        or ""
    ).strip()


def parse_build_scope(data: dict | None = None, *, inp: Any = None) -> BuildScope:
    """Parse build_scope from JSON / AutogenInput fields."""
    data = dict(data or {})
    if inp is not None:
        mode = str(getattr(inp, "build_scope_mode", None) or data.get("mode") or SCOPE_FULL)
        areas = list(getattr(inp, "build_scope_areas", None) or data.get("selected_areas") or [])
        intent = str(getattr(inp, "build_intent", None) or data.get("intent") or INTENT_PARTIAL)
        req = bool(
            getattr(inp, "require_commissionable", None)
            if getattr(inp, "require_commissionable", None) is not None
            else data.get("require_commissionable", False)
        )
    else:
        mode = str(data.get("mode") or SCOPE_FULL)
        areas = list(data.get("selected_areas") or data.get("areas") or [])
        intent = str(data.get("intent") or INTENT_PARTIAL)
        req = bool(data.get("require_commissionable", False))
    mode_u = mode.strip().upper().replace("-", "_")
    if mode_u in {"AREA", "SELECTED", "SELECTED_AREA", "ONE_AREA"}:
        mode_u = SCOPE_AREA
    else:
        mode_u = SCOPE_FULL
    intent_u = intent.strip().upper()
    if intent_u not in {INTENT_PARTIAL, INTENT_COMPLETE}:
        intent_u = INTENT_PARTIAL
    return BuildScope(
        mode=mode_u,
        selected_areas=areas,
        intent=intent_u,
        require_commissionable=req,
    )


def compute_build_closure(
    *,
    areas: list | None,
    conveyors: list | None,
    safety_zones: list | None = None,
    safety_zone_members: list | None = None,
    scope: BuildScope | None = None,
) -> BuildClosure:
    """Compute deterministic closure for FULL or SELECTED_AREA scope.

    Does not invent objects. Cross-area Safety relationships become external_deps.
    """
    scope = scope or BuildScope()
    all_areas = [_area_name(a) for a in (areas or []) if _area_name(a)]
    selected = scope.normalized_areas() if scope.mode == SCOPE_AREA else list(all_areas)
    if scope.mode == SCOPE_AREA and not selected:
        # No area selected → empty closure (PARTIAL engineering placeholder)
        return BuildClosure(scope=scope, areas=[], conveyors=[], safety_zones=[])

    area_set = set(selected) if scope.mode == SCOPE_AREA else set(all_areas)
    convs_in: list[str] = []
    for c in conveyors or []:
        cn = _conv_name(c)
        if not cn:
            continue
        if scope.mode == SCOPE_AREA and _conv_area(c) not in area_set:
            continue
        convs_in.append(cn)

    zones_in: list[str] = []
    external: list[dict[str, Any]] = []
    for z in safety_zone_members or []:
        if not isinstance(z, dict):
            continue
        zn = str(z.get("name") or z.get("engineering_name") or "").strip()
        za = str(z.get("area") or z.get("areaRef") or "").strip()
        zconvs = [
            str(x).strip()
            for x in (z.get("conveyors") or z.get("conveyorRefs") or [])
            if str(x).strip()
        ]
        if scope.mode != SCOPE_AREA:
            if zn:
                zones_in.append(zn)
            continue
        # In scope if zone's area matches OR any conveyor overlaps closure
        conv_hit = bool(set(x.upper() for x in zconvs) & set(x.upper() for x in convs_in))
        if za in area_set or conv_hit:
            if zn:
                zones_in.append(zn)
        elif zn and (z.get("members") or []):
            # Shared Safety device membership may cross Areas — record external
            for m in z.get("members") or []:
                external.append(
                    {
                        "kind": "shared_safety_device",
                        "device": str(m),
                        "zone": zn,
                        "area": za,
                        "relationship": "OUT_OF_SCOPE_ZONE",
                        "confidence": CONF_UNKNOWN,
                    }
                )

    # Named safety_zones list
    for n in safety_zones or []:
        ns = str(n).strip()
        if ns and ns not in zones_in and scope.mode != SCOPE_AREA:
            zones_in.append(ns)

    # Dedupe preserve order
    def _dedupe(xs: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for x in xs:
            k = x.upper() if x else ""
            if not x or k in seen:
                continue
            seen.add(k)
            out.append(x)
        return out

    return BuildClosure(
        scope=scope,
        areas=_dedupe(selected if scope.mode == SCOPE_AREA else all_areas),
        conveyors=_dedupe(convs_in),
        safety_zones=_dedupe(zones_in),
        external_deps=external,
    )


def classify_build_result(
    *,
    closure: BuildClosure,
    unresolved_in_closure: list[str] | None = None,
    live_fast_conv: int = 0,
    pi_writer_ok: bool = True,
) -> dict[str, Any]:
    """Return build_state + commissionable without weakening Safety integrity."""
    unresolved = list(unresolved_in_closure or [])
    intent = closure.scope.intent
    if unresolved or not pi_writer_ok:
        state = INTENT_PARTIAL
    elif intent == INTENT_COMPLETE:
        state = INTENT_COMPLETE
    else:
        state = INTENT_PARTIAL

    # GENERATED != COMMISSIONABLE: commissionable only when COMPLETE + resolved + live motion
    commissionable = (
        state == INTENT_COMPLETE
        and not unresolved
        and pi_writer_ok
        and (live_fast_conv > 0 or not closure.conveyors)
    )

    hard_block = False
    if intent == INTENT_COMPLETE and unresolved:
        hard_block = True
    if closure.scope.require_commissionable and not commissionable:
        hard_block = True

    return {
        "project_scope": "FULL_RUN",
        "build_scope": {
            "mode": closure.scope.mode,
            "selected_areas": list(closure.areas),
            "intent": intent,
        },
        "build_state": state,  # PARTIAL | COMPLETE
        "commissionable": bool(commissionable),
        "generated_ne_commissionable": True,  # always remind GENERATED != COMMISSIONABLE
        "closure": {
            "areas": list(closure.areas),
            "conveyors": list(closure.conveyors),
            "safety_zones": list(closure.safety_zones),
            "external_deps": list(closure.external_deps),
            "withheld": list(closure.withheld),
        },
        "unresolved_in_closure": unresolved,
        "hard_block_complete": hard_block,
        "note": (
            "Default/Unassigned Safety = discovered but not finally zoned; "
            "it does not automatically protect motion. Only unresolved deps "
            "inside the selected build closure affect COMPLETE/COMMISSIONABLE."
        ),
    }


def area_export_manifest(
    *,
    closure: BuildClosure,
    build_result: dict[str, Any],
    included_programs: list[str] | None = None,
    required_aois: list[str] | None = None,
    required_udts: list[str] | None = None,
    shared_safety_devices: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Architectural stub for Area → importable Program L5X dependency manifest."""
    return {
        "export_kind": "AREA_PROGRAM_L5X",
        "build_scope": build_result.get("build_scope"),
        "build_state": build_result.get("build_state"),
        "commissionable": build_result.get("commissionable"),
        "included": {
            "areas": list(closure.areas),
            "conveyors": list(closure.conveyors),
            "safety_zones": list(closure.safety_zones),
            "programs": list(included_programs or []),
        },
        "required_aois": list(required_aois or []),
        "required_udts": list(required_udts or []),
        "shared_safety_devices": list(shared_safety_devices or []),
        "external_tags_refs": list(closure.external_deps),
        "upstream_downstream_boundaries": [],
        "unresolved_dependencies": list(build_result.get("unresolved_in_closure") or []),
        "policy": {
            "no_invented_NO_star_for_cross_boundary": True,
            "no_safe_escape_hatch": True,
            "generated_ne_commissionable": True,
        },
    }

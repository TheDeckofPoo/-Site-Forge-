#!/usr/bin/env python3
"""Read-only Site Forge AI tool interfaces (Stage 1 design).

These tools expose narrow evidence lookups for the decoder investigator.
They MUST NOT mutate Site Forge state, Autogen, compiler input, or L5X.

Live OpenAI tool-calling is NOT wired yet — this module defines the contract
and a local in-process implementation for tests.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from fortna_ai_failure_cluster import cluster_unresolved_claims
from fortna_ai_io_evidence import build_evidence_bundle
from fortna_configio_binding_trace import get_configio_binding_trace as _binding_trace
from fortna_physical_word_resolver import PhysicalWordResolver, _load_eipmodules_rows
from fortna_rack_discovery import discover_racks


class ReadOnlyViolation(RuntimeError):
    """Raised if a mutation is attempted through the AI tool surface."""


@dataclass
class SiteForgeReadOnlyContext:
    """Immutable snapshot for one investigation session."""

    run_dir: Path
    machine: str
    project: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    _mutation_log: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.run_dir = Path(self.run_dir)
        if not self.evidence:
            self.evidence = build_evidence_bundle(
                self.run_dir, self.machine, project=self.project
            )

    def _deny_write(self, op: str) -> None:
        self._mutation_log.append(op)
        raise ReadOnlyViolation(f"AI tools are read-only; refused: {op}")


def get_project_identity(ctx: SiteForgeReadOnlyContext) -> dict[str, Any]:
    return {
        "project": ctx.evidence.get("project") or ctx.project,
        "machine": ctx.machine,
        "run_dir": str(ctx.run_dir),
        "evidence_status": ctx.evidence.get("evidence_status"),
    }


def get_machine(ctx: SiteForgeReadOnlyContext) -> dict[str, Any]:
    return {"machine": ctx.machine, "project": ctx.evidence.get("project")}


def get_io_claim(ctx: SiteForgeReadOnlyContext, claim_id: str) -> dict[str, Any] | None:
    for c in ctx.evidence.get("raw_claims") or []:
        if c.get("claim_id") == claim_id:
            return dict(c)
    return None


def get_configio_word(ctx: SiteForgeReadOnlyContext, word: int | str) -> list[dict[str, Any]]:
    try:
        w = int(float(str(word)))
    except (TypeError, ValueError):
        return []
    out = []
    for r in ctx.evidence.get("configio") or []:
        try:
            ow = int(r.get("Octal_Word") if "Octal_Word" in r else r.get("octal_word"))
        except (TypeError, ValueError):
            continue
        if ow == w:
            out.append(dict(r))
    return out


def get_configio_rows(ctx: SiteForgeReadOnlyContext, **filters: Any) -> list[dict[str, Any]]:
    rows = list(ctx.evidence.get("configio") or [])
    if "bank" in filters:
        want = str(filters["bank"])
        rows = [
            r
            for r in rows
            if str(r.get("Bank") if r.get("Bank") is not None else r.get("bank")) == want
        ]
    if "interface" in filters:
        want = str(filters["interface"]).upper()
        rows = [
            r
            for r in rows
            if str(r.get("Interface") or r.get("interface") or "").upper() == want
        ]
    return rows


def get_adapter(ctx: SiteForgeReadOnlyContext, adapter_name: str) -> dict[str, Any] | None:
    want = (adapter_name or "").strip().upper()
    for ad in (ctx.evidence.get("eipcfg") or {}).get("adapters") or []:
        rio = str(ad.get("rio_name") or ad.get("eipcfg_name") or "").upper()
        if rio == want:
            return dict(ad)
    return None


def get_module(
    ctx: SiteForgeReadOnlyContext, adapter_name: str, slot: int
) -> dict[str, Any] | None:
    ad = get_adapter(ctx, adapter_name)
    if not ad:
        return None
    for m in ad.get("modules") or []:
        try:
            if int(m.get("slot")) == int(slot):
                return dict(m)
        except (TypeError, ValueError):
            continue
    return None


def get_neighbor_claims(
    ctx: SiteForgeReadOnlyContext,
    *,
    word: int | str | None = None,
    adapter: str | None = None,
    limit: int = 40,
) -> list[dict[str, Any]]:
    out = []
    for c in ctx.evidence.get("raw_claims") or []:
        if word is not None and str(c.get("word")) != str(word):
            continue
        if adapter and str(c.get("adapter") or "").upper() != adapter.upper():
            continue
        out.append(
            {
                "claim_id": c.get("claim_id"),
                "io_name": c.get("io_name"),
                "word": c.get("word"),
                "bit": c.get("bit"),
                "disposition": c.get("deterministic_disposition"),
                "physical_address": c.get("physical_address"),
            }
        )
        if len(out) >= limit:
            break
    return out


def get_proven_io_examples(
    ctx: SiteForgeReadOnlyContext, *, limit: int = 20
) -> list[dict[str, Any]]:
    out = []
    for c in ctx.evidence.get("raw_claims") or []:
        if c.get("deterministic_disposition") != "ASSIGNED":
            continue
        out.append(
            {
                "claim_id": c.get("claim_id"),
                "io_name": c.get("io_name"),
                "word": c.get("word"),
                "bit": c.get("bit"),
                "physical_address": c.get("physical_address"),
            }
        )
        if len(out) >= limit:
            break
    return out


def get_failure_cluster(
    ctx: SiteForgeReadOnlyContext, cluster_id: str
) -> dict[str, Any] | None:
    clustered = cluster_unresolved_claims(
        ctx.evidence.get("raw_claims") or [], evidence=ctx.evidence
    )
    for cl in clustered.get("clusters") or []:
        if cl.get("cluster_id") == cluster_id:
            return cl
    return None


def get_source_rows(
    ctx: SiteForgeReadOnlyContext, source: str, row: int
) -> dict[str, Any] | None:
    src = (source or "").lower()
    if "conveyor" in src:
        for r in ctx.evidence.get("conveyor") or []:
            if int(r.get("row") or -1) == int(row):
                return dict(r)
    if "configio" in src:
        for r in ctx.evidence.get("configio") or []:
            if int(r.get("row") or -1) == int(row):
                return dict(r)
    return None


def get_hardware_family(ctx: SiteForgeReadOnlyContext, catalog: str) -> str:
    from fortna_hardware_family import detect_family_from_catalog

    return detect_family_from_catalog(catalog)


def get_physical_word_resolution_trace(
    ctx: SiteForgeReadOnlyContext, claim_id: str
) -> dict[str, Any]:
    claim = get_io_claim(ctx, claim_id)
    if not claim:
        return {"ok": False, "error": "claim_id not found"}
    resolver = PhysicalWordResolver(ctx.run_dir, ctx.machine)
    hit = resolver.resolve(claim.get("word"), claim.get("bit"))
    return {
        "ok": True,
        "claim_id": claim_id,
        "word": claim.get("word"),
        "bit": claim.get("bit"),
        "resolver_hit": hit,
        "deterministic_disposition": claim.get("deterministic_disposition"),
    }


def get_configio_binding_trace(ctx: SiteForgeReadOnlyContext, word: int | str) -> dict[str, Any]:
    """Read-only Configio word → hardware binding attempt log."""
    return _binding_trace(ctx.run_dir, ctx.machine, word)


def get_configio_binding_cluster_summary(ctx: SiteForgeReadOnlyContext) -> dict[str, Any]:
    """Aggregate Configio binding failures into root-cause clusters (one call)."""
    from fortna_configio_binding_trace import build_mscatl_binding_dossier
    from fortna_physical_word_resolver import _load_configio_rows

    # Generic: build dossier-like summary for current machine
    configio = _load_configio_rows(ctx.run_dir, ctx.machine)
    words = sorted({int(r["octal_word"]) for r in configio if r.get("octal_word") is not None})
    clusters: dict[str, dict[str, Any]] = {}
    representatives = []
    for w in words:
        tr = _binding_trace(ctx.run_dir, ctx.machine, w)
        final = tr.get("final") or {}
        reason = final.get("reason") or final.get("result") or "UNKNOWN"
        rej = [
            a.get("reason")
            for a in (tr.get("candidates_attempted") or [])
            if a.get("result") == "rejected" and a.get("reason")
        ]
        if final.get("result") == "NO_BINDING" and rej:
            from collections import Counter

            reason = Counter(rej).most_common(1)[0][0]
        halves = ((tr.get("configio") or {}).get("halves") or [])
        desc_patterns = [h.get("Desc") for h in halves]
        banks = [h.get("Bank") for h in halves]
        lohi = [h.get("LoHi") for h in halves]
        iface = [h.get("Interface") for h in halves]
        bucket = clusters.setdefault(
            str(reason),
            {
                "root_cause": reason,
                "words": [],
                "word_count": 0,
                "desc_patterns": [],
                "banks": [],
                "lohi": [],
                "interfaces": [],
            },
        )
        bucket["words"].append(w)
        bucket["word_count"] += 1
        bucket["desc_patterns"].extend([d for d in desc_patterns if d])
        bucket["banks"].extend([b for b in banks if b is not None])
        bucket["lohi"].extend([x for x in lohi if x])
        bucket["interfaces"].extend([x for x in iface if x])
        if len(representatives) < 8:
            representatives.append(
                {
                    "word": w,
                    "root_cause": reason,
                    "configio": tr.get("configio"),
                    "final": final,
                }
            )
    # Deduplicate pattern lists
    for b in clusters.values():
        b["desc_patterns"] = sorted(set(map(str, b["desc_patterns"])))[:20]
        b["banks"] = sorted(set(b["banks"]))[:40]
        b["lohi"] = sorted(set(map(str, b["lohi"])))
        b["interfaces"] = sorted(set(map(str, b["interfaces"])))
    return {
        "ok": True,
        "machine": ctx.machine,
        "configio_word_count": len(words),
        "root_cause_clusters": sorted(clusters.values(), key=lambda x: -x["word_count"]),
        "representatives": representatives,
        "read_only": True,
    }


def get_adapter_modules(ctx: SiteForgeReadOnlyContext, adapter_name: str) -> dict[str, Any]:
    """Complete rack in one call from rack discovery."""
    disc = discover_racks(ctx.run_dir, ctx.machine)
    want = (adapter_name or "").strip().upper()
    for rack in disc.get("racks") or []:
        aliases = [str(a).upper() for a in (rack.get("source_aliases") or [])]
        if want in aliases or want == str(rack.get("provisional_display_name") or "").upper():
            return {"ok": True, "rack": rack, "read_only": True}
    return {"ok": False, "error": f"adapter not found: {adapter_name}", "read_only": True}


def get_eip_bank_map(ctx: SiteForgeReadOnlyContext) -> dict[str, Any]:
    """Compact current-machine adapter/slot/catalog/bank map."""
    disc = discover_racks(ctx.run_dir, ctx.machine)
    rows = []
    for rack in disc.get("racks") or []:
        for m in rack.get("modules") or []:
            rows.append(
                {
                    "adapter": (rack.get("source_aliases") or [None])[0],
                    "provisional_display_name": rack.get("provisional_display_name"),
                    "canonical_adapter_id": rack.get("canonical_adapter_id"),
                    "ip": rack.get("ip_address"),
                    "slot": m.get("physical_slot"),
                    "catalog": m.get("catalog_number"),
                    "family": m.get("hardware_family"),
                    "direction": m.get("direction"),
                    "input_bank": m.get("input_bank"),
                    "output_bank": m.get("output_bank"),
                    "data_index": m.get("data_index"),
                    "status": m.get("status"),
                }
            )
    return {"ok": True, "machine": ctx.machine, "rows": rows, "count": len(rows), "read_only": True}


def compare_candidate_rule_against_site(
    ctx: SiteForgeReadOnlyContext, candidate: dict[str, Any]
) -> dict[str, Any]:
    """Read-only: validate schema + report affected claim coverage. No mutation."""
    from fortna_ai_decoder_schema import validate_decoder_rule_candidate

    v = validate_decoder_rule_candidate(candidate)
    ids = set(candidate.get("affected_claim_ids") or [])
    present = {
        c.get("claim_id")
        for c in (ctx.evidence.get("raw_claims") or [])
        if c.get("claim_id") in ids
    }
    return {
        "schema_ok": v["ok"],
        "compiler_authority": False,
        "creates_ready": False,
        "reasons": v["reasons"],
        "affected_present": sorted(present),
        "affected_missing": sorted(ids - present),
    }


# Explicit mutation stubs — always refuse
def _refuse_mutation(ctx: SiteForgeReadOnlyContext, *args: Any, **kwargs: Any) -> None:
    ctx._deny_write(kwargs.get("op") or args[0] if args else "mutation")


TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "get_project_identity": get_project_identity,
    "get_machine": get_machine,
    "get_io_claim": get_io_claim,
    "get_configio_word": get_configio_word,
    "get_configio_rows": get_configio_rows,
    "get_adapter": get_adapter,
    "get_module": get_module,
    "get_neighbor_claims": get_neighbor_claims,
    "get_proven_io_examples": get_proven_io_examples,
    "get_failure_cluster": get_failure_cluster,
    "get_source_rows": get_source_rows,
    "get_hardware_family": get_hardware_family,
    "get_physical_word_resolution_trace": get_physical_word_resolution_trace,
    "get_configio_binding_trace": get_configio_binding_trace,
    "get_configio_binding_cluster_summary": get_configio_binding_cluster_summary,
    "get_adapter_modules": get_adapter_modules,
    "get_eip_bank_map": get_eip_bank_map,
    "compare_candidate_rule_against_site": compare_candidate_rule_against_site,
}

# Documented as non-tools — any attempt must fail
FORBIDDEN_MUTATION_OPS = frozenset(
    {
        "save_hardware_io_channel",
        "write_autogen",
        "accept_assignment",
        "generate_plc",
        "edit_engineer_selection",
        "modify_compiler",
        "write_l5x",
    }
)


def invoke_tool(ctx: SiteForgeReadOnlyContext, name: str, **kwargs: Any) -> Any:
    if name in FORBIDDEN_MUTATION_OPS:
        ctx._deny_write(name)
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        raise KeyError(f"unknown read-only tool: {name}")
    result = fn(ctx, **kwargs) if name != "get_project_identity" else fn(ctx)
    # Evidence-purity annotation — CURRENT_DECODER_OUTPUT must not prove decoder rules
    try:
        from fortna_evidence_purity import classify_tool_evidence

        purity = classify_tool_evidence(name)
        if isinstance(result, dict):
            out = dict(result)
            out["evidence_purity"] = purity
            if purity.get("evidence_class") == "CURRENT_DECODER_OUTPUT":
                out["evidence_purity_warning"] = (
                    "Current decoder output is not evidence that the decoder's rule is correct."
                )
            return out
    except Exception:
        pass
    return result

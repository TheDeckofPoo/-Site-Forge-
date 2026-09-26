#!/usr/bin/env python3
"""Cost-budgeted Decoder Investigator (Responses API, two-phase).

PHASE A INVESTIGATE — read-only tools
PHASE B SYNTHESIZE — tools disabled, DecoderRuleCandidate required

Primary stop: estimated_session_cost_usd ($0.40 synthesis / $0.50 hard).
Never leave outstanding function calls unserviced then continue invalidly.
Never implements decoder rules.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_ai_decoder_schema import (  # noqa: E402
    FORBIDDEN_AUTHORITY_FIELDS,
    validate_decoder_rule_candidate,
)
from fortna_ai_readonly_tools import (  # noqa: E402
    FORBIDDEN_MUTATION_OPS,
    ReadOnlyViolation,
    SiteForgeReadOnlyContext,
    invoke_tool,
)

DEFAULT_MODEL = "gpt-5.6-terra"
PRICING_PATH = REPO_ROOT / "config" / "ai_model_pricing.json"

INVESTIGATOR_TOOLS = [
    "get_project_identity",
    "get_configio_word",
    "get_configio_rows",
    "get_configio_binding_trace",
    "get_configio_binding_cluster_summary",
    "get_adapter",
    "get_adapter_modules",
    "get_eip_bank_map",
    "get_module",
    "get_hardware_family",
    "get_source_rows",
    "get_failure_cluster",
    "get_physical_word_resolution_trace",
    "compare_candidate_rule_against_site",
    "get_io_claim",
    "get_neighbor_claims",
]


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _model_name() -> str:
    return (os.environ.get("SITEFORGE_AI_MODEL") or DEFAULT_MODEL).strip()


def load_pricing(model: str) -> dict[str, Any]:
    raw = json.loads(PRICING_PATH.read_text(encoding="utf-8"))
    m = (raw.get("models") or {}).get(model) or (raw.get("models") or {}).get(DEFAULT_MODEL) or {}
    return {
        "pricing_snapshot": {
            "model": model,
            "source": str(PRICING_PATH),
            "input_usd_per_million": float(m.get("input_usd_per_million") or 1.25),
            "cached_input_usd_per_million": float(m.get("cached_input_usd_per_million") or 0.125),
            "output_usd_per_million": float(m.get("output_usd_per_million") or 10.0),
            "investigation_session_budget_usd": float(
                raw.get("investigation_session_budget_usd") or 0.50
            ),
            "synthesis_trigger_usd": float(raw.get("synthesis_trigger_usd") or 0.40),
            "note": raw.get("note"),
        }
    }


def estimate_cost_usd(usage: dict[str, Any], pricing: dict[str, Any]) -> float:
    p = pricing["pricing_snapshot"]
    inp = float(usage.get("input_tokens") or 0)
    cached = float(usage.get("cached_input_tokens") or usage.get("input_tokens_details", {}).get("cached_tokens") or 0)
    # If cached reported separately, non-cached = input - cached
    if cached and cached <= inp:
        non_cached = inp - cached
    else:
        non_cached = inp
        cached = 0.0
    out = float(usage.get("output_tokens") or 0)
    cost = (
        non_cached * p["input_usd_per_million"]
        + cached * p["cached_input_usd_per_million"]
        + out * p["output_usd_per_million"]
    ) / 1_000_000.0
    return round(cost, 6)


def _tool_schemas() -> list[dict[str, Any]]:
    return [
        {"type": "function", "name": "get_project_identity", "description": "Project/machine identity.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
        {"type": "function", "name": "get_configio_binding_cluster_summary", "description": "Aggregate Configio binding root-cause clusters for the whole machine in one call.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
        {"type": "function", "name": "get_eip_bank_map", "description": "Compact adapter/slot/catalog/bank map for current machine.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
        {"type": "function", "name": "get_adapter_modules", "description": "Complete rack: adapter + all modules/slots/banks.", "parameters": {"type": "object", "properties": {"adapter_name": {"type": "string"}}, "required": ["adapter_name"], "additionalProperties": False}},
        {"type": "function", "name": "get_configio_word", "description": "Configio rows for one Octal_Word.", "parameters": {"type": "object", "properties": {"word": {"type": ["integer", "string"]}}, "required": ["word"], "additionalProperties": False}},
        {"type": "function", "name": "get_configio_rows", "description": "Filter Configio rows.", "parameters": {"type": "object", "properties": {"bank": {"type": ["integer", "string"]}, "interface": {"type": "string"}}, "additionalProperties": False}},
        {"type": "function", "name": "get_unsupported_interfaces", "description": "List unsupported Configio interface families (e.g. PAMUX_AC51) the deterministic decoder skipped.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
        {"type": "function", "name": "get_unsupported_configio_rows", "description": "Raw unsupported Configio rows (AC51 etc.) with provenance. Never invents endpoints.", "parameters": {"type": "object", "properties": {"interface": {"type": "string"}, "limit": {"type": "integer"}}, "additionalProperties": False}},
        {"type": "function", "name": "get_raw_unresolved_source_rows", "description": "Controller-context raw/unsupported evidence for total deterministic failure sites.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}, "additionalProperties": False}},
        {"type": "function", "name": "get_configio_binding_trace", "description": "Full binding attempt for one Configio word.", "parameters": {"type": "object", "properties": {"word": {"type": ["integer", "string"]}}, "required": ["word"], "additionalProperties": False}},
        {"type": "function", "name": "get_adapter", "description": "One adapter by name.", "parameters": {"type": "object", "properties": {"adapter_name": {"type": "string"}}, "required": ["adapter_name"], "additionalProperties": False}},
        {"type": "function", "name": "get_module", "description": "One module by adapter+slot.", "parameters": {"type": "object", "properties": {"adapter_name": {"type": "string"}, "slot": {"type": "integer"}}, "required": ["adapter_name", "slot"], "additionalProperties": False}},
        {"type": "function", "name": "get_hardware_family", "description": "Family from catalog.", "parameters": {"type": "object", "properties": {"catalog": {"type": "string"}}, "required": ["catalog"], "additionalProperties": False}},
        {"type": "function", "name": "get_source_rows", "description": "Conveyor/Configio row.", "parameters": {"type": "object", "properties": {"source": {"type": "string"}, "row": {"type": "integer"}}, "required": ["source", "row"], "additionalProperties": False}},
        {"type": "function", "name": "get_failure_cluster", "description": "Failure cluster by id.", "parameters": {"type": "object", "properties": {"cluster_id": {"type": "string"}}, "required": ["cluster_id"], "additionalProperties": False}},
        {"type": "function", "name": "get_physical_word_resolution_trace", "description": "Resolver hit for claim_id.", "parameters": {"type": "object", "properties": {"claim_id": {"type": "string"}}, "required": ["claim_id"], "additionalProperties": False}},
        {"type": "function", "name": "compare_candidate_rule_against_site", "description": "Validate DecoderRuleCandidate schema/coverage.", "parameters": {"type": "object", "properties": {"candidate": {"type": "object"}}, "required": ["candidate"], "additionalProperties": False}},
        {"type": "function", "name": "get_io_claim", "description": "One claim by id.", "parameters": {"type": "object", "properties": {"claim_id": {"type": "string"}}, "required": ["claim_id"], "additionalProperties": False}},
        {"type": "function", "name": "get_neighbor_claims", "description": "Neighbor claims.", "parameters": {"type": "object", "properties": {"word": {"type": ["integer", "string"]}, "adapter": {"type": "string"}, "limit": {"type": "integer"}}, "additionalProperties": False}},
    ]


def _dispatch(ctx: SiteForgeReadOnlyContext, name: str, args: dict[str, Any]) -> Any:
    if name in FORBIDDEN_MUTATION_OPS or name not in INVESTIGATOR_TOOLS:
        raise ReadOnlyViolation(f"tool not allowed: {name}")
    if name in {"get_project_identity", "get_configio_binding_cluster_summary", "get_eip_bank_map"}:
        return invoke_tool(ctx, name)
    if name == "get_hardware_family":
        return invoke_tool(ctx, name, catalog=args.get("catalog") or "")
    if name == "get_adapter_modules":
        return invoke_tool(ctx, name, adapter_name=args.get("adapter_name") or "")
    if name == "get_configio_rows":
        kw = {k: args[k] for k in ("bank", "interface") if k in args and args[k] is not None}
        return invoke_tool(ctx, name, **kw)
    if name == "get_neighbor_claims":
        kw = {k: args[k] for k in ("word", "adapter", "limit") if k in args}
        return invoke_tool(ctx, name, **kw)
    if name == "compare_candidate_rule_against_site":
        return invoke_tool(ctx, name, candidate=args.get("candidate") or {})
    if name == "get_module":
        return invoke_tool(ctx, name, adapter_name=args.get("adapter_name") or "", slot=int(args["slot"]))
    if name == "get_source_rows":
        return invoke_tool(ctx, name, source=args.get("source") or "", row=int(args["row"]))
    key = {
        "get_configio_word": "word",
        "get_configio_binding_trace": "word",
        "get_adapter": "adapter_name",
        "get_failure_cluster": "cluster_id",
        "get_physical_word_resolution_trace": "claim_id",
        "get_io_claim": "claim_id",
    }[name]
    return invoke_tool(ctx, name, **{key: args.get(key)})


def _usage_dict(resp: Any) -> dict[str, Any]:
    usage = getattr(resp, "usage", None)
    if usage is None and isinstance(resp, dict):
        usage = resp.get("usage") or {}
    if usage is None:
        return {}
    if isinstance(usage, dict):
        out = dict(usage)
    else:
        out = {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }
        details = getattr(usage, "input_tokens_details", None)
        if details is not None:
            out["cached_input_tokens"] = getattr(details, "cached_tokens", None)
    # nested cached
    itd = out.get("input_tokens_details")
    if isinstance(itd, dict) and "cached_tokens" in itd and "cached_input_tokens" not in out:
        out["cached_input_tokens"] = itd.get("cached_tokens")
    return out


def _output_text(resp: Any) -> str:
    t = getattr(resp, "output_text", None)
    if t:
        return str(t)
    if isinstance(resp, dict) and resp.get("output_text"):
        return str(resp["output_text"])
    chunks = []
    output = getattr(resp, "output", None)
    if output is None and isinstance(resp, dict):
        output = resp.get("output")
    for item in output or []:
        if isinstance(item, dict) and item.get("type") == "message":
            for c in item.get("content") or []:
                if isinstance(c, dict) and c.get("type") in {"output_text", "text"}:
                    chunks.append(c.get("text") or "")
        else:
            content = getattr(item, "content", None)
            if content:
                for c in content:
                    txt = getattr(c, "text", None)
                    if txt:
                        chunks.append(str(txt))
    return "\n".join(chunks)


def _tool_calls(resp: Any) -> list[dict[str, Any]]:
    calls = []
    output = getattr(resp, "output", None)
    if output is None and isinstance(resp, dict):
        output = resp.get("output")
    for item in output or []:
        typ = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
        if typ in {"function_call", "tool_call", "custom_tool_call"}:
            if isinstance(item, dict):
                calls.append(item)
            else:
                calls.append(
                    {
                        "type": typ,
                        "call_id": getattr(item, "call_id", None) or getattr(item, "id", None),
                        "name": getattr(item, "name", None),
                        "arguments": getattr(item, "arguments", None),
                    }
                )
    return calls


def _dump(resp: Any) -> dict[str, Any]:
    try:
        return resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)
    except Exception:
        return {"output_text": _output_text(resp), "usage": _usage_dict(resp)}


def _parse_candidate(text: str) -> tuple[dict[str, Any] | None, str | None]:
    t = (text or "").strip()
    if not t:
        return None, "empty_final_text"
    if "```" in t:
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
        if m:
            t = m.group(1)
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        return None, "no_json_object"
    try:
        return json.loads(t[start : end + 1]), None
    except Exception as exc:
        return None, str(exc)


def _authority_hits(obj: Any) -> list[str]:
    text = obj if isinstance(obj, str) else json.dumps(obj)
    hits = []
    for f in FORBIDDEN_AUTHORITY_FIELDS | {"plc_channel", "Autogen", "compiler_accepted", "physical_endpoint"}:
        if f in text:
            hits.append(f)
    if re.search(r'"status"\s*:\s*"READY"', text):
        hits.append("status=READY")
    return sorted(set(hits))


def reclassify_r1_session(r1_dir: Path) -> dict[str, Any]:
    note = {
        "investigation_id": "MSCATL_BINDING_INVESTIGATION_001",
        "reclassified_at": _ts(),
        "prior_label": "INSUFFICIENT_EVIDENCE",
        "corrected_classification": "INCOMPLETE_SESSION",
        "reason": "TOOL_BUDGET_PROTOCOL_TERMINATION",
        "explanation": (
            "Session ended with outstanding function calls when the hard 30-call limit "
            "was reached. The model did NOT conclude Atlanta lacks evidence; the harness "
            "interrupted investigation. No DecoderRuleCandidate was produced; no rule "
            "was implemented; compiler untouched."
        ),
    }
    r1_dir.mkdir(parents=True, exist_ok=True)
    (r1_dir / "reclassification.json").write_text(json.dumps(note, indent=2), encoding="utf-8")
    # Patch summary if present
    summary_path = r1_dir / "investigation_summary.json"
    if summary_path.is_file():
        s = json.loads(summary_path.read_text(encoding="utf-8"))
        s["final_status"] = "INCOMPLETE_SESSION"
        s["incomplete_reason"] = "TOOL_BUDGET_PROTOCOL_TERMINATION"
        s["reclassified"] = True
        summary_path.write_text(json.dumps(s, indent=2), encoding="utf-8")
    return note


def run_investigation(
    *,
    run_dir: Path,
    blind_packet: dict[str, Any],
    out_dir: Path,
    machine: str = "MSCATL_CP3",
    project: str = "MSCATL_CP3",
    investigation_id: str = "MSCATL_BINDING_INVESTIGATION_001_R2",
) -> dict[str, Any]:
    from openai import OpenAI

    out_dir.mkdir(parents=True, exist_ok=True)
    model = _model_name()
    pricing = load_pricing(model)
    snap = pricing["pricing_snapshot"]
    budget = float(snap["investigation_session_budget_usd"])
    trigger = float(snap["synthesis_trigger_usd"])
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise SystemExit("OPENAI_API_KEY missing")

    client = OpenAI(api_key=key)
    mach = (machine or "MSCATL_CP3").strip()
    proj = (project or mach).strip()
    inv_id = (
        investigation_id
        or blind_packet.get("investigation_id")
        or "DECODER_INVESTIGATION"
    )
    ctx = SiteForgeReadOnlyContext(run_dir=run_dir, machine=mach, project=proj)

    (out_dir / "blind_packet.json").write_text(json.dumps(blind_packet, indent=2), encoding="utf-8")
    (out_dir / "pricing_snapshot.json").write_text(json.dumps(pricing, indent=2), encoding="utf-8")

    system = (
        f"You are Site Forge Decoder Investigator for {mach} (project {proj}). "
        "Investigate missing Fortna deterministic conventions. "
        "You are NOT an endpoint resolver. Use read-only tools. "
        "Prefer aggregate tools (get_configio_binding_cluster_summary, get_eip_bank_map, "
        "get_adapter_modules) before many single-word calls. "
        "Cite tool evidence. Search for counterexamples across multiple words. "
        "Final answer MUST be DecoderRuleCandidate JSON. "
        "status: CANDIDATE | REVIEW_REQUIRED | INSUFFICIENT_EVIDENCE. "
        "Never return physical_endpoint, ai_derived, READY, Autogen, or PLC code. "
        "Do not assume High Configio halves bind to Low modules unless evidence proves it."
    )
    user = (
        (blind_packet.get("problem_statement") or blind_packet.get("question") or "")
        + "\n\n"
        + json.dumps(
            {
                "site_summary": blind_packet.get("site_summary"),
                "constraints": blind_packet.get("constraints"),
                "output_contract": blind_packet.get("output_contract"),
                "available_read_only_tools": blind_packet.get("available_read_only_tools")
                or INVESTIGATOR_TOOLS,
                "evidence_rows": blind_packet.get("evidence_rows"),
                "configio_words_available": [
                    w.get("word") for w in (blind_packet.get("configio_word_evidence") or [])
                ]
                or sorted(
                    {
                        str(r.get("octal_word"))
                        for r in (blind_packet.get("evidence_rows") or [])
                        if r.get("octal_word") is not None
                    }
                ),
            },
            indent=2,
        )
    )

    initial = {
        "model": model,
        "investigation_id": inv_id,
        "budget_usd": budget,
        "synthesis_trigger_usd": trigger,
        "system": system,
        "machine": mach,
        "project": proj,
    }
    (out_dir / "initial_request.json").write_text(json.dumps(initial, indent=2), encoding="utf-8")

    transcript: list[dict[str, Any]] = []
    request_count = 0
    tool_rounds = 0
    tool_calls = 0
    cumulative_cost = 0.0
    cost_log: list[dict[str, Any]] = []
    usage_tot = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    t0 = time.perf_counter()
    phase = "INVESTIGATE"
    synthesis_triggered = False
    final_text = ""
    prev_id = None

    def _accumulate(usage: dict[str, Any]) -> float:
        nonlocal cumulative_cost
        for k in ("input_tokens", "output_tokens", "total_tokens"):
            if usage.get(k) is not None:
                usage_tot[k] = int(usage_tot.get(k) or 0) + int(usage[k] or 0)
        if usage.get("cached_input_tokens") is not None:
            usage_tot["cached_input_tokens"] = int(usage_tot.get("cached_input_tokens") or 0) + int(
                usage.get("cached_input_tokens") or 0
            )
        req_cost = estimate_cost_usd(usage, pricing)
        cumulative_cost = round(cumulative_cost + req_cost, 6)
        return req_cost

    def _service_calls(resp: Any) -> list[dict[str, Any]]:
        nonlocal tool_calls, tool_rounds
        calls = _tool_calls(resp)
        if not calls:
            return []
        tool_rounds += 1
        outs = []
        for call in calls:
            tool_calls += 1
            name = call.get("name") or ""
            raw_args = call.get("arguments") or "{}"
            call_id = call.get("call_id") or call.get("id") or f"call_{tool_calls}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except json.JSONDecodeError:
                args = {}
            try:
                result = _dispatch(ctx, name, args if isinstance(args, dict) else {})
                ok, err = True, None
            except Exception as exc:
                result, ok, err = {"ok": False, "error": str(exc)}, False, str(exc)
            rec = {
                "event": "tool_call",
                "round": tool_rounds,
                "call_index": tool_calls,
                "call_id": call_id,
                "name": name,
                "arguments": args,
                "ok": ok,
                "error": err,
                "result": result,
            }
            transcript.append(rec)
            (out_dir / f"tool_call_{tool_calls:03d}_{name}.json").write_text(
                json.dumps(rec, indent=2, default=str), encoding="utf-8"
            )
            outs.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result, default=str)[:120000],
                }
            )
        return outs

    # ---- PHASE A: first request with tools ----
    request_count += 1
    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        tools=_tool_schemas(),
    )
    prev_id = getattr(resp, "id", None)
    usage = _usage_dict(resp)
    req_cost = _accumulate(usage)
    cost_log.append({"request": request_count, "phase": phase, "usage": usage, "request_cost_usd": req_cost, "cumulative_session_cost_usd": cumulative_cost})
    (out_dir / f"model_response_{request_count:02d}.json").write_text(
        json.dumps(_dump(resp), indent=2, default=str), encoding="utf-8"
    )
    transcript.append({"event": "model_response", "request": request_count, "phase": phase, "usage": usage})

    # Investigate loop: always fully service tool batches before next model call
    while True:
        calls = _tool_calls(resp)
        text = _output_text(resp)
        if text:
            final_text = text

        if not calls:
            # Model returned text without tools — may already be final
            break

        # Service ALL outstanding calls before any continuation decision
        outs = _service_calls(resp)

        # Cost gate AFTER servicing (never leave dangling calls)
        if cumulative_cost >= budget:
            phase = "TERMINATED_AT_BUDGET"
            transcript.append(
                {
                    "event": "hard_budget_stop",
                    "cumulative_session_cost_usd": cumulative_cost,
                    "note": "No new model requests after servicing outstanding tools",
                }
            )
            break

        if cumulative_cost >= trigger and not synthesis_triggered:
            synthesis_triggered = True
            phase = "SYNTHESIZE"
            request_count += 1
            synth_msg = (
                "You are approaching the investigation cost budget. "
                "Use only evidence already collected. Tools are now disabled. "
                "Return your final DecoderRuleCandidate JSON now. "
                "If evidence does not support a candidate, return status "
                "INSUFFICIENT_EVIDENCE. Do not assign endpoints."
            )
            resp = client.responses.create(
                model=model,
                previous_response_id=prev_id,
                input=outs
                + [{"role": "user", "content": synth_msg}],
                # tools omitted = synthesis
            )
            prev_id = getattr(resp, "id", None)
            usage = _usage_dict(resp)
            req_cost = _accumulate(usage)
            cost_log.append(
                {
                    "request": request_count,
                    "phase": phase,
                    "usage": usage,
                    "request_cost_usd": req_cost,
                    "cumulative_session_cost_usd": cumulative_cost,
                    "synthesis_triggered": True,
                }
            )
            (out_dir / f"model_response_{request_count:02d}.json").write_text(
                json.dumps(_dump(resp), indent=2, default=str), encoding="utf-8"
            )
            transcript.append(
                {"event": "model_response", "request": request_count, "phase": phase, "usage": usage}
            )
            final_text = _output_text(resp) or final_text
            # If synthesis still tries tools, service then stop without another paid loop ideally
            if _tool_calls(resp):
                _service_calls(resp)
            break

        # Continue investigate with tools
        if cumulative_cost >= budget:
            break
        request_count += 1
        resp = client.responses.create(
            model=model,
            previous_response_id=prev_id,
            input=outs,
            tools=_tool_schemas(),
        )
        prev_id = getattr(resp, "id", None)
        usage = _usage_dict(resp)
        req_cost = _accumulate(usage)
        cost_log.append(
            {
                "request": request_count,
                "phase": phase,
                "usage": usage,
                "request_cost_usd": req_cost,
                "cumulative_session_cost_usd": cumulative_cost,
            }
        )
        (out_dir / f"model_response_{request_count:02d}.json").write_text(
            json.dumps(_dump(resp), indent=2, default=str), encoding="utf-8"
        )
        transcript.append(
            {"event": "model_response", "request": request_count, "phase": phase, "usage": usage}
        )

        # If next iteration would exceed budget before synthesis, force synthesize next
        if cumulative_cost >= trigger and not synthesis_triggered:
            # loop will hit synthesize branch after servicing any new calls
            continue

    # If we ended investigate with text but never synthesized and cost < trigger,
    # ask one synthesis-only call if budget remains
    if (
        not synthesis_triggered
        and cumulative_cost < budget
        and (not final_text or _parse_candidate(final_text)[0] is None)
        and phase == "INVESTIGATE"
    ):
        # Only if last response had no outstanding tools
        if not _tool_calls(resp):
            synthesis_triggered = True
            phase = "SYNTHESIZE"
            request_count += 1
            resp = client.responses.create(
                model=model,
                previous_response_id=prev_id,
                input=[
                    {
                        "role": "user",
                        "content": (
                            "Investigation phase complete. Tools disabled. "
                            "Return ONLY DecoderRuleCandidate JSON now, or "
                            "INSUFFICIENT_EVIDENCE if unsupported."
                        ),
                    }
                ],
            )
            usage = _usage_dict(resp)
            req_cost = _accumulate(usage)
            cost_log.append(
                {
                    "request": request_count,
                    "phase": phase,
                    "usage": usage,
                    "request_cost_usd": req_cost,
                    "cumulative_session_cost_usd": cumulative_cost,
                    "synthesis_triggered": True,
                }
            )
            (out_dir / f"model_response_{request_count:02d}.json").write_text(
                json.dumps(_dump(resp), indent=2, default=str), encoding="utf-8"
            )
            transcript.append(
                {"event": "model_response", "request": request_count, "phase": phase, "usage": usage}
            )
            final_text = _output_text(resp) or final_text

    latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    (out_dir / "raw_final_text.txt").write_text(final_text or "", encoding="utf-8")
    (out_dir / "transcript.json").write_text(json.dumps(transcript, indent=2, default=str), encoding="utf-8")

    auth = _authority_hits(final_text)
    candidate, parse_err = _parse_candidate(final_text)
    if auth:
        status = "REVIEW_REQUIRED"
        candidate = {
            "investigation_id": inv_id,
            "subsystem": "configio_to_hardware_binding",
            "failure_pattern": "AUTHORITY_VIOLATION",
            "affected_claim_ids": [],
            "affected_count": 0,
            "observed_facts": [f"Forbidden fields: {auth}"],
            "evidence_refs": [],
            "candidate_rule_name": "rejected_authority_response",
            "candidate_rule_description": "Forbidden compiler/endpoint authority in response.",
            "proposed_inputs": [],
            "proposed_transformation": "NONE",
            "expected_outputs": [],
            "supporting_examples": [],
            "counterexamples": [],
            "ambiguities": [],
            "additional_evidence_needed": [],
            "tests_required": [],
            "scope": mach,
            "confidence": "LOW",
            "status": "REVIEW_REQUIRED",
        }
    elif candidate is None:
        status = "INSUFFICIENT_EVIDENCE"
        candidate = {
            "investigation_id": inv_id,
            "subsystem": "configio_to_hardware_binding",
            "failure_pattern": "UNPARSEABLE_OR_INCOMPLETE",
            "affected_claim_ids": [],
            "affected_count": 0,
            "observed_facts": [f"parse_error: {parse_err}", f"phase={phase}"],
            "evidence_refs": [],
            "candidate_rule_name": "none",
            "candidate_rule_description": "No parseable DecoderRuleCandidate returned.",
            "proposed_inputs": [],
            "proposed_transformation": "NONE",
            "expected_outputs": [],
            "supporting_examples": [],
            "counterexamples": [],
            "ambiguities": [],
            "additional_evidence_needed": [],
            "tests_required": [],
            "scope": mach,
            "confidence": "LOW",
            "status": "INSUFFICIENT_EVIDENCE",
        }
    else:
        status = str(candidate.get("status") or "INSUFFICIENT_EVIDENCE")

    schema = validate_decoder_rule_candidate(candidate)
    (out_dir / "final_decoder_rule_candidate.json").write_text(
        json.dumps(candidate, indent=2), encoding="utf-8"
    )
    (out_dir / "schema_validation.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")

    usage_out = {
        "model": model,
        "reasoning_setting": os.environ.get("SITEFORGE_AI_REASONING") or "default/unspecified",
        "pricing_snapshot": snap,
        "request_count": request_count,
        "tool_rounds": tool_rounds,
        "tool_calls": tool_calls,
        "latency_ms": latency_ms,
        "usage_totals": usage_tot,
        "estimated_cost_by_request": cost_log,
        "estimated_session_cost_usd": cumulative_cost,
        "synthesis_trigger_usd": trigger,
        "hard_budget_usd": budget,
        "synthesis_triggered": synthesis_triggered,
        "final_phase": phase,
        "authority_hits": auth,
        "parse_error": parse_err,
        "cost_label": "estimated_session_cost_usd",
    }
    (out_dir / "usage.json").write_text(json.dumps(usage_out, indent=2), encoding="utf-8")

    summary = {
        "investigation_id": inv_id,
        "machine": mach,
        "project": proj,
        "final_status": status,
        "candidate_rule_name": candidate.get("candidate_rule_name"),
        "candidate_rule_description": candidate.get("candidate_rule_description"),
        "confidence": candidate.get("confidence"),
        "schema_ok": schema.get("ok"),
        "schema_reasons": schema.get("reasons"),
        "tools_called": [t.get("name") for t in transcript if t.get("event") == "tool_call"],
        "tool_call_count": tool_calls,
        "tool_rounds": tool_rounds,
        "request_count": request_count,
        "model": model,
        "latency_ms": latency_ms,
        "estimated_session_cost_usd": cumulative_cost,
        "synthesis_triggered": synthesis_triggered,
        "implemented_rule": False,
        "compiler_touched": False,
        "live_api_called": True,
        "supporting_examples": candidate.get("supporting_examples"),
        "counterexamples": candidate.get("counterexamples"),
        "ambiguities": candidate.get("ambiguities"),
        "additional_evidence_needed": candidate.get("additional_evidence_needed"),
        "tests_required": candidate.get("tests_required"),
        "observed_facts": candidate.get("observed_facts"),
        "evidence_refs": candidate.get("evidence_refs"),
        "proposed_transformation": candidate.get("proposed_transformation"),
    }
    (out_dir / "investigation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return {"ok": True, "summary": summary, "candidate": candidate, "usage": usage_out, "out_dir": str(out_dir)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare-only", action="store_true")
    ap.add_argument("--reclassify-r1", action="store_true")
    ap.add_argument("--offline-precheck", action="store_true")
    ap.add_argument("--run-dir", type=Path, default=REPO_ROOT / "workspace/_mscatl_peek/MSCATL_CP3/RUN")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "exports/ai-io/investigations/MSCATL_BINDING_001_R2",
    )
    args = ap.parse_args(argv)

    if args.reclassify_r1:
        note = reclassify_r1_session(
            REPO_ROOT / "exports/ai-io/investigations/MSCATL_BINDING_001"
        )
        print(json.dumps(note, indent=2))
        return 0

    from fortna_configio_binding_trace import (
        build_mscatl_binding_dossier,
        build_mscatl_blind_packet,
        build_mscatl_investigation_packet,
    )
    from fortna_rack_discovery import discover_racks
    from fortna_ai_readonly_tools import SiteForgeReadOnlyContext, invoke_tool

    dossier = build_mscatl_binding_dossier(args.run_dir, "MSCATL_CP3")
    inv = REPO_ROOT / "exports/ai-io/investigations"
    inv.mkdir(parents=True, exist_ok=True)
    (inv / "mscatl_binding_dossier.json").write_text(json.dumps(dossier, indent=2), encoding="utf-8")
    eng = build_mscatl_investigation_packet(dossier)
    (inv / "mscatl_binding_investigation_packet.json").write_text(json.dumps(eng, indent=2), encoding="utf-8")
    blind = build_mscatl_blind_packet(dossier)
    # Refresh tools list in blind packet
    blind["available_read_only_tools"] = INVESTIGATOR_TOOLS
    (inv / "mscatl_binding_blind_packet.json").write_text(json.dumps(blind, indent=2), encoding="utf-8")

    ss = dossier["site_summary"]
    gate = (
        ss.get("physical_claims") == 256
        and ss.get("proven") == 0
        and ss.get("needs_resolution") == 256
        and ss.get("physical_resolution_failure") == 256
        and ss.get("conservation") == "PASS"
        and ss.get("evidence_status") == "NEEDS_RESOLUTION"
    )
    print(json.dumps({"packet_gate_pass": gate, "site_summary": ss}, indent=2))
    if not gate:
        return 2

    if args.offline_precheck or args.prepare_only:
        disc = discover_racks(args.run_dir, "MSCATL_CP3")
        ctx = SiteForgeReadOnlyContext(args.run_dir, "MSCATL_CP3", project="MSCATL_CP3")
        pre = {
            "racks": [
                {
                    "provisional": r["provisional_display_name"],
                    "canonical_adapter_id": r["canonical_adapter_id"],
                    "aliases": r["source_aliases"],
                    "ip": r["ip_address"],
                    "catalog": r["catalog_number"],
                    "family": r["hardware_family"],
                    "modules": [
                        {
                            "slot": m["physical_slot"],
                            "catalog": m["catalog_number"],
                            "ib": m["input_bank"],
                            "ob": m["output_bank"],
                            "di": m["data_index"],
                            "status": m["status"],
                        }
                        for m in r["modules"]
                    ],
                    "unplaced": len(r.get("unplaced_modules") or []),
                }
                for r in disc.get("racks") or []
            ],
            "suffix_analysis": disc.get("numeric_suffix_analysis"),
            "cluster_summary": invoke_tool(ctx, "get_configio_binding_cluster_summary"),
            "eip_bank_map_count": invoke_tool(ctx, "get_eip_bank_map").get("count"),
            "word_700_trace_final": invoke_tool(ctx, "get_configio_binding_trace", word=700).get("final"),
            "adapter_modules_example": invoke_tool(
                ctx,
                "get_adapter_modules",
                adapter_name=((disc.get("racks") or [{}])[0].get("source_aliases") or ["?"])[0],
            ).get("ok"),
        }
        outp = REPO_ROOT / "exports/ai-io/audits/mscatl_rack_discovery_precheck.json"
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps({"discovery": disc, "precheck": pre}, indent=2, default=str), encoding="utf-8")
        print(json.dumps({"offline_precheck": True, "out": str(outp), "racks": pre["racks"], "suffix": pre["suffix_analysis"].get("conclusion"), "clusters": pre["cluster_summary"].get("root_cause_clusters"), "word_700": pre["word_700_trace_final"]}, indent=2, default=str))
        if args.prepare_only:
            return 0
        if args.offline_precheck and not args.prepare_only:
            # allow chaining to live if not prepare-only exclusive — but CLI uses flags separately
            pass

    if args.prepare_only:
        return 0
    if args.offline_precheck:
        return 0

    result = run_investigation(run_dir=args.run_dir, blind_packet=blind, out_dir=args.out_dir)
    print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

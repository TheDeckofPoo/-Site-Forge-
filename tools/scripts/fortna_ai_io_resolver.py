#!/usr/bin/env python3
"""OpenAI-backed I/O evidence resolver (advisory sidecar).

Uses OPENAI_API_KEY + SITEFORGE_AI_MODEL (default gpt-5.6-terra).
Structured JSON only — never writes L5X.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

DEFAULT_MODEL = "gpt-5.6-terra"

# Strict JSON schema for Responses API structured output
AI_IO_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "project": {"type": "string"},
        "machine": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "claim_id": {"type": "string"},
                    "logical_name": {"type": "string"},
                    "physical_endpoint": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "adapter": {"type": "string"},
                            "family": {"type": "string"},
                            "slot": {"type": "integer"},
                            "direction": {"type": "string", "enum": ["I", "O"]},
                            "data_index": {"type": "integer"},
                            "bit": {"type": "integer"},
                            "channel": {"type": "string"},
                        },
                        "required": [
                            "adapter",
                            "family",
                            "slot",
                            "direction",
                            "data_index",
                            "bit",
                            "channel",
                        ],
                    },
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "source": {"type": "string"},
                                "row": {"type": "integer"},
                                "fact": {"type": "string"},
                            },
                            "required": ["source", "row", "fact"],
                        },
                    },
                    "proposal_status": {
                        "type": "string",
                        "enum": ["PROVEN", "DERIVED", "REVIEW_REQUIRED", "UNKNOWN"],
                    },
                    "ambiguity": {"type": "array", "items": {"type": "string"}},
                    "explanation": {"type": "string"},
                },
                "required": [
                    "claim_id",
                    "logical_name",
                    "physical_endpoint",
                    "evidence",
                    "proposal_status",
                    "ambiguity",
                    "explanation",
                ],
            },
        },
        "unresolved": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "claim_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["claim_id", "reason"],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["project", "machine", "claims", "unresolved", "warnings"],
}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _model_name() -> str:
    return (os.environ.get("SITEFORGE_AI_MODEL") or DEFAULT_MODEL).strip()


def api_key_available() -> bool:
    """Presence-only check (legacy). Prefer check_openai_api_health()."""
    return bool((os.environ.get("OPENAI_API_KEY") or "").strip())


def check_openai_api_health(
    *,
    http_get: Any | None = None,
    timeout_s: float = 15.0,
) -> dict[str, Any]:
    """ORI-038: authentication-aware OpenAI health check.

    Does NOT treat env-var presence as authenticity. Never logs/returns the key.
    http_get may be injected for unit tests (signature: (url, headers, timeout) -> response).
    """
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    model = _model_name()
    base = {
        "ok": True,
        "provider": "openai",
        "key_present": bool(key),
        "authenticated": False,
        "model_available": False,
        "configured_model": model,
        "api_available": False,
        "error_type": None,
        "error_message": None,
    }
    if not key:
        base["error_type"] = "KEY_MISSING"
        base["error_message"] = "OPENAI_API_KEY not set"
        return base

    url = "https://api.openai.com/v1/models"
    headers = {"Authorization": f"Bearer {key}"}

    try:
        if http_get is not None:
            resp = http_get(url, headers, timeout_s)
            status = int(getattr(resp, "status_code", None) or resp.get("status_code"))
            body = getattr(resp, "json", None)
            data = body() if callable(body) else (resp.get("json") if isinstance(resp, dict) else {})
        else:
            try:
                import urllib.request

                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=timeout_s) as r:  # noqa: S310
                    status = int(getattr(r, "status", 200) or 200)
                    raw = r.read().decode("utf-8", errors="replace")
                    data = json.loads(raw) if raw else {}
            except Exception as exc:  # urllib errors
                # Try to extract HTTP status from HTTPError
                status = int(getattr(exc, "code", 0) or 0)
                data = {}
                if status == 401:
                    base["error_type"] = "AUTHENTICATION_FAILED"
                    base["error_message"] = "OpenAI authentication failed (401)"
                    return base
                if status == 403:
                    base["error_type"] = "AUTHENTICATION_FAILED"
                    base["error_message"] = "OpenAI authentication forbidden (403)"
                    return base
                base["error_type"] = "NETWORK_ERROR"
                base["error_message"] = f"OpenAI models request failed: {type(exc).__name__}"
                return base
    except Exception as exc:
        base["error_type"] = "NETWORK_ERROR"
        base["error_message"] = f"OpenAI health check error: {type(exc).__name__}"
        return base

    if status == 401 or status == 403:
        base["error_type"] = "AUTHENTICATION_FAILED"
        base["error_message"] = f"OpenAI authentication failed ({status})"
        return base
    if status < 200 or status >= 300:
        base["error_type"] = "HTTP_ERROR"
        base["error_message"] = f"OpenAI models HTTP {status}"
        return base

    base["authenticated"] = True
    models = []
    if isinstance(data, dict):
        models = [str(m.get("id") or "") for m in (data.get("data") or []) if isinstance(m, dict)]
    model_ids = {m for m in models if m}
    base["model_available"] = (not model) or (model in model_ids) or any(
        model.startswith(m) or m.startswith(model) for m in model_ids if m
    )
    if model and not base["model_available"]:
        base["error_type"] = "MODEL_UNAVAILABLE"
        base["error_message"] = f"configured model {model!r} not listed by provider"
    else:
        base["api_available"] = True
        base["error_type"] = None
        base["error_message"] = None
    return base


def build_ai_prompt(evidence: dict[str, Any], *, analyze_all: bool = False) -> str:
    """Focus AI on unresolved/review points; include known-good examples."""
    raw = evidence.get("raw_claims") or []
    unresolved = evidence.get("unresolved_points") or []
    conflicts = evidence.get("conflicts") or {}
    adapters = (evidence.get("eipcfg") or {}).get("adapters") or []
    configio = evidence.get("configio") or []

    # Known-good examples: first few ASSIGNED-looking claims from conveyor that are NOT unresolved
    unresolved_ids = {u.get("claim_id") for u in unresolved if u.get("claim_id")}
    examples = [c for c in raw if c.get("claim_id") not in unresolved_ids][:12]

    focus = unresolved
    if analyze_all:
        focus = [
            {
                "claim_id": c.get("claim_id"),
                "claim_name": c.get("io_name"),
                "word": c.get("word"),
                "bit": c.get("bit"),
                "disposition": "ANALYZE_ALL",
            }
            for c in raw
        ]

    payload = {
        "instructions": [
            "You are Site Forge I/O evidence interpreter.",
            "Propose physical endpoints ONLY from the provided evidence.",
            "Use proposal_status in {PROVEN, DERIVED, REVIEW_REQUIRED, UNKNOWN} — never GUESSED.",
            "Cite real Conveyor.asc / Configio.asc row numbers and facts that appear in evidence.",
            "Do not invent adapters, slots, channels, or source rows.",
            "Do not use foreign-machine evidence.",
            "Prefer focusing on unresolved/conflict claims.",
        ],
        "project": evidence.get("project"),
        "machine": evidence.get("machine"),
        "adapters": adapters,
        "configio_sample": configio[:120],
        "known_good_examples": examples,
        "focus_claims": focus[:200],
        "conflict_channels": list(conflicts.items())[:40],
        "conservation_counts": evidence.get("conservation_counts"),
    }
    return (
        "Return structured JSON matching the schema. "
        "Resolve focus_claims using adapters + configio + conveyor evidence.\n\n"
        + json.dumps(payload, indent=2)
    )


def call_openai_resolver(
    evidence: dict[str, Any],
    *,
    analyze_all: bool = False,
    mock_response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call OpenAI Responses API or return mock_response for tests."""
    started = time.perf_counter()
    if mock_response is not None:
        return {
            "ok": True,
            "mode": "mock",
            "model": "mock",
            "latency_ms": 0,
            "usage": {},
            "response": mock_response,
        }

    if not api_key_available():
        return {
            "ok": False,
            "error": "OPENAI_API_KEY not set — AI I/O resolver unavailable",
            "mode": "unavailable",
            "latency_ms": 0,
            "usage": {},
            "response": None,
        }

    prompt = build_ai_prompt(evidence, analyze_all=analyze_all)
    model = _model_name()
    try:
        from openai import OpenAI
    except Exception as exc:
        return {
            "ok": False,
            "error": f"openai SDK not installed: {exc}",
            "mode": "unavailable",
            "latency_ms": 0,
            "usage": {},
            "response": None,
        }

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    try:
        # Responses API with structured JSON schema
        resp = client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You map Fortna RUN I/O claims to physical endpoints. "
                        "Only use provided evidence. Never invent adapters or rows."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "siteforge_ai_io_response",
                    "strict": True,
                    "schema": AI_IO_RESPONSE_SCHEMA,
                }
            },
        )
        latency = round((time.perf_counter() - started) * 1000, 1)
        text = getattr(resp, "output_text", None) or ""
        if not text:
            # Fallback: gather text from output items
            chunks = []
            for item in getattr(resp, "output", None) or []:
                for c in getattr(item, "content", None) or []:
                    t = getattr(c, "text", None)
                    if t:
                        chunks.append(t)
            text = "".join(chunks)
        parsed = json.loads(text) if text else None
        if not isinstance(parsed, dict):
            return {
                "ok": False,
                "error": "malformed AI response (not a JSON object)",
                "mode": "openai",
                "model": model,
                "latency_ms": latency,
                "usage": _usage_dict(resp),
                "response": None,
                "raw_text": text[:2000],
            }
        return {
            "ok": True,
            "mode": "openai",
            "model": model,
            "latency_ms": latency,
            "usage": _usage_dict(resp),
            "response": parsed,
        }
    except Exception as exc:
        latency = round((time.perf_counter() - started) * 1000, 1)
        return {
            "ok": False,
            "error": str(exc),
            "mode": "openai",
            "model": model,
            "latency_ms": latency,
            "usage": {},
            "response": None,
        }


def _usage_dict(resp: Any) -> dict[str, Any]:
    usage = getattr(resp, "usage", None)
    if not usage:
        return {}
    if isinstance(usage, dict):
        return usage
    return {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="OpenAI I/O resolver (advisory)")
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--analyze-all", action="store_true")
    ap.add_argument("--mock", type=Path, default=None, help="Use mock JSON response (tests)")
    args = ap.parse_args(argv)
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    mock = None
    if args.mock:
        mock = json.loads(args.mock.read_text(encoding="utf-8"))
    result = call_openai_resolver(evidence, analyze_all=args.analyze_all, mock_response=mock)
    out = args.out or args.evidence.with_name("ai_response.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"ok": result.get("ok"), "out": str(out), "error": result.get("error"), "latency_ms": result.get("latency_ms")}, indent=2))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())

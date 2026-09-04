#!/usr/bin/env python3
"""
Site Twin bridge: Site Forge gaps ↔ PRISM retrieval ↔ SpaceXAI propose-patches.

Commands:
  load-gaps [--site SITE] [--export-dir DIR]
  search QUERY [--limit N] [--system SYS]
  propose [--gaps PATH|JSON] [--limit-gaps N]
  apply-patches --patches PATH|JSON [--workbook PATH]

SpaceXAI (xAI): XAI_API_KEY + https://api.x.ai/v1 — never writes L5X.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from fortna_prism_ingest import _prism_root, _site_dir  # noqa: E402
from fortna_source_id import export_label_from_meta, safe_fs_name  # noqa: E402
from fortna_workbook import (  # noqa: E402
    DEFAULT_WORKBOOK_PATH,
    load_workbook,
    save_workbook,
)

XAI_BASE = "https://api.x.ai/v1"
XAI_MODEL = os.environ.get("XAI_MODEL", "grok-4.5").strip() or "grok-4.5"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _active_site(explicit: str = "") -> str:
    if (explicit or "").strip():
        return safe_fs_name(explicit.strip())
    return safe_fs_name(export_label_from_meta() or "Autogen_Project")


def _latest_export_gaps() -> Path | None:
    root = REPO_ROOT / "exports" / "autogen"
    if not root.is_dir():
        return None
    cands = sorted(root.glob("*/twin_gaps.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0] if cands else None


def load_gaps(*, site: str = "", export_dir: str = "") -> dict:
    """Prefer export twin_gaps.json, else PRISM twin/gaps.json."""
    site_name = _active_site(site)
    paths: list[Path] = []
    if export_dir:
        paths.append(Path(export_dir) / "twin_gaps.json")
    latest = _latest_export_gaps()
    if latest:
        paths.append(latest)
    paths.append(_site_dir(_prism_root(), site_name) / "twin" / "gaps.json")
    paths.append(
        _site_dir(_prism_root(), site_name) / "generated" / "transport" / "twin_gaps.json"
    )

    for p in paths:
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return {"ok": False, "error": f"Bad gaps JSON {p}: {exc}"}
            peers_path = _site_dir(_prism_root(), site_name) / "twin" / "peers.json"
            peers = []
            if peers_path.is_file():
                try:
                    peers = (json.loads(peers_path.read_text(encoding="utf-8")) or {}).get(
                        "peers"
                    ) or []
                except (OSError, json.JSONDecodeError):
                    peers = []
            return {
                "ok": True,
                "site": site_name,
                "source": str(p),
                "gaps": data.get("gaps") or [],
                "gap_count": data.get("gap_count") or len(data.get("gaps") or []),
                "by_type": data.get("by_type") or {},
                "payload": data,
                "peers": peers,
            }
    return {
        "ok": True,
        "site": site_name,
        "source": "",
        "gaps": [],
        "gap_count": 0,
        "by_type": {},
        "payload": {},
        "peers": [],
        "message": "No twin_gaps.json yet — Export L5X Package once to create gaps.",
    }


def prism_search(
    query: str,
    *,
    limit: int = 5,
    system: str = "",
    status: str = "production",
) -> dict:
    prism = _prism_root()
    entry = prism / "Rockwell-Vector-Database.py"
    if not entry.is_file():
        return {"ok": False, "error": f"PRISM CLI missing: {entry}"}
    cmd = [
        sys.executable,
        str(entry),
        "search",
        query,
        "--limit",
        str(max(1, min(limit, 20))),
        "--json",
        "--status",
        status or "production",
    ]
    if system:
        cmd.extend(["--system", system])
    try:
        r = subprocess.run(
            cmd,
            cwd=str(prism),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    out = (r.stdout or "").strip()
    hits = []
    if out:
        try:
            start = out.find("[")
            hits = json.loads(out[start:] if start >= 0 else out)
        except json.JSONDecodeError:
            return {
                "ok": False,
                "error": "PRISM search returned non-JSON",
                "stderr": (r.stderr or "")[-400:],
                "stdout_tail": out[-400:],
            }
    # Slim for UI
    slim = []
    for h in hits if isinstance(hits, list) else []:
        meta = h.get("metadata") or {}
        text = h.get("text") or ""
        slim.append(
            {
                "id": h.get("id"),
                "score": h.get("score"),
                "snippet": text[:500],
                "path": meta.get("path") or "",
                "system": meta.get("system") or meta.get("controller") or "",
                "source": meta.get("source") or "",
            }
        )
    return {
        "ok": r.returncode == 0,
        "query": query,
        "hits": slim,
        "count": len(slim),
        "stderr_tail": ((r.stderr or "")[-300:] if r.returncode else ""),
    }


def _xai_key() -> str:
    return (os.environ.get("XAI_API_KEY") or os.environ.get("xai_api_key") or "").strip()


def _call_spacexai(system: str, user: str) -> dict:
    key = _xai_key()
    if not key:
        return {"ok": False, "error": "missing_xai_api_key"}
    body = {
        "model": XAI_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    req = urllib.request.Request(
        f"{XAI_BASE}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")[:500]
        return {"ok": False, "error": f"SpaceXAI HTTP {exc.code}: {err_body}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    try:
        text = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return {"ok": False, "error": "Unexpected SpaceXAI response shape", "raw": raw}
    return {"ok": True, "text": text, "model": XAI_MODEL}


def _extract_json_obj(text: str) -> dict | list | None:
    if not text:
        return None
    text = text.strip()
    # fenced
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # first { … }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _heuristic_patches(gaps: list[dict], hits_by_gap: dict) -> list[dict]:
    """PRISM-only fallback when no XAI key — suggest PE maps from search snippets."""
    patches = []
    pe_re = re.compile(r"\b((?:EZ)?PE[A-Z0-9_-]*[PJF]\d*)\b", re.I)
    for i, g in enumerate(gaps):
        gid = g.get("id") or f"gap_{i}"
        hits = hits_by_gap.get(gid) or []
        found = []
        for h in hits:
            for m in pe_re.findall(h.get("snippet") or ""):
                u = m.upper()
                if u not in found:
                    found.append(u)
        if g.get("type") == "missing_exit_pe" and found:
            patches.append(
                {
                    "id": f"patch_{i}_exit",
                    "gap_id": gid,
                    "target": "workbook",
                    "op": "set_exit_pe",
                    "conveyor": g.get("conveyor") or "",
                    "value": found[0],
                    "cite": (hits[0].get("path") if hits else "") or "prism_search",
                    "confidence": 0.35,
                    "source": "prism_heuristic",
                    "rationale": f"Nearest PE-like tag in PRISM hit: {found[0]}",
                    "approved": False,
                }
            )
        elif g.get("type") in ("pe_not_in_run_io", "merge_pe_not_in_run_io"):
            patches.append(
                {
                    "id": f"patch_{i}_note",
                    "gap_id": gid,
                    "target": "workbook",
                    "op": "note_only",
                    "conveyor": g.get("conveyor") or g.get("merge") or "",
                    "value": g.get("pe") or "",
                    "cite": (hits[0].get("path") if hits else "") or "",
                    "confidence": 0.2,
                    "source": "prism_heuristic",
                    "rationale": (
                        "PE not in active RUN IO — bind a real SHIP PE in Transport roles "
                        "or enable create-missing-PE on merge. AI needs XAI_API_KEY for mapped suggestions."
                    ),
                    "approved": False,
                }
            )
        elif g.get("type") == "merge_pe_blank" and found:
            field = g.get("field") or "pe_a"
            patches.append(
                {
                    "id": f"patch_{i}_merge",
                    "gap_id": gid,
                    "target": "workbook",
                    "op": "set_merge_pe",
                    "merge": g.get("merge") or "",
                    "field": field,
                    "value": found[0],
                    "cite": (hits[0].get("path") if hits else "") or "prism_search",
                    "confidence": 0.3,
                    "source": "prism_heuristic",
                    "rationale": f"Suggest {field}={found[0]} from PRISM snippet",
                    "approved": False,
                }
            )
    return patches


def propose(
    *,
    site: str = "",
    gaps_path: str = "",
    gap_ids: list[str] | None = None,
    limit_gaps: int = 8,
) -> dict:
    loaded = load_gaps(site=site)
    if not loaded.get("ok"):
        return loaded
    gaps = list(loaded.get("gaps") or [])
    if gaps_path:
        p = Path(gaps_path)
        if p.is_file():
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
                gaps = payload.get("gaps") or gaps
            except (OSError, json.JSONDecodeError) as exc:
                return {"ok": False, "error": str(exc)}

    # Attach stable ids
    for i, g in enumerate(gaps):
        g.setdefault("id", f"gap_{i}")

    if gap_ids:
        want = set(gap_ids)
        gaps = [g for g in gaps if g.get("id") in want]
    gaps = gaps[: max(1, min(limit_gaps, 20))]

    hits_by_gap: dict[str, list] = {}
    all_hits = []
    for g in gaps:
        q_parts = [
            g.get("type") or "",
            g.get("conveyor") or g.get("merge") or "",
            g.get("pe") or "",
            "Fortna photoeye Fast_Conv Slow_Jam Merge_2to1",
        ]
        q = " ".join(x for x in q_parts if x)
        sr = prism_search(q, limit=4)
        hits = sr.get("hits") or []
        hits_by_gap[g["id"]] = hits
        all_hits.extend(hits)

    system = (
        "You are a Fortna PLC Site Forge assistant. "
        "Sealed AOIs (Fast_Conv, Slow_Jam, Full_PE, Merge_2to1, Slow_Flt) must NOT be rewritten. "
        "Propose ONLY workbook JSON patches to fill gaps. "
        "Return a single JSON object: {\"patches\":[...]} where each patch has: "
        "id, gap_id, target=\"workbook\", op, conveyor?, merge?, field?, value, cite, confidence (0-1), rationale. "
        "Allowed op: set_exit_pe, set_add_pe, add_jam_pe, add_full_pe, set_merge_pe, note_only. "
        "If unsure, use note_only. Cite PRISM paths from the context."
    )
    user = json.dumps(
        {
            "site": loaded.get("site"),
            "gaps": gaps,
            "prism_hits_by_gap": hits_by_gap,
            "peers": loaded.get("peers") or [],
        },
        indent=2,
    )[:120000]

    ai = _call_spacexai(system, user)
    patches: list[dict] = []
    mode = "spacexai"
    note = ""
    if not ai.get("ok"):
        mode = "prism_heuristic"
        patches = _heuristic_patches(gaps, hits_by_gap)
        note = ai.get("error") or "SpaceXAI unavailable"
    else:
        parsed = _extract_json_obj(ai.get("text") or "")
        if isinstance(parsed, dict):
            patches = parsed.get("patches") or []
        elif isinstance(parsed, list):
            patches = parsed
        else:
            mode = "prism_heuristic"
            patches = _heuristic_patches(gaps, hits_by_gap)
            note = "SpaceXAI returned non-JSON — fell back to PRISM heuristics"

    for i, p in enumerate(patches):
        if not isinstance(p, dict):
            continue
        p.setdefault("id", f"patch_{i}")
        p.setdefault("approved", False)
        p.setdefault("source", mode)
        p.setdefault("target", "workbook")

    out = {
        "ok": True,
        "site": loaded.get("site"),
        "mode": mode,
        "model": XAI_MODEL if mode == "spacexai" else None,
        "gap_count": len(gaps),
        "patch_count": len(patches),
        "patches": [p for p in patches if isinstance(p, dict)],
        "prism_hit_count": len(all_hits),
        "note": note
        or (
            "Set XAI_API_KEY for SpaceXAI proposals; PRISM heuristics used as fallback."
            if mode != "spacexai"
            else "Review patches — Approve then Apply. Does not write L5X."
        ),
        "generated_utc": _utc(),
    }
    # Persist last propose under exports for audit
    try:
        dest = REPO_ROOT / "exports" / "twin"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "last_propose.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    except OSError:
        pass
    return out


def apply_patches(
    patches: list[dict],
    *,
    workbook_path: Path | None = None,
) -> dict:
    path = Path(workbook_path) if workbook_path else DEFAULT_WORKBOOK_PATH
    wb = load_workbook(path) or {"conveyors": [], "merges_2to1": [], "options": {}}
    by_name = {
        str(r.get("conveyor") or "").strip().upper(): r
        for r in (wb.get("conveyors") or [])
        if str(r.get("conveyor") or "").strip()
    }
    merges = list(wb.get("merges_2to1") or [])
    applied = []
    skipped = []

    def _row(conv: str) -> dict | None:
        return by_name.get((conv or "").strip().upper())

    for p in patches:
        if not isinstance(p, dict):
            continue
        if p.get("approved") is False:
            skipped.append({"id": p.get("id"), "reason": "not_approved"})
            continue
        op = (p.get("op") or "").strip()
        if op == "note_only":
            skipped.append({"id": p.get("id"), "reason": "note_only"})
            continue
        if op == "set_exit_pe":
            row = _row(p.get("conveyor") or "")
            if not row:
                skipped.append({"id": p.get("id"), "reason": "conveyor_not_found"})
                continue
            row["exit_pe_tag"] = str(p.get("value") or "").strip()
            row["edited"] = True
            applied.append(p.get("id"))
        elif op == "set_add_pe":
            row = _row(p.get("conveyor") or "")
            if not row:
                skipped.append({"id": p.get("id"), "reason": "conveyor_not_found"})
                continue
            row["add_pe_tag"] = str(p.get("value") or "").strip()
            row["edited"] = True
            applied.append(p.get("id"))
        elif op in ("add_jam_pe", "add_full_pe"):
            row = _row(p.get("conveyor") or "")
            if not row:
                skipped.append({"id": p.get("id"), "reason": "conveyor_not_found"})
                continue
            key = "jam_pe_tags" if op == "add_jam_pe" else "full_pe_tags"
            val = str(p.get("value") or "").strip()
            cur = [str(x).strip() for x in (row.get(key) or []) if str(x).strip()]
            if val and val not in cur:
                cur.append(val)
            row[key] = cur
            row["edited"] = True
            applied.append(p.get("id"))
        elif op == "set_merge_pe":
            mname = str(p.get("merge") or "").strip().upper()
            field = str(p.get("field") or "pe_a").strip()
            val = str(p.get("value") or "").strip()
            hit = None
            for m in merges:
                key = str(m.get("name") or m.get("discharge") or "").strip().upper()
                if key == mname:
                    hit = m
                    break
            if not hit or field not in ("pe_a", "pe_b", "pe_c", "jam_pe"):
                skipped.append({"id": p.get("id"), "reason": "merge_not_found"})
                continue
            hit[field] = val
            applied.append(p.get("id"))
        else:
            skipped.append({"id": p.get("id"), "reason": f"unknown_op:{op}"})

    wb["merges_2to1"] = merges
    saved = save_workbook(wb, path)
    return {
        "ok": True,
        "workbook_path": str(saved),
        "applied": applied,
        "skipped": skipped,
        "applied_count": len(applied),
        "message": (
            f"Applied {len(applied)} patch(es) to workbook. "
            "Export L5X Package to refresh Studio project."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("load-gaps")
    p1.add_argument("--site", default="")
    p1.add_argument("--export-dir", default="")

    p2 = sub.add_parser("search")
    p2.add_argument("query")
    p2.add_argument("--limit", type=int, default=5)
    p2.add_argument("--system", default="")

    p3 = sub.add_parser("propose")
    p3.add_argument("--site", default="")
    p3.add_argument("--gaps", default="", help="Optional twin_gaps.json path")
    p3.add_argument("--gap-ids", default="", help="Comma-separated gap ids")
    p3.add_argument("--limit-gaps", type=int, default=8)

    p4 = sub.add_parser("apply-patches")
    p4.add_argument("--patches", required=True, help="JSON file or inline JSON")
    p4.add_argument("--workbook", default="")

    args = ap.parse_args()
    if args.cmd == "load-gaps":
        print(json.dumps(load_gaps(site=args.site, export_dir=args.export_dir), indent=2))
        return 0
    if args.cmd == "search":
        print(json.dumps(prism_search(args.query, limit=args.limit, system=args.system), indent=2))
        return 0
    if args.cmd == "propose":
        ids = [x.strip() for x in (args.gap_ids or "").split(",") if x.strip()]
        print(
            json.dumps(
                propose(
                    site=args.site,
                    gaps_path=args.gaps,
                    gap_ids=ids or None,
                    limit_gaps=args.limit_gaps,
                ),
                indent=2,
            )
        )
        return 0
    if args.cmd == "apply-patches":
        raw = args.patches
        if Path(raw).is_file():
            payload = json.loads(Path(raw).read_text(encoding="utf-8"))
        else:
            payload = json.loads(raw)
        patches = payload.get("patches") if isinstance(payload, dict) else payload
        wb = Path(args.workbook) if args.workbook else None
        print(json.dumps(apply_patches(patches or [], workbook_path=wb), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

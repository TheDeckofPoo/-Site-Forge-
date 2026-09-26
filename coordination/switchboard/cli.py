"""Switchboard CLI: ``python -m coordination.switchboard <command>``.

Exit codes: 0 ok; 1 packet invalid/rejected or check failed; 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .reports import build_handoff, morning_brief, status_text
from .store import Store, dumps, load_json, validate_packet
from .validator import validate


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _prefix(store: Store) -> str:
    d = store.packets_dir.resolve()
    try:
        return str(d.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(d)


def _print_post(res: dict) -> int:
    if res["errors"]:
        print(f"INVALID {res['type'] or 'packet'} — not stored:")
        for e in res["errors"]:
            print(f"  - {e}")
        return 1
    print(f"{'ACCEPTED' if res['accepted'] else 'REJECTED'} {res['type']} → {res['stored']}")
    for f in res["flags"]:
        print(f"  [{f['severity']}] {f['code']}: {f['message']}")
    return 0 if res["accepted"] else 1


def cmd_status(store: Store, a) -> int:
    state, subs = store.load_state(), store.load_subsystems()
    if a.json:
        print(dumps({"current": state, "subsystems": subs}), end="")
    else:
        print(status_text(state, subs), end="")
    return 0


def cmd_validate(store: Store, a) -> int:
    rc = 0
    for path in a.packets:
        try:
            obj = load_json(path)
        except (OSError, json.JSONDecodeError) as e:
            print(f"INVALID {path}: {e}")
            rc = 1
            continue
        if a.type:
            t, errs = a.type, validate(obj, a.type)
        else:
            t, errs = validate_packet(obj)
        if errs:
            rc = 1
            print(f"INVALID {path} ({t or 'unknown'}):")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"VALID {path} ({t})")
    return rc


def cmd_post(store: Store, a, expected: str | None) -> int:
    rc = 0
    for path in a.packets:
        res = store.post(load_json(path), expected)
        rc = max(rc, _print_post(res))
    return rc


def cmd_new_mission(store: Store, a) -> int:
    state = store.load_state()
    cfg = store.config()
    base: dict = {}
    if a.from_handoff:
        h = load_json(a.from_handoff)
        base = dict(h.get("suggested_mission") or {})
        if not base:
            print("handoff has no suggested_mission (loop halted or owner is not an agent)")
            return 1
    m = {
        "packet_type": "mission",
        "mission_id": a.id or base.get("mission_id"),
        "title": a.title or base.get("title"),
        "created_at": a.created_at or _now(),
        "created_by": a.created_by,
        "assigned_to": a.assigned_to or base.get("assigned_to"),
        "repository": a.repository or base.get("repository") or state.get("repository") or cfg.get("repository"),
        "branch": a.branch or base.get("branch") or state.get("branch"),
        "required_start_sha": a.start_sha or base.get("required_start_sha") or state.get("latest_sha"),
        "scope": a.scope or base.get("scope") or [],
        "prohibited_scope": a.prohibited or [],
        "ori_ids": a.ori or base.get("ori_ids") or [],
        "acceptance_criteria": a.accept or base.get("acceptance_criteria") or [],
        "inputs": a.input or [],
        "artifacts": a.artifact or [],
        "authorization": {"granted_by": a.granted_by, "actions": a.action or [],
                          "push_branch": a.branch or base.get("branch") or state.get("branch")},
        "stop_conditions": a.stop or ["ENGINEER_DECISION_REQUIRED", "SHA mismatch", "dirty tree"],
        "expected_return": {"format": "coordination/switchboard/schema/result.schema.json"},
        "next_owner": a.next_owner or base.get("next_owner") or cfg.get("default_auditor", "Warden"),
    }
    if a.from_handoff:
        m["handoff_ref"] = str(a.from_handoff)
    if a.dry_run:
        errs = validate(m, "mission")
        print(dumps(m), end="")
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 1 if errs else 0
    if a.out:
        Path(a.out).write_text(dumps(m), encoding="utf-8")
    return _print_post(store.post(m, "mission"))


def cmd_next_handoff(store: Store, a) -> int:
    cfg = store.config()
    h = build_handoff(store.load_state(), _prefix(store),
                      cfg.get("default_implementer", "Anton"), cfg.get("default_auditor", "Warden"))
    errs = validate(h, "handoff")
    if errs:  # pragma: no cover - guards generator bugs
        print("generated handoff failed schema validation:", errs, file=sys.stderr)
        return 1
    text = dumps(h)
    if not a.no_write:
        store.handoffs_dir.mkdir(parents=True, exist_ok=True)
        out = store.handoffs_dir / f"{h['handoff_id']}.json"
        out.write_text(text, encoding="utf-8")
        print(f"# wrote {out}", file=sys.stderr)
    print(text, end="")
    return 0


def cmd_brief(store: Store, a) -> int:
    text = morning_brief(store.load_state(), _prefix(store), all_history=a.all, subsystems=store.load_subsystems())
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


def cmd_rebuild(store: Store, a) -> int:
    if a.check:
        diffs = store.check()
        if diffs:
            print("STATE DRIFT (differs from rebuild of packet history):")
            for d in diffs:
                print(f"  - {d}")
            return 1
        print(f"OK: state matches rebuild of {len(store.packet_files())} packet(s)")
        return 0
    eng = store.rebuild()
    print(f"rebuilt state from {len(store.packet_files())} packet(s); digest {eng.cur['history']['digest'][:16]}")
    return 0


def cmd_replay(store: Store, a) -> int:
    """Post every *.json in a fixture directory in filename order."""
    files = sorted(Path(a.dir).glob("*.json"))
    rc = 0
    for f in files:
        print(f"-- {f.name}")
        rc = max(rc, _print_post(store.post(load_json(f))))
    return 0 if not a.strict else rc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m coordination.switchboard",
                                description="SWITCHBOARD coordination/handoff data plane (no engineering decisions).")
    p.add_argument("--root", default=os.environ.get("SWITCHBOARD_ROOT"),
                   help="Switchboard root (packets/, state/, handoffs/). Default: coordination/switchboard")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="show current routing/state")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("validate", help="schema-validate packet file(s) without storing")
    s.add_argument("packets", nargs="+")
    s.add_argument("--type", choices=["mission", "result", "defect", "decision", "handoff", "state"])

    for name, help_ in (("post-result", "post a result packet"), ("post-mission", "post a mission packet file"),
                        ("post-defect", "register an ORI (defect packet, state OPEN)"),
                        ("decide", "post an engineer decision packet (Curtis only)")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("packets", nargs="+")

    s = sub.add_parser("new-mission", help="create + post a mission packet from flags or a handoff")
    s.add_argument("--from-handoff")
    s.add_argument("--id")
    s.add_argument("--title")
    s.add_argument("--assigned-to")
    s.add_argument("--created-by", default="Curtis")
    s.add_argument("--created-at")
    s.add_argument("--repository")
    s.add_argument("--branch")
    s.add_argument("--start-sha")
    s.add_argument("--ori", action="append")
    s.add_argument("--scope", action="append")
    s.add_argument("--prohibited", action="append")
    s.add_argument("--accept", action="append")
    s.add_argument("--input", action="append")
    s.add_argument("--artifact", action="append")
    s.add_argument("--stop", action="append")
    s.add_argument("--granted-by", default="Curtis")
    s.add_argument("--action", action="append")
    s.add_argument("--next-owner")
    s.add_argument("--out", help="also write the mission JSON here")
    s.add_argument("--dry-run", action="store_true", help="print, do not post")

    s = sub.add_parser("next-handoff", help="generate the handoff packet for the next owner")
    s.add_argument("--no-write", action="store_true")

    s = sub.add_parser("morning-brief", help="concise Night Shift brief")
    s.add_argument("--all", action="store_true", help="whole history instead of current shift")
    s.add_argument("--out")

    s = sub.add_parser("rebuild", help="rebuild state/ deterministically from packets/")
    s.add_argument("--check", action="store_true", help="exit 1 if committed state differs from rebuild")

    s = sub.add_parser("replay", help="post all packets in a fixture dir (filename order)")
    s.add_argument("dir")
    s.add_argument("--strict", action="store_true", help="exit 1 if any packet is invalid/rejected")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    store = Store(a.root)
    if a.cmd == "status":
        return cmd_status(store, a)
    if a.cmd == "validate":
        return cmd_validate(store, a)
    if a.cmd == "post-result":
        return cmd_post(store, a, "result")
    if a.cmd == "post-mission":
        return cmd_post(store, a, "mission")
    if a.cmd == "post-defect":
        return cmd_post(store, a, "defect")
    if a.cmd == "decide":
        return cmd_post(store, a, "decision")
    if a.cmd == "new-mission":
        return cmd_new_mission(store, a)
    if a.cmd == "next-handoff":
        return cmd_next_handoff(store, a)
    if a.cmd == "morning-brief":
        return cmd_brief(store, a)
    if a.cmd == "rebuild":
        return cmd_rebuild(store, a)
    if a.cmd == "replay":
        return cmd_replay(store, a)
    return 2  # pragma: no cover

"""Deterministic Switchboard state engine.

State is a pure function of (config, ordered packet history).  ``Engine.apply``
is fed packets in sequence order; there is no wall-clock input anywhere, so
``rebuild`` always reproduces the same state byte-for-byte.

Severity model for contradiction / integrity flags
--------------------------------------------------
REJECT  The whole packet is refused: it is kept in history for audit, but it
        changes no defect or mission state, and the Night Shift loop halts
        with next owner = Curtis.
BLOCK   The packet is accepted, but the specific disposition that could not
        be trusted is withheld (no state transition for that ORI) and the
        loop halts with next owner = Curtis.
WARN    The packet is accepted and applied; the flag is surfaced in status,
        handoff and morning brief.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

DEFECT_STATES = (
    "OPEN", "CLAIMED_FIXED", "WARDEN_VERIFIED", "REOPENED",
    "DEFERRED", "UNSUPPORTED", "LOCKED_REGRESSION",
)
SUBSYSTEM_STATES = ("DEVELOPMENT", "CANDIDATE_FOR_GRADUATION", "LOCKED", "REOPENED_BY_REGRESSION")
WORK_STATES = ("OPEN", "REOPENED")
CLOSED_STATES = ("WARDEN_VERIFIED", "LOCKED_REGRESSION", "DEFERRED", "UNSUPPORTED")

VERDICTS = ("PASS", "FAIL")
IMPLEMENTER_ONLY = ("FIXED", "PARTIAL", "PROPOSE_DEFER", "PROPOSE_UNSUPPORTED")

# code -> severity (documented in docs/SWITCHBOARD.md)
FLAG_SEVERITY = {
    # hard rejections
    "UNKNOWN_MISSION": "REJECT",
    "WRONG_MISSION_AGENT": "REJECT",
    "DUPLICATE_RESULT": "REJECT",
    "SHA_MISMATCH": "REJECT",
    "BRANCH_MISMATCH": "REJECT",
    "UNAUTHORIZED_VERIFICATION": "REJECT",
    "INDEPENDENCE_VIOLATION": "REJECT",
    "MISSING_VERIFIED_SHA": "REJECT",
    "DUPLICATE_MISSION": "REJECT",
    "UNKNOWN_AGENT": "REJECT",
    "DUPLICATE_ORI": "REJECT",
    "INVALID_REGISTRATION_STATE": "REJECT",
    "UNAUTHORIZED_DECISION": "REJECT",
    # blocking
    "VERIFIED_SHA_MISMATCH": "BLOCK",
    "VERIFY_WITHOUT_CLAIM": "BLOCK",
    "UNKNOWN_ORI": "BLOCK",
    "DIRTY_TREE": "BLOCK",
    # warnings
    "IMPLEMENTER_AUDITOR_CONFLICT": "WARN",
    "MISSING_ARTIFACT": "WARN",
    "MISSING_TESTS": "WARN",
    "TESTS_FAILING": "WARN",
    "NOT_PUSHED": "WARN",
    "ORI_OUT_OF_SCOPE": "WARN",
    "MISSING_DISPOSITION": "WARN",
    "CLAIM_ON_CLOSED_STATE": "WARN",
    "RECLAIM": "WARN",
    "REGRESSION": "WARN",
    "AGENT_BLOCKED": "WARN",
    "AUDITOR_CHANGED_FILES": "WARN",
    "DUPLICATE_NEW_ORI": "WARN",
    "MISSION_UNKNOWN_ORI": "WARN",
    "MISSION_WHILE_HALTED": "WARN",
    "LOCK_WITH_OPEN_ORIS": "WARN",
}


def short(sha: str | None) -> str:
    return sha[:7] if sha else "—"


def clip(text: str | None, n: int = 48) -> str:
    """Short reproducer label: text before ':' when that is a short handle (e.g. 'TPNA1')."""
    if not text:
        return "—"
    head = text.split(":", 1)[0].strip()
    if 0 < len(head) <= 24 and head != text:
        return head
    return text if len(text) <= n else text[: n - 1] + "…"


def sha_eq(a: str | None, b: str | None) -> bool:
    """SHA equality allowing abbreviated (>=7 hex) forms."""
    if not a or not b:
        return False
    a, b = a.lower(), b.lower()
    n = min(len(a), len(b))
    return n >= 7 and a[:n] == b[:n]


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def artifact_path(a: Any) -> str:
    return a["path"] if isinstance(a, dict) else a


class Engine:
    def __init__(self, config: dict):
        self.config = config
        ns = config.get("night_shift", {})
        self._digest = hashlib.sha256()
        self.locks: dict[str, bool] = {}
        self.regressed: dict[str, bool] = {}
        seed = {k: v for k, v in config.get("subsystem_seed", {}).items() if not k.startswith("_")}
        self.subsystem_names = list(seed)
        self.cur: dict[str, Any] = {
            "kind": "switchboard.current",
            "schema_version": 1,
            "history": {"packet_count": 0, "last_packet": None, "last_timestamp": None,
                        "digest": self._digest.hexdigest()},
            "repository": config.get("repository"),
            "branch": None,
            "latest_sha": None,
            "night_shift": {
                "max_cycles": int(ns.get("max_cycles", 1)),
                "cycles_used": 0,
                "budget_limit": ns.get("budget_limit"),
                "budget_used": 0,
                "stop_on_engineer_decision": bool(ns.get("stop_on_engineer_decision", True)),
                "stop_on_dirty_tree": bool(ns.get("stop_on_dirty_tree", True)),
                "stop_on_sha_mismatch": bool(ns.get("stop_on_sha_mismatch", True)),
                "loop_status": "RUNNING",
                "halt_reasons": [],
                "starting_sha": None,
                "ending_sha": None,
                "shift_started_seq": 0,
            },
            "missions": {},
            "results": [],
            "defects": {},
            "flags": [],
            "engineer_decisions_required": [],
            "next_owner": config.get("default_engineer", "Curtis"),
            "next_action": "No packets yet. Register ORIs (defect packets) and post a first mission.",
            "recommended_after_review": None,
            "transitions": [],
        }
        self._route()

    # ------------------------------------------------------------------ roles
    def role(self, agent: str) -> str:
        return self.config.get("roles", {}).get(agent, {}).get("role", "UNKNOWN")

    def is_verifier(self, agent: str) -> bool:
        return self.role(agent) in self.config.get("verification_roles", ["AUDITOR"])

    def is_engineer(self, agent: str) -> bool:
        return self.role(agent) in self.config.get("engineer_roles", ["ENGINEER"])

    @property
    def implementer(self) -> str:
        return self.config.get("default_implementer", "Anton")

    @property
    def auditor(self) -> str:
        return self.config.get("default_auditor", "Warden")

    @property
    def engineer(self) -> str:
        return self.config.get("default_engineer", "Curtis")

    # ---------------------------------------------------------------- helpers
    def _flag(self, out: list, code: str, message: str, *, seq: int, packet: str,
              mission_id: str | None = None, ori_id: str | None = None) -> dict:
        f = {"code": code, "severity": FLAG_SEVERITY[code], "message": message,
             "packet": packet, "mission_id": mission_id, "ori_id": ori_id, "seq": seq}
        out.append(f)
        return f

    def _halt(self, reason: str) -> None:
        ns = self.cur["night_shift"]
        if reason not in ns["halt_reasons"]:
            ns["halt_reasons"].append(reason)
        ns["loop_status"] = "HALTED"

    def _transition(self, d: dict, to: str, *, seq: int, packet: str, by: str, owner: str,
                    next_action: str, note: str = "") -> None:
        frm = d.get("state")
        d["state"] = to
        d["current_owner"] = owner
        d["next_action"] = next_action
        entry = {"seq": seq, "from": frm, "to": to, "by": by, "packet": packet, "owner": owner}
        if note:
            entry["note"] = note
        d.setdefault("history", []).append(entry)
        self.cur["transitions"].append({"ori_id": d["ori_id"], **entry})
        sub = d.get("subsystem")
        if sub and sub not in self.subsystem_names:
            self.subsystem_names.append(sub)
        if to == "REOPENED" or (frm is None and to == "OPEN"):
            if sub and self.locks.get(sub):
                self.regressed[sub] = True

    # ------------------------------------------------------------------ apply
    def apply(self, seq: int, name: str, packet: dict) -> list[dict]:
        """Apply one schema-valid packet. Returns flags raised by it."""
        self._digest.update(name.encode() + b"\n" + canonical(packet).encode() + b"\n")
        h = self.cur["history"]
        h["packet_count"] += 1
        h["last_packet"] = name
        ts = (packet.get("created_at") or packet.get("submitted_at") or packet.get("decided_at")
              or packet.get("discovered_at"))
        if ts:
            h["last_timestamp"] = ts
        h["digest"] = self._digest.hexdigest()

        kind = packet.get("packet_type")
        flags: list[dict] = []
        if kind == "defect":
            self._apply_defect(seq, name, packet, flags)
        elif kind == "mission":
            self._apply_mission(seq, name, packet, flags)
        elif kind == "result":
            self._apply_result(seq, name, packet, flags)
        elif kind == "decision":
            self._apply_decision(seq, name, packet, flags)
        else:  # pragma: no cover - schema validation prevents this
            raise ValueError(f"unknown packet_type {kind!r}")

        # SHA_MISMATCH / DIRTY_TREE halt (above) only when their stop_on_* switch
        # is set; every other REJECT/BLOCK always halts the loop.
        governed = {"SHA_MISMATCH", "DIRTY_TREE"}
        rejects = sorted({f["code"] for f in flags if f["severity"] == "REJECT"} - governed)
        blocks = sorted({f["code"] for f in flags if f["severity"] == "BLOCK"} - governed)
        if rejects:
            self._halt(f"REJECTED_PACKET {'/'.join(rejects)} in {name}")
        if blocks:
            self._halt(f"BLOCKING_FLAG {'/'.join(blocks)} in {name}")
        self.cur["flags"].extend(flags)
        self._route()
        return flags

    # defect registration ----------------------------------------------------
    def _apply_defect(self, seq, name, p, flags):
        ori = p["ori_id"]
        if ori in self.cur["defects"]:
            self._flag(flags, "DUPLICATE_ORI", f"{ori} already registered", seq=seq, packet=name, ori_id=ori)
            return
        if p["state"] != "OPEN":
            self._flag(flags, "INVALID_REGISTRATION_STATE",
                       f"{ori} registered as {p['state']}; registration must be OPEN "
                       "(other states require an engineer decision packet)", seq=seq, packet=name, ori_id=ori)
            return
        d = {k: copy.deepcopy(v) for k, v in p.items() if k not in ("packet_type", "history")}
        d["state"] = None
        d["history"] = []
        d["implementer_claim"] = None
        d["warden_verification"] = None
        self._transition(d, "OPEN", seq=seq, packet=name, by=p["discovered_by"], owner=self.implementer,
                         next_action=f"{self.implementer}: fix and claim with a result packet")
        self.cur["defects"][ori] = d

    # mission ----------------------------------------------------------------
    def _apply_mission(self, seq, name, p, flags):
        mid = p["mission_id"]
        if mid in self.cur["missions"]:
            self._flag(flags, "DUPLICATE_MISSION", f"mission {mid} already exists", seq=seq, packet=name, mission_id=mid)
            return
        if self.role(p["assigned_to"]) == "UNKNOWN":
            self._flag(flags, "UNKNOWN_AGENT", f"assigned_to {p['assigned_to']!r} has no registered role",
                       seq=seq, packet=name, mission_id=mid)
            return
        for ori in p["ori_ids"]:
            if ori not in self.cur["defects"]:
                self._flag(flags, "MISSION_UNKNOWN_ORI", f"{ori} is not a registered ORI", seq=seq, packet=name,
                           mission_id=mid, ori_id=ori)
        ns = self.cur["night_shift"]
        if ns["loop_status"] == "HALTED":
            self._flag(flags, "MISSION_WHILE_HALTED",
                       "mission posted while Night Shift is halted; it will not be routed until Curtis resumes",
                       seq=seq, packet=name, mission_id=mid)
        self.cur["missions"][mid] = {
            "title": p["title"], "assigned_to": p["assigned_to"], "role": self.role(p["assigned_to"]),
            "created_by": p["created_by"], "created_at": p["created_at"], "branch": p["branch"],
            "required_start_sha": p["required_start_sha"], "ori_ids": list(p["ori_ids"]),
            "artifacts": list(p["artifacts"]), "status": "AWAITING_RESULT", "packet": name, "seq": seq,
            "result_packet": None,
        }
        self.cur["repository"] = p["repository"]
        self.cur["branch"] = p["branch"]
        if ns["starting_sha"] is None:
            ns["starting_sha"] = p["required_start_sha"]

    # result -----------------------------------------------------------------
    def _apply_result(self, seq, name, p, flags):
        mid, agent = p["mission_id"], p["agent"]
        ns = self.cur["night_shift"]
        m = self.cur["missions"].get(mid)
        kw = dict(seq=seq, packet=name, mission_id=mid)
        rec = {"seq": seq, "packet": name, "mission_id": mid, "agent": agent, "role": self.role(agent),
               "accepted": False, "start_sha": p["start_sha"], "final_sha": p["final_sha"],
               "verified_sha": p.get("verified_sha"), "stop_reason": p["stop_reason"],
               "tests_run": len(p["tests_run"]), "test_results": p["test_results"],
               "dispositions": {d["ori_id"]: d["disposition"] for d in p["ori_dispositions"]},
               "claimed_fixes": list(p["claimed_fixes"]),
               "new_oris": [n["ori_id"] for n in p.get("new_oris", [])]}
        self.cur["results"].append(rec)

        # ---- hard rejections
        if m is None:
            self._flag(flags, "UNKNOWN_MISSION", f"result for unknown mission {mid}", **kw)
            return
        if m["status"] != "AWAITING_RESULT":
            self._flag(flags, "DUPLICATE_RESULT", f"mission {mid} already has an accepted result ({m['result_packet']})", **kw)
        if agent != m["assigned_to"]:
            self._flag(flags, "WRONG_MISSION_AGENT", f"{agent} posted a result for {mid}, assigned to {m['assigned_to']}", **kw)
        if not sha_eq(p["start_sha"], m["required_start_sha"]):
            self._flag(flags, "SHA_MISMATCH", f"start_sha {short(p['start_sha'])} != mission required_start_sha "
                       f"{short(m['required_start_sha'])}", **kw)
            if ns["stop_on_sha_mismatch"]:
                self._halt(f"SHA_MISMATCH in {name}")
        if p["branch"] != m["branch"]:
            self._flag(flags, "BRANCH_MISMATCH", f"result branch {p['branch']!r} != mission branch {m['branch']!r}", **kw)
        verifier = self.is_verifier(agent)
        disp = p["ori_dispositions"]
        if not verifier:
            bad = [d["ori_id"] for d in disp if d["disposition"] in VERDICTS or d.get("verified_sha")]
            if bad or p.get("verified_sha"):
                self._flag(flags, "UNAUTHORIZED_VERIFICATION",
                           f"{agent} ({self.role(agent)}) attempted to issue verification verdicts for "
                           f"{', '.join(bad) or 'verified_sha'}; only an independent acceptance role may verify", **kw)
        else:
            bad = [d["ori_id"] for d in disp if d["disposition"] in IMPLEMENTER_ONLY] + list(p["claimed_fixes"])
            if bad:
                self._flag(flags, "INDEPENDENCE_VIOLATION",
                           f"auditor {agent} claimed implementation for {', '.join(sorted(set(bad)))}", **kw)
            for d in disp:
                if d["disposition"] in VERDICTS and not (d.get("verified_sha") or p.get("verified_sha")):
                    self._flag(flags, "MISSING_VERIFIED_SHA", f"{d['ori_id']} {d['disposition']} has no verified_sha",
                               ori_id=d["ori_id"], **kw)
        if any(f["severity"] == "REJECT" for f in flags):
            return

        # ---- accepted
        rec["accepted"] = True
        m["status"] = "RESULT_ACCEPTED"
        m["result_packet"] = name
        self.cur["latest_sha"] = p["final_sha"]
        ns["ending_sha"] = p["final_sha"]
        ns["budget_used"] = ns["budget_used"] + p.get("cost", 0)
        paths = {artifact_path(a) for a in p["artifacts"]}
        for a in m["artifacts"]:
            if a not in paths:
                self._flag(flags, "MISSING_ARTIFACT", f"required artifact not returned: {a}", **kw)
        claimed = list(dict.fromkeys(list(p["claimed_fixes"]) +
                                     [d["ori_id"] for d in disp if d["disposition"] == "FIXED"]))
        verdicts = [d for d in disp if d["disposition"] in VERDICTS]
        if not p["tests_run"] and (claimed or verdicts):
            self._flag(flags, "MISSING_TESTS", f"{agent} reported {'fix claims' if claimed else 'verdicts'} with no tests_run", **kw)
        if claimed and p["test_results"].get("failed", 0) + p["test_results"].get("errors", 0) > 0:
            self._flag(flags, "TESTS_FAILING", f"{agent} claims fixes while tests report failures", **kw)
        if claimed and not p["pushed"]:
            self._flag(flags, "NOT_PUSHED", f"{agent} claims fixes at {short(p['final_sha'])} but pushed=false", **kw)
        if p.get("working_tree_clean") is False:
            self._flag(flags, "DIRTY_TREE", f"{agent} reports a dirty working tree", **kw)
            if ns["stop_on_dirty_tree"]:
                self._halt(f"DIRTY_TREE in {name}")
        if verifier and p["files_changed"]:
            self._flag(flags, "AUDITOR_CHANGED_FILES", f"auditor {agent} changed files: {', '.join(p['files_changed'][:5])}", **kw)
        if p["stop_reason"] == "BLOCKED":
            self._flag(flags, "AGENT_BLOCKED", f"{agent} stopped BLOCKED", **kw)
        touched = set(claimed) | {d["ori_id"] for d in disp}
        for ori in sorted(touched - set(m["ori_ids"])):
            self._flag(flags, "ORI_OUT_OF_SCOPE", f"{ori} is not in mission {mid} ori_ids", ori_id=ori, **kw)
        for ori in m["ori_ids"]:
            if ori not in touched:
                self._flag(flags, "MISSING_DISPOSITION", f"no disposition returned for in-scope {ori}", ori_id=ori, **kw)

        decisions: list[dict] = list(p.get("engineer_decisions_required", []))
        if verifier:
            self._apply_verdicts(seq, name, p, m, flags, decisions)
        else:
            self._apply_claims(seq, name, p, claimed, flags, decisions)

        # new ORIs (any role may discover; Warden is the usual source)
        for n in p.get("new_oris", []):
            ori = n["ori_id"]
            if ori in self.cur["defects"]:
                self._flag(flags, "DUPLICATE_NEW_ORI", f"{ori} reported as new but already registered", ori_id=ori, **kw)
                continue
            d = {"ori_id": ori, "title": n["title"], "subsystem": n["subsystem"], "state": None,
                 "discovered_by": agent, "discovered_at": p.get("submitted_at") or m["created_at"],
                 "first_seen_sha": n.get("first_seen_sha") or p.get("verified_sha") or p["final_sha"],
                 "latest_tested_sha": n.get("first_seen_sha") or p.get("verified_sha") or p["final_sha"],
                 "reproducer": n["reproducer"], "evidence": list(n["evidence"]),
                 "implementer_claim": None, "warden_verification": None, "history": []}
            self._transition(d, "OPEN", seq=seq, packet=name, by=agent, owner=self.implementer,
                             next_action=f"{self.implementer}: fix new ORI (reproducer {clip(n['reproducer'])})",
                             note="new ORI reported in result")
            self.cur["defects"][ori] = d

        if p["stop_reason"] == "ENGINEER_DECISION_REQUIRED" and not decisions:
            decisions.append({"question": f"{agent} stopped with ENGINEER_DECISION_REQUIRED (see {name})"})
        for i, q in enumerate(decisions, 1):
            self.cur["engineer_decisions_required"].append({
                "id": f"EDR-{seq:04d}-{i}", "raised_by": agent, "packet": name, "mission_id": mid,
                "question": q["question"], "ori_id": q.get("ori_id"), "options": q.get("options", []),
                "resolved": False, "resolved_by": None})
        if decisions and ns["stop_on_engineer_decision"]:
            self._halt("ENGINEER_DECISION_REQUIRED")

        if verifier:
            ns["cycles_used"] += 1
            if ns["cycles_used"] >= ns["max_cycles"]:
                self._halt(f"MAX_CYCLES ({ns['cycles_used']}/{ns['max_cycles']})")
        if ns["budget_limit"] is not None and ns["budget_used"] >= ns["budget_limit"]:
            self._halt(f"BUDGET_EXHAUSTED ({ns['budget_used']}/{ns['budget_limit']})")

    def _apply_claims(self, seq, name, p, claimed, flags, decisions):
        agent, mid = p["agent"], p["mission_id"]
        kw = dict(seq=seq, packet=name, mission_id=mid)
        per = {d["ori_id"]: d for d in p["ori_dispositions"]}
        for ori in claimed:
            d = self.cur["defects"].get(ori)
            if d is None:
                self._flag(flags, "UNKNOWN_ORI", f"{agent} claimed fix for unregistered {ori}", ori_id=ori, **kw)
                continue
            sha = per.get(ori, {}).get("sha") or p["final_sha"]
            claim = {"agent": agent, "sha": sha, "mission_id": mid, "packet": name}
            if per.get(ori, {}).get("notes"):
                claim["notes"] = per[ori]["notes"]
            if d["state"] in WORK_STATES:
                d["implementer_claim"] = claim
                self._transition(d, "CLAIMED_FIXED", seq=seq, packet=name, by=agent, owner=self.auditor,
                                 next_action=f"{self.auditor}: independently verify {ori} at {short(sha)}",
                                 note="implementer claim — NOT closure")
            elif d["state"] == "CLAIMED_FIXED":
                d["implementer_claim"] = claim
                self._flag(flags, "RECLAIM", f"{ori} re-claimed at {short(sha)} while already CLAIMED_FIXED", ori_id=ori, **kw)
            else:
                self._flag(flags, "CLAIM_ON_CLOSED_STATE", f"{agent} claimed {ori} fixed but it is {d['state']}; no change",
                           ori_id=ori, **kw)
        for dd in p["ori_dispositions"]:
            ori, disp = dd["ori_id"], dd["disposition"]
            d = self.cur["defects"].get(ori)
            if disp in ("PROPOSE_DEFER", "PROPOSE_UNSUPPORTED", "ENGINEER_DECISION_REQUIRED"):
                decisions.append({"question": f"{agent} {disp} for {ori}: {dd.get('notes', 'see packet')}", "ori_id": ori})
            elif disp == "BLOCKED" and d is not None:
                d["next_action"] = f"{agent} BLOCKED: {dd.get('notes', 'see ' + name)}"
            if d is not None and dd.get("reproducer"):
                d["reproducer"] = dd["reproducer"]

    def _apply_verdicts(self, seq, name, p, m, flags, decisions):
        agent, mid = p["agent"], p["mission_id"]
        kw = dict(seq=seq, packet=name, mission_id=mid)
        for dd in p["ori_dispositions"]:
            ori, disp = dd["ori_id"], dd["disposition"]
            if disp == "ENGINEER_DECISION_REQUIRED":
                decisions.append({"question": f"{agent}: {ori}: {dd.get('notes', 'see packet')}", "ori_id": ori})
                continue
            if disp not in VERDICTS:
                continue
            d = self.cur["defects"].get(ori)
            if d is None:
                self._flag(flags, "UNKNOWN_ORI", f"{agent} issued {disp} for unregistered {ori}", ori_id=ori, **kw)
                continue
            vsha = dd.get("verified_sha") or p.get("verified_sha")
            repro = dd.get("reproducer")
            verification = {"auditor": agent, "verdict": disp, "verified_sha": vsha, "mission_id": mid, "packet": name}
            if repro:
                verification["reproducer"] = repro
            claim = d.get("implementer_claim")
            state = d["state"]
            if state == "CLAIMED_FIXED" and claim and not sha_eq(vsha, claim["sha"]):
                d["latest_tested_sha"] = vsha
                self._flag(flags, "VERIFIED_SHA_MISMATCH",
                           f"{agent} {disp} {ori} at {short(vsha)} but {claim['agent']} claimed the fix at "
                           f"{short(claim['sha'])}; verdict withheld", ori_id=ori, **kw)
                continue
            d["latest_tested_sha"] = vsha
            if disp == "PASS":
                if state == "CLAIMED_FIXED":
                    d["warden_verification"] = verification
                    self._transition(d, "WARDEN_VERIFIED", seq=seq, packet=name, by=agent, owner=self.engineer,
                                     next_action="None required; engineer may lock subsystem/regression when ready",
                                     note=f"independent PASS at {short(vsha)}")
                elif state in WORK_STATES:
                    self._flag(flags, "VERIFY_WITHOUT_CLAIM",
                               f"{agent} PASS for {ori} which is {state} (no implementer claim); verdict withheld",
                               ori_id=ori, **kw)
                elif state in ("WARDEN_VERIFIED", "LOCKED_REGRESSION"):
                    d["warden_verification"] = verification  # re-verification, no transition
                continue
            # FAIL
            if repro:
                d["reproducer"] = repro
            if dd.get("evidence"):
                d["evidence"] = list(dict.fromkeys(d["evidence"] + dd["evidence"]))
            d["warden_verification"] = verification
            nxt = f"{self.implementer}: fix {ori} (Warden FAIL at {short(vsha)}" + (f", reproducer {clip(repro)})" if repro else ")")
            if state == "CLAIMED_FIXED":
                self._flag(flags, "IMPLEMENTER_AUDITOR_CONFLICT",
                           f"{claim['agent'] if claim else 'implementer'} claimed {ori} FIXED at "
                           f"{short(claim['sha']) if claim else '?'}; {agent} FAIL at {short(vsha)}"
                           + (f" (reproducer {clip(repro)})" if repro else ""), ori_id=ori, **kw)
                self._transition(d, "REOPENED", seq=seq, packet=name, by=agent, owner=self.implementer,
                                 next_action=nxt, note="auditor FAIL of implementer claim")
            elif state in ("WARDEN_VERIFIED", "LOCKED_REGRESSION"):
                self._flag(flags, "REGRESSION", f"{ori} was {state}; {agent} FAIL at {short(vsha)}", ori_id=ori, **kw)
                self._transition(d, "REOPENED", seq=seq, packet=name, by=agent, owner=self.implementer,
                                 next_action=nxt, note="regression")
            elif state in WORK_STATES:
                d["next_action"] = nxt
            # DEFERRED / UNSUPPORTED: recorded, no transition (engineer-owned)

    # decision ---------------------------------------------------------------
    def _apply_decision(self, seq, name, p, flags):
        by = p["decided_by"]
        kw = dict(seq=seq, packet=name)
        if not self.is_engineer(by):
            self._flag(flags, "UNAUTHORIZED_DECISION", f"{by} ({self.role(by)}) may not post engineer decisions", **kw)
            return
        ns = self.cur["night_shift"]
        for k, v in p.get("night_shift", {}).items():
            ns[k] = v
        for o in p.get("defect_overrides", []):
            d = self.cur["defects"].get(o["ori_id"])
            if d is None:
                self._flag(flags, "UNKNOWN_ORI", f"override for unregistered {o['ori_id']}", ori_id=o["ori_id"], **kw)
                continue
            owner = self.implementer if o["state"] == "OPEN" else self.engineer
            self._transition(d, o["state"], seq=seq, packet=name, by=by, owner=owner,
                             next_action=(f"{self.implementer}: fix" if o["state"] == "OPEN"
                                          else f"None (engineer: {o['reason']})"), note=o["reason"])
        for o in p.get("subsystem_overrides", []):
            sub = o["subsystem"]
            if sub not in self.subsystem_names:
                self.subsystem_names.append(sub)
            if o["state"] == "LOCKED":
                open_oris = [d["ori_id"] for d in self.cur["defects"].values()
                             if d["subsystem"] == sub and d["state"] not in CLOSED_STATES]
                if open_oris:
                    self._flag(flags, "LOCK_WITH_OPEN_ORIS", f"{sub} locked with open ORIs {', '.join(open_oris)}", **kw)
                self.locks[sub] = True
                self.regressed[sub] = False
                for d in self.cur["defects"].values():
                    if d["subsystem"] == sub and d["state"] == "WARDEN_VERIFIED":
                        self._transition(d, "LOCKED_REGRESSION", seq=seq, packet=name, by=by, owner=self.engineer,
                                         next_action="None (locked by regression)", note=o["reason"])
            else:
                self.locks[sub] = False
                self.regressed[sub] = False
        if p.get("resolve_all_decisions") or p.get("resume_night_shift"):
            for e in self.cur["engineer_decisions_required"]:
                if not e["resolved"]:
                    e["resolved"] = True
                    e["resolved_by"] = name
            if "ENGINEER_DECISION_REQUIRED" in ns["halt_reasons"]:
                ns["halt_reasons"].remove("ENGINEER_DECISION_REQUIRED")
        if p.get("resume_night_shift"):
            ns["cycles_used"] = 0
            ns["halt_reasons"] = []
            ns["shift_started_seq"] = seq
            ns["starting_sha"] = None
            ns["ending_sha"] = None
        if not ns["halt_reasons"]:
            ns["loop_status"] = "RUNNING"

    # ---------------------------------------------------------------- routing
    def _work_route(self) -> tuple[str, str]:
        defects = self.cur["defects"]
        claimed = sorted(o for o, d in defects.items() if d["state"] == "CLAIMED_FIXED")
        work = sorted(o for o, d in defects.items() if d["state"] in WORK_STATES)
        if claimed:
            parts = [f"{o}@{short(defects[o]['implementer_claim']['sha'])}" for o in claimed]
            return self.auditor, f"Independently verify CLAIMED_FIXED {', '.join(parts)}"
        if work:
            parts = []
            for o in work:
                d = defects[o]
                parts.append(f"{o} ({d['state']}" + (f", reproducer {clip(d['reproducer'])})" if d.get("reproducer") else ")"))
            return self.implementer, f"Fix {', '.join(parts)} from {short(self.cur['latest_sha'])}"
        if defects:
            return self.engineer, "No open ORIs. Review verified ORIs / subsystem graduation"
        return self.engineer, "No ORIs registered. Register ORIs and post a first mission"

    def _route(self) -> None:
        ns = self.cur["night_shift"]
        unresolved = [e for e in self.cur["engineer_decisions_required"] if not e["resolved"]]
        pending = [(mid, m) for mid, m in self.cur["missions"].items() if m["status"] == "AWAITING_RESULT"]
        work_owner, work_action = self._work_route()
        if pending:
            mid, m = max(pending, key=lambda x: x[1]["seq"])
            work_owner, work_action = m["assigned_to"], f"Complete mission {mid} and post a result packet"
        if unresolved or ns["loop_status"] == "HALTED":
            self.cur["next_owner"] = self.engineer
            bits = []
            if unresolved:
                bits.append(f"{len(unresolved)} engineer decision(s) required")
            if ns["halt_reasons"]:
                bits.append("Night Shift halted: " + "; ".join(ns["halt_reasons"]))
            if work_owner == self.engineer:
                self.cur["next_action"] = ". ".join(bits) + f". {work_action}"
                self.cur["recommended_after_review"] = None
            else:
                self.cur["next_action"] = (". ".join(bits) + ". Review, then post a decision packet "
                                           "(resume_night_shift=true) to continue")
                self.cur["recommended_after_review"] = f"{work_owner}: {work_action}"
        else:
            self.cur["next_owner"], self.cur["next_action"] = work_owner, work_action
            self.cur["recommended_after_review"] = None

    # --------------------------------------------------------------- outputs
    def subsystem_status(self) -> dict:
        subs = {}
        defects = self.cur["defects"].values()
        for s in self.subsystem_names:
            mine = [d for d in defects if d["subsystem"] == s]
            open_oris = sorted(d["ori_id"] for d in mine if d["state"] not in CLOSED_STATES)
            verified = sorted(d["ori_id"] for d in mine if d["state"] in ("WARDEN_VERIFIED", "LOCKED_REGRESSION"))
            if self.locks.get(s) and self.regressed.get(s):
                st, note = "REOPENED_BY_REGRESSION", "Locked subsystem has a reopened/new ORI"
            elif self.locks.get(s):
                st, note = "LOCKED", "Locked by engineer decision"
            elif mine and not open_oris and verified:
                st, note = "CANDIDATE_FOR_GRADUATION", "All ORIs closed with independent verification; engineer decides lock"
            else:
                st, note = "DEVELOPMENT", "Open ORIs" if open_oris else "No independently verified ORIs yet"
            subs[s] = {"state": st, "open_oris": open_oris, "verified_oris": verified, "note": note}
        return {"kind": "switchboard.subsystem_status", "schema_version": 1, "subsystems": subs}

    def current(self) -> dict:
        return copy.deepcopy(self.cur)

"""Derived outputs: handoff packets, status text, morning brief."""
from __future__ import annotations

from .engine import CLOSED_STATES, WORK_STATES, clip, short

AUDIT_CRITERIA = [
    "Reproduce each ORI's reproducer at required_start_sha",
    "Issue PASS/FAIL per ORI with verified_sha",
    "Report any new defect as a NEW ORI with reproducer and evidence",
]
FIX_CRITERIA = [
    "Each ORI reproducer no longer reproduces",
    "Regression tests added/updated and passing",
    "Result packet lists tests_run, final_sha, pushed branch",
]


def _shift_flags(state: dict, all_history: bool = False) -> list[dict]:
    start = 0 if all_history else state["night_shift"]["shift_started_seq"]
    return [f for f in state["flags"] if (f.get("seq") or 0) >= start]


def build_handoff(state: dict, packet_prefix: str = "packets", implementer: str = "Anton",
                  auditor: str = "Warden") -> dict:
    ns = state["night_shift"]
    to = state["next_owner"]
    defects = state["defects"]
    last = state["history"]["last_packet"]
    seq = state["history"]["packet_count"]
    pending = sorted((m["seq"], mid) for mid, m in state["missions"].items() if m["status"] == "AWAITING_RESULT")
    running = ns["loop_status"] == "RUNNING" and to in (implementer, auditor)
    if not running:
        oris = sorted(o for o, d in defects.items() if d["state"] not in CLOSED_STATES)
    elif pending:
        oris = list(state["missions"][pending[-1][1]]["ori_ids"])
    elif to == auditor:
        oris = sorted(o for o, d in defects.items() if d["state"] == "CLAIMED_FIXED")
    else:
        oris = sorted(o for o, d in defects.items() if d["state"] in WORK_STATES)
    summary = []
    for o in oris:
        d = defects[o]
        item = {"ori_id": o, "state": d["state"], "subsystem": d["subsystem"], "reproducer": d["reproducer"]}
        if d.get("implementer_claim"):
            item["claimed_sha"] = d["implementer_claim"]["sha"]
        if d.get("warden_verification"):
            item["last_verdict"] = f"{d['warden_verification']['verdict']}@{short(d['warden_verification']['verified_sha'])}"
        summary.append(item)
    blocking = [f for f in _shift_flags(state) if f["severity"] in ("REJECT", "BLOCK")]
    edrs = [e for e in state["engineer_decisions_required"] if not e["resolved"]]
    refs = sorted({f"{packet_prefix}/{f['packet']}" for f in blocking if f.get("packet")} |
                  {f"{packet_prefix}/{e['packet']}" for e in edrs} |
                  ({f"{packet_prefix}/{last}"} if last else set()))
    suggested = None
    if running and not pending and oris:
        audit = to == auditor
        suggested = {
            "mission_id": f"{to.upper()}-{'-'.join(o.replace('-', '') for o in oris)}-{seq + 1:04d}",
            "title": ("Independent audit of " if audit else "Fix ") + ", ".join(oris),
            "assigned_to": to,
            "repository": state["repository"],
            "branch": state["branch"],
            "required_start_sha": state["latest_sha"],
            "ori_ids": oris,
            "scope": [f"{o}: {defects[o]['title']}" for o in oris],
            "acceptance_criteria": AUDIT_CRITERIA if audit else FIX_CRITERIA,
            "next_owner": implementer if audit else auditor,
        }
    return {
        "handoff_id": f"HANDOFF-{seq:04d}-{to}",
        "generated_at": state["history"]["last_timestamp"],
        "based_on_packet": last,
        "to": to,
        "reason": state["next_action"],
        "loop_status": ns["loop_status"],
        "halt_reasons": list(ns["halt_reasons"]),
        "repository": state["repository"],
        "branch": state["branch"],
        "required_start_sha": state["latest_sha"],
        "ori_ids": oris,
        "ori_summary": summary,
        "blocking_flags": blocking,
        "engineer_decisions_required": edrs,
        "recommended_after_review": state["recommended_after_review"],
        "suggested_mission": suggested,
        "packet_refs": refs,
    }


def status_text(state: dict, subsystems: dict) -> str:
    ns = state["night_shift"]
    h = state["history"]
    budget = f"{ns['budget_used']}/{ns['budget_limit'] if ns['budget_limit'] is not None else '∞'}"
    lines = [
        f"SWITCHBOARD STATUS — {state['repository']} @ {state['branch'] or '—'}",
        f"History: {h['packet_count']} packet(s); last {h['last_packet'] or '—'}",
        f"Latest SHA: {short(state['latest_sha'])}   Loop: {ns['loop_status']}   "
        f"cycles {ns['cycles_used']}/{ns['max_cycles']}   budget {budget}",
    ]
    if ns["halt_reasons"]:
        lines.append("Halt reasons: " + "; ".join(ns["halt_reasons"]))
    lines.append(f"NEXT OWNER: {state['next_owner']} — {state['next_action']}")
    if state["recommended_after_review"]:
        lines.append(f"After review: {state['recommended_after_review']}")
    lines.append("ORIs:")
    if not state["defects"]:
        lines.append("  (none)")
    for o, d in sorted(state["defects"].items()):
        lines.append(f"  {o:<9} {d['state']:<17} owner={d['current_owner']:<7} {d['subsystem']}: {d['title']}")
    edrs = [e for e in state["engineer_decisions_required"] if not e["resolved"]]
    if edrs:
        lines.append("Engineer decisions required:")
        lines += [f"  {e['id']} ({e['raised_by']}): {e['question']}" for e in edrs]
    flags = _shift_flags(state)
    if flags:
        lines.append("Flags this shift:")
        lines += [f"  [{f['severity']}] {f['code']}: {f['message']} ({f['packet']})" for f in flags]
    lines.append("Subsystems: " + ", ".join(f"{k}={v['state']}" for k, v in subsystems["subsystems"].items()))
    return "\n".join(lines) + "\n"


def morning_brief(state: dict, packet_prefix: str = "packets", all_history: bool = False,
                  subsystems: dict | None = None) -> str:
    ns = state["night_shift"]
    start = 0 if all_history else ns["shift_started_seq"]
    defects = state["defects"]
    results = [r for r in state["results"] if r["seq"] >= start]
    trans = [t for t in state["transitions"] if t["seq"] >= start]
    flags = _shift_flags(state, all_history)
    P = lambda name: f"{packet_prefix}/{name}"  # noqa: E731

    def tests(r):
        tr = r["test_results"]
        return f"tests {tr.get('passed', 0)} passed/{tr.get('failed', 0)} failed ({r['tests_run']} suites)"

    starting = ns["starting_sha"]
    ending = ns["ending_sha"]
    if all_history:
        firsts = [m for m in state["missions"].values()]
        starting = min(firsts, key=lambda m: m["seq"])["required_start_sha"] if firsts else None
        ending = state["latest_sha"]
    L = ["BACKPLANE BANDITS — NIGHT SHIFT",
         f"Repo/branch:  {state['repository']} @ {state['branch'] or '—'}",
         f"Starting SHA: {starting or '—'}",
         f"Ending SHA:   {ending or '—'}",
         f"Loop:         {ns['loop_status']} (cycles {ns['cycles_used']}/{ns['max_cycles']})"
         + (" — " + "; ".join(ns["halt_reasons"]) if ns["halt_reasons"] else "")]
    for role, label in (("IMPLEMENTER", "Anton"), ("AUDITOR", "Warden")):
        rs = [r for r in results if r["role"] == role]
        if not rs:
            L.append(f"{label + ':':<8}(no result this shift)")
        for r in rs:
            if not r["accepted"]:
                what = "REJECTED"
            elif role == "IMPLEMENTER":
                c = r["claimed_fixes"] or [o for o, v in r["dispositions"].items() if v == "FIXED"]
                what = (f"claims FIXED {', '.join(c)} @ {short(r['final_sha'])}" if c else r["stop_reason"])
            else:
                v = [f"{o} {d}" for o, d in sorted(r["dispositions"].items()) if d in ("PASS", "FAIL")]
                what = (", ".join(v) or r["stop_reason"]) + f" @ {short(r['verified_sha'] or r['final_sha'])}"
                if r["new_oris"]:
                    what += f"; NEW {', '.join(r['new_oris'])}"
            kind = "audit" if role == "AUDITOR" else "mission"
            L.append(f"{r['agent'] + ':':<8}{kind} {r['mission_id']} → {what}; {tests(r)}  [{P(r['packet'])}]")

    def lst(items):
        return ", ".join(items) if items else "—"

    verified = sorted({t["ori_id"] for t in trans if t["to"] == "WARDEN_VERIFIED"})
    reopened = []
    for o in sorted({t["ori_id"] for t in trans if t["to"] == "REOPENED"}):
        d = defects[o]
        extra = f"reproducer {clip(d['reproducer'])}" if d.get("reproducer") else ""
        reopened.append(f"{o} ({extra}; now {d['state']})" if extra else f"{o} (now {d['state']})")
    new = sorted({t["ori_id"] for t in trans if t["from"] is None and t["seq"] >= start
                  and "new ORI" in t.get("note", "")})
    registered = sorted({t["ori_id"] for t in trans if t["from"] is None} - set(new))
    L.append(f"Verified closed: {lst(verified)}")
    L.append(f"Reopened:        {lst(reopened)}")
    L.append(f"New:             {lst([f'{o} ({defects[o]['subsystem']}: {defects[o]['title']})' for o in new])}"
             + (f"   (registered: {', '.join(registered)})" if registered else ""))
    conflicts = [f for f in flags if f["severity"] != "REJECT" and f["code"] in (
        "IMPLEMENTER_AUDITOR_CONFLICT", "VERIFIED_SHA_MISMATCH", "REGRESSION")]
    L.append("Contradictions:  " + lst([f"{f['code']} {f.get('ori_id') or ''}".strip() for f in conflicts]))
    blockers = []
    for o, d in sorted(defects.items()):
        if d["state"] in WORK_STATES or d["state"] == "CLAIMED_FIXED":
            blockers.append(f"{o} {d['state']} (owner {d['current_owner']})")
    blockers += [f"[{f['severity']}] {f['code']} in {P(f['packet'])}" for f in flags if f["severity"] in ("REJECT", "BLOCK")]
    warns = sorted({f["code"] for f in flags if f["severity"] == "WARN" and f not in conflicts})
    L.append(f"Current blockers: {lst(blockers)}")
    if warns:
        L.append(f"Warnings:        {', '.join(warns)}")
    edrs = [e for e in state["engineer_decisions_required"] if not e["resolved"]]
    decisions = [f"{e['id']}: {e['question']} [{P(e['packet'])}]" for e in edrs]
    if ns["loop_status"] == "HALTED" and not decisions:
        decisions.append("Review shift; post a decision packet (resume_night_shift=true) only if more cycles are wanted")
    L.append("Curtis decisions required: " + lst(decisions))
    if subsystems:
        notable = [f"{k} {v['state']}" for k, v in subsystems["subsystems"].items() if v["state"] != "DEVELOPMENT"]
        if notable:
            L.append(f"Subsystems:      {', '.join(notable)}")
    if state["recommended_after_review"]:
        L.append(f"Next recommended action: {state['next_owner']} review → then {state['recommended_after_review']}")
    else:
        L.append(f"Next recommended action: {state['next_owner']} — {state['next_action']}")
    return "\n".join(L) + "\n"

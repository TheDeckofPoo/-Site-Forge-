# SWITCHBOARD — coordination / handoff data plane (MVP)

**Status:** MVP on `feature/switchboard-mvp` · stdlib-only Python · isolated under `coordination/switchboard/`.

Switchboard tracks missions, results, and ORI (defect) state for the Site Forge crew, and it
routes work to the next owner. It **does not** make engineering decisions, write PLC logic,
call LLM APIs, invoke agents, or change Site Forge compiler behavior. Its job is bookkeeping
with rules: normalize packets, keep an append-only history, apply deterministic transitions,
flag contradictions, and produce short handoff packets and a morning brief.

---

## 1. Architecture

```
 mission / result / defect / decision packets (JSON, schema-validated)
                │  post-* / decide / new-mission
                ▼
 packets/NNNN-<type>-<id>.json      ← append-only history (source of truth)
                │  Engine.apply() in seq order (pure; no clock, no network)
                ▼
 state/current.json + state/subsystem_status.json   ← derived; `rebuild` reproduces byte-for-byte
                │
                ├── status        (terminal summary)
                ├── next-handoff  → handoffs/HANDOFF-<seq>-<owner>.json (derived, never an input)
                └── morning-brief (one screen)
```

| File | Role |
|------|------|
| `coordination/switchboard/validator.py` | Small JSON Schema validator (subset of draft 2020-12; no `jsonschema` dependency) |
| `coordination/switchboard/engine.py` | State machine, routing, contradiction detection |
| `coordination/switchboard/store.py` | Packet history, validation-on-post, rebuild / drift check |
| `coordination/switchboard/reports.py` | Handoff, status, and morning brief rendering |
| `coordination/switchboard/cli.py` | `python -m coordination.switchboard …` |
| `coordination/switchboard/config.json` | Roles, Night Shift defaults, and the subsystem seed list |
| `coordination/switchboard/schema/*.schema.json` | mission, result, defect, decision, handoff, and state schemas |
| `coordination/switchboard/state/` | Committed initial state (empty history) |
| `coordination/switchboard/examples/replay_ori052/` | Committed end-to-end replay run: packets, state, handoff, and briefs |
| `coordination/switchboard/tests/` | unittest suite + `fixtures/replay_ori052/` |

## 2. Roles (`config.json`)

| Agent | Role | Can… | Cannot… |
|-------|------|------|---------|
| **Curtis** | ENGINEER | Final authority: resume Night Shift, resolve decisions, lock subsystems, DEFER / UNSUPPORTED an ORI | Verify (unless configured as a verification role) |
| Gilfoyle | COORDINATOR | Author missions | Verify, decide |
| **Anton** | IMPLEMENTER | Claim FIXED (→ `CLAIMED_FIXED` only), report NOT_FIXED/PARTIAL/BLOCKED, propose defer | Issue PASS/FAIL, set `verified_sha` |
| **Warden** | AUDITOR | PASS/FAIL per ORI with `verified_sha`, report NEW ORIs | Claim FIXED (independence) |
| Hunter | EVIDENCE | Return evidence artifacts via missions | Verify |

`verification_roles` (default `["AUDITOR"]`) names the independent acceptance roles. A future
second auditor ("Backplane Bandits") is added by giving it role `AUDITOR`.

## 3. States

**Defect (ORI):** `OPEN`, `CLAIMED_FIXED`, `WARDEN_VERIFIED`, `REOPENED`, `DEFERRED`, `UNSUPPORTED`, `LOCKED_REGRESSION`.

| From | Event | To | Next owner |
|------|-------|----|-----------|
| — | defect packet (must be OPEN) or NEW ORI in a result | OPEN | Anton |
| OPEN / REOPENED | implementer FIXED | CLAIMED_FIXED | Warden |
| CLAIMED_FIXED | auditor PASS at the claimed SHA | WARDEN_VERIFIED | Curtis (graduation review) |
| CLAIMED_FIXED | auditor FAIL (+ IMPLEMENTER_AUDITOR_CONFLICT) | REOPENED | Anton |
| WARDEN_VERIFIED / LOCKED_REGRESSION | auditor FAIL (+ REGRESSION) | REOPENED | Anton |
| WARDEN_VERIFIED | engineer locks the subsystem | LOCKED_REGRESSION | Curtis |
| any | engineer override | DEFERRED / UNSUPPORTED / OPEN | Curtis / Anton |

**Critical law:** an implementer's FIXED only reaches `CLAIMED_FIXED`. Only a verification role
can reach `WARDEN_VERIFIED`, and only from `CLAIMED_FIXED`, and only when `verified_sha`
matches the implementer's claimed SHA. There is no `CLOSED` state. If an implementer (or
Hunter, Gilfoyle, Curtis) submits PASS/FAIL or a `verified_sha`, the whole packet is rejected
(`UNAUTHORIZED_VERIFICATION`).

**Subsystem:** `DEVELOPMENT`, `CANDIDATE_FOR_GRADUATION` (all of its ORIs are closed and at least
one is independently verified), `LOCKED` (engineer decision only), and `REOPENED_BY_REGRESSION`
(a locked subsystem has a reopened or new ORI). Switchboard proposes candidates and never locks.

## 4. Packet formats

All packets carry `packet_type`. Full schemas are in `coordination/switchboard/schema/`.
Real examples are in `coordination/switchboard/tests/fixtures/replay_ori052/`.

* **mission:** `mission_id, title, created_at, created_by, assigned_to, repository, branch,
  required_start_sha, scope[], prohibited_scope[], ori_ids[], acceptance_criteria[], inputs[],
  artifacts[] (paths the result MUST return), authorization{granted_by, actions[], push_branch},
  stop_conditions[], expected_return{format}, next_owner` (+ optional `handoff_ref`, `notes`).
* **result:** `mission_id, agent, start_sha, final_sha, branch, pushed, files_changed[], tests_run[],
  test_results{passed, failed, errors?, skipped?, summary?}, artifacts[], ori_dispositions[],
  claimed_fixes[], unresolved_items[], deviations[], stop_reason, recommended_next_owner`.
  Optional: `submitted_at, verified_sha` (auditor), `working_tree_clean`, `new_oris[]`,
  `engineer_decisions_required[]`, `cost`.
  * `ori_dispositions[].disposition` ∈ `FIXED, NOT_FIXED, PARTIAL, BLOCKED, PROPOSE_DEFER,
    PROPOSE_UNSUPPORTED` (implementer) · `PASS, FAIL, NOT_TESTED` (auditor) · `ENGINEER_DECISION_REQUIRED` (either).
    Auditor entries carry `verified_sha` (or inherit the top-level value), plus `reproducer` and `evidence[]`.
  * `stop_reason: "ENGINEER_DECISION_REQUIRED"` or any `engineer_decisions_required[]` entry sets the marker.
* **defect** (registration and state record): `ori_id, title, subsystem, state, discovered_by, discovered_at,
  first_seen_sha, latest_tested_sha, reproducer, evidence[], implementer_claim, warden_verification,
  current_owner, next_action` (+ `history[]` in state).
* **decision** (Curtis only): `decision_id, decided_by, decided_at, summary`, plus the optional
  `resume_night_shift, resolve_all_decisions, defect_overrides[], subsystem_overrides[], night_shift{max_cycles, budget_limit}`.
* **handoff** (derived): `to, reason, loop_status, halt_reasons, required_start_sha, ori_ids, ori_summary,
  blocking_flags, engineer_decisions_required, recommended_after_review, suggested_mission, packet_refs`.

## 5. CLI

```
python -m coordination.switchboard [--root DIR] <command>
  status [--json]                   routing + ORIs + flags for this shift
  validate <file>... [--type T]     schema check only (never stores)
  post-defect <file>                register an ORI (state OPEN)
  new-mission [flags | --from-handoff H] [--dry-run]   build + post a mission
  post-mission <file>               post a mission JSON
  post-result <file>                post an Anton/Warden/Hunter result
  decide <file>                     engineer decision (resume / lock / defer)
  next-handoff [--no-write]         write handoffs/HANDOFF-<seq>-<owner>.json
  morning-brief [--all] [--out F]   one-screen Night Shift brief
  rebuild [--check]                 regenerate state/ from packets/ (--check: exit 1 on drift)
  replay <dir> [--strict]           post every *.json in a directory (filename order)
```

`--root` (or `SWITCHBOARD_ROOT`) points at an alternate data root. The default is
`coordination/switchboard`. Exit codes: 0 means OK, 1 means invalid, rejected, or drift, and 2 means a usage error.

Schema-invalid packets are **not stored**. Schema-valid packets are **always stored**, even when the
engine rejects them, so every rejection is auditable and `rebuild` reproduces it.

Tests: `python -m unittest discover -s coordination/switchboard/tests -t .` (or `python -m pytest coordination/switchboard/tests`).

## 6. Routing rules (deterministic, evaluated after every packet)

1. Unresolved engineer decision **or** loop HALTED → **Curtis**. `recommended_after_review` records
   who would be next otherwise.
2. A mission awaiting its result → that mission's `assigned_to`.
3. Any ORI in `CLAIMED_FIXED` → **Warden** (verify at the claimed SHA).
4. Any ORI in `OPEN` / `REOPENED` → **Anton** (from `latest_sha`, with the reproducer).
5. Otherwise → **Curtis** (graduation review).

The loop HALTS on: `ENGINEER_DECISION_REQUIRED` (when `stop_on_engineer_decision`), `cycles_used >= max_cycles`,
`budget_used >= budget_limit`, any REJECT or BLOCK flag, `SHA_MISMATCH` (when `stop_on_sha_mismatch`), or
`DIRTY_TREE` (when `stop_on_dirty_tree`). Only a Curtis decision packet with `resume_night_shift: true`
clears the halt. That packet also resolves open decisions, resets `cycles_used`, and starts a new shift.

### Contradiction and integrity flags

| Code | Severity | Trigger |
|------|----------|---------|
| `UNKNOWN_MISSION` | REJECT | result for a mission not in history |
| `WRONG_MISSION_AGENT` | REJECT | result agent ≠ mission `assigned_to` |
| `DUPLICATE_RESULT` | REJECT | mission already has an accepted result |
| `SHA_MISMATCH` | REJECT | result `start_sha` ≠ mission `required_start_sha` (abbreviated SHAs of ≥7 characters match by prefix) |
| `BRANCH_MISMATCH` | REJECT | result branch ≠ mission branch |
| `UNAUTHORIZED_VERIFICATION` | REJECT | a non-verification role issues PASS/FAIL or a `verified_sha` |
| `INDEPENDENCE_VIOLATION` | REJECT | an auditor claims FIXED/PARTIAL/proposes |
| `MISSING_VERIFIED_SHA` | REJECT | an auditor PASS/FAIL has no `verified_sha` |
| `UNAUTHORIZED_DECISION` / `UNKNOWN_AGENT` / `DUPLICATE_MISSION` / `DUPLICATE_ORI` / `INVALID_REGISTRATION_STATE` | REJECT | integrity |
| `VERIFIED_SHA_MISMATCH` | BLOCK | auditor verdict at a SHA ≠ implementer's claimed SHA → verdict withheld |
| `VERIFY_WITHOUT_CLAIM` | BLOCK | PASS on an ORI with no implementer claim → withheld |
| `UNKNOWN_ORI` | BLOCK | claim or verdict for an unregistered ORI |
| `DIRTY_TREE` | BLOCK | `working_tree_clean: false` |
| `IMPLEMENTER_AUDITOR_CONFLICT` | WARN | Anton claimed FIXED and Warden FAIL (the transition to REOPENED still applies) |
| `MISSING_ARTIFACT` | WARN | a mission `artifacts[]` path is not in the result |
| `MISSING_TESTS` | WARN | fix claims or verdicts with an empty `tests_run` |
| `TESTS_FAILING`, `NOT_PUSHED`, `ORI_OUT_OF_SCOPE`, `MISSING_DISPOSITION`, `RECLAIM`, `CLAIM_ON_CLOSED_STATE`, `REGRESSION`, `AGENT_BLOCKED`, `AUDITOR_CHANGED_FILES`, `DUPLICATE_NEW_ORI`, `MISSION_UNKNOWN_ORI`, `MISSION_WHILE_HALTED`, `LOCK_WITH_OPEN_ORIS` | WARN | surfaced in status and the brief |

The dividing line: a REJECT is any case where the packet cannot be tied to the right work, SHA,
branch, or authority, so it is not trusted at all. A BLOCK is a packet that is fine overall, but one
verdict or claim cannot be applied safely. A WARN is recorded and applied, and it stays visible.

## 7. Night Shift concept (designed, not automated)

`state/current.json → night_shift` holds these fields: `max_cycles` (default **1**), `cycles_used`,
`budget_limit` (null means unlimited), `budget_used` (the sum of result `cost`), `stop_on_engineer_decision`,
`stop_on_dirty_tree`, and `stop_on_sha_mismatch` (all true), plus `loop_status`, `halt_reasons`, `starting_sha`,
`ending_sha`, and `shift_started_seq`.

One cycle is one Anton result followed by one Warden result. With `max_cycles = 1`, the Night Shift runs
Anton → Warden, drafts the next Anton handoff, and then **stops for Curtis review**. `next_owner` is Curtis, and
`recommended_after_review` names the Anton work. Nothing runs automatically: a human or a future runner
reads `next-handoff` and invokes the agent.

## 8. Example: ORI-052 historical replay

`tests/fixtures/replay_ori052/` → committed run in `examples/replay_ori052/`:

| # | Packet | ORI-052 | Owner |
|---|--------|---------|-------|
| 1 | defect (Warden, first seen 444d222) | OPEN | Anton |
| 3 | Anton result FIXED @ 969eb83 | CLAIMED_FIXED | Warden |
| 5 | Warden FAIL @ 969eb83, reproducer TPNA1 (IMPLEMENTER_AUDITOR_CONFLICT; MAX_CYCLES halt) | REOPENED | Anton (after Curtis review) |
| 6 | Curtis decision: resume | — | Anton |
| 8 | Anton result FIXED @ c0de052* | CLAIMED_FIXED | Warden |
| 10 | Warden PASS @ c0de052* | WARDEN_VERIFIED | Curtis |

\* `c0de052…0052` is a synthetic SHA standing in for Anton's hypothetical re-fix. The fixtures are replay data, not real builds.

Generated brief (`examples/replay_ori052/MORNING_BRIEF.txt`):

```
BACKPLANE BANDITS — NIGHT SHIFT
Repo/branch:  TheDeckofPoo/-Site-Forge- @ feature/plc2-transport-fidelity
Starting SHA: 969eb83a9fe124e0e07614b40c1bd083d3bb1f5d
Ending SHA:   c0de052000000000000000000000000000000052
Loop:         HALTED (cycles 1/1) — MAX_CYCLES (1/1)
Anton:  mission ANTON-ORI052-02 → claims FIXED ORI-052 @ c0de052; tests 41 passed/0 failed (2 suites)  [coordination/switchboard/examples/replay_ori052/packets/0008-result-ANTON-ORI052-02-Anton.json]
Warden: audit WARDEN-ORI052-02 → ORI-052 PASS @ c0de052; tests 42 passed/0 failed (3 suites)  [coordination/switchboard/examples/replay_ori052/packets/0010-result-WARDEN-ORI052-02-Warden.json]
Verified closed: ORI-052
Reopened:        —
New:             —
Contradictions:  —
Current blockers: —
Curtis decisions required: Review shift; post a decision packet (resume_night_shift=true) only if more cycles are wanted
Subsystems:      Safety CANDIDATE_FOR_GRADUATION
Next recommended action: Curtis — Night Shift halted: MAX_CYCLES (1/1). No open ORIs. Review verified ORIs / subsystem graduation
```

## 9. Limitations (MVP)

* It does not invoke agents, call LLM/OpenAI/xAI APIs, run CI, merge, or push. Packets are written by humans or agents and posted with the CLI.
* It does not check SHAs or artifacts against git or the filesystem. Artifact checks compare path strings only, and SHA checks compare strings (by prefix for ≥7 characters).
* It uses one global Night Shift loop and one history per root. There is no locking against concurrent posts, so posts should be serialized.
* The JSON Schema validator implements only the subset of keywords that the schemas use.
* Roles are keyed by agent name from `config.json`. There is no authentication, so identity is whatever the packet claims.
* The subsystem seed (`Transport, Safety, Sorter, IO` = DEVELOPMENT) is a placeholder, not an engineering assessment.
* A rejected packet stays in history by design. Correct it by posting a new packet, never by editing history.

## 10. Future CI integration

* **Phase 2:** a CI job (GitHub Actions on the feature branch, read-only) runs `validate` and `rebuild --check` on any
  change under `coordination/switchboard/packets/`, and cross-checks result `final_sha` / `pushed` against
  `git ls-remote`. It also verifies that artifact paths exist at the SHA. The brief is posted as a job summary artifact, not as chat.
* **Phase 3:** a supervised runner (for example a self-hosted Windows runner for Studio-adjacent evidence) reads `next-handoff`,
  launches the named agent with the suggested mission, and posts the result packet. It stops on every halt condition above,
  with Curtis approval gates. Auto-merge and production pushes stay out of scope.

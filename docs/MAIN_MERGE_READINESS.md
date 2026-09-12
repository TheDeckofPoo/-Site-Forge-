# Main Merge Readiness

**Branch:** `feature/integration-hardening` (checkpoint / hardening tip)  
**Question:** Can this checkpoint merge to `main` now?

## Answer: **NO**

Conservative gate. Architecture review and Studio manual confirmation must land before any promote. Do **not** auto-merge.

Evidence snapshot: `exports/integration-hardening/summary.json` (`ready_for_main_merge: false`). Frozen blind pack under `exports/cp5-blind/` stays immutable.

---

## Blockers (must clear or explicitly waive)

| Blocker | Why it blocks |
|---------|----------------|
| **Studio manual test pending** | Static precheck ≠ Studio PASS. Curtis checklist in `exports/studio-validation/validation_checklist.md` is empty until import/open is recorded. |
| **Area still engineer-required** | No proven RUN Area membership. Suggested / provisional candidates only — finished-PLC Area names forbidden as generation rules. |
| **Safety membership CFG** | E-stop devices inventoriable; circuit/zone membership largely engineer-required. Safety zone logic must not pretend READY. |
| **Sorter partial** | Leaf generation only (encoder / induct / scanner / reason). Divert trigger and related leaves remain unsupported. No `Sorter_Track` monolith. |
| **WCS unsupported** | Messaging inventoriable; PLC generation `NOT_SUPPORTED`. |

Additional caution: transport relationships still need review; PE roles mix auto + engineer-required; many conveyor/motor gaps stay CONFIGURATION_REQUIRED.

---

## What may remain unsupported after a **future** merge

These are acceptable long-lived gaps if labeled honestly in UI / capability matrix — they are **not** merge excuses to fake READY:

- Divert trigger / confirm / rate limiting / recirculation / track offset
- Full WCS interface PLC (route response, heartbeat, divert confirm to host)
- `Sorter_Track` / shipping-sorter L3 gold-pack clones as “generation”
- Perfect Engineering Area auto-inference from RUN alone
- Behavioral / online Studio verification automation

A future merge may ship with these marked `GENERATION NOT SUPPORTED` / `CONFIGURATION REQUIRED` / `PARTIAL GENERATION` — never silently upgraded.

---

## Needs engineer confirmation

- Engineering Area split / rename / membership
- E-stop (and related safety) zone membership
- Sorter lane → divert IO map (readiness CFG; trigger still unsupported)
- Route / destination maps where CFG
- Any remaining PE / motor / VFD wiring marked engineer-required
- CP5 unresolved inclusion items (evidence-based only — not N/A alone, not finished PLC)

---

## Needs Studio test

Import each staged candidate in Studio 5000 and record results:

- `exports/studio-validation/ORNCCP2_knowledge_driven_candidate.L5X`
- `exports/studio-validation/ORNCCP4_knowledge_driven_candidate.L5X`
- `exports/studio-validation/ORNCCP5_candidate_v2.L5X`

Expect missing Main warnings, absent full Sorter_Track / WCS, and Safety blocked until membership confirmed. See `docs/STUDIO_IMPORT_PRECHECK.md`.

---

## Related

- `docs/PROJECT_SCORECARD.md`
- `docs/SORTER_LIBRARY_CONTRACT.md`
- `docs/UI_SUBSYSTEM_STATUS.md`
- `docs/INTEGRATION_READINESS.md`

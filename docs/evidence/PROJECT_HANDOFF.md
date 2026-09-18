# Project Handoff (5–10 minute orientation)

**Branch:** `feature/plc2-transport-fidelity`  
**Verify tip:** `git rev-parse HEAD` / `git log -5 --oneline`

> When reviewing or modifying a subsystem, reopen the authoritative raw evidence or reproducible acceptance artifact before making a new semantic claim. **Do not treat this summary as a substitute for raw evidence.**

---

## Current architecture

```
RUN → decoder (CP1–CP4 FROZEN + CP5A) → canonical models
    → engineer Apply → Autogen workbook → L5X
```

Partial builds: FOUND ≠ INCLUDED ≠ GENERATED. REVIEW does not block Build; ERROR on INCLUDED does.

---

## Frozen checkpoints

CP1 `bedcb7a` · CP2 `83dc7bb` · CP3 `d43abd6` · CP4 `e426152` — **do not rewrite**

Registry: [ACCEPTED_CHECKPOINTS.md](ACCEPTED_CHECKPOINTS.md)

---

## Current workstream

PLC5 Sorter foundation + I/O physical endpoint correction + Transport freeze + Evidence Authority docs.  
Tip at docs refresh time included `8c28daf` lineage — **always re-check `git log`**.

---

## Known accepted facts (pointers only)

| Area | Open |
|------|------|
| FortnaPlus semantics | [FORTNAPLUS_RUNTIME.md](FORTNAPLUS_RUNTIME.md) |
| Evidence authority | [../RUN_EVIDENCE_AUTHORITY.md](../RUN_EVIDENCE_AUTHORITY.md) |
| Transportation | [TRANSPORTATION_BASELINE.md](TRANSPORTATION_BASELINE.md) |
| Safety | [SAFETY_BASELINE.md](SAFETY_BASELINE.md) |
| Physical I/O | [PHYSICAL_IO_BASELINE.md](PHYSICAL_IO_BASELINE.md) |
| Sorter | [SORTER_BASELINE.md](SORTER_BASELINE.md) |

---

## Known REVIEW_REQUIRED

- Sorter divert output IO / track offsets / induct chain  
- Sorter_Track PLC generation (NOT STARTED)  
- Curve physical L/R elbow (UNKNOWN)  
- Residual PLC5 I/O class-E collisions (see plc5_io_collision_report)  
- Curtis visual acceptance on Flex width / two-rack viewport / CURVE angles  

---

## Do-not-break regressions

```bat
python tools/scripts/test_transportation_freeze.py
python tools/scripts/test_live_canonical_handoff.py
python tools/scripts/test_safety_membership_handoff.py
python tools/scripts/test_es_compiler.py
python tools/scripts/test_m220_aux_identity.py
python tools/scripts/test_plc5_io_endpoint_collision.py
python tools/scripts/test_plc5_sorter_discovery.py
python tools/scripts/test_cp4_merge.py
```

---

## No-cheating / no-speculation

- No finished-PLC discovery  
- No guessed topology / Safety membership  
- No fuzzy logical identity collapse  
- No site-name conditionals as production rules  
- No silencing duplicate OTE diagnostics  

---

## Subsystem maturity (summary)

| Subsystem | Status |
|-----------|--------|
| Hardware/I/O | Strong discovery + editing; visual polish READY FOR CURTIS ACCEPTANCE |
| Transportation | Freeze PASS; selection/handoff solid |
| Safety | Discovery + membership handoff + ES architecture; unassigned = REVIEW |
| Sorter | Blind discovery + UI foundation; **PLC generation NOT STARTED** |
| Sawtooth/Merge | Existing behavior preserved; not this handoff focus |
| PLC Autogen | Single L5X; partial build allowed |

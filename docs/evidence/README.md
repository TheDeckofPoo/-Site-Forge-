# Site Forge Evidence Index

**Primary refresh page** for Curtis, Gilfoyle, and future AI/review sessions.  
This is an **INDEX / REFRESHER**, not an oracle. Reopen raw evidence before new semantic claims.

**Current tip (verify):** `git rev-parse HEAD` on `feature/plc2-transport-fidelity`

---

## 1. What Site Forge is

Site Forge (repo folder: FortnaPlus) is an Electron + Python engineering tool that:

1. Imports a Fortna FPC / SortPlus **RUN** archive  
2. Discovers equipment, I/O, Safety, Transport, Sorter (when evidenced)  
3. Lets the engineer **review / correct / include**  
4. Compiles a supported Rockwell Studio 5000 **L5X**

It does **not** launch Studio 5000.

---

## 2. Greenfield vs Brownfield

| Mode | Meaning |
|------|---------|
| **Brownfield** | RUN exists → discover → engineer corrects → Build PLC |
| **Greenfield** | Manual / sparse configuration → Build what is INCLUDED |

Partial builds are first-class: **FOUND ≠ INCLUDED ≠ GENERATED**.

---

## 3. Architecture (always)

```
RUN (site evidence)
  ↓
Decoder / FortnaPlus semantics (.mnu + schema)
  ↓
Canonical SiteModel / subsystem models
  ↓
Engineer review / Apply
  ↓
Effective Autogen workbook
  ↓
PLC compiler → L5X
```

Finished PLC files are **validation oracles only** — never discovery or generation input.

---

## 4. Evidence authority philosophy

Authority depends on the **engineering fact**, not on “most important file.”

See: [`docs/RUN_EVIDENCE_AUTHORITY.md`](../RUN_EVIDENCE_AUTHORITY.md)  
Machine-readable: [`config/run_evidence_authority.json`](../../config/run_evidence_authority.json)

### Confidence vocabulary

| Level | Meaning |
|-------|---------|
| **PROVEN** | Explicit RUN value or accepted schema/runtime relationship |
| **DERIVED** | Deterministic transform from PROVEN evidence |
| **ENGINEER_ASSIGNED** | Engineer supplied/corrected; authoritative in effective model |
| **REVIEW_REQUIRED** | Evidence exists but is insufficient for a unique safe choice |
| **UNKNOWN** | No accepted evidence |

**Never:** GUESSED / ASSUMED / PROBABLY.

---

## 5. Source hierarchy (no confusion)

| Layer | Role |
|-------|------|
| **RAW RUN** | Site configuration evidence |
| **FortnaPlus + .mnu schema** | Interpretation / relationship semantics |
| **Accepted decoder tests/artifacts** | Reproducible proof of our interpretation |
| **Engineer canonical config** | Effective Site Forge project state |
| **Finished PLC** | Validation / reference oracle |
| **Documentation** | Summary / index of accepted evidence |

**Documentation NEVER outranks raw evidence.**

---

## 6. Two different “precedence” questions

1. **Which physical file does FortnaPlus open?**  
   `Table.rom.<MACHINE>` → `Table.rom` → `Table.asc.<MACHINE>` → `Table.asc`

2. **Which engineering table has semantic authority for this fact?**  
   Answered by the Evidence Authority Matrix — not the same as (1).

---

## 7. Subsystem baselines (open these)

| Doc | Purpose |
|-----|---------|
| [ACCEPTED_CHECKPOINTS.md](ACCEPTED_CHECKPOINTS.md) | Frozen / accepted / ready / review registry |
| [FORTNAPLUS_RUNTIME.md](FORTNAPLUS_RUNTIME.md) | .mnu / find_data_source / typed loader |
| [TRANSPORTATION_BASELINE.md](TRANSPORTATION_BASELINE.md) | Merges, chains, freeze counts |
| [SAFETY_BASELINE.md](SAFETY_BASELINE.md) | Discovery vs membership vs ES architecture |
| [PHYSICAL_IO_BASELINE.md](PHYSICAL_IO_BASELINE.md) | Logical vs RUN physical vs Logix endpoint |
| [SORTER_BASELINE.md](SORTER_BASELINE.md) | Blind RUN discovery vs PLC validation |
| [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md) | 5–10 minute orientation |

Also: [`docs/DOCUMENTATION_INDEX.md`](../DOCUMENTATION_INDEX.md) · [`docs/REGRESSION_MANIFEST.md`](../REGRESSION_MANIFEST.md) · [`exports/stabilization/README.md`](../../exports/stabilization/README.md)

---

## 8. Instruction for reviewers / AIs

When modifying a subsystem, **reopen the authoritative raw evidence or reproducible acceptance artifact** before making a new semantic claim. Do not treat this summary as a substitute for raw evidence.

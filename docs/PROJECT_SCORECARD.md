# Project Scorecard (Integration Hardening)

**Branch:** `feature/integration-hardening`  
**Rule:** Score honestly. Do not inflate unsupported leaves to READY / GENERATED.  
**Evidence:** `exports/integration-hardening/`, discovery/compiler packs, Studio precheck (static only).

Scale per dimension: **Strong / Partial / Thin / None**.

| Dimension | Meaning |
|-----------|---------|
| **Discovery** | RUN → inventory / SiteModel with provenance |
| **Modeling** | Generic schema / capability contracts |
| **Engineer UX** | Override / status surface for remaining gaps |
| **Generation** | Generic library path emits L5X structure |
| **Validation** | Oracle / tests beyond generation inputs; Studio download separate |

---

## Transport

| Discovery | Modeling | Engineer UX | Generation | Validation |
|:---------:|:--------:|:-----------:|:----------:|:----------:|
| Strong | Strong | Partial | Strong | Partial |

- Included equipment + PE/IO paths proven on CP2/CP4/CP5 candidates.
- Relationships often still need review; PE roles mix auto + engineer-required.
- XML/structural validation exists; **Studio download not claimed**.

## Safety / Area / ES

| Discovery | Modeling | Engineer UX | Generation | Validation |
|:---------:|:--------:|:-----------:|:----------:|:----------:|
| Partial | Partial | Thin | Thin | Thin |

- E-stop **devices** inventoriable from RUN; **zone membership** mostly engineer-required (CFG).
- Engineering Area has no reliable RUN table — provisional / suggested candidates only; engineer confirmation required.
- Do **not** copy finished-PLC Area names into generation.
- Safety logic emit blocked until membership confirmed → UI: CONFIGURATION REQUIRED / BLOCKED for zone logic.

## Sawtooth

| Discovery | Modeling | Engineer UX | Generation | Validation |
|:---------:|:--------:|:-----------:|:----------:|:----------:|
| Strong (CP4) | Strong | Partial | Partial | Partial |

- CP4 path: detected, parameterized, candidate emit with explicit config gaps.
- CP5: **N/A** (0 sawtooth merges) — absence is correct, not a failure.
- Some pack symbols remain engineer config; no invented gold constants.

## Sorter

| Discovery | Modeling | Engineer UX | Generation | Validation |
|:---------:|:--------:|:-----------:|:----------:|:----------:|
| Strong | Partial | Thin | Partial | Thin |

- Entity / encoder / scan / track / WCS tables discoverable.
- Leaf contract in `docs/SORTER_LIBRARY_CONTRACT.md`.
- **Generated leaves (partial):** encoder/speed, induct, scanner association, reason code.
- **Still unsupported:** track offset, destination response, divert trigger/confirm/rate, recirculation.
- Divert readiness / route request = CONFIGURATION_REQUIRED.
- **No** `Sorter_Track` monolith. Divert trigger = `NOT_SUPPORTED`.

## WCS

| Discovery | Modeling | Engineer UX | Generation | Validation |
|:---------:|:--------:|:-----------:|:----------:|:----------:|
| Partial | Partial | Thin | None | None |

- Topics / queues / MsgMap inventoriable (`MODELED`).
- Route request CFG; route response / divert confirm / heartbeat `NOT_SUPPORTED`.
- PLC generation: **GENERATION NOT SUPPORTED** (gold WCS pack ≠ generic path).

## Studio

| Discovery | Modeling | Engineer UX | Generation | Validation |
|:---------:|:--------:|:-----------:|:----------:|:----------:|
| n/a | n/a | Partial | n/a | Thin |

- Static preflight (`fortna_studio_preflight.py`) green on staged CP2/CP4/CP5 candidates.
- Manual Studio import / open **pending** — precheck ≠ PASS.
- See `docs/STUDIO_IMPORT_PRECHECK.md`, `exports/studio-validation/`.

---

## Headline

| Subsystem | Honest headline |
|-----------|-----------------|
| Transport | Strongest path; Studio still pending |
| Safety / Area / ES | Discoverable devices; membership + Area remain engineer gates |
| Sawtooth | CP4 workable; CP5 N/A |
| Sorter | Partial leaf generation only |
| WCS | Inventory/model; generation unsupported |
| Studio | Static OK; manual test required |

**Do not merge main on this scorecard alone.**

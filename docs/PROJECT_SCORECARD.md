# Project Scorecard (Integration Hardening)

**Branch:** `feature/connectivity-sorter-closure`  
**Rule:** Score honestly. Do not inflate unsupported leaves to READY / GENERATED.  
**Evidence:** discovery/compiler packs, sorter-research, Studio precheck (static only).

Scale per dimension: **Strong / Partial / Thin / None**.

| Dimension | Meaning |
|-----------|---------|
| **Discovery** | RUN → inventory / SiteModel with provenance |
| **Modeling** | Generic schema / capability contracts |
| **Engineer UX** | Override / status surface for remaining gaps |
| **Generation** | Generic library path emits L5X structure |
| **Validation** | Oracle / tests beyond generation inputs; Studio download separate |

---

## Product decisions (Area / ES)

| Decision | Disposition |
|----------|-------------|
| Area auto-discovery | **NOT REQUIRED** — engineer workflow is **REQUIRED** |
| E-stop zone auto-reconstruction | **NOT REQUIRED** |

Default `Area_1` / `EStop_Zone_1` plus engineer move/rename is the supported path. Do **not** list Area or ES auto-discovery as architectural blockers when that workflow works. Finished-PLC Area names remain forbidden as generation rules.

**Connectivity fidelity** (equipment links, PE/lane/takeaway hints with honest confidence, CFG vs NOT_SUPPORTED labels) is a **major quality metric**.

---

## Transport

| Discovery | Modeling | Engineer UX | Generation | Validation |
|:---------:|:--------:|:-----------:|:----------:|:----------:|
| Strong | Strong | Partial | Strong | Partial |

- Included equipment + PE/IO paths proven on CP2/CP4/CP5 candidates.
- Relationships / connectivity fidelity still need review; PE roles mix auto + engineer-required.
- XML/structural validation exists; **Studio download not claimed**.

## Safety / Area / ES

| Discovery | Modeling | Engineer UX | Generation | Validation |
|:---------:|:--------:|:-----------:|:----------:|:----------:|
| Partial | Partial | Partial | Thin | Thin |

- E-stop **devices** inventoriable from RUN; zone membership via engineer workflow (default `EStop_Zone_1` + move/rename) — auto-reconstruction **not required**.
- Engineering Area: default `Area_1` + engineer confirm/rename — auto-discovery **not required**.
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

- Entity / encoder / scan / track / WCS tables discoverable; divert map modeled from `SrtZoneLane` (see `docs/SORTER_DIVERT_MODEL.md`).
- Leaf contract in `docs/SORTER_LIBRARY_CONTRACT.md`.
- **Generated:** encoder/speed, induct, scanner association, reason code.
- **Modeled:** token schema.
- **CFG:** track offset (`ticks_per_foot` known; `offset_counts` engineer), divert readiness / output IO.
- **NOT_SUPPORTED:** divert trigger (until offset + token + IO + timing proven), confirm/rate, recirculation, destination response.
- **No** `Sorter_Track` monolith.

## WCS

| Discovery | Modeling | Engineer UX | Generation | Validation |
|:---------:|:--------:|:-----------:|:----------:|:----------:|
| Partial | Partial | Thin | None | None |

- Topics / queues / MsgMap inventoriable (`MODELED`).
- Route request CFG; route response / divert confirm / heartbeat `NOT_SUPPORTED`.
- PLC generation: **GENERATION NOT SUPPORTED** (gold WCS pack ≠ generic path). WCS remains **mostly unsupported**.

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
| Transport | Strongest path; connectivity fidelity is the quality bar; Studio still pending |
| Safety / Area / ES | Engineer workflow required; auto-discovery not a blocker |
| Sawtooth | CP4 workable; CP5 N/A |
| Sorter | Encoder/induct/scanner/reason generated; token modeled; offset/readiness CFG; trigger unsupported |
| WCS | Mostly unsupported (inventory/model only) |
| Studio | Static OK; manual test required |

**Do not merge main on this scorecard alone.**

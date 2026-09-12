# Activity Classification Model

**Status:** Binding for RUN SiteModel activity + inclusion  
**Implementation:** `tools/scripts/fortna_activity_classify.py`  
**Related:** `docs/RUN_DISCOVERY_MODEL.md`, `docs/SITEMODEL_V2.md`, `docs/RUN_TABLE_PRECEDENCE.md`

Evidence-driven. Docs supply semantics; RUN supplies facts. Stale rows are never deleted — only classified.

---

## Activity states

| State | Meaning |
|-------|---------|
| `ACTIVE_CONFIRMED` | Strong cross-table / I/O / overlay proof of live participation |
| `ACTIVE_LIKELY` | Controller-scoped or scored presence without full confirmation |
| `INACTIVE_CONFIRMED` | Explicit documented offline / disable (not N/A or blank) |
| `HISTORICAL_OR_STALE` | `old.*` / historical scope, or confirmed supersession |
| `CANDIDATE` | Weak reference only (geometry neighbor, numbering hint, low score) |
| `UNKNOWN` | Insufficient positive evidence |

---

## Inclusion buckets

| Bucket | Meaning |
|--------|---------|
| `INCLUDED` | In machine scope, active enough for this pass, not overridden out |
| `AVAILABLE` | Present / related, but not selected (out of scope, candidate, review) |
| `EXCLUDED` | Inactive confirmed, historical/stale, or engineer-excluded |

Hard rule: `INACTIVE_CONFIRMED` / `HISTORICAL_OR_STALE` are **never** `INCLUDED`.

---

## High-confidence evidence sources

Positive activity weight comes from explicit RUN relationships and controller ownership, including:

1. **Motor startup chains** — `Mtrchain` / `Motor_Chained*` / `Motor_Aux` / stop-zone links (`FPC-Motor-Startup-Chains`)
2. **Jam / full / fulljam** — `Jamcheck` / `Fullline` / `Fulljam` / `Jamzones` sensor↔conveyor↔response links (`FPC-Fulls-Jams-Fulljams`)
3. **Start/stop zones** — `StartStopZones` ↔ `Jamzones` (Latch Bit → Mtrchain Motor_Aux) (`FPC-StartStopZones`)
4. **Sawtooth** — `SawLane` / `SawMerge` / `HSSaw*` lane & merge participation
5. **Sorter static config** — named sorter table rows (static config ≠ runtime track slots)
6. **I/O assignment ownership** — Configio / FORTNADT / IOCard / View I/O / controller I/O words
7. **Controller overlay presence** with valid current I/O or explicit enable
8. **Explicit machine ownership** when `Machine_Name` is a real controller id (not N/A)

Scoring weights and thresholds live in `fortna_activity_classify.py` (`EVIDENCE_WEIGHTS`, `SCORE_ACTIVE_CONFIRMED=5`, `SCORE_ACTIVE_LIKELY=3`).

---

## Forbidden as sole proof

Do **not** use any of the following alone to activate, deactivate, include, exclude, or mark stale:

- ASC **row order**
- **Number matching** / P-tag sequencing
- **Suffix assumptions** (PE role, zone kind, etc.)
- **`N/A` / `NA` alone**
- **Blank optional fields alone**
- **Absence from one unrelated table**

Row order and numbering may appear only as supporting / zero-weight hints.

---

## Ambiguous field policy (mandatory)

Values in `{N/A, NA, blank, NONE, NULL, ?, -, --, UNKNOWN, INVALID, …}`:

- **MUST NOT** deactivate, exclude, mark stale, or prevent generation
- **MAY** appear under Source Evidence as `ambiguous_ownership_evidence` with `automatic_activity_weight=0`

**`Machine_Name=N/A` (or blank/NONE)** means **ambiguous ownership**, not inactive device. Fall back to positive cross-table / overlay / I/O evidence; never force `EXCLUDED` from the placeholder alone.

`Disable I/O` alone is also not automatic deactivation.

---

## Decision record (every object)

Every classification writes:

| Field | Role |
|-------|------|
| `evidence_for[]` | Positive reasons |
| `evidence_against[]` | Negative / limiting reasons |
| `source_tables[]` | Tables consulted |
| `confidence` | `HIGH` / `MEDIUM` / `LOW` / `UNKNOWN` |
| `engineer_override` | Override blob when present (wins over classifier) |
| `generation_reason` | Why generation state was chosen |

Also preserved when relevant: `activity_score`, `activity_score_breakdown`, `source_evidence_notes`.

---

## Distinct operational object types

Do not conflate catalogs or identities:

| Keep distinct | Not the same as |
|---------------|-----------------|
| ES / E-stop **device** | ES / E-stop **zone** |
| Full **PE** | Full **group** / Fulljam zone |
| Jamcheck / jam **PE** | Jam **zone** |
| StartStop **zone** | Engineering **Area** |
| Sorter host / scan **zone** | StartStop island |
| Motor | VFD / drive |
| Conveyor (equipment) | Path / geometry candidate only |

Area rename propagates to equipment `area_id` only — never silently renames Jam / ES / StartStop / Full / Sorter zones.

---

## Supersession

- `superseded_candidates[]` records overlay winners vs historical losers.
- State `SUPERSEDED_CANDIDATE` **never auto-deletes** a row.
- Auto-exclude as `HISTORICAL_OR_STALE` only when engineer-confirmed, or `confidence=HIGH` with definitive `replacement_relationship` (see classifier). Candidates alone stay reviewable.

---

## Summary rules

1. Explicit RUN relationships beat numbering.
2. Row order is supporting only.
3. N/A / blank / NONE alone never deactivate or block generation.
4. Stale rows stay in the model as `AVAILABLE` / `EXCLUDED` — never deleted.
5. Engineer override wins and must be recorded.

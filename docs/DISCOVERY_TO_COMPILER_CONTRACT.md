# Discovery → Compiler Contract

**Branch:** `feature/cp5-gap-closure`  
**Policy:** RUN + SiteModel + generic libraries + engineer config only. Finished / answer-sheet PLC is a validation oracle — never a generation input.

---

## Entity flow

```text
RUN (.tar.gz / ASC)
  → SiteModel (discovery + knowledge enrichment)
    → AutogenInput (compiler-facing projection)
      → L5X (Studio candidate)
```

| Stage | Owns | Must not |
|-------|------|----------|
| RUN | Raw tables, overlays, project identity | Invent Area / PE roles / topology |
| SiteModel | Inclusion, roles, relationships, provenance, capability state | Import finished PLC names or constants |
| AutogenInput | Conveyors, PE devices, IO points, areas, modules for emit | Silently drop discovered entities |
| L5X | Structural programs / tags / tasks | Be claimed GENERATED without containing the structure |

Correct load path: `fortna_autogen.load_from_run` enriched by SiteModel roles (PE roles, area assignment, inclusion, motor/VFD classification). Do not hand-build a thin `AutogenInput` that bypasses RUN IO/PE extraction.

---

## Required fields per entity

Fields below are the minimum for a row to be eligible for generation. Missing required fields → disposition `CONFIGURATION_REQUIRED` (or earlier exclusion disposition), not silent invent.

### Conveyor

| Field | Required | Notes |
|-------|----------|-------|
| Identity (`raw_name` / `normalized_name` / P-tag) | yes | Mechanical conveyor only |
| `inclusion` | yes | Only `INCLUDED` may generate |
| `main_area` / `area_id` | yes | Default `Area_1` is engineer-required when RUN has no Area |
| Equipment / drive type | yes | Selects template family (MS / VFD / MDR / …) |
| Template resolvable in library | yes | Else `NO_TEMPLATE` |
| Downstream / next conveyor | preferred | `NO_Conv` only when explicitly unknown |
| PE wiring slots (exit / jam / full / product) | preferred | From SiteModel PE roles + RUN linkage |
| Motor / VFD linkage | preferred | Else Slow_Flt / drive path stays CONFIGURATION_REQUIRED |

### PE (photoeye)

| Field | Required | Notes |
|-------|----------|-------|
| Device name / tag | yes | |
| Linked conveyor (when owned) | yes for conveyor wiring | Orphan PE may still appear in IO_MAP |
| Role (`pe_roles` / product / jam / full / …) | preferred | Knowledge+RUN; engineer confirms LOW confidence |
| IO bank / bit or EIP map | preferred | Needed for IO_MAP points |

### IO point

| Field | Required | Notes |
|-------|----------|-------|
| Device name | yes | |
| Direction (I/O) | yes | |
| Source module / bank / bit (or EIP word map) | yes for mapped emit | Unmapped → CONFIGURATION_REQUIRED |
| Device type / kind | preferred | PE / MS / VFD / station / … |
| Controller scope | yes | Must belong to this machine |

### Encoder

| Field | Required | Notes |
|-------|----------|-------|
| Identity | yes | |
| Owning subsystem link (sawtooth / sorter / tracking) | preferred | |
| Enable / reset / pulse wiring | preferred | Stub tags only when CONFIGURATION_REQUIRED |

### Zone (operational — not Engineering Area)

| Field | Required | Notes |
|-------|----------|-------|
| Zone kind | yes | E-stop / StartStop / Jam / Full / Sorter host — distinct catalogs |
| Zone name | yes | |
| Ownership / members evidence | preferred | From RUN tables; do not invent |
| Engineering Area id | optional | Zones must not be renamed when Area renames |

---

## Disposition enum

Every discovered / candidate entity that does not emit (or that does) carries an explicit disposition:

| Disposition | Meaning |
|-------------|---------|
| `NOT_MECHANICAL_CONVEYOR` | Row is not a mechanical conveyor (PE, VFD, station, placeholder, …) |
| `DUPLICATE` | Same identity already represented by a canonical row |
| `SUPERSEDED` | Overlay / newer identity replaces this historical row |
| `INACTIVE` | Confirmed inactive / offline / excluded by activity |
| `UNSUPPORTED_TYPE` | Type known but no compiler path |
| `NO_TEMPLATE` | No matching generic library template |
| `CONFIGURATION_REQUIRED` | Evidence incomplete; engineer must decide before emit |
| `GENERATOR_BUG` | Should have emitted; failure is compiler-side |
| `INTENTIONALLY_EXCLUDED` | Engineer or policy excluded |
| `GENERATED` | Structure present in the emitted L5X |

---

## Capability lifecycle

Capabilities (conveyor fast/slow, PE logic, IO map, sorter divert, WCS, …) advance only forward when evidence and library path justify it:

```text
DISCOVERED
  → MODELED
    → GENERATABLE
      → REQUESTED_FOR_GENERATION
        → GENERATED
          → STRUCTURALLY_VALIDATED
            → BEHAVIORALLY_VALIDATED
```

| State | Gate |
|-------|------|
| DISCOVERED | RUN inventory exists with provenance |
| MODELED | SiteModel / editor fields defined without inventing values |
| GENERATABLE | Generic library path can emit from RUN + overrides |
| REQUESTED_FOR_GENERATION | Build pass selected this capability |
| GENERATED | Emitted L5X **contains** the corresponding structure |
| STRUCTURALLY_VALIDATED | XML / tag / routine structural checks pass |
| BEHAVIORALLY_VALIDATED | Post-generation oracle / Studio behavior accepted (separate from generate) |

### Hard rule — matrix vs L5X

The generation support matrix **must not** report `GENERATED` unless the L5X contains the structure for that capability. Inventory or modeling alone is never `GENERATED`.

---

## Separation — validation must not import into generation

```text
RUN + SiteModel + engineer config + generic libraries
        ↓
     GENERATE (AutogenInput → L5X)
        ↓
-------- VALIDATION BARRIER --------
        ↓
finished PLC / prints / answer-sheet / comparator
```

- Validation and answer-sheet tools must not write into SiteModel, workbook, Transport graph, or AutogenInput.
- Area names, PE maps, divert maps, and task rates from finished PLC are oracles only.
- See `docs/SOURCE_OF_TRUTH_POLICY.md`.

---

## Blind v1 gap (CP5) — do not repeat

PLC5 blind v1 (`fortna_cp5_blind_build.generate_supported_l5x`) hard-capped conveyors at **40** and built a thin `AutogenInput` **without** `pe_devices` / `io_points`. Result: 79 INCLUDED conveyors discovered, 40 emitted, `pe_device_count=0`, `io_point_count=0`.

**Correct path for gap closure:**

1. Discover + enrich SiteModel (roles, inclusion, areas).
2. Build AutogenInput via `fortna_autogen.load_from_run`.
3. Overlay SiteModel roles / area / inclusion onto that input.
4. Emit full INCLUDED set (no arbitrary cap) with PE + IO when RUN provides them.
5. Mark matrix `GENERATED` only for structures actually present in L5X.

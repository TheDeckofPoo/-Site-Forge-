# Accepted Checkpoint Registry

Status vocabulary:

| Status | Meaning |
|--------|---------|
| **FROZEN** | Do not rewrite; regression-locked |
| **ACCEPTED** | Curtis field/architecture acceptance recorded |
| **READY FOR CURTIS ACCEPTANCE** | Implemented + automated tests; awaiting visual/field OK |
| **REVIEW_REQUIRED** | Incomplete / unresolved semantics |
| **SUPERSEDED** | Replaced by a later checkpoint |

Automated tests alone do **not** equal ACCEPTED.

---

## FROZEN — CP1–CP4

### CP1 — Fortna .mnu runtime archaeology

| | |
|---|---|
| **SHA** | `bedcb7a51ed0ac368ee3e9de8c6ff947aaa94352` |
| **Status** | **FROZEN** |
| **Purpose** | `.mnu` schema / `find_data_source` archaeology |
| **Reproduce** | `python tools/scripts/test_fortna_mnu_schema.py` · `test_fortna_mnu_runtime.py` |
| **Docs** | `docs/FORTNAPLUS_MNU_SCHEMA.md`, `docs/FORTNAPLUS_MNU_RUNTIME.md` |

### CP2 — Typed RUN loader

| | |
|---|---|
| **SHA** | `83dc7bb503f704c94a23be984ed4ee59b57fc69c` |
| **Status** | **FROZEN** |
| **Purpose** | Generic typed RUN loader |
| **Reproduce** | `python tools/scripts/test_fortna_run_loader.py` |
| **Docs** | `docs/FORTNAPLUS_RUN_LOADER.md` |

### CP3 — Relationship graph

| | |
|---|---|
| **SHA** | `d43abd698f2820c32942e8aabcbc1497bea8e42e` |
| **Status** | **FROZEN** |
| **Purpose** | Generic relationship resolver / cross-site acceptance |
| **Reproduce** | `python tools/scripts/test_fortna_mnu_runtime.py` (relationship portions) · related CP3 tests |
| **Docs** | `docs/FORTNAPLUS_MNU_RELATIONSHIPS.md`, `docs/FORTNAPLUS_RELATIONSHIP_MODEL.md` |

### CP4 — Semantic adapters

| | |
|---|---|
| **SHA** | `e4261521c0a5c0f3f00b7b8ac66d2093da4caa9d` |
| **Status** | **FROZEN** |
| **Purpose** | Semantic adapters (merge, jam, mtrchain, safety, transport) |
| **Reproduce** | `python tools/scripts/test_cp4_bundle.py` · `test_cp4_merge.py` · `test_cp4_transportation.py` |
| **Known REVIEW** | Some site-specific adapter completeness; do not rewrite core |

### CP5A — Decoder → Transport integration

| | |
|---|---|
| **SHA** | `9ec550a` (lineage) |
| **Status** | **ACCEPTED** (integration into RUN import + Transportation) |
| **Reproduce** | `python tools/scripts/test_cp5a_integration.py` |

---

## Later major checkpoints (plc2-transport-fidelity)

| SHA (short) | Status | Purpose |
|-------------|--------|---------|
| `58fb309` | READY→merged lineage | Transport hit geometry + Safety ES shell |
| `8231b5a` | ACCEPTED (product contract) | Partial build: FOUND≠INCLUDED≠GENERATED |
| `ccb2acd` | READY FOR CURTIS ACCEPTANCE (Safety E2E) | Membership handoff + ES zone emit + operand validator |
| `60e62eb` | ACCEPTED (live handoff fix) | Engineer Areas/Safety reach L5X (not ORNCCP2 defaults) |
| `99ab6ee` | READY FOR CURTIS ACCEPTANCE | Transport freeze + Evidence Authority + Sorter archaeology |
| `8c28daf` | READY FOR CURTIS ACCEPTANCE | PLC5 sorter autobuild foundation + I/O bank collision fix + UI polish |

**Verify tip:** `git rev-parse HEAD` — do not trust stamped SHAs in older README offline tables without `git log`.

---

## How to use this registry

1. Before editing a frozen layer → STOP; open this page + CP docs.  
2. Before claiming “accepted” → check Status column, not only CI.  
3. Before Sorter/I/O claims → open subsystem baselines under `docs/evidence/`.
